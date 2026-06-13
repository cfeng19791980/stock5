# Stock5 Model Autoresearch Experiment

## Goal
Improve buy signal accuracy and count for stock5 model.

## Benchmark
```bash
cd E:\stock5 && python backtest_5minute.py
```

## Current Baseline
- **Strong Buy Accuracy**: 84.0% (100 samples)
- **Strong Buy Total Return**: +34.41%
- **Buy Accuracy**: 40.0% (468 samples)
- **Total Samples**: 4,206 verified

## Metric
- **Primary**: Strong buy signal accuracy (higher is better)
- **Secondary**: Total strong buy signals count (> 100)
- **Target**: Maintain >80% accuracy while increasing signal count

## Optimization Directions
1. Increase strong buy signal generation (more than 100)
2. Improve buy accuracy from 40% to 50%+
3. Optimize threshold for buy signals

## Scope
- analyzer_v5_minute.py: prediction logic and threshold
- config.py: score thresholds