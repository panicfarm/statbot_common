from typing import Protocol, Optional, Literal

class HasPrice(Protocol):
    """A protocol for objects that have a price attribute."""
    price: float

class HasSize(Protocol):
    """A protocol for objects that have a size attribute."""
    size: float

class Trade(Protocol):
    """A protocol for trade objects with timestamp, quantity, and optional side."""
    timestamp: int  # Unix timestamp (any unit - will be normalized)
    quantity: float
    side: Optional[str] = None  # 'buy', 'sell', or None for combined

class L3Trade(Trade, Protocol):
    """L3 trade with aggressor side for markout calculations."""
    aggressor_sign: Literal[1, -1]  # +1 = buy aggressor, -1 = sell aggressor
    price: float  # Trade price (required for markout)

class MidPrice(HasPrice, Protocol):
    """Mid-price at a timestamp for markout calculations."""
    timestamp: int  # Unix timestamp (any unit - will be normalized) 