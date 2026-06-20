# -*- coding: utf-8 -*-
"""
止损风控管理器
"""
from typing import Dict, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class PositionInfo:
    """持仓信息"""
    code: str
    name: str
    entry_price: float
    entry_date: str
    quantity: int
    current_price: float = 0
    
    @property
    def market_value(self) -> float:
        return self.current_price * self.quantity
    
    @property
    def cost_value(self) -> float:
        return self.entry_price * self.quantity
    
    @property
    def pnl_ratio(self) -> float:
        if self.cost_value <= 0:
            return 0
        return (self.market_value - self.cost_value) / self.cost_value
    
    @property
    def pnl(self) -> float:
        return self.market_value - self.cost_value


class StopLossManager:
    """止损管理器"""
    
    def __init__(self, config: Dict = None):
        """
        Args:
            config: 配置字典
                - enabled: 是否启用
                - fixed_stop_loss: 固定止损比例
                - time_based_stop: 时间止损天数
        """
        self.config = config or {
            "enabled": True,
            "fixed_stop_loss": 0.07,
            "time_based_stop": 20,
        }
        
        self.enabled = self.config.get("enabled", True)
        self.fixed_stop_loss = self.config.get("fixed_stop_loss", 0.07)
        self.time_based_stop = self.config.get("time_based_stop", 20)
    
    def should_stop_loss(self, position: PositionInfo) -> tuple[bool, str]:
        """
        检查是否需要止损
        
        Args:
            position: 持仓信息
            
        Returns:
            (是否止损, 原因)
        """
        if not self.enabled:
            return False, "止损未启用"
        
        pnl_ratio = position.pnl_ratio
        
        # 固定止损检查
        if pnl_ratio <= -self.fixed_stop_loss:
            return True, f"触发固定止损 {self.fixed_stop_loss*100}%"
        
        # 时间止损检查
        if position.entry_date:
            try:
                entry_dt = datetime.strptime(position.entry_date, "%Y-%m-%d")
                days_held = (datetime.now() - entry_dt).days
                if days_held > self.time_based_stop and pnl_ratio < 0:
                    return True, f"持仓{days_held}天超时且亏损"
            except:
                pass
        
        return False, ""
    
    def get_stop_loss_price(self, entry_price: float, is_buy: bool = True) -> float:
        """
        计算止损价
        
        Args:
            entry_price: 入场价格
            is_buy: 是否是买入持仓
            
        Returns:
            止损价格
        """
        if is_buy:
            return entry_price * (1 - self.fixed_stop_loss)
        else:
            return entry_price * (1 + self.fixed_stop_loss)


class TrailingStopLoss(StopLossManager):
    """移动止损管理器"""
    
    def __init__(self, config: Dict = None):
        """
        Args:
            config: 配置字典
                - trailing_distance: 移动止损距离
                - activation_profit: 激活移动止损的盈利比例
        """
        super().__init__(config)
        
        self.trailing_distance = self.config.get("trailing_distance", 0.05)
        self.activation_profit = self.config.get("activation_profit", 0.03)
        
        # 记录最高价/最低价
        self.highest_price: Dict[str, float] = {}
        self.lowest_price: Dict[str, float] = {}
    
    def update_price(self, code: str, current_price: float):
        """更新价格记录"""
        if code not in self.highest_price:
            self.highest_price[code] = current_price
            self.lowest_price[code] = current_price
        else:
            self.highest_price[code] = max(self.highest_price[code], current_price)
            self.lowest_price[code] = min(self.lowest_price[code], current_price)
    
    def get_trailing_stop_price(self, code: str, entry_price: float) -> float:
        """
        计算移动止损价
        
        Args:
            code: 股票代码
            entry_price: 入场价格
            
        Returns:
            移动止损价格
        """
        highest = self.highest_price.get(code, entry_price)
        
        # 移动止损价 = 最高价 - 距离
        trailing_stop = highest * (1 - self.trailing_distance)
        
        # 不能低于入场价格
        return max(trailing_stop, entry_price * (1 + self.activation_profit))
    
    def should_stop_loss(self, position: PositionInfo) -> tuple[bool, str]:
        """
        检查是否需要止损（支持移动止损）
        """
        if not self.enabled:
            return False, "止损未启用"
        
        # 先检查固定止损
        fixed_result = super().should_stop_loss(position)
        if fixed_result[0]:
            return fixed_result
        
        # 更新最高价
        self.update_price(position.code, position.current_price)
        
        # 检查移动止损
        trailing_stop = self.get_trailing_stop_price(
            position.code, position.entry_price
        )
        
        if position.current_price <= trailing_stop:
            # 检查是否已激活（需要有一定盈利）
            if position.pnl_ratio >= self.activation_profit:
                return True, f"触发移动止损，距离{self.trailing_distance*100}%"
        
        return False, ""
    
    def reset_price(self, code: str):
        """重置价格记录（平仓后调用）"""
        if code in self.highest_price:
            del self.highest_price[code]
        if code in self.lowest_price:
            del self.lowest_price[code]


class TimeBasedStopLoss:
    """时间止损：持仓超过指定天数强制平仓"""
    
    def __init__(self, max_days: int = 20, min_profit: float = 0.02):
        """
        Args:
            max_days: 最大持仓天数
            min_profit: 最小盈利要求
        """
        self.max_days = max_days
        self.min_profit = min_profit
    
    def should_stop(self, position: PositionInfo) -> tuple[bool, str]:
        """检查是否需要时间止损"""
        if not position.entry_date:
            return False, ""
        
        try:
            entry_dt = datetime.strptime(position.entry_date, "%Y-%m-%d")
            days_held = (datetime.now() - entry_dt).days
            
            if days_held > self.max_days:
                if position.pnl_ratio >= self.min_profit:
                    return True, f"持仓{days_held}天，盈利{position.pnl_ratio*100:.1f}%，止盈"
                elif position.pnl_ratio >= 0:
                    return True, f"持仓{days_held}天，保本卖出"
                else:
                    return True, f"持仓{days_held}天，亏损{abs(position.pnl_ratio)*100:.1f}%，止损"
        except:
            pass
        
        return False, ""