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
    q0 = qi.compute_queue_diff(b, a, w)
    assert q0 is not None
    assert abs(float(q0)) <= 1e-12

    # All ask zero => raw QI equals weighted bid depth
    b = [Decimal("5"), Decimal("2"), Decimal("1")]
    a = [Decimal("0"), Decimal("0"), Decimal("0")]
    q_pos = qi.compute_queue_diff(b, a, w)
    assert q_pos is not None
    # D_bid = 5 + 0.5*2 + 0.25*1 = 25/4
    assert q_pos == (Decimal(25) / Decimal(4))

    # All bid zero => raw QI equals negative weighted ask depth
    b = [Decimal("0"), Decimal("0"), Decimal("0")]
    a = [Decimal("3"), Decimal("2"), Decimal("1")]
    q_neg = qi.compute_queue_diff(b, a, w)
    assert q_neg is not None
    # D_ask = 3 + 0.5*2 + 0.25*1 = 17/4
    assert q_neg == -(Decimal(17) / Decimal(4))

    # Zero denominator => None
    b = [Decimal("0"), Decimal("0"), Decimal("0")]
    a = [Decimal("0"), Decimal("0"), Decimal("0")]
    q_none = qi.compute_queue_diff(b, a, w)
    assert q_none is None


def test_ib_normal_value():
    # A non-edge case: IB strictly between -1 and 1 and not 0
    hl = Decimal("1.0")
    w = qi.compute_exponential_weights(3, hl)

    b = [Decimal("10"), Decimal("5"), Decimal("1")]  # bids
    a = [Decimal("8"), Decimal("3"), Decimal("2")]   # asks

    q = qi.compute_queue_diff(b, a, w)
    assert q is not None

    # Manual expected (raw):
    # D_bid = 10 + 0.5*5 + 0.25*1 = 12.75 = 51/4
    # D_ask =  8 + 0.5*3 + 0.25*2 = 10.00 = 40/4
    # QI = 51/4 - 40/4 = 11/4
    expected = Decimal(11) / Decimal(4)
    assert q == expected

    # Extended case: K=4 while the book has 7 levels per side
    # Build a 7-level book around the touch
    best_bid = Decimal("100.00")
    best_ask = Decimal("100.01")
    tick = Decimal("0.01")
    k_levels = 4
    hl4 = Decimal("1.0")
    w4 = qi.compute_exponential_weights(k_levels, hl4)  # [1, 1/2, 1/4, 1/8]

    bids_map = {
        Decimal("100.00"): Decimal("10"),
        Decimal("99.99"): Decimal("9"),
        Decimal("99.98"): Decimal("8"),
        Decimal("99.97"): Decimal("7"),
        Decimal("99.96"): Decimal("6"),
        Decimal("99.95"): Decimal("5"),
        Decimal("99.94"): Decimal("4"),
    }
    asks_map = {
        Decimal("100.01"): Decimal("8"),
        Decimal("100.02"): Decimal("7"),
        Decimal("100.03"): Decimal("6"),
        Decimal("100.04"): Decimal("5"),
        Decimal("100.05"): Decimal("4"),
        Decimal("100.06"): Decimal("3"),
        Decimal("100.07"): Decimal("2"),
    }

    b4, a4 = qi.sizes_on_tick_grid(best_bid, best_ask, tick, k_levels, bids_map, asks_map)
    # Only the first 4 levels should be considered
    assert b4 == [Decimal("10"), Decimal("9"), Decimal("8"), Decimal("7")]
    assert a4 == [Decimal("8"), Decimal("7"), Decimal("6"), Decimal("5")]

    qi4 = qi.compute_queue_diff(b4, a4, w4)
    assert qi4 is not None

    # Manual expected using weights [1, 1/2, 1/4, 1/8]
    # D_bid = 10 + 0.5*9 + 0.25*8 + 0.125*7 = 139/8 = 17.375
    # D_ask =  8 + 0.5*7 + 0.25*6 + 0.125*5 = 109/8 = 13.625
    # QI = (139/8) - (109/8) = 30/8 = 15/4
    expected4 = Decimal(15) / Decimal(4)
    assert qi4 == expected4

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
    # Segment1: QI = +10 from [base, base+5000)
    bids1 = {Decimal("100.00"): Decimal("10")}
    asks1 = {Decimal("100.01"): Decimal("0")}
    calc.update_from_book(base, Decimal("100.00"), Decimal("100.01"), bids1, asks1)

    # Segment2: QI = -8 from [base+5000, base+10000)
    bids2 = {Decimal("100.00"): Decimal("0")}
    asks2 = {Decimal("100.01"): Decimal("8")}
    calc.update_from_book(base + 5000, Decimal("100.00"), Decimal("100.01"), bids2, asks2)

    # Evaluate TW mean at T=base+10000 over window [base, base+10000]
    tw = calc.get_time_weighted_mean(base + 10_000)
    # Raw segments: +10 for 5s, then -8 for 5s => TW mean = +1
    assert tw is not None
    assert tw == Decimal(1)


