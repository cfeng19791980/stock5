# -*- coding: utf-8 -*-
"""
Stock5 v5修复方案 - KDJ计算 + 评分权重
功能：
  1. 修复KDJ计算逻辑（平滑处理）
  2. 调整评分权重（基于相关性分析）
  3. 回测验证修复效果

修复内容：
  - KDJ: 当前直接用RSV作为K值 → 改为平滑计算
  - 权重: RSI权重高但相关性低 → 改为K/D权重高
"""

import sys
sys.stdout.reconfigure(encoding='utf-8')

import sqlite3, pathlib
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

DB_PATH = str(pathlib.Path(__file__).parent / 'stocks.db')

# ========== 1. 修复KDJ计算 ==========

def calculate_kdj_correct(high_prices, low_prices, close_prices, n=9):
    """
    正确的KDJ计算（带平滑处理）
    
    Args:
        high_prices: 最高价数组（最新在前）
        low_prices: 最低价数组（最新在前）
        close_prices: 收盘价数组（最新在前）
        n: 周期（默认9）
    
    Returns:
        dict: {k, d, j}
    """
    if len(close_prices) < n:
        return {'k': 50, 'd': 50, 'j': 50}
    
    # 反转数组（从旧到新）
    high_prices = high_prices[::-1]
    low_prices = low_prices[::-1]
    close_prices = close_prices[::-1]
    
    # 计算RSV序列
    rsv_list = []
    for i in range(n-1, len(close_prices)):
        highest_n = np.max(high_prices[i-n+1:i+1])
        lowest_n = np.min(low_prices[i-n+1:i+1])
        close_n = close_prices[i]
        
        if highest_n != lowest_n:
            rsv = (close_n - lowest_n) / (highest_n - lowest_n) * 100
        else:
            rsv = 50
        rsv_list.append(rsv)
    
    if len(rsv_list) == 0:
        return {'k': 50, 'd': 50, 'j': 50}
    
    # 平滑计算K值
    # K = 2/3 × 前一日K + 1/3 × 今日RSV
    k_list = [50]  # 初始K值
    for rsv in rsv_list:
        k = 2/3 * k_list[-1] + 1/3 * rsv
        k_list.append(k)
    
    # 平滑计算D值
    # D = 2/3 × 前一日D + 1/3 × 今日K
    d_list = [50]  # 初始D值
    for k in k_list[1:]:  # 跳过初始值
        d = 2/3 * d_list[-1] + 1/3 * k
        d_list.append(d)
    
    # 计算J值
    # J = 3 × K - 2 × D
    if len(k_list) > 1 and len(d_list) > 1:
        k_current = k_list[-1]
        d_current = d_list[-1]
        j_current = 3 * k_current - 2 * d_current
    else:
        k_current = 50
        d_current = 50
        j_current = 50
    
    return {
        'k': round(k_current, 2),
        'd': round(d_current, 2),
        'j': round(j_current, 2)
    }

# ========== 2. 新评分权重 ==========

def calculate_score_new(feat):
    """
    新评分逻辑（基于相关性分析）
    
    相关性分析结果：
      - K/D值相关性: 0.41（最高） → 权重±15
      - MACD相关性: 0.18 → 权重±10
      - 涨跌幅相关性: 高 → 权重±10
      - 量比相关性: 中 → 权重±10
      - RSI相关性: -0.05（最低） → 权重±5
    """
    score = 50
    
    # 1. KDJ权重（相关性最高）±15
    k = feat.get('k', 50)
    d = feat.get('d', 50)
    j = feat.get('j', 50)
    
    # K值位置
    if k > 80:
        score -= 10  # 超买区域
    elif k < 20:
        score += 10  # 超卖区域
    elif k > 60:
        score += 5
    elif k < 40:
        score -= 5
    
    # K/D金叉死叉
    if k > d:
        kd_diff = k - d
        score += min(5, kd_diff)  # 金叉加分（最多+5）
    else:
        kd_diff = d - k
        score -= min(5, kd_diff)  # 死叉减分（最多-5）
    
    # J值极端情况
    if j > 100:
        score -= 3  # 过度超买
    elif j < 0:
        score += 3  # 过度超卖
    
    # 2. MACD权重 ±10
    macd = feat.get('macd', 0)
    macd_hist = feat.get('macd_hist', 0)
    
    if macd > 0:
        score += 5
    else:
        score -= 5
    
    if macd_hist > 0:
        score += 3  # MACD柱增长
    else:
        score -= 3
    
    # 3. 涨跌幅权重 ±10
    pct_chg = feat.get('pct_chg', 0)
    
    if pct_chg > 2:
        score += 8
    elif pct_chg > 1:
        score += 5
    elif pct_chg > 0:
        score += 2
    elif pct_chg < -2:
        score -= 8
    elif pct_chg < -1:
        score -= 5
    elif pct_chg < 0:
        score -= 2
    
    # 4. 量比权重 ±10
    volume_ratio = feat.get('volume_ratio', 1)
    
    if volume_ratio > 2:
        score += 8  # 大幅放量
    elif volume_ratio > 1.5:
        score += 5
    elif volume_ratio < 0.5:
        score -= 5  # 明显缩量
    elif volume_ratio < 0.8:
        score -= 3
    
    # 5. RSI权重 ±5（相关性最低）
    rsi6 = feat.get('rsi6', 50)
    
    if rsi6 > 80:
        score -= 3  # 超买
    elif rsi6 < 20:
        score += 3  # 超卖
    elif rsi6 > 60:
        score += 2
    elif rsi6 < 40:
        score -= 2
    
    # 限制范围
    score = max(0, min(100, score))
    
    return int(score)

# ========== 3. 修复历史数据 ==========

def fix_kdj_in_db():
    """修复数据库中的KDJ值"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("\n=== 修复历史KDJ数据 ===")
    
    # 获取所有股票代码
    codes = pd.read_sql_query("""
        SELECT DISTINCT code FROM minute_5_price
    """, conn)['code'].tolist()
    
    fixed_count = 0
    
    for code in codes:
        # 获取该股票的所有数据（按时间升序）
        df = pd.read_sql_query("""
            SELECT id, datetime, high, low, close
            FROM minute_5_price
            WHERE code = ?
            ORDER BY datetime ASC
        """, conn, params=(code,))
        
        if len(df) < 9:
            continue
        
        # 计算正确的KDJ
        high_prices = df['high'].values
        low_prices = df['low'].values
        close_prices = df['close'].values
        
        # 批量计算KDJ
        kdj_values = []
        for i in range(len(df)):
            if i < 8:  # 前8个数据无法计算
                kdj_values.append({'k': 50, 'd': 50, 'j': 50})
            else:
                # 取最近9个数据
                kdj = calculate_kdj_correct(
                    high_prices[max(0, i-20):i+1],
                    low_prices[max(0, i-20):i+1],
                    close_prices[max(0, i-20):i+1],
                    n=9
                )
                kdj_values.append(kdj)
        
        # 更新数据库
        for i, kdj in enumerate(kdj_values):
            row_id = df.iloc[i]['id']
            cursor.execute("""
                UPDATE minute_5_price
                SET k = ?, d = ?, j = ?
                WHERE id = ?
            """, (kdj['k'], kdj['d'], kdj['j'], row_id))
            fixed_count += 1
        
        print(f"  {code}: {len(df)}条数据已修复")
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ 共修复 {fixed_count} 条KDJ数据")
    return fixed_count

# ========== 4. 回测验证 ==========

def backtest_with_new_score():
    """使用新评分逻辑回测"""
    conn = sqlite3.connect(DB_PATH)
    
    print("\n=== 新评分逻辑回测 ===")
    
    # 获取有验证结果的预测
    predictions = pd.read_sql_query("""
        SELECT id, stock_code, predict_datetime, predict_action, predict_score, predict_price,
               actual_result, actual_return
        FROM prediction_logs_v5
        WHERE predict_datetime IS NOT NULL AND actual_result IS NOT NULL
    """, conn)
    
    print(f"样本量: {len(predictions)} 条")
    
    # 对每个预测重新计算评分
    results = []
    
    for pred in predictions.itertuples():
        code = pred.stock_code
        predict_time = pred.predict_datetime
        
        # 获取预测时刻的特征
        m5_data = pd.read_sql_query("""
            SELECT close, pct_chg, rsi6, macd, macd_hist, k, d, j, volume, amount
            FROM minute_5_price
            WHERE code = ? AND datetime = ?
            LIMIT 1
        """, conn, params=(code, predict_time))
        
        if len(m5_data) == 0:
            continue
        
        # 构建特征字典（使用修复后的KDJ）
        feat = {
            'pct_chg': m5_data.iloc[0]['pct_chg'],
            'rsi6': m5_data.iloc[0]['rsi6'],
            'macd': m5_data.iloc[0]['macd'],
            'macd_hist': m5_data.iloc[0]['macd_hist'],
            'k': m5_data.iloc[0]['k'],
            'd': m5_data.iloc[0]['d'],
            'j': m5_data.iloc[0]['j'],
            'volume_ratio': 1  # 简化处理
        }
        
        # 计算新评分
        new_score = calculate_score_new(feat)
        actual_return = pred.actual_return
        
        results.append({
            'old_score': pred.predict_score,
            'new_score': new_score,
            'actual_return': actual_return,
            'action': pred.predict_action
        })
    
    conn.close()
    
    if len(results) == 0:
        print("无有效回测样本")
        return
    
    df_results = pd.DataFrame(results)
    
    print("\n=== 旧评分 vs 新评分对比 ===")
    
    # 旧评分准确率
    print("\n旧评分评分区间收益:")
    for low, high in [(0, 40), (40, 60), (60, 80), (80, 100)]:
        subset = df_results[(df_results['old_score'] >= low) & (df_results['old_score'] < high)]
        if len(subset) > 0:
            avg_ret = subset['actual_return'].mean()
            print(f"  [{low}-{high}]: {len(subset)}条, 平均收益 {avg_ret:+.2f}%")
    
    # 新评分准确率
    print("\n新评分评分区间收益:")
    for low, high in [(0, 40), (40, 60), (60, 80), (80, 100)]:
        subset = df_results[(df_results['new_score'] >= low) & (df_results['new_score'] < high)]
        if len(subset) > 0:
            avg_ret = subset['actual_return'].mean()
            print(f"  [{low}-{high}]: {len(subset)}条, 平均收益 {avg_ret:+.2f}%")
    
    # 评分与收益相关性
    old_corr = df_results['old_score'].corr(df_results['actual_return'])
    new_corr = df_results['new_score'].corr(df_results['actual_return'])
    
    print(f"\n评分-收益相关性:")
    print(f"  旧评分: {old_corr:.3f}")
    print(f"  新评分: {new_corr:.3f}")
    
    if new_corr > old_corr:
        print(f"  ✅ 新评分相关性提升 {(new_corr - old_corr)/abs(old_corr)*100:.1f}%")
    else:
        print(f"  ⚠️ 新评分相关性下降")
    
    return df_results

# ========== 5. 主流程 ==========

def main():
    """主修复流程"""
    print("=" * 70)
    print("Stock5 v5 修复方案")
    print("=" * 70)
    
    # 1. 修复KDJ数据
    print("\n[1] 修复KDJ计算")
    fixed = fix_kdj_in_db()
    
    # 2. 回测验证
    print("\n[2] 回测验证效果")
    results = backtest_with_new_score()
    
    print("\n" + "=" * 70)
    print("修复完成！")
    print("=" * 70)

if __name__ == '__main__':
    main()