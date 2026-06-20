"""
逐日预测回测脚本 - 防止数据泄露
严格按时间顺序：每天用之前的数据训练预测当天
每天重新训练模型
"""
import sys, os, sqlite3, importlib, pathlib
import pandas as pd, numpy as np, warnings, json
from datetime import datetime, timedelta
warnings.filterwarnings('ignore')
_RUN_DIR = str(pathlib.Path(__file__).parent.absolute())
os.chdir(_RUN_DIR); sys.path.insert(0, _RUN_DIR)
from config import DB_PATH, CSV_PATH, RISE_THRESHOLD, PREDICT_DAYS

def run_daily_backtest(start_date, end_date):
    """
    逐日回测 - 每天用之前的数据预测当天
    每天重新训练模型
    """
    conn = sqlite3.connect(DB_PATH)
    pool = pd.read_csv(CSV_PATH, encoding='utf-8-sig')['股票代码'].tolist()
    
    # 加载分析器模块
    spec = importlib.util.spec_from_file_location("av6_mod", os.path.join(_RUN_DIR, "analyzer_v5.py"))
    av6 = importlib.util.module_from_spec(spec)
    sys.modules["av6_mod"] = av6; spec.loader.exec_module(av6)
    av6.PREDICT_DAYS = PREDICT_DAYS
    av6.RISE_THRESHOLD = RISE_THRESHOLD
    
    # 转换日期
    start_dt = pd.Timestamp(start_date)
    end_dt = pd.Timestamp(end_date)
    
    # 获取所有交易日期 - 过滤无效日期
    all_dates_df = pd.read_sql("SELECT DISTINCT date FROM daily_price WHERE date LIKE '2%' ORDER BY date", conn)
    all_dates = []
    for d in all_dates_df['date']:
        try:
            pd.Timestamp(str(d))
            all_dates.append(str(d))
        except:
            continue
    
    # 找到回测期间的交易日
    trade_dates = [d for d in all_dates if start_dt <= pd.Timestamp(d) <= end_dt]
    print(f"回测期间: {len(trade_dates)} 个交易日 ({start_date} ~ {end_date})")
    
    # 存储结果
    all_predictions = []
    
    # 清空之前的预测结果 - 先创建表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT, name TEXT, prediction_date TEXT, 
            train_end TEXT, score INTEGER, 
            actual_change REAL, actual_up INTEGER, close REAL
        )
    """)
    conn.execute("DELETE FROM daily_predictions WHERE prediction_date >= ? AND prediction_date <= ?", (start_date, end_date))
    conn.commit()
    
    total = len(trade_dates)
    for i, pred_date in enumerate(trade_dates):
        # 训练数据截止日: pred_date的前一天
        train_end = (pd.Timestamp(pred_date) - timedelta(days=1)).strftime('%Y-%m-%d')
        
        print(f"[{i+1}/{total}] {pred_date} (训练截止: {train_end})", end=" ")
        
        try:
            # 训练模型
            models = av6.train_models_v6(pool, conn, train_end=train_end)
            
            if len(models['xgb']) == 0:
                print("→ 无模型")
                continue
                
            macro, fund = av6.load_macro_factors(conn)
            
            day_preds = 0
            
            # 对pred_date进行预测
            for code in pool:
                if code not in models['xgb']:
                    continue
                    
                df = pd.read_sql(f"SELECT * FROM daily_price WHERE code='{code}' ORDER BY date", conn)
                if len(df) < 60:
                    continue
                    
                # 找到pred_date在数据中的位置
                df['date'] = pd.to_datetime(df['date'])
                pred_idx_df = df[df['date'] == pd.Timestamp(pred_date)].index
                
                if len(pred_idx_df) == 0:
                    continue
                    
                pred_idx = pred_idx_df[0]
                
                # 跳过无法计算实际涨跌的日子
                if pred_idx + PREDICT_DAYS >= len(df):
                    continue
                
                # 提取特征
                df_alpha = av6.compute_alpha158(df)
                feat = av6.extract_features_v6(df.iloc[::-1], len(df) - pred_idx - 1)
                
                if not feat:
                    continue
                    
                # 添加Alpha158因子
                ar = df_alpha.iloc[pred_idx] if pred_idx < len(df_alpha) else None
                if ar is not None:
                    for c in ar.index:
                        if c.startswith('a158_'):
                            feat[c] = float(ar[c]) if pd.notna(ar[c]) else 0.0
                
                # 添加宏观因子
                feat = av6.add_macro_features(feat, pred_date, code, macro, fund)
                
                # 预测
                score = av6.predict_fusion_v6(models, code, feat)
                
                # 计算实际涨跌 (用预测当天收盘价vs次日收盘价)
                close_today = float(df.iloc[pred_idx]['close'])
                close_next = float(df.iloc[pred_idx + PREDICT_DAYS]['close'])
                actual_change = (close_next - close_today) / close_today
                actual_up = 1 if actual_change >= RISE_THRESHOLD else 0
                
                all_predictions.append({
                    'code': code,
                    'name': code,
                    'prediction_date': pred_date,
                    'train_end': train_end,
                    'score': score,
                    'actual_change': actual_change,
                    'actual_up': actual_up,
                    'close': close_today
                })
                
                day_preds += 1
            
            print(f"→ {day_preds}条预测")
            
            # 每10天写入一次数据库
            if (i + 1) % 10 == 0:
                save_to_db(conn, all_predictions)
                all_predictions = []
                
        except Exception as e:
            print(f"→ 错误: {str(e)[:50]}")
            continue
    
    # 最后保存一次
    if all_predictions:
        save_to_db(conn, all_predictions)
    
    conn.close()
    
    print(f"\n=== 回测完成 ===")
    print(f"总预测记录: {len(all_predictions) if all_predictions else 0}")

def save_to_db(conn, predictions):
    """保存到数据库"""
    # 确保表存在
    conn.execute("""
        CREATE TABLE IF NOT EXISTS daily_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT, name TEXT, prediction_date TEXT, 
            train_end TEXT, score INTEGER, 
            actual_change REAL, actual_up INTEGER, close REAL
        )
    """)
    
    for p in predictions:
        conn.execute("""
            INSERT INTO daily_predictions 
            (code, name, prediction_date, train_end, score, actual_change, actual_up, close)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (p['code'], p['name'], p['prediction_date'], p['train_end'], 
             p['score'], p['actual_change'], p['actual_up'], p['close']))
    
    conn.commit()
    print(f"  [已保存 {len(predictions)} 条到数据库]")

if __name__ == '__main__':
    # 运行一年的回测: 2025-06-11 ~ 2026-06-11
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
    
    print(f"开始逐日回测（每天重新训练模型）")
    print(f"时间范围: {start_date} ~ {end_date}")
    print("=" * 60)
    
    run_daily_backtest(start_date, end_date)