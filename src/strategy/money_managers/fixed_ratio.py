# -*- coding: utf-8 -*-
"""
固定比例资金管理
根据信号强度固定比例分配仓位
"""
from typing import Dict, Optional


class FixedRatioMM:
    """固定比例资金管理"""
    
    def __init__(self, config: Dict = None):
        """
        Args:
            config: 配置字典
                - max_position_per_stock: 单只股票最大仓位比例
                - max_positions: 最大持仓股票数
                - min_cash_reserve: 最小现金储备比例
                - pyramiding: 是否允许金字塔加仓
                - pyramiding_step: 加仓步长
        """
        self.config = config or {
            "max_position_per_stock": 0.15,
            "max_positions": 5,
            "min_cash_reserve": 0.1,
            "pyramiding": True,
            "pyramiding_step": 0.05,
        }
        
        self.max_position_per_stock = self.config["max_position_per_stock"]
        self.max_positions = self.config["max_positions"]
        self.min_cash_reserve = self.config["min_cash_reserve"]
        self.pyramiding = self.config.get("pyramiding", True)
        self.pyramiding_step = self.config.get("pyramiding_step", 0.05)
    
    def calculate_position(self, 
                          signal_weight: float,
                          total_cash: float,
                          current_positions: int,
                          existing_position_value: float = 0) -> float:
        """
        计算实际仓位
        
        Args:
            signal_weight: 信号权重 (0-1)
            total_cash: 总资金
            current_positions: 当前持仓数
            existing_position_value: 现有持仓市值
            
        Returns:
            float: 建议买入金额
        """
        # 检查是否已达最大持仓数
        if current_positions >= self.max_positions:
            return 0
        
        # 计算可用资金
        available_cash = total_cash * (1 - self.min_cash_reserve)
        
        # 计算目标仓位
        target_position = available_cash * signal_weight
        
        # 检查是���超过单只股票最大仓位
        max_single = total_cash * self.max_position_per_stock
        
        # 如果已有持仓，考虑金字塔加仓
        if existing_position_value > 0 and self.pyramiding:
            # 金字塔加仓：每次增加固定步长
            if existing_position_value < max_single:
                additional = min(
                    target_position,
                    max_single - existing_position_value,
                    total_cash * self.pyramiding_step
                )
                return additional
            else:
                return 0
        else:
            return min(target_position, max_single)
    
    def get_position_shares(self, 
                           amount: float, 
                           price: float,
                           max_shares: int = 100) -> int:
        """
        计算可买入股数
        
        Args:
            amount: 可用金额
            price: 当前价格
            max_shares: 最大股数限制
            
        Returns:
            int: 可买入股数 (100股=1手)
        """
        if price <= 0:
            return 0
        
        shares = int(amount / price / 100) * 100  # 整手交易
        return min(shares, max_shares)
    
    def should_rebalance(self, 
                        current_positions: int,
                        total_value: float,
                        target_positions: int) -> bool:
        """
        是否需要调仓
        
        Args:
            current_positions: 当前持仓数
            total_value: 总市值
            target_positions: 目标持仓数
            
        Returns:
            bool: 是否需要调仓
        """
        # 持仓数超过目标，且当前有空仓余量
        if current_positions > target_positions:
            return True
        
        # 持仓数不足，且有新的买入信号
        if current_positions < target_positions:
            return True
        
        return False
    
    def get_cash_allocation(self, 
                           total_cash: float,
                           num_signals: int) -> Dict[str, float]:
        """
        计算现金分配方案
        
        Args:
            total_cash: 总资金
            num_signals: 信号数量
            
        Returns:
            分配方案字典
        """
        available = total_cash * (1 - self.min_cash_reserve)
        
        if num_signals == 0:
            return {"per_stock": 0, "total_allocated": 0}
        
        # 均匀分配给每只股票，但不超过单只最大仓位
        per_stock = available / min(num_signals, self.max_positions)
        max_single = total_cash * self.max_position_per_stock
        
        actual_per_stock = min(per_stock, max_single)
        
        return {
            "per_stock": actual_per_stock,
            "total_allocated": actual_per_stock * min(num_signals, self.max_positions),
            "cash_reserve": total_cash - actual_per_stock * min(num_signals, self.max_positions)
        }