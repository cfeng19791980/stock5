# -*- coding: utf-8 -*-
"""
补充 get_qwen_bull_bear 函数（基于技术指标的简化版本）
"""

import pandas as pd

def get_qwen_bull_bear(code, name, row_data):
    """
    基于技术指标的多空评分（简化版本）
    
    参数:
        code: 股票代码
        name: 股票名称
        row_data: 技术指标数据字典
        
    返回:
        {
            'score': int,      # 多空评分（-100到100）
            'bull': str,       # 看涨理由（最多25字符）
            'bear': str,       # 看跌理由（最多25字符）
            'confidence': int  # 置信度（0-100）
        }
    """
    
    # 提取关键技术指标
    pct_chg = row_data.get('pct_chg', 0)
    ma5_ratio = row_data.get('ma5_ratio', 1.0)
    ma10_ratio = row_data.get('ma10_ratio', 1.0)
    rsi6 = row_data.get('rsi6', 50)
    macd = row_data.get('macd', 0)
    volume_ratio = row_data.get('volume_ratio', 1.0)
    
    # 计算多空评分
    score = 0
    bull_reason = ""
    bear_reason = ""
    
    # 1. 趋势分析
    if ma5_ratio > 1.02 and ma10_ratio > 1.02:
        score += 30
        bull_reason = "均线多头排列"
    elif ma5_ratio < 0.98 and ma10_ratio < 0.98:
        score -= 30
        bear_reason = "均线空头排列"
    
    # 2. 涨跌幅分析
    if pct_chg > 3.0:
        score += 20
        bull_reason += "大涨"
    elif pct_chg < -3.0:
        score -= 20
        bear_reason += "大跌"
    
    # 3. RSI分析
    if rsi6 < 30:
        score += 15
        bull_reason += "RSI超卖"
    elif rsi6 > 70:
        score -= 15
        bear_reason += "RSI超买"
    
    # 4. MACD分析
    if macd > 0:
        score += 10
        bull_reason += "MACD金叉"
    elif macd < 0:
        score -= 10
        bear_reason += "MACD死叉"
    
    # 5. 量能分析
    if volume_ratio > 1.5:
        score += 5
        bull_reason += "放量"
    elif volume_ratio < 0.5:
        score -= 5
        bear_reason += "缩量"
    
    # 限制字符串长度
    bull_reason = bull_reason[:25] if bull_reason else "无明显看涨信号"
    bear_reason = bear_reason[:25] if bear_reason else "无明显看跌信号"
    
    # 计算置信度（基于信号数量）
    confidence = min(abs(score) + 20, 100)
    
    return {
        'score': score,
        'bull': bull_reason,
        'bear': bear_reason,
        'confidence': confidence,
        'method': 'tech_indicator_v1'
    }