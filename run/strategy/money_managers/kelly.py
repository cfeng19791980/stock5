# -*- coding: utf-8 -*-
"""
Kelly 公式资金管理
根据胜率和赔率计算最优仓位
"""
from typing import Dict, Optional
import math


class KellyMM:
    """Kelly 公式资金管理"""
    
    def __init__(self, config: Dict = None):
        """
        Args:
            config: 配置字典
                - fraction: Kelly 分数 (0.25 = 半 Kelly)
                - max_position: 最大仓位上限
                - min_position: 最小仓位下限
        """
        self.config = config or {
            "fraction": 0.25,
            "max_position": 0.2,
            "min_position": 0.02,
        }
        
        self.fraction = self.config["fraction"]
        self.max_position = self.config["max_position"]
        self.min_position = self.config["min_position"]
    
    def calculate_kelly(self, 
                       win_rate: float, 
                       avg_win: float, 
                       avg_loss: float) -> float:
        """
        计算 Kelly 比例
        
        Args:
            win_rate: 胜率 (0-1)
            avg_win: 平均盈利比例 (如 0.15 = 15%)
            avg_loss: 平均亏损比例 (如 0.10 = 10%)
            
        Returns:
            float: Kelly 比例 (0-1)
        """
        if avg_loss <= 0:
            return 0
        
        # Kelly 公式: f* = (bp - q) / b
        # b = odds = avg_win / avg_loss
        # p = win_rate
        # q = 1 - p
        
        b = avg_win / avg_loss
        p = win_rate
        q = 1 - p
        
        kelly = (b * p - q) / b
        
        # 确保非负
        return max(0, kelly)
    
    def calculate_position(self,
                          total_cash: float,
                          win_rate: float = 0.5,
                          avg_win: float = 0.15,
                          avg_loss: float = 0.10) -> float:
        """
        计算 Kelly 仓位
        
        Args:
            total_cash: 总资金
            win_rate: 胜率估计
            avg_win: 平均盈利
            avg_loss: 平均亏损
            
        Returns:
            float: 建议买入金额
        """
        kelly_raw = self.calculate_kelly(win_rate, avg_win, avg_loss)
        
        # 应用分数
        kelly_adjusted = kelly_raw * self.fraction
        
        # 限制在 min/max 范围内
        kelly_clamped = max(self.min_position, 
                           min(self.max_position, kelly_adjusted))
        
        return total_cash * kelly_clamped
    
    def estimate_from_history(self, trades: list) -> Dict:
        """
        从历史交易记录估算 Kelly 参数
        
        Args:
            trades: 交易记录列表，每条包含 'pnl' (盈亏比例)
            
        Returns:
            包含 win_rate, avg_win, avg_loss, kelly 的字典
        """
        if not trades:
            return {"win_rate": 0.5, "avg_win": 0.15, "avg_loss": 0.10, "kelly": 0}
        
        wins = [t["pnl"] for t in trades if t.get("pnl", 0) > 0]
        losses = [abs(t["pnl"]) for t in trades if t.get("pnl", 0) < 0]
        
        win_rate = len(wins) / len(trades) if trades else 0.5
        avg_win = sum(wins) / len(wins) if wins else 0.15
        avg_loss = sum(losses) / len(losses) if losses else 0.10
        
        kelly = self.calculate_kelly(win_rate, avg_win, avg_loss)
        
        return {
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "kelly": kelly,
            "kelly_adjusted": kelly * self.fraction,
            "num_trades": len(trades),
            "num_wins": len(wins),
            "num_losses": len(losses),
        }
    
    def get_fraction_recommendation(self, kelly: float) -> str:
        """
        获取 Kelly 分数建议
        
        Args:
            kelly: 计算出的 Kelly 比例
            
        Returns:
            str: 建议文本
        """
        if kelly <= 0:
            return "不建议入场"
        elif kelly < 0.1:
            return "低仓位运行"
        elif kelly < 0.2:
            return "正常仓位"
        elif kelly < 0.3:
            return "较高仓位"
        else:
            return "高仓位运作，注意风险"


class AdaptiveKellyMM(KellyMM):
    """自适应 Kelly，根据市场环境动态调整"""
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        
        # 市场环境系数
        self.market_factors = {
            "bull": 1.2,      # 牛市增加仓位
            "normal": 1.0,   # 正常
            "bear": 0.6,     # 熊市降低仓位
            "volatile": 0.8, # ���波动市场
        }
        self.current_factor = 1.0
    
    def set_market_environment(self, env: str):
        """设置市场环境"""
        self.current_factor = self.market_factors.get(env, 1.0)
    
    def calculate_position(self,
                          total_cash: float,
                          win_rate: float = 0.5,
                          avg_win: float = 0.15,
                          avg_loss: float = 0.10) -> float:
        """计算考虑市场环境的仓位"""
        kelly_raw = self.calculate_kelly(win_rate, avg_win, avg_loss)
        
        # 应用市场环境系数
        kelly_adjusted = kelly_raw * self.fraction * self.current_factor
        
        # 限制范围
        kelly_clamped = max(self.min_position, 
                           min(self.max_position, kelly_adjusted))
        
        return total_cash * kelly_clamped