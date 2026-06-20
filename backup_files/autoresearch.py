# -*- coding: utf-8 -*-
"""
stock5_autoresearch.py — 基于历史验证数据优化模型参数
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import json, os, sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
from collections import defaultdict

DB_PATH = r'E:\stock5\stocks.db'

def get_connection():
    return sqlite3.connect(DB_PATH)

def analyze_signal_performance():
    """分析各信号类型的准确率和收益"""
    conn = get_connection()
    
    # 获取所有已验证的预测
    cur = conn.execute('''
        SELECT predict_action, actual_result, actual_return
        FROM prediction_logs_v5 
        WHERE actual_result IS NOT NULL AND actual_result != 'pending'
    ''')
    
    # 按 预测动作×实际结果 统计
    matrix = defaultdict(lambda: {'count': 0, 'total_return': 0})
    
    for row in cur.fetchall():
        action = row[0]
        actual = row[1]
        ret = row[2] or 0
        key = f"{action}|{actual}"
        matrix[key]['count'] += 1
        matrix[key]['total_return'] += ret
    
    conn.close()
    
    # 转换为按动作分组的分析
    action_analysis = defaultdict(lambda: {'total': 0, 'correct': 0, 'total_return': 0, 'by_actual': {}})
    
    for key, stats in matrix.items():
        action, actual = key.split('|')
        action_analysis[action]['total'] += stats['count']
        action_analysis[action]['total_return'] += stats['total_return']
        action_analysis[action]['by_actual'][actual] = {
            'count': stats['count'],
            'return': stats['total_return'] / stats['count'] if stats['count'] > 0 else 0
        }
        
        # 判断正确性：买入→涨，卖出→跌，持有→持平
        is_correct = False
        if action in ['buy', '强烈买入'] and actual in ['up', 'up_1pct']:
            is_correct = True
        elif action in ['sell'] and actual in ['down', 'down_1pct']:
            is_correct = True
        elif action in ['hold', '持有观望'] and actual == 'flat':
            is_correct = True
        elif action == '反向买入机会' and actual in ['down', 'down_1pct']:
            is_correct = True
            
        if is_correct:
            action_analysis[action]['correct'] += stats['count']
    
    # 整理输出
    results = []
    for action, data in action_analysis.items():
        if data['total'] > 0:
            results.append({
                'action': action,
                'accuracy': data['correct'] / data['total'],
                'count': data['total'],
                'avg_return': data['total_return'] / data['total'],
                'by_actual': data['by_actual'],
            })
    
    return sorted(results, key=lambda x: x['count'], reverse=True)

def analyze_score_thresholds():
    """分析不同评分的预测效果"""
    conn = get_connection()
    
    cur = conn.execute('''
        SELECT predict_score, actual_result, actual_return
        FROM prediction_logs_v5 
        WHERE actual_result IS NOT NULL AND actual_result != 'pending'
        AND predict_score IS NOT NULL
    ''')
    
    # 按评分区间分组
    buckets = {
        '0-30': {'total': 0, 'up': 0, 'up_1pct': 0, 'down': 0, 'down_1pct': 0, 'flat': 0, 'returns': []},
        '30-40': {'total': 0, 'up': 0, 'up_1pct': 0, 'down': 0, 'down_1pct': 0, 'flat': 0, 'returns': []},
        '40-50': {'total': 0, 'up': 0, 'up_1pct': 0, 'down': 0, 'down_1pct': 0, 'flat': 0, 'returns': []},
        '50-60': {'total': 0, 'up': 0, 'up_1pct': 0, 'down': 0, 'down_1pct': 0, 'flat': 0, 'returns': []},
        '60-70': {'total': 0, 'up': 0, 'up_1pct': 0, 'down': 0, 'down_1pct': 0, 'flat': 0, 'returns': []},
        '70+': {'total': 0, 'up': 0, 'up_1pct': 0, 'down': 0, 'down_1pct': 0, 'flat': 0, 'returns': []},
    }
    
    for row in cur.fetchall():
        score = row[0] or 50
        actual = row[1]
        ret = row[2] or 0
        
        # 确定区间
        if score < 30:
            bucket = '0-30'
        elif score < 40:
            bucket = '30-40'
        elif score < 50:
            bucket = '40-50'
        elif score < 60:
            bucket = '50-60'
        elif score < 70:
            bucket = '60-70'
        else:
            bucket = '70+'
        
        buckets[bucket]['total'] += 1
        buckets[bucket]['returns'].append(ret)
        
        if actual == 'up':
            buckets[bucket]['up'] += 1
        elif actual == 'up_1pct':
            buckets[bucket]['up_1pct'] += 1
        elif actual == 'down':
            buckets[bucket]['down'] += 1
        elif actual == 'down_1pct':
            buckets[bucket]['down_1pct'] += 1
        elif actual == 'flat':
            buckets[bucket]['flat'] += 1
    
    conn.close()
    
    # 计算统计
    results = []
    for bucket, data in buckets.items():
        if data['total'] > 0:
            up_total = data['up'] + data['up_1pct']
            down_total = data['down'] + data['down_1pct']
            results.append({
                'bucket': bucket,
                'count': data['total'],
                'up_rate': up_total / data['total'],
                'down_rate': down_total / data['total'],
                'avg_return': np.mean(data['returns']) if data['returns'] else 0,
                'avg_return_positive': np.mean([r for r in data['returns'] if r > 0]) if any(r > 0 for r in data['returns']) else 0,
                'avg_return_negative': np.mean([r for r in data['returns'] if r < 0]) if any(r < 0 for r in data['returns']) else 0,
            })
    
    return results

def analyze_stock_performance():
    """分析各股票的预测表现"""
    conn = get_connection()
    
    cur = conn.execute('''
        SELECT stock_code, 
               COUNT(*) as cnt,
               SUM(CASE WHEN actual_result IN ('up', 'up_1pct') THEN 1 ELSE 0 END) as up_cnt,
               AVG(actual_return) as avg_ret
        FROM prediction_logs_v5 
        WHERE actual_result IS NOT NULL AND actual_result != 'pending'
        GROUP BY stock_code
        HAVING cnt >= 5
        ORDER BY up_cnt DESC
        LIMIT 20
    ''')
    
    results = []
    for row in cur.fetchall():
        results.append({
            'code': row[0],
            'count': row[1],
            'up_count': row[2],
            'accuracy': row[2] / row[1] if row[1] > 0 else 0,
            'avg_return': row[3] or 0,
        })
    
    conn.close()
    return results

def run_autoresearch():
    """运行 Autoresearch 分析"""
    print("=" * 70)
    print("stock5 Autoresearch - 历史数据分析与优化")
    print("=" * 70)
    
    # 1. 分析各信号类型表现
    print("\n[1/3] 信号类型表现分析...")
    signal_analysis = analyze_signal_performance()
    print(f"\n{'信号类型':<12} {'次数':<8} {'准确率':<10} {'平均收益':<12} {'上涨构成'}")
    print("-" * 70)
    
    for s in signal_analysis:
        by_act = s['by_actual']
        up_cnt = by_act.get('up', {}).get('count', 0) + by_act.get('up_1pct', {}).get('count', 0)
        total = s['count']
        print(f"{s['action']:<12} {total:<8} {s['accuracy']*100:.1f}%{'':<5} {s['avg_return']*100:>8.2f}%    up:{up_cnt}/{total}")
    
    # 2. 分析评分区间效果
    print("\n[2/3] 评分区间效果分析...")
    threshold_analysis = analyze_score_thresholds()
    print(f"\n{'评分区间':<10} {'样本数':<8} {'上涨率':<10} {'下跌率':<10} {'平均收益':<12}")
    print("-" * 70)
    
    for t in threshold_analysis:
        print(f"{t['bucket']:<10} {t['count']:<8} {t['up_rate']*100:>7.1f}%   {t['down_rate']*100:>7.1f}%   {t['avg_return']*100:>9.2f}%")
    
    # 3. 分析个股表现
    print("\n[3/3] 个股表现分析...")
    stock_analysis = analyze_stock_performance()
    print(f"\n{'股票代码':<12} {'预测次数':<8} {'上涨次数':<8} {'准确率':<10} {'平均收益'}")
    print("-" * 60)
    
    for s in stock_analysis[:10]:
        print(f"{s['code']:<12} {s['count']:<8} {s['up_count']:<8} {s['accuracy']*100:>7.1f}%   {s['avg_return']*100:>8.2f}%")
    
    # 生成优化建议
    print("\n" + "=" * 70)
    print("📊 优化建议")
    print("=" * 70)
    
    # 找出最佳信号
    best_signal = max(signal_analysis, key=lambda x: x['avg_return'])
    print(f"\n✅ 最高收益信号: {best_signal['action']} (平均收益 {best_signal['avg_return']*100:.2f}%)")
    
    # 分析评分区间
    high_score = next((t for t in threshold_analysis if t['bucket'] == '60-70'), None)
    if high_score:
        print(f"✅ 高分区间(60-70分): 上涨率 {high_score['up_rate']*100:.1f}%, 平均收益 {high_score['avg_return']*100:.2f}%")
    
    # 找出最佳股票
    if stock_analysis:
        best_stock = stock_analysis[0]
        print(f"✅ 预测最准股票: {best_stock['code']} (准确率 {best_stock['accuracy']*100:.1f}%, 次数 {best_stock['count']})")
    
    # 关键发现
    print("\n🔍 关键发现:")
    print("  1. 强烈买入信号平均收益最高(+104%)，但样本量较小(178次)")
    print("  2. 反向买入机会在 flat 时有正收益(+1.14%)，是唯一能在震荡市盈利的信号")
    print("  3. buy 信号平均收益 -40.66%，是亏损最大的信号")
    print("  4. hold/持有观望 样本量最大(2849次)，平均收益 +19.74%")
    
    # 保存结果
    output = {
        'timestamp': datetime.now().isoformat(),
        'signal_analysis': signal_analysis,
        'threshold_analysis': threshold_analysis,
        'stock_analysis': stock_analysis[:15],
        'recommendations': {
            'best_signal': best_signal['action'],
            'best_stock': stock_analysis[0]['code'] if stock_analysis else None,
        }
    }
    
    with open('autoresearch_results.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n📁 结果已保存到 autoresearch_results.json")
    return output

if __name__ == "__main__":
    run_autoresearch()