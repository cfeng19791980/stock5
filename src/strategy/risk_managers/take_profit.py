# -*- coding: utf-8 -*-
"""
止盈风控管理器
"""
from typing import Dict, List, Tuple
from dataclasses import dataclass


@dataclass
class TakeProfitLevel:
    """止盈档位"""
    threshold: float      # 涨跌幅阈值 (如 0.08 = 8%)
    exit_ratio: float     # 卖出比例 (如 0.5 = 50%)
    reached: bool = False # 是否已触发


class TakeProfitManager:
    """止盈管理器"""
    
    def __init__(self, config: Dict = None):
        """
        Args:
            config: 配置字典
                - enabled: 是否启用
                - levels: 止盈档位列表 [{"threshold": 0.08, "exit_ratio": 0.5}, ...]
        """
        self.config = config or {
            "enabled": True,
            "levels": [
                {"threshold": 0.08, "exit_ratio": 0.5},
                {"threshold": 0.15, "exit_ratio": 0.7},
                {"threshold": 0.25, "exit_ratio": 1.0},
            ]
        }
        
        self.enabled = self.config.get("enabled", True)
        
        # 初始化止盈档位
        levels_config = self.config.get("levels", [])
        self.levels = [
            TakeProfitLevel(
                threshold=l["threshold"],
                exit_ratio=l["exit_ratio"]
            ) for l in levels_config
        ]
        
        # 按阈值排序（从低到高）
        self.levels.sort(key=lambda x: x.threshold)
    
    def check_take_profit(self, 
                         entry_price: float, 
                         current_price: float,
                         reset: bool = False) -> List[Tuple[float, float, bool]]:
        """
        检查是否触发止盈
        
        Args:
            entry_price: 入场价格
            current_price: 当前价格
            reset: 是否重置（每次调用前重置）
            
        Returns:
            [(threshold, exit_ratio, reached), ...] 各档位是否触发
        """
        if not self.enabled:
            return []
        
        if reset:
            for level in self.levels:
                level.reached = False
        
        pnl_ratio = (current_price - entry_price) / entry_price
        
        results = []
        for level in self.levels:
            if pnl_ratio >= level.threshold:
                results.append((level.threshold, level.exit_ratio, True))
                level.reached = True
            else:
                results.append((level.threshold, level.exit_ratio, False))
        
        return results
    
    def get_exit_action(self,
                       entry_price: float,
                       current_price: float,
                       total_shares: int,
                       reset: bool = False) -> List[Dict]:
        """
        获取止盈动作
        
        Args:
            entry_price: 入场价格
            current_price: 当前价格
            total_shares: 总股数
            reset: 是否重置
            
        Returns:
            [{"shares": 股数, "price": 价格, "reason": 原因}, ...]
        """
        if not self.enabled:
            return []
        
        pnl_ratio = (current_price - entry_price) / entry_price
        
        actions = []
        remaining_ratio = 1.0
        
        for level in self.levels:
            if level.reached and reset:
                level.reached = False
                continue
                
            if pnl_ratio >= level.threshold and not level.reached:
                # 计算本次卖出的股数
                exit_ratio = level.exit_ratio
                shares_to_sell = int(total_shares * exit_ratio / 100) * 100
                
                # 确保不超过剩余股数
                max_possible = int(total_shares * remaining_ratio / 100) * 100
                shares_to_sell = min(shares_to_sell, max_possible)
                
                if shares_to_sell > 0:
                    actions.append({
                        "shares": shares_to_sell,
                        "price": current_price,
                        "reason": f"涨{level.threshold*100:.0f}%止盈，卖出{level.exit_ratio*100:.0f}%"
                    })
                    
                    remaining_ratio -= level.exit_ratio
                    level.reached = True
                
                if remaining_ratio <= 0:
                    break
        
        return actions
    
    def get_next_take_profit_threshold(self, 
                                      entry_price: float,
                                      current_price: float) -> float:
        """
        获取下一个止盈档位阈值
        
        Args:
            entry_price: 入场价格
            current_price: 当前价格
            
        Returns:
            下一个止盈阈值，如果没有则返回 -1
        """
        pnl_ratio = (current_price - entry_price) / entry_price
        
        for level in self.levels:
            if pnl_ratio < level.threshold:
                return level.threshold
        
        return -1  # 已达到最高档
    
    def estimate_exit_value(self,
                           entry_price: float,
                           current_price: float,
                           total_shares: int) -> Dict:
        """
        预估各档位止盈后的市值
        
        Returns:
            {"total": 总市值, "levels": [(threshold, value), ...]}
        """
        pnl_ratio = (current_price - entry_price) / entry_price
        total_value = current_price * total_shares
        
        level_values = []
        remaining_shares = total_shares
        total_exit_value = 0
        
        for level in self.levels:
            if pnl_ratio >= level.threshold:
                exit_shares = int(remaining_shares * level.exit_ratio)
                exit_value = exit_shares * current_price
                total_exit_value += exit_value
                remaining_shares -= exit_shares
                
                level_values.append((
                    level.threshold,
                    total_exit_value + remaining_shares * current_price
                ))
        
        return {
            "total": total_value,
            "projected_levels": level_values,
            "remaining_shares": remaining_shares,
            "remaining_value": remaining_shares * current_price,
        }


class TrailingTakeProfit:
    """移动止盈：随着价格上涨不断提高止盈线"""
    
    def __init__(self, 
                 min_profit: float = 0.05,
                 trailing_distance: float = 0.03):
        """
        Args:
            min_profit: 最小激活盈利比例
            trailing_distance: 移动距离比例
        """
        self.min_profit = min_profit
        self.trailing_distance = trailing_distance
        
        self.highest_price: Dict[str, float] = {}
    
    def update_price(self, code: str, current_price: float):
        """更新最高价"""
        if code not in self.highest_price:
            self.highest_price[code] = current_price
        else:
            self.highest_price[code] = max(self.highest_price[code], current_price)
    
    def get_trailing_stop(self, code: str, entry_price: float) -> float:
        """计算移动止盈价格"""
        highest = self.highest_price.get(code, entry_price)
        
        # 移动止盈价 = 最高价 * (1 - 距离)
        trailing_stop = highest * (1 - self.trailing_distance)
        
        # 不能低于入场价 + 最小盈利
        min_acceptable = entry_price * (1 + self.min_profit)
        
        return max(trailing_stop, min_acceptable)
    
    def should_take_profit(self, code: str, current_price: float) -> bool:
        """检查是否触发移动止盈"""
        highest = self.highest_price.get(code, current_price)
        
        if highest is None:
            return False
        
        trailing_stop = highest * (1 - self.trailing_distance)
        
        return current_price <= trailing_stop
    
    def reset(self, code: str):
        """重置（平仓后）"""
        if code in self.highest_price:
            del self.highest_price[code]