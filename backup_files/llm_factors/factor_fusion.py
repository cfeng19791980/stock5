# -*- coding: utf-8 -*-
"""
factor_fusion.py — 多因子融合评分器
融合技术指标评分 + LLM因子评分，输出最终分数

用法:
    from factor_fusion import get_fusion_score
    score = get_fusion_score(code, latest_row, date='2026-05-06')
"""

import sqlite3, json, os, sys, math
import pandas as pd
import numpy as np
from datetime import datetime

DB_PATH = r'E:\\stock5\\stocks.db'

# 异动因子权重
ANOMALY_WEIGHT = 0.10      # 异动因子权重
LLM_INSIGHT_WEIGHT = 0.10  # LLM洞察权重

# 特征列表（技术面核心特征）
TECH_FEATURES = ['pct_chg', 'ma5_ratio', 'ma10_ratio', 'ma20_ratio',
                 'rsi6', 'macd', 'k', 'd', 'volume_ratio', 'high_low_ratio']


def get_tech_score(row):
    """
    技术面评分（0-100）
    沿用之前验证过的多维度加权方案
    """
    scores = {}
    
    # 1. 趋势分
    close = row['close'] if pd.notna(row.get('close', 0)) else 0
    ma5r = row['ma5_ratio'] if pd.notna(row.get('ma5_ratio', 0)) else 1.0
    ma10r = row['ma10_ratio'] if pd.notna(row.get('ma10_ratio', 0)) else 1.0
    ma20r = row['ma20_ratio'] if pd.notna(row.get('ma20_ratio', 0)) else 1.0
    
    if ma5r > 1.02 and ma10r > 1.02:
        trend = 80
    elif ma5r > 1.0 and ma10r > 1.0:
        trend = 65
    elif ma5r < 0.98 and ma10r < 0.98:
        trend = 20
    elif ma5r < 1.0 and ma10r < 1.0:
        trend = 35
    else:
        trend = 50
    scores['trend'] = trend
    
    # 2. 动量分 (RSI + MACD + KDJ)
    rsi6 = row['rsi6'] if pd.notna(row.get('rsi6', 0)) else 50
    macd = row['macd'] if pd.notna(row.get('macd', 0)) else 0
    k_val = row['k'] if pd.notna(row.get('k', 0)) else 50
    d_val = row['d'] if pd.notna(row.get('d', 0)) else 50
    
    momentum = 50
    if rsi6 < 30:
        momentum = 20
    elif 30 <= rsi6 <= 45:
        momentum = 60
    elif 55 < rsi6 <= 70:
        momentum = 45
    elif rsi6 > 70:
        momentum = 30
    
    if macd > 0 and rsi6 <= 55:
        momentum += 15
    if k_val > d_val and k_val < 80:
        momentum += 10
    momentum = np.clip(momentum, 0, 100)
    scores['momentum'] = momentum
    
    # 3. 量能分
    if 'vr' in row.index and pd.notna(row['vr']):
        vr = row['vr']
    elif 'volume_ratio' in row.index and pd.notna(row['volume_ratio']):
        vr = row['volume_ratio']
    else:
        vr = 1.0
    if 0.8 <= vr <= 1.4:
        vol = 70
    elif vr > 1.4:
        vol = 40
    elif vr < 0.5:
        vol = 30
    elif vr < 0.8:
        vol = 50
    else:
        vol = 50
    scores['volume'] = vol
    
    # 4. 综合技术分
    tech_score = trend * 0.35 + momentum * 0.40 + vol * 0.25
    return int(tech_score), scores


def get_anomaly_signals(code, date=None):
    """
    从 daily_features 表获取异动和 LLM 分析数据。
    """
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT anomaly_flag, anomaly_reasons, anomaly_severity, llm_analysis "
            "FROM daily_features WHERE code=? AND trade_date=? "
            "ORDER BY id DESC LIMIT 1",
            (code, date)
        ).fetchone()
        if not row:
            return None
        result = {
            'anomaly_flag': row[0] if row[0] else 0,
            'anomaly_reasons': json.loads(row[1]) if row[1] else [],
            'anomaly_severity': row[2] if row[2] else 'none',
        }
        if row[3]:
            try:
                result['llm_analysis'] = json.loads(row[3])
            except json.JSONDecodeError:
                result['llm_analysis'] = {}
        else:
            result['llm_analysis'] = {}
        return result
    except Exception as e:
        return None
    finally:
        conn.close()


def calc_anomaly_score(anomaly_signal):
    """根据异动信号计算评分"""
    if anomaly_signal is None:
        return 50, "no_data"
    flag = anomaly_signal.get('anomaly_flag', 0)
    severity = anomaly_signal.get('anomaly_severity', 'none')
    reasons = anomaly_signal.get('anomaly_reasons', [])
    if flag == 0:
        return 50, "normal"
    if severity == 'high':
        return 70, f"high: {'; '.join(reasons)}"
    elif severity == 'medium':
        return 55, f"medium: {'; '.join(reasons)}"
    else:
        return 45, f"low: {'; '.join(reasons)}"


def calc_llm_insight_score(llm_analysis):
    """根据 LLM 分析结果计算洞察评分"""
    if not llm_analysis:
        return 50
    confidence = llm_analysis.get('confidence', 50)
    if isinstance(confidence, (int, float)):
        return max(0, min(100, confidence))
    return 50


def get_fundamental_signals(date, session='afternoon'):
    """
    从数据库获取当天因子信号。
    
    资金流向信号从 fund_flow 表读取（实时采集），
    不再依赖 factor_signals 的静态数据。
    
    Returns:
        {code: {'news': -1~1, 'fin': 0-100, 'fund': 0-100, 'conf': 0-100}}
    """
    conn = sqlite3.connect(DB_PATH)
    
    # 1. 从 factor_signals 表读新闻/财务/LLM置信度
    cursor = conn.cursor()
    cursor.execute('''
        SELECT code, news_score, fin_score, fund_score, llm_confidence
        FROM factor_signals
        WHERE date=? AND session=?
    ''', (date, session))
    rows = cursor.fetchall()
    
    signals = {}
    for r in rows:
        signals[r[0]] = {
            'news': r[1] if r[1] is not None else 0,
            'fin': r[2] if r[2] is not None else 50,
            'fund': r[3] if r[3] is not None else 50,
            'conf': r[4] if r[4] is not None else 50,
        }
    
    # 2. 从 fund_flow 表读取真实资金流向，覆盖 fund_score
    try:
        fund_rows = conn.execute('''
            SELECT code, main_net, main_pct, close, pct_chg
            FROM fund_flow WHERE date=?
        ''', (date,)).fetchall()
        
        for r in fund_rows:
            code = r[0]
            main_net = r[1] if r[1] is not None else 0
            main_pct = r[2] if r[2] is not None else 0
            
            # 将主力资金占比映射到 fund_score (0~100)
            # main_pct > 3% → 80-100 (大幅净流入)
            # main_pct 1~3% → 60-80 (净流入)
            # main_pct -1~1% → 40-60 (中性)
            # main_pct -3~-1% → 20-40 (净流出)
            # main_pct < -3% → 0-20 (大幅净流出)
            if main_pct > 3:
                fund_score = min(100, 80 + (main_pct - 3) * 5)
            elif main_pct > 1:
                fund_score = 60 + (main_pct - 1) * 10
            elif main_pct > -1:
                fund_score = 50 + main_pct * 10
            elif main_pct > -3:
                fund_score = 40 + (main_pct + 1) * 10
            else:
                fund_score = max(0, 20 + (main_pct + 3) * 5)
            
            if code in signals:
                signals[code]['fund'] = int(fund_score)
                # 有真实资金数据，略微提高置信度
                signals[code]['conf'] = min(100, signals[code]['conf'] + 5)
            else:
                signals[code] = {
                    'news': 0,
                    'fin': 50,
                    'fund': int(fund_score),
                    'conf': 30,  # 无新闻数据，置信度偏低
                }
    except Exception as e:
        pass  # fund_flow 表可能还没数据
    
    conn.close()
    return signals


def get_fusion_score(code, latest_row, date=None, session='afternoon', fund_signals=None):
    """
    多因子融合评分
    
    技术面权重: 0.50
    LLM因子权重: 0.30 (新闻0.15 + 异动0.10 + LLM洞察0.05)
    基本面权重: 0.20 (财务0.10 + 资金0.10)
    
    异动和LLM洞察来自 stream_collector 的实时数据。
    """
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    
    # 1. 技术面评分
    tech_score, breakdown = get_tech_score(latest_row)
    
    # 2. 基本面因子评分
    if fund_signals is None:
        fund_signals = get_fundamental_signals(date, session)
    
    fund_sig = fund_signals.get(code, {'news': 0, 'fin': 50, 'fund': 50, 'conf': 0})
    
    # 新闻情感转分数 (-1~1 → 0~100)
    news_score_adj = (fund_sig['news'] + 1) * 50  # [-1,1] → [0,100]
    news_score_adj = np.clip(news_score_adj, 0, 100)
    
    # 3. 异动因子（从 daily_features 读取）
    anomaly_signal = get_anomaly_signals(code, date)
    anomaly_score, anomaly_reason = calc_anomaly_score(anomaly_signal)
    
    llm_analysis = anomaly_signal.get('llm_analysis', {}) if anomaly_signal else {}
    llm_insight_score = calc_llm_insight_score(llm_analysis)
    
    # 4. 融合（带异动因子）
    conf = fund_sig['conf'] / 100.0
    has_anomaly = anomaly_signal and anomaly_signal.get('anomaly_flag', 0) == 1
    
    if has_anomaly and conf >= 0.6:
        # 有实时异动数据 + 高置信度LLM
        final = (tech_score * 0.50 +
                 news_score_adj * 0.10 +
                 fund_sig['fin'] * 0.10 +
                 fund_sig['fund'] * 0.10 +
                 anomaly_score * 0.10 +
                 llm_insight_score * 0.10)
    elif has_anomaly:
        # 有异动但LLM置信度一般
        final = (tech_score * 0.55 +
                 news_score_adj * 0.10 +
                 fund_sig['fin'] * 0.10 +
                 fund_sig['fund'] * 0.10 +
                 anomaly_score * 0.10 +
                 llm_insight_score * 0.05)
    elif conf < 0.05:
        # LLM因子未就绪(fin=50, conf=0), 仅用技术面+资金流
        # fund_score已在get_fundamental_signals中从腾讯行情实时计算
        final = tech_score * 0.80 + fund_sig['fund'] * 0.20
    else:
        # 无实时异动，传统LLM因子权重低
        final = tech_score * 0.80 + news_score_adj * 0.05 + fund_sig['fin'] * 0.05 + fund_sig['fund'] * 0.10
    
    return int(final), {
        'tech_score': tech_score,
        'trend': breakdown.get('trend', 50),
        'momentum': breakdown.get('momentum', 50),
        'volume': breakdown.get('volume', 50),
        'news_score': round(news_score_adj, 1),
        'fin_score': fund_sig['fin'],
        'fund_score': fund_sig['fund'],
        'confidence': fund_sig['conf'],
        'anomaly_score': anomaly_score,
        'anomaly_reason': anomaly_reason,
        'llm_insight_score': llm_insight_score,
        'fusion_weight': '50/20/20/10' if conf >= 0.6 else ('65/20/10/5' if conf >= 0.3 else '80/10/5/5'),
    }


def get_advice(final_score, tech_breakdown=None):
    """根据最终评分生成交易建议"""
    if final_score >= 75:
        return 'buy_strong', f"强烈买入(评分{final_score})"
    elif final_score >= 65:
        return 'buy', f"建议买入(评分{final_score})"
    elif final_score >= 55:
        return 'light_buy', f"轻仓试探(评分{final_score})"
    elif final_score <= 25:
        return 'sell_strong', f"强烈卖出(评分{final_score})"
    elif final_score <= 35:
        return 'sell', f"建议卖出(评分{final_score})"
    else:
        return 'hold', f"持有观望(评分{final_score})"


if __name__ == '__main__':
    # 测试
    import sqlite3
    
    # 从数据库取最新数据
    codes = [s['code'] for s in json.load(open(r'E:\csi10\result_v5.json', 'r', encoding='utf-8'))['stocks']]
    
    conn = sqlite3.connect(DB_PATH)
    signals = get_fundamental_signals('2026-05-06', 'afternoon')
    
    print(f"{'='*60}")
    print("多因子融合评分测试 (2026-05-06)")
    print(f"{'='*60}")
    
    for code in codes[:10]:
        df = pd.read_sql(f"SELECT * FROM daily_price WHERE code='{code}' ORDER BY date DESC LIMIT 1", conn)
        if len(df) == 0:
            continue
        
        row = df.iloc[0]
        score, info = get_fusion_score(code, row, '2026-05-06', 'afternoon', signals)
        advice, reason = get_advice(score)
        
        has_fund = 'Y' if code in signals else 'N'
        print(f"  {code} [{has_fund}]: 评分{score:3d} (技术{info['tech_score']} 新闻{info['news_score']:.0f} "
              f"财务{info['fin_score']} 资金{info['fund_score']}) → {reason}")
    
    conn.close()

# 导入补充函数
try:
    from qwen_bull_bear import get_qwen_bull_bear
except ImportError:
    pass
