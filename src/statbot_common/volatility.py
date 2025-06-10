import math
import logging
from typing import List, Tuple, Optional
from .timestamp import normalize_timestamp_to_ms

def compute_volatility(
    data_points: List[Tuple[int, float]],
) -> Optional[float]:
    """
    Compute volatility from a list of (timestamp, value) tuples.

    This function accounts for uneven time intervals between data points
    and automatically normalizes timestamps to milliseconds.
    The value is typically the log of the price.

    Args:
        data_points: A list of tuples, where each tuple contains a
                     Unix timestamp (s, ms, us, or ns) and a float value.

    Returns:
        The calculated volatility per minute, or None if computation is not possible.
    """
    if len(data_points) < 2:
        logging.debug("Volatility calc: Not enough data points (< 2).")
        return None

    # Normalize all timestamps to milliseconds first
    normalized_data = [
        (normalize_timestamp_to_ms(ts), value) for ts, value in data_points
    ]

    # Ensure data is sorted by timestamp, as it may not be guaranteed.
    sorted_data = sorted(normalized_data, key=lambda x: x[0])

    delta_values = []
    delta_times_minutes = []

    for i in range(len(sorted_data) - 1):
        ts_curr, val_curr = sorted_data[i]
        ts_next, val_next = sorted_data[i + 1]

        delta_value = val_next - val_curr
        delta_time_ms = ts_next - ts_curr
        
        # Convert time delta from milliseconds to minutes
        delta_time_min = delta_time_ms / 60000.0

        if delta_time_min > 0:
            delta_values.append(delta_value)
            delta_times_minutes.append(delta_time_min)
        else:
            logging.warning(
                f"Volatility calc: Non-positive time delta ({delta_time_min} min) "
                f"between point {i} ({ts_curr}) and {i + 1} ({ts_next}). Skipping."
            )

    if not delta_values or not delta_times_minutes:
        logging.debug("Volatility calc: No valid time intervals found.")
        return None

    # Sum of squared log returns
    numerator = sum(dv**2 for dv in delta_values)
    # Total time duration in minutes
    denominator = sum(delta_times_minutes)

    if denominator > 0:
        try:
            variance_per_minute = numerator / denominator
            volatility = math.sqrt(variance_per_minute)
            return volatility
        except ValueError:
            logging.error(f"Volatility calc: Math domain error for variance={variance_per_minute:.8f}")
            return None
    else:
        logging.debug("Volatility calc: Zero total time interval, cannot compute volatility.")
        return None 