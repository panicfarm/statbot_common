"""
Tests for markout skew functionality.

This module tests the MarkoutSkewCalculator and related utilities against
the specification in markout.md. Tests cover:
- L3 trade coalescing by timestamp and side (§2)
- Cross-stream tie-break ordering (§3) 
- Completion-time sliding windows (§4)
- Side-conditional means and skew calculation (§5)
- Clock-time and event-time horizons (§1, §6)
- Edge cases and NaN handling (§7)
"""

import pytest
import math
from typing import NamedTuple, List
from unittest.mock import patch
from statbot_common import (
    MarkoutSkewCalculator, 
    MarkoutObservation, 
    MarkoutConfig,
    coalesce_l3_trades_by_timestamp,
    compute_mid_price,
    validate_l2_consistency
)


class MockL3Trade(NamedTuple):
    """Mock L3 trade for testing."""
    timestamp: int
    quantity: float
    price: float
    aggressor_sign: int  # +1 = buy, -1 = sell
    side: str = None  # Optional for Trade protocol compatibility


class TestUtilityFunctions:
    """Test utility functions for markout skew calculations."""
    
    def test_compute_mid_price(self):
        """Test mid-price calculation."""
        assert compute_mid_price(100.0, 102.0) == 101.0
        assert compute_mid_price(99.5, 100.5) == 100.0
        assert compute_mid_price(0.0, 10.0) == 5.0
    
    def test_coalesce_l3_trades_by_timestamp(self):
        """Test L3 trade coalescing by timestamp."""
        trades = [
            MockL3Trade(timestamp=1000, quantity=100, price=101.0, aggressor_sign=1),
            MockL3Trade(timestamp=1000, quantity=50, price=101.0, aggressor_sign=-1),  # Same timestamp
            MockL3Trade(timestamp=2000, quantity=200, price=102.0, aggressor_sign=1),
            MockL3Trade(timestamp=1000, quantity=25, price=101.0, aggressor_sign=1),   # Same timestamp as first
        ]
        
        coalesced = coalesce_l3_trades_by_timestamp(trades)
        
        assert len(coalesced) == 2  # Two unique timestamps
        # Timestamps get normalized to milliseconds (1000 seconds -> 1000000 ms)
        assert len(coalesced[1000000]) == 3  # Three trades at t=1000 (normalized to 1000000)
        assert len(coalesced[2000000]) == 1  # One trade at t=2000 (normalized to 2000000)
        
        # Check correct grouping
        t1000_trades = coalesced[1000000]  # Use normalized timestamp
        buy_trades_t1000 = [t for t in t1000_trades if t.aggressor_sign == 1]
        sell_trades_t1000 = [t for t in t1000_trades if t.aggressor_sign == -1]
        
        assert len(buy_trades_t1000) == 2  # Two buy trades at t=1000
        assert len(sell_trades_t1000) == 1  # One sell trade at t=1000
    
    @patch('statbot_common.markout_skew.logging')
    def test_validate_l2_consistency_warning(self, mock_logging):
        """Test L2 consistency validation and warning."""
        # Should warn when coalesced L3 trades but L2 updates != 1
        result = validate_l2_consistency(1000, l3_trades_count=2, l2_updates_count=0)
        assert result is False
        mock_logging.warning.assert_called_once()
        
        mock_logging.reset_mock()
        
        result = validate_l2_consistency(1000, l3_trades_count=2, l2_updates_count=2)
        assert result is False
        mock_logging.warning.assert_called_once()
        
        # Should not warn when consistent
        mock_logging.reset_mock()
        result = validate_l2_consistency(1000, l3_trades_count=2, l2_updates_count=1)
        assert result is True
        mock_logging.warning.assert_not_called()
        
        # Should not warn when no L3 trades
        result = validate_l2_consistency(1000, l3_trades_count=0, l2_updates_count=5)
        assert result is True
        mock_logging.warning.assert_not_called()


class TestMarkoutConfig:
    """Test markout configuration validation."""
    
    def test_valid_clock_config(self):
        """Test valid clock-time configuration."""
        config = MarkoutConfig(
            horizon_type="clock",
            tau_ms=1000,
            window_ms=30000
        )
        calculator = MarkoutSkewCalculator(config)
        assert calculator.config.horizon_type == "clock"
        assert calculator.config.tau_ms == 1000
    
    def test_valid_event_config(self):
        """Test valid event-time configuration."""
        config = MarkoutConfig(
            horizon_type="event",
            k_trades=10,
            window_ms=30000
        )
        calculator = MarkoutSkewCalculator(config)
        assert calculator.config.horizon_type == "event"
        assert calculator.config.k_trades == 10
    
    def test_invalid_clock_config(self):
        """Test invalid clock-time configuration."""
        with pytest.raises(ValueError, match="Clock-time horizon requires tau_ms"):
            config = MarkoutConfig(horizon_type="clock", window_ms=30000)
            MarkoutSkewCalculator(config)
    
    def test_invalid_event_config(self):
        """Test invalid event-time configuration."""
        with pytest.raises(ValueError, match="Event-time horizon requires k_trades"):
            config = MarkoutConfig(horizon_type="event", window_ms=30000)
            MarkoutSkewCalculator(config)


class TestMarkoutSkewCalculatorClockTime:
    """Test markout skew calculator with clock-time horizons."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = MarkoutConfig(
            horizon_type="clock",
            tau_ms=1000,  # 1 second horizon
            window_ms=5000  # 5 second window
        )
        self.calculator = MarkoutSkewCalculator(self.config)
    
    def test_add_coalesced_trades_single_side(self):
        """Test adding coalesced trades with single side."""
        trades = [
            MockL3Trade(timestamp=1700000000000, quantity=100, price=101.0, aggressor_sign=1),
            MockL3Trade(timestamp=1700000000000, quantity=50, price=101.0, aggressor_sign=1),
        ]
        
        observations = self.calculator.add_coalesced_l3_trades(1700000000000, trades, pre_trade_mid=100.5)
        
        assert len(observations) == 1  # Only buy side
        obs = observations[0]
        assert obs.start_time_ms == 1700000000000
        assert obs.horizon_time_ms == 1700000001000  # 1700000000000 + tau_ms
        assert obs.side == 1
        assert obs.pre_trade_mid == 100.5
        assert obs.markout is None  # Not completed yet
    
    def test_add_coalesced_trades_both_sides(self):
        """Test adding coalesced trades with both sides."""
        trades = [
            MockL3Trade(timestamp=1700000000000, quantity=100, price=101.0, aggressor_sign=1),
            MockL3Trade(timestamp=1700000000000, quantity=75, price=101.0, aggressor_sign=-1),
            MockL3Trade(timestamp=1700000000000, quantity=25, price=101.0, aggressor_sign=1),
        ]
        
        observations = self.calculator.add_coalesced_l3_trades(1700000000000, trades, pre_trade_mid=100.8)
        
        assert len(observations) == 2  # Both buy and sell sides
        
        buy_obs = next(obs for obs in observations if obs.side == 1)
        sell_obs = next(obs for obs in observations if obs.side == -1)
        
        # Both should have same start time and pre-trade mid
        assert buy_obs.start_time_ms == sell_obs.start_time_ms == 1700000000000
        assert buy_obs.pre_trade_mid == sell_obs.pre_trade_mid == 100.8
        assert buy_obs.horizon_time_ms == sell_obs.horizon_time_ms == 1700000001000
    
    def test_complete_horizons_clock_time(self):
        """Test completing clock-time horizons."""
        # Add some trades
        trades = [
            MockL3Trade(timestamp=1000, quantity=100, price=101.0, aggressor_sign=1),
            MockL3Trade(timestamp=1000, quantity=50, price=101.0, aggressor_sign=-1),
        ]
        
        self.calculator.add_coalesced_l3_trades(1000, trades, pre_trade_mid=100.5)
        
        # Complete at horizon time
        completed = self.calculator.complete_horizons_clock_time(2000, current_mid=101.2)
        
        assert len(completed) == 2  # Both observations completed
        
        for obs in completed:
            assert obs.markout is not None
            expected_markout = 101.2 - 100.5  # current_mid - pre_trade_mid
            assert obs.markout == pytest.approx(expected_markout)
    
    def test_complete_horizons_partial(self):
        """Test completing only some horizons."""
        # Add trades at different times
        trades1 = [MockL3Trade(timestamp=1700000000000, quantity=100, price=101.0, aggressor_sign=1)]
        trades2 = [MockL3Trade(timestamp=1700000002000, quantity=100, price=102.0, aggressor_sign=1)]
        
        self.calculator.add_coalesced_l3_trades(1700000000000, trades1, pre_trade_mid=100.5)
        self.calculator.add_coalesced_l3_trades(1700000002000, trades2, pre_trade_mid=101.5)
        
        # Complete only first horizon (horizon at 1700000001000)
        completed = self.calculator.complete_horizons_clock_time(1700000001500, current_mid=102.0)
        
        assert len(completed) == 1  # Only first observation completed
        assert len(self.calculator.pending_observations) == 1  # One still pending
    
    def test_markout_skew_calculation_basic(self):
        """Test basic markout skew calculation."""
        # Use proper 13-digit millisecond timestamps
        # Add buy-aggressor trade that should have positive markout
        buy_trades = [MockL3Trade(timestamp=1700000000000, quantity=100, price=101.0, aggressor_sign=1)]
        self.calculator.add_coalesced_l3_trades(1700000000000, buy_trades, pre_trade_mid=100.5)
        
        # Add sell-aggressor trade that should have negative markout (closer in time)
        sell_trades = [MockL3Trade(timestamp=1700000001500, quantity=100, price=100.0, aggressor_sign=-1)]
        self.calculator.add_coalesced_l3_trades(1700000001500, sell_trades, pre_trade_mid=100.8)
        
        # Complete both horizons (horizons are at t+1000ms)
        self.calculator.complete_horizons_clock_time(1700000001000, current_mid=101.0)  # Complete first
        self.calculator.complete_horizons_clock_time(1700000002500, current_mid=100.5)  # Complete second
        
        # Calculate skew (both should be in 5-second window)
        skew_data = self.calculator.get_markout_skew(1700000003000)
        
        assert skew_data['n_buys'] == 1
        assert skew_data['n_sells'] == 1
        assert skew_data['mplus'] == pytest.approx(101.0 - 100.5)  # Buy markout
        assert skew_data['mminus'] == pytest.approx(100.5 - 100.8)  # Sell markout
        assert skew_data['skew'] == pytest.approx(skew_data['mplus'] - skew_data['mminus'])
    
    def test_markout_skew_zero_counts(self):
        """Test markout skew with zero counts (NaN handling)."""
        skew_data = self.calculator.get_markout_skew(1000)
        
        assert skew_data['n_buys'] == 0
        assert skew_data['n_sells'] == 0
        assert skew_data['mplus'] is None
        assert skew_data['mminus'] is None
        assert skew_data['skew'] is None
    
    def test_markout_skew_single_side(self):
        """Test markout skew with only one side."""
        # Add only buy trades (use proper millisecond timestamps)
        buy_trades = [MockL3Trade(timestamp=1700000000000, quantity=100, price=101.0, aggressor_sign=1)]
        self.calculator.add_coalesced_l3_trades(1700000000000, buy_trades, pre_trade_mid=100.5)
        
        # Complete horizon (horizon is at t+1000ms)
        self.calculator.complete_horizons_clock_time(1700000001000, current_mid=101.2)
        
        skew_data = self.calculator.get_markout_skew(1700000002000)
        
        assert skew_data['n_buys'] == 1
        assert skew_data['n_sells'] == 0
        assert skew_data['mplus'] == pytest.approx(101.2 - 100.5)
        assert skew_data['mminus'] is None
        assert skew_data['skew'] is None  # Can't compute skew with only one side
    
    def test_completion_time_window_eviction(self):
        """Test that completion-time windows properly evict old data."""
        # Add trade that will be completed and then evicted (use proper millisecond timestamps)
        trades = [MockL3Trade(timestamp=1700000000000, quantity=100, price=101.0, aggressor_sign=1)]
        self.calculator.add_coalesced_l3_trades(1700000000000, trades, pre_trade_mid=100.5)
        
        # Complete at horizon time (t+1000ms)
        self.calculator.complete_horizons_clock_time(1700000001000, current_mid=101.0)
        
        # Should be in window at t+5000ms (window_ms=5000)
        skew_data = self.calculator.get_markout_skew(1700000005000)
        assert skew_data['n_buys'] == 1
        
        # Should be evicted at t+8000ms (cutoff = 1700000008000 - 5000 = 1700000003000, completion was at 1700000001000)
        skew_data = self.calculator.get_markout_skew(1700000008000)
        assert skew_data['n_buys'] == 0


class TestMarkoutSkewCalculatorEventTime:
    """Test markout skew calculator with event-time horizons."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = MarkoutConfig(
            horizon_type="event",
            k_trades=3,  # 3-trade horizon
            window_ms=10000  # 10 second window
        )
        self.calculator = MarkoutSkewCalculator(self.config)
    
    def test_add_trades_updates_counter(self):
        """Test that adding trades updates the trade counter."""
        assert self.calculator.trade_counter == 0
        
        trades = [
            MockL3Trade(timestamp=1000, quantity=100, price=101.0, aggressor_sign=1),
            MockL3Trade(timestamp=1000, quantity=50, price=101.0, aggressor_sign=-1),
        ]
        
        self.calculator.add_coalesced_l3_trades(1000, trades, pre_trade_mid=100.5)
        assert self.calculator.trade_counter == 2
    
    def test_event_horizon_scheduling(self):
        """Test that event horizons are scheduled correctly."""
        trades = [MockL3Trade(timestamp=1000, quantity=100, price=101.0, aggressor_sign=1)]
        
        observations = self.calculator.add_coalesced_l3_trades(1000, trades, pre_trade_mid=100.5)
        
        assert len(observations) == 1
        assert observations[0].horizon_time_ms == -1  # Placeholder
        assert len(self.calculator.event_horizon_queue) == 1
        
        target_index, obs = self.calculator.event_horizon_queue[0]
        assert target_index == 3  # trade_counter (0) + k_trades (3) = 3
    
    def test_complete_event_horizons(self):
        """Test completing event-time horizons."""
        # Add initial trade (counter becomes 1)
        trades1 = [MockL3Trade(timestamp=1000, quantity=100, price=101.0, aggressor_sign=1)]
        self.calculator.add_coalesced_l3_trades(1000, trades1, pre_trade_mid=100.5)
        
        # Add more trades to reach horizon (counter becomes 4)
        trades2 = [
            MockL3Trade(timestamp=2000, quantity=50, price=102.0, aggressor_sign=-1),
            MockL3Trade(timestamp=2000, quantity=25, price=102.0, aggressor_sign=1),
            MockL3Trade(timestamp=3000, quantity=75, price=103.0, aggressor_sign=1),
        ]
        self.calculator.add_coalesced_l3_trades(2000, trades2[:2], pre_trade_mid=101.0)
        self.calculator.add_coalesced_l3_trades(3000, trades2[2:], pre_trade_mid=102.0)
        
        # Complete horizons at t=3000
        completed = self.calculator.complete_horizons_event_time(3000, current_mid=103.0)
        
        # First observation (target=3) and two from second batch (target=4) should be completed
        assert len(completed) == 3  # Three observations completed when counter reaches 4
        # Check that first observation is from the first batch
        first_obs = next(obs for obs in completed if obs.start_time_ms == 1000000)  # Normalized timestamp
        assert first_obs.horizon_time_ms == 3000  # Set to current time
        assert first_obs.markout == pytest.approx(103.0 - 100.5)
    
    def test_event_horizon_multiple_observations(self):
        """Test event horizons with multiple observations at same timestamp."""
        # Add trades with both sides (creates 2 observations)
        trades = [
            MockL3Trade(timestamp=1000, quantity=100, price=101.0, aggressor_sign=1),
            MockL3Trade(timestamp=1000, quantity=50, price=101.0, aggressor_sign=-1),
        ]
        self.calculator.add_coalesced_l3_trades(1000, trades, pre_trade_mid=100.5)
        
        # Both observations should have same target index
        assert len(self.calculator.event_horizon_queue) == 2
        target_indices = [idx for idx, _ in self.calculator.event_horizon_queue]
        assert all(idx == 3 for idx in target_indices)  # 0 + 3 = 3
        
        # Add 3 more trades to complete horizons
        for i in range(3):
            trade = [MockL3Trade(timestamp=2000 + i * 100, quantity=25, price=102.0, aggressor_sign=1)]
            self.calculator.add_coalesced_l3_trades(2000 + i * 100, trade, pre_trade_mid=101.0)
        
        # Complete horizons
        completed = self.calculator.complete_horizons_event_time(2300, current_mid=102.5)
        
        # Both initial observations (target=3) plus one from added trades should be completed
        assert len(completed) == 3  # Three observations completed


class TestMarkoutObservation:
    """Test MarkoutObservation data structure."""
    
    def test_observation_creation(self):
        """Test creating markout observations."""
        obs = MarkoutObservation(
            start_time_ms=1000,
            horizon_time_ms=2000,
            side=1,
            pre_trade_mid=100.5,
            markout=0.7
        )
        
        assert obs.start_time_ms == 1000
        assert obs.horizon_time_ms == 2000
        assert obs.side == 1
        assert obs.pre_trade_mid == 100.5
        assert obs.markout == 0.7
    
    def test_observation_replace(self):
        """Test replacing observation fields."""
        obs = MarkoutObservation(
            start_time_ms=1000,
            horizon_time_ms=2000,
            side=1,
            pre_trade_mid=100.5
        )
        
        completed_obs = obs._replace(markout=0.5)
        
        assert completed_obs.markout == 0.5
        assert completed_obs.start_time_ms == 1000  # Other fields unchanged
        assert obs.markout is None  # Original unchanged


class TestMarkoutSkewStateManagement:
    """Test state saving and restoration."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = MarkoutConfig(
            horizon_type="clock",
            tau_ms=1000,
            window_ms=5000
        )
        self.calculator = MarkoutSkewCalculator(self.config)
    
    def test_get_and_restore_state(self):
        """Test state serialization and restoration."""
        # Add some trades and complete some horizons (use proper timestamps)
        trades = [
            MockL3Trade(timestamp=1700000000000, quantity=100, price=101.0, aggressor_sign=1),
            MockL3Trade(timestamp=1700000000000, quantity=50, price=101.0, aggressor_sign=-1),
        ]
        
        self.calculator.add_coalesced_l3_trades(1700000000000, trades, pre_trade_mid=100.5)
        self.calculator.complete_horizons_clock_time(1700000001000, current_mid=101.0)
        
        # Get state
        state = self.calculator.get_state()
        
        # Create new calculator and restore state
        new_calculator = MarkoutSkewCalculator(self.config)
        new_calculator.restore_from_state(state)
        
        # Verify restoration (use time within window)
        original_skew = self.calculator.get_markout_skew(1700000002000)
        restored_skew = new_calculator.get_markout_skew(1700000002000)
        
        assert original_skew == restored_skew
    
    def test_event_time_state_management(self):
        """Test state management for event-time horizons."""
        config = MarkoutConfig(horizon_type="event", k_trades=2, window_ms=5000)
        calculator = MarkoutSkewCalculator(config)
        
        # Add trade
        trades = [MockL3Trade(timestamp=1000, quantity=100, price=101.0, aggressor_sign=1)]
        calculator.add_coalesced_l3_trades(1000, trades, pre_trade_mid=100.5)
        
        # Get and restore state
        state = calculator.get_state()
        new_calculator = MarkoutSkewCalculator(config)
        new_calculator.restore_from_state(state)
        
        # Verify event-time state restored
        assert new_calculator.trade_counter == 1
        assert len(new_calculator.event_horizon_queue) == 1
