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

def test_purge_method():
    """Test the purge() method for explicit time-based cleanup."""
    window = SlidingWindow(10000)  # 10 second window
    
    # Add test data (timestamps in ms)
    window.add(1678886401000, DataPoint(value="a"))  # t=1000
    window.add(1678886405000, DataPoint(value="b"))  # t=5000
    window.add(1678886410000, DataPoint(value="c"))  # t=10000
    
    # All items should be present initially
    assert len(window) == 3
    
    # Purge with window end at t=12000
    # Cutoff time = 12000 - 10000 = 2000
    # So only "a" (at t=1000) should be removed
    window.purge(1678886412000)
    
    data = window.get_window_data()
    assert len(data) == 2
    assert data[0][1].value == "b"
    assert data[1][1].value == "c"
    
    # Purge with window end at t=20000
    # Cutoff time = 20000 - 10000 = 10000
    # So "b" (at t=5000) should be removed, only "c" (at t=10000) remains
    window.purge(1678886420000)
    
    data = window.get_window_data()
    assert len(data) == 1
    assert data[0][1].value == "c"

def test_purge_timestamp_normalization():
    """Test that purge() correctly normalizes different timestamp formats."""
    window = SlidingWindow(10000)  # 10 second window
    
    # Add data with millisecond timestamps
    window.add(1678886400000, DataPoint(value="a"))  # t=0
    window.add(1678886405000, DataPoint(value="b"))  # t=5000
    window.add(1678886410000, DataPoint(value="c"))  # t=10000
    
    # Purge using a timestamp in seconds (should be normalized to ms)
    # 1678886412 seconds = 1678886412000 ms
    # Cutoff = 1678886412000 - 10000 = 1678886402000
    # So "a" should be removed
    window.purge(1678886412)  # timestamp in seconds
    
    data = window.get_window_data()
    assert len(data) == 2
    assert data[0][1].value == "b"
    assert data[1][1].value == "c"

def test_purge_empty_window():
    """Test purge() behavior on an empty window."""
    window = SlidingWindow(10000)
    
    # Should not raise an error
    window.purge(1678886400000)
    assert len(window) == 0
    assert window.get_window_data() == []

def test_purge_no_items_to_remove():
    """Test purge() when no items need to be removed.""" 
    window = SlidingWindow(10000)
    
    # Add recent data
    window.add(1678886410000, DataPoint(value="a"))
    window.add(1678886415000, DataPoint(value="b"))
    
    # Purge with a window end that keeps all data
    # Cutoff = 1678886420000 - 10000 = 1678886410000
    # Both items should remain (timestamps >= cutoff)
    window.purge(1678886420000)
    
    data = window.get_window_data()
    assert len(data) == 2
    assert data[0][1].value == "a"
    assert data[1][1].value == "b"

def test_purge_deterministic_behavior():
    """Test that purge() provides deterministic behavior compared to implicit cleanup."""
    window1 = SlidingWindow(10000)
    window2 = SlidingWindow(10000)
    
    # Add same data to both windows
    test_data = [
        (1678886400000, DataPoint(value="a")),
        (1678886405000, DataPoint(value="b")),
        (1678886410000, DataPoint(value="c")),
        (1678886415000, DataPoint(value="d"))
    ]
    
    for ts, data in test_data:
        window1.add(ts, data)
        window2.add(ts, data)
    
    # Window1: use implicit cleanup by adding new data
    window1.add(1678886422000, DataPoint(value="e"))
    
    # Window2: use explicit purge at the same timestamp
    window2.purge(1678886422000)
    
    # Both should have the same result
    data1 = window1.get_window_data()
    data2 = window2.get_window_data()
    
    # Remove the "e" item from window1 for comparison
    data1_without_e = [item for item in data1 if item[1].value != "e"]
    
    assert len(data1_without_e) == len(data2)
    for i in range(len(data2)):
        assert data1_without_e[i][0] == data2[i][0]  # Same timestamps
        assert data1_without_e[i][1].value == data2[i][1].value  # Same values 