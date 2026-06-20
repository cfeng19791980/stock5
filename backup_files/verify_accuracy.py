# -*- coding: utf-8 -*-
"""准确率验证脚本"""
import sys, os, sqlite3, importlib, shutil
import pandas as pd, numpy as np, warnings
warnings.filterwarnings('ignore')
os.chdir(r'E:\stock5'); sys.path.insert(0, r'E:\stock5')

from config import DB_PATH, CSV_PATH, RISE_THRESHOLD, PREDICT_DAYS

# 加载模块
spec = importlib.util.spec_from_file_location("av5_mod", r"E:\stock5\analyzer_v5.py")
av5 = importlib.util.module_from_spec(spec)
sys.modules["av5_mod"] = av5
spec.loader.exec_module(av5)
av5.PREDICT_DAYS = PREDICT_DAYS
av5.RISE_THRESHOLD = RISE_THRESHOLD

conn = sqlite3.connect(DB_PATH)
stock_pool = pd.read_csv(CSV_PATH, encoding='utf-8-sig')['股票代码'].tolist()

# 清缓存重新训练
train_end = '2026-05-31'
cache_file = os.path.join(r'E:\stock5\v6\model_cache_v6', 'models_v6.pkl')
if os.path.exists(cache_file):
    os.remove(cache_file)

print("训练模型...")
models = av5.train_models_v6(stock_pool, conn, train_end=train_end)
macro_test, fund_test = av5.load_macro_factors(conn)

# 回测
records = []
for code in stock_pool:
    if code not in models['xgb']:
        continue
    df = pd.read_sql("SELECT * FROM daily_price WHERE code=? ORDER BY date", conn, params=(code,))
    if len(df) < 60:
        continue
    
    df_alpha = av5.compute_alpha158(df, windows=av5.ALPHA158_WINDOWS, priority=av5.ALPHA158_PRIORITY)
    date_col = pd.to_datetime(df['date'])
    test_mask = (date_col >= pd.Timestamp('2026-05-08')) & (date_col <= pd.Timestamp('2026-06-06') - pd.DateOffset(days=av5.PREDICT_DAYS))
    
    for idx in df[test_mask].index.tolist():
        feat = av5.extract_features_v6(df.iloc[::-1], len(df) - idx - 1)
        if not feat:
            continue
        
        alpha_row = df_alpha.iloc[idx] if idx < len(df_alpha) else None
        if alpha_row is not None:
            for col in alpha_row.index:
                if col.startswith('a158_'):
                    val = alpha_row[col]
                    feat[col] = float(val) if pd.notna(val) else 0.0
        
        feat = av5.add_macro_features(feat, str(df.iloc[idx]['date']), code, macro_test, fund_test)
        tech_score = av5.predict_fusion_v6(models, code, feat)
        
        if idx + av5.PREDICT_DAYS < len(df):
            close_now = float(df.iloc[idx]['close'])
            close_fut = float(df.iloc[idx + av5.PREDICT_DAYS]['close'])
            actual_rise = (close_fut - close_now) / close_now if close_now > 0 else 0
            actual_up = 1 if actual_rise >= av5.RISE_THRESHOLD else 0
            
            # 预测是否买入
            pred_up = 1 if tech_score >= 56 else 0
            # 是否预测正确
            is_correct = 1 if pred_up == actual_up else 0
            
            records.append({
                'tech_score': tech_score,
                'pred_up': pred_up,
                'actual_up': actual_up,
                'is_correct': is_correct,
            })

df_r = pd.DataFrame(records)

# 统计
total = len(df_r)
correct = int(df_r['is_correct'].sum())
actual_up_count = int(df_r['actual_up'].sum())
accuracy = correct / total * 100 if total > 0 else 0

print(f"\n{'='*60}")
print(f"有效样本: {total}")
print(f"实际上涨: {actual_up_count} ({actual_up_count/total*100:.1f}%)")
print(f"预测上涨: {int(df_r['pred_up'].sum())} ({int(df_r['pred_up'].sum())/total*100:.1f}%)")
print(f"\n整体准确率: {correct}/{total} = {accuracy:.1f}%")

# 分段统计
print(f"\n评分分段统计:")
for lo in [0, 10, 20, 30, 40, 50, 60, 70, 80]:
    hi = lo + 10
    mask = (df_r['tech_score'] >= lo) & (df_r['tech_score'] < hi)
    cnt = mask.sum()
    if cnt > 0:
        up_rate = df_r.loc[mask, 'actual_up'].mean() * 100
        print(f"  {lo:3d}~{hi:3d}: {cnt:4d}条, 上涨率 {up_rate:5.1f}%")

conn.close()
print("\n完成!")
