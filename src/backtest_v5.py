# -*- coding: utf-8 -*-
"""完整日线回测 - 使用正确的无缝时间窗口"""
import sys, os, sqlite3, importlib, pickle, pathlib
import pandas as pd, numpy as np, warnings
warnings.filterwarnings('ignore')
_RUN_DIR = str(pathlib.Path(__file__).parent.absolute())
os.chdir(_RUN_DIR); sys.path.insert(0, _RUN_DIR)
from config import DB_PATH, CSV_PATH, RISE_THRESHOLD, PREDICT_DAYS, MODEL_CACHE_DIR

# 时间窗口 - 测试期1个月，无缝衔接
train_end = '2026-05-07'
test_end = '2026-06-06'

print(f"训练截止: {train_end}")
print(f"测试窗口: {train_end} ~ {test_end}")

spec = importlib.util.spec_from_file_location("av6_mod", os.path.join(_RUN_DIR, "analyzer_v5.py"))
av6 = importlib.util.module_from_spec(spec)
sys.modules["av6_mod"] = av6; spec.loader.exec_module(av6)
av6.PREDICT_DAYS = PREDICT_DAYS; av6.RISE_THRESHOLD = RISE_THRESHOLD

conn = sqlite3.connect(DB_PATH)
pool = pd.read_csv(CSV_PATH, encoding='utf-8-sig')['股票代码'].tolist()  # 全部30只
print(f"股票池: {len(pool)}只")

# 清除旧缓存
cache_file = os.path.join(MODEL_CACHE_DIR, 'models_v6.pkl')
if os.path.exists(cache_file):
    os.remove(cache_file)

models = av6.train_models_v6(pool, conn, train_end=train_end)
print(f"模型训练完成")
macro, fund = av6.load_macro_factors(conn)

records = []
for code in pool:
    if code not in models['xgb']: continue
    df = pd.read_sql("SELECT * FROM daily_price WHERE code=? ORDER BY date", conn, params=(code,))
    if len(df) < 60: continue
    df_a = av6.compute_alpha158(df)
    dc = pd.to_datetime(df['date'])
    # 测试期: train_end < date <= test_end
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
        rm = av6.risk_check(feat)
        ra = int(score * rm)
        if idx + av6.PREDICT_DAYS < len(df):
            up = 1 if (float(df.iloc[idx+av6.PREDICT_DAYS]['close']) - float(df.iloc[idx]['close']))/float(df.iloc[idx]['close']) >= av6.RISE_THRESHOLD else 0
            records.append({'code':code,'score':score,'rm':rm,'ra':ra,'up':up})

df_r = pd.DataFrame(records)
total = len(df_r)
print(f"\n有效样本: {total}")

if total > 0:
    print(f"\n=== 阈值扫描 ===")
    for th in [30, 40, 50, 60, 70]:
        cnt = (df_r['score'] >= th).sum()
        pct = cnt / total * 100
        up_rate = df_r[df_r['score'] >= th]['up'].mean() * 100 if cnt > 0 else 0
        print(f"score >= {th}: {cnt}条 ({pct:.1f}%) 上涨率: {up_rate:.1f}%")
    
    print(f"\n=== 风控后阈值扫描 ===")
    for th in [30, 40, 50, 60, 70]:
        cnt = (df_r['ra'] >= th).sum()
        pct = cnt / total * 100
        up_rate = df_r[df_r['ra'] >= th]['up'].mean() * 100 if cnt > 0 else 0
        print(f"ra >= {th}: {cnt}条 ({pct:.1f}%) 上涨率: {up_rate:.1f}%")
    
    print(f"\n=== 风控统计 ===")
    print(f"rm均值: {df_r['rm'].mean():.3f}")
    print(f"rm<0.8占比: {(df_r['rm']<0.8).mean()*100:.1f}%")

conn.close()
print("\n完成")
