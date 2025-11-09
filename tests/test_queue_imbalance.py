import pytest
from decimal import Decimal


# Skip all tests in this module until the implementation exists
qi = pytest.importorskip("statbot_common.queue_imbalance")


def test_exponential_weights_half_life_default():
    """Test exponential weights with HL=0.5 ticks, K=4."""
    hl = Decimal("0.5")
    weights = qi.compute_exponential_weights(4, hl)
    # Expected: [1.0, 0.25, 0.0625, 0.015625]
    expected = [1.0, 0.25, 0.0625, 0.015625]
    assert len(weights) == 4
    for w, e in zip(weights, expected):
        assert pytest.approx(float(w), rel=1e-12, abs=1e-12) == e


def test_exponential_weights_half_life_one():
    """Test exponential weights with HL=1.0 ticks, K=3."""
    hl = Decimal("1.0")
    weights = qi.compute_exponential_weights(3, hl)
    # Expected: [1.0, 0.5, 0.25]
    expected = [1.0, 0.5, 0.25]
    assert len(weights) == 3
    for w, e in zip(weights, expected):
        assert w == Decimal(str(e))


def test_exponential_weights_validation():
    """Test that invalid inputs raise ValueError."""
    with pytest.raises(ValueError):
        qi.compute_exponential_weights(0, Decimal("0.5"))
    with pytest.raises(ValueError):
        qi.compute_exponential_weights(3, Decimal("0"))
    with pytest.raises(ValueError):
        qi.compute_exponential_weights(3, Decimal("-1"))


def test_tick_grid_zero_padding():
    """Test that missing tick levels are padded with zero."""
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


def test_tick_grid_validation():
    """Test that invalid tick_size or k_levels raise ValueError."""
    best_bid = Decimal("100.00")
    best_ask = Decimal("100.01")
    bids = {Decimal("100.00"): Decimal("5")}
    asks = {Decimal("100.01"): Decimal("4")}
    
    with pytest.raises(ValueError):
        qi.sizes_on_tick_grid(best_bid, best_ask, Decimal("0"), 3, bids, asks)
    with pytest.raises(ValueError):
        qi.sizes_on_tick_grid(best_bid, best_ask, Decimal("0.01"), 0, bids, asks)


def test_queue_diff_symmetry_and_extremes():
    """Test raw queue difference (QI) for symmetry and extreme cases."""
    hl = Decimal("1.0")
    w = qi.compute_exponential_weights(3, hl)  # [1, 0.5, 0.25]

    # Symmetry: equal sizes => QI = 0
    b = [Decimal("10"), Decimal("10"), Decimal("10")]
    a = [Decimal("10"), Decimal("10"), Decimal("10")]
    q0 = qi.compute_queue_diff(b, a, w)
    assert q0 is not None
    assert q0 == Decimal("0")

    # All ask zero => raw QI equals weighted bid depth
    b = [Decimal("5"), Decimal("2"), Decimal("1")]
    a = [Decimal("0"), Decimal("0"), Decimal("0")]
    q_pos = qi.compute_queue_diff(b, a, w)
    assert q_pos is not None
    # D_bid = 5 + 0.5*2 + 0.25*1 = 5 + 1 + 0.25 = 6.25 = 25/4
    assert q_pos == Decimal(25) / Decimal(4)

    # All bid zero => raw QI equals negative weighted ask depth
    b = [Decimal("0"), Decimal("0"), Decimal("0")]
    a = [Decimal("3"), Decimal("2"), Decimal("1")]
    q_neg = qi.compute_queue_diff(b, a, w)
    assert q_neg is not None
    # D_ask = 3 + 0.5*2 + 0.25*1 = 3 + 1 + 0.25 = 4.25 = 17/4
    # QI = 0 - 17/4 = -17/4
    assert q_neg == -(Decimal(17) / Decimal(4))

    # Both sides zero => None
    b = [Decimal("0"), Decimal("0"), Decimal("0")]
    a = [Decimal("0"), Decimal("0"), Decimal("0")]
    q_none = qi.compute_queue_diff(b, a, w)
    assert q_none is None


def test_queue_diff_normal_value():
    """Test raw queue difference for a normal case with K=3."""
    hl = Decimal("1.0")
    w = qi.compute_exponential_weights(3, hl)  # [1, 0.5, 0.25]

    b = [Decimal("10"), Decimal("5"), Decimal("1")]  # bids
    a = [Decimal("8"), Decimal("3"), Decimal("2")]   # asks

    q = qi.compute_queue_diff(b, a, w)
    assert q is not None

    # Manual calculation:
    # D_bid = 10 + 0.5*5 + 0.25*1 = 10 + 2.5 + 0.25 = 12.75 = 51/4
    # D_ask =  8 + 0.5*3 + 0.25*2 =  8 + 1.5 + 0.5  = 10.00 = 40/4
    # QI = 51/4 - 40/4 = 11/4
    expected = Decimal(11) / Decimal(4)
    assert q == expected


def test_queue_diff_k4_with_7level_book():
    """Test raw queue difference with K=4 when book has 7 levels per side."""
    best_bid = Decimal("100.00")
    best_ask = Decimal("100.01")
    tick = Decimal("0.01")
    k_levels = 4
    hl4 = Decimal("1.0")
    w4 = qi.compute_exponential_weights(k_levels, hl4)  # [1, 0.5, 0.25, 0.125]

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

    # Manual calculation using weights [1, 0.5, 0.25, 0.125]:
    # D_bid = 10 + 0.5*9 + 0.25*8 + 0.125*7 = 10 + 4.5 + 2 + 0.875 = 17.375 = 139/8
    # D_ask =  8 + 0.5*7 + 0.25*6 + 0.125*5 =  8 + 3.5 + 1.5 + 0.625 = 13.625 = 109/8
    # QI = 139/8 - 109/8 = 30/8 = 15/4
    expected4 = Decimal(15) / Decimal(4)
    assert qi4 == expected4


def test_queue_diff_length_mismatch():
    """Test that mismatched input lengths raise ValueError."""
    w = [Decimal("1"), Decimal("0.5")]
    b = [Decimal("10"), Decimal("5")]
    a = [Decimal("8")]
    
    with pytest.raises(ValueError):
        qi.compute_queue_diff(b, a, w)


def test_calculator_update_from_book():
    """Test QueueImbalanceCalculator.update_from_book computes raw QI correctly."""
    config = qi.QueueImbalanceConfig(
        k_levels=3,
        tick_size=Decimal("0.01"),
        half_life_ticks=Decimal("1.0"),
        window_ms=30_000,
    )
    calc = qi.QueueImbalanceCalculator(config)

    base = 1_700_000_000_000  # ms
    bids = {Decimal("100.00"): Decimal("10"), Decimal("99.99"): Decimal("5")}
    asks = {Decimal("100.01"): Decimal("8"), Decimal("100.02"): Decimal("3")}

    qi_val = calc.update_from_book(base, Decimal("100.00"), Decimal("100.01"), bids, asks)
    assert qi_val is not None
    
    # With HL=1.0, K=3: weights = [1, 0.5, 0.25]
    # Tick grid: b=[10, 5, 0], a=[8, 3, 0]
    # D_bid = 10 + 0.5*5 + 0.25*0 = 12.5 = 25/2
    # D_ask =  8 + 0.5*3 + 0.25*0 =  9.5 = 19/2
    # QI = 25/2 - 19/2 = 6/2 = 3
    assert qi_val == Decimal(3)


def test_calculator_update_from_book_missing_best():
    """Test that missing best bid/ask returns None."""
    config = qi.QueueImbalanceConfig(
        k_levels=3,
        tick_size=Decimal("0.01"),
        half_life_ticks=Decimal("0.5"),
        window_ms=10_000,
    )
    calc = qi.QueueImbalanceCalculator(config)

    base = 1_700_000_000_000
    bids = {Decimal("100.00"): Decimal("10")}
    asks = {Decimal("100.01"): Decimal("8")}

    # Missing best bid
    qi_val = calc.update_from_book(base, None, Decimal("100.01"), bids, asks)
    assert qi_val is None

    # Missing best ask
    qi_val = calc.update_from_book(base + 1000, Decimal("100.00"), None, bids, asks)
    assert qi_val is None


def test_time_weighted_mean_segments():
    """Test time-weighted mean over a window with multiple segments."""
    config = qi.QueueImbalanceConfig(
        k_levels=3,
        tick_size=Decimal("0.01"),
        half_life_ticks=Decimal("0.5"),
        window_ms=10_000,
    )
    calc = qi.QueueImbalanceCalculator(config)

    base = 1_700_000_000_000  # ms
    # Segment1: QI = +10 from [base, base+5000)
    # With HL=0.5, K=3: weights = [1, 0.25, 0.0625]
    # bids1 = {100.00: 10}, asks1 = {100.01: 0}
    # Tick grid: b=[10, 0, 0], a=[0, 0, 0]
    # D_bid = 10*1 = 10, D_ask = 0 => QI = 10
    bids1 = {Decimal("100.00"): Decimal("10")}
    asks1 = {Decimal("100.01"): Decimal("0")}
    calc.update_from_book(base, Decimal("100.00"), Decimal("100.01"), bids1, asks1)

    # Segment2: QI = -8 from [base+5000, base+10000)
    # bids2 = {100.00: 0}, asks2 = {100.01: 8}
    # Tick grid: b=[0, 0, 0], a=[8, 0, 0]
    # D_bid = 0, D_ask = 8*1 = 8 => QI = -8
    bids2 = {Decimal("100.00"): Decimal("0")}
    asks2 = {Decimal("100.01"): Decimal("8")}
    calc.update_from_book(base + 5000, Decimal("100.00"), Decimal("100.01"), bids2, asks2)

    # Evaluate TW mean at T=base+10000 over window [base, base+10000]
    tw = calc.get_time_weighted_mean(base + 10_000)
    # TW mean = (10*5000 + (-8)*5000) / 10000 = (50000 - 40000) / 10000 = 1
    assert tw is not None
    assert tw == Decimal(1)


def test_time_weighted_mean_window_pruning():
    """Test that old segments are pruned from the window."""
    config = qi.QueueImbalanceConfig(
        k_levels=3,
        tick_size=Decimal("0.01"),
        half_life_ticks=Decimal("0.5"),
        window_ms=10_000,
    )
    calc = qi.QueueImbalanceCalculator(config)

    base = 1_700_000_000_000
    # Add segment at base: QI=10
    calc.update_from_book(base, Decimal("100.00"), Decimal("100.01"),
                          {Decimal("100.00"): Decimal("10")}, {Decimal("100.01"): Decimal("0")})
    
    # Add segment at base+5000: QI=0 (balanced)
    calc.update_from_book(base + 5000, Decimal("100.00"), Decimal("100.01"),
                          {Decimal("100.00"): Decimal("5")}, {Decimal("100.01"): Decimal("5")})
    
    # Add segment at base+15000: QI=6
    calc.update_from_book(base + 15000, Decimal("100.00"), Decimal("100.01"),
                          {Decimal("100.00"): Decimal("8")}, {Decimal("100.01"): Decimal("2")})

    # At base+20000, window is [base+10000, base+20000]
    # Segment [base+5000, base+15000) with QI=0 overlaps [base+10000, base+15000) = 5000ms
    # Segment [base+15000, base+20000) with QI=6 covers 5000ms
    # TW mean = (0*5000 + 6*5000) / 10000 = 3
    tw = calc.get_time_weighted_mean(base + 20_000)
    assert tw is not None
    assert tw == Decimal(3)


def test_time_weighted_mean_empty_window():
    """Test that empty window returns None."""
    config = qi.QueueImbalanceConfig(
        k_levels=3,
        tick_size=Decimal("0.01"),
        half_life_ticks=Decimal("0.5"),
        window_ms=10_000,
    )
    calc = qi.QueueImbalanceCalculator(config)

    base = 1_700_000_000_000
    # No updates yet
    tw = calc.get_time_weighted_mean(base + 10_000)
    assert tw is None


def test_time_weighted_mean_partial_coverage():
    """Test TW mean when window only partially covers segments."""
    config = qi.QueueImbalanceConfig(
        k_levels=3,
        tick_size=Decimal("0.01"),
        half_life_ticks=Decimal("0.5"),
        window_ms=5_000,
    )
    calc = qi.QueueImbalanceCalculator(config)

    base = 1_700_000_000_000
    # Segment: QI=10 from [base, base+10000)
    calc.update_from_book(base, Decimal("100.00"), Decimal("100.01"),
                          {Decimal("100.00"): Decimal("10")}, {Decimal("100.01"): Decimal("0")})

    # At base+7500, window is [base+2500, base+7500]
    # Segment covers [base, base+10000), window overlap = [base+2500, base+7500] = 5000ms
    tw = calc.get_time_weighted_mean(base + 7_500)
    # TW mean = 10*5000 / 5000 = 10
    assert tw is not None
    assert tw == Decimal(10)


def test_calculator_state_save_restore():
    """Test that state can be saved and restored correctly."""
    config = qi.QueueImbalanceConfig(
        k_levels=3,
        tick_size=Decimal("0.01"),
        half_life_ticks=Decimal("0.5"),
        window_ms=10_000,
    )
    calc1 = qi.QueueImbalanceCalculator(config)

    base = 1_700_000_000_000
    calc1.update_from_book(base, Decimal("100.00"), Decimal("100.01"),
                           {Decimal("100.00"): Decimal("10")}, {Decimal("100.01"): Decimal("0")})
    calc1.update_from_book(base + 5000, Decimal("100.00"), Decimal("100.01"),
                           {Decimal("100.00"): Decimal("5")}, {Decimal("100.01"): Decimal("5")})

    state = calc1.get_state()
    
    # Create new calculator and restore
    calc2 = qi.QueueImbalanceCalculator(config)
    calc2.restore_from_state(state)

    # Verify restored state produces same TW mean
    tw1 = calc1.get_time_weighted_mean(base + 10_000)
    tw2 = calc2.get_time_weighted_mean(base + 10_000)
    assert tw1 == tw2


def test_calculator_config_validation():
    """Test that invalid config raises ValueError when creating calculator."""
    invalid_config = qi.QueueImbalanceConfig(
        k_levels=3,
        tick_size=Decimal("0.01"),
        half_life_ticks=Decimal("0.5"),
        window_ms=0,  # Invalid: must be positive
    )
    with pytest.raises(ValueError):
        qi.QueueImbalanceCalculator(invalid_config)
