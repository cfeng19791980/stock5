# -*- coding: utf-8 -*-
"""
Autoresearch 兼容的回测脚本 - 标签阈值优化
测试不同 RISE_THRESHOLD 值对模型准确率的影响
"""
import sys, os, sqlite3, importlib, pathlib
import pandas as pd, numpy as np, warnings
warnings.filterwarnings('ignore')
_RUN_DIR = str(pathlib.Path(__file__).parent.absolute())
os.chdir(_RUN_DIR); sys.path.insert(0, _RUN_DIR)

# 时间窗口
train_end = '2026-05-07'
test_end = '2026-06-06'

# 动态导入 analyzer_v5 并修改参数
spec = importlib.util.spec_from_file_location('av6_mod', os.path.join(_RUN_DIR, 'analyzer_v5.py'))
av6 = importlib.util.module_from_spec(spec)
sys.modules['av6_mod'] = av6; spec.loader.exec_module(av6)

# 从 config 获取当前参数
from config import DB_PATH, CSV_PATH

# 需要测试的 RISE_THRESHOLD 值
RISE_THRESHOLDS = [0.01, 0.02, 0.03, 0.05]

conn = sqlite3.connect(DB_PATH)
pool = pd.read_csv(CSV_PATH, encoding='utf-8-sig')['股票代码'].tolist()

# 对每个阈值分别测试
results = []

for RISE_THRESHOLD in RISE_THRESHOLDS:
    print(f"\n=== 测试 RISE_THRESHOLD={RISE_THRESHOLD} ===")
    
    # 设置当前阈值
    av6.RISE_THRESHOLD = RISE_THRESHOLD
    
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
        tm = (dc > pd.Timestamp(train_end)) & (dc <= pd.Timestamp(test_end) - pd.DateOffset(days=1))
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
            if idx + 1 < len(df):
                up = 1 if (float(df.iloc[idx+1]['close']) - float(df.iloc[idx]['close']))/float(df.iloc[idx]['close']) >= RISE_THRESHOLD else 0
                records.append({'score':score, 'up':up})
    
    df_r = pd.DataFrame(records)
    total = len(df_r)
    
    # 计算各阈值的指标
    for buy_thresh in [40, 50, 60]:
        cnt = (df_r['score'] >= buy_thresh).sum()
        pct = cnt / total * 100 if total > 0 else 0
        acc = df_r[df_r['score'] >= buy_thresh]['up'].mean() * 100 if cnt > 0 else 0
        
        print(f"  买入阈值{buy_thresh}: 信号数={cnt}, 准确率={acc:.1f}%")
    
    # 输出 Autoresearch METRIC 格式
    print(f"\n--- RISE_THRESHOLD={RISE_THRESHOLD} 结果 ---")
    print(f"METRIC rise_threshold={RISE_THRESHOLD}")
    print(f"METRIC total_samples={total}")
    print(f"METRIC buy_accuracy_50={(df_r[df_r['score'] >= 50]['up'].mean() * 100) if (df_r['score'] >= 50).sum() > 0 else 0:.2f}")
    print(f"METRIC signal_count_50={(df_r['score'] >= 50).sum()}")
    print(f"METRIC signal_pct_50={(df_r['score'] >= 50).sum() / total * 100 if total > 0 else 0:.2f}")
    print(f"METRIC buy_accuracy_60={(df_r[df_r['score'] >= 60]['up'].mean() * 100) if (df_r['score'] >= 60).sum() > 0 else 0:.2f}")
    print(f"METRIC signal_count_60={(df_r['score'] >= 60).sum()}")
    
    # 合并信号数作为主要指标 (50和60阈值信号数之和)
    total_signals = (df_r['score'] >= 50).sum() + (df_r['score'] >= 60).sum()
    results.append({
        'threshold': RISE_THRESHOLD,
        'total': total,
        'signal_50': (df_r['score'] >= 50).sum(),
        'acc_50': df_r[df_r['score'] >= 50]['up'].mean() * 100 if (df_r['score'] >= 50).sum() > 0 else 0,
        'signal_60': (df_r['score'] >= 60).sum(),
        'acc_60': df_r[df_r['score'] >= 60]['up'].mean() * 100 if (df_r['score'] >= 60).sum() > 0 else 0,
    })

conn.close()

# 输出最终结果
print("\n=== 汇总结果 ===")
for r in results:
    print(f"RISE_THRESHOLD={r['threshold']}: 信号50数={r['signal_50']}, 准确率50={r['acc_50']:.1f}%, 信号60数={r['signal_60']}, 准确率60={r['acc_60']:.1f}%")