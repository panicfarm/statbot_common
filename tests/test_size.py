import pytest
from statbot_common import compute_total_size
from dataclasses import dataclass

@dataclass
class Trade:
    price: float
    size: float

@dataclass
class OtherObject:
    value: int

def test_compute_total_size_happy_path():
    """Test with a standard list of trade objects."""
    data = [
        (1678886400000, Trade(price=100.0, size=1.5)),
        (1678886460000, Trade(price=101.0, size=0.5)),
        (1678886520000, Trade(price=100.5, size=2.0)),
    ]
    total_size = compute_total_size(data)
    assert total_size == pytest.approx(4.0)

def test_compute_total_size_empty_list():
    """Test with an empty list of data points."""
    assert compute_total_size([]) == 0.0

def test_compute_total_size_with_zero_size():
    """Test with trades that have zero size."""
    data = [
        (1678886400000, Trade(price=100.0, size=1.5)),
        (1678886460000, Trade(price=101.0, size=0.0)),
        (1678886520000, Trade(price=100.5, size=2.0)),
    ]
    total_size = compute_total_size(data)
    assert total_size == pytest.approx(3.5)

def test_compute_total_size_mixed_objects():
    """Test with a mix of conforming and non-conforming objects."""
    data = [
        (1678886400000, Trade(price=100.0, size=1.5)),
        (1678886430000, OtherObject(value=10)), # Should be ignored
        (1678886460000, Trade(price=101.0, size=0.5)),
    ]
    total_size = compute_total_size(data)
    assert total_size == pytest.approx(2.0)

def test_compute_total_size_all_non_conforming():
    """Test with a list containing only non-conforming objects."""
    data = [
        (1678886400000, OtherObject(value=10)),
        (1678886430000, OtherObject(value=20)),
    ]
    total_size = compute_total_size(data)
    assert total_size == 0.0 