## Markout Skew (Information Content) — statbot_common implementation

This document captures the parts of the Markout Skew spec that are implemented in `statbot_common`.

### Scope and responsibilities

- Implemented here (library, exchange-agnostic):
  - Aggregation of coalesced L3 prints by timestamp and side (buy/sell)
  - Horizon scheduling for clock-time and event-time horizons
  - Completion-time sliding windows with O(1) maintenance
  - Side-conditional means and the markout skew indicator
  - Timestamp normalization (to milliseconds)
  - Optional L2-consistency validation utility

- Expected from the caller (application layer):
  - Cross-stream event ordering and book/replay management to supply a true pre-trade mid $m(t^-)$ for each aggregated L3 timestamp
  - Feeding L2/L3 streams and invoking the calculator at appropriate times

---

### 1) Inputs and Notation (as used by the library)

#### Book-derived prices
- Midprice at time $t$:

```math
m(t) := \frac{p^a_t + p^b_t}{2}
```

#### "Pre-trade" time $t_i^-$
- $t_i^-$ is the instant just before executing the trades at timestamp $t_i$. The caller must provide the mid from that state: 

```math
m(t_i^-) = \frac{p^a_{t_i^-}+p^b_{t_i^-}}{2}
```

#### Horizon
Choose one:
- Clock-time horizon $\tau$: horizon time $u := t + \tau$.
- Event-time horizon $K$ trades: horizon time $u :=$ the timestamp of the $(i+K)$-th trade.

For an observation (trade or aggregated side-group) starting at time $t$, define the markout:

```math
\Delta m := m(u) - m(t^-)
```

Implementation note (event-time): the library maintains a global trade counter. For an aggregated observation at time $t$, the target index is set to the current global counter plus $K$, and the counter is incremented by the number of trades in that timestamp after observations are created. When the counter reaches or exceeds the target, the observation's horizon completes at that time.

---

### 2) Aggregation of coalesced L3 prints (required)

When multiple L3 prints share the exact same timestamp $t$, they are aggregated by aggressor side to form up to two observations (one buy, one sell):

For each timestamp $t$:
- Let $G_t^{+}$ be the set of buy-aggressor prints at $t$.
- Let $G_t^{-}$ be the set of sell-aggressor prints at $t$.

Create up to two observations at $t$ (one for each non-empty set). For each observation:
- Start time $t$ with the same pre-trade mid $m(t^-)$ (shared by both sides at that $t$).
- Horizon time $u$ is determined by the chosen horizon type (clock or event time).
- Markout $\Delta m = m(u) - m(t^-)$.

L2 consistency utility: If coalesced L3 prints occur at $t$, the library exposes `validate_l2_consistency(t, n_l3, n_l2)` which logs a warning when $n_\text{L2} \neq 1$.

---

### 4) Sliding Window by Completion Time — definition

Let $W>0$ be the window width and current clock $T$.

- Each observation $j$ (a side-aggregated group at timestamp $t_j$) has a completion time $u_j$ (when its markout is evaluated) and a markout $\Delta m_j$.
- At time $T$, include only completed observations with completion time within $[T-W,T]$.

Define the buy and sell sets in the window:

```math
B_T := \{j: \text{observation is buy-aggressor}, u_j \in [T-W,T] \}
```

```math
S_T := \{j: \text{observation is sell-aggressor}, u_j \in [T-W,T] \}
```

Define the counts:

```math
N_T^{+} := |B_T|, \qquad N_T^{-} := |S_T|
```

Here $|\cdot|$ denotes set cardinality (number of observations).

---

### 5) Window Statistics and Indicator

Side-conditional means:

```math
\widehat{M}^{+}_{\tau}(T) = 
\begin{cases}
\dfrac{1}{N_T^{+}}\sum_{j\in B_T}\Delta m_j,& N_T^{+}>0\\
\text{NaN (or carry last)},& N_T^{+}=0
\end{cases}
```

```math
\widehat{M}^{-}_{\tau}(T) = 
\begin{cases}
\dfrac{1}{N_T^{-}}\sum_{j\in S_T}\Delta m_j,& N_T^{-}>0\\
\text{NaN (or carry last)},& N_T^{-}=0
\end{cases}
```

Markout Skew (indicator):

```math
\widehat{S}_{\tau}(T) = \widehat{M}^{+}_{\tau}(T) - \widehat{M}^{-}_{\tau}(T)
```

Implementation note: At the API level, the library returns `None` when a side has zero observations in-window; this corresponds to “NaN (or carry last)” in the spec text.

---

### 6) Horizon Scheduling and Window Maintenance

For each aggregated observation at time $t$ and side $s$:
1. Capture $m(t^-)$ (provided by caller).
2. Compute horizon $u$ (clock or event time).
3. Schedule evaluation at $u$.

When current clock reaches $u$:
- Read $m(u)$, compute $\Delta m = m(u)-m(t^-)$.
- Insert $(u, \Delta m)$ into the buy deque if $s=+1$, else the sell deque.

**CRITICAL IMPLEMENTATION CONSTRAINT (Clock-time horizons):**
The caller MUST invoke `complete_horizons_clock_time(u, m(u))` separately for each distinct horizon time $u$, passing the mid-price evaluated at that specific time $u$. Never batch multiple distinct horizon times into a single call, as this would cause all observations to use the same mid-price regardless of their actual horizon time, violating the spec requirement that $\Delta m = m(u) - m(t^-)$ where $m(u)$ is the mid-price at the specific horizon time $u$ for each observation.

Eviction (completion-time window):
- At each update time $T$, evict from the front of each deque all entries with $u < T-W$.
- Maintain running sums and counts for O(1) updates:
  - Buys: $\text{sum}^+, N^+$
  - Sells: $\text{sum}^-, N^-$

Compute:

```math
\widehat{M}^{+}_{\tau} = \text{sum}^+ / N^+, \quad
\widehat{M}^{-}_{\tau} = \text{sum}^- / N^-, \quad
\widehat{S}_{\tau} = \widehat{M}^{+}_{\tau} - \widehat{M}^{-}_{\tau}
```

---

### 7) Edge Handling / Hygiene

- Aggressor side: use only the side from L3 (no inference).
- Incomplete horizons: if $u$ has not occurred, the observation is not included.
- Zero counts: if a side has zero observations in-window, its mean (and skew if the other side is also missing) is reported as `None`.
- Coalesced L3 but no single L2 at same $t$: a validation utility is provided to log a warning (see §2 above).
- Timestamps: the library normalizes input timestamps to milliseconds; callers may pass seconds/milliseconds/microseconds/nanoseconds.

---

### API outline (summary)

- `MarkoutConfig(horizon_type: Literal["clock","event"], tau_ms: Optional[int], k_trades: Optional[int], window_ms: int)`
- `MarkoutSkewCalculator(config)`
  - `add_coalesced_l3_trades(timestamp_ms, trades, pre_trade_mid)` → create up to two observations (buy/sell)
  - `complete_horizons_clock_time(current_time_ms, current_mid)` → complete and insert into windows ⚠️ **See constraint below**
  - `complete_horizons_event_time(current_time_ms, current_mid)` → complete and insert into windows
  - `get_markout_skew(current_time_ms)` → `{mplus, mminus, skew, n_buys, n_sells}`
  - `get_state()` / `restore_from_state(state)`
- Utilities
  - `coalesce_l3_trades_by_timestamp(trades)`
  - `compute_mid_price(bid, ask)`
  - `validate_l2_consistency(timestamp_ms, l3_trades_count, l2_updates_count)`

**USAGE CONSTRAINTS:**
- The caller is responsible for producing the true pre-trade mid $m(t^-)$ at each L3 timestamp (per the cross-stream tie-break in the spec). The library then handles aggregation, scheduling, completion-time windowing, and indicator computation.
- **For clock-time horizons**: The caller MUST call `complete_horizons_clock_time(u, m(u))` separately for each distinct horizon time $u$, providing the mid-price evaluated at that specific time. Batching multiple horizon times in a single call will produce incorrect markouts.
- **For event-time horizons**: The caller may batch multiple completions in a single call to `complete_horizons_event_time(current_time, current_mid)` since all completed observations use the current time as their horizon completion time.



