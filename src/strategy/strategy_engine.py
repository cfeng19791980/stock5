# -*- coding: utf-8 -*-
"""
交易策略引擎主入口
读取分析预测结果 + 用户持仓/资金，生成买卖建议
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .config_strategy import (
    RESULT_FILE, DEFAULT_STRATEGY,
    SCORE_THRESHOLDS, MONEY_MANAGER_CONFIG,
    STOP_LOSS_CONFIG, TAKE_PROFIT_CONFIG
)
from .portfolio_manager import PortfolioManager


class SignalType(Enum):
    STRONG_BUY = "强烈买入"
    BUY = "买入"
    HOLD = "持有"
    SELL = "卖出"
    STRONG_SELL = "强烈卖出"
    NONE = "无信号"


class PositionStatus(Enum):
    NONE = "空仓"
    HOLDING = "持仓"
    PENDING = "待确认"


@dataclass
class StockSignal:
    code: str
    name: str
    score: float
    price: float
    pct_chg: float
    signal: SignalType
    position_ratio: float
    stop_loss_price: float
    take_profit_price: float
    reasons: List[str] = field(default_factory=list)


@dataclass
class Position:
    code: str
    name: str
    quantity: int
    avg_cost: float
    current_price: float
    entry_date: str
    stop_loss_price: float
    take_profit_price: float


@dataclass
class TradeAction:
    action: str        # buy/sell/hold
    code: str
    name: str
    quantity: int
    price: float
    reason: str


class StrategyEngine:
    """交易策略引擎 — 基于预测评分 + 组合持仓生成买卖建议"""

    def __init__(self, config: Dict = None):
        self.config = config or DEFAULT_STRATEGY
        self.score_thresholds = SCORE_THRESHOLDS
        self.mm_config = MONEY_MANAGER_CONFIG
        self.sl_config = STOP_LOSS_CONFIG
        self.tp_config = TAKE_PROFIT_CONFIG
        self.portfolio_mgr = PortfolioManager()
        self.portfolio = None
        self.analysis_stocks = []

    def load_analysis_result(self, file_path: str = None) -> Dict:
        path = Path(file_path) if file_path else RESULT_FILE
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def load_portfolio(self, analysis_stocks: List[Dict] = None) -> Dict:
        stocks = analysis_stocks if analysis_stocks is not None else []
        self.portfolio = self.portfolio_mgr.load_portfolio(analysis_stocks=stocks)
        self.analysis_stocks = stocks or []
        return {
            "total_cash": self.portfolio.total_cash,
            "position_value": self.portfolio.position_value,
            "total_value": self.portfolio.total_value,
            "cash_ratio": self.portfolio.cash_ratio,
            "holding_count": self.portfolio.holding_count,
        }

    def get_signal_from_score(self, score: float) -> SignalType:
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
        position_map = {
            SignalType.STRONG_BUY: 0.15, SignalType.BUY: 0.10,
            SignalType.HOLD: 0.05, SignalType.SELL: 0.0,
            SignalType.STRONG_SELL: 0.0, SignalType.NONE: 0.0,
        }
        return position_map.get(signal, 0.0)

    def calculate_stop_loss(self, price: float, signal: SignalType) -> float:
        if not self.sl_config["enabled"]:
            return price * 0.9
        if signal in [SignalType.STRONG_BUY, SignalType.BUY]:
            if self.sl_config["trailing_stop"]:
                return price * (1 - self.sl_config["trailing_distance"])
            else:
                return price * (1 - self.sl_config["fixed_stop_loss"])
        return price

    def calculate_take_profit(self, price: float, signal: SignalType) -> float:
        if not self.tp_config["enabled"]:
            return price * 1.3
        if self.tp_config["levels"]:
            threshold = self.tp_config["levels"][0]["threshold"]
            return price * (1 + threshold)
        return price * 1.15

    def generate_signals(self, analysis_result: Dict = None) -> List[StockSignal]:
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
            signal = self.get_signal_from_score(score)
            position_ratio = self.calculate_position_ratio(signal)
            stop_loss_price = self.calculate_stop_loss(price, signal)
            take_profit_price = self.calculate_take_profit(price, signal)
            reasons = []
            if signal in [SignalType.BUY, SignalType.STRONG_BUY]:
                reasons.append(f"评分{score} >= {self.score_thresholds['buy']}")
                reasons.append(f"建议仓位{int(position_ratio*100)}%")
            elif signal == SignalType.HOLD:
                reasons.append(f"评分{score} 在持有区间")
            else:
                reasons.append(f"评分{score} 低于买入阈值")
            stock_signal = StockSignal(
                code=code, name=name, score=score, price=price, pct_chg=pct_chg,
                signal=signal, position_ratio=position_ratio,
                stop_loss_price=stop_loss_price, take_profit_price=take_profit_price,
                reasons=reasons,
            )
            signals.append(stock_signal)
        signals.sort(key=lambda x: x.score, reverse=True)
        return signals

    def generate_recommendations(self) -> Dict:
        """核心接口：基于实时持仓+资金+预测评分，生成完整买卖建议"""
        analysis = self.load_analysis_result()
        stocks = analysis.get("stocks", [])
        self.load_portfolio(analysis_stocks=stocks)
        return PortfolioManager.compute_recommendation(
            self.portfolio, stocks,
            config={
                "buy_threshold": self.score_thresholds["buy"],
                "strong_buy_threshold": self.score_thresholds["strong_buy"],
                "sell_threshold": self.score_thresholds["sell"],
                "max_positions": self.mm_config["max_positions"],
                "max_single_pct": self.mm_config["max_position_per_stock"],
                "stop_loss_pct": self.sl_config["fixed_stop_loss"],
                "take_profit_pct": self.tp_config["levels"][0]["threshold"] if self.tp_config["levels"] else 0.15,
            }
        )

    def get_trading_recommendations(self) -> Dict:
        return self.generate_recommendations()

    def export_signals(self, output_path: str = None) -> str:
        recommendations = self.generate_recommendations()
        if output_path is None:
            output_path = Path(RESULT_FILE).parent / "strategy_signals.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(recommendations, f, ensure_ascii=False, indent=2, default=str)
        return str(output_path)


def run_strategy():
    engine = StrategyEngine()
    print("=" * 60)
    print("Stock5 交易策略引擎")
    print("=" * 60)
    print("\n📊 加载持仓和预测数据...")
    rec = engine.generate_recommendations()
    portfolio = rec["portfolio"]
    print(f"   总资金: {portfolio['total_cash']:,.0f} 元")
    print(f"   持仓市值: {portfolio['position_value']:,.0f} 元")
    print(f"   总市值: {portfolio['total_value']:,.0f} 元")
    print(f"   持仓数: {portfolio['holding_count']} 只")
    holdings = rec.get("holdings", [])
    sells = [h for h in holdings if h["action"].startswith("sell")]
    adds = [h for h in holdings if h["action"] == "add_position"]
    if sells:
        print(f"\n🛡️ 建议卖出/减仓: {len(sells)} 只")
        for h in sells[:5]:
            print(f"   {h['code']} {h['name']}: {h['reason']}")
    if adds:
        print(f"\n📈 建议加仓: {len(adds)} 只")
        for h in adds[:5]:
            print(f"   {h['code']} {h['name']}: {h['reason']}")
    buy_signals = rec.get("buy_signals", [])
    print(f"\n🎯 买入信号: {len(buy_signals)} 只 (可用仓位: {rec['summary']['slots_available']})")
    for b in buy_signals[:5]:
        print(f"   {b['code']} {b['name']}: 评分{b['score']}, "
              f"建议{b['suggested_shares']}股 (约{b['suggested_amount']:,.0f}元)")
    s = rec["summary"]
    print(f"\n📊 汇总:")
    print(f"   建议卖出金额: {s['total_sell_amount']:,.0f} 元")
    print(f"   建议买入金额: {s['total_buy_amount']:,.0f} 元")
    output_file = engine.export_signals()
    print(f"\n✅ 策略报告已导出到: {output_file}")
    return rec


if __name__ == "__main__":
    run_strategy()
