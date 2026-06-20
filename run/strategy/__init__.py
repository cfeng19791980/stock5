# -*- coding: utf-8 -*-
"""
Stock5 交易策略模块

从分析预测模型读取结果，生成交易信号，管理仓位和风控

模块结构:
├── strategy_engine.py    # 策略引擎主入口
├── config_strategy.py    # 策略配置
├── signals/              # 信号指示器
│   ├── score_signal.py  # 评分信号
│   └── momentum_signal.py
├── money_managers/       # 资金管理
│   ├── fixed_ratio.py   # 固定比例仓位
│   └── kelly.py         # Kelly公式仓位
├── risk_managers/        # 风控组件
│   ├── stop_loss.py     # 止损管理
│   └── take_profit.py   # 止盈管理
└── backtest/            # 回测引擎
    └── runner.py        # 回测运行器

快速使用:
    from strategy.strategy_engine import run_strategy
    result = run_strategy()  # 生成交易信号
    
    from strategy.backtest.runner import run_backtest
    result = run_backtest()  # 运行回测
"""
from .strategy_engine import StrategyEngine, run_strategy
from .backtest.runner import BacktestRunner, run_backtest

__version__ = "1.0.0"
__all__ = [
    "StrategyEngine",
    "run_strategy",
    "BacktestRunner", 
    "run_backtest",
]