# This file makes the `statbot_common` directory a Python package.

from .sliding_window import SlidingWindow
from .volatility import compute_volatility
from .timestamp import normalize_timestamp_to_ms
from .protocols import HasPrice, HasSize, Trade, L3Trade, MidPrice
from .size import compute_total_size
from .vmf import compute_vmf
from .markout_skew import (
    MarkoutSkewCalculator, 
    MarkoutObservation, 
    MarkoutConfig,
    coalesce_l3_trades_by_timestamp,
    compute_mid_price,
    validate_l2_consistency
)
from importlib.metadata import version

__version__ = version("statbot-common")

# This defines the public API for the package.
# When a user does `from statbot_common import *`, only these names will be imported.
__all__ = [
    "SlidingWindow",
    "compute_volatility",
    "normalize_timestamp_to_ms",
    "HasPrice",
    "HasSize",
    "Trade",
    "L3Trade",
    "MidPrice",
    "compute_total_size",
    "compute_vmf",
    "MarkoutSkewCalculator",
    "MarkoutObservation",
    "MarkoutConfig",
    "coalesce_l3_trades_by_timestamp",
    "compute_mid_price",
    "validate_l2_consistency",
] 