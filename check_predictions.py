import sqlite3
conn = sqlite3.connect('E:/stock5/stocks.db')

# 检查表是否存在和记录数
count = conn.execute('SELECT COUNT(*) FROM daily_predictions').fetchone()[0]
print(f'=== 预测结果统计 ===')
print(f'总预测记录数: {count}')

if count > 0:
    # 查看日期范围
    dates = conn.execute('SELECT MIN(prediction_date), MAX(prediction_date) FROM daily_predictions').fetchone()
    print(f'日期范围: {dates[0]} ~ {dates[1]}')
    
    # 统计买入信号
    buy_signals = conn.execute("SELECT COUNT(*) FROM daily_predictions WHERE score >= 54").fetchone()[0]
    print(f'分数>=54的信号数: {buy_signals}')
    
    # 按日期统计
    daily = conn.execute("SELECT prediction_date, COUNT(*) FROM daily_predictions GROUP BY prediction_date ORDER BY prediction_date DESC LIMIT 5").fetchall()
    print('\n最近5天预测数:')
    for d in daily:
        print(f'  {d[0]}: {d[1]}条')
    
    # 验证准确率
    print('\n=== 准确率统计 ===')
    for thresh in [30, 40, 50, 54, 60]:
        subset = conn.execute(f"SELECT COUNT(*), SUM(actual_up) FROM daily_predictions WHERE score >= {thresh}").fetchone()
        if subset[0] > 0:
            acc = subset[1] / subset[0] * 100
            print(f'分数>={thresh}: {subset[0]}条, 准确率{acc:.1f}%')

conn.close()