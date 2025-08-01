from typing import Protocol, Optional

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