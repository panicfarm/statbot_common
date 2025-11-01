# Depth/Queue Imbalance — statbot_common implementation

This document defines the Depth/Queue Imbalance indicator implemented in `statbot_common` and the library API exposed to applications.

## Scope and responsibilities

- Implemented here (library, exchange-agnostic):
  - Tick-normalized depth extraction around the touch up to `K` levels, padding missing ticks with zero size
  - Exponential distance-weighting by tick distance using a half-life parameter (in ticks)
  - Instantaneous imbalance IB_t from weighted bid/ask queues
  - Time-weighted sliding-window mean of IB_t over an adjustable window W
  - Timestamp normalization to milliseconds and state snapshot/restore
- Expected from the caller (application layer):
  - Provide best bid/ask, tick size, and full depth maps at each evaluation time
  - Decide when to invoke updates (typically on L2 updates that change top-of-book/depth)
  - Configure K, half-life, and window length; handle persistence/plotting

---

## 1) Notation and definitions

- Let `tick_size > 0` be the minimum price increment for the instrument.
- Let `K ≥ 1` be the number of tick levels per side to include, starting at the touch.
- Let $V_b^{(k)}$ and $V_a^{(k)}$ be the posted size on bid/ask at distance $k$ ticks from the touch (k=1 is best bid/ask). If a tick level is absent in the raw book, treat its size as 0.
- Exponential weights via half-life `HL` (in ticks):

```math
w_k = 2^{- (k-1) / \text{HL}}
```

  with `HL > 0`. Example: `HL = 0.5` gives `w_1 = 1.0, w_2 = 0.25, w_3 = 0.0625, ...`.

- Distance-weighted queue sizes:

```math
D_{\text{bid}} = \sum_{k=1}^{K} w_k \cdot V_b^{(k)}
```

```math
D_{\text{ask}} = \sum_{k=1}^{K} w_k \cdot V_a^{(k)}
```

- Instantaneous imbalance (bounded):

```math
\text{IB}_t = \frac{D_{\text{bid}} - D_{\text{ask}}}{D_{\text{bid}} + D_{\text{ask}}} \in (-1, 1)
```
  
  If `D_bid + D_ask = 0`, return `None` (undefined).

---

## 2) Tick grid mapping (from raw book)

Given best bid `p^b`, best ask `p^a`, and `tick_size`:
- Bid grid levels: `p^b - (k-1)*tick_size` for k=1..K
- Ask grid levels: `p^a + (k-1)*tick_size` for k=1..K
- For each grid price, read posted size from the raw book maps; if missing, use 0. Size inputs and outputs use `Decimal`.

---

## 3) Time-weighted mean over a sliding window

Let the current time be `T` (ms) and the window width be `W` (ms). Treat `IB_t` as piecewise-constant between updates (e.g., L2 changes). Maintain segments `(start_ms, end_ms, ib_value)` that fall within `[T-W, T]`. The time-weighted mean is:

```math
\text{queue\_imbalance\_tw}(T) = \frac{\sum \text{ib\_value} \cdot \Delta t}{\sum \Delta t}
```

where the sum is over segments within the window and `Δt` is the segment overlap with `[T-W, T]`.

If no covered time exists in-window, return `None`.

---

## 4) API outline

- `QueueImbalanceConfig(k_levels: int, tick_size: Decimal, half_life_ticks: Decimal, window_ms: int)`
- `QueueImbalanceCalculator(config)`
  - `update_from_book(t_ms: int, best_bid: Decimal, best_ask: Decimal, bids: Mapping[Decimal, Decimal], asks: Mapping[Decimal, Decimal]) -> Optional[Decimal]`
    - Computes current `IB_t` from the provided book snapshot (tick-normalized) and returns it (or `None` if undefined). Also updates the internal piecewise-constant segment ending at `t_ms`.
  - `get_time_weighted_mean(current_time_ms: int) -> Optional[Decimal]`
    - Returns `queue_imbalance_tw` over `[current_time_ms - window_ms, current_time_ms]`.
  - `get_state() -> dict` / `restore_from_state(state: dict) -> None`

- Utilities (exposed for testing):
  - `compute_exponential_weights(k_levels: int, half_life_ticks: Decimal) -> List[Decimal]`
  - `sizes_on_tick_grid(best_bid: Decimal, best_ask: Decimal, tick_size: Decimal, k_levels: int, bids: Mapping[Decimal, Decimal], asks: Mapping[Decimal, Decimal]) -> Tuple[List[Decimal], List[Decimal]]`
  - `compute_ib(bid_sizes: List[Decimal], ask_sizes: List[Decimal], weights: List[Decimal]) -> Optional[Decimal]`

All functions use `Decimal` for prices/sizes/weights; timestamps are normalized to milliseconds.

---

## 5) Edge handling

- If either side of the book is missing best price, skip update and return `None`.
- If `tick_size <= 0` or `half_life_ticks <= 0`, do not compute and log a warning.
- If `D_bid + D_ask = 0`, `IB_t` is `None`.
- Window with no covered time returns `None`.

---

## 6) Usage constraints

- Call `update_from_book` whenever L2 updates change depth (especially the touch). Pass the timestamp of that update in milliseconds.
- The indicator is defined from L2 only (no L3 required).
- The library treats the series as right-continuous per update times to compute the time-weighted mean.

---

## 7) Defaults

- Default half-life: `0.5` ticks (very front-heavy weighting).
- Default behavior does not normalize weights; the ratio is scale-invariant.

---

## 8) Interpretation (brief)

- `IB_t ≈ 0`: balanced queues near the touch
- `IB_t >> 0`: more weighted depth on the bid side (supportive)
- `IB_t << 0`: more weighted depth on the ask side (resistance)
- Rapid sustained cross of the time-weighted mean can indicate a structural shift in passive liquidity.


