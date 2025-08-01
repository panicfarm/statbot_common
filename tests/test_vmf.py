import unittest
import math
from typing import NamedTuple
from src.statbot_common.vmf import compute_vmf


class MockTrade(NamedTuple):
    """Mock trade object for testing."""
    timestamp: int
    quantity: float
    side: str = None


class TestVMF(unittest.TestCase):
    """Test cases for the compute_vmf function."""
    
    def test_insufficient_data(self):
        """Test VMF with insufficient data points."""
        # Test with empty list
        result = compute_vmf([])
        self.assertIsNone(result)
        
        # Test with single trade
        trades = [(1000, MockTrade(timestamp=1000, quantity=100.0))]
        result = compute_vmf(trades)
        self.assertIsNone(result)
        
        # Test with less than 2 * smoothing_period_trades (default 20, so need 40)
        trades = []
        for i in range(30):  # Less than 40
            timestamp = 1000 + i * 1000
            trades.append((timestamp, MockTrade(timestamp=timestamp, quantity=100.0)))
        
        result = compute_vmf(trades)
        self.assertIsNone(result)
    
    def test_invalid_smoothing_period(self):
        """Test VMF with invalid smoothing period."""
        trades = []
        for i in range(50):
            timestamp = 1000 + i * 1000
            trades.append((timestamp, MockTrade(timestamp=timestamp, quantity=100.0)))
        
        # Test with zero smoothing period
        result = compute_vmf(trades, smoothing_period_trades=0)
        self.assertIsNone(result)
        
        # Test with negative smoothing period
        result = compute_vmf(trades, smoothing_period_trades=-1)
        self.assertIsNone(result)
    
    def test_trade_aggregation_same_timestamp(self):
        """Test that trades with identical timestamps are aggregated."""
        trades = [
            (1000, MockTrade(timestamp=1000, quantity=100.0)),
            (1000, MockTrade(timestamp=1000, quantity=50.0)),   # Same timestamp - should aggregate
            (1000, MockTrade(timestamp=1000, quantity=25.0)),   # Same timestamp - should aggregate
        ]
        
        # Add more trades to meet minimum requirement
        for i in range(2, 50):  # Need enough for 2 * smoothing_period_trades
            timestamp = 1000 + i * 1000
            trades.append((timestamp, MockTrade(timestamp=timestamp, quantity=100.0)))
        
        # Should not raise an error and should handle aggregation
        result = compute_vmf(trades, smoothing_period_trades=3)
        self.assertIsInstance(result, float)
        self.assertFalse(math.isnan(result))
        self.assertFalse(math.isinf(result))
    
    def test_manual_vmf_calculation_non_trivial(self):
        """
        Test VMF calculation against a manual, step-by-step non-trivial case.
        
        This test verifies the entire VMF formula:
        1. Instantaneous Velocity: v_k = q_k / (t_k - t_{k-1})
        2. Smoothed Velocity: VMF_raw,k = mean of last N velocities
        3. Normalized VMF: VMF_k = (VMF_raw,k - μ) / σ
        
        With N=3, we need 6 trades total to get our first VMF value.
        """
        
        trades = [
            (1000, MockTrade(timestamp=1000, quantity=150)),  # t_0
            (2000, MockTrade(timestamp=2000, quantity=300)),  # t_1
            (4000, MockTrade(timestamp=4000, quantity=600)),  # t_2
            (5000, MockTrade(timestamp=5000, quantity=100)),  # t_3
            (6000, MockTrade(timestamp=6000, quantity=150)),  # t_4
            (9000, MockTrade(timestamp=9000, quantity=900)),  # t_5
        ]
        
        # --- Manual Calculation ---
        # Step 1: Instantaneous Velocities (v_k)
        # v_1 = 300 / (2-1) = 300.0 (quantity at t_1 / time_diff)
        # v_2 = 600 / (4-2) = 300.0
        # v_3 = 100 / (5-4) = 100.0
        # v_4 = 150 / (6-5) = 150.0
        # v_5 = 900 / (9-6) = 300.0
        
        # Step 2: Smoothed Velocities (VMF_raw,k) with N=3
        # VMF_raw,2 = mean(v_1, v_2, v_3) = mean(300, 300, 100) = 233.333
        # VMF_raw,3 = mean(v_2, v_3, v_4) = mean(300, 100, 150) = 183.333  
        # VMF_raw,4 = mean(v_3, v_4, v_5) = mean(100, 150, 300) = 183.333
        
        # Step 3: Normalized VMF (VMF_k) using last N=3 VMF_raw values
        # VMF_raw values: [233.333, 183.333, 183.333]
        #
        # μ = mean(233.333, 183.333, 183.333) = 200.0
        #
        # σ = sqrt( mean( (233.333-200)^2, (183.333-200)^2, (183.333-200)^2 ) )
        # σ = sqrt( mean( 1111.089, 277.789, 277.789 ) )
        # σ = sqrt( 555.556 ) = 23.570
        #
        # VMF_final = (VMF_raw,4 - μ) / σ
        # VMF_final = (183.333 - 200.0) / 23.570 = -16.667 / 23.570 = -0.7071
        
        expected_vmf = -0.7071
        
        # --- Code Execution ---
        result = compute_vmf(trades, smoothing_period_trades=3)
        
        # Assert that the calculated VMF is close to our manual calculation
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, expected_vmf, places=4)
    
    def test_constant_velocity_normalization(self):
        """Test that constant velocity produces zero normalized VMF."""
        # Create trades with constant velocity (same quantity, same time intervals)
        trades = []
        for i in range(50):  # Need enough for 2 * smoothing_period_trades
            timestamp = 1000 + i * 1000  # 1s intervals
            quantity = 100.0  # Constant quantity
            trades.append((timestamp, MockTrade(timestamp=timestamp, quantity=quantity)))
        
        result = compute_vmf(trades, smoothing_period_trades=3)
        
        # With constant velocity, the normalized VMF should be 0.0
        # (since all VMF_raw values are the same, std dev is 0)
        self.assertIsNotNone(result)
        self.assertEqual(result, 0.0)
    
    def test_large_dataset(self):
        """Test VMF with a larger dataset to ensure it produces reasonable results."""
        # Generate a realistic sequence of trades
        trades = []
        for i in range(100):  # Plenty of data
            timestamp = 1000 + i * 1000  # 1s intervals
            quantity = 100.0 + (i % 3) * 50.0  # Varying quantities
            trades.append((timestamp, MockTrade(timestamp=timestamp, quantity=quantity)))
        
        result = compute_vmf(trades, smoothing_period_trades=5)
        
        # Should produce a valid result
        self.assertIsNotNone(result)
        self.assertIsInstance(result, float)
        self.assertFalse(math.isnan(result))
        self.assertFalse(math.isinf(result))
        # Normalized values should typically be within reasonable bounds
        self.assertTrue(-5 <= result <= 5)
    
    def test_timestamp_units(self):
        """Test that different timestamp units are handled correctly."""
        # Create trades with millisecond timestamps
        trades_ms = []
        for i in range(50):
            timestamp = 1000000 + i * 1000  # Millisecond timestamps
            trades_ms.append((timestamp, MockTrade(timestamp=timestamp, quantity=100.0)))
        
        result_ms = compute_vmf(trades_ms, smoothing_period_trades=3)
        
        # Create trades with second timestamps  
        trades_s = []
        for i in range(50):
            timestamp = 1000 + i  # Second timestamps
            trades_s.append((timestamp, MockTrade(timestamp=timestamp, quantity=100.0)))
        
        result_s = compute_vmf(trades_s, smoothing_period_trades=3)
        
        # Both should produce valid results
        self.assertIsNotNone(result_ms)
        self.assertIsNotNone(result_s)
        self.assertIsInstance(result_ms, float)
        self.assertIsInstance(result_s, float)
    
    def test_missing_attributes(self):
        """Test handling of trade objects missing required attributes."""
        class BadTrade:
            def __init__(self, timestamp=None, quantity=None):
                if timestamp is not None:
                    self.timestamp = timestamp
                if quantity is not None:
                    self.quantity = quantity
        
        trades = [
            (1000, BadTrade()),  # Missing both attributes
            (2000, BadTrade(timestamp=2000)),  # Missing quantity
            (3000, BadTrade(quantity=100.0)),  # Missing timestamp
        ]
        
        # Add some valid trades
        for i in range(4, 50):
            timestamp = 1000 + i * 1000
            trades.append((timestamp, MockTrade(timestamp=timestamp, quantity=100.0)))
        
        # Should handle gracefully and still compute VMF from valid trades
        result = compute_vmf(trades, smoothing_period_trades=3)
        self.assertIsNotNone(result)
    
    def test_zero_time_difference(self):
        """Test handling of zero time differences (edge case)."""
        trades = [
            (1000, MockTrade(timestamp=1000, quantity=100.0)),
            (1000, MockTrade(timestamp=1000, quantity=200.0)),  # Same timestamp - should aggregate
            (2000, MockTrade(timestamp=2000, quantity=300.0)),
        ]
        
        # Add more trades to meet minimum requirement
        for i in range(3, 50):
            timestamp = 1000 + i * 1000
            trades.append((timestamp, MockTrade(timestamp=timestamp, quantity=100.0)))
        
        # Should handle aggregation properly
        result = compute_vmf(trades, smoothing_period_trades=3)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, float)
    
    def test_sliding_window_integration(self):
        """Test that compute_vmf works with SlidingWindow output format."""
        # Create data in the format that SlidingWindow.get_window_data() returns
        # This is a list of (timestamp_ms, data) tuples
        window_data = []
        for i in range(50):
            timestamp = 1000000 + i * 1000  # Milliseconds
            trade = MockTrade(timestamp=timestamp, quantity=100.0 + i * 10)
            window_data.append((timestamp, trade))
        
        # This simulates what you'd get from: trade_window.get_window_data()
        result = compute_vmf(window_data, smoothing_period_trades=5)
        
        # Should produce a valid result
        self.assertIsNotNone(result)
        self.assertIsInstance(result, float)
        self.assertFalse(math.isnan(result))
        self.assertFalse(math.isinf(result))


if __name__ == '__main__':
    unittest.main()