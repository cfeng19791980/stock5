# -*- coding: utf-8 -*-
"""
analyzer_v5 基准线回测 v2
回测方式：每期独立导入模块，保证各窗口模型完全不串
"""
import sys, os, json, sqlite3, importlib, shutil
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

DB_PATH = r'E:\stock5\stocks.db'
CSV_PATH = r'e:\stock5\波段股票Top30.csv'
CACHE_DIR = r'E:\stock5\model_cache_v5'
PREDICT_DAYS = 3
RISE_THRESHOLD = 0.03

conn = sqlite3.connect(DB_PATH)
stock_pool = pd.read_csv(CSV_PATH, encoding='utf-8-sig')['股票代码'].tolist()
print(f"股票池: {len(stock_pool)}只")

# 获取所有股票日期交集范围
date_ranges = []
for code in stock_pool:
    r = conn.execute("SELECT MIN(date), MAX(date) FROM daily_price WHERE code=?", (code,)).fetchone()
    if r[0]: date_ranges.append((code, r[0], r[1]))
start_date = pd.Timestamp(max(d[1] for d in date_ranges))
end_date = pd.Timestamp(min(d[2] for d in date_ranges))
print(f"有效日期范围: {start_date.date()} ~ {end_date.date()}")

# ===== 滚动回测 =====
all_predictions = []
window_end = pd.Timestamp('2025-06-01')

while window_end + pd.DateOffset(months=3) <= end_date:
    train_start = window_end - pd.DateOffset(months=18)
    train_end = window_end
    test_end = window_end + pd.DateOffset(months=3)
    
    print(f"\n{'='*60}")
    print(f"窗口: 训练 {train_start.date()} ~ {train_end.date()}")
    print(f"      测试 {train_end.date()} ~ {test_end.date()}")
    
    # 每期开始时清除缓存，强制重训
    if os.path.exists(CACHE_DIR):
        shutil.rmtree(CACHE_DIR)
    os.makedirs(CACHE_DIR)
    
    # 重新加载模块（复用解析器函数）
    spec = importlib.util.spec_from_file_location(f"analyzer_{int(window_end.timestamp())}", "analyzer_v5.py")
    a = importlib.util.module_from_spec(spec)
    sys.modules[f'analyzer_{int(window_end.timestamp())}'] = a
    spec.loader.exec_module(a)
    
    # 训练模型
    models = a.train_models_v5(stock_pool, conn)
    
    # 加载宏观因子
    macro_test, fund_test = a.load_macro_factors(conn)
    
    correct, total = 0, 0
    results = []
    
    for code in stock_pool:
        if code not in models['xgb']:
            continue
        df = pd.read_sql("SELECT * FROM daily_price WHERE code=? ORDER BY date", conn, params=(code,))
        if len(df) < 60:
            continue
        
        # 只取测试日期段
        date_col = pd.to_datetime(df['date'])
        test_mask = (date_col > pd.Timestamp(train_end)) & \
                    (date_col <= pd.Timestamp(test_end) - pd.DateOffset(days=PREDICT_DAYS*2))
        test_indices = df[test_mask].index.tolist()[::5]  # 每5天采样
        
        for idx in test_indices:
            feat = a.extract_features_v5(df.iloc[::-1], len(df)-idx-1)
            if not feat:
                continue
            row_date = str(df.iloc[idx]['date'])
            feat = a.add_macro_features(feat, row_date, code, macro_test, fund_test)
            feat_filtered = {k: v for k, v in feat.items() if k in a.SELECTED_FEATURES}
            
            score = a.predict_fusion(models, code, feat_filtered)
            
            if idx + PREDICT_DAYS < len(df):
                close_now = float(df.iloc[idx]['close'])
                close_fut = float(df.iloc[idx+PREDICT_DAYS]['close'])
                actual_rise = (close_fut - close_now) / close_now if close_now > 0 else 0
                actual_up = 1 if actual_rise >= RISE_THRESHOLD else 0
                pred_up = 1 if score >= 60 else 0
                
                total += 1
                if pred_up == actual_up:
                    correct += 1
                
                results.append({
                    'code': code, 'date': row_date,
                    'score': score, 'pred_up': pred_up,
                    'actual_rise': round(actual_rise * 100, 2),
                    'actual_up': actual_up,
                })
    
    acc = correct / total * 100 if total > 0 else 0
    print(f"  正确: {correct}/{total} = {acc:.1f}%")
    all_predictions.extend(results)
    window_end += pd.DateOffset(months=3)

conn.close()

# ===== 汇总统计 =====
print(f"\n{'='*60}")
print(f"回测总样本: {len(all_predictions)}")
if all_predictions:
    df_all = pd.DataFrame(all_predictions)
    
    # 按评分区间
    print(f"\n--- 按评分区间 ---")
    bins = [0, 30, 40, 50, 60, 70, 100]
    labels = ['<30(强卖出)', '30-39(卖出)', '40-49(观望-)', '50-59(观望+)', '60-69(买入)', '>=70(强买入)']
    df_all['score_bin'] = pd.cut(df_all['score'], bins=bins, labels=labels, right=False)
    
    for label in labels:
        subset = df_all[df_all['score_bin'] == label]
        if len(subset) > 0:
            up_pct = subset['actual_up'].mean() * 100
            print(f"  {label:12s}: {len(subset):4d}样本, 实际上涨率={up_pct:.1f}% (分数中位数={subset['score'].median():.0f})")
    
    # 信号统计
    print(f"\n--- 信号统计 ---")
    buys = df_all[df_all['pred_up'] == 1]
    sells = df_all[df_all['pred_up'] == 0]
    print(f"  买入信号(>=60): {len(buys)}次, 上涨率={buys['actual_up'].mean()*100:.1f}%, 平均收益={buys['actual_rise'].mean():+.2f}%")
    print(f"  卖出信号(<60): {len(sells)}次, 上涨率={sells['actual_up'].mean()*100:.1f}%, 平均收益={sells['actual_rise'].mean():+.2f}%")
    print(f"  整体准确率: {(df_all['pred_up']==df_all['actual_up']).mean()*100:.1f}%")
    print(f"  全部平均收益: {df_all['actual_rise'].mean():+.2f}%")
    
    # 按股票
    print(f"\n--- 每只股票准确率 ---")
    for code in sorted(df_all['code'].unique()):
        sub = df_all[df_all['code'] == code]
        print(f"  {code:10s}: {len(sub):3d}样本, 准确率={(sub['pred_up']==sub['actual_up']).mean()*100:.1f}%")

# 保存
with open('backtest_result_v5.json', 'w', encoding='utf-8') as f:
    json.dump({
        'config': {'predict_days': PREDICT_DAYS, 'rise_threshold': RISE_THRESHOLD},
        'total_samples': len(all_predictions),
        'accuracy': round((df_all['pred_up']==df_all['actual_up']).mean()*100, 2) if len(all_predictions) > 0 else 0,
        'buy_accuracy': round(buys['actual_up'].mean()*100, 2) if len(buys) > 0 else 0,
        'sell_accuracy': round(sells['actual_up'].mean()*100, 2) if len(sells) > 0 else 0,
    }, f, ensure_ascii=False, indent=2)
print(f"\n结果已保存: backtest_result_v5.json")
