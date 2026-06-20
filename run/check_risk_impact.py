# -*- coding: utf-8 -*-
"""快速验证 risk_check 影响：用缓存模型+最近一周+30只"""
import sys, os, sqlite3, importlib, pickle, json, pathlib
import pandas as pd, numpy as np, warnings
warnings.filterwarnings('ignore')
_RUN_DIR = str(pathlib.Path(__file__).parent.absolute())
os.chdir(_RUN_DIR); sys.path.insert(0, _RUN_DIR)
from config import DB_PATH, CSV_PATH, RISE_THRESHOLD, PREDICT_DAYS

spec = importlib.util.spec_from_file_location("av6_mod", os.path.join(_RUN_DIR, "analyzer_v5.py"))
av6 = importlib.util.module_from_spec(spec)
sys.modules["av6_mod"] = av6; spec.loader.exec_module(av6)
av6.PREDICT_DAYS = PREDICT_DAYS; av6.RISE_THRESHOLD = RISE_THRESHOLD

conn = sqlite3.connect(DB_PATH)
pool = pd.read_csv(CSV_PATH, encoding='utf-8-sig')['股票代码'].tolist()

# 用当前result_v5.json里的最后评分，反查tech_score
import json
with open(os.path.join(_RUN_DIR, 'result_v5.json')) as f:
    result = json.load(f)

# result_v5.json 存的是 final_score，我们需要的���始tech_score
# 从 prediction_logs_v5 里看日线预测（如果有）
# 实际上日线评分没有单独日志，但可以从result_v5.json看score = final_score

# 直接看 result_v5.json 的 score 分布
stocks = result['stocks']
print(f"当前 result_v5.json: {result['timestamp']}")
scores = [s['score'] for s in stocks]
print(f"score范围: {min(scores)}~{max(scores)}")
print(f"≥60: {sum(1 for s in scores if s>=60)}个")
print(f"40-59: {sum(1 for s in scores if 40<=s<60)}个")
print(f"<40: {sum(1 for s in scores if s<40)}个")

# 用缓存模型跑一次全量，看tech_score分布
cache_file = os.path.join(_RUN_DIR, 'v6', 'model_cache_v6', 'models_v6.pkl')
if not os.path.exists(cache_file):
    print("无缓存模型，重新训练...")
    models = av6.train_models_v6(pool, conn, train_end=(pd.Timestamp.now() - pd.DateOffset(days=7)).strftime('%Y-%m-%d'))
    print(f"模型训练完成: {len(models)}")
else:
    with open(cache_file, 'rb') as f:
        models = pickle.load(f)
    print(f"\n加载缓存模型: {len(models)}")
    macro, fund = av6.load_macro_factors(conn)
    
    # 最近3天
    test_end = pd.Timestamp.now() - pd.DateOffset(days=1)
    test_start = test_end - pd.DateOffset(days=3)
    
    records = []
    for code in pool:
        if code not in models['xgb']: continue
        df = pd.read_sql("SELECT * FROM daily_price WHERE code=? ORDER BY date", conn, params=(code,))
        if len(df) < 60: continue
        
        # 跳过Alpha158（太慢），只看基础特征
        dc = pd.to_datetime(df['date'])
        tm = (dc >= test_start) & (dc <= test_end - pd.DateOffset(days=av6.PREDICT_DAYS))
        for idx in df[tm].index.tolist():
            feat = av6.extract_features_v6(df.iloc[::-1], len(df)-idx-1)
            if not feat: continue
            feat = av6.add_macro_features(feat, str(df.iloc[idx]['date']), code, macro, fund)
            score = av6.predict_fusion_v6(models, code, feat)
            rm = av6.risk_check(feat)
            ra = int(score * rm)
            if idx + av6.PREDICT_DAYS < len(df):
                up = 1 if (float(df.iloc[idx+av6.PREDICT_DAYS]['close']) - float(df.iloc[idx]['close']))/float(df.iloc[idx]['close']) >= av6.RISE_THRESHOLD else 0
                records.append({'code':code,'date':str(df.iloc[idx]['date']),'score':score,'rm':rm,'ra':ra,'up':up})
    
    df_r = pd.DataFrame(records)
    print(f"\n最近3天有效样本: {len(df_r)}")
    if len(df_r) > 0:
        r1 = df_r[df_r['score'] >= 60]
        r2 = df_r[df_r['ra'] >= 60]
        print(f"  tech>=60买入: {len(r1)}次 上涨 {r1['up'].mean()*100:.1f}%")
        print(f"  ra>=60买入:   {len(r2)}次 上涨 {r2['up'].mean()*100:.1f}%")
        print(f"  rm均值: {df_r['rm'].mean():.3f}")
        sup = df_r[(df_r['score']>=60)&(df_r['ra']<60)]
        if len(sup) > 0:
            print(f"  被压下: {len(sup)}条 涨 {sup['up'].mean()*100:.1f}%")
        print(f"\n评分分布:")
        for lo in range(0,100,10):
            cnt = ((df_r['score']>=lo)&(df_r['score']<lo+10)).sum()
            if cnt:
                print(f"  {lo:3d}~{lo+10:3d}: {cnt}条 涨 {df_r[(df_r['score']>=lo)&(df_r['score']<lo+10)]['up'].mean()*100:.1f}%")
conn.close()
print("\n✅")
