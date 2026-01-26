# State Migration for Dynamic Parameters

## Problem
Calculators like `QueueImbalanceCalculator` are initialized with static configurations (e.g., `tick_size`). In live markets (especially Polymarket), these parameters can change dynamically.
- **Naive Re-instantiation:** Creating `new QueueImbalanceCalculator(new_tick_size)` acts as a "cold start," discarding all history. This causes massive artifacts/discontinuities in rolling indicators (e.g., dropping to `None`).
- **Desired Behavior:** We want to preserve the rolling window history (metrics computed under the *old* regime) while processing new updates under the *new* regime. The standard `get_state()` -> `restore_from_state()` is unsafe because it blindly restores the old configuration.

## Proposed Solution: `migrate_state()` Utility

Add a utility to explicitly handle the "hot-swap" of configuration while preserving history.

### Implementation Sketch
```python
def migrate_calculator(old_instance, new_tick_size: Decimal):
    """
    Creates a new calculator instance with updated tick_size but preserving
    the historical time-weighted segments from the old instance.
    """
    # 1. Capture full history
    state = old_instance.get_state()
    
    # 2. Patch the configuration in the serialized state
    # This ensures restore_from_state() uses the NEW parameter
    state['config']['tick_size'] = str(new_tick_size)
    
    # 3. Initialize fresh instance with NEW config
    # (Note: restore_from_state will overwrite this config from the dict, 
    # so step 2 is critical)
    new_config = QueueImbalanceConfig(
        k_levels=old_instance.config.k_levels,
        tick_size=new_tick_size,  # New Value
        half_life_ticks=old_instance.config.half_life_ticks,
        window_ms=old_instance.config.window_ms
    )
    new_instance = QueueImbalanceCalculator(new_config)
    
    # 4. Restore history into the new container
    new_instance.restore_from_state(state)
    
    return new_instance
```

### Usage Guide
1. Detect `tick_size` change in your event loop.
2. Call `new_calc = migrate_calculator(old_calc, new_tick_size)`.
3. Proceed with `new_calc.update_from_book(...)`.

### Interpretation Caveat
This creates a "blended" window where historical segments represent queue pressure at the *old* tick size scale, and new segments represent the *new* scale.
- **Mathematically:** It's a "smooth transition" rather than a correct normalization (since "1 tick" meant a different dollar amount previously).
- **Practically:** This is preferred over a discontinuity/drop-to-zero, as the blended average will converge to the new regime over `window_ms`.
