# -*- coding: utf-8 -*-
"""
5分钟预测回测方案
功能：验证模型在5分钟时间框架下的预测准确率
"""
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

DB_PATH = r'E:\stock5\stocks.db'

def run_backtest():
    conn = sqlite3.connect(DB_PATH)
    
    print("=" * 60)
    print("5分钟预测回测")
    print("=" * 60)
    
    # 初始化变量（防止UnboundLocalError）
    verified_count = 0
    correct_count = 0
    total_return = 0
    
    # 1. 获取预测日志
    df_logs = pd.read_sql("""
        SELECT id, stock_code, predict_date, predict_datetime, predict_action, predict_price, 
               actual_result, actual_return, predict_score
        FROM prediction_logs_v5
        ORDER BY predict_date
    """, conn)
    
    print(f"\n[1] 预测日志: {len(df_logs)} 条")
    
    # 2. 对未验证的预测进行回测
    pending = df_logs[df_logs['actual_result'] == 'pending']
    verified = df_logs[df_logs['actual_result'] != 'pending']
    
    print(f"    待验证: {len(pending)}")
    print(f"    已验证: {len(verified)}")
    
    # 3. 对待验证的预测进行验证
    if len(pending) > 0:
        print("\n[2] 验证待处理预测...")
        
        verified_count = 0
        correct_count = 0
        total_return = 0
        
        for idx, row in pending.iterrows():
            code = row['stock_code']
            # 处理 code 格式不一致
            code_full = code  # 原格式 '605196.SH'
            code_short = code.split('.')[0] if '.' in code else code  # '605196'
            
            predict_time = row['predict_datetime'] or row['predict_date']
            action = row['predict_action']
            predict_price = row['predict_price']
            log_id = row['id']
            
            # 有精确时间 -> 用5分钟数据验证
            pdt = row['predict_datetime']
            pdt_str = str(pdt) if pdt and not pd.isna(pdt) else ''
            
            if len(pdt_str) > 10:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT datetime, close, pct_chg, amount
                    FROM minute_5_price
                    WHERE code = ? AND datetime >= ?
                    ORDER BY datetime ASC
                    LIMIT 3
                """, (code_short, predict_time))  # 用无后缀格式
                
                rows = cursor.fetchall()
                
                if len(rows) >= 2:
                    current_close = rows[0][1]
                    next_close = rows[1][1]
                    next_pct = rows[1][2]
                    
                    if predict_price and predict_price > 0:
                        actual_return = (next_close - predict_price) / predict_price * 100
                    else:
                        actual_return = next_pct
                    
                    # 判断结果
                    if actual_return >= 1:
                        actual_result = 'up_1pct'
                    elif actual_return >= 0.3:
                        actual_result = 'up'
                    elif actual_return >= -0.3:
                        actual_result = 'flat'
                    elif actual_return >= -1:
                        actual_result = 'down'
                    else:
                        actual_result = 'down_1pct'
                    
                    # 判断正确性
                    is_correct = False
                    if action == '强烈买入' and actual_return >= 0.3:
                        is_correct = True
                    elif action == '持有观望' and -0.3 <= actual_return <= 0.3:
                        is_correct = True
                    elif action == '反向买入机会' and actual_return >= 0.5:
                        is_correct = True
                    
                    if is_correct:
                        correct_count += 1
                    total_return += actual_return
                    verified_count += 1
                    
                    cursor.execute("""
                        UPDATE prediction_logs_v5
                        SET actual_result = ?, actual_return = ?, feedback_time = ?
                        WHERE id = ?
                    """, (actual_result, round(actual_return, 4), 
                          datetime.now().isoformat(), log_id))
            else:
                # 无精确时间 -> 用日线验证（次日涨跌）
                cursor = conn.cursor()
                # predict_time 可能是 NaN，用 predict_date
                date_str = row['predict_date'] if row['predict_date'] and not pd.isna(row['predict_date']) else ''
                if not date_str:
                    continue
                    
                cursor.execute("""
                    SELECT close, pct_chg, date
                    FROM daily_price
                    WHERE code = ? AND date >= ?
                    ORDER BY date ASC
                    LIMIT 2
                """, (code_full, date_str[:10]))  # 用完整格式
                
                rows = cursor.fetchall()
                
                if len(rows) >= 2:
                    next_pct = rows[1][1]
                    actual_return = next_pct
                    
                    if actual_return >= 1:
                        actual_result = 'up_1pct'
                    elif actual_return >= 0:
                        actual_result = 'up'
                    elif actual_return >= -1:
                        actual_result = 'down'
                    else:
                        actual_result = 'down_1pct'
                    
                    is_correct = False
                    if '买入' in action and actual_return >= 0:
                        is_correct = True
                    elif action == '持有观望' and -1 <= actual_return <= 1:
                        is_correct = True
                    
                    if is_correct:
                        correct_count += 1
                    total_return += actual_return
                    verified_count += 1
                    
                    cursor.execute("""
                        UPDATE prediction_logs_v5
                        SET actual_result = ?, actual_return = ?, feedback_time = ?
                        WHERE id = ?
                    """, (actual_result, round(actual_return, 4), 
                          datetime.now().isoformat(), log_id))
        
        conn.commit()
        print(f"    本次验证: {verified_count} 条")
        print(f"    正确预测: {correct_count} 条")
        if verified_count > 0:
            print(f"    准确率: {correct_count/verified_count*100:.1f}%")
            print(f"    平均收益: {total_return/verified_count:.2f}%")
    
    # 4. 统计已验证数据
    stats_by_action = {}
    print("\n[3] 已验证数据统计:")
    
    # 按预测类型统计
    for action in verified['predict_action'].unique():
        subset = verified[verified['predict_action'] == action]
        correct = subset[subset['actual_result'].isin(['up', 'up_1pct', 'flat'])].shape[0]
        total = len(subset)
        avg_return = subset['actual_return'].mean()
        
        stats_by_action[action] = {
            'total': total,
            'correct': correct,
            'avg_return': avg_return
        }
        
        print(f"    {action}:")
        print(f"      总数: {total}")
        print(f"      正确: {correct} ({correct/total*100:.1f}%)")
        print(f"      平均收益: {avg_return:.2f}%")
    
    # 5. 模拟回测收益
    print("\n[4] 模拟交易回测:")
    
    # 只交易强烈买入信号
    strong_buy = verified[verified['predict_action'] == '强烈买入']
    if len(strong_buy) > 0:
        buy_returns = strong_buy['actual_return'].sum()
        print(f"    累计收益(强烈买入): {buy_returns:.2f}%")
        print(f"    交易次数: {len(strong_buy)}")
    
    # 反向买入机会
    reverse_buy = verified[verified['predict_action'] == '反向买入机会']
    if len(reverse_buy) > 0:
        rev_returns = reverse_buy['actual_return'].sum()
        print(f"    累计收益(反向买入): {rev_returns:.2f}%")
        print(f"    交易次数: {len(reverse_buy)}")
    
    conn.close()
    print("\n" + "=" * 60)
    
    # 保存回测历史
    save_backtest_history(verified_count, correct_count, verified, stats_by_action)
    
    return verified_count, correct_count

def save_backtest_history(verified_count, correct_count, verified_df, stats):
    """保存回测结果到历史表"""
    import sqlite3
    
    conn_hist = sqlite3.connect(DB_PATH)
    cursor = conn_hist.cursor()
    
    # 计算统计数据
    accuracy = correct_count / verified_count * 100 if verified_count > 0 else 0
    avg_return = verified_df['actual_return'].mean() if len(verified_df) > 0 else 0
    
    # 各信号统计
    buy_acc = 0
    sell_acc = 0
    buy_ret = 0
    sell_ret = 0
    
    for action, data in stats.items():
        if '买入' in action:
            buy_acc = data['correct'] / data['total'] * 100 if data['total'] > 0 else 0
            buy_ret = data['avg_return']
        elif '反向' in action or action == 'sell':
            sell_acc = data['correct'] / data['total'] * 100 if data['total'] > 0 else 0
            sell_ret = data['avg_return']
    
    # 写入历史
    cursor.execute("""
        INSERT INTO backtest_history 
        (run_time, verified_count, correct_count, accuracy_pct, avg_return,
         buy_accuracy, sell_accuracy, buy_avg_return, sell_avg_return, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().isoformat(),
        verified_count,
        correct_count,
        round(accuracy, 2),
        round(avg_return, 4),
        round(buy_acc, 2),
        round(sell_acc, 2),
        round(buy_ret, 4),
        round(sell_ret, 4),
        f"自动验证 {verified_count} 条预测"
    ))
    
    conn_hist.commit()
    conn_hist.close()
    print(f"  ✓ 回测历史已保存")

if __name__ == "__main__":
    run_backtest()