# -*- coding: utf-8 -*-
"""
bull_bear.py — Stock5 v6 LLM 多空双视角分析

基于 fine-r1-7b-i1 (LM Studio 1234端口)
场景自适应: 财报季 / 突发利空 / 行业政策 / 常规

用法:
    from v6.bull_bear import analyze
    result = analyze(code, name, indicators="...", news="...", scenario="normal")
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import json
import requests
from datetime import datetime

LLM_URL = "http://127.0.0.1:1234/v1/chat/completions"
LLM_MODEL = "fine-r1-7b-i1"

# ==================== 场景 Prompt ====================
PROMPTS = {
    "normal": """你是A股量化分析师。分析以下股票，从多头和空头两个角度分别评价。
输出严格JSON格式，不要任何其他文字。

股票: {code} {name}
技术数据: {indicators}
最新公告: {news}

{{
  "bull": {{"score": 整数0-100, "reason": "最多20字"}},
  "bear": {{"score": 整数0-100, "reason": "最多20字"}},
  "verdict": "buy/hold/sell",
  "confidence": 整数0-100
}}""",

    "earnings": """你是A股量化分析师。当前是财报季，重点分析财报数据对股价的影响。
输出严格JSON格式。

股票: {code} {name}
财务数据: {indicators}
最新公告: {news}

请特别注意营收增速、利润增速、毛利率变化、ROE等财务指标。
{{
  "bull": {{"score": 整数0-100, "reason": "最多20字"}},
  "bear": {{"score": 整数0-100, "reason": "最多20字"}},
  "verdict": "buy/hold/sell",
  "confidence": 整数0-100,
  "key_metrics": ["季度营收增速", "净利润增速"]
}}""",

    "panic": """你是A股量化分析师。当前出现突发利空消息，请冷静分析影响。
输出严格JSON格式。

股票: {code} {name}
当前数据: {indicators}
突发消息: {news}

请评估该利空的影响程度、持续性和股价是否已过度反应。
{{
  "bull": {{"score": 整数0-100, "reason": "最多20字"}},
  "bear": {{"score": 整数0-100, "reason": "最多20字"}},
  "verdict": "buy/hold/sell",
  "confidence": 整数0-100,
  "impact_level": "high/medium/low"
}}""",

    "policy": """你是A股量化分析师。当前发生行业政策变化，请分析对个股的传导影响。
输出严格JSON格式。

股票: {code} {name}
所属行业: {sector}
当前数据: {indicators}
政策变化: {news}

请从政策受益/受损两个方向分别评估。
{{
  "bull": {{"score": 整数0-100, "reason": "最多20字"}},
  "bear": {{"score": 整数0-100, "reason": "最多20字"}},
  "verdict": "buy/hold/sell",
  "confidence": 整数0-100
}}""",
}


def detect_scenario(news: str) -> str:
    """自动检测场景"""
    if not news:
        return "normal"
    news_lower = news.lower()
    
    # 财报季关键词
    earnings_kw = ['营收', '利润', '净利润', '毛利率', '财报', '季报', '年报', '收入', '增长', '下滑']
    if any(kw in news for kw in earnings_kw):
        return "earnings"
    
    # 利空关键词
    panic_kw = ['跌停', '暴跌', '利空', '处罚', '调查', 'st', '退市', '亏', '诉讼', '违约']
    if any(kw in news for kw in panic_kw):
        return "panic"
    
    # 政策关键词
    policy_kw = ['政策', '产业', '补贴', '税收', '监管', '法规', '扶持', '限制']
    if any(kw in news for kw in policy_kw):
        return "policy"
    
    return "normal"


def analyze(code: str, name: str,
            indicators: str = "",
            news: str = "",
            scenario: str = "auto",
            sector: str = "") -> dict:
    """
    调用 fine-r1 进行 Bull/Bear 双视角分析
    
    返回:
        {
            "bull": {"score": int, "reason": str},
            "bear": {"score": int, "reason": str},
            "verdict": str,
            "confidence": int,
            "scenario": str,
            "success": bool
        }
    """
    if scenario == "auto":
        scenario = detect_scenario(news)
    
    prompt_template = PROMPTS.get(scenario, PROMPTS["normal"])
    prompt = prompt_template.format(
        code=code, name=name,
        indicators=indicators,
        news=news,
        sector=sector
    )
    
    try:
        resp = requests.post(LLM_URL, json={
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": "你是有10年A股经验的量化研究员。只说JSON。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 512,
        }, timeout=30)
        
        raw = resp.json()['choices'][0]['message']['content']
        
        # 提取JSON
        if '```json' in raw:
            raw = raw.split('```json')[1].split('```')[0]
        elif '```' in raw:
            raw = raw.split('```')[1].split('```')[0]
        
        # 清理BOM/非ASCII
        raw = raw.strip().lstrip('\ufeff')
        
        data = json.loads(raw)
        
        return {
            'bull': {'score': data.get('bull', {}).get('score', 50),
                     'reason': data.get('bull', {}).get('reason', '')[:20]},
            'bear': {'score': data.get('bear', {}).get('score', 50),
                     'reason': data.get('bear', {}).get('reason', '')[:20]},
            'verdict': data.get('verdict', 'hold'),
            'confidence': data.get('confidence', 50),
            'scenario': scenario,
            'success': True,
        }
    
    except Exception as e:
        return {
            'bull': {'score': 50, 'reason': ''},
            'bear': {'score': 50, 'reason': ''},
            'verdict': 'hold',
            'confidence': 0,
            'scenario': scenario,
            'success': False,
            'error': str(e),
        }


# ==================== 自测 ====================
if __name__ == '__main__':
    # 测试四个场景
    tests = [
        ("normal", "技术面偏多", "无重大消息"),
        ("earnings", "收盘78.50, 涨跌幅+2.3%, RSI=62", "存储芯片Q2营收环比增长15%"),
        ("panic", "跌停, 换手率0.5%", "公司收到证监会立案调查通知"),
        ("policy", "行业整体估值偏低", "半导体产业获国家大基金三期注资"),
    ]
    
    for scenario, indicators, news in tests:
        print(f"\n=== 场景: {scenario} ===")
        result = analyze("603986.SH", "兆易创新", indicators, news, "auto")
        if result['success']:
            b = result['bull']
            be = result['bear']
            print(f"  多头: {b['score']}分 - {b['reason']}")
            print(f"  空头: {be['score']}分 - {be['reason']}")
            print(f"  结论: {result['verdict']} (置信度{result['confidence']})")
            print(f"  场景识别: {result['scenario']}")
        else:
            print(f"  ❌ {result.get('error', '失败')}")
