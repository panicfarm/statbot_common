import pytest
from decimal import Decimal


# Skip all tests in this module until the implementation exists
qi = pytest.importorskip("statbot_common.queue_imbalance")


def test_exponential_weights_half_life_default():
    # HL = 0.5 ticks, K = 4
    hl = Decimal("0.5")
    weights = qi.compute_exponential_weights(4, hl)
    # Expected: [1.0, 0.25, 0.0625, 0.015625]
    expected = [1.0, 0.25, 0.0625, 0.015625]
    assert len(weights) == 4
    for w, e in zip(weights, expected):
        assert pytest.approx(float(w), rel=1e-12, abs=1e-12) == e


def test_tick_grid_zero_padding():
    # Best bid/ask and tick size
    best_bid = Decimal("100.00")
    best_ask = Decimal("100.01")
    tick = Decimal("0.01")
    k = 3
    # Raw books with gaps
    bids = {
        Decimal("100.00"): Decimal("5"),
        # 99.99 missing -> zero pad
        Decimal("99.98"): Decimal("7"),
    }
    asks = {
        Decimal("100.01"): Decimal("4"),
        # 100.02 missing -> zero pad
        Decimal("100.03"): Decimal("6"),
    }
    b_sizes, a_sizes = qi.sizes_on_tick_grid(best_bid, best_ask, tick, k, bids, asks)
    assert b_sizes == [Decimal("5"), Decimal("0"), Decimal("7")]
    assert a_sizes == [Decimal("4"), Decimal("0"), Decimal("6")]


def test_ib_symmetry_and_extremes():
    hl = Decimal("1.0")
    w = qi.compute_exponential_weights(3, hl)

    # Symmetry: equal sizes => IB = 0
    b = [Decimal("10"), Decimal("10"), Decimal("10")]
    a = [Decimal("10"), Decimal("10"), Decimal("10")]
    ib0 = qi.compute_ib(b, a, w)
    assert ib0 is not None
    assert abs(float(ib0)) <= 1e-12

    # All ask zero => IB = +1
    b = [Decimal("5"), Decimal("2"), Decimal("1")]
    a = [Decimal("0"), Decimal("0"), Decimal("0")]
    ib_pos = qi.compute_ib(b, a, w)
    assert ib_pos is not None
    assert pytest.approx(float(ib_pos), rel=1e-12, abs=1e-12) == 1.0

    # All bid zero => IB = -1
    b = [Decimal("0"), Decimal("0"), Decimal("0")]
    a = [Decimal("3"), Decimal("2"), Decimal("1")]
    ib_neg = qi.compute_ib(b, a, w)
    assert ib_neg is not None
    assert pytest.approx(float(ib_neg), rel=1e-12, abs=1e-12) == -1.0

    # Zero denominator => None
    b = [Decimal("0"), Decimal("0"), Decimal("0")]
    a = [Decimal("0"), Decimal("0"), Decimal("0")]
    ib_none = qi.compute_ib(b, a, w)
    assert ib_none is None


def test_ib_normal_value():
    # A non-edge case: IB strictly between -1 and 1 and not 0
    hl = Decimal("1.0")
    w = qi.compute_exponential_weights(3, hl)

    b = [Decimal("10"), Decimal("5"), Decimal("1")]  # bids
    a = [Decimal("8"), Decimal("3"), Decimal("2")]   # asks

    ib = qi.compute_ib(b, a, w)
    assert ib is not None

    # Manual expected:
    # D_bid = 10 + 0.5*5 + 0.25*1 = 12.75
    # D_ask =  8 + 0.5*3 + 0.25*2 = 10.00
    # IB = (12.75 - 10.00) / (12.75 + 10.00) = 2.75 / 22.75 = 11/91 ≈ 0.1208791208791209
    expected = Decimal(11) / Decimal(91)
    assert ib == expected

def test_time_weighted_mean_segments():
    # Configure calculator
    config = qi.QueueImbalanceConfig(
        k_levels=3,
        tick_size=Decimal("0.01"),
        half_life_ticks=Decimal("0.5"),
        window_ms=10_000,
    )
    calc = qi.QueueImbalanceCalculator(config)

    # Synthetic book snapshots at base epoch ms to avoid unit inference issues
    base = 1_700_000_000_000  # ms
    # Segment1: IB = +1 from [base, base+5000)
    bids1 = {Decimal("100.00"): Decimal("10")}
    asks1 = {Decimal("100.01"): Decimal("0")}
    calc.update_from_book(base, Decimal("100.00"), Decimal("100.01"), bids1, asks1)

    # Segment2: IB = -1 from [base+5000, base+10000)
    bids2 = {Decimal("100.00"): Decimal("0")}
    asks2 = {Decimal("100.01"): Decimal("8")}
    calc.update_from_book(base + 5000, Decimal("100.00"), Decimal("100.01"), bids2, asks2)

    # Evaluate TW mean at T=base+10000 over window [base, base+10000]
    tw = calc.get_time_weighted_mean(base + 10_000)
    # Half time at +1, half at -1 => mean 0
    assert tw is not None
    assert abs(float(tw)) <= 1e-12


