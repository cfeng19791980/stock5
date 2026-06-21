# -*- coding: utf-8 -*-
"""
组合管理器
读取用户持仓和资金，结合预测评分生成买卖建议

数据文件:
- account.json: {"total_cash": 100000, "available_cash": 95000}
- holdings.json: [{"code": "600519.SH", "name": "贵州茅台", "buyPrice": 1600, "buyQty": 100, "entryDate": "2024-01-15"}]
"""
import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, date


PROJECT_DIR = Path(__file__).parent.parent
ACCOUNT_FILE = PROJECT_DIR / "account.json"
HOLDINGS_FILE = PROJECT_DIR / "holdings.json"


@dataclass
class Holding:
    """单条持仓"""
    code: str           # "600519.SH"
    name: str           # "贵州茅台"
    buy_price: float    # 买入价
    buy_qty: int        # 买入股数
    entry_date: str     # "2024-01-15"
    current_price: float = 0      # 当前价（从预测结果填充）
    current_score: float = 0      # 当前评分（从预测结果填充）

    @property
    def cost(self) -> float:
        return self.buy_price * self.buy_qty

    @property
    def market_value(self) -> float:
        return self.current_price * self.buy_qty

    @property
    def pnl_ratio(self) -> float:
        if self.buy_price <= 0:
            return 0
        return (self.current_price - self.buy_price) / self.buy_price


@dataclass
class Portfolio:
    """组合快照"""
    total_cash: float = 100000
    holdings: List[Holding] = field(default_factory=list)

    @property
    def position_value(self) -> float:
        return sum(h.market_value for h in self.holdings)

    @property
    def position_cost(self) -> float:
        return sum(h.cost for h in self.holdings)

    @property
    def total_value(self) -> float:
        return self.total_cash + self.position_value

    @property
    def cash_ratio(self) -> float:
        if self.total_value <= 0:
            return 0
        return self.total_cash / self.total_value

    @property
    def holding_count(self) -> int:
        return len(self.holdings)


class PortfolioManager:
    """组合管理器 — 读取持仓/资金，结合分析结果生成买卖建议"""

    def __init__(self, project_dir: Path = None):
        self.project_dir = project_dir or PROJECT_DIR
        self.account_file = self.project_dir / "account.json"
        self.holdings_file = self.project_dir / "holdings.json"

    # ---- 读取 ----

    def load_account(self) -> Dict:
        """读取账户资金"""
        if self.account_file.exists():
            try:
                return json.loads(self.account_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, KeyError):
                pass
        return {"total_cash": 100000}

    def load_holdings(self) -> List[Dict]:
        """读取持仓列表"""
        if self.holdings_file.exists():
            try:
                return json.loads(self.holdings_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, KeyError):
                pass
        return []

    def load_portfolio(self, analysis_stocks: List[Dict] = None) -> Portfolio:
        """
        从文件构建组合快照，可选地用预测结果填充当前价和评分

        Args:
            analysis_stocks: result_v5.json 中的 stocks 列表
        """
        account = self.load_account()
        raw_holdings = self.load_holdings()

        # 构建 code -> stock 索引 (支持带后缀、不带后缀、纯数字三种匹配)
        stock_map = {}
        if analysis_stocks:
            for s in analysis_stocks:
                code_raw = str(s.get("code", ""))
                stock_map[code_raw] = s
                # 不带后缀
                code_short = code_raw.replace(".SH", "").replace(".SZ", "")
                if code_short != code_raw:
                    stock_map[code_short] = s
                # 纯数字
                code_num = "".join(c for c in code_raw if c.isdigit())
                stock_map[code_num] = s

        holdings = []
        for h in raw_holdings:
            code = str(h.get("code", ""))
            # 三层匹配：精确 → 去后缀 → 纯数字
            stock = stock_map.get(code)
            if not stock:
                code_short = code.replace(".SH", "").replace(".SZ", "")
                stock = stock_map.get(code_short)
            if not stock:
                code_num = "".join(c for c in code if c.isdigit())
                stock = stock_map.get(code_num)

            holding = Holding(
                code=code,
                name=stock.get("name") if stock else h.get("name", code),
                buy_price=float(h.get("buyPrice", h.get("buy_price", 0))),
                buy_qty=int(h.get("buyQty", h.get("buy_qty", 0))),
                entry_date=str(h.get("entryDate", h.get("entry_date", ""))),
                current_price=float(stock.get("close", 0)) if stock else 0,
                current_score=float(stock.get("score", 0)) if stock else 0,
            )
            holdings.append(holding)

        return Portfolio(
            total_cash=float(account.get("total_cash", 100000)),
            holdings=holdings,
        )

    # ---- 保存 ----

    def save_account(self, total_cash: float):
        """保存账户资金"""
        data = {"total_cash": total_cash}
        self.account_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def save_holdings(self, holdings: List[Dict]):
        """保存持仓"""
        self.holdings_file.write_text(json.dumps(holdings, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- 策略决策 ----

    @staticmethod
    def compute_recommendation(
        portfolio: Portfolio,
        analysis_stocks: List[Dict],
        config: Dict = None,
    ) -> Dict:
        """
        核心方法：根据持仓+资金+预测评分，生成买卖建议

        Args:
            portfolio: 当前组合快照
            analysis_stocks: 预测结果列表
            config: 策略配置（阈值等）

        Returns:
            {
                "portfolio": {total_cash, position_value, total_value, holding_count},
                "holdings": [{code, name, cost, market_value, pnl_pct, score, action, reason, ...}],
                "buy_signals": [{code, name, score, price, suggested_amount, suggested_shares, ...}],
                "summary": {total_buy_amount, total_sell_amount, ...}
            }
        """
        config = config or {}
        buy_threshold = config.get("buy_threshold", 55)
        strong_buy_threshold = config.get("strong_buy_threshold", 70)
        sell_threshold = config.get("sell_threshold", 30)
        max_positions = config.get("max_positions", 5)
        max_single_pct = config.get("max_single_pct", 0.20)
        stop_loss_pct = config.get("stop_loss_pct", 0.07)
        take_profit_pct = config.get("take_profit_pct", 0.15)

        # ---- 构建 code -> holding 索引 (三层匹配) ----
        holding_map: Dict[str, Holding] = {}
        for h in portfolio.holdings:
            holding_map[h.code] = h
            short = h.code.replace(".SH", "").replace(".SZ", "")
            if short != h.code:
                holding_map[short] = h
            num = "".join(c for c in h.code if c.isdigit())
            holding_map[num] = h

        # ---- 分析现有持仓 ----
        holdings_result = []
        total_sell_amount = 0.0

        for h in portfolio.holdings:
            action = "hold"
            reason = ""
            sell_shares = 0

            if h.buy_price > 0 and h.current_price > 0:
                pnl = h.pnl_ratio

                # 止损检查
                if pnl <= -stop_loss_pct:
                    action = "sell_all"
                    sell_shares = h.buy_qty
                    reason = f"跌破止损线({stop_loss_pct*100:.0f}%)，当前亏损{pnl*100:.1f}%"
                # 止盈检查
                elif pnl >= take_profit_pct:
                    action = "sell_half"
                    sell_shares = h.buy_qty // 2
                    reason = f"达到止盈线({take_profit_pct*100:.0f}%)，当前盈利{pnl*100:.1f}%"
                # 低评分 → 建议卖出
                elif h.current_score < sell_threshold:
                    action = "sell_suggest"
                    reason = f"评分{h.current_score:.0f}低于卖出阈值{sell_threshold}"
                # 高评分 → 建议加仓
                elif h.current_score >= strong_buy_threshold:
                    action = "add_position"
                    reason = f"评分{h.current_score:.0f}≥{strong_buy_threshold}，强烈建议加仓"
                # 中等评分 → 持有
                else:
                    reason = f"评分{h.current_score:.0f}，持有观望"

            if sell_shares > 0:
                total_sell_amount += sell_shares * h.current_price

            holdings_result.append({
                "code": h.code,
                "name": h.name,
                "buy_price": round(h.buy_price, 2),
                "buy_qty": h.buy_qty,
                "current_price": round(h.current_price, 2),
                "market_value": round(h.market_value, 2),
                "pnl_pct": round(h.pnl_ratio * 100, 2),
                "score": round(h.current_score, 1),
                "entry_date": h.entry_date,
                "action": action,
                "reason": reason,
                "sell_shares": sell_shares,
            })

        # ---- 分析买入信号 ----
        # 过滤已有持仓的股票
        holding_codes = set()
        for h in portfolio.holdings:
            holding_codes.add(h.code)
            holding_codes.add(h.code.replace(".SH", "").replace(".SZ", ""))
            holding_codes.add("".join(c for c in h.code if c.isdigit()))

        buy_candidates = []
        for stock in analysis_stocks:
            code = str(stock.get("code", ""))
            code_short = code.replace(".SH", "").replace(".SZ", "")
            code_num = "".join(c for c in code if c.isdigit())
            if code in holding_codes or code_short in holding_codes or code_num in holding_codes:
                continue

            score = float(stock.get("score", 0))
            if score < buy_threshold:
                continue

            price = float(stock.get("close", 0))
            if price <= 0:
                continue

            # 仓位权重
            if score >= strong_buy_threshold:
                weight = max_single_pct
            else:
                weight = max_single_pct * 0.6  # 普通买入60%仓位

            suggested_amount = portfolio.total_cash * weight
            suggested_shares = int(suggested_amount / price / 100) * 100

            buy_candidates.append({
                "code": code,
                "name": stock.get("name", ""),
                "score": round(score, 1),
                "price": round(price, 2),
                "pct_chg": round(float(stock.get("pct_chg", 0)), 2),
                "weight": round(weight * 100, 1),
                "suggested_amount": round(suggested_amount, 0),
                "suggested_shares": suggested_shares,
                "signal": "strong_buy" if score >= strong_buy_threshold else "buy",
            })

        # 按评分排序
        buy_candidates.sort(key=lambda x: x["score"], reverse=True)

        # 限制最大持仓数
        current_count = len(portfolio.holdings)
        slots_available = max(0, max_positions - current_count)
        buy_signals = buy_candidates[:slots_available]

        total_buy_amount = sum(b["suggested_amount"] for b in buy_signals)

        # ---- 汇总 ----
        return {
            "portfolio": {
                "total_cash": round(portfolio.total_cash, 2),
                "position_value": round(portfolio.position_value, 2),
                "position_cost": round(portfolio.position_cost, 2),
                "total_value": round(portfolio.total_value, 2),
                "cash_ratio": round(portfolio.cash_ratio * 100, 1),
                "holding_count": portfolio.holding_count,
            },
            "holdings": holdings_result,
            "buy_signals": buy_signals,
            "summary": {
                "total_sell_amount": round(total_sell_amount, 2),
                "total_buy_amount": round(total_buy_amount, 2),
                "buy_candidates": len(buy_candidates),
                "slots_available": slots_available,
                "buy_threshold": buy_threshold,
                "sell_threshold": sell_threshold,
            },
        }


def load_and_recommend(config: Dict = None) -> Dict:
    """便捷入口：读文件 → 出建议"""
    from .config_strategy import RESULT_FILE
    import json

    pm = PortfolioManager()

    # 加载预测结果
    result_file = pm.project_dir / "result_v5.json"
    if not result_file.exists() and RESULT_FILE.exists():
        result_file = RESULT_FILE
    analysis = json.loads(result_file.read_text(encoding="utf-8")) if result_file.exists() else {}
    stocks = analysis.get("stocks", [])

    # 构建组合
    portfolio = pm.load_portfolio(analysis_stocks=stocks)

    # 生成建议
    return PortfolioManager.compute_recommendation(portfolio, stocks, config=config)
