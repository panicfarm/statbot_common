# StatBot Common Utilities

This package provides common, reusable utilities for statistical analysis of market data, including:

- **`SlidingWindow`**: A generic, time-based sliding window data structure that handles multiple timestamp resolutions (s, ms, μs, ns).
- **`compute_volatility`**: A standalone volatility calculation function for time-series data.
- **`normalize_timestamp_to_ms`**: Automatic timestamp normalization utility.

## Installation

You can install this package directly from GitHub:

```bash
pip install git+https://github.com/panicfarm/statbot_common.git
```

For development (includes pytest):
```bash
pip install git+https://github.com/panicfarm/statbot_common.git[dev]
```

## Quick Start

```python
from statbot_common import SlidingWindow, compute_volatility
import math
import time

# Create a sliding window that holds 60 seconds of data
price_window = SlidingWindow(window_duration_ms=60 * 1000)

# Add price data (timestamps can be in seconds, ms, μs, or ns)
price_window.add(1678886400, 100.5)      # seconds
price_window.add(1678886410000, 101.2)   # milliseconds  
price_window.add(1678886420000000, 101.8) # microseconds

# Get current data in the window (auto-expires old data)
recent_data = price_window.get_window_data()
print(f"Data points in window: {len(recent_data)}")

# Calculate volatility from price data
if len(recent_data) > 1:
    # For volatility, data should be (timestamp, log_price)
    log_price_data = [(ts, math.log(price)) for ts, price in recent_data]
    volatility = compute_volatility(log_price_data)
    print(f"Volatility (per minute): {volatility:.8f}")
```

## API Reference

### SlidingWindow

A time-based sliding window that automatically manages data expiration.

```python
from statbot_common import SlidingWindow

# Create window
window = SlidingWindow(window_duration_ms=30000)  # 30 second window
```

#### Methods

- **`add(timestamp, data)`**: Add a data point to the window
  - `timestamp`: Unix timestamp (auto-detects s/ms/μs/ns based on magnitude)
  - `data`: Any data to store (price, trade info, etc.)

- **`get_window_data()`**: Get all current data in the window
  - Returns: `List[Tuple[int, Any]]` - list of (timestamp_ms, data) tuples
  - Automatically removes expired entries

- **`get_latest()`**: Get the most recently added data point
  - Returns: The data portion of the latest entry, or `None` if empty

- **`__len__()`**: Get the number of items currently in the window

#### Timestamp Formats

The `SlidingWindow` automatically detects and normalizes timestamp formats:

| Format | Example | Digits | Converted To |
|--------|---------|--------|--------------|
| Seconds | `1678886400` | ≤10 | `1678886400000` ms |
| Milliseconds | `1678886400000` | 11-13 | `1678886400000` ms |
| Microseconds | `1678886400000000` | 14-16 | `1678886400000` ms |
| Nanoseconds | `1678886400000000000` | 17-19 | `1678886400000` ms |

### compute_volatility

Calculate volatility from time-series data with uneven intervals.

```python
from statbot_common import compute_volatility
import math

# Prepare data: list of (timestamp, log_price) tuples
data = [
    (1678886400000, math.log(100.0)),
    (1678886410000, math.log(100.5)),
    (1678886420000, math.log(99.8)),
]

volatility = compute_volatility(data)
print(f"Volatility per minute: {volatility:.8f}")
```

#### Parameters

- **`data_points`**: `List[Tuple[int, float]]`
  - List of (timestamp, value) tuples
  - Timestamp: Unix timestamp (any resolution - auto-normalized)
  - Value: Typically `math.log(price)` for price volatility

#### Returns

- `float`: Volatility per minute
- `None`: If insufficient data (< 2 points) or calculation error

#### Data Requirements

For price volatility calculation:
1. **Convert prices to log returns**: Use `math.log(price)` as the value
2. **Minimum 2 data points**: Need at least 2 points for calculation
3. **Chronological order**: Data is automatically sorted by timestamp

## Usage Examples

### Market Data Analysis

```python
from statbot_common import SlidingWindow, compute_volatility
import math

# Track 15 minutes of trade data
trade_window = SlidingWindow(window_duration_ms=15 * 60 * 1000)

def on_trade_received(trade):
    """Called when a new trade arrives"""
    price = float(trade['price'])
    timestamp = int(trade['timestamp'])  # Can be any resolution
    
    # Store the log price for volatility calculation
    trade_window.add(timestamp, math.log(price))

def calculate_current_volatility():
    """Calculate volatility from recent trades"""
    recent_trades = trade_window.get_window_data()
    
    if len(recent_trades) < 2:
        return None
        
    # Data is already in (timestamp, log_price) format
    volatility = compute_volatility(recent_trades)
    return volatility

# Example usage
trades = [
    {'timestamp': 1678886400000, 'price': '100.50'},
    {'timestamp': 1678886410000, 'price': '100.75'},
    {'timestamp': 1678886420000, 'price': '100.25'},
]

for trade in trades:
    on_trade_received(trade)

vol = calculate_current_volatility()
if vol:
    print(f"Current 15-min volatility: {vol:.6f} per minute")
```

### Multiple Time Windows

```python
from statbot_common import SlidingWindow

# Track multiple timeframes simultaneously
windows = {
    '1m': SlidingWindow(1 * 60 * 1000),
    '5m': SlidingWindow(5 * 60 * 1000),
    '15m': SlidingWindow(15 * 60 * 1000),
}

def add_price_data(timestamp, price):
    log_price = math.log(price)
    for window in windows.values():
        window.add(timestamp, log_price)

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
add_price_data(1678886460000, 100.5)  # 1 minute later
add_price_data(1678886520000, 99.8)   # 2 minutes later

volatilities = get_multi_timeframe_volatility()
for timeframe, vol in volatilities.items():
    print(f"{timeframe} volatility: {vol:.6f}")
```

## Testing

Run the test suite:

```bash
pytest
```

All tests verify:
- Correct volatility calculations with known datasets
- Sliding window data management and expiration
- Timestamp normalization across different resolutions
- Edge cases and error handling

## License

MIT License 