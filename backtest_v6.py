# -*- coding: utf-8 -*-
"""
backtest_v6.py — v6 全周期回测 v3
覆盖：多个牛熊时间段 + 丰富输出指标
"""
import sys, os, json, sqlite3, importlib, shutil, pickle

# 将项目根目录添加到 Python 路径，确保模块可导入
_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

# central config
from config import DB_PATH, CSV_PATH, MODEL_CACHE_DIR, USE_MODEL_CACHE, RETRAIN_FORCE, QUICK_RUN, N_ESTIMATORS, RISE_THRESHOLD, PREDICT_DAYS, CACHE_FILENAME

# ===== 多时间段配置（覆盖牛熊周期） =====
BACKTEST_PERIODS = [
    {"name": "熊市大跌", "train_end": "2022-06-01", "test_end": "2022-10-31", "desc": "上证3700→2800"},
    {"name": "反弹修复", "train_end": "2022-12-01", "test_end": "2023-05-31", "desc": "2800→3400"},
    {"name": "震荡下跌", "train_end": "2023-06-01", "test_end": "2024-01-31", "desc": "3400→2600"},
    {"name": "急跌修复", "train_end": "2024-02-01", "test_end": "2024-05-31", "desc": "2600→3100"},
    {"name": "宽幅震荡", "train_end": "2024-06-01", "test_end": "2025-02-28", "desc": "3100-2600-3400"},
    {"name": "震荡偏强", "train_end": "2025-03-01", "test_end": "2026-05-29", "desc": "3300→3600"},
]

conn = sqlite3.connect(DB_PATH)
stock_pool = pd.read_csv(CSV_PATH, encoding='utf-8-sig')['股票代码'].tolist()
print(f"股票池: {len(stock_pool)}只")
print(f"回测时段数: {len(BACKTEST_PERIODS)}")

all_period_results = []

for period_idx, period in enumerate(BACKTEST_PERIODS):
    train_end = pd.Timestamp(period['train_end'])
    test_end = pd.Timestamp(period['test_end'])
    train_start = train_end - pd.DateOffset(months=12)  # 12个月训练窗口
    
    print(f"\n{'='*70}")
    print(f"[时段{period_idx+1}/{len(BACKTEST_PERIODS)}] {period['name']}")
    print(f"  训练: {train_start.date()} ~ {train_end.date()}")
    print(f"  测试: {train_end.date()} ~ {test_end.date()}")
    print(f"  行情: {period['desc']}")
    
    # 缓存控制
    cache_file = os.path.join(MODEL_CACHE_DIR, CACHE_FILENAME)
    if RETRAIN_FORCE and os.path.exists(MODEL_CACHE_DIR):
        shutil.rmtree(MODEL_CACHE_DIR)
    os.makedirs(MODEL_CACHE_DIR, exist_ok=True)
    
    # 加载v6模块
    spec = importlib.util.spec_from_file_location(f"av6_{period_idx}",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "v6", "analyzer_v6.py"))
    av6 = importlib.util.module_from_spec(spec)
    sys.modules[f'av6_{period_idx}'] = av6
    spec.loader.exec_module(av6)
    
    # 覆盖配置为回测模式（可由 config 控制）
    av6.PREDICT_DAYS = PREDICT_DAYS
    av6.RISE_THRESHOLD = RISE_THRESHOLD
    
    # 训练/加载模型（严格限制训练期）
    train_end_str = period['train_end']
    models = None
    if USE_MODEL_CACHE and os.path.exists(cache_file):
        try:
            with open(cache_file, 'rb') as f:
                models = pickle.load(f)
            print('Loaded models from cache')
        except Exception:
            models = None

    if models is None:
        models = av6.train_models_v6(stock_pool, conn, train_end=train_end_str)
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(models, f)
        except Exception:
            pass
    
    # 加载测试期宏观因子
    macro_test, fund_test = av6.load_macro_factors(conn)
    
    all_results = []
    period_correct, period_total = 0, 0
    
    for code in stock_pool:
        if code not in models['xgb']:
            continue
        df = pd.read_sql("SELECT * FROM daily_price WHERE code=? ORDER BY date", conn, params=(code,))
        if len(df) < 60:
            continue
        
        # 计算 Alpha158
        df_alpha = av6.compute_alpha158(df, windows=av6.ALPHA158_WINDOWS, priority=av6.ALPHA158_PRIORITY)
        
        # 测试窗口
        date_col = pd.to_datetime(df['date'])
        test_mask = (date_col > pd.Timestamp(train_end)) & \
                    (date_col <= pd.Timestamp(test_end) - pd.DateOffset(days=av6.PREDICT_DAYS))
        test_indices = df[test_mask].index.tolist()
        
        if not test_indices:
            continue
        
        for idx in test_indices:
            # 特征提取（与训练时一致）
            feat = av6.extract_features_v6(df.iloc[::-1], len(df) - idx - 1)
            if not feat:
                continue
            
            # Alpha158 因子
            alpha_row = df_alpha.iloc[idx] if idx < len(df_alpha) else None
            if alpha_row is not None:
                for col in alpha_row.index:
                    if col.startswith('a158_'):
                        val = alpha_row[col]
                        feat[col] = float(val) if pd.notna(val) else 0.0
            
            row_date = str(df.iloc[idx]['date'])
            feat = av6.add_macro_features(feat, row_date, code, macro_test, fund_test)
            
            score = av6.predict_fusion_v6(models, code, feat)
            
            if idx + av6.PREDICT_DAYS < len(df):
                close_now = float(df.iloc[idx]['close'])
                close_fut = float(df.iloc[idx + av6.PREDICT_DAYS]['close'])
                actual_rise = (close_fut - close_now) / close_now if close_now > 0 else 0
                actual_up = 1 if actual_rise >= av6.RISE_THRESHOLD else 0
                # 多阈值判断：记录原始评分，后续算不同阈值的信号比例和准确率
                pred_up = 1 if score >= 60 else 0
                
                period_total += 1
                if pred_up == actual_up:
                    period_correct += 1
                
                all_results.append({
                    'code': code, 'date': row_date,
                    'score': score, 'pred_up': pred_up,
                    'actual_rise': round(actual_rise * 100, 4),
                    'actual_up': actual_up,
                })
    
    period_acc = period_correct / period_total * 100 if period_total > 0 else 0
    print(f"  → 准确率: {period_correct}/{period_total} = {period_acc:.1f}%")
    
    # ===== 该时段详细统计 =====
    if not all_results:
        all_period_results.append({"period": period['name'], "desc": period['desc'], "samples": 0, "accuracy": 0, "buy_signals": 0, "buy_up_rate": 0, "buy_avg_return": 0, "f1_score": 0})
        continue
    
    df_p = pd.DataFrame(all_results)
    
    # 评分分布概览（必须先于 period_summary，因为引用了 scores_arr）
    scores_arr = df_p['score'].values
    
    # 每日买入信号统计（必须先于 period_summary，因为引用了 daily_signals）
    df_p['date_dt'] = pd.to_datetime(df_p['date'])
    daily_signals = df_p[df_p['pred_up']==1].groupby('date_dt').size()
    
    # 混淆矩阵
    tp = len(df_p[(df_p['pred_up']==1) & (df_p['actual_up']==1)])
    fp = len(df_p[(df_p['pred_up']==1) & (df_p['actual_up']==0)])
    fn = len(df_p[(df_p['pred_up']==0) & (df_p['actual_up']==1)])
    tn = len(df_p[(df_p['pred_up']==0) & (df_p['actual_up']==0)])
    
    # 买入信号统计
    buys = df_p[df_p['pred_up'] == 1]
    sells = df_p[df_p['pred_up'] == 0]
    
    # 评分区间统计
    bins = [0, 40, 50, 60, 70, 100]
    labels = ['<40(卖��)', '40-49(观望)', '50-59(观望+)', '60-69(买入)', '>=70(强买入)']
    df_p['score_bin'] = pd.cut(df_p['score'], bins=bins, labels=labels, right=False)
    
    bin_stats = {}
    for label in labels:
        sub = df_p[df_p['score_bin'] == label]
        if len(sub) > 0:
            bin_stats[label] = {
                'count': len(sub),
                'up_rate': round(sub['actual_up'].mean() * 100, 1),
                'avg_return': round(sub['actual_rise'].mean(), 2),
            }
    
    # 每只股票统计
    code_stats = []
    for code in sorted(df_p['code'].unique()):
        sub = df_p[df_p['code'] == code]
        sub_acc = (sub['pred_up'] == sub['actual_up']).mean() * 100
        sub_buys = sub[sub['pred_up'] == 1]
        code_stats.append({
            'code': code,
            'samples': len(sub),
            'accuracy': round(sub_acc, 1),
            'buy_signals': len(sub_buys),
            'buy_up_rate': round(sub_buys['actual_up'].mean() * 100, 1) if len(sub_buys) > 0 else 0,
            'avg_return': round(sub['actual_rise'].mean(), 2),
        })
    
    period_summary = {
        "period": period['name'],
        "desc": period['desc'],
        "train_end": period['train_end'],
        "test_end": period['test_end'],
        "samples": period_total,
        "accuracy": round(period_acc, 1),
        "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "precision": round(tp / (tp + fp) * 100, 1) if (tp + fp) > 0 else 0,
        "recall": round(tp / (tp + fn) * 100, 1) if (tp + fn) > 0 else 0,
        "f1_score": round(2 * tp / (2 * tp + fp + fn) * 100, 1) if (2 * tp + fp + fn) > 0 else 0,
        "buy_signals": len(buys),
        "buy_up_rate": round(buys['actual_up'].mean() * 100, 1) if len(buys) > 0 else 0,
        "buy_avg_return": round(buys['actual_rise'].mean(), 2) if len(buys) > 0 else 0,
        "sell_up_rate": round(sells['actual_up'].mean() * 100, 1) if len(sells) > 0 else 0,
        "sell_avg_return": round(sells['actual_rise'].mean(), 2) if len(sells) > 0 else 0,
        "score_bins": bin_stats,
        "stock_stats": code_stats,
        "all_return_std": round(df_p['actual_rise'].std(), 2),
        "score_summary": {
            "min": int(scores_arr.min()),
            "max": int(scores_arr.max()),
            "mean": round(float(scores_arr.mean()), 1),
            "median": int(np.median(scores_arr)),
        },
        "daily_signals": {
            "days": int(daily_signals.sum()) if len(daily_signals) > 0 else 0,
            "avg_per_day": round(float(daily_signals.mean()), 1) if len(daily_signals) > 0 else 0.0,
            "max_per_day": int(daily_signals.max()) if len(daily_signals) > 0 else 0,
            "min_per_day": int(daily_signals.min()) if len(daily_signals) > 0 else 0,
            "signal_ratio": round(len(buys) / len(df_p) * 100, 2),
            "total_samples": len(df_p),
        },
        "threshold_scan": {
            str(thr): {
                "signal_ratio": round(float((df_p['score'] >= thr).mean() * 100), 2),
                "buy_count": int((df_p['score'] >= thr).sum()),
                "accuracy": round(float(( (df_p['score'] >= thr).astype(int) == df_p['actual_up'] ).mean() * 100), 1),
                "buy_up_rate": round(float(df_p[df_p['score'] >= thr]['actual_up'].mean() * 100), 1) if (df_p['score'] >= thr).any() else 0,
                "buy_avg_return": round(float(df_p[df_p['score'] >= thr]['actual_rise'].mean()), 2) if (df_p['score'] >= thr).any() else 0,
                "daily_avg": round(float((df_p['score'] >= thr).mean() * 30), 1),
            }
            for thr in [30, 40, 45, 50, 55, 60, 65, 70]
        },
    }
    all_period_results.append(period_summary)
    
    # ===== 多阈值扫描：找最优阈值 =====
    print(f"\n  多阈值扫描 (score>=threshold):")
    for thr in [30, 40, 45, 50, 55, 60, 65, 70]:
        pred_thr = (df_p['score'] >= thr).astype(int)
        thr_total = len(df_p)
        thr_buy = pred_thr.sum()
        thr_signal_ratio = thr_buy / thr_total * 100
        thr_correct = (pred_thr == df_p['actual_up']).sum()
        thr_acc = thr_correct / thr_total * 100
        thr_buy_up = df_p[pred_thr == 1]['actual_up'].mean() * 100 if thr_buy > 0 else 0
        thr_buy_ret = df_p[pred_thr == 1]['actual_rise'].mean() if thr_buy > 0 else 0
        # 估算每日买入信号：30只股票
        daily_buys = thr_signal_ratio / 100 * 30
        print(f"    score>={thr:2d}: 信号比例={thr_signal_ratio:5.2f}%({thr_buy:5d}/{thr_total}) "
              f"全量准确率={thr_acc:5.1f}% 买入上涨率={thr_buy_up:>5.1f}% "
              f"买入收益={thr_buy_ret:+.2f}% 日均买入≈{daily_buys:.1f}只/天")
    
    # ===== 每日买入信号统计 =====
    print(f"\n  每日买入信号分布:")

    # 处理 daily_signals 可能为空的场景
    if len(daily_signals) > 0:
        print(f"    交易日数: {len(daily_signals)}天")
        print(f"    日均买入: {daily_signals.mean():.1f}只/天 (30只池)")
        print(f"    最多: {daily_signals.max()}只/天, 最少: {daily_signals.min()}只/天")
    else:
        print(f"    买入信号: 0次")
    
    # 评分分布（上面已计算 scores_arr，这里直接打印）
    print(f"\n  评分分布: min={scores_arr.min()}, max={scores_arr.max()}, "
          f"mean={scores_arr.mean():.1f}, median={np.median(scores_arr):.0f}")
    
    # 打印摘要
    print(f"  买入: {len(buys)}次 上涨率={period_summary['buy_up_rate']}% 收益={period_summary['buy_avg_return']:+.2f}%")
    print(f"  F1={period_summary['f1_score']}% P={period_summary['precision']}% R={period_summary['recall']}%")
    for label, st in bin_stats.items():
        print(f"    {label:12s}: {st['count']:4d}次 上涨率={st['up_rate']:>5.1f}% 收益={st['avg_return']:+.2f}%")

conn.close()

# ===== 汇总统计 =====
print(f"\n{'='*70}")
print("=== 全周期回测汇总 ===")
total_samples = sum(p['samples'] for p in all_period_results)
print(f"总样本: {total_samples}")

summary_rows = []
for p in all_period_results:
    summary_rows.append({
        'period': p['period'],
        'samples': p['samples'],
        'accuracy': p['accuracy'],
        'buy_sig': p['buy_signals'],
        'buy_up': p['buy_up_rate'],
        'buy_ret': p['buy_avg_return'],
        'f1': p['f1_score'],
    })

df_summary = pd.DataFrame(summary_rows)
print(f"\n{'时段':12s} {'样本':>6s} {'准确率':>6s} {'买入信号':>8s} {'上涨率':>6s} {'收益':>6s} {'F1':>4s}")
print('-' * 56)
for _, r in df_summary.iterrows():
    print(f"{r['period']:12s} {r['samples']:>6d} {r['accuracy']:>5.1f}% {r['buy_sig']:>6d}次 {r['buy_up']:>5.1f}% {r['buy_ret']:>+5.2f}% {r['f1']:>4.1f}%")
print()

# 加权平均
weighted_acc = sum(p['accuracy'] * p['samples'] for p in all_period_results) / total_samples if total_samples > 0 else 0
total_buy_sigs = sum(p['buy_signals'] for p in all_period_results)
total_buy_up = sum(p['buy_up_rate'] * p['buy_signals'] for p in all_period_results) / total_buy_sigs if total_buy_sigs > 0 else 0
print(f"加权平均准确率: {weighted_acc:.1f}%")
print(f"总买入信号: {total_buy_sigs}次, 平均上涨率: {total_buy_up:.1f}%")

# ===== 全周期多阈值汇总 =====
print(f"\n  全周期多阈值汇总 (加权):")
for thr in [30, 40, 45, 50, 55, 60, 65, 70]:
    thr_str = str(thr)
    total_buy = sum(p.get('threshold_scan', {}).get(thr_str, {}).get('buy_count', 0) for p in all_period_results)
    total_samp = sum(p['samples'] for p in all_period_results if p['samples'] > 0)
    weighted_buy_up = 0
    total_buy_weight = 0
    for p in all_period_results:
        ts = p.get('threshold_scan', {}).get(thr_str, {})
        bc = ts.get('buy_count', 0)
        if bc > 0:
            weighted_buy_up += ts['buy_up_rate'] * bc
            total_buy_weight += bc
    avg_buy_up = weighted_buy_up / total_buy_weight if total_buy_weight > 0 else 0
    signal_ratio = total_buy / total_samp * 100 if total_samp > 0 else 0
    daily_avg = signal_ratio / 100 * 30
    print(f"    score>={thr:2d}: 总买入={total_buy:5d}/{total_samp}({signal_ratio:5.2f}%) "
          f"买入上涨率={avg_buy_up:5.1f}% 日均买入≈{daily_avg:.1f}只/天")

# 保存
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backtest_result_v6.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump({
        'config': {'predict_days': 1, 'rise_threshold': 0.01},
        'periods_count': len(all_period_results),
        'total_samples': total_samples,
        'weighted_accuracy': round(weighted_acc, 1),
        'total_buy_signals': total_buy_sigs,
        'avg_buy_up_rate': round(total_buy_up, 1),
        'periods': all_period_results,
    }, f, ensure_ascii=False, indent=2)

print(f"\n结果已保存: {out_path}")
print(f"{'='*70}")
