from typing import Protocol

class HasPrice(Protocol):
    """A protocol for objects that have a price attribute."""
    price: float

class HasSize(Protocol):
    """A protocol for objects that have a size attribute."""
    size: float 