# -*- coding: utf-8 -*-
"""
评分信号指示器
将分析模型的评分转换为交易信号
"""
from typing import Dict, List
from enum import Enum

from ..config_strategy import SCORE_THRESHOLDS


class SignalType(Enum):
    """交易信号类型"""
    STRONG_BUY = "强烈买入"
    BUY = "买入"
    HOLD = "持有"
    SELL = "卖出"
    STRONG_SELL = "强烈卖出"
    NONE = "无信号"


class ScoreSignal:
    """基于评分的信号指示器"""
    
    def __init__(self, config: Dict = None):
        self.config = config or SCORE_THRESHOLDS
    
    def get_signal(self, score: float) -> SignalType:
        """
        根据评分获取交易信号
        
        Args:
            score: 分析模型评分 (0-100)
            
        Returns:
            SignalType: 交易信号
        """
        if score >= self.config.get("strong_buy", 75):
            return SignalType.STRONG_BUY
        elif score >= self.config.get("buy", 60):
            return SignalType.BUY
        elif score >= self.config.get("hold", 40):
            return SignalType.HOLD
        elif score >= self.config.get("sell", 30):
            return SignalType.SELL
        else:
            return SignalType.STRONG_SELL
    
    def get_signal_with_weight(self, score: float) -> tuple[SignalType, float]:
        """
        获取信号和对应的仓位权重
        
        Args:
            score: 分析模型评分
            
        Returns:
            (SignalType, float): 信号类型和仓位权重 (0-1)
        """
        signal = self.get_signal(score)
        
        # 仓位权重映射
        weight_map = {
            SignalType.STRONG_BUY: 0.15,  # 15%
            SignalType.BUY: 0.10,         # 10%
            SignalType.HOLD: 0.05,        # 5%
            SignalType.SELL: 0.0,         # 0%
            SignalType.STRONG_SELL: 0.0, # 0%
            SignalType.NONE: 0.0,
        }
        
        weight = weight_map.get(signal, 0.0)
        return signal, weight
    
    def filter_signals(self, signals: List[Dict], 
                       min_score: float = 0,
                       signal_type: SignalType = None) -> List[Dict]:
        """
        过滤信号列表
        
        Args:
            signals: 信号列表
            min_score: 最小评分
            signal_type: 信号类型过滤
            
        Returns:
            过滤后的信号列表
        """
        filtered = []
        
        for s in signals:
            score = s.get("score", 0)
            if score < min_score:
                continue
            
            signal = self.get_signal(score)
            
            if signal_type and signal != signal_type:
                continue
            
            s["signal"] = signal.value
            filtered.append(s)
        
        # 按评分排序
        filtered.sort(key=lambda x: x.get("score", 0), reverse=True)
        return filtered
    
    def generate_recommendation(self, stock: Dict) -> Dict:
        """
        生成单只股票的买卖建议
        
        Args:
            stock: 股票数据字典，需包含 score, close, pct_chg 等字段
            
        Returns:
            包含信号和建议的字典
        """
        score = stock.get("score", 0)
        signal, weight = self.get_signal_with_weight(score)
        
        recommendation = {
            "code": stock.get("code", ""),
            "name": stock.get("name", ""),
            "score": score,
            "price": stock.get("close", 0),
            "pct_chg": stock.get("pct_chg", 0),
            "signal": signal.value,
            "position_weight": weight,
            "reason": self._generate_reason(signal, score, stock),
        }
        
        # 添加风控价格
        price = stock.get("close", 0)
        if price > 0 and signal in [SignalType.BUY, SignalType.STRONG_BUY]:
            recommendation["stop_loss"] = round(price * 0.93, 2)   # 7% 止损
            recommendation["take_profit"] = round(price * 1.15, 2) # 15% 止盈
        
        return recommendation
    
    def _generate_reason(self, signal: SignalType, score: float, stock: Dict) -> str:
        """生成建议原因"""
        reasons = {
            SignalType.STRONG_BUY: f"评分 {score}，强烈买入信号",
            SignalType.BUY: f"评分 {score}，买入信号",
            SignalType.HOLD: f"评分 {score}，持有观望",
            SignalType.SELL: f"评分 {score}，卖出信号",
            SignalType.STRONG_SELL: f"评分 {score}，强烈卖出",
            SignalType.NONE: "无有效信号",
        }
        
        base_reason = reasons.get(signal, "未知信号")
        
        # 添加附加信息
        if stock.get("buy_signal"):
            base_reason += "，模型给出买入信号"
        if stock.get("advice"):
            base_reason += f"，模型建议{stock['advice']}"
            
        return base_reason