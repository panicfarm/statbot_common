import pytest
from statbot_common import SlidingWindow
from dataclasses import dataclass

@dataclass
class DataPoint:
    value: str

def test_window_initialization():
    """Test that the window initializes correctly."""
    window = SlidingWindow(10000)
    assert len(window) == 0
    assert window.get_window_data() == []

def test_add_and_get_data():
    """Test adding items and retrieving them."""
    window = SlidingWindow(10000)
    # Timestamps are in milliseconds for this test to avoid normalization confusion
    window.add(1678886401000, DataPoint(value="a"))
    window.add(1678886402000, DataPoint(value="b"))
    assert len(window) == 2
    retrieved = window.get_window_data()
    assert retrieved[0][1].value == "a"
    assert retrieved[1][1].value == "b"

def test_window_pruning():
    """Test that the window correctly prunes expired entries."""
    window = SlidingWindow(10000) # 10 second window
    
    # Add initial items (timestamps in ms)
    window.add(1678886401000, DataPoint(value="a"))  # Should be pruned
    window.add(1678886405000, DataPoint(value="b"))  # Should remain
    
    # Add a new item that forces a cleanup.
    # New time is 12s after the first item.
    window.add(1678886413000, DataPoint(value="c"))
    
    data = window.get_window_data()
    
    # Cutoff time = 1678886413000 - 10000 = 1678886403000.
    # So, "a" should be gone. "b" and "c" should remain.
    assert len(data) == 2
    assert data[0][1].value == "b"
    assert data[1][1].value == "c"

    # Add another item far in the future
    window.add(1678886420000, DataPoint(value="d"))
    data = window.get_window_data()
    # Cutoff time = 1678886420000 - 10000 = 1678886410000.
    # "b" should be gone. "c" and "d" should remain.
    assert len(data) == 2
    assert data[0][1].value == "c"
    assert data[1][1].value == "d"

def test_get_window_data_pruning():
    """Test that get_window_data() correctly triggers pruning."""
    window = SlidingWindow(10000)
    # Manually add raw data to bypass the `add` method's normalization for this test
    window._data.append((1678886401000, DataPoint(value="a"))) # Expired
    window._data.append((1678886412000, DataPoint(value="b"))) # Not expired
    
    # Calling get_window_data() should prune the expired item
    # because the latest timestamp is 1678886412000, making the cutoff 1678886402000.
    data = window.get_window_data()
    assert len(data) == 1
    assert data[0][1].value == "b"

def test_timestamp_normalization_in_window():
    """Test that the window correctly normalizes timestamps upon adding."""
    window = SlidingWindow(20000) # 20s window
    
    # Timestamps in s, ms, us, ns
    window.add(1678886400, DataPoint(value="a"))              # seconds
    window.add(1678886410000, DataPoint(value="b"))           # milliseconds
    window.add(1678886415000000, DataPoint(value="c"))        # microseconds
    window.add(1678886421000000000, DataPoint(value="d"))     # nanoseconds
    
    # Latest timestamp is 1678886421000, so cutoff is 1678886401000
    # "a" (at 1678886400000) should be pruned.
    
    data = window.get_window_data()
    assert len(data) == 3
    assert data[0][1].value == "b"
    assert data[1][1].value == "c"
    assert data[2][1].value == "d"

def test_empty_window():
    """Test behavior with an empty window."""
    window = SlidingWindow(1000)
    assert window.get_window_data() == []
    assert len(window) == 0
    assert window.get_latest() is None

def test_get_latest():
    """Test the get_latest() method."""
    window = SlidingWindow(10000)
    data_a = DataPoint(value="a")
    data_b = DataPoint(value="b")
    data_c = DataPoint(value="c")
    window.add(1000, data_a)
    assert window.get_latest() == data_a
    window.add(2000, data_b)
    assert window.get_latest() == data_b
    # Add an item that prunes the first one
    window.add(12000, data_c)
    assert window.get_latest() == data_c 