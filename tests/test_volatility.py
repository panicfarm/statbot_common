import pytest
from statbot_common import compute_volatility
from dataclasses import dataclass

@dataclass
class Trade:
    price: float

def test_volatility_not_enough_data():
    """Test that volatility returns None if there are fewer than 2 data points."""
    assert compute_volatility([(1, Trade(price=100.0))]) is None
    assert compute_volatility([]) is None

def test_volatility_constant_price():
    """Test that volatility is zero for a constant price."""
    data = [
        (1678886400000, Trade(price=100.0)),
        (1678886401000, Trade(price=100.0)),
        (1678886402000, Trade(price=100.0)),
    ]
    assert compute_volatility(data) == pytest.approx(0.0)

def test_volatility_varied_price():
    """Test a basic volatility calculation with a known varied price series."""
    base_time_ms = 1234567890000
    data = [
        (base_time_ms + 0,    Trade(price=250.00)),
        (base_time_ms + 2000, Trade(price=250.50)),
        (base_time_ms + 5000, Trade(price=250.25)),
        (base_time_ms + 9000, Trade(price=251.00)),
    ]
    
    # Manual calculation for verification:
    # d_t = [2000, 3000, 4000] ms -> [2/60, 3/60, 4/60] min
    # d_v = [log(250.5/250), log(250.25/250.5), log(251/250.25)]
    # d_v approx = [0.001998, -0.000998, 0.002994]
    # numerator = sum(d_v^2) = 0.000003992 + 0.000000996 + 0.000008964 = 0.000013952
    # denominator = sum(d_t_min) = (2+3+4)/60 = 9/60 = 0.15
    # variance_per_min = num / den = 0.000013952 / 0.15 = 0.000093013
    # vol = sqrt(variance) = 0.009644
    
    expected_vol = 0.0096443
    assert compute_volatility(data) == pytest.approx(expected_vol, abs=1e-5)

def test_volatility_with_different_timestamp_units():
    """Test that calculation works correctly with mixed timestamp resolutions."""
    base_time_s = 1234567890
    data = [
        (base_time_s,                          Trade(price=250.00)), # seconds
        ((base_time_s + 2) * 1000,             Trade(price=250.50)), # milliseconds
        ((base_time_s + 5) * 1_000_000_000,    Trade(price=250.25)), # nanoseconds
    ]

    # Manual calculation:
    # d_t = [2000, 3000] ms -> [2/60, 3/60] min
    # d_v approx = [0.001998, -0.000998]
    # numerator = sum(d_v^2) = 0.000003992 + 0.000000996 = 0.000004988
    # denominator = sum(d_t_min) = 5/60 = 0.08333
    # variance_per_min = num / den = 0.000059856
    # vol = sqrt(variance) = 0.007736
    
    expected_vol = 0.0077366
    assert compute_volatility(data) == pytest.approx(expected_vol, abs=1e-5)

def test_volatility_with_unsorted_data():
    """Test that the function correctly sorts data before calculation."""
    base_time_ms = 1234567890000
    data = [
        (base_time_ms + 9000, Trade(price=251.00)), # Out of order
        (base_time_ms + 0,    Trade(price=250.00)),
        (base_time_ms + 5000, Trade(price=250.25)),
        (base_time_ms + 2000, Trade(price=250.50)),
    ]
    expected_vol = 0.0096443
    assert compute_volatility(data) == pytest.approx(expected_vol, abs=1e-5)

def test_volatility_with_missing_price():
    """Test robustness against objects without a 'price' attribute."""
    @dataclass
    class BadTrade:
        value: float

    data = [
        (1678886400000, Trade(price=100.0)),
        (1678886460000, BadTrade(value=101.0)),
        (1678886520000, Trade(price=100.5)),
    ]
    # The bad trade is skipped, calculation happens on first and third.
    # Time delta = 2 mins. Log price delta = log(100.5/100) = 0.004987
    # Numerator = 0.004987^2 = 0.00002487
    # Denominator = 2
    # Variance = num/den = 0.000012435
    # Vol = sqrt(variance) = 0.003526
    vol = compute_volatility(data)
    assert vol == pytest.approx(0.003526, abs=1e-5)
    
    # Test with only one valid point remaining
    data_one_valid = [
        (1678886400000, Trade(price=100.0)),
        (1678886460000, BadTrade(value=101.0)),
    ]
    assert compute_volatility(data_one_valid) is None 