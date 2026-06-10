# -*- coding: utf-8 -*-
"""
factor_runner.py — 多因子采集守护进程（三合一）
功能：
  1. 基本面评分 (fin_score)   — LLM 批量分析财务健康度
  2. 新闻情感评分 (news_score) — 东方财富公告采集 + LLM 情感分析
  3. 资金流向评分 (fund_score) — 东方财富资金流 API
  4. 大盘/板块因子           → macro_factors 表

GUI 通过 FACTOR_RUNNER 引用此文件，使用 --daemon 模式启动。

运行:
  python factor_runner.py                    # 单次全量
  python factor_runner.py --daemon           # 守护进程（交易日每小时）
  python factor_runner.py --quick            # 跳过LLM（仅大盘+资金流）
  python factor_runner.py --stop             # 停止守护进程
"""

import sys, os, json, sqlite3, time, re, logging, signal
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path

# ===== 配置 =====
PROJECT_DIR = Path(__file__).parent.parent.absolute()
DB_PATH = str(PROJECT_DIR / 'stocks.db')
CSV_PATH = str(PROJECT_DIR / '波段股票Top30.csv')
PID_FILE = str(PROJECT_DIR / 'factor_collection.pid')
LOG_FILE = str(PROJECT_DIR / 'logs' / 'factor_collection.log')
LOG_DIR = str(PROJECT_DIR / 'logs')

os.makedirs(LOG_DIR, exist_ok=True)

# LLM 配置
LLM_URL = 'http://127.0.0.1:1234/v1/chat/completions'
LLM_MODEL = 'fine-r1-7b-i1'
BATCH_SIZE = 10

# 日志
logger = logging.getLogger('factor_runner')
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logger.addHandler(_handler)
logger.setLevel(logging.INFO)
_file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
_file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logger.addHandler(_file_handler)

# 股票名称（6位代码）
STOCK_NAMES = {
    '605196':'华通线缆','688028':'沃尔德','688195':'腾景科技','688233':'神工股份',
    '688519':'南亚新材','002353':'杰瑞股份','002384':'东山精密','600183':'生益科技',
    '603876':'鼎胜新材','603986':'兆易创新','688416':'恒烁股份','688521':'芯原股份',
    '688676':'金盘科技','300136':'信维通信','603225':'新凤鸣','688308':'欧科亿',
    '688388':'嘉元科技','688556':'高测股份','600118':'中国卫星','601231':'环旭电子',
    '688658':'悦康药业','688668':'鼎通科技','688788':'科思股份','002202':'金风科技',
    '002916':'深南电路','300604':'长川科技','603228':'景旺电子','688698':'伟创电气',
    '002460':'赣锋锂业','300476':'胜宏科技',
}

running = True

def signal_handler(signum, frame):
    global running
    logger.info("收到退出信号，准备停止...")
    running = False

# ========== 工具 ==========

def call_llm(prompt, max_tokens=800, timeout=120, temperature=0.1):
    try:
        res = requests.post(LLM_URL, json={
            'model': LLM_MODEL,
            'messages': [
                {'role': 'system', 'content': '你是A股基本面分析师。只输出数据行，不要Markdown表格、不要分隔线、不要额外说明。每行一个。'},
                {'role': 'user', 'content': prompt}
            ],
            'max_tokens': max_tokens, 'temperature': temperature,
        }, timeout=(10, timeout))
        data = res.json()
        if 'choices' in data:
            return data['choices'][0]['message']['content']
        return f"API Error: {json.dumps(data)[:200]}"
    except Exception as e:
        return f"请求失败: {e}"

def init_db(conn):
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS factor_signals (
        code TEXT NOT NULL, date TEXT NOT NULL, session TEXT DEFAULT 'afternoon',
        news_score REAL DEFAULT 0, news_count INTEGER DEFAULT 0, news_sentiment TEXT,
        fin_score REAL DEFAULT 50, revenue_growth REAL, profit_growth REAL, roe REAL, gross_margin REAL,
        fund_score REAL DEFAULT 50, main_net_inflow REAL, main_ratio REAL,
        llm_summary TEXT, llm_confidence REAL DEFAULT 0, created_at TEXT,
        PRIMARY KEY (code, date, session)
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS macro_factors (
        id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, update_time TEXT,
        hs300_close REAL, hs300_pct REAL, zz500_close REAL, zz500_pct REAL,
        hs300_ma5 REAL, hs300_ma20 REAL, hs300_trend TEXT,
        zz500_ma5 REAL, zz500_ma20 REAL, zz500_trend TEXT,
        advance_decline_ratio REAL, market_volume REAL,
        top_sector TEXT, sector_rotation REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    # 兼容旧��：缺少 news_sentiment 列则加
    try:
        cur.execute("ALTER TABLE factor_signals ADD COLUMN news_sentiment TEXT")
    except:
        pass
    conn.commit()

def get_codes():
    return list(STOCK_NAMES.keys())

# ====================================================================
# 模块1: 基本面 (fin_score)
# ====================================================================

def collect_fundamental(conn, codes_6digit):
    logger.info("\n=== 基本面因子(LLM评分) ===")
    today = datetime.now().strftime('%Y-%m-%d')
    all_results = {}
    batch_count = 0

    for i in range(0, len(codes_6digit), BATCH_SIZE):
        batch = codes_6digit[i:i+BATCH_SIZE]
        batch_count += 1
        stocks_text = ""
        for c6 in batch:
            code_full = f"{c6}.SH" if c6.startswith(('6','5')) else f"{c6}.SZ"
            df = pd.read_sql(f"SELECT close, pct_chg, amount FROM daily_price WHERE code='{code_full}' ORDER BY date DESC LIMIT 5", conn)
            name = STOCK_NAMES.get(c6, c6)
            if len(df) >= 3:
                avg_chg = df['pct_chg'].mean()
                avg_vol = df['amount'].mean()
                stocks_text += f"{code_full} {name}: 近5日均涨跌{avg_chg:.2f}%, 均成交额{avg_vol:.0f}\n"
            else:
                df5 = pd.read_sql(f"SELECT pct_chg FROM minute_5_price WHERE code='{c6}' ORDER BY datetime DESC LIMIT 5", conn)
                if len(df5) > 0:
                    avg_chg = df5['pct_chg'].mean()
                    stocks_text += f"{code_full}({name}): 近5周期均涨跌{avg_chg:.2f}%\n"
                else:
                    stocks_text += f"{code_full}({name}): 数据不足\n"

        prompt = f"""评分标准(0-100): 80-100优秀 60-79良好 40-59一般 20-39较差 0-19危险

{stocks_text}
每行: 代码|评分|等级|理由(10字内)"""

        logger.info(f"  📡 批次{batch_count}: {len(batch)}只...")
        t0 = time.time()
        content = call_llm(prompt)
        t1 = time.time()
        logger.info(f"  ⏱ {(t1-t0):.0f}s")

        lines = content.strip().split('\n')
        line_idx = 0
        for line in lines:
            line = line.strip()
            if not line or '---' in line: continue
            fin_score = None; grade = '一般'; reason = ''
            if '|' in line:
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 2:
                    code_part = parts[0]
                    try: fin_score = int(re.sub(r'[^0-9]', '', parts[1])[:3])
                    except: pass
                    if len(parts) >= 3: grade = parts[2] or parts[1]
                    if len(parts) >= 4: reason = parts[3]
            else:
                mc = re.match(r'([A-Z0-9.]+)', line)
                if mc:
                    code_part = mc.group(1)
                    nums = re.findall(r'\b(\d{2,3})\b', line)
                    if nums:
                        fin_score = int(nums[0])
                        after = line[line.index(str(nums[0])):] if str(nums[0]) in line else ''
                        ap = after.split(None, 3)
                        if len(ap) >= 2: grade = ap[1]; reason = ' '.join(ap[2:]) if len(ap) >= 3 else ''
            if fin_score is None: continue
            fin_score = max(0, min(100, fin_score))
            matched = False
            for c6 in batch:
                if c6 in code_part or code_part.startswith(c6) or code_part.replace('.SH','').replace('.SZ','').startswith(c6):
                    all_results[c6] = {'fin_score': fin_score, 'llm_summary': f"{grade}-{reason[:20]}", 'llm_confidence': min(80, fin_score)}
                    matched = True; break
            if not matched and line_idx < len(batch):
                c6 = batch[line_idx]
                all_results[c6] = {'fin_score': fin_score, 'llm_summary': f"{grade}-{reason[:20]}", 'llm_confidence': min(80, fin_score)}
            line_idx += 1
        time.sleep(1)
    return all_results

# ====================================================================
# 模块2: 新闻情感 (news_score)
# ====================================================================

NEWS_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://quote.eastmoney.com/"}

def fetch_news(code_6digit):
    try:
        resp = requests.get("https://np-anotice-stock.eastmoney.com/api/security/ann", params={
            "sr": -1, "page_size": 5, "page_index": 1, "ann_type": "A",
            "stock_list": code_6digit, "f_node": 0, "s_node": 0,
        }, headers=NEWS_HEADERS, timeout=10)
        if resp.status_code != 200: return []
        items = resp.json().get("data", {}).get("list", [])
        return [{"title": it.get("title",""), "content": it.get("abstract","")} for it in items[:5]]
    except: return []

def analyze_news_llm(code_6digit, name, news_list):
    if not news_list: return None
    news_text = "\n".join(f"- {n['title']}\n  {n['content'][:100]}" for n in news_list)
    try:
        resp = requests.post(LLM_URL, json={
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": "你是A股量化分析师。分析新闻公告输出JSON: {\"sentiment\":-1~1, \"confidence\":0-100, \"reason\":\"\"}"},
                {"role": "user", "content": f"股票: {name}({code_6digit})\n最新公告:\n{news_text}\n分析短期影响。"}
            ], "temperature": 0.05, "max_tokens": 256,
        }, timeout=30)
        if resp.status_code != 200: return None
        content = resp.json()["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if m:
            r = json.loads(m.group())
            return {"sentiment": float(r.get("sentiment",0)), "confidence": int(r.get("confidence",50)), "reason": r.get("reason","")}
    except: return None
    return None

def collect_news(codes_6digit):
    logger.info("\n=== 新闻情感因子 ===")
    results = {}
    for c6 in codes_6digit:
        name = STOCK_NAMES.get(c6, c6)
        logger.info(f"  [{c6}] {name}: 采集新闻...")
        news = fetch_news(c6)
        if news:
            logger.info(f"    {len(news)}条公告，LLM分析中...")
            r = analyze_news_llm(c6, name, news)
            if r:
                results[c6] = {"sentiment": r['sentiment'], "news_count": len(news), "confidence": r['confidence'], "sentiment_raw": r}
                logger.info(f"    → 情感:{r['sentiment']:+.2f} 置信度:{r['confidence']}")
            else: logger.info(f"    → LLM跳过")
        else: logger.info(f"    → 无公告")
        time.sleep(0.3)
    logger.info(f"  ✅ {len(results)}只有新闻数据")
    return results

# ====================================================================
# 模块3: 资金流向 (fund_score)
# ====================================================================

def fetch_fund_flow(code_6digit):
    """使用腾讯行情接口（24小时可用），从量价数据推算资金流向"""
    market = "sh" if code_6digit.startswith(('6','5')) else "sz"
    try:
        resp = requests.get(f"http://qt.gtimg.cn/q={market}{code_6digit}",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        text = resp.text
        parts = text.split("~")
        if len(parts) < 44: return None
        pct = float(parts[32]) if parts[32] else 0
        amount = float(parts[37]) if parts[37] else 0  # 万元
        vol = int(parts[6]) if parts[6] else 0  # 手
        turnover = float(parts[38]) if parts[38] else 0  # 换手率%
        amplitude = float(parts[43]) if parts[43] else 0  # 振幅%

        # 综合资金因子 =
        #   方向: 涨为正、跌为负
        #   强度: 换手率×振幅（量价配合度）
        #   归一化: 对数压缩成交额
        # 基本原理: 量价齐升→主力买入；放量下跌→主力出货
        log_vol = max(0.001, amount / 10000)  # 亿
        log_vol = __import__('math').log1p(log_vol) / 5  # 0~1之间，压缩大盘股

        # 主力净额估算
        direction = 1 if pct >= 0 else -1
        energy = min(turnover, 10) * min(abs(pct), 10) / 100  # 0~1
        main_net = direction * log_vol * energy * 10  # 亿

        # 主力占比（量价配合指标）
        main_ratio = direction * min(energy * 2, 0.5)

        return {"main_net": round(main_net, 4), "main_pct": round(main_ratio, 4)}
    except: return None

def calc_fund_score(data):
    if not data: return 50
    mn = data.get('main_net', 0) or 0
    # 主力净额(亿)映射到0-100
    if mn > 1.5: return min(100, 70 + (mn-1.5)*12)
    if mn > 0.5: return 55 + (mn-0.5)*25
    if mn > 0: return 50 + mn*10
    if mn > -0.5: return 45 + mn*10
    if mn > -1.5: return 30 + (mn+0.5)*25
    return max(0, 15 + (mn+1.5)*12)

def collect_fund(codes_6digit):
    logger.info("\n=== 资金流向因子 ===")
    results = {}
    for c6 in codes_6digit:
        name = STOCK_NAMES.get(c6, c6)
        d = fetch_fund_flow(c6)
        if d:
            score = calc_fund_score(d)
            results[c6] = {"fund_score": score, "main_net": d['main_net'], "main_pct": d.get('main_pct')}
            logger.info(f"  [{c6}] {name}: 主力净流入{d['main_net']:.2f}亿 → 资金分{score}")
        else: logger.info(f"  [{c6}] {name}: 无资金流数据")
        time.sleep(0.1)
    logger.info(f"  ✅ {len(results)}只含资金数据")
    return results

# ====================================================================
# 模块4: 大盘+板块因子 (macro_factors)
# ====================================================================

def collect_macro(conn, codes_6digit):
    logger.info("\n=== 大盘因子 ===")
    df300 = pd.read_sql("SELECT date, close, pct_chg FROM index_daily WHERE code='sh.000300' ORDER BY date DESC LIMIT 1", conn)
    df500 = pd.read_sql("SELECT date, close, pct_chg FROM index_daily WHERE code='sh.000905' ORDER BY date DESC LIMIT 1", conn)
    if df300.empty or df500.empty:
        logger.info("  ❌ 指数数据为空")
        return

    r300, r500 = df300.iloc[0], df500.iloc[0]
    d300 = pd.read_sql("SELECT close FROM index_daily WHERE code='sh.000300' ORDER BY date DESC LIMIT 20", conn)['close'].values
    d500 = pd.read_sql("SELECT close FROM index_daily WHERE code='sh.000905' ORDER BY date DESC LIMIT 20", conn)['close'].values

    hs300_ma5 = d300[:5].mean() if len(d300)>=5 else r300['close']
    hs300_ma20 = d300.mean() if len(d300)>=20 else r300['close']
    zz500_ma5 = d500[:5].mean() if len(d500)>=5 else r500['close']
    zz500_ma20 = d500.mean() if len(d500)>=20 else r500['close']

    def trend(c, m20):
        if c > m20*1.03: return 'up'
        if c < m20*0.97: return 'down'
        return 'sideways'

    now = datetime.now()
    cur = conn.cursor()
    cur.execute("""INSERT INTO macro_factors
        (date, update_time, hs300_close, hs300_pct, zz500_close, zz500_pct,
         hs300_ma5, hs300_ma20, hs300_trend, zz500_ma5, zz500_ma20, zz500_trend)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (now.strftime('%Y-%m-%d'), now.strftime('%H:%M'),
         r300['close'], r300['pct_chg'], r500['close'], r500['pct_chg'],
         round(hs300_ma5,2), round(hs300_ma20,2), trend(r300['close'], hs300_ma20),
         round(zz500_ma5,2), round(zz500_ma20,2), trend(r500['close'], zz500_ma20)))
    conn.commit()
    logger.info(f"  沪深300: {r300['close']:.0f} ({r300['pct_chg']:+.2f}%) 趋势={trend(r300['close'], hs300_ma20)}")
    logger.info(f"  中证500: {r500['close']:.0f} ({r500['pct_chg']:+.2f}%) 趋势={trend(r500['close'], zz500_ma20)}")

    # 板块
    logger.info("\n=== 板块因子 ===")
    def get_sector(n):
        if any(k in n for k in ['PCB','南亚','生益','深南','景旺','胜宏']): return '电子-PCB'
        if any(k in n for k in ['半导体','芯片','芯原','恒烁','兆易','长川','神工']): return '半导体'
        if any(k in n for k in ['赣锋','嘉元','鼎胜']): return '新能源-锂电'
        if any(k in n for k in ['金风','高测']): return '新能源'
        if any(k in n for k in ['华通','鼎通','信维','环旭','东山']): return '电子-元器件'
        if any(k in n for k in ['悦康','药业']): return '医药'
        if any(k in n for k in ['卫星','科思','欧科亿','伟创','金盘','博众','沃尔德']): return '高端制造'
        if any(k in n for k in ['新凤鸣','杰瑞']): return '化工/能源'
        return '其他'

    today_data = {}
    for c6 in codes_6digit:
        cf = f"{c6}.SH" if c6.startswith(('6','5')) else f"{c6}.SZ"
        df = pd.read_sql(f"SELECT pct_chg FROM daily_price WHERE code='{cf}' ORDER BY date DESC LIMIT 1", conn)
        if not df.empty and pd.notna(df['pct_chg'].iloc[0]): today_data[c6] = df['pct_chg'].iloc[0]

    sector_map = {c6: get_sector(STOCK_NAMES.get(c6,'')) for c6 in codes_6digit}
    sp = {}
    for c6, s in sector_map.items():
        if c6 in today_data: sp.setdefault(s, []).append(today_data[c6])
    sa = {s: round(np.mean(v),2) for s,v in sp.items() if v}
    if sa:
        top = max(sa, key=sa.get); worst = min(sa, key=sa.get); rot = round(abs(sa[top]-sa[worst]),2)
        for s, v in sorted(sa.items(), key=lambda x: -x[1]):
            logger.info(f"  {s}: {v:+.2f}% ({len(sp[s])}只)")
        logger.info(f"  最强: {top} | 最弱: {worst} | 轮动强度: {rot}")
        cur.execute("""UPDATE macro_factors SET top_sector=?, sector_rotation=?
            WHERE rowid IN (SELECT rowid FROM macro_factors ORDER BY id DESC LIMIT 1)""", (top, rot))
        conn.commit()

# ====================================================================
# 写入 factor_signals
# ====================================================================

def save_signals(conn, codes_6digit, today, session, fin=None, news=None, fund=None):
    cur = conn.cursor()
    written = 0
    for c6 in codes_6digit:
        f = (fin or {}).get(c6, {})
        n = (news or {}).get(c6, {})
        fu = (fund or {}).get(c6, {})
        code_full = f"{c6}.SH" if c6.startswith(('6','5')) else f"{c6}.SZ"

        sentiment = n.get('sentiment', 0)
        news_score = max(0, min(100, (sentiment+1)*50))
        sent_json = json.dumps(n.get('sentiment_raw',{}), ensure_ascii=False) if n.get('sentiment_raw') else None

        if not f and not n and not fu: continue
        cur.execute("""INSERT OR REPLACE INTO factor_signals
            (code, date, session, news_score, news_count, news_sentiment,
             fin_score, llm_summary, llm_confidence,
             fund_score, main_net_inflow, main_ratio, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (code_full, today, session,
             round(news_score,1), n.get('news_count',0), sent_json,
             f.get('fin_score',50), f.get('llm_summary',''), f.get('llm_confidence',0),
             fu.get('fund_score',50), fu.get('main_net'), fu.get('main_pct'),
             datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        written += 1
    conn.commit()
    logger.info(f"\n  ✅ {written}/{len(codes_6digit)} 只已写入 factor_signals")

# ====================================================================
# 主流程
# ====================================================================

def run_once(quick=False):
    logger.info("=" * 56)
    logger.info(f"  factor_runner | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if quick: logger.info("  模式: quick (跳过LLM)")
    logger.info("=" * 56)

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    codes = get_codes()
    logger.info(f"  股票池: {len(codes)}只")
    today = datetime.now().strftime('%Y-%m-%d')
    session = 'afternoon'

    collect_macro(conn, codes)

    if quick:
        fund = collect_fund(codes)
        save_signals(conn, codes, today, session, fund=fund)
    else:
        fin = collect_fundamental(conn, codes)
        news = collect_news(codes)
        fund = collect_fund(codes)
        save_signals(conn, codes, today, session, fin=fin, news=news, fund=fund)

    conn.close()
    logger.info(f"\n  ✅ 采集完成 | {datetime.now().strftime('%H:%M')}")

def daemon_loop():
    """守护进程：交易时段每小时运行一次"""
    logger.info("=" * 56)
    logger.info(f"  factor_runner 守护进程启动 | PID: {os.getpid()}")
    logger.info("  模式: 交易日 09:00-15:00 每小时整点采集")
    logger.info("=" * 56)

    # 写 PID
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    last_run_date = ""
    last_run_hour = -1

    while running:
        now = datetime.now()
        is_weekday = now.weekday() < 5
        hour = now.hour
        minute = now.minute
        is_trading = is_weekday and ((hour >= 9 and hour < 12) or (hour >= 13 and hour < 15))

        should_run = (is_trading and (minute < 5 and hour != last_run_hour) or (last_run_date != now.strftime('%Y-%m-%d')))

        if not is_weekday:
            logger.debug(f"[非交易日] {now.strftime('%Y-%m-%d')} 跳过")
        elif not is_trading:
            logger.debug(f"[非交易时间] {now.strftime('%H:%M')} 跳过")
        elif should_run or (now.minute == 0 and last_run_hour != hour):
            try:
                run_once(quick=True)  # daemon 模式默认 quick（不调 LLM）
                last_run_date = now.strftime('%Y-%m-%d')
                last_run_hour = hour
            except Exception as e:
                logger.error(f"采集异常: {e}")

        # 每60秒检查一次
        for _ in range(60):
            if not running: break
            time.sleep(1)

    # 清理
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
    logger.info("factor_runner 已停止")

# ====================================================================
# 入口
# ====================================================================

if __name__ == '__main__':
    if len(sys.argv) > 1:
        if sys.argv[1] == '--daemon':
            daemon_loop()
        elif sys.argv[1] == '--stop':
            if os.path.exists(PID_FILE):
                pid = int(open(PID_FILE).read().strip())
                try:
                    os.kill(pid, signal.SIGTERM)
                    print(f"已发送停止信号 (PID: {pid})")
                except:
                    os.remove(PID_FILE)
                    print("PID文件已清理")
            else:
                print("PID文件不存在，守护进程未运行")
        elif sys.argv[1] == '--quick':
            run_once(quick=True)
        else:
            print(f"未知参数: {sys.argv[1]}")
    else:
        run_once(quick=False)
