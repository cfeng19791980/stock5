# -*- coding: utf-8 -*-
"""
交易策略引擎主入口
读取分析预测结果，生成交易信号，管理仓位和风控
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .config_strategy import (
    RESULT_FILE, DEFAULT_STRATEGY, 
    SCORE_THRESHOLDS, MONEY_MANAGER_CONFIG,
    STOP_LOSS_CONFIG, TAKE_PROFIT_CONFIG
)


class SignalType(Enum):
    """交易信号类型"""
    STRONG_BUY = "强烈买入"
    BUY = "买入"
    HOLD = "持有"
    SELL = "卖出"
    STRONG_SELL = "强烈卖出"
    NONE = "无信号"


class PositionStatus(Enum):
    """持仓状态"""
    NONE = "空仓"
    HOLDING = "持仓"
    PENDING = "待确认"


@dataclass
class StockSignal:
    """股票信号"""
    code: str
    name: str
    score: float           # 分析模型评分
    price: float           # 当前价格
    pct_chg: float         # ���跌幅
    signal: SignalType     # 交易信号
    position_ratio: float  # 建议仓位比例
    stop_loss_price: float # 止损价
    take_profit_price: float # 止盈价
    reasons: List[str] = field(default_factory=list)


@dataclass
class Position:
    """持仓"""
    code: str
    name: str
    quantity: int          # 持股数量
    avg_cost: float        # 平均成本
    current_price: float   # 当前价格
    entry_date: str        # 入场日期
    stop_loss_price: float # 止损价
    take_profit_price: float # 止盈价


@dataclass
class TradeAction:
    """交易动作"""
    action: str            # buy/sell/hold
    code: str
    name: str
    quantity: int
    price: float
    reason: str


class StrategyEngine:
    """交易策略引擎"""
    
    def __init__(self, config: Dict = None):
        self.config = config or DEFAULT_STRATEGY
        self.score_thresholds = SCORE_THRESHOLDS
        self.mm_config = MONEY_MANAGER_CONFIG
        self.sl_config = STOP_LOSS_CONFIG
        self.tp_config = TAKE_PROFIT_CONFIG
        
        self.positions: Dict[str, Position] = {}  # 当前持仓
        self.cash: float = 1000000                # 现金 (默认100万)
        self.initial_cash: float = 1000000
        
        self.trade_log: List[TradeAction] = []
    
    def load_analysis_result(self, file_path: str = None) -> Dict:
        """加载分析预测结果"""
        path = Path(file_path) if file_path else RESULT_FILE
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_signal_from_score(self, score: float) -> SignalType:
        """根据评分获取信号"""
        if score >= self.score_thresholds["strong_buy"]:
            return SignalType.STRONG_BUY
        elif score >= self.score_thresholds["buy"]:
            return SignalType.BUY
        elif score >= self.score_thresholds["hold"]:
            return SignalType.HOLD
        elif score >= self.score_thresholds["sell"]:
            return SignalType.SELL
        else:
            return SignalType.STRONG_SELL
    
    def calculate_position_ratio(self, signal: SignalType) -> float:
        """根据信号计算仓位比例"""
        position_map = {
            SignalType.STRONG_BUY: 0.15,  # 15%
            SignalType.BUY: 0.10,         # 10%
            SignalType.HOLD: 0.05,        # 5%
            SignalType.SELL: 0.0,         # 0%
            SignalType.STRONG_SELL: 0.0,  # 0%
            SignalType.NONE: 0.0,
        }
        return position_map.get(signal, 0.0)
    
    def calculate_stop_loss(self, price: float, signal: SignalType) -> float:
        """计算止损价"""
        if not self.sl_config["enabled"]:
            return price * 0.9
        
        if signal in [SignalType.STRONG_BUY, SignalType.BUY]:
            # 买入持仓使用移动止损或固定止损
            if self.sl_config["trailing_stop"]:
                return price * (1 - self.sl_config["trailing_distance"])
            else:
                return price * (1 - self.sl_config["fixed_stop_loss"])
        return price
    
    def calculate_take_profit(self, price: float, signal: SignalType) -> float:
        """计算止盈价"""
        if not self.tp_config["enabled"]:
            return price * 1.3
        
        # 返回第一档止盈价
        if self.tp_config["levels"]:
            threshold = self.tp_config["levels"][0]["threshold"]
            return price * (1 + threshold)
        return price * 1.15
    
    def generate_signals(self, analysis_result: Dict = None) -> List[StockSignal]:
        """生成交易信号列表"""
        if analysis_result is None:
            analysis_result = self.load_analysis_result()
        
        stocks = analysis_result.get("stocks", [])
        signals = []
        
        for stock in stocks:
            code = stock.get("code", "")
            name = stock.get("name", "")
            score = stock.get("score", 0)
            price = stock.get("close", 0)
            pct_chg = stock.get("pct_chg", 0)
            
            # 获取信号
            signal = self.get_signal_from_score(score)
            
            # 计算仓位和风控价格
            position_ratio = self.calculate_position_ratio(signal)
            stop_loss_price = self.calculate_stop_loss(price, signal)
            take_profit_price = self.calculate_take_profit(price, signal)
            
            # 生成原因
            reasons = []
            if signal in [SignalType.BUY, SignalType.STRONG_BUY]:
                reasons.append(f"评���{score} >= {self.score_thresholds['buy']}")
                reasons.append(f"建议仓位{int(position_ratio*100)}%")
            elif signal == SignalType.HOLD:
                reasons.append(f"评分{score} 在持有区间")
            else:
                reasons.append(f"评分{score} 低于买入阈值")
            
            stock_signal = StockSignal(
                code=code,
                name=name,
                score=score,
                price=price,
                pct_chg=pct_chg,
                signal=signal,
                position_ratio=position_ratio,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                reasons=reasons
            )
            signals.append(stock_signal)
        
        # 按评分排序
        signals.sort(key=lambda x: x.score, reverse=True)
        return signals
    
    def get_trading_recommendations(self) -> Dict:
        """获取交易建议"""
        signals = self.generate_signals()
        
        recommendations = {
            "timestamp": datetime.now().isoformat(),
            "total_cash": self.cash,
            "positions": len(self.positions),
            "recommendations": {
                "strong_buy": [],
                "buy": [],
                "hold": [],
                "sell": [],
            }
        }
        
        for signal in signals:
            item = {
                "code": signal.code,
                "name": signal.name,
                "score": signal.score,
                "price": signal.price,
                "pct_chg": signal.pct_chg,
                "position_ratio": signal.position_ratio,
                "stop_loss": signal.stop_loss_price,
                "take_profit": signal.take_profit_price,
                "reasons": signal.reasons,
            }
            
            if signal.signal == SignalType.STRONG_BUY:
                recommendations["recommendations"]["strong_buy"].append(item)
            elif signal.signal == SignalType.BUY:
                recommendations["recommendations"]["buy"].append(item)
            elif signal.signal == SignalType.HOLD:
                recommendations["recommendations"]["hold"].append(item)
            elif signal.signal in [SignalType.SELL, SignalType.STRONG_SELL]:
                recommendations["recommendations"]["sell"].append(item)
        
        return recommendations
    
    def export_signals(self, output_path: str = None) -> str:
        """导出信号到JSON文件"""
        recommendations = self.get_trading_recommendations()
        
        if output_path is None:
            output_path = Path(RESULT_FILE).parent / "strategy_signals.json"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(recommendations, f, ensure_ascii=False, indent=2)
        
        return str(output_path)


def run_strategy():
    """运行策略引擎"""
    engine = StrategyEngine()
    
    print("=" * 60)
    print("Stock5 交易策略引擎")
    print("=" * 60)
    
    # 加载分析结果并生成信号
    print("\n📊 加载分析预测结果...")
    signals = engine.generate_signals()
    print(f"   加载了 {len(signals)} 只股票的分析结果")
    
    # 获取交易建议
    print("\n🎯 生成交易信号...")
    recommendations = engine.get_trading_recommendations()
    
    # 打印各等级信号数量
    rec = recommendations["recommendations"]
    print(f"   强烈买入: {len(rec['strong_buy'])} 只")
    print(f"   买入: {len(rec['buy'])} 只")
    print(f"   持有: {len(rec['hold'])} 只")
    print(f"   卖出: {len(rec['sell'])} 只")
    
    # 导出结果
    output_file = engine.export_signals()
    print(f"\n✅ 信号已导出到: {output_file}")
    
    return recommendations


if __name__ == "__main__":
    run_strategy()