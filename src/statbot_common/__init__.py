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
from .queue_imbalance import (
    compute_exponential_weights,
    sizes_on_tick_grid,
    compute_ib,
    compute_queue_diff,
    QueueImbalanceConfig,
    QueueImbalanceCalculator,
)
from importlib.metadata import PackageNotFoundError, version

# Attempt to grab the installed package version.  When the project is
# imported from source (e.g. in a testing environment where the package has
# not been installed), ``importlib.metadata.version`` raises a
# ``PackageNotFoundError``.  Previously this bubbled up during import and
# prevented the library from being used at all.  Instead, fall back to a
# sensible default so the modules can be imported without installation.
try:
    __version__ = version("statbot-common")
except PackageNotFoundError:  # pragma: no cover - exercised in tests
    __version__ = "0.0.0"

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
    "compute_exponential_weights",
    "sizes_on_tick_grid",
    "compute_ib",
    "compute_queue_diff",
    "QueueImbalanceConfig",
    "QueueImbalanceCalculator",
] 