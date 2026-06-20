import sqlite3, pathlib
import json
from datetime import datetime

_DB_PATH = str(pathlib.Path(__file__).parent / 'stocks.db')

def setup_prediction_table():
    """创建预测结果表"""
    conn = sqlite3.connect(str(pathlib.Path(__file__).parent / 'stocks.db'))
    
    # 创建预测结果表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS prediction_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            name TEXT,
            score INTEGER,
            tech_score INTEGER,
            risk_mult REAL,
            close REAL,
            pct_chg REAL,
            date TEXT,
            advice TEXT,
            prediction_date TEXT NOT NULL,
            model_version TEXT DEFAULT 'v5',
            UNIQUE(code, prediction_date, model_version)
        )
    """)
    
    # 创建索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pred_date ON prediction_results(prediction_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pred_code ON prediction_results(code)")
    
    conn.commit()
    conn.close()
    print("预测结果表已创建/更新")

def save_daily_predictions(json_file, model_version='v5'):
    """将每日预测结果写入数据库"""
    conn = sqlite3.connect(_DB_PATH)
    prediction_date = datetime.now().strftime('%Y-%m-%d')
    
    # 读取预测结果
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 写入数据库
    for stock in data.get('stocks', []):
        conn.execute("""
            INSERT OR REPLACE INTO prediction_results 
            (code, name, score, tech_score, risk_mult, close, pct_chg, date, advice, prediction_date, model_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            stock.get('code'),
            stock.get('name'),
            stock.get('score'),
            stock.get('tech_score'),
            stock.get('risk_mult'),
            stock.get('close'),
            stock.get('pct_chg'),
            stock.get('date'),
            stock.get('advice'),
            prediction_date,
            model_version
        ))
    
    conn.commit()
    
    # 统计
    total = len(data.get('stocks', []))
    buy_count = len([s for s in data.get('stocks', []) if s.get('advice') == '买入'])
    
    print(f"已保存 {total} 条预测记录 (买入信号: {buy_count})")
    conn.close()

def get_predictions_by_date(prediction_date=None):
    """获取指定日期的预测结果"""
    conn = sqlite3.connect(_DB_PATH)
    
    if prediction_date is None:
        prediction_date = datetime.now().strftime('%Y-%m-%d')
    
    preds = conn.execute("""
        SELECT code, name, score, advice, prediction_date 
        FROM prediction_results 
        WHERE prediction_date = ? AND model_version = 'v5'
        ORDER BY score DESC
    """, (prediction_date,)).fetchall()
    
    print(f"=== {prediction_date} 日线预测结果 ===")
    for p in preds:
        print(f"  {p[0]} {p[1]}: score={p[2]}, advice={p[3]}")
    
    conn.close()
    return preds

def verify_predictions(prediction_date):
    """验证预测效果 - 对比预测日期的下一天实际涨跌"""
    conn = sqlite3.connect(_DB_PATH)
    
    # 获取预测结果
    preds = conn.execute("""
        SELECT code, name, score, advice 
        FROM prediction_results 
        WHERE prediction_date = ? AND model_version = 'v5' AND advice = '买入'
    """, (prediction_date,)).fetchall()
    
    print(f"=== 预测验证: {prediction_date} 买入信号 ===")
    
    correct = 0
    total = len(preds)
    
    for p in preds:
        code, name, score, advice = p
        # 获取预测日期的下一天实际涨跌
        actual = conn.execute("""
            SELECT pct_chg FROM daily_price 
            WHERE code = ? AND date > ? 
            ORDER BY date LIMIT 1
        """, (code, prediction_date)).fetchone()
        
        if actual:
            is_correct = actual[0] > 0
            if is_correct:
                correct += 1
            print(f"  {code} {name}: 预测买入, 实际 {'涨' if is_correct else '跌'} {actual[0]:.2f}%")
        else:
            print(f"  {code} {name}: 无后续数据")
    
    if total > 0:
        accuracy = correct / total * 100
        print(f"\n准确率: {correct}/{total} = {accuracy:.1f}%")
    
    conn.close()

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        
        if cmd == 'setup':
            setup_prediction_table()
            
        elif cmd == 'save':
            save_daily_predictions(str(pathlib.Path(__file__).parent / 'result_v5.json'), 'v5')
            
        elif cmd == 'verify':
            date = sys.argv[2] if len(sys.argv) > 2 else None
            verify_predictions(date)
            
        elif cmd == 'list':
            get_predictions_by_date(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        print("用法:")
        print("  python prediction_db.py setup     - 创建/初始化数据库表")
        print("  python prediction_db.py save      - 保存今日预测结果到数据库")
        print("  python prediction_db.py verify [日期] - 验证指定日期的预测效果")
        print("  python prediction_db.py list [日期]  - 查看指定日期的预测结果")