# StatBot Common Utilities

This package provides common, reusable utilities for statistical analysis of market data, including:

- **`SlidingWindow`**: A generic, time-based sliding window that can store any Python object.
- **`compute_volatility`**: Calculates volatility from time-series data. Found in `volatility.py`.
- **`compute_total_size`**: Calculates the total size from time-series data. Found in `size.py`.
- **`VMF`**: Calculates the Volume-weighted Market Flow (VMF) indicator, providing normalized insights into trade velocity. Found in `vmf.py`.
- **Protocols (`HasPrice`, `HasSize`)**: Define the expected structure for data objects, enabling type-safe and flexible metric calculations.


## Installation

You can install this package directly from GitHub.

### Latest Version (v0.4.0+)

For new projects, install the latest version to get all features and the most flexible architecture:
```bash
pip install git+https://github.com/panicfarm/statbot_common.git
```
Or to install a specific version:
```bash
pip install git+https://github.com/panicfarm/statbot_common.git@v0.4.0
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
pip install git+https://github.com/panicfarm/statbot_common.git@v0.4.0#egg=statbot_common[dev]
```

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