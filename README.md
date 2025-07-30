# StatBot Common Utilities

This package provides common, reusable utilities for statistical analysis of market data, including:

- **`SlidingWindow`**: A generic, time-based sliding window that can store any Python object.
- **`compute_volatility`**: Calculates volatility from time-series data. Found in `volatility.py`.
- **`compute_total_size`**: Calculates the total size from time-series data. Found in `size.py`.
- **Protocols (`HasPrice`, `HasSize`)**: Define the expected structure for data objects, enabling type-safe and flexible metric calculations.

## Installation

You can install this package directly from GitHub.

### Latest Version (v2.0.0+)

For new projects, install the latest version to get all features and the most flexible architecture:
```bash
pip install git+https://github.com/panicfarm/statbot_common.git
```
Or to install a specific version:
```bash
pip install git+https://github.com/panicfarm/statbot_common.git@v2.0.0
```

### Legacy Version (v1.0.0)

For older projects that depend on the original, float-based API, you can install the legacy `v1.0.0` release:
```bash
pip install git+https://github.com/panicfarm/statbot_common.git@v1.0.0
```

For development (includes pytest):
```bash
# For latest version
pip install git+https://github.com/panicfarm/statbot_common.git[dev]

# For a specific version
pip install git+https://github.com/panicfarm/statbot_common.git@v2.0.0#egg=statbot_common[dev]
```

## Quick Start

```python
from statbot_common import SlidingWindow, compute_volatility, compute_total_size
from dataclasses import dataclass
import time

# Define a data structure for our trades
@dataclass
class Trade:
    price: float
    size: float

# Create a sliding window that holds 60 seconds of data
trade_window = SlidingWindow(window_duration_ms=60 * 1000)

# Add rich trade objects to the window
trade_window.add(1678886400, Trade(price=100.5, size=1.5))      # seconds
trade_window.add(1678886410000, Trade(price=101.2, size=2.0))   # milliseconds
trade_window.add(1678886420000000, Trade(price=101.8, size=0.8)) # microseconds

# Get current data in the window
recent_trades = trade_window.get_window_data()
print(f"Data points in window: {len(recent_trades)}")

# Calculate volatility and total size from the same data
if len(recent_trades) > 1:
    volatility = compute_volatility(recent_trades)
    total_size = compute_total_size(recent_trades)
    print(f"Volatility (per minute): {volatility:.8f}")
    print(f"Total trade size: {total_size:.2f}")
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

### Data Protocols

To enable flexible and type-safe calculations, `statbot_common` uses `Protocol` to define data requirements. Your data objects should conform to these protocols to work with the computation functions.

- **`HasPrice`**: Requires the object to have a `price: float` attribute.
- **`HasSize`**: Requires the object to have a `size: float` attribute.

You can use a `dataclass` or any custom class that meets these requirements:

```python
from dataclasses import dataclass

@dataclass
class MyTrade:
    price: float  # Conforms to HasPrice
    size: float   # Conforms to HasSize
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
  - A list of (timestamp, data) tuples, where `data` has a `.price` attribute.
- **Returns**: `float` (volatility per minute) or `None`.

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

## Usage Examples

### Market Data Analysis with Rich Objects

```python
from statbot_common import SlidingWindow, compute_volatility, compute_total_size
from dataclasses import dataclass

@dataclass
class Trade:
    price: float
    size: float

# Track 15 minutes of trade data
trade_window = SlidingWindow(window_duration_ms=15 * 60 * 1000)

def on_trade_received(trade_event):
    """Called when a new trade arrives"""
    trade = Trade(
        price=float(trade_event['price']),
        size=float(trade_event['size'])
    )
    timestamp = int(trade_event['timestamp'])
    trade_window.add(timestamp, trade)

def get_current_metrics():
    """Calculate all metrics from recent trades"""
    recent_trades = trade_window.get_window_data()
    
    if len(recent_trades) < 2:
        return None, None
        
    volatility = compute_volatility(recent_trades)
    total_size = compute_total_size(recent_trades)
    return volatility, total_size

# Example usage
trades = [
    {'timestamp': 1678886400000, 'price': '100.50', 'size': '1.0'},
    {'timestamp': 1678886410000, 'price': '100.75', 'size': '0.5'},
    {'timestamp': 1678886420000, 'price': '100.25', 'size': '2.0'},
]

for trade in trades:
    on_trade_received(trade)

vol, size = get_current_metrics()
if vol is not None:
    print(f"Current 15-min volatility: {vol:.6f} per minute")
    print(f"Total size in window: {size:.2f}")
```

### Explicit Window Management with `purge(window_end_timestamp_ms: int))`

For applications requiring precise time alignment, use the `purge(window_end_timestamp_ms: int))` method to explicitly control window boundaries:

```python
from statbot_common import SlidingWindow
from dataclasses import dataclass

@dataclass
class MarketData:
    price: float
    size: float

# Create a 60-second sliding window
window = SlidingWindow(window_duration_ms=60000)

def process_message_batch(messages):
    """Process a batch of market data messages with precise time alignment"""
    for message in messages:
        # Add the data point
        data = MarketData(price=message['price'], size=message['size'])
        window.add(message['timestamp'], data)
        
        # Explicitly purge data older than current message time
        # This ensures window is always aligned to current message processing time
        window.purge(message['timestamp'])
        
        # Now any metrics calculated are precisely time-aligned
        current_data = window.get_window_data()
        print(f"Data points in {len(current_data)} precisely aligned to message at {message['timestamp']}")

# Example: Market data replay with precise timing
messages = [
    {'timestamp': 1678886400000, 'price': 100.0, 'size': 1.0},
    {'timestamp': 1678886430000, 'price': 100.5, 'size': 1.5},  # 30s later
    {'timestamp': 1678886480000, 'price': 101.0, 'size': 2.0},  # 50s later
]

process_message_batch(messages)
```

### Multiple Time Windows

You can still use multiple time windows, now with richer data objects.

```python
from statbot_common import SlidingWindow, compute_volatility
from dataclasses import dataclass

@dataclass
class DataPoint:
    price: float

# Track multiple timeframes
windows = {
    '1m': SlidingWindow(1 * 60 * 1000),
    '5m': SlidingWindow(5 * 60 * 1000),
    '15m': SlidingWindow(15 * 60 * 1000),
}

def add_price_data(timestamp, price):
    data = DataPoint(price=price)
    for window in windows.values():
        window.add(timestamp, data)

def get_multi_timeframe_volatility():
    results = {}
    for timeframe, window in windows.items():
        data = window.get_window_data()
        if len(data) > 1:
            vol = compute_volatility(data)
            results[timeframe] = vol
    return results

# Example
add_price_data(1678886400000, 100.0)
add_price_data(1678886460000, 100.5)
add_price_data(1678886520000, 99.8)

volatilities = get_multi_timeframe_volatility()
for timeframe, vol in volatilities.items():
    if vol is not None:
        print(f"{timeframe} volatility: {vol:.6f}")
```

## Testing

Run the test suite:

```bash
pytest
```

All tests verify:
- Correct metric calculations (e.g., `volatility`, `size`).
- `SlidingWindow` data management and expiration with rich objects.
- Timestamp normalization across different resolutions.
- Graceful handling of objects that do not conform to protocols.

## License

MIT License