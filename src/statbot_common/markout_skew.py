"""
Markout Skew (Information Content) — Sliding Window Implementation

This module implements the markout skew calculation as specified in the markout.md spec.
It leverages the existing SlidingWindow infrastructure and follows the established patterns
in statbot_common for windowed calculations.

Key features:
- Completion-time sliding windows (§4 from spec)
- L3 trade aggregation by timestamp and side (§2 from spec)
- Cross-stream tie-break ordering support (§3 from spec)
- Clock-time and event-time horizon support (§1 from spec)
- NaN handling for zero counts (§7 from spec)
"""

import logging
from typing import List, Dict, Optional, NamedTuple, Literal, Tuple
from collections import defaultdict
from .sliding_window import SlidingWindow
from .protocols import L3Trade, MidPrice
from .timestamp import normalize_timestamp_to_ms


class MarkoutObservation(NamedTuple):
    """
    A single markout observation representing an aggregated trade at a timestamp.
    
    This corresponds to one side (buy or sell) of coalesced L3 trades sharing 
    the same timestamp, as described in §2 of the spec.
    """
    start_time_ms: int      # Trade timestamp (t)
    horizon_time_ms: int    # When markout should be evaluated (u = t + τ)
    side: Literal[1, -1]    # +1 = buy aggressor, -1 = sell aggressor
    pre_trade_mid: float    # Mid-price just before trade execution m(t^-)
    markout: Optional[float] = None  # Δm = m(u) - m(t^-), set when completed


class MarkoutConfig(NamedTuple):
    """Configuration for markout skew calculation."""
    horizon_type: Literal["clock", "event"]  # Clock-time or event-time horizon
    tau_ms: Optional[int] = None             # Clock-time horizon in milliseconds
    k_trades: Optional[int] = None           # Event-time horizon in number of trades
    window_ms: int = 300000                  # Completion-time window (default 5 minutes)


class MarkoutSkewCalculator:
    """
    Calculates markout skew using completion-time sliding windows.
    
    This class implements the core algorithm from the markout.md spec:
    1. Aggregates coalesced L3 trades by timestamp and side (§2)
    2. Schedules horizon evaluations (clock or event time) (§6)
    3. Maintains completion-time windows for buy/sell observations (§4, §5)
    4. Computes side-conditional means and skew (§5)
    
    Uses existing SlidingWindow infrastructure for O(1) window operations.
    """
    
    def __init__(self, config: MarkoutConfig):
        """
        Initialize the markout skew calculator.
        
        Args:
            config: Configuration specifying horizon type, parameters, and window size
        """
        self.config = config
        
        # Validate configuration
        if config.horizon_type == "clock" and config.tau_ms is None:
            raise ValueError("Clock-time horizon requires tau_ms parameter")
        if config.horizon_type == "event" and config.k_trades is None:
            raise ValueError("Event-time horizon requires k_trades parameter")
        
        # Use existing SlidingWindow for completed observations (completion-time windows)
        self.buy_window = SlidingWindow(config.window_ms)
        self.sell_window = SlidingWindow(config.window_ms)
        
        # Pending observations awaiting horizon completion
        self.pending_observations: List[MarkoutObservation] = []
        # Track last input timestamp for order diagnostics
        self._last_input_time_ms: Optional[int] = None
        
        # Event-time horizon state
        if config.horizon_type == "event":
            self.trade_counter = 0
            self.event_horizon_queue: List[Tuple[int, MarkoutObservation]] = []  # (target_trade_index, obs)
    
    def add_coalesced_l3_trades(self, 
                               timestamp_ms: int, 
                               trades: List[L3Trade], 
                               pre_trade_mid: float) -> List[MarkoutObservation]:
        """
        Add coalesced L3 trades from the same timestamp.
        
        Implements §2 from spec: aggregates trades by aggressor side into 
        up to two observations (one buy, one sell) sharing the same pre-trade mid.
        
        Args:
            timestamp_ms: Timestamp of the coalesced trades
            trades: List of L3 trades sharing this timestamp
            pre_trade_mid: Mid-price m(t^-) just before these trades
            
        Returns:
            List of created observations (0-2 observations)
        """
        if not trades:
            return []

        normalized_timestamp_ms = normalize_timestamp_to_ms(timestamp_ms)
        if (
            self._last_input_time_ms is not None
            and normalized_timestamp_ms < self._last_input_time_ms
        ):
            logging.warning(
                "MarkoutSkew received out-of-order timestamp: %s < last %s",
                normalized_timestamp_ms,
                self._last_input_time_ms,
            )
        self._last_input_time_ms = normalized_timestamp_ms
        
        # Group trades by aggressor side (§2)
        buy_trades = [t for t in trades if t.aggressor_sign == 1]
        sell_trades = [t for t in trades if t.aggressor_sign == -1]
        
        created_observations = []
        
        # Create buy observation if buy-aggressor trades exist
        if buy_trades:
            obs = self._create_observation(normalized_timestamp_ms, 1, pre_trade_mid)
            created_observations.append(obs)
            self.pending_observations.append(obs)
        
        # Create sell observation if sell-aggressor trades exist  
        if sell_trades:
            obs = self._create_observation(normalized_timestamp_ms, -1, pre_trade_mid)
            created_observations.append(obs)
            self.pending_observations.append(obs)
        
        # Update trade counter for event-time horizons AFTER creating observations
        if self.config.horizon_type == "event":
            self.trade_counter += len(trades)
        
        logging.debug(f"Created {len(created_observations)} observations at t={timestamp_ms}, "
                     f"pre_trade_mid={pre_trade_mid:.6f}")
        
        return created_observations
    
    def _create_observation(self, timestamp_ms: int, side: Literal[1, -1], pre_trade_mid: float) -> MarkoutObservation:
        """Create a single markout observation with appropriate horizon scheduling.
        
        Note: timestamp_ms is expected to already be normalized by the caller.
        """
        if self.config.horizon_type == "clock":
            # Clock-time horizon: u = t + τ
            horizon_time_ms = timestamp_ms + self.config.tau_ms
            return MarkoutObservation(
                start_time_ms=timestamp_ms,
                horizon_time_ms=horizon_time_ms,
                side=side,
                pre_trade_mid=pre_trade_mid
            )
        else:
            # Event-time horizon: u = timestamp of (i+K)th trade
            # Use current trade counter + K (counter will be updated after all observations are created)
            target_trade_index = self.trade_counter + self.config.k_trades
            obs = MarkoutObservation(
                start_time_ms=timestamp_ms,
                horizon_time_ms=-1,  # Placeholder, will be set when target trade occurs
                side=side,
                pre_trade_mid=pre_trade_mid
            )
            self.event_horizon_queue.append((target_trade_index, obs))
            return obs
    
    def complete_horizons_clock_time(self, current_time_ms: int, current_mid: float) -> List[MarkoutObservation]:
        """
        Complete any clock-time horizons that have reached their target time.
        
        Args:
            current_time_ms: Current wall-clock time in replay
            current_mid: Current mid-price m(u)
            
        Returns:
            List of completed observations
        """
        if self.config.horizon_type != "clock":
            return []
        
        # Normalize current time
        normalized_current_time_ms = normalize_timestamp_to_ms(current_time_ms)
        
        completed = []
        remaining = []
        
        for obs in self.pending_observations:
            if obs.horizon_time_ms <= normalized_current_time_ms:
                # Complete this observation: Δm = m(u) - m(t^-)
                markout = current_mid - obs.pre_trade_mid
                completed_obs = obs._replace(markout=markout)
                completed.append(completed_obs)
                
                # Add to appropriate completion-time window
                # Note: horizon_time_ms is already in milliseconds, don't normalize again
                if obs.side == 1:
                    self.buy_window.add(obs.horizon_time_ms, completed_obs)
                else:
                    self.sell_window.add(obs.horizon_time_ms, completed_obs)
                    
                logging.debug(f"Completed observation: side={obs.side}, markout={markout:.6f}, "
                             f"horizon_time={obs.horizon_time_ms}")
            else:
                remaining.append(obs)
        
        self.pending_observations = remaining
        return completed
    
    def complete_horizons_event_time(self, current_time_ms: int, current_mid: float) -> List[MarkoutObservation]:
        """
        Complete any event-time horizons that have reached their target trade count.
        
        Args:
            current_time_ms: Current timestamp (used as horizon time for completed observations)
            current_mid: Current mid-price m(u)
            
        Returns:
            List of completed observations
        """
        if self.config.horizon_type != "event":
            return []
        
        completed = []
        remaining_queue = []
        remaining_pending = []
        
        # Check event horizon queue
        for target_index, obs in self.event_horizon_queue:
            if self.trade_counter >= target_index:
                # This observation's horizon has been reached
                # Update horizon time to current timestamp and complete
                obs_with_horizon = obs._replace(horizon_time_ms=current_time_ms)
                markout = current_mid - obs.pre_trade_mid
                completed_obs = obs_with_horizon._replace(markout=markout)
                completed.append(completed_obs)
                
                # Add to appropriate completion-time window
                if obs.side == 1:
                    self.buy_window.add(current_time_ms, completed_obs)
                else:
                    self.sell_window.add(current_time_ms, completed_obs)
                    
                logging.debug(f"Completed event-time observation: side={obs.side}, markout={markout:.6f}, "
                             f"trade_count={self.trade_counter}")
            else:
                remaining_queue.append((target_index, obs))
        
        # Update pending observations (remove completed ones)
        for obs in self.pending_observations:
            if not any(obs is queue_obs for _, queue_obs in self.event_horizon_queue):
                remaining_pending.append(obs)
        
        self.event_horizon_queue = remaining_queue
        self.pending_observations = remaining_pending
        return completed
    
    def get_markout_skew(self, current_time_ms: int) -> Dict[str, Optional[float]]:
        """
        Calculate current markout skew using completion-time windows.
        
        Implements §4-§5 from spec: uses sliding windows by completion time,
        computes side-conditional means, and returns skew.
        
        Args:
            current_time_ms: Current time for window boundary (T in spec)
            
        Returns:
            Dictionary with keys: 'mplus', 'mminus', 'skew', 'n_buys', 'n_sells'
            NaN values returned when counts are zero (§7 from spec)
        """
        # Normalize current time and purge windows to maintain completion-time boundary [T-W, T]
        normalized_current_time_ms = normalize_timestamp_to_ms(current_time_ms)
        self.buy_window.purge(normalized_current_time_ms)
        self.sell_window.purge(normalized_current_time_ms)
        
        # Get completed observations in current window
        buy_data = self.buy_window.get_window_data()
        sell_data = self.sell_window.get_window_data()
        
        # Extract markout values
        buy_markouts = [obs[1].markout for obs in buy_data if obs[1].markout is not None]
        sell_markouts = [obs[1].markout for obs in sell_data if obs[1].markout is not None]
        
        # Calculate counts (§4)
        n_buys = len(buy_markouts)
        n_sells = len(sell_markouts)
        
        # Calculate side-conditional means (§5)
        m_plus = sum(buy_markouts) / n_buys if n_buys > 0 else None
        m_minus = sum(sell_markouts) / n_sells if n_sells > 0 else None
        
        # Calculate markout skew (§5)
        skew = None
        if m_plus is not None and m_minus is not None:
            skew = m_plus - m_minus
        
        return {
            'mplus': m_plus,
            'mminus': m_minus,
            'skew': skew,
            'n_buys': n_buys,
            'n_sells': n_sells
        }
    
    def get_state(self) -> Dict:
        """Get serializable state for persistence."""
        return {
            'config': self.config._asdict(),
            'buy_window_data': [(ts, obs._asdict()) for ts, obs in self.buy_window.get_window_data()],
            'sell_window_data': [(ts, obs._asdict()) for ts, obs in self.sell_window.get_window_data()],
            'pending_observations': [obs._asdict() for obs in self.pending_observations],
            'trade_counter': getattr(self, 'trade_counter', 0),
            'event_horizon_queue': [(idx, obs._asdict()) for idx, obs in getattr(self, 'event_horizon_queue', [])]
        }
    
    def restore_from_state(self, state: Dict):
        """Restore calculator from saved state."""
        config_dict = state['config']
        self.config = MarkoutConfig(**config_dict)
        
        # Recreate windows
        self.buy_window = SlidingWindow(self.config.window_ms)
        self.sell_window = SlidingWindow(self.config.window_ms)
        
        # Restore window data
        for ts, obs_data in state.get('buy_window_data', []):
            if isinstance(obs_data, dict):
                obs = MarkoutObservation(**obs_data)
            else:
                obs = obs_data  # Already a MarkoutObservation
            self.buy_window.add(ts, obs)
        
        for ts, obs_data in state.get('sell_window_data', []):
            if isinstance(obs_data, dict):
                obs = MarkoutObservation(**obs_data)
            else:
                obs = obs_data  # Already a MarkoutObservation
            self.sell_window.add(ts, obs)
        
        # Restore pending observations
        self.pending_observations = [
            MarkoutObservation(**obs_dict) 
            for obs_dict in state.get('pending_observations', [])
        ]
        
        # Restore event-time state if applicable
        if self.config.horizon_type == "event":
            self.trade_counter = state.get('trade_counter', 0)
            self.event_horizon_queue = [
                (idx, MarkoutObservation(**obs_dict))
                for idx, obs_dict in state.get('event_horizon_queue', [])
            ]


# Utility functions for L3 coalescing and cross-stream processing

def coalesce_l3_trades_by_timestamp(trades: List[L3Trade]) -> Dict[int, List[L3Trade]]:
    """
    Group L3 trades by timestamp for coalesced processing.
    
    Implements the aggregation requirement from §2 of the spec.
    
    Args:
        trades: List of L3 trades to group
        
    Returns:
        Dictionary mapping timestamp_ms -> list of trades at that timestamp
    """
    groups = defaultdict(list)
    for trade in trades:
        ts_ms = normalize_timestamp_to_ms(trade.timestamp)
        groups[ts_ms].append(trade)
    return dict(groups)


def compute_mid_price(bid: float, ask: float) -> float:
    """
    Compute mid-price from bid/ask spread.
    
    Args:
        bid: Best bid price
        ask: Best ask price
        
    Returns:
        Mid-price: (bid + ask) / 2
    """
    return (bid + ask) / 2.0


def validate_l2_consistency(timestamp_ms: int, 
                           l3_trades_count: int, 
                           l2_updates_count: int) -> bool:
    """
    Validate L2 consistency as specified in §2 of the spec.
    
    When coalesced L3 trades occur at a timestamp, there should be exactly
    one combined L2 update at the same timestamp.
    
    Args:
        timestamp_ms: Timestamp being validated
        l3_trades_count: Number of coalesced L3 trades at this timestamp
        l2_updates_count: Number of L2 updates at this timestamp
        
    Returns:
        True if consistent, False otherwise (logs warning)
    """
    if l3_trades_count > 0 and l2_updates_count != 1:
        logging.warning(
            f"WARN markout_skew: expected combined L2 update at t={timestamp_ms} "
            f"for coalesced L3 prints; observed {l2_updates_count} L2 updates"
        )
        return False
    return True
