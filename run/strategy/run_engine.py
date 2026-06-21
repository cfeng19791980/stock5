# -*- coding: utf-8 -*-
"""策略引擎 CLI 入口 — 输出 JSON 到 stdout"""
import sys, json, os

# 确保项目根在 path 中
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from strategy.strategy_engine import StrategyEngine
engine = StrategyEngine()
result = engine.generate_recommendations()
print(json.dumps(result, ensure_ascii=False, indent=2))
