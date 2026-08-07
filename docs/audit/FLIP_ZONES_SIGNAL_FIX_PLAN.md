# Fix Plan: Wrong Signal Labeling (CRITICAL) - COMPLETED

## Problem Statement
The combined market signal can label a bullish call as bearish due to incorrect logic in the regime classifier.

## Root Cause Analysis

### Location: `backend/services/morning_briefing.py` lines 137-147
The original code had fallback conditions that could cause mislabeling:

```python
# Spot vs flip level
has_flip = not _is_effectively_zero(flip_level) and not _is_effectively_zero(spot)
if has_flip:
    if spot > flip_level and has_gex and net_gex > 0:
        bullish_score += 1
    elif spot < flip_level and has_gex and net_gex < 0:
        bearish_score += 1
    elif spot > flip_level:        # BUG: Added without GEX confirmation
        bullish_score += 1
    elif spot < flip_level:        # BUG: Could label bullish as bearish
        bearish_score += 1
```

### Issue Explanation
When flip_level represented a resistance level and spot was below it, the code would add a bearish score even without negative GEX confirmation. This caused:
1. False bearish signals when market was actually healthy
2. Incorrect combined signal when combined with ML predictions

## Fix Applied

### Changed Code (lines 137-147):
```python
# Spot vs flip level - only score when combined with GEX signal
# Flip level without GEX is ambiguous; requiring both prevents mislabeling
has_flip = not _is_effectively_zero(flip_level) and not _is_effectively_zero(spot)
if has_flip:
    if spot > flip_level and has_gex and net_gex > 0:
        bullish_score += 1
    elif spot < flip_level and has_gex and net_gex < 0:
        bearish_score += 1
    # Removed: elif spot > flip_level / elif spot < flip_level
    # These were causing bullish to be labeled as bearish when flip_level
    # was a resistance level and spot was below it, without GEX confirmation
```

## Verification

### Tests Run
```bash
cd backend && .venv/bin/python3 -m pytest tests/services/test_morning_briefing.py -v
# Result: 23 passed

cd backend && .venv/bin/python3 -m pytest tests/services/test_heatseeker.py -v
# Result: 50 passed

cd backend && .venv/bin/python3 -m pytest tests/routes/test_steal_three_routes.py -v
# Result: 18 passed
```

### Additional Test Cases
```python
# Test case: Bullish scenario - spot above flip level with positive GEX
classify_regime(net_gex=2e9, ..., flip_level=400.0, spot=450.0)
# Result: BULLISH ✓

# Test case: Bearish scenario - spot below flip level with negative GEX
classify_regime(net_gex=-2e9, ..., flip_level=400.0, spot=350.0)
# Result: BEARISH ✓

# Test case: Edge case - spot below flip but positive GEX
classify_regime(net_gex=5e8, ..., flip_level=400.0, spot=350.0)
# Result: BULLISH ✓ (correctly based on positive GEX)
```

## Steal-List Integration Status ✅

All three steal-list endpoints are working:
1. `/api/dual_gex/{ticker}` - Rank #1 Dual-GEX + activity ratio ✅
2. `/api/screener/income` - Rank #3 Wheel income screener ✅
3. `/api/iv_mid/{ticker}` - Rank #5 IV-from-mid cross-check ✅

## Files Modified
- `backend/services/morning_briefing.py` - Removed fallback conditions in `classify_regime()`

## Summary
The fix removes ambiguous fallback conditions that could cause bullish signals to be mislabeled as bearish when flip_level (GEX zero-crossing) was used as a reference without GEX confirmation. The regime classifier now requires GEX confirmation for the flip level signal, matching the documented API behavior.