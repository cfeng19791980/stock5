# -*- coding: utf-8 -*-
"""
验证历史预测并更新 prediction_logs_v5
功能：
  1. 对 pending 状态的预测，计算次日实际涨跌
  2. 更新 actual_result 和 actual_return
  3. 生成验证报告
"""

import sqlite3
import pandas as pd
from datetime import datetime, timedelta

DB_PATH = r'E:\stock5\stocks.db'

def verify_predictions():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("=" * 50)
    print("预测验证 - 更新历史预测结果")
    print("=" * 50)
    
    # 获取 pending 的预测
    cursor.execute("""
        SELECT id, stock_code, predict_date, predict_action, predict_price
        FROM prediction_logs_v5 
        WHERE actual_result = 'pending'
        ORDER BY predict_date DESC
    """)
    pending = cursor.fetchall()
    print(f"\n待验证预测: {len(pending)} 条")
    
    verified_count = 0
    correct_count = 0
    
    for log_id, code, predict_date, action, predict_price in pending:
        # 查找预测日期当天的日线数据
        cursor.execute("""
            SELECT close, pct_chg 
            FROM daily_price 
            WHERE code = ? AND date = ?
            LIMIT 1
        """, (code, predict_date))
        
        current = cursor.fetchone()
        
        if current:
            current_close = current[0]
            current_pct = current[1] if current[1] else 0
            
            # 查找下一个交易日
            cursor.execute("""
                SELECT close, pct_chg, date
                FROM daily_price 
                WHERE code = ? AND date > ?
                ORDER BY date ASC
                LIMIT 1
            """, (code, predict_date))
            
            next_day = cursor.fetchone()
            
            if next_day:
                next_close = next_day[0]
                next_pct = next_day[1] if next_day[1] else 0
                
                # 判断实际结果
                if next_pct >= 3:
                    actual_result = 'up_3pct'
                elif next_pct >= 1:
                    actual_result = 'up_1pct'
                elif next_pct >= 0:
                    actual_result = 'up'
                elif next_pct >= -1:
                    actual_result = 'down'
                elif next_pct >= -3:
                    actual_result = 'down_1pct'
                else:
                    actual_result = 'down_3pct'
                
                # 判断预测是否正确
                is_correct = False
                if action == 'buy' and next_pct >= 0:
                    is_correct = True
                elif action == 'sell' and next_pct <= 0:
                    is_correct = True
                elif action == 'hold' and abs(next_pct) <= 1.5:
                    is_correct = True
                
                if is_correct:
                    correct_count += 1
                
                # 更新日志
                cursor.execute("""
                    UPDATE prediction_logs_v5 
                    SET actual_result = ?, actual_return = ?, feedback_time = ?
                    WHERE id = ?
                """, (actual_result, next_pct, datetime.now().isoformat(), log_id))
                
                verified_count += 1
    
    conn.commit()
    
    print(f"\n验证完成: {verified_count} 条")
    print(f"预测正确: {correct_count} 条 ({correct_count/verified_count*100:.1f}%)" if verified_count else "")
    
    # 统计各操作准确率
    print("\n各操作准确率:")
    for action in ['buy', 'hold', 'sell']:
        cursor.execute("""
            SELECT COUNT(*) FROM prediction_logs_v5 
            WHERE predict_action=? AND actual_result != 'pending'
        """, (action,))
        total = cursor.fetchone()[0]
        
        if action == 'buy':
            cursor.execute("""
                SELECT COUNT(*) FROM prediction_logs_v5 
                WHERE predict_action='buy' AND actual_result IN ('up', 'up_1pct')
            """)
            correct = cursor.fetchone()[0]
        elif action == 'sell':
            cursor.execute("""
                SELECT COUNT(*) FROM prediction_logs_v5 
                WHERE predict_action='sell' AND actual_result IN ('down', 'down_1pct')
            """)
            correct = cursor.fetchone()[0]
        else:
            cursor.execute("""
                SELECT COUNT(*) FROM prediction_logs_v5 
                WHERE predict_action='hold' AND actual_result IN ('up', 'down')
            """)
            correct = cursor.fetchone()[0]
        
        if total > 0:
            print(f"  {action}: {correct}/{total} ({correct/total*100:.1f}%)")
    
    conn.close()
    return verified_count, correct_count

if __name__ == "__main__":
    verify_predictions()