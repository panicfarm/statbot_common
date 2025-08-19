# StatBot Common Utilities

This package provides common, reusable utilities for statistical analysis of market data, including:

- **`SlidingWindow`**: A generic, time-based sliding window that can store any Python object.
- **`compute_volatility`**: Calculates volatility from time-series data. Found in `volatility.py`.
- **`compute_total_size`**: Calculates the total size from time-series data. Found in `size.py`.
- **`VMF`**: Calculates the Volume-weighted Market Flow (VMF) indicator, providing normalized insights into trade velocity. Found in `vmf.py`.
- **Markout Skew**: Computes side-conditional markouts and skew using completion-time sliding windows; supports clock-time and event-time horizons. Found in `markout_skew.py`.
- **Protocols (`HasPrice`, `HasSize`)**: Define the expected structure for data objects, enabling type-safe and flexible metric calculations.


## Installation

You can install this package directly from GitHub.

### Latest Version (v0.5.0)

For new projects, install the latest version to get all features and the most flexible architecture:
```bash
pip install git+https://github.com/panicfarm/statbot_common.git
```
Or to install a specific version:
```bash
pip install git+https://github.com/panicfarm/statbot_common.git@v0.5.0
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
pip install git+https://github.com/panicfarm/statbot_common.git@v0.5.0#egg=statbot_common[dev]
```

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
from statbot_common import SlidingWindow, compute_volatility, compute_total_size, compute_vmf, Trade
from dataclasses import dataclass
import time
from typing import Optional

# Define a data structure for our trades
@dataclass
class Trade:
    timestamp: int
    price: float
    quantity: float
    size: float
    side: Optional[str] = None # 'buy', 'sell', or None for combined

# Create a sliding window that holds 60 seconds of data
trade_window = SlidingWindow(window_duration_ms=60 * 1000)

# Add rich trade objects to the window
trade_window.add(1678886400, Trade(timestamp=1678886400000, price=100.5, quantity=150.0, size=1.5))      # seconds
trade_window.add(1678886410000, Trade(timestamp=1678886410000, price=101.2, quantity=200.0, size=2.0))   # milliseconds
trade_window.add(1678886420000000, Trade(timestamp=1678886420000, price=101.8, quantity=120.0, size=0.8)) # microseconds

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
  - `timestamp`: Unix timestamp (auto-detects s/ms/μs/ns based on magnitude)
  - `data`: Any data object to store (e.g., a `dataclass` or custom object).

- **`get_window_data()`**: Get all current data in the window
  - Returns: `List[Tuple[int, Any]]` - list of (timestamp_ms, data) tuples.
  - Automatically removes expired entries before returning.

- **`get_latest()`**: Get the most recently added data point
  - Returns: The data portion of the latest entry, or `None` if empty.

- **`__len__()`**: Get the number of items currently in the window.

- **`purge(window_end_timestamp_ms)`**: Explicitly remove data points older than the specified window end time
  - `window_end_timestamp_ms`: Unix timestamp marking the absolute end of the desired window (auto-detects s/ms/μs/ns)
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
- **Returns**: `get_markout_skew(T)` → `Dict[str, Optional[float]]` with keys `mplus`, `mminus`, `skew`, `n_buys`, `n_sells`.
- **Notes**: Timestamps auto-normalize to milliseconds; missing side counts yield `None` for the corresponding means and `skew`.

### Data Protocols

To enable flexible and type-safe calculations, `statbot_common` uses `Protocol` to define data requirements. Your data objects should conform to these protocols to work with the computation functions.

- **`HasPrice`**: Requires the object to have a `price: float` attribute.
- **`HasSize`**: Requires the object to have a `size: float` attribute.
- **`Trade`**: Requires the object to have `timestamp: int`, `quantity: float`, and optionally `side: Optional[str]` attributes.

You can use a `dataclass` or any custom class that meets these requirements:

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class MyTrade:
    timestamp: int
    quantity: float
    price: float  # Conforms to HasPrice
    size: float   # Conforms to HasSize
    side: Optional[str] = None
    exchange: str # Extra data is fine
```

### Computation Functions

#### `compute_volatility`

Calculates volatility from a list of time-series data points.

```python
from statbot_common import compute_volatility

# Data must contain objects conforming to HasPrice
volatility = compute_volatility(trade_window.get_window_data())
print(f"Volatility per minute: {volatility:.8f}")
```

- **Module**: `statbot_common.volatility`
- **Parameters**: `List[Tuple[int, HasPrice]]`
  - A list of (timestamp, data) tuples, where `