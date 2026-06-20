# -*- coding: utf-8 -*-
"""
回测运行器
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import pandas as pd

from ..config_strategy import BACKTEST_CONFIG, RESULT_FILE
from ..signals.score_signal import ScoreSignal
from ..money_managers.fixed_ratio import FixedRatioMM
from ..risk_managers.stop_loss import StopLossManager
from ..risk_managers.take_profit import TakeProfitManager


@dataclass
class TradeRecord:
    """交易记录"""
    date: str
    code: str
    name: str
    action: str       # buy/sell
    price: float
    shares: int
    amount: float
    commission: float
    reason: str


@dataclass
class DailyRecord:
    """每日净值记录"""
    date: str
    cash: float
    position_value: float
    total_value: float
    positions: int


class BacktestRunner:
    """回测运行器"""
    
    def __init__(self, config: Dict = None):
        self.config = config or BACKTEST_CONFIG
        
        # 回测参数
        self.initial_cash = self.config.get("initial_cash", 1000000)
        self.commission_rate = self.config.get("commission_rate", 0.0003)
        self.stamp_tax_rate = self.config.get("stamp_tax_rate", 0.001)
        self.slippage = self.config.get("slippage", 0.001)
        
        # 初始化组件
        self.signal_generator = ScoreSignal()
        self.money_manager = FixedRatioMM()
        self.stop_loss_manager = StopLossManager()
        self.take_profit_manager = TakeProfitManager()
        
        # 回测状态
        self.cash = self.initial_cash
        self.positions: Dict[str, Dict] = {}  # {code: {shares, avg_cost, ...}}
        self.trade_history: List[TradeRecord] = []
        self.daily_records: List[DailyRecord] = []
        
        # 绩效统计
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
    
    def load_market_data(self, date: str) -> List[Dict]:
        """
        加载指定日期的市场数据
        实际应该从数据库读取，这里简化处理
        """
        # 读取分析结果
        try:
            with open(RESULT_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            stocks = data.get("stocks", [])
            # 简化：返回当天的股票数据
            return stocks
        except:
            return []
    
    def calculate_commission(self, amount: float, is_buy: bool = True) -> float:
        """计算佣金"""
        commission = amount * self.commission_rate
        # 最低佣金 5 元
        return max(commission, 5)
    
    def calculate_stamp_tax(self, amount: float) -> float:
        """计算印花税（仅卖出）"""
        return amount * self.stamp_tax_rate
    
    def apply_slippage(self, price: float, is_buy: bool = True) -> float:
        """应用滑点"""
        if is_buy:
            return price * (1 + self.slippage)
        else:
            return price * (1 - self.slippage)
    
    def execute_buy(self, 
                   date: str,
                   stock: Dict,
                   target_shares: int) -> bool:
        """执行买入"""
        if target_shares <= 0:
            return False
        
        code = stock.get("code")
        price = self.apply_slippage(stock.get("close", 0), is_buy=True)
        
        if price <= 0:
            return False
        
        amount = target_shares * price
        commission = self.calculate_commission(amount, is_buy=True)
        total_cost = amount + commission
        
        # 检查现金是否足够
        if total_cost > self.cash:
            # 现金不足，调整股数
            available = self.cash - commission
            target_shares = int(available / price / 100) * 100
            if target_shares <= 0:
                return False
            amount = target_shares * price
            total_cost = amount + commission
        
        # 执行买入
        self.cash -= total_cost
        
        if code in self.positions:
            # 金字塔加仓
            old_shares = self.positions[code]["shares"]
            old_cost = self.positions[code]["avg_cost"] * old_shares
            new_shares = old_shares + target_shares
            new_cost = (old_cost + amount) / new_shares
            self.positions[code] = {
                "shares": new_shares,
                "avg_cost": new_cost,
                "name": stock.get("name", ""),
                "entry_date": date,
            }
        else:
            # 新建持仓
            self.positions[code] = {
                "shares": target_shares,
                "avg_cost": price,
                "name": stock.get("name", ""),
                "entry_date": date,
            }
        
        # 记录交易
        self.trade_history.append(TradeRecord(
            date=date,
            code=code,
            name=stock.get("name", ""),
            action="buy",
            price=price,
            shares=target_shares,
            amount=amount,
            commission=commission,
            reason=f"买入信号，评分{stock.get('score', 0)}"
        ))
        
        self.total_trades += 1
        return True
    
    def execute_sell(self, 
                    date: str,
                    code: str,
                    shares: int,
                    price: float,
                    reason: str) -> bool:
        """执行卖出"""
        if code not in self.positions or shares <= 0:
            return False
        
        position = self.positions[code]
        
        price = self.apply_slippage(price, is_buy=False)
        amount = shares * price
        commission = self.calculate_commission(amount, is_buy=False)
        stamp_tax = self.calculate_stamp_tax(amount)
        total_proceeds = amount - commission - stamp_tax
        
        # 更新现金
        self.cash += total_proceeds
        
        # 更新持仓
        position["shares"] -= shares
        if position["shares"] <= 0:
            del self.positions[code]
        
        # 记录交易
        avg_cost = position.get("avg_cost", price)
        pnl = (price - avg_cost) * shares - commission - stamp_tax
        
        self.trade_history.append(TradeRecord(
            date=date,
            code=code,
            name=position.get("name", ""),
            action="sell",
            price=price,
            shares=shares,
            amount=amount,
            commission=commission + stamp_tax,
            reason=reason
        ))
        
        self.total_trades += 1
        if pnl > 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1
        
        return True
    
    def check_and_execute_stops(self, date: str, stock_data: Dict) -> List[str]:
        """检查并执行止损止盈"""
        executed = []
        
        for code, position in list(self.positions.items()):
            # 获取当前价格
            current_price = 0
            for s in stock_data:
                if s.get("code") == code:
                    current_price = s.get("close", 0)
                    break
            
            if current_price <= 0:
                continue
            
            entry_price = position["avg_cost"]
            shares = position["shares"]
            
            # 检查止损
            should_stop, reason = self.stop_loss_manager.should_stop_loss(
                type('obj', (object,), {
                    'code': code,
                    'name': position.get('name', ''),
                    'entry_price': entry_price,
                    'entry_date': position.get('entry_date', date),
                    'quantity': shares,
                    'current_price': current_price,
                })()
            )
            
            if should_stop:
                self.execute_sell(date, code, shares, current_price, reason)
                executed.append(f"{code} 止损: {reason}")
                continue
            
            # 检查止盈
            pnl_ratio = (current_price - entry_price) / entry_price
            exit_actions = self.take_profit_manager.get_exit_action(
                entry_price, current_price, shares, reset=False
            )
            
            for action in exit_actions:
                if action["shares"] > 0:
                    self.execute_sell(
                        date, code, action["shares"], 
                        current_price, action["reason"]
                    )
                    executed.append(f"{code} 止盈: {action['reason']}")
        
        return executed
    
    def run_backtest(self, 
                    start_date: str = None,
                    end_date: str = None,
                    output_file: str = None) -> Dict:
        """
        运行回测
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            output_file: 输出文件路径
            
        Returns:
            回测结果字典
        """
        print("=" * 60)
        print("Stock5 交易策略回测")
        print("=" * 60)
        
        print(f"\n📊 初始资金: {self.initial_cash:,.0f} 元")
        print(f"   佣金费率: {self.commission_rate*100:.2f}%")
        print(f"   印花税率: {self.stamp_tax_rate*100:.2f}%")
        print(f"   滑点: {self.slippage*100:.2f}%")
        
        # 加载市场数据
        stock_data = self.load_market_data(datetime.now().strftime("%Y-%m-%d"))
        print(f"\n📈 加载了 {len(stock_data)} 只股票数据")
        
        # 生成交易信号
        signals = []
        for stock in stock_data:
            score = stock.get("score", 0)
            signal, weight = self.signal_generator.get_signal_with_weight(score)
            
            if signal.value in ["强烈买入", "买入"]:
                signals.append({
                    **stock,
                    "signal": signal,
                    "weight": weight,
                })
        
        # 按评分排序，取前N只
        signals.sort(key=lambda x: x.get("score", 0), reverse=True)
        max_positions = self.money_manager.max_positions
        top_signals = signals[:max_positions]
        
        print(f"\n🎯 买入信号: {len(top_signals)} 只")
        for s in top_signals[:5]:
            print(f"   {s.get('code')} {s.get('name')}: 评分{s.get('score')}")
        
        # 模拟每日执行
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        # 检查持仓的止损止盈
        stops_executed = self.check_and_execute_stops(current_date, stock_data)
        if stops_executed:
            print(f"\n🛡️ 执行风控: {len(stops_executed)} 项")
            for s in stops_executed[:3]:
                print(f"   - {s}")
        
        # 买入新信号
        for signal in top_signals:
            code = signal.get("code")
            
            # 跳过已有持仓
            if code in self.positions:
                continue
            
            # 检查是否需要减仓
            if len(self.positions) >= max_positions:
                break
            
            # 计算买入股数
            signal_weight = signal.get("weight", 0.1)
            target_amount = self.money_manager.calculate_position(
                signal_weight,
                self.cash + sum(p["shares"] * p.get("avg_cost", 0) for p in self.positions.values()),
                len(self.positions),
            )
            
            price = signal.get("close", 0)
            if price > 0:
                target_shares = self.money_manager.get_position_shares(
                    target_amount, price
                )
                
                if target_shares > 0:
                    self.execute_buy(current_date, signal, target_shares)
        
        # 记录每日净值
        total_value = self.cash
        for code, pos in self.positions.items():
            # 查找当前价格
            for s in stock_data:
                if s.get("code") == code:
                    total_value += pos["shares"] * s.get("close", 0)
                    break
        
        self.daily_records.append(DailyRecord(
            date=current_date,
            cash=self.cash,
            position_value=total_value - self.cash,
            total_value=total_value,
            positions=len(self.positions)
        ))
        
        # 输出结果
        result = {
            "initial_cash": self.initial_cash,
            "final_cash": self.cash,
            "final_value": total_value,
            "total_return": (total_value - self.initial_cash) / self.initial_cash * 100,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.winning_trades / max(1, self.total_trades) * 100,
            "positions": len(self.positions),
            "trade_history": [
                {
                    "date": t.date,
                    "code": t.code,
                    "action": t.action,
                    "price": t.price,
                    "shares": t.shares,
                    "reason": t.reason,
                } for t in self.trade_history[-20:]
            ],
        }
        
        print(f"\n📊 回测结果:")
        print(f"   初始资金: {result['initial_cash']:,.0f} 元")
        print(f"   最终市值: {result['final_value']:,.0f} 元")
        print(f"   总收益率: {result['total_return']:.2f}%")
        print(f"   交易次数: {result['total_trades']}")
        print(f"   胜率: {result['win_rate']:.1f}%")
        print(f"   当前持仓: {result['positions']} 只")
        
        # 保存结果
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"\n✅ 结果已保存到: {output_file}")
        
        return result


def run_backtest():
    """运行回测"""
    runner = BacktestRunner()
    result = runner.run_backtest()
    return result


if __name__ == "__main__":
    run_backtest()