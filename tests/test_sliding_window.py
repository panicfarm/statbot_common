from statbot_common import SlidingWindow
import pytest

def test_window_initialization():
    """Test that the window initializes correctly."""
    window = SlidingWindow(10000)
    assert len(window) == 0
    assert window.get_window_data() == []

def test_add_and_get_data():
    """Test adding items and retrieving them."""
    window = SlidingWindow(10000)
    # Timestamps are in milliseconds for this test to avoid normalization confusion
    window.add(1678886401000, "a")
    window.add(1678886402000, "b")
    assert len(window) == 2
    assert window.get_window_data() == [(1678886401000, "a"), (1678886402000, "b")]

def test_window_pruning():
    """Test that the window correctly prunes expired entries."""
    window = SlidingWindow(10000) # 10 second window
    
    # Add initial items (timestamps in ms)
    window.add(1678886401000, "a")  # Should be pruned
    window.add(1678886405000, "b")  # Should remain
    
    # Add a new item that forces a cleanup.
    # New time is 12s after the first item.
    window.add(1678886413000, "c")
    
    data = window.get_window_data()
    
    # Cutoff time = 1678886413000 - 10000 = 1678886403000.
    # So, (1678886401000, "a") should be gone.
    # (1678886405000, "b") and (1678886413000, "c") should remain.
    assert len(data) == 2
    assert data == [(1678886405000, "b"), (1678886413000, "c")]

    # Add another item far in the future
    window.add(1678886420000, "d")
    data = window.get_window_data()
    # Cutoff time = 1678886420000 - 10000 = 1678886410000.
    # (1678886405000, "b") should be gone.
    # (1678886413000, "c") and (1678886420000, "d") should remain.
    assert len(data) == 2
    assert data == [(1678886413000, "c"), (1678886420000, "d")]

def test_get_window_data_pruning():
    """Test that get_window_data() correctly triggers pruning."""
    window = SlidingWindow(10000)
    # Manually add raw data to bypass the `add` method's normalization for this test
    window._data.append((1678886401000, "a")) # Expired
    window._data.append((1678886412000, "b")) # Not expired
    
    # Calling get_window_data() should prune the expired item
    # because the latest timestamp is 1678886412000, making the cutoff 1678886402000.
    data = window.get_window_data()
    assert data == [(1678886412000, "b")]

def test_timestamp_normalization_in_window():
    """Test that the window correctly normalizes timestamps upon adding."""
    window = SlidingWindow(20000) # 20s window
    
    # Timestamps in s, ms, us, ns
    window.add(1678886400, "a")              # seconds
    window.add(1678886410000, "b")           # milliseconds
    window.add(1678886415000000, "c")        # microseconds
    window.add(1678886421000000000, "d")     # nanoseconds
    
    # Latest timestamp is 1678886421000, so cutoff is 1678886401000
    # "a" (at 1678886400000) should be pruned.
    
    expected_data = [
        (1678886410000, "b"),
        (1678886415000, "c"),
        (1678886421000, "d"),
    ]
    
    assert window.get_window_data() == expected_data

def test_empty_window():
    """Test behavior with an empty window."""
    window = SlidingWindow(1000)
    assert window.get_window_data() == []
    assert len(window) == 0
    assert window.get_latest() is None

def test_get_latest():
    """Test the get_latest() method."""
    window = SlidingWindow(10000)
    window.add(1000, "a")
    assert window.get_latest() == "a"
    window.add(2000, "b")
    assert window.get_latest() == "b"
    # Add an item that prunes the first one
    window.add(12000, "c")
    assert window.get_latest() == "c" 