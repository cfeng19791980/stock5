# -*- coding: utf-8 -*-
"""
Autoresearch 兼容的回测脚本
输出 METRIC 格式，供 Autoresearch 解析
"""
import sys, os, sqlite3, importlib
import pandas as pd, numpy as np, warnings
warnings.filterwarnings('ignore')
os.chdir(r'E:\stock5'); sys.path.insert(0, r'E:\stock5')
from config import DB_PATH, CSV_PATH, RISE_THRESHOLD, PREDICT_DAYS

# 时间窗口
train_end = '2026-05-07'
test_end = '2026-06-06'

spec = importlib.util.spec_from_file_location('av6_mod', r'E:\stock5\analyzer_v5.py')
av6 = importlib.util.module_from_spec(spec)
sys.modules['av6_mod'] = av6; spec.loader.exec_module(av6)
av6.PREDICT_DAYS = PREDICT_DAYS; av6.RISE_THRESHOLD = RISE_THRESHOLD

conn = sqlite3.connect(DB_PATH)
pool = pd.read_csv(CSV_PATH, encoding='utf-8-sig')['股票代码'].tolist()

# 训练模型
models = av6.train_models_v6(pool, conn, train_end=train_end)
macro, fund = av6.load_macro_factors(conn)

records = []
for code in pool:
    if code not in models['xgb']: continue
    df = pd.read_sql("SELECT * FROM daily_price WHERE code=? ORDER BY date", conn, params=(code,))
    if len(df) < 60: continue
    df_a = av6.compute_alpha158(df)
    dc = pd.to_datetime(df['date'])
    tm = (dc > pd.Timestamp(train_end)) & (dc <= pd.Timestamp(test_end) - pd.DateOffset(days=av6.PREDICT_DAYS))
    test_indices = df[tm].index.tolist()
    
    for idx in test_indices:
        feat = av6.extract_features_v6(df.iloc[::-1], len(df)-idx-1)
        if not feat: continue
        ar = df_a.iloc[idx] if idx < len(df_a) else None
        if ar is not None:
            for c in ar.index:
                if c.startswith('a158_'): feat[c] = float(ar[c]) if pd.notna(ar[c]) else 0.0
        feat = av6.add_macro_features(feat, str(df.iloc[idx]['date']), code, macro, fund)
        score = av6.predict_fusion_v6(models, code, feat)
        if idx + av6.PREDICT_DAYS < len(df):
            up = 1 if (float(df.iloc[idx+av6.PREDICT_DAYS]['close']) - float(df.iloc[idx]['close']))/float(df.iloc[idx]['close']) >= av6.RISE_THRESHOLD else 0
            records.append({'score':score, 'up':up})

df_r = pd.DataFrame(records)
total = len(df_r)

# 计算 score>=54 的指标
cnt_54 = (df_r['score'] >= 54).sum()
pct_54 = cnt_54 / total * 100
acc_54 = df_r[df_r['score'] >= 54]['up'].mean() * 100 if cnt_54 > 0 else 0

# 计算 score>=55 的指标 (新阈值测试)
cnt_55 = (df_r['score'] >= 55).sum()
pct_55 = cnt_55 / total * 100
acc_55 = df_r[df_r['score'] >= 55]['up'].mean() * 100 if cnt_55 > 0 else 0

# 计算 score>=52 的指标 (备选)
cnt_52 = (df_r['score'] >= 52).sum()
pct_52 = cnt_52 / total * 100
acc_52 = df_r[df_r['score'] >= 52]['up'].mean() * 100 if cnt_52 > 0 else 0

# 输出 Autoresearch 需要的 METRIC 格式
print(f"METRIC signal_pct={pct_54:.2f}")
print(f"METRIC buy_accuracy_54={acc_54:.2f}")
print(f"METRIC signal_count_54={cnt_54}")
print(f"METRIC signal_pct_52={pct_52:.2f}")
print(f"METRIC buy_accuracy_52={acc_52:.2f}")
print(f"METRIC signal_pct_55={pct_55:.2f}")
print(f"METRIC buy_accuracy_55={acc_55:.2f}")

conn.close()