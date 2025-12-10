"""
Tests for Aggressive Volume Concentration Index (AVCI) functionality.

This module tests the AvciCalculator against the specification in AVCI.md.
Tests cover:
- Edge cases (empty window, single taker, equal volumes)
- Non-trivial concentration calculations
- Sliding window mechanics (insert, evict, incremental updates)
- Side-conditional variants (buy-only, sell-only, combined)
- State save/restore
"""

import pytest
from typing import NamedTuple
from decimal import Decimal


# Skip all tests in this module until the implementation exists
avci = pytest.importorskip("statbot_common.avci")


class MockFill(NamedTuple):
    """Mock L3 fill object for testing."""
    timestamp: int
    taker_order_id: str
    side: int  # +1 = buy, -1 = sell
    qty: float
    maker_order_id: str = "maker_unused"


# Base timestamp for all tests (13-digit milliseconds, recognized by normalize_timestamp_to_ms)
BASE_TS = 1_700_000_000_000


# =============================================================================
# 1. Edge Case Tests
# =============================================================================

class TestEdgeCases:
    """Test edge cases for AVCI calculations."""

    def test_empty_window_returns_none(self):
        """Test that empty window returns None for all metrics.
        
        No fills in window should return None for AVCI and related metrics.
        """
        config = avci.AvciConfig(window_ms=10000)
        calc = avci.AvciCalculator(config)
        
        # No fills added - should return None
        metrics = calc.get_metrics()
        
        assert metrics['combined']['avci'] is None
        assert metrics['combined']['avci_excess'] is None
        assert metrics['combined']['N'] == 0
        assert metrics['combined']['V'] == 0

    def test_single_fill_single_taker(self):
        """Test AVCI with one taker, one fill.
        
        Manual calculation:
            Fill: taker=A, qty=100, side=+1
            v_A = 100, V = 100, Σ_2 = 100² = 10000, N = 1
            AVCI = 10000 / 100² = 1.0
            AVCI_excess = 1 * 1.0 - 1 = 0.0
        """
        config = avci.AvciConfig(window_ms=10000)
        calc = avci.AvciCalculator(config)
        
        fill = MockFill(timestamp=BASE_TS + 1000, taker_order_id="A", side=1, qty=100)
        calc.add_fill(fill)
        
        metrics = calc.get_metrics()
        combined = metrics['combined']
        
        assert combined['N'] == 1
        assert combined['V'] == pytest.approx(100.0)
        assert combined['avci'] == pytest.approx(1.0)
        assert combined['avci_excess'] == pytest.approx(0.0)

    def test_single_taker_multiple_fills(self):
        """Test AVCI with one taker with multiple fills.
        
        Manual calculation:
            Fills: taker=A, qty=50; taker=A, qty=30; taker=A, qty=20
            v_A = 50 + 30 + 20 = 100, V = 100, Σ_2 = 100² = 10000, N = 1
            AVCI = 10000 / 10000 = 1.0
        
        One taker with multiple fills → AVCI = 1 (max concentration).
        """
        config = avci.AvciConfig(window_ms=10000)
        calc = avci.AvciCalculator(config)
        
        calc.add_fill(MockFill(timestamp=BASE_TS + 1000, taker_order_id="A", side=1, qty=50))
        calc.add_fill(MockFill(timestamp=BASE_TS + 1100, taker_order_id="A", side=1, qty=30))
        calc.add_fill(MockFill(timestamp=BASE_TS + 1200, taker_order_id="A", side=1, qty=20))
        
        metrics = calc.get_metrics()
        combined = metrics['combined']
        
        # v_A = 50 + 30 + 20 = 100
        assert combined['N'] == 1
        assert combined['V'] == pytest.approx(100.0)
        # Σ_2 = 100² = 10000, AVCI = 10000 / 10000 = 1.0
        assert combined['avci'] == pytest.approx(1.0)

    def test_two_takers_equal_volume(self):
        """Test AVCI with two takers having equal volume.
        
        Manual calculation:
            Fills: taker=A, qty=50; taker=B, qty=50
            v_A = 50, v_B = 50, V = 100
            Σ_2 = 50² + 50² = 2500 + 2500 = 5000
            AVCI = 5000 / 10000 = 0.5
            AVCI_excess = 2 * 0.5 - 1 = 0.0
        
        Two takers with equal volume → AVCI = 1/N = 0.5.
        """
        config = avci.AvciConfig(window_ms=10000)
        calc = avci.AvciCalculator(config)
        
        calc.add_fill(MockFill(timestamp=BASE_TS + 1000, taker_order_id="A", side=1, qty=50))
        calc.add_fill(MockFill(timestamp=BASE_TS + 1100, taker_order_id="B", side=1, qty=50))
        
        metrics = calc.get_metrics()
        combined = metrics['combined']
        
        assert combined['N'] == 2
        assert combined['V'] == pytest.approx(100.0)
        # Σ_2 = 50² + 50² = 5000, V² = 10000, AVCI = 0.5
        assert combined['avci'] == pytest.approx(0.5)
        # AVCI_excess = 2 * 0.5 - 1 = 0.0
        assert combined['avci_excess'] == pytest.approx(0.0)

    def test_three_takers_equal_volume(self):
        """Test AVCI with three takers having equal volume.
        
        Manual calculation:
            Fills: taker=A, qty=30; taker=B, qty=30; taker=C, qty=30
            v_A = v_B = v_C = 30, V = 90
            Σ_2 = 30² + 30² + 30² = 900 + 900 + 900 = 2700
            V² = 90² = 8100
            AVCI = 2700 / 8100 = 1/3 ≈ 0.333333
            AVCI_excess = 3 * (1/3) - 1 = 0.0
        
        Three takers with equal volume → AVCI = 1/3.
        """
        config = avci.AvciConfig(window_ms=10000)
        calc = avci.AvciCalculator(config)
        
        calc.add_fill(MockFill(timestamp=BASE_TS + 1000, taker_order_id="A", side=1, qty=30))
        calc.add_fill(MockFill(timestamp=BASE_TS + 1100, taker_order_id="B", side=1, qty=30))
        calc.add_fill(MockFill(timestamp=BASE_TS + 1200, taker_order_id="C", side=1, qty=30))
        
        metrics = calc.get_metrics()
        combined = metrics['combined']
        
        assert combined['N'] == 3
        assert combined['V'] == pytest.approx(90.0)
        # Σ_2 = 2700, V² = 8100, AVCI = 2700/8100 = 1/3
        assert combined['avci'] == pytest.approx(1.0 / 3.0)
        # AVCI_excess = 3 * (1/3) - 1 = 0.0
        assert combined['avci_excess'] == pytest.approx(0.0)


# =============================================================================
# 2. Non-Trivial Concentration Tests
# =============================================================================

class TestNonTrivialConcentration:
    """Test non-trivial concentration calculations."""

    def test_two_takers_unequal_volume(self):
        """Test AVCI with two takers having unequal volume.
        
        Manual calculation:
            Fills: taker=A, qty=80; taker=B, qty=20
            v_A = 80, v_B = 20, V = 100
            Σ_2 = 80² + 20² = 6400 + 400 = 6800
            V² = 100² = 10000
            AVCI = 6800 / 10000 = 0.68
            AVCI_excess = 2 * 0.68 - 1 = 0.36
        """
        config = avci.AvciConfig(window_ms=10000)
        calc = avci.AvciCalculator(config)
        
        calc.add_fill(MockFill(timestamp=BASE_TS + 1000, taker_order_id="A", side=1, qty=80))
        calc.add_fill(MockFill(timestamp=BASE_TS + 1100, taker_order_id="B", side=1, qty=20))
        
        metrics = calc.get_metrics()
        combined = metrics['combined']
        
        assert combined['N'] == 2
        assert combined['V'] == pytest.approx(100.0)
        # Σ_2 = 6400 + 400 = 6800, AVCI = 6800/10000 = 0.68
        assert combined['avci'] == pytest.approx(0.68)
        # AVCI_excess = 2 * 0.68 - 1 = 0.36
        assert combined['avci_excess'] == pytest.approx(0.36)

    def test_three_takers_varying_volumes(self):
        """Test AVCI with three takers having varying volumes.
        
        Manual calculation:
            Fills: taker=A, qty=60; taker=B, qty=30; taker=C, qty=10
            v_A = 60, v_B = 30, v_C = 10, V = 100
            Σ_2 = 60² + 30² + 10² = 3600 + 900 + 100 = 4600
            V² = 100² = 10000
            AVCI = 4600 / 10000 = 0.46
            AVCI_excess = 3 * 0.46 - 1 = 0.38
        """
        config = avci.AvciConfig(window_ms=10000)
        calc = avci.AvciCalculator(config)
        
        calc.add_fill(MockFill(timestamp=BASE_TS + 1000, taker_order_id="A", side=1, qty=60))
        calc.add_fill(MockFill(timestamp=BASE_TS + 1100, taker_order_id="B", side=1, qty=30))
        calc.add_fill(MockFill(timestamp=BASE_TS + 1200, taker_order_id="C", side=1, qty=10))
        
        metrics = calc.get_metrics()
        combined = metrics['combined']
        
        assert combined['N'] == 3
        assert combined['V'] == pytest.approx(100.0)
        # Σ_2 = 3600 + 900 + 100 = 4600, AVCI = 4600/10000 = 0.46
        assert combined['avci'] == pytest.approx(0.46)
        # AVCI_excess = 3 * 0.46 - 1 = 0.38
        assert combined['avci_excess'] == pytest.approx(0.38)

    def test_multiple_fills_same_taker_accumulated(self):
        """Test AVCI with multiple fills per taker (accumulation).
        
        Manual calculation:
            Fills: A:40, A:20, B:25, B:15 (two takers, multiple fills each)
            v_A = 40 + 20 = 60, v_B = 25 + 15 = 40, V = 100
            Σ_2 = 60² + 40² = 3600 + 1600 = 5200
            V² = 100² = 10000
            AVCI = 5200 / 10000 = 0.52
            AVCI_excess = 2 * 0.52 - 1 = 0.04
        """
        config = avci.AvciConfig(window_ms=10000)
        calc = avci.AvciCalculator(config)
        
        # Interleaved fills from two takers
        calc.add_fill(MockFill(timestamp=BASE_TS + 1000, taker_order_id="A", side=1, qty=40))
        calc.add_fill(MockFill(timestamp=BASE_TS + 1100, taker_order_id="B", side=1, qty=25))
        calc.add_fill(MockFill(timestamp=BASE_TS + 1200, taker_order_id="A", side=1, qty=20))
        calc.add_fill(MockFill(timestamp=BASE_TS + 1300, taker_order_id="B", side=1, qty=15))
        
        metrics = calc.get_metrics()
        combined = metrics['combined']
        
        assert combined['N'] == 2
        # v_A = 40 + 20 = 60, v_B = 25 + 15 = 40, V = 100
        assert combined['V'] == pytest.approx(100.0)
        # Σ_2 = 60² + 40² = 3600 + 1600 = 5200, AVCI = 5200/10000 = 0.52
        assert combined['avci'] == pytest.approx(0.52)
        # AVCI_excess = 2 * 0.52 - 1 = 0.04
        assert combined['avci_excess'] == pytest.approx(0.04)


# =============================================================================
# 3. Sliding Window Tests
# =============================================================================

class TestSlidingWindow:
    """Test sliding window eviction mechanics."""

    def test_window_eviction_removes_taker(self):
        """Test that window eviction completely removes a taker.
        
        Manual calculation:
            t=BASE+1000: taker=A, qty=50
            t=BASE+2000: taker=B, qty=50
            
            Before eviction (both in window):
                v_A=50, v_B=50, V=100
                Σ_2 = 50² + 50² = 5000
                AVCI = 5000 / 10000 = 0.5
            
            t=BASE+12000: evict to BASE+12000 (window=10000ms, cutoff=BASE+2000)
            After eviction (only B remains, A's fill at t=BASE+1000 < cutoff=BASE+2000):
                v_B=50, V=50
                Σ_2 = 50² = 2500
                AVCI = 2500 / 2500 = 1.0
        """
        config = avci.AvciConfig(window_ms=10000)
        calc = avci.AvciCalculator(config)
        
        calc.add_fill(MockFill(timestamp=BASE_TS + 1000, taker_order_id="A", side=1, qty=50))
        calc.add_fill(MockFill(timestamp=BASE_TS + 2000, taker_order_id="B", side=1, qty=50))
        
        # Before eviction
        metrics = calc.get_metrics()
        assert metrics['combined']['N'] == 2
        assert metrics['combined']['avci'] == pytest.approx(0.5)
        
        # Evict to t=BASE+12000, cutoff = BASE+12000 - 10000 = BASE+2000
        # Fill at t=BASE+1000 < BASE+2000, so A is evicted
        calc.evict_to(BASE_TS + 12000)
        
        metrics = calc.get_metrics()
        combined = metrics['combined']
        
        # Only B remains
        assert combined['N'] == 1
        assert combined['V'] == pytest.approx(50.0)
        # Σ_2 = 2500, V² = 2500, AVCI = 1.0
        assert combined['avci'] == pytest.approx(1.0)

    def test_window_eviction_partial_taker(self):
        """Test that window eviction partially reduces a taker's volume.
        
        Manual calculation:
            t=BASE+1000: taker=A, qty=30
            t=BASE+2000: taker=A, qty=30
            t=BASE+3000: taker=B, qty=40
            
            Before eviction:
                v_A = 30 + 30 = 60, v_B = 40, V = 100
                Σ_2 = 60² + 40² = 3600 + 1600 = 5200
                AVCI = 5200 / 10000 = 0.52
            
            t=BASE+11500: evict to BASE+11500 (window=10000ms, cutoff=BASE+1500)
            Only t=BASE+1000 fill is evicted (BASE+1000 < BASE+1500), t=BASE+2000 and t=BASE+3000 remain.
            
            After eviction:
                v_A = 30 (only t=BASE+2000 fill), v_B = 40, V = 70
                Σ_2 = 30² + 40² = 900 + 1600 = 2500
                V² = 70² = 4900
                AVCI = 2500 / 4900 ≈ 0.5102
        """
        config = avci.AvciConfig(window_ms=10000)
        calc = avci.AvciCalculator(config)
        
        calc.add_fill(MockFill(timestamp=BASE_TS + 1000, taker_order_id="A", side=1, qty=30))
        calc.add_fill(MockFill(timestamp=BASE_TS + 2000, taker_order_id="A", side=1, qty=30))
        calc.add_fill(MockFill(timestamp=BASE_TS + 3000, taker_order_id="B", side=1, qty=40))
        
        # Before eviction
        metrics = calc.get_metrics()
        assert metrics['combined']['N'] == 2
        assert metrics['combined']['V'] == pytest.approx(100.0)
        assert metrics['combined']['avci'] == pytest.approx(0.52)
        
        # Evict to t=BASE+11500, cutoff = BASE+11500 - 10000 = BASE+1500
        # Fill at t=BASE+1000 < BASE+1500, so that fill is evicted
        calc.evict_to(BASE_TS + 11500)
        
        metrics = calc.get_metrics()
        combined = metrics['combined']
        
        # A still exists but reduced, B unchanged
        assert combined['N'] == 2
        # v_A = 30, v_B = 40, V = 70
        assert combined['V'] == pytest.approx(70.0)
        # Σ_2 = 900 + 1600 = 2500, V² = 4900, AVCI = 2500/4900 ≈ 0.5102
        assert combined['avci'] == pytest.approx(2500.0 / 4900.0, rel=1e-4)

    def test_insert_evict_incremental_update(self):
        """Test that incremental O(1) updates are correct.
        
        Manual calculation:
            Initial state: taker=A, qty=50
                v_A = 50, V = 50, Σ_2 = 50² = 2500, N = 1
                AVCI = 2500 / 2500 = 1.0
            
            Insert: taker=A, qty=30
                Old x = 50, new x' = 50 + 30 = 80
                V' = 50 + 30 = 80
                Σ_2' = Σ_2 - x² + x'² = 2500 - 50² + 80² = 2500 - 2500 + 6400 = 6400
                AVCI = 6400 / 6400 = 1.0
        """
        config = avci.AvciConfig(window_ms=10000)
        calc = avci.AvciCalculator(config)
        
        # Initial state
        calc.add_fill(MockFill(timestamp=BASE_TS + 1000, taker_order_id="A", side=1, qty=50))
        
        metrics = calc.get_metrics()
        assert metrics['combined']['V'] == pytest.approx(50.0)
        assert metrics['combined']['avci'] == pytest.approx(1.0)
        
        # Add another fill from same taker
        calc.add_fill(MockFill(timestamp=BASE_TS + 1100, taker_order_id="A", side=1, qty=30))
        
        metrics = calc.get_metrics()
        combined = metrics['combined']
        
        # v_A = 80, V = 80, Σ_2 = 6400, AVCI = 6400/6400 = 1.0
        assert combined['N'] == 1
        assert combined['V'] == pytest.approx(80.0)
        assert combined['avci'] == pytest.approx(1.0)


# =============================================================================
# 4. Side-Conditional Variant Tests
# =============================================================================

class TestSideConditionalVariants:
    """Test side-conditional AVCI calculations (buy-only, sell-only)."""

    def test_buy_only_variant(self):
        """Test AVCI for buy-only fills.
        
        Manual calculation:
            Fills: 
                taker=A, qty=60, side=+1 (buy)
                taker=B, qty=40, side=-1 (sell)
            
            Combined: v_A=60, v_B=40, V=100
                Σ_2 = 60² + 40² = 3600 + 1600 = 5200
                AVCI = 5200 / 10000 = 0.52
            
            Buy only: only A's fill, v_A=60, V=60
                Σ_2 = 60² = 3600
                AVCI = 3600 / 3600 = 1.0
            
            Sell only: only B's fill, v_B=40, V=40
                Σ_2 = 40² = 1600
                AVCI = 1600 / 1600 = 1.0
        """
        config = avci.AvciConfig(window_ms=10000)
        calc = avci.AvciCalculator(config)
        
        calc.add_fill(MockFill(timestamp=BASE_TS + 1000, taker_order_id="A", side=1, qty=60))
        calc.add_fill(MockFill(timestamp=BASE_TS + 1100, taker_order_id="B", side=-1, qty=40))
        
        metrics = calc.get_metrics()
        
        # Combined: AVCI = 0.52
        assert metrics['combined']['N'] == 2
        assert metrics['combined']['V'] == pytest.approx(100.0)
        assert metrics['combined']['avci'] == pytest.approx(0.52)
        
        # Buy only: single taker A, AVCI = 1.0
        assert metrics['buy']['N'] == 1
        assert metrics['buy']['V'] == pytest.approx(60.0)
        assert metrics['buy']['avci'] == pytest.approx(1.0)
        
        # Sell only: single taker B, AVCI = 1.0
        assert metrics['sell']['N'] == 1
        assert metrics['sell']['V'] == pytest.approx(40.0)
        assert metrics['sell']['avci'] == pytest.approx(1.0)

    def test_mixed_sides_multiple_takers(self):
        """Test AVCI with mixed sides and multiple takers.
        
        Manual calculation:
            Fills:
                taker=A, qty=30, side=+1
                taker=B, qty=20, side=+1
                taker=C, qty=25, side=-1
                taker=D, qty=25, side=-1
            
            Combined: V = 30 + 20 + 25 + 25 = 100
                Σ_2 = 30² + 20² + 25² + 25² = 900 + 400 + 625 + 625 = 2550
                AVCI = 2550 / 10000 = 0.255
            
            Buy only: v_A=30, v_B=20, V=50
                Σ_2 = 30² + 20² = 900 + 400 = 1300
                AVCI = 1300 / 2500 = 0.52
            
            Sell only: v_C=25, v_D=25, V=50
                Σ_2 = 25² + 25² = 625 + 625 = 1250
                AVCI = 1250 / 2500 = 0.5
        """
        config = avci.AvciConfig(window_ms=10000)
        calc = avci.AvciCalculator(config)
        
        calc.add_fill(MockFill(timestamp=BASE_TS + 1000, taker_order_id="A", side=1, qty=30))
        calc.add_fill(MockFill(timestamp=BASE_TS + 1100, taker_order_id="B", side=1, qty=20))
        calc.add_fill(MockFill(timestamp=BASE_TS + 1200, taker_order_id="C", side=-1, qty=25))
        calc.add_fill(MockFill(timestamp=BASE_TS + 1300, taker_order_id="D", side=-1, qty=25))
        
        metrics = calc.get_metrics()
        
        # Combined: Σ_2 = 2550, V² = 10000, AVCI = 0.255
        assert metrics['combined']['N'] == 4
        assert metrics['combined']['V'] == pytest.approx(100.0)
        assert metrics['combined']['avci'] == pytest.approx(0.255)
        
        # Buy: Σ_2 = 1300, V² = 2500, AVCI = 0.52
        assert metrics['buy']['N'] == 2
        assert metrics['buy']['V'] == pytest.approx(50.0)
        assert metrics['buy']['avci'] == pytest.approx(0.52)
        
        # Sell: Σ_2 = 1250, V² = 2500, AVCI = 0.5
        assert metrics['sell']['N'] == 2
        assert metrics['sell']['V'] == pytest.approx(50.0)
        assert metrics['sell']['avci'] == pytest.approx(0.5)

    def test_no_sells_returns_none_for_sell(self):
        """Test that sell-only metrics return None when no sells exist."""
        config = avci.AvciConfig(window_ms=10000)
        calc = avci.AvciCalculator(config)
        
        # Only buy fills
        calc.add_fill(MockFill(timestamp=BASE_TS + 1000, taker_order_id="A", side=1, qty=50))
        calc.add_fill(MockFill(timestamp=BASE_TS + 1100, taker_order_id="B", side=1, qty=50))
        
        metrics = calc.get_metrics()
        
        # Buy should have valid metrics
        assert metrics['buy']['avci'] is not None
        
        # Sell should have None metrics (no sells)
        assert metrics['sell']['avci'] is None
        assert metrics['sell']['N'] == 0
        assert metrics['sell']['V'] == 0


# =============================================================================
# 5. State Management Tests
# =============================================================================

class TestStateManagement:
    """Test state save/restore and configuration validation."""

    def test_state_save_restore(self):
        """Test that state can be saved and restored correctly."""
        config = avci.AvciConfig(window_ms=10000)
        calc1 = avci.AvciCalculator(config)
        
        # Add some fills
        calc1.add_fill(MockFill(timestamp=BASE_TS + 1000, taker_order_id="A", side=1, qty=60))
        calc1.add_fill(MockFill(timestamp=BASE_TS + 1100, taker_order_id="B", side=-1, qty=40))
        
        # Save state
        state = calc1.get_state()
        
        # Create new calculator and restore
        calc2 = avci.AvciCalculator(config)
        calc2.restore_from_state(state)
        
        # Verify restored state produces same metrics
        metrics1 = calc1.get_metrics()
        metrics2 = calc2.get_metrics()
        
        assert metrics1['combined']['avci'] == metrics2['combined']['avci']
        assert metrics1['combined']['N'] == metrics2['combined']['N']
        assert metrics1['combined']['V'] == metrics2['combined']['V']
        assert metrics1['buy']['avci'] == metrics2['buy']['avci']
        assert metrics1['sell']['avci'] == metrics2['sell']['avci']

    def test_config_validation_zero_window(self):
        """Test that zero window_ms raises ValueError."""
        with pytest.raises(ValueError):
            config = avci.AvciConfig(window_ms=0)
            avci.AvciCalculator(config)

    def test_config_validation_negative_window(self):
        """Test that negative window_ms raises ValueError."""
        with pytest.raises(ValueError):
            config = avci.AvciConfig(window_ms=-1000)
            avci.AvciCalculator(config)


# =============================================================================
# 6. Complex Integration Test
# =============================================================================

class TestIntegration:
    """Test realistic feed sequences with interleaved operations."""

    def test_realistic_feed_sequence(self):
        """Test realistic order flow with interleaved inserts and evictions.
        
        Manual calculation:
            W = 5000ms (window width)
            
            t=BASE+1000: A buys 100
                v_A=100, V=100, N=1, AVCI=1.0
            
            t=BASE+2000: B sells 50
                v_A=100, v_B=50, V=150
                Σ_2 = 100² + 50² = 10000 + 2500 = 12500
                AVCI = 12500 / 22500 ≈ 0.5556
            
            t=BASE+3000: A buys 50 (A total = 150)
                v_A=150, v_B=50, V=200
                Σ_2 = 150² + 50² = 22500 + 2500 = 25000
                AVCI = 25000 / 40000 = 0.625
            
            t=BASE+4000: C buys 30
                v_A=150, v_B=50, v_C=30, V=230
                Σ_2 = 150² + 50² + 30² = 22500 + 2500 + 900 = 25900
                AVCI = 25900 / 52900 ≈ 0.4896
            
            t=BASE+6500: evict to BASE+6500 (cutoff = BASE+6500 - 5000 = BASE+1500)
                Fill at t=BASE+1000 evicted (A's first fill of 100)
                v_A = 50 (only t=BASE+3000 fill), v_B=50, v_C=30, V=130
                Σ_2 = 50² + 50² + 30² = 2500 + 2500 + 900 = 5900
                V² = 130² = 16900
                AVCI = 5900 / 16900 ≈ 0.3491
        """
        config = avci.AvciConfig(window_ms=5000)
        calc = avci.AvciCalculator(config)
        
        # t=BASE+1000: A buys 100
        calc.add_fill(MockFill(timestamp=BASE_TS + 1000, taker_order_id="A", side=1, qty=100))
        metrics = calc.get_metrics()
        assert metrics['combined']['N'] == 1
        assert metrics['combined']['avci'] == pytest.approx(1.0)
        
        # t=BASE+2000: B sells 50
        calc.add_fill(MockFill(timestamp=BASE_TS + 2000, taker_order_id="B", side=-1, qty=50))
        metrics = calc.get_metrics()
        assert metrics['combined']['N'] == 2
        # Σ_2 = 12500, V² = 22500, AVCI ≈ 0.5556
        assert metrics['combined']['avci'] == pytest.approx(12500.0 / 22500.0, rel=1e-4)
        
        # t=BASE+3000: A buys 50 (A total = 150)
        calc.add_fill(MockFill(timestamp=BASE_TS + 3000, taker_order_id="A", side=1, qty=50))
        metrics = calc.get_metrics()
        assert metrics['combined']['N'] == 2
        # Σ_2 = 25000, V² = 40000, AVCI = 0.625
        assert metrics['combined']['avci'] == pytest.approx(0.625)
        
        # t=BASE+4000: C buys 30
        calc.add_fill(MockFill(timestamp=BASE_TS + 4000, taker_order_id="C", side=1, qty=30))
        metrics = calc.get_metrics()
        assert metrics['combined']['N'] == 3
        # Σ_2 = 25900, V² = 52900, AVCI ≈ 0.4896
        assert metrics['combined']['avci'] == pytest.approx(25900.0 / 52900.0, rel=1e-4)
        
        # t=BASE+6500: evict (cutoff = BASE+1500)
        calc.evict_to(BASE_TS + 6500)
        metrics = calc.get_metrics()
        
        # A's first fill evicted, v_A=50, v_B=50, v_C=30, V=130
        assert metrics['combined']['N'] == 3
        assert metrics['combined']['V'] == pytest.approx(130.0)
        # Σ_2 = 5900, V² = 16900, AVCI ≈ 0.3491
        assert metrics['combined']['avci'] == pytest.approx(5900.0 / 16900.0, rel=1e-4)

    def test_complete_eviction_to_empty(self):
        """Test that evicting all fills results in empty window (None metrics)."""
        config = avci.AvciConfig(window_ms=5000)
        calc = avci.AvciCalculator(config)
        
        calc.add_fill(MockFill(timestamp=BASE_TS + 1000, taker_order_id="A", side=1, qty=50))
        calc.add_fill(MockFill(timestamp=BASE_TS + 2000, taker_order_id="B", side=1, qty=50))
        
        # Verify non-empty
        metrics = calc.get_metrics()
        assert metrics['combined']['avci'] is not None
        
        # Evict all (cutoff = BASE+10000 - 5000 = BASE+5000, all fills < BASE+5000)
        calc.evict_to(BASE_TS + 10000)
        
        metrics = calc.get_metrics()
        assert metrics['combined']['avci'] is None
        assert metrics['combined']['N'] == 0
        assert metrics['combined']['V'] == 0
