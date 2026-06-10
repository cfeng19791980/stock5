# -*- coding: utf-8 -*-
"""
Stock5 Phase 0: 修复 KDJ 计算
问题: 大跌时 RSV=0 导致 K/D/J=0 (因为 close==low_9)
修复: 当 high==low 时 RSV=50（中性值），平滑递归计算
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime

DB_PATH = r'E:\stock5\stocks.db'

def fix_kdj_for_stock(code, conn):
    """为单只股票修复 K/D/J 值"""
    df = pd.read_sql(f"""
        SELECT rowid, date, open, high, low, close 
        FROM daily_price WHERE code='{code}' 
        ORDER BY date
    """, conn)
    if len(df) < 9:
        return 0
    
    n = 9
    updates = []
    
    # 取前n-1天的max/min作为初始值
    high_prices = df['high'].values
    low_prices = df['low'].values
    close_prices = df['close'].values
    
    # 递给归 K/D
    k_prev = 50.0
    d_prev = 50.0
    
    for i in range(len(df)):
        start = max(0, i - n + 1)
        highest = np.max(high_prices[start:i+1])
        lowest = np.min(low_prices[start:i+1])
        close_i = close_prices[i]
        
        if highest != lowest:
            rsv = (close_i - lowest) / (highest - lowest) * 100
        else:
            rsv = 50.0  # 关键修复：当 high==low 时用中性值而不是 0
        
        # 递归计算
        k = 2/3 * k_prev + 1/3 * rsv
        d = 2/3 * d_prev + 1/3 * k
        j = 3 * k - 2 * d
        
        k_prev = k
        d_prev = d
        
        # 检查原值是否错误
        rowid = df.iloc[i]['rowid']
        updates.append((rowid, round(k, 2), round(d, 2), round(j, 2)))
    
    # 批量更新
    cursor = conn.cursor()
    cursor.executemany(
        "UPDATE daily_price SET k=?, d=?, j=? WHERE rowid=?",
        [(k, d, j, rid) for rid, k, d, j in updates]
    )
    conn.commit()
    return len(updates)


def main():
    conn = sqlite3.connect(DB_PATH)
    
    # 获取所有股票代码
    codes = pd.read_sql("SELECT DISTINCT code FROM daily_price", conn)['code'].tolist()
    print(f"股票总数: {len(codes)}")
    
    total = 0
    for code in codes:
        try:
            n = fix_kdj_for_stock(code, conn)
            total += n
            print(f"  {code}: {n}行 ✓")
        except Exception as e:
            print(f"  {code}: ✗ {e}")
    
    # 验证修复效果
    print(f"\n修复完成: {total}行")
    print("\n验证: K=0 的记录数")
    bad = conn.execute("SELECT COUNT(*) FROM daily_price WHERE k=0").fetchone()[0]
    print(f"  修复前应当有很多, 当前: {bad}条K=0")
    
    # 检查最近日期的K值是否合理
    print("\n最新数据K值分布:")
    rows = conn.execute("""
        SELECT code, date, k, d, j, close, low 
        FROM daily_price 
        WHERE date=(SELECT MAX(date) FROM daily_price)
        ORDER BY k
    """).fetchall()
    for r in rows[:5]:
        print(f"  {r[0]} {r[1]} K={r[2]:.1f} D={r[3]:.1f} J={r[4]:.1f} close={r[5]:.2f}")
    print("  ...")
    for r in rows[-5:]:
        print(f"  {r[0]} {r[1]} K={r[2]:.1f} D={r[3]:.1f} J={r[4]:.1f} close={r[5]:.2f}")
    
    conn.close()
    print("\nPhase 0 完成 ✓")


if __name__ == '__main__':
    main()
