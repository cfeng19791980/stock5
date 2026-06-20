# -*- coding: utf-8 -*-
"""
kline_patterns.py — K线形态识别模块
基于 TA-Lib 识别常用 K 线形态，作为模型特征输入

使用方式:
    from kline_patterns import add_kline_pattern_features
    feat = add_kline_pattern_features(feat, open_prices, high_prices, low_prices, close_prices)

支持的形态 (15个最常用):
    反转形态: 锤头、上吊线、吞没、晨星、暮星、十字星、射击之星、倒锤头
    持续形态: 三白兵、三乌鸦、上升三法、下降三法
    单根形态: 长脚十字、光头光脚、纺锤
"""

import numpy as np
import talib as tl

# 选用的15个最常用K线形态
PATTERN_CONFIG = {
    # === 反转形态 ===
    'cdl_hammer': {
        'func': tl.CDLHAMMER,
        'desc': '锤头 (底部反转)',
        'type': 'bullish_reversal'
    },
    'cdl_hanging_man': {
        'func': tl.CDLHANGINGMAN,
        'desc': '上吊线 (顶部反转)',
        'type': 'bearish_reversal'
    },
    'cdl_engulfing': {
        'func': tl.CDLENGULFING,
        'desc': '吞没形态',
        'type': 'reversal'
    },
    'cdl_morning_star': {
        'func': tl.CDLMORNINGSTAR,
        'desc': '晨星 (买入信号)',
        'type': 'bullish_reversal'
    },
    'cdl_evening_star': {
        'func': tl.CDLEVENINGSTAR,
        'desc': '暮星 (卖出信号)',
        'type': 'bearish_reversal'
    },
    'cdl_doji': {
        'func': tl.CDLDOJI,
        'desc': '十字星 (犹豫)',
        'type': 'neutral'
    },
    'cdl_shooting_star': {
        'func': tl.CDLSHOOTINGSTAR,
        'desc': '射击之星 (顶部反转)',
        'type': 'bearish_reversal'
    },
    'cdl_inverted_hammer': {
        'func': tl.CDLINVERTEDHAMMER,
        'desc': '倒锤头 (底部反转)',
        'type': 'bullish_reversal'
    },
    'cdl_piercing': {
        'func': tl.CDLPIERCING,
        'desc': '刺透形态 (买入)',
        'type': 'bullish_reversal'
    },
    'cdl_dark_cloud_cover': {
        'func': tl.CDLDARKCLOUDCOVER,
        'desc': '乌云盖顶 (卖出)',
        'type': 'bearish_reversal'
    },
    # === 持续形态 ===
    'cdl_3_white_soldiers': {
        'func': tl.CDL3WHITESOLDIERS,
        'desc': '三白兵 (强势)',
        'type': 'bullish_continuation'
    },
    'cdl_3_black_crows': {
        'func': tl.CDL3BLACKCROWS,
        'desc': '三乌鸦 (弱势)',
        'type': 'bearish_continuation'
    },
    'cdl_rising_3_methods': {
        'func': tl.CDLRISEFALL3METHODS,
        'desc': '上升三法 (中继)',
        'type': 'bullish_continuation'
    },
    # === 单根形态 ===
    'cdl_long_legged_doji': {
        'func': tl.CDLLONGLEGGEDDOJI,
        'desc': '长脚十字 (变盘)',
        'type': 'neutral'
    },
    'cdl_marubozu': {
        'func': tl.CDLMARUBOZU,
        'desc': '光头光脚 (趋势强)',
        'type': 'trend'
    },
}


def compute_kline_patterns(open_prices, high_prices, low_prices, close_prices):
    """
    计算所有K线形态，返回最近一根K线的形态信号字典
    
    Args:
        open_prices: 开盘价序列 (list or np.array, 最新在前)
        high_prices: 最高价序列
        low_prices: 最低价序列
        close_prices: 收盘价序列
    
    Returns:
        dict: {pattern_name: signal_value}
              signal_value: -100~100, 正=买入信号, 负=卖出信号, 0=无信号
    """
    # TA-Lib 需要 numpy array，且最新数据在最后
    open_arr = np.array(open_prices[::-1], dtype=float)
    high_arr = np.array(high_prices[::-1], dtype=float)
    low_arr = np.array(low_prices[::-1], dtype=float)
    close_arr = np.array(close_prices[::-1], dtype=float)
    
    result = {}
    for name, config in PATTERN_CONFIG.items():
        try:
            # TA-Lib 返回数组，最后一个值是最新K线的形态信号
            pattern_values = config['func'](open_arr, high_arr, low_arr, close_arr)
            if len(pattern_values) > 0:
                result[name] = int(pattern_values[-1])
            else:
                result[name] = 0
        except Exception:
            result[name] = 0
    
    return result


def add_kline_pattern_features(feat, open_prices, high_prices, low_prices, close_prices):
    """
    将K线形态信号添加到特征字典中
    
    Args:
        feat: 现有的特征字典 (会被修改)
        open_prices: 开盘价序列 (最新在前)
        high_prices: 最高价序列
        low_prices: 最低价序列
        close_prices: 收盘价序列
    
    Returns:
        dict: 添加了形态特征后的特征字典
    """
    patterns = compute_kline_patterns(open_prices, high_prices, low_prices, close_prices)
    
    # 添加每个形态的原始信号 (-100~100)
    for name, value in patterns.items():
        feat[name] = value
    
    # 添加聚合特征
    # 1. 总买入信号强度 (正信号之和)
    buy_signal = sum(v for v in patterns.values() if v > 0)
    feat['cdl_buy_strength'] = buy_signal
    
    # 2. 总卖出信号强度 (负信号绝对值之和)
    sell_signal = sum(abs(v) for v in patterns.values() if v < 0)
    feat['cdl_sell_strength'] = sell_signal
    
    # 3. 净信号强度 (买入-卖出)
    feat['cdl_net_signal'] = buy_signal - sell_signal
    
    # 4. 是否有强反转信号 (任一形态信号绝对值>=80)
    feat['cdl_strong_reversal'] = 1 if any(abs(v) >= 80 for v in patterns.values()) else 0
    
    # 5. 是否有十字星 (犹豫信号)
    feat['cdl_doji_present'] = 1 if patterns.get('cdl_doji', 0) != 0 else 0
    
    return feat


def get_pattern_description(pattern_name):
    """获取形态的中文描述"""
    config = PATTERN_CONFIG.get(pattern_name)
    if config:
        return config['desc']
    return pattern_name


def list_available_patterns():
    """列出所有可用的K线形态"""
    print("\n=== K线形态识别模块 ===")
    print(f"{'形态名称':<25} {'描述':<20} {'类型'}")
    print("-" * 65)
    for name, config in PATTERN_CONFIG.items():
        print(f"{name:<25} {config['desc']:<20} {config['type']}")
    print(f"\n共 {len(PATTERN_CONFIG)} 个形态")


if __name__ == "__main__":
    # 测试
    list_available_patterns()
    
    # 模拟数据测试
    np.random.seed(42)
    n = 30
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    open_p = close - np.random.randn(n) * 0.3
    high_p = np.maximum(close, open_p) + np.abs(np.random.randn(n)) * 0.2
    low_p = np.minimum(close, open_p) - np.abs(np.random.randn(n)) * 0.2
    
    feat = {}
    feat = add_kline_pattern_features(feat, open_p, high_p, low_p, close)
    
    print("\n=== 测试结果 ===")
    for k, v in feat.items():
        if v != 0:
            print(f"{k}: {v}")