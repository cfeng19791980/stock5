import sqlite3
conn = sqlite3.connect('E:/stock5/stocks.db')

# 查看数据库有哪些表
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print('=== 数据库表 ===')
for t in tables:
    print(t[0])

print()

# 查看prediction_results表
print('=== prediction_results 表结构 ===')
try:
    cols = conn.execute("PRAGMA table_info(prediction_results)").fetchall()
    for c in cols:
        print(f"  {c[1]} ({c[2]})")
except:
    print("表不存在")

print()

# 查看最近的预测记录
print('=== 最近预测记录 ===')
try:
    preds = conn.execute("SELECT code, score, advice, prediction_date FROM prediction_results ORDER BY prediction_date DESC LIMIT 10").fetchall()
    for p in preds:
        print(f"  {p[0]}: score={p[1]}, advice={p[2]}, date={p[3]}")
except Exception as e:
    print(f"查询失败: {e}")

conn.close()