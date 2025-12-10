"""Aggressive Volume Concentration Index (AVCI) calculator.

AVCI measures how concentrated aggressive volume is within a time window —
whether a few large taker orders dominate, or volume is spread across many
small taker orders.

Core formula:
    AVCI(T) = Σ_j (v_j / V)² = Σ_2 / V²

Where:
    v_j = per-taker volume contribution
    V = total volume
    Σ_2 = sum of squared per-taker volumes

Range: AVCI ∈ [1/N, 1]
    - = 1 when one taker accounts for all volume
    - = 1/N when volume is split equally across N takers
"""

from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Deque, Dict, Tuple

from .timestamp import normalize_timestamp_to_ms


@dataclass
class AvciConfig:
    """Configuration for AVCI calculator."""
    window_ms: int  # Sliding window width in milliseconds


class _AvciBucket:
    """Internal bucket maintaining AVCI state for one side (combined/buy/sell).

    Maintains O(1) incremental updates using:
        - deque of fills (timestamp, taker_id, qty) in timestamp order
        - vol_by_taker dict for per-taker volume
        - Running scalars: V (total), sigma_2 (sum of squared volumes), N (count)
    """

    def __init__(self) -> None:
        # Deque of (timestamp_ms, taker_id, qty) in arrival order
        self._fills: Deque[Tuple[int, str, Decimal]] = deque()
        # Per-taker accumulated volume
        self._vol_by_taker: Dict[str, Decimal] = {}
        # Running totals
        self._V: Decimal = Decimal("0")  # Total volume
        self._sigma_2: Decimal = Decimal("0")  # Sum of squared per-taker volumes
        self._N: int = 0  # Count of active takers

    def insert(self, timestamp_ms: int, taker_id: str, qty: Decimal) -> None:
        """Insert a fill into the bucket with O(1) update."""
        self._fills.append((timestamp_ms, taker_id, qty))

        # Get old volume for this taker
        old_vol = self._vol_by_taker.get(taker_id, Decimal("0"))
        new_vol = old_vol + qty

        # Update running totals
        self._V += qty
        # Σ_2 = Σ_2 - x² + (x+q)²
        self._sigma_2 = self._sigma_2 - (old_vol * old_vol) + (new_vol * new_vol)

        # Update taker count if new taker
        if old_vol == 0:
            self._N += 1

        self._vol_by_taker[taker_id] = new_vol

    def evict_before(self, cutoff_ms: int) -> None:
        """Evict fills with timestamp < cutoff_ms with O(k) where k = evicted count."""
        while self._fills and self._fills[0][0] < cutoff_ms:
            _, taker_id, qty = self._fills.popleft()

            old_vol = self._vol_by_taker.get(taker_id, Decimal("0"))
            new_vol = old_vol - qty

            # Update running totals
            self._V -= qty
            # Σ_2 = Σ_2 - x² + (x-q)²
            self._sigma_2 = self._sigma_2 - (old_vol * old_vol) + (new_vol * new_vol)

            if new_vol <= 0:
                # Taker fully evicted
                self._vol_by_taker.pop(taker_id, None)
                self._N -= 1
            else:
                self._vol_by_taker[taker_id] = new_vol

    def get_metrics(self) -> Dict[str, Any]:
        """Compute and return current metrics."""
        if self._V <= 0:
            return {
                "avci": None,
                "avci_excess": None,
                "N": 0,
                "V": Decimal("0"),
            }

        avci = self._sigma_2 / (self._V * self._V)
        avci_excess = Decimal(self._N) * avci - Decimal("1")

        return {
            "avci": avci,
            "avci_excess": avci_excess,
            "N": self._N,
            "V": self._V,
        }

    def get_state(self) -> Dict[str, Any]:
        """Return serializable state for persistence."""
        return {
            "fills": [(ts, tid, str(q)) for (ts, tid, q) in self._fills],
            "vol_by_taker": {k: str(v) for k, v in self._vol_by_taker.items()},
            "V": str(self._V),
            "sigma_2": str(self._sigma_2),
            "N": self._N,
        }

    def restore_from_state(self, state: Dict[str, Any]) -> None:
        """Restore state from serialized dict."""
        self._fills = deque(
            (int(ts), str(tid), Decimal(str(q))) for ts, tid, q in state.get("fills", [])
        )
        self._vol_by_taker = {
            k: Decimal(str(v)) for k, v in state.get("vol_by_taker", {}).items()
        }
        self._V = Decimal(str(state.get("V", "0")))
        self._sigma_2 = Decimal(str(state.get("sigma_2", "0")))
        self._N = int(state.get("N", 0))


class AvciCalculator:
    """Calculator for Aggressive Volume Concentration Index with side variants.

    Maintains three buckets:
        - combined: all fills regardless of side
        - buy: only buy fills (side = +1)
        - sell: only sell fills (side = -1)
    """

    def __init__(self, config: AvciConfig) -> None:
        if config.window_ms <= 0:
            raise ValueError("window_ms must be positive")

        self.config = config
        self._combined = _AvciBucket()
        self._buy = _AvciBucket()
        self._sell = _AvciBucket()

    def add_fill(self, fill: Any) -> None:
        """Add an L3 fill to the calculator.

        Args:
            fill: Object with timestamp, taker_order_id, side (+1/-1), qty attributes.
        """
        ts_ms = normalize_timestamp_to_ms(fill.timestamp)
        taker_id = fill.taker_order_id
        qty = Decimal(str(fill.qty))
        side = fill.side

        # Always add to combined bucket
        self._combined.insert(ts_ms, taker_id, qty)

        # Add to side-specific bucket
        if side == 1:
            self._buy.insert(ts_ms, taker_id, qty)
        elif side == -1:
            self._sell.insert(ts_ms, taker_id, qty)

    def evict_to(self, current_time_ms: int) -> None:
        """Evict fills older than window from current time.

        Args:
            current_time_ms: Current timestamp (window end).
        """
        ts_ms = normalize_timestamp_to_ms(current_time_ms)
        cutoff_ms = ts_ms - self.config.window_ms

        self._combined.evict_before(cutoff_ms)
        self._buy.evict_before(cutoff_ms)
        self._sell.evict_before(cutoff_ms)

    def get_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Return metrics for all three buckets.

        Returns:
            Dict with keys 'combined', 'buy', 'sell', each containing:
                - avci: AVCI value (None if V=0)
                - avci_excess: N * AVCI - 1 (None if V=0)
                - N: active taker count
                - V: total volume
        """
        return {
            "combined": self._combined.get_metrics(),
            "buy": self._buy.get_metrics(),
            "sell": self._sell.get_metrics(),
        }

    def get_state(self) -> Dict[str, Any]:
        """Return serializable state for persistence."""
        return {
            "config": {
                "window_ms": self.config.window_ms,
            },
            "combined": self._combined.get_state(),
            "buy": self._buy.get_state(),
            "sell": self._sell.get_state(),
        }

    def restore_from_state(self, state: Dict[str, Any]) -> None:
        """Restore state from serialized dict."""
        cfg = state.get("config", {})
        window_ms = int(cfg.get("window_ms", 10000))
        if window_ms <= 0:
            raise ValueError("window_ms must be positive")
        self.config = AvciConfig(window_ms=window_ms)

        self._combined = _AvciBucket()
        self._combined.restore_from_state(state.get("combined", {}))

        self._buy = _AvciBucket()
        self._buy.restore_from_state(state.get("buy", {}))

        self._sell = _AvciBucket()
        self._sell.restore_from_state(state.get("sell", {}))
