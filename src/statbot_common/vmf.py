import math
import logging
from typing import List, Tuple, Optional, Deque
from collections import deque
from .timestamp import normalize_timestamp_to_ms
from .protocols import Trade


def compute_vmf(
    data_points: List[Tuple[int, Trade]],
    smoothing_period_trades: int = 20,
) -> Optional[float]:
    """
    Compute Volume-weighted Market Flow (VMF) from a list of (timestamp, trade) tuples.
    
    The VMF indicator calculates normalized trade velocity using three steps:
    1. Instantaneous Velocity: v_k = q_k / (t_k - t_{k-1})
    2. Smoothed Velocity: VMF_raw,k = mean of last N velocities  
    3. Normalized VMF: VMF_k = (VMF_raw,k - μ) / σ
    
    Args:
        data_points: A list of tuples, where each tuple contains a
                     Unix timestamp (s, ms, us, or ns) and a Trade object
                     with 'timestamp' and 'quantity' attributes.
        smoothing_period_trades: Number of trades (N) for smoothing velocity. Defaults to 20.
    
    Returns:
        The normalized VMF value, or None if computation is not possible.
        Requires at least (2 * smoothing_period_trades) data points.
    """
    if len(data_points) < 2 * smoothing_period_trades:
        logging.debug(f"VMF calc: Not enough data points ({len(data_points)} < {2 * smoothing_period_trades}).")
        return None
    
    if smoothing_period_trades <= 0:
        logging.error("VMF calc: smoothing_period_trades must be positive.")
        return None
    
    # Step 1: Aggregate trades with same timestamp and extract valid trade data
    aggregated_trades = {}
    for ts, trade_data in data_points:
        if not hasattr(trade_data, 'timestamp') or not hasattr(trade_data, 'quantity'):
            logging.warning("VMF calc: Trade object missing 'timestamp' or 'quantity' attribute. Skipping entry.")
            continue
            
        try:
            # Normalize timestamp from the tuple (for window management) 
            # but use the trade's own timestamp for calculations
            normalized_ts = normalize_timestamp_to_ms(trade_data.timestamp)
            quantity = float(trade_data.quantity)
            
            if normalized_ts in aggregated_trades:
                aggregated_trades[normalized_ts] += quantity
            else:
                aggregated_trades[normalized_ts] = quantity
                
        except (ValueError, TypeError) as e:
            logging.warning(f"VMF calc: Could not process trade data: {e}. Skipping entry.")
            continue
    
    if len(aggregated_trades) < 2:
        logging.debug("VMF calc: Not enough valid trades after aggregation and filtering.")
        return None
    
    # Step 2: Sort by timestamp and calculate instantaneous velocities
    sorted_trades = sorted(aggregated_trades.items())
    velocities = []
    
    for i in range(1, len(sorted_trades)):
        ts_prev, _ = sorted_trades[i-1]
        ts_curr, quantity_curr = sorted_trades[i]
        
        time_diff_ms = ts_curr - ts_prev
        if time_diff_ms == 0:
            logging.debug(f"VMF calc: Zero time delta ({time_diff_ms} ms). Skipping.")
        elif time_diff_ms < 0:
            logging.warning(f"VMF calc: Negative time delta ({time_diff_ms} ms). Skipping.")
        else:
            # Convert to seconds for velocity calculation
            time_diff_s = time_diff_ms / 1000.0
            velocity = quantity_curr / time_diff_s
            velocities.append(velocity)
    
    if len(velocities) < smoothing_period_trades:
        logging.debug(f"VMF calc: Not enough velocities ({len(velocities)} < {smoothing_period_trades}).")
        return None
    
    # Step 3: Calculate smoothed velocities (VMF_raw values)
    vmf_raw_values = []
    for i in range(smoothing_period_trades - 1, len(velocities)):
        # Take the last N velocities for smoothing
        velocity_window = velocities[i - smoothing_period_trades + 1:i + 1]
        vmf_raw = sum(velocity_window) / len(velocity_window)
        vmf_raw_values.append(vmf_raw)
    
    if len(vmf_raw_values) < smoothing_period_trades:
        logging.debug(f"VMF calc: Not enough VMF_raw values ({len(vmf_raw_values)} < {smoothing_period_trades}).")
        return None
    
    # Step 4: Calculate normalized VMF using all VMF_raw values (two-timescale approach)
    # Use the entire set of smoothed values for normalization to capture long-term context
    normalization_window = vmf_raw_values
    
    # Calculate mean and standard deviation
    mean_vmf_raw = sum(normalization_window) / len(normalization_window)
    
    # Calculate variance
    variance = sum((x - mean_vmf_raw) ** 2 for x in normalization_window) / len(normalization_window)
    std_vmf_raw = math.sqrt(variance)
    
    # Get the latest VMF_raw value for normalization
    latest_vmf_raw = vmf_raw_values[-1]
    
    # Avoid division by zero or extremely small standard deviations that arise
    # from floating point rounding errors when all VMF_raw values are
    # effectively identical.  Using direct equality can misclassify a near-zero
    # standard deviation as non-zero, leading to spurious large normalized
    # results (e.g. constant velocity test returning ``1.0``).  Treat values
    # close to zero within a tiny tolerance as zero.
    if math.isclose(std_vmf_raw, 0.0, abs_tol=1e-12):
        logging.debug("VMF calc: Standard deviation is zero, returning 0.0.")
        return 0.0
    
    # Calculate normalized VMF
    try:
        vmf_normalized = (latest_vmf_raw - mean_vmf_raw) / std_vmf_raw
        return vmf_normalized
    except (ValueError, ZeroDivisionError) as e:
        logging.error(f"VMF calc: Error calculating normalized VMF: {e}")
        return None