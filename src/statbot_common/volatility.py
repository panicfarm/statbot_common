import math
import logging
from typing import List, Tuple, Optional
from .timestamp import normalize_timestamp_to_ms
from .protocols import HasLogPrice

def compute_volatility(
    data_points: List[Tuple[int, HasLogPrice]],
) -> Optional[float]:
    """
    Compute volatility from a list of (timestamp, data) tuples.

    This function accounts for uneven time intervals between data points
    and automatically normalizes timestamps to milliseconds.
    The data objects are expected to conform to the HasLogPrice protocol.

    IMPORTANT: The caller is responsible for computing the log-price (or any
    other log-transformed coordinate such as log-odds/logit) before passing
    data to this function. This allows domain-specific transforms (e.g.,
    clipping probabilities, converting to odds) to be handled at the
    application layer.

    Args:
        data_points: A list of tuples, where each tuple contains a
                     Unix timestamp (s, ms, us, or ns) and an object
                     with a 'log_price' attribute (the log of the price,
                     or log-odds, or any log-transformed coordinate).

    Returns:
        The calculated volatility per minute, or None if computation is not possible.
    """
    if len(data_points) < 2:
        logging.debug("Volatility calc: Not enough data points (< 2).")
        return None

    # Extract log-prices and normalize timestamps
    log_price_data = []
    for ts, data in data_points:
        if hasattr(data, 'log_price'):
            try:
                log_price_data.append(
                    (normalize_timestamp_to_ms(ts), float(data.log_price))
                )
            except (ValueError, TypeError):
                logging.warning(f"Could not process log_price: {data.log_price}. Skipping entry.")
        else:
            logging.warning(f"Data object missing 'log_price' attribute. Skipping entry.")


    if len(log_price_data) < 2:
        logging.debug("Volatility calc: Not enough valid data points after filtering.")
        return None


    # Ensure data is sorted by timestamp, as it may not be guaranteed.
    sorted_data = sorted(log_price_data, key=lambda x: x[0])

    delta_values = []
    delta_times_minutes = []

    for i in range(len(sorted_data) - 1):
        ts_curr, val_curr = sorted_data[i]
        ts_next, val_next = sorted_data[i + 1]

        delta_value = val_next - val_curr
        delta_time_ms = ts_next - ts_curr
        
        # Convert time delta from milliseconds to minutes
        delta_time_min = delta_time_ms / 60000.0

        if delta_time_min == 0:
            logging.debug(
                f"Volatility calc: Zero time delta ({delta_time_min} min) "
                f"between point {i} ({ts_curr}) and {i + 1} ({ts_next}). Skipping."
            )
        elif delta_time_min < 0:
            logging.warning(
                f"Volatility calc: Negative time delta ({delta_time_min} min) "
                f"between point {i} ({ts_curr}) and {i + 1} ({ts_next}). Skipping."
            )
        else:
            delta_values.append(delta_value)
            delta_times_minutes.append(delta_time_min)

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
