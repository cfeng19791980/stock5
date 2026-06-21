# -*- coding: utf-8 -*-
"""
Stock5 交易策略模块

基于预测模型评分 + 用户持仓/资金，生成买卖建议

模块结构:
├── strategy_engine.py    # 策略引擎主入口
├── config_strategy.py    # 策略配置
├── portfolio_manager.py  # 组合管理器（持仓+资金）
├── signals/              # 信号指示器
├── money_managers/       # 资金管理
├── risk_managers/        # 风控组件
└── backtest/            # 回测引擎

快速使用:
    from strategy.strategy_engine import run_strategy
    result = run_strategy()

    from strategy.portfolio_manager import load_and_recommend
    result = load_and_recommend()
"""
from .strategy_engine import StrategyEngine, run_strategy
from .portfolio_manager import PortfolioManager, load_and_recommend
from .backtest.runner import BacktestRunner, run_backtest

__version__ = "1.1.0"
__all__ = [
    "StrategyEngine",
    "run_strategy",
    "PortfolioManager",
    "load_and_recommend",
    "BacktestRunner",
    "run_backtest",
]
