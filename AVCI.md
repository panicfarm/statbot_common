# Aggressive Volume Concentration Index (AVCI) — Library Implementation (statbot_common)

This document specifies the Aggressive Volume Concentration Index (AVCI) as implemented in `statbot_common`. AVCI measures how concentrated aggressive volume is within a time window — whether a few large taker orders dominate, or volume is spread across many small taker orders.

### Scope

- Implemented here (library, exchange-agnostic):
  - Ingestion of L3 prints (fills) with `takerOrderId`, `makerOrderId`, `side`, `qty`, `timestamp`
  - Per-window aggregation of aggressive size by taker order ID
  - Time-based sliding-window maintenance with O(1) updates
  - Computation of AVCI and companion statistics (effective count, top-k share)
  - Optional side-conditional variants (buy-only, sell-only)

- Expected from the caller (application layer): see `qbot/notes/AVCI.md` for replay ordering, feed ingestion, configuration, and diagnostics.

---

## 1) Inputs and Notation

Each L3 fill i has:
- Timestamp \(t_i\)
- Aggressor side \(s_i\in\{+1,-1\}\)
- Quantity \(q_i>0\)
- Taker order ID \(\tau_i\)
- Maker order ID (unused here)

Fix a window end time \(T\) and width \(W>0\). The active set:

```math
\mathcal{I}_T := \{\, i : t_i \in [T-W,\,T] \,\}.
```

Unique taker IDs active in-window:

```math
\mathcal{J}_T := \{\, \tau : \exists\, i\in\mathcal{I}_T \text{ with } \tau_i=\tau \,\},
\qquad N(T) := |\mathcal{J}_T|.
```

Per-taker aggressive volume contribution and total:

```math
v_j(T) := \sum_{i\in\mathcal{I}_T : \tau_i=j} q_i,
\qquad
V(T) := \sum_{j\in\mathcal{J}_T} v_j(T).
```

(For buy-only / sell-only variants, simply restrict \(\mathcal{I}_T\) to fills with \(s_i=+1\) or \(s_i=-1\).)

---

## 2) Indicator Definition

### Core Metric — AVCI

```math
\text{AVCI}(T) := \sum_{j\in\mathcal{J}_T} \left( \frac{v_j(T)}{V(T)} \right)^2,
\qquad V(T)>0.
```

Range:

```math
\text{AVCI}(T) \in \left[\frac{1}{N(T)},\,1\right].
```

- = 1 when one taker order accounts for all aggressive volume.
- = 1 / N(T) when volume is split equally across N(T) takers.
- Lower values ⇒ diffuse flow; higher values ⇒ concentration.

---

### Effective Count (Equal-Size Equivalent)

```math
N_{\text{eff}}(T) := \frac{1}{\text{AVCI}(T)} \in [1,\,N(T)].
```

---

### Top-k Share (Optional Diagnostic)

If \(v_{(1)}\ge v_{(2)}\ge\cdots\) are sorted:

```math
S_k(T) := \frac{\sum_{\ell=1}^{k} v_{(\ell)}(T)}{V(T)}.
```

---

### Equal-Split Anchored Concentration (Window-Comparable)

```math
\text{AVCI}_{\text{excess}}(T) := N(T)\,\text{AVCI}(T) - 1.
```

Range:

```math
\text{AVCI}_{\text{excess}}(T) \in [\,0,\,N(T)-1\,].
```

---

## 3) Sliding-Window Maintenance (Time-Based)

Each bucket (combined / buy / sell) maintains:

- A timestamp-ordered deque of fills in-window  
- `vol_by_taker[j] = v_j`
- Scalars:
  - \(V = \sum_j v_j\)
  - \(\Sigma_2 = \sum_j v_j^2\)
  - \(N = |\{j: v_j>0\}|\)

### Insert (arrival at time \(t\))

Let old \(x = v_{\tau}\) (default 0), new \(x' = x+q\):

```math
V \gets V + q
```

```math
\Sigma_2 \gets \Sigma_2 - x^2 + (x+q)^2
```

If \(x=0\) then \(N\gets N+1\).

### Evict (while oldest fill has \(t < T-W\))

Let old \(x=v_{\tau}\), new \(x'=x-q\):

```math
V \gets V - q
```

```math
\Sigma_2 \gets \Sigma_2 - x^2 + (x-q)^2
```

If \(x=q\) then remove \(\tau\) and decrement \(N\).

### Compute (O(1))

```math
\text{AVCI} = \frac{\Sigma_2}{V^2},
\qquad
N_{\text{eff}} = \frac{1}{\text{AVCI}},
\qquad
\text{AVCI}_{\text{excess}} = N\cdot\text{AVCI} - 1.
```

Top-k requires a partial sort on demand.

---

## 4) Side-Conditional Variants

Returned structure:

```
{
  combined: { avci, n_eff, avci_excess, N, V, (optional) top_k },
  buy:      { ... },
  sell:     { ... }
}
```

---

## 5) Edge Handling / Hygiene

- If \(V=0\), return `None`.
- Assumes stable `takerOrderId` across partial fills.
- Memory usage scales with fills and unique taker IDs in-window.
- Optional diagnostics (top-k) should be bounded if needed.

---

## 6) API outline (summary)

- `AvciConfig(window_ms, mode, track_topk)`
- `AvciCalculator(config)`
  - `add_fill(...)`
  - `evict_to(...)`
  - `get_metrics(...)`
  - `get_state() / restore_from_state(...)`

Returned per bucket:

- `avci`
- `n_eff`
- `avci_excess`
- `N`, `V`
- `top_k` (optional)


