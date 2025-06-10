import logging

def normalize_timestamp_to_ms(ts: int) -> int:
    """
    Normalizes a timestamp to milliseconds.

    Infers the unit (s, ms, us, ns) from the number of digits and converts.

    Args:
        ts: The timestamp to normalize.

    Returns:
        The timestamp normalized to milliseconds.
    """
    num_digits = len(str(ts))

    if num_digits <= 10:  # Assumed to be seconds
        return ts * 1000
    elif num_digits <= 13:  # Assumed to be milliseconds
        return ts
    elif num_digits <= 16:  # Assumed to be microseconds
        return ts // 1000
    elif num_digits <= 19:  # Assumed to be nanoseconds
        return ts // 1_000_000
    else:
        logging.warning(f"Timestamp {ts} has an unexpected number of digits ({num_digits}). Assuming milliseconds.")
        return ts 