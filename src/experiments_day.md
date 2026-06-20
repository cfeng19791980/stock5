# Stock5 Day-Level (日线) Model Optimization

## Goal
Improve day-level model prediction accuracy to generate buy signals (score >= 60).

## Current Status
- **Max score**: 55 (no buy signals)
- **Score range**: 13-55
- **Problem**: Model output distribution is too compressed

## Benchmark
```bash
cd E:\stock5 && python backtest_v5.py
```

## Root Causes
1. Score scaling - model outputs need to be scaled up
2. Feature weights may need adjustment
3. Risk check threshold may be too strict

## Optimization Directions

### 1. Score Scaling (Quick Win)
In `analyzer_v5.py` - `predict_fusion_v6` function:
- Current: `return int(np.clip(score * 100, 0, 100))`
- Try: `return int(np.clip(score * 120 + 10, 0, 100))`

### 2. Adjust Buy Threshold
In `config.py` or `analyzer_v5.py`:
- Current threshold: 60
- Try: 45-50 (similar to 5-minute model effective range)

### 3. Reduce Risk Check Aggression
In `analyzer_v5.py` - `risk_check` function:
- Current: risk multipliers reduce score significantly
- Try: more lenient multipliers

## Target Metrics
- Generate buy signals (score >= 60): > 5 per run
- Maintain reasonable accuracy (> 50%)

## Scope
- analyzer_v5.py: predict_fusion_v6, risk_check
- config.py: RISE_THRESHOLD, score thresholds