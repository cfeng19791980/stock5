# -*- coding: utf-8 -*-
"""
测试 K线形态识别模块在 analyzer_v5 中的集成效果
"""
import sys
import os
import sqlite3
import pandas as pd
import numpy as np

# 添加 stock5 目录到路径
sys.path.insert(0, r'e:\stock5')

from kline_patterns import add_kline_pattern_features, compute_kline_patterns, list_available_patterns

DB_PATH = r'E:\stock5\stocks.db'

def test_kline_module():
    """测试 K线形态模块独立运行"""
    print("=" * 60)
    print("测试1: K线形态模块独立运行")
    print("=" * 60)
    
    # 模拟数据
    np.random.seed(42)
    n = 30
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    open_p = close - np.random.randn(n) * 0.3
    high_p = np.maximum(close, open_p) + np.abs(np.random.randn(n)) * 0.2
    low_p = np.minimum(close, open_p) - np.abs(np.random.randn(n)) * 0.2
    
    feat = {}
    feat = add_kline_pattern_features(feat, open_p, high_p, low_p, close)
    
    # 检查是否所有特征都存在
    expected_features = [
        'cdl_hammer', 'cdl_hanging_man', 'cdl_engulfing',
        'cdl_morning_star', 'cdl_evening_star', 'cdl_doji',
        'cdl_shooting_star', 'cdl_inverted_hammer', 'cdl_piercing',
        'cdl_dark_cloud_cover', 'cdl_3_white_soldiers', 'cdl_3_black_crows',
        'cdl_rising_3_methods', 'cdl_long_legged_doji', 'cdl_marubozu',
        'cdl_buy_strength', 'cdl_sell_strength', 'cdl_net_signal',
        'cdl_strong_reversal', 'cdl_doji_present'
    ]
    
    all_present = all(f in feat for f in expected_features)
    non_zero = {k: v for k, v in feat.items() if v != 0}
    
    print(f"  所有特征都存在: {'✅' if all_present else '❌'}")
    print(f"  特征总数: {len(feat)}")
    print(f"  非零信号: {len(non_zero)}个")
    for k, v in non_zero.items():
        print(f"    {k}: {v}")
    
    return all_present


def test_with_real_data():
    """从数据库取真实数据测试"""
    print("\n" + "=" * 60)
    print("测试2: 从数据库取真实数据测试")
    print("=" * 60)
    
    if not os.path.exists(DB_PATH):
        print(f"  ❌ 数据库不存在: {DB_PATH}")
        return False
    
    conn = sqlite3.connect(DB_PATH)
    
    # 取一只股票的最新60条日线数据
    code = '605196.SH'
    try:
        df = pd.read_sql(f"SELECT * FROM daily_price WHERE code='{code}' ORDER BY date DESC LIMIT 60", conn)
        print(f"  股票: {code}, 数据量: {len(df)}条")
        
        if len(df) < 20:
            print(f"  ❌ 数据不足20条")
            conn.close()
            return False
        
        # 提取OHLC数据 (最新在前)
        open_prices = df['open'].tolist()
        high_prices = df['high'].tolist()
        low_prices = df['low'].tolist()
        close_prices = df['close'].tolist()
        
        # 计算形态
        feat = {}
        feat = add_kline_pattern_features(feat, open_prices, high_prices, low_prices, close_prices)
        
        non_zero = {k: v for k, v in feat.items() if v != 0}
        print(f"  特征总数: {len(feat)}")
        print(f"  检测到的形态信号: {len(non_zero)}个")
        for k, v in non_zero.items():
            print(f"    {k}: {v}")
        
        # 显示最近5天的K线数据
        print(f"\n  最近5天K线数据:")
        print(f"  {'日期':<12} {'开盘':>8} {'最高':>8} {'最低':>8} {'收盘':>8} {'涨跌幅':>8}")
        for i in range(min(5, len(df))):
            row = df.iloc[i]
            print(f"  {str(row['date']):<12} {float(row['open']):>8.2f} {float(row['high']):>8.2f} {float(row['low']):>8.2f} {float(row['close']):>8.2f} {float(row['pct_chg']):>+7.2f}%")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"  ❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        conn.close()
        return False


def test_analyzer_import():
    """测试 analyzer_v5 是否能正常导入（不运行完整流程）"""
    print("\n" + "=" * 60)
    print("测试3: analyzer_v5 导入测试")
    print("=" * 60)
    
    try:
        # 只测试 extract_features_v6 函数是否能正常导入
        # 不运行完整 main() 避免训练
        from analyzer_v5 import extract_features_v6, DB_PATH
        
        conn = sqlite3.connect(DB_PATH)
        code = '605196.SH'
        df = pd.read_sql(f"SELECT * FROM daily_price WHERE code='{code}' ORDER BY date DESC LIMIT 60", conn)
        conn.close()
        
        if len(df) < 30:
            print(f"  ❌ 数据不足")
            return False
        
        # 反转数据 (extract_features_v6 需要最新在前的数据)
        df_rev = df.iloc[::-1].reset_index(drop=True)
        
        # 测试提取特征 (索引从后往前，取最新一条)
        feat = extract_features_v6(df_rev, len(df_rev) - 1)
        
        if feat is None:
            print(f"  ❌ 特征提取返回 None")
            return False
        
        # 检查是否包含K线形态特征
        cdl_features = [k for k in feat.keys() if k.startswith('cdl_')]
        print(f"  特征总数: {len(feat)}")
        print(f"  K线形态特征数: {len(cdl_features)}")
        print(f"  K线形态特征: {cdl_features}")
        
        # 显示非零的形态特征
        non_zero_cdl = {k: v for k, v in feat.items() if k.startswith('cdl_') and v != 0}
        if non_zero_cdl:
            print(f"  检测到的形态信号:")
            for k, v in non_zero_cdl.items():
                print(f"    {k}: {v}")
        else:
            print(f"  当前K线无显著形态信号 (正常)")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    print("K线形态集成测试\n")
    
    t1 = test_kline_module()
    t2 = test_with_real_data()
    t3 = test_analyzer_import()
    
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    print(f"  测试1 (模块独立运行): {'✅ 通过' if t1 else '❌ 失败'}")
    print(f"  测试2 (真实数据测试): {'✅ 通过' if t2 else '❌ 失败'}")
    print(f"  测试3 (analyzer集成): {'✅ 通过' if t3 else '❌ 失败'}")
    
    if all([t1, t2, t3]):
        print("\n  🎉 全部测试通过！K线形态集成成功")
    else:
        print("\n  ❌ 部分测试失败，请检查错误信息")