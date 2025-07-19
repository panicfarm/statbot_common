from typing import List, Tuple
from .protocols import HasSize

def compute_total_size(
    data_points: List[Tuple[int, HasSize]],
) -> float:
    """
    Compute the total size from a list of (timestamp, data) tuples.

    Args:
        data_points: A list of tuples, where each tuple contains a
                     timestamp and an object that conforms to the HasSize protocol.

    Returns:
        The total size of all data points.
    """
    if not data_points:
        return 0.0

    total_size = 0.0
    for _, data in data_points:
        if hasattr(data, 'size'):
            total_size += data.size

    return total_size 