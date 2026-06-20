# -*- coding: utf-8 -*-
"""
交易策略配置
定义各组件的参数
"""
from pathlib import Path

# 项目路径
PROJECT_DIR = Path(__file__).parent.parent.absolute()
RESULT_FILE = PROJECT_DIR / "result_v5.json"

# ==================== 信号指示器配置 ====================

# 评分信号阈值
SCORE_THRESHOLDS = {
    "strong_buy": 75,   # 强烈买入
    "buy": 60,         # 买入
    "hold": 40,        # 持有
    "sell": 30,        # 卖出
    "strong_sell": 20, # 强烈卖出
}

# ==================== 资金管理配置 ====================

# 固定比例仓位配置
MONEY_MANAGER_CONFIG = {
    "type": "fixed_ratio",
    "max_position_per_stock": 0.15,  # 单只股票最大仓位 15%
    "max_positions": 5,               # 最大持仓股票数
    "min_cash_reserve": 0.1,         # 最小现金储备 10%
    "pyramiding": True,              # 允许金字塔加仓
    "pyramiding_step": 0.05,         # 加仓步长 5%
}

# Kelly 公式仓位配置
KELLY_CONFIG = {
    "type": "kelly",
    "fraction": 0.25,                # Kelly 分�� (0.25 = 半 Kelly)
    "max_position": 0.2,             # 最大仓位上限
    "min_position": 0.02,            # 最小仓位下限
}

# ==================== 风控配置 ====================

STOP_LOSS_CONFIG = {
    "enabled": True,
    "trailing_stop": True,           # 启用移动止损
    "fixed_stop_loss": 0.07,         # 固定止损 7%
    "trailing_distance": 0.05,       # 移动止损距离 5%
    "time_based_stop": 20,           # 持仓超过20天强制止损
}

TAKE_PROFIT_CONFIG = {
    "enabled": True,
    "levels": [
        {"threshold": 0.08, "exit_ratio": 0.5},   # 涨 8% 卖出一半
        {"threshold": 0.15, "exit_ratio": 0.7},   # 涨 15% 卖出 70%
        {"threshold": 0.25, "exit_ratio": 1.0},   # 涨 25% 全部卖出
    ],
}

# ==================== 回测配置 ====================

BACKTEST_CONFIG = {
    "initial_cash": 1000000,         # 初始资金 100万
    "commission_rate": 0.0003,      # 佣金万三
    "stamp_tax_rate": 0.001,        # 印花税千一 (卖出)
    "slippage": 0.001,              # 滑点千一
    "start_date": "2024-01-01",
    "end_date": "2026-06-30",
}

# ==================== 默认策略配置 ====================

DEFAULT_STRATEGY = {
    "name": "score_based_strategy",
    "signal": {
        "type": "score_signal",
        "config": SCORE_THRESHOLDS,
    },
    "money_manager": {
        "type": "fixed_ratio",
        "config": MONEY_MANAGER_CONFIG,
    },
    "risk_manager": {
        "stop_loss": STOP_LOSS_CONFIG,
        "take_profit": TAKE_PROFIT_CONFIG,
    },
}