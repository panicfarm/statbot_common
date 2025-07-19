# This file makes the `statbot_common` directory a Python package.

from .sliding_window import SlidingWindow
from .volatility import compute_volatility
from .timestamp import normalize_timestamp_to_ms
from .protocols import HasPrice, HasSize
from .size import compute_total_size

# This defines the public API for the package.
# When a user does `from statbot_common import *`, only these names will be imported.
__all__ = [
    "SlidingWindow",
    "compute_volatility",
    "normalize_timestamp_to_ms",
    "HasPrice",
    "HasSize",
    "compute_total_size",
] 