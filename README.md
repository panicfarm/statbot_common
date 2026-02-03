# StatBot Common Utilities

This package provides common, reusable utilities for statistical analysis of market data, including:

- **`SlidingWindow`**: A generic, time-based sliding window that can store any Python object.
- **`compute_volatility`**: Calculates volatility from time-series data. Found in `volatility.py`.
- **`compute_total_size`**: Calculates the total size from time-series data. Found in `size.py`.
- **`VMF`**: Calculates the Volume-weighted Market Flow (VMF) indicator, providing normalized insights into trade velocity. Found in `vmf.py`.
- **Markout Skew**: Computes side-conditional markouts and skew using completion-time sliding windows; supports clock-time and event-time horizons. Found in `markout_skew.py`.
- **Queue Imbalance**: Calculates depth-weighted queue imbalance using exponential distance weighting and time-weighted averaging. Found in `queue_imbalance.py`.
- **AVCI**: Aggressive Volume Concentration Index measuring how concentrated aggressive volume is within a time window. Found in `avci.py`.
- **Protocols (`HasPrice`, `HasSize`, `HasLogPrice`, `L3Trade`, `MidPrice`, `L3Fill`)**: Define the expected structure for data objects, enabling type-safe and flexible metric calculations.


## Installation

You can install this package directly from GitHub.

### Latest Version (v0.8.0)

For new projects, install the latest version to get all features and the most flexible architecture:
```bash
pip install git+https://github.com/panicfarm/statbot_common.git
```
Or to install a specific version:
```bash
pip install git+https://github.com/panicfarm/statbot_common.git@v0.8.0
```

### Legacy Version (v2.0.0)

For older projects that depend on the original, float-based API, you can install the legacy `v2.0.0` release:
```bash
pip install git+https://github.com/panicfarm/statbot_common.git@v2.0.0
```

For development (includes pytest):
```bash
# For latest version
pip install git+https://github.com/panicfarm/statbot_common.git[dev]

# For a specific version
pip install git+https://github.com/panicfarm/statbot_common.git@v0.8.0#egg=statbot_common[dev]
```

## What's New in v0.8.0

**BREAKING CHANGE**: `compute_volatility` now requires the caller to provide `log_price` instead of `price`.

- The library no longer computes `log()` internally for volatility calculations.
- Data objects must now conform to the `HasLogPrice` protocol (provide a `log_price: float` attribute).
- This change allows domain-specific transforms (e.g., clipping probabilities, converting to odds/logit) to be handled at the application layer.

### Migration Guide

**Before (v0.7.x)**:
```python
@dataclass
class Trade:
    price: float

data = [(ts, Trade(price=100.0)), ...]
volatility = compute_volatility(data)  # Library called log(price) internally
```

**After (v0.8.0)**:
```python
import math

@dataclass
class LogPriceData:
    log_price: float

# Caller computes log_price (or log-odds, logit, etc.)
data = [(ts, LogPriceData(log_price=math.log(100.0))), ...]
volatility = compute_volatility(data)  # Library uses log_price directly
```

For prediction markets, you might use log-odds instead:
```python
def logit(p: float, eps: float = 0.04) -> float:
    """Convert probability to log-odds with edge clipping."""
    p = max(eps, min(1 - eps, p))
    return math.log(p / (1 - p))

data = [(ts, LogPriceData(log_price=logit(prob))), ...]
```

## What's New in v0.7.0

- Added Aggressive Volume Concentration Index (AVCI) for L3 fill analysis:
  - New protocol: `L3Fill` (with `taker_order_id`, `side`, `qty`).
  - New module `avci.py` exporting:
    - `AvciCalculator`, `AvciConfig`
  - Re-exported in package `__init__` for direct import from `statbot_common`.
- O(1) sliding window maintenance for efficient real-time computation
- Side-conditional variants (combined, buy-only, sell-only)
- Returns metrics: `avci`, `avci_excess`, `N` (taker count), `V` (total volume)

AVCI measures whether aggressive volume is concentrated in a few large taker orders or spread across many small ones.

## What's New in v0.6.1

- Added queue imbalance utilities for L2 depth analysis:
  - New module `queue_imbalance.py` exporting:
    - `QueueImbalanceCalculator`, `QueueImbalanceConfig`
    - Utilities: `compute_exponential_weights`, `sizes_on_tick_grid`, `compute_queue_diff` (raw QI_t)
    - Legacy: `compute_ib` (normalized IB_t) retained for back-compat
  - Re-exported in package `__init__` for direct import from `statbot_common`.
- Exponential distance weighting with configurable half-life (in ticks)
- Time-weighted averaging over sliding windows
- Tick-normalized depth extraction with zero-padding for missing levels

These additions implement depth-weighted queue imbalance calculation, supporting market microstructure analysis of order book pressure.

## What's New in v0.5.0

- Added markout skew utilities and protocols for L3/L2 analysis:
  - New protocols: `L3Trade` (with `aggressor_sign`) and `MidPrice`.
  - New module `markout_skew.py` exporting:
    - `MarkoutSkewCalculator`, `MarkoutObservation`, `MarkoutConfig`
    - Utilities: `coalesce_l3_trades_by_timestamp`, `compute_mid_price`, `validate_l2_consistency`
  - Re-exported in package `__init__` for direct import from `statbot_common`.
- Updated `protocols.py` to include `L3Trade` and `MidPrice` definitions.

These additions implement completion-time sliding windows, clock/event horizon support, and coalesced L3 processing to compute side-conditional markout means and skew.

## Quick Start

```python
import math
from statbot_common import SlidingWindow, compute_volatility, compute_total_size, compute_vmf
from dataclasses import dataclass
from typing import Optional

# Define a data structure for our trades
@dataclass
class Trade:
    timestamp: int
    price: float
    log_price: float  # Required for compute_volatility (v0.8.0+)
    quantity: float
    size: float
    side: Optional[str] = None  # 'buy', 'sell', or None for combined

# Create a sliding window that holds 60 seconds of data
trade_window = SlidingWindow(window_duration_ms=60 * 1000)

# Add rich trade objects to the window
# Note: log_price is computed by the caller
trade_window.add(1678886400, Trade(timestamp=1678886400000, price=100.5, log_price=math.log(100.5), quantity=150.0, size=1.5))
trade_window.add(1678886410000, Trade(timestamp=1678886410000, price=101.2, log_price=math.log(101.2), quantity=200.0, size=2.0))
trade_window.add(1678886420000000, Trade(timestamp=1678886420000, price=101.8, log_price=math.log(101.8), quantity=120.0, size=0.8))

# Get current data in the window
recent_trades = trade_window.get_window_data()
print(f"Data points in window: {len(recent_trades)}")

# Calculate metrics from the same data
if len(recent_trades) > 1:
    volatility = compute_volatility(recent_trades)
    total_size = compute_total_size(recent_trades)
    print(f"Volatility (per minute): {volatility:.8f}")
    print(f"Total trade size: {total_size:.2f}")

# Calculate VMF if we have enough data (needs 2 * smoothing_period_trades)
if len(recent_trades) >= 40:  # Default smoothing_period_trades=20
    vmf = compute_vmf(recent_trades)
    if vmf is not None:
        print(f"VMF indicator: {vmf:.4f}")
```

## API Reference

### SlidingWindow

A time-based sliding window that can store any type of Python object and automatically manages data expiration.

The `SlidingWindow` uses a `deque` (double-ended queue) for efficient storage. Data is automatically pruned based on timestamps to maintain the window duration.

```python
from statbot_common import SlidingWindow

# Create window
window = SlidingWindow(window_duration_ms=30000)  # 30 second window
```

#### Methods

- **`add(timestamp, data)`**: Add a data point to the window
  - `timestamp`: Unix timestamp (auto-detects s/ms/us/ns based on magnitude)
  - `data`: Any data object to store (e.g., a `dataclass` or custom object).

- **`get_window_data()`**: Get all current data in the window
  - Returns: `List[Tuple[int, Any]]` - list of (timestamp_ms, data) tuples.
  - Automatically removes expired entries before returning.

- **`get_latest()`**: Get the most recently added data point
  - Returns: The data portion of the latest entry, or `None` if empty.

- **`__len__()`**: Get the number of items currently in the window.

- **`purge(window_end_timestamp_ms)`**: Explicitly remove data points older than the specified window end time
  - `window_end_timestamp_ms`: Unix timestamp marking the absolute end of the desired window (auto-detects s/ms/us/ns)
  - Removes all data points whose timestamps are older than `(window_end_timestamp_ms - window_duration_ms)`
  - Provides precise control over window boundaries for time-sensitive applications

#### `compute_total_size`

Calculates the sum of the `size` attribute from a list of data points.

```python
from statbot_common import compute_total_size

# Data must contain objects conforming to HasSize
total_size = compute_total_size(trade_window.get_window_data())
print(f"Total size: {total_size:.2f}")
```

- **Module**: `statbot_common.size`
- **Parameters**: `List[Tuple[int, HasSize]]`
  - A list of (timestamp, data) tuples, where `data` has a `.size` attribute.
- **Returns**: `float` (total size).

#### `compute_vmf`

Calculates the Volume-weighted Market Flow (VMF) indicator from a list of time-series data points.

```python
from statbot_common import compute_vmf

# Data must contain objects conforming to Trade protocol
vmf = compute_vmf(trade_window.get_window_data())
if vmf is not None:
    print(f"VMF indicator: {vmf:.4f}")
```

- **Module**: `statbot_common.vmf`
- **Parameters**: `List[Tuple[int, Trade]]`, `smoothing_period_trades: int = 20`
  - A list of (timestamp, data) tuples, where `data` has `timestamp` and `quantity` attributes.
  - `smoothing_period_trades`: Number of trades for smoothing and normalization window.
- **Returns**: `float` (normalized VMF value) or `None`. Requires at least `2 * smoothing_period_trades` data points.

### Markout Skew

Calculates side-conditional markouts and skew using completion-time sliding windows with either clock-time or event-time horizons.

```python
from dataclasses import dataclass
from typing import List

from statbot_common import (
    MarkoutSkewCalculator,
    MarkoutConfig,
    coalesce_l3_trades_by_timestamp,
    compute_mid_price,
)

@dataclass
class L3Print:
    timestamp: int
    price: float
    quantity: float
    aggressor_sign: int  # +1 = buy, -1 = sell

# Configure a 1s clock-time horizon and a 5-minute completion-time window
cfg = MarkoutConfig(horizon_type="clock", tau_ms=1000, window_ms=5 * 60 * 1000)
calc = MarkoutSkewCalculator(cfg)

# Example inputs for a single timestamp
ts_ms = 1710000000000
bid, ask = 100.00, 100.20
pre_mid = compute_mid_price(bid, ask)
prints: List[L3Print] = [
    L3Print(timestamp=ts_ms, price=100.10, quantity=5.0, aggressor_sign=1),
    L3Print(timestamp=ts_ms, price=100.18, quantity=3.0, aggressor_sign=-1),
]

# Add coalesced prints (aggregated by timestamp and side)
by_ts = coalesce_l3_trades_by_timestamp(prints)
for t_ms, l3s in by_ts.items():
    calc.add_coalesced_l3_trades(t_ms, l3s, pre_mid)

# Later (>= tau_ms), complete horizons with the current mid and time
current_time_ms = ts_ms + 1200
current_mid = 100.15
calc.complete_horizons_clock_time(current_time_ms, current_mid)

# Compute current skew for the completion-time window
skew_stats = calc.get_markout_skew(current_time_ms)
print(skew_stats)  # {'mplus': ..., 'mminus': ..., 'skew': ..., 'n_buys': ..., 'n_sells': ...}

# Event-time variant: use k_trades instead of tau_ms and call complete_horizons_event_time
# cfg = MarkoutConfig(horizon_type="event", k_trades=50, window_ms=5 * 60 * 1000)
# calc.complete_horizons_event_time(current_time_ms, current_mid)
```

- **Module**: `statbot_common.markout_skew`
- **Core types**: `MarkoutSkewCalculator`, `MarkoutConfig`, `MarkoutObservation`
- **Utilities**: `coalesce_l3_trades_by_timestamp`, `compute_mid_price`, `validate_l2_consistency`
- **Configuration**:
  - `horizon_type`: `"clock"` or `"event"`
  - `tau_ms`: Clock-time horizon in milliseconds (required when `horizon_type == "clock"`)
  - `k_trades`: Event-time horizon in number of trades (required when `horizon_type == "event"`)
  - `window_ms`: Completion-time sliding window size (default 300000 ms)
- **Returns**: `get_markout_skew(T)` -> `Dict[str, Optional[float]]` with keys `mplus`, `mminus`, `skew`, `n_buys`, `n_sells`.
- **Notes**: Timestamps auto-normalize to milliseconds; missing side counts yield `None` for the corresponding means and `skew`.

### Queue Imbalance

Calculates depth-weighted queue imbalance using exponential distance weighting and time-weighted averaging over sliding windows.

```python
from decimal import Decimal
from statbot_common import (
    QueueImbalanceCalculator,
    QueueImbalanceConfig,
    compute_exponential_weights,
    sizes_on_tick_grid,
    compute_ib,
)

# Configure calculator for SOL/USDT with 0.01 tick size
# K=3 levels per side, half-life=0.5 ticks, 30-second window
config = QueueImbalanceConfig(
    k_levels=3,
    tick_size=Decimal("0.01"),
    half_life_ticks=Decimal("0.5"),
    window_ms=30_000,
)
calc = QueueImbalanceCalculator(config)

# Example order book snapshot at timestamp t_ms
t_ms = 1700000000000
best_bid = Decimal("100.00")
best_ask = Decimal("100.01")
bids = {Decimal("100.00"): Decimal("10"), Decimal("99.99"): Decimal("5"), Decimal("99.98"): Decimal("2")}
asks = {Decimal("100.01"): Decimal("8"), Decimal("100.02"): Decimal("4"), Decimal("100.03"): Decimal("1")}

# Update calculator with current book state
ib_t = calc.update_from_book(t_ms, best_bid, best_ask, bids, asks)
print(f"Instantaneous imbalance IB_t: {ib_t}")

# Get time-weighted mean over the window
tw_mean = calc.get_time_weighted_mean(t_ms + 1000)
print(f"Time-weighted mean: {tw_mean}")

# Manual calculation example
weights = compute_exponential_weights(3, Decimal("0.5"))  # [1.0, 0.25, 0.0625]
bid_sizes, ask_sizes = sizes_on_tick_grid(best_bid, best_ask, Decimal("0.01"), 3, bids, asks)
ib = compute_ib(bid_sizes, ask_sizes, weights)
print(f"Manual IB calculation: {ib}")
```

- **Module**: `statbot_common.queue_imbalance`
- **Core types**: `QueueImbalanceCalculator`, `QueueImbalanceConfig`
- **Utilities**: `compute_exponential_weights`, `sizes_on_tick_grid`, `compute_ib`
- **Configuration**:
  - `k_levels`: Number of tick levels per side to include (default 10)
  - `tick_size`: Minimum price increment as `Decimal` (required)
  - `half_life_ticks`: Exponential decay half-life in ticks (default 0.5)
  - `window_ms`: Time-weighted averaging window in milliseconds (default 30000)
- **Returns**: 
  - `update_from_book(...)` -> `Optional[Decimal]` (instantaneous IB_t or `None`)
  - `get_time_weighted_mean(t_ms)` -> `Optional[Decimal]` (time-weighted mean or `None`)
- **Notes**: Uses tick-normalized grid with zero-padding for missing levels; IB_t ranges from -1 (ask pressure) to +1 (bid pressure); requires `Decimal` for all price/size inputs.

### AVCI (Aggressive Volume Concentration Index)

Measures how concentrated aggressive volume is within a time window - whether a few large taker orders dominate, or volume is spread across many small taker orders.

```python
from dataclasses import dataclass
from statbot_common import AvciCalculator, AvciConfig

@dataclass
class Fill:
    timestamp: int
    taker_order_id: str
    side: int  # +1 = buy, -1 = sell
    qty: float

# Configure calculator with 10-second window
config = AvciConfig(window_ms=10000)
calc = AvciCalculator(config)

# Add L3 fills as they arrive
calc.add_fill(Fill(timestamp=1000, taker_order_id="A", side=1, qty=60))
calc.add_fill(Fill(timestamp=1100, taker_order_id="B", side=1, qty=25))
calc.add_fill(Fill(timestamp=1200, taker_order_id="C", side=-1, qty=15))

# Get metrics for all three buckets (combined, buy, sell)
metrics = calc.get_metrics()
print(metrics['combined'])
# {'avci': 0.46, 'avci_excess': 0.38, 'N': 3, 'V': 100.0}

# Evict old fills when advancing time
calc.evict_to(12000)  # Evicts fills older than 12000 - 10000 = 2000ms
```

- **Module**: `statbot_common.avci`
- **Core types**: `AvciCalculator`, `AvciConfig`
- **Protocol**: `L3Fill` (requires `timestamp`, `taker_order_id`, `side`, `qty`)
- **Configuration**:
  - `window_ms`: Sliding window width in milliseconds
- **Returns**: `get_metrics()` -> `Dict` with keys `combined`, `buy`, `sell`, each containing:
  - `avci`: Concentration index (1/N for equal split, 1 for single taker); `None` if V=0
  - `avci_excess`: N * AVCI - 1 (0 for equal split); `None` if V=0
  - `avci_norm`: Normalized AVCI in [0, 1] (0 for equal split, 1 for single taker); `None` if V=0
  - `N`: Count of active taker IDs in window
  - `V`: Total volume in window
- **Notes**: AVCI is in [1/N, 1]; higher values indicate more concentrated flow.

### Data Protocols

To enable flexible and type-safe calculations, `statbot_common` uses `Protocol` to define data requirements. Your data objects should conform to these protocols to work with the computation functions.

- **`HasPrice`**: Requires the object to have a `price: float` attribute.
- **`HasSize`**: Requires the object to have a `size: float` attribute.
- **`HasLogPrice`**: Requires the object to have a `log_price: float` attribute. Used by `compute_volatility`. The caller is responsible for computing the log-price (or log-odds, logit, etc.) before passing to the library.
- **`Trade`**: Requires the object to have `timestamp: int`, `quantity: float`, and optionally `side: Optional[str]` attributes.

You can use a `dataclass` or any custom class that meets these requirements:

```python
from dataclasses import dataclass
from typing import Optional
import math

@dataclass
class MyTrade:
    timestamp: int
    quantity: float
    price: float      # Conforms to HasPrice
    log_price: float  # Conforms to HasLogPrice (compute as math.log(price) or logit(prob))
    size: float       # Conforms to HasSize
    side: Optional[str] = None
    exchange: str = ""  # Extra data is fine
```

### Computation Functions

#### `compute_volatility`

Calculates volatility from a list of time-series data points containing log-prices.

```python
import math
from statbot_common import compute_volatility
from dataclasses import dataclass

@dataclass
class LogPriceData:
    log_price: float

# Caller computes log_price before passing to the library
prices = [100.0, 101.2, 100.8, 102.0]
timestamps = [1678886400000, 1678886410000, 1678886420000, 1678886430000]

data = [(ts, LogPriceData(log_price=math.log(p))) for ts, p in zip(timestamps, prices)]
volatility = compute_volatility(data)
print(f"Volatility per minute: {volatility:.8f}")
```

- **Module**: `statbot_common.volatility`
- **Parameters**: `List[Tuple[int, HasLogPrice]]`
  - A list of (timestamp, data) tuples, where `data` has a `.log_price` attribute.
  - The `log_price` should be the log of the price (or log-odds/logit for prediction markets).
- **Returns**: `float` (volatility per minute) or `None` if computation is not possible.
- **Notes**: 
  - Timestamps auto-normalize to milliseconds.
  - Requires at least 2 valid data points.
  - The caller is responsible for computing `log_price` - this allows domain-specific transforms (clipping, odds conversion) at the application layer.
