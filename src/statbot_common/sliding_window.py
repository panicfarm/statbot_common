from collections import deque
from typing import Deque, Tuple, Any, List
from .timestamp import normalize_timestamp_to_ms

class SlidingWindow:
    """
    A generic, time-based sliding window for storing timestamped data.
    
    This class manages a deque of (timestamp, data) tuples and automatically
    prunes entries that are older than the specified window duration.
    It automatically normalizes timestamps to milliseconds.
    """

    def __init__(self, window_duration_ms: int):
        """
        Initializes the sliding window.
        
        Args:
            window_duration_ms: The duration of the window in milliseconds.
        """
        if window_duration_ms <= 0:
            raise ValueError("Window duration must be positive.")
            
        self.window_duration_ms = window_duration_ms
        self._data: Deque[Tuple[int, Any]] = deque()

    def add(self, timestamp: int, data: Any):
        """
        Adds a new data point to the window, normalizing the timestamp.
        
        It is assumed that timestamps are monotonically increasing.
        
        Args:
            timestamp: The Unix timestamp (s, ms, us, or ns).
            data: The data point to store.
        """
        ts_ms = normalize_timestamp_to_ms(timestamp)
        self._data.append((ts_ms, data))
        self._cleanup(ts_ms)

    def get_window_data(self) -> List[Tuple[int, Any]]:
        """
        Returns all data points currently within the time window.
        
        Also performs a cleanup based on the timestamp of the latest entry.
        
        Returns:
            A list of (timestamp_ms, data) tuples.
        """
        if not self._data:
            return []
            
        latest_timestamp = self._data[-1][0]
        self._cleanup(latest_timestamp)
        
        return list(self._data)

    def _cleanup(self, current_timestamp_ms: int):
        """
        Removes expired data points from the left of the deque.
        """
        if not self._data:
            return
            
        cutoff_time = current_timestamp_ms - self.window_duration_ms
        
        while self._data and self._data[0][0] < cutoff_time:
            self._data.popleft()
            
    def __len__(self) -> int:
        """Returns the number of items currently in the window."""
        return len(self._data)

    def get_latest(self) -> Any:
        """Returns the most recently added data point, or None if empty."""
        if not self._data:
            return None
        return self._data[-1][1]

    def purge(self, window_end_timestamp_ms: int):
        """
        Explicitly removes data points that are older than the specified window end time.
        
        This method provides precise control over window boundaries by removing all data points
        whose timestamps are older than (window_end_timestamp_ms - window_duration_ms).
        
        Args:
            window_end_timestamp_ms: The absolute end timestamp of the desired window in milliseconds.
                                   Data points older than (window_end_timestamp_ms - window_duration_ms) 
                                   will be removed.
        """
        end_timestamp_ms = normalize_timestamp_to_ms(window_end_timestamp_ms)
        self._cleanup(end_timestamp_ms) 