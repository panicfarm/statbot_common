import logging
from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from typing import Deque, List, Mapping, Optional, Tuple

from .timestamp import normalize_timestamp_to_ms


def compute_exponential_weights(k_levels: int, half_life_ticks: Decimal) -> List[Decimal]:
    """Compute exponential distance weights with half-life in ticks.

    w_k = 2^{- (k-1) / HL}, k=1..K

    Uses exact integer exponents when (1/HL) is an integer, otherwise falls back
    to exp/ln for fractional exponents.
    """
    if k_levels <= 0:
        raise ValueError("k_levels must be positive")
    if half_life_ticks <= Decimal("0"):
        raise ValueError("half_life_ticks must be positive")

    weights: List[Decimal] = []
    inv_hl = (Decimal(1) / half_life_ticks)
    inv_hl_int = inv_hl.to_integral_value()

    if inv_hl == inv_hl_int:
        # Exact integer step per tick: exponent is integer => exact powers of 2
        step = int(inv_hl_int)
        for k in range(1, k_levels + 1):
            exponent = (k - 1) * step
            weights.append(Decimal(1) / (Decimal(2) ** exponent))
        return weights

    # Fallback: fractional exponent via exp/ln using decimal context for portability
    from decimal import getcontext
    ln2 = getcontext().ln(Decimal(2))
    for k in range(1, k_levels + 1):
        exponent = - (Decimal(k - 1) / half_life_ticks) * ln2
        weights.append(getcontext().exp(exponent))
    return weights


def sizes_on_tick_grid(
    best_bid: Decimal,
    best_ask: Decimal,
    tick_size: Decimal,
    k_levels: int,
    bids: Mapping[Decimal, Decimal],
    asks: Mapping[Decimal, Decimal],
) -> Tuple[List[Decimal], List[Decimal]]:
    """Return size arrays on a tick-normalized grid around the touch.

    Missing grid levels are padded with zero.
    """
    if tick_size <= Decimal("0"):
        raise ValueError("tick_size must be positive")
    if k_levels <= 0:
        raise ValueError("k_levels must be positive")

    bid_sizes: List[Decimal] = []
    ask_sizes: List[Decimal] = []
    for i in range(k_levels):
        bid_px = best_bid - (tick_size * Decimal(i))
        ask_px = best_ask + (tick_size * Decimal(i))
        bid_sizes.append(bids.get(bid_px, Decimal("0")))
        ask_sizes.append(asks.get(ask_px, Decimal("0")))
    return bid_sizes, ask_sizes


def compute_ib(
    bid_sizes: List[Decimal],
    ask_sizes: List[Decimal],
    weights: List[Decimal],
) -> Optional[Decimal]:
    """Compute instantaneous imbalance IB_t from weighted queues (normalized).

    IB = (D_bid - D_ask) / (D_bid + D_ask), None if denominator == 0.
    """
    if len(bid_sizes) != len(ask_sizes) or len(bid_sizes) != len(weights):
        raise ValueError("bid_sizes, ask_sizes, and weights must have equal length")

    d_bid = Decimal("0")
    d_ask = Decimal("0")
    for s_b, s_a, w in zip(bid_sizes, ask_sizes, weights):
        d_bid += w * s_b
        d_ask += w * s_a

    denom = d_bid + d_ask
    if denom == Decimal("0"):
        return None
    return (d_bid - d_ask) / denom


def compute_queue_diff(
    bid_sizes: List[Decimal],
    ask_sizes: List[Decimal],
    weights: List[Decimal],
) -> Optional[Decimal]:
    """Compute raw queue imbalance QI_t from weighted queues.

    QI = D_bid - D_ask (unbounded). Returns None if both D_bid and D_ask are zero.
    """
    if len(bid_sizes) != len(ask_sizes) or len(bid_sizes) != len(weights):
        raise ValueError("bid_sizes, ask_sizes, and weights must have equal length")

    d_bid = Decimal("0")
    d_ask = Decimal("0")
    for s_b, s_a, w in zip(bid_sizes, ask_sizes, weights):
        d_bid += w * s_b
        d_ask += w * s_a

    if d_bid == Decimal("0") and d_ask == Decimal("0"):
        return None
    return d_bid - d_ask


@dataclass
class QueueImbalanceConfig:
    k_levels: int
    tick_size: Decimal
    half_life_ticks: Decimal
    window_ms: int


class QueueImbalanceCalculator:
    """Maintains instantaneous QI_t and its time-weighted mean over a window.

    QI_t is treated as piecewise-constant between update times.
    """

    def __init__(self, config: QueueImbalanceConfig) -> None:
        if config.window_ms <= 0:
            raise ValueError("window_ms must be positive")
        self.config = config
        self.weights: List[Decimal] = compute_exponential_weights(
            config.k_levels, config.half_life_ticks
        )
        # Closed segments of (start_ms, end_ms, value)
        self._segments: Deque[Tuple[int, int, Decimal]] = deque()
        # Current open segment (start_ms, value), if any
        self._current_start_ms: Optional[int] = None
        self._current_value: Optional[Decimal] = None
        # Last processed time (ms), for monotonicity checks
        self._last_time_ms: Optional[int] = None

    def update_from_book(
        self,
        t_ms: int,
        best_bid: Optional[Decimal],
        best_ask: Optional[Decimal],
        bids: Mapping[Decimal, Decimal],
        asks: Mapping[Decimal, Decimal],
    ) -> Optional[Decimal]:
        """Compute QI_t from the provided book snapshot and update segments.

        Returns the instantaneous QI_t (or None if undefined).
        """
        now_ms = normalize_timestamp_to_ms(t_ms)
        if self._last_time_ms is not None and now_ms < self._last_time_ms:
            # Enforce monotonic time progression
            logging.warning(
                "QueueImbalance received out-of-order timestamp: %s < last %s; "
                "clamping to last seen time",
                now_ms,
                self._last_time_ms,
            )
            now_ms = self._last_time_ms
        self._last_time_ms = now_ms

        qi_value: Optional[Decimal] = None
        if best_bid is not None and best_ask is not None:
            bid_sizes, ask_sizes = sizes_on_tick_grid(
                best_bid=best_bid,
                best_ask=best_ask,
                tick_size=self.config.tick_size,
                k_levels=self.config.k_levels,
                bids=bids,
                asks=asks,
            )
            # Use raw queue difference as the instantaneous indicator value
            qi_value = compute_queue_diff(bid_sizes, ask_sizes, self.weights)

        # Segment management (piecewise-constant QI)
        prev_val = self._current_value
        prev_start = self._current_start_ms

        if prev_val is None:
            # Previously undefined
            if qi_value is not None:
                # Start new open segment
                self._current_start_ms = now_ms
                self._current_value = qi_value
        else:
            # Previously defined
            if qi_value is None:
                # Close existing segment at now_ms
                if prev_start is not None and now_ms > prev_start:
                    self._segments.append((prev_start, now_ms, prev_val))
                self._current_start_ms = None
                self._current_value = None
            elif qi_value != prev_val:
                # Close previous and start new segment
                if prev_start is not None and now_ms > prev_start:
                    self._segments.append((prev_start, now_ms, prev_val))
                self._current_start_ms = now_ms
                self._current_value = qi_value
            else:
                # Value unchanged: keep open segment as-is
                pass

        return qi_value

    def _prune(self, window_start_ms: int) -> None:
        while self._segments and self._segments[0][1] <= window_start_ms:
            self._segments.popleft()

    def get_time_weighted_mean(self, current_time_ms: int) -> Optional[Decimal]:
        """Return time-weighted mean of QI over [T - W, T]."""
        T = normalize_timestamp_to_ms(current_time_ms)
        window_start = T - self.config.window_ms
        self._prune(window_start)

        num = Decimal("0")
        den = Decimal("0")

        # Closed segments
        for seg_start, seg_end, val in self._segments:
            if seg_end <= window_start or seg_start >= T:
                continue
            start = max(seg_start, window_start)
            end = min(seg_end, T)
            if end > start:
                dt = Decimal(end - start)
                num += val * dt
                den += dt

        # Open segment up to T
        if self._current_value is not None and self._current_start_ms is not None:
            seg_start = self._current_start_ms
            if seg_start < T:
                start = max(seg_start, window_start)
                end = T
                if end > start:
                    dt = Decimal(end - start)
                    num += self._current_value * dt
                    den += dt

        if den == Decimal("0"):
            return None
        return num / den

    def get_state(self) -> dict:
        return {
            "config": {
                "k_levels": self.config.k_levels,
                "tick_size": str(self.config.tick_size),
                "half_life_ticks": str(self.config.half_life_ticks),
                "window_ms": self.config.window_ms,
            },
            "segments": [
                [int(s), int(e), str(v)] for (s, e, v) in self._segments
            ],
            "current": None
            if self._current_value is None or self._current_start_ms is None
            else [int(self._current_start_ms), str(self._current_value)],
            "last_time_ms": self._last_time_ms,
        }

    def restore_from_state(self, state: dict) -> None:
        cfg = state.get("config", {})
        self.config = QueueImbalanceConfig(
            k_levels=int(cfg.get("k_levels", 10)),
            tick_size=Decimal(cfg.get("tick_size", "0.01")),
            half_life_ticks=Decimal(cfg.get("half_life_ticks", "0.5")),
            window_ms=int(cfg.get("window_ms", 30000)),
        )
        self.weights = compute_exponential_weights(
            self.config.k_levels, self.config.half_life_ticks
        )
        self._segments.clear()
        for s, e, v in state.get("segments", []):
            self._segments.append((int(s), int(e), Decimal(v)))
        cur = state.get("current")
        if cur is None:
            self._current_start_ms = None
            self._current_value = None
        else:
            self._current_start_ms = int(cur[0])
            self._current_value = Decimal(cur[1])
        self._last_time_ms = state.get("last_time_ms")


