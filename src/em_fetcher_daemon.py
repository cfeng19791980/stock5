# -*- coding: utf-8 -*-
"""
em_fetcher_daemon.py — 东方财富数据采集器（独立运行，不依赖现有系统）
功能：采集新增特征数据写入 stock5 数据库
特点：
  1. 完全独立，不影响现有腾讯 API 采集链路
  2. 新特征写入新表 em_fundamentals 和 em_market_metrics
  3. 支持 --once 单次采集 和 --daemon 定时采集

运行方式：
  python em_fetcher_daemon.py --once           # 单次采集验证
  python em_fetcher_daemon.py --daemon          # 交易日定时采集（每小时1次，9-15点）
  python em_fetcher_daemon.py --daemon --interval 60  # 自定义间隔（分钟）

数据库新增表：
  em_fundamentals  — 基本面指标
  em_market_metrics — 市场面指标（含行业/基本面评分）
"""

import sys
sys.stdout.reconfigure(encoding='utf-8')

import requests
import json
import time
import sqlite3
import pandas as pd
import argparse
import os
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime, date
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ========== 配置 - 使用相对路径 ==========
import pathlib
PROJECT_DIR = pathlib.Path(__file__).parent.absolute()
DB_PATH = PROJECT_DIR / "stocks.db"
CSV_PATH = PROJECT_DIR / "波段股票Top30.csv"
LOG_PATH = PROJECT_DIR / "logs" / "em_fetcher.log"
PID_FILE = PROJECT_DIR / "em_fetcher.pid"

os.makedirs(PROJECT_DIR / "logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        TimedRotatingFileHandler(LOG_PATH, when='midnight', interval=1, backupCount=30, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ========== 股票列表 ==========
STOCK_CODES = [
    '605196','688028','688195','688233','688519',
    '002353','002384','600183','603876','603986',
    '688416','688521','688676','300136','603225',
    '688308','688388','688556','600118','601231',
    '688658','688668','688788','002202','002916',
    '300604','603228','688698','002460','300476',
]

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

# 代码转东方财富格式
def code_to_em(code):
    """6开头→上海(SH)，其他→深圳(SZ)"""
    if code.startswith(('6','5')):
        return f"SH{code}"
    return f"SZ{code}"

# ========== 数据源封装 ==========
class EMDataSource:
    """东方财富数据源 - 只使用可用的 API"""

    def __init__(self):
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()
        retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('https://', adapter)
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://quote.eastmoney.com/',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        })
        return session

    def _get(self, url, timeout=15):
        for attempt in range(2):
            try:
                resp = self.session.get(url, timeout=timeout)
                return resp
            except Exception:
                if attempt == 0:
                    time.sleep(1)
                else:
                    return None
        return None

    def fetch_selection(self, code):
        """选股器 - 获取个股基本面/技术面综合数据"""
        url = (
            "https://data.eastmoney.com/dataapi/xuangu/list"
            f"?sty=SECUCODE,SECURITY_CODE,SECURITY_NAME_ABBR,CHANGE_RATE,NEW_PRICE,OPEN_PRICE,HIGH_PRICE,LOW_PRICE,"
            f"PRE_CLOSE_PRICE,VOLUME_RATIO,TURNOVERRATE,AMPLITUDE,SPEED_INCREASE,SPEED_INCREASE_5,"
            f"SPEED_INCREASE_60,SPEED_INCREASE_ALL,PE9,PBNEWMRQ,TOTAL_MARKET_CAP,FREE_CAP,INDUSTRY"
            f"&filter=(SECURITY_CODE=%22{code}%22)&p=1&ps=1&source=SELECT_SECURITIES&client=WEB"
        )
        resp = self._get(url)
        if resp is None:
            return None
        try:
            items = resp.json().get('result', {}).get('data', [])
            return items[0] if items else None
        except:
            return None

    def fetch_fundamentals(self, code):
        """操盘必读 - 获取基本面指标（主要指标/所属板块/股东人数）"""
        em_code = code_to_em(code)
        url = f"https://emweb.securities.eastmoney.com/PC_HSF10/OperationsRequired/PageAjax?code={em_code}"
        resp = self._get(url)
        if resp is None:
            return None
        try:
            data = resp.json()
            result = {}

            # 主要指标（zxzb）
            zb = data.get('zxzb', [{}])[0]
            result['eps'] = zb.get('EPSJB', 0)       # 每股收益
            result['bps'] = zb.get('BPS', 0)          # 每股净资产
            result['roe'] = zb.get('ROEJQ', 0)        # ROE
            result['gross_margin'] = zb.get('XSMLL', 0)  # 毛利率
            result['debt_ratio'] = zb.get('ZCFZL', 0)    # 资产负债率
            result['revenue'] = zb.get('TOTAL_OPERATEINCOME', 0)   # 营业收入
            result['net_profit'] = zb.get('PARENT_NETPROFIT', 0)   # 归属净利润
            result['revenue_yoy'] = zb.get('YYZSRGDHBZC', 0)       # 营收同比
            result['profit_yoy'] = zb.get('NETPROFITRPHBZC', 0)    # 利润同比
            result['mg_gjj'] = zb.get('MGZBGJ', 0)    # 每股公积金
            result['mg_wfplr'] = zb.get('MGWFPLR', 0) # 每股未分配利润
            result['report_date'] = str(zb.get('REPORT_DATE', ''))[:10]

            # 股东人数（gdrs 最新）
            gdrs = data.get('gdrs', [])
            if gdrs:
                result['holder_count'] = gdrs[0].get('HOLDER_TOTAL_NUM', 0)
                result['avg_hold_amt'] = gdrs[0].get('AVG_HOLD_AMT', 0)
            else:
                result['holder_count'] = 0
                result['avg_hold_amt'] = 0

            # 所属板块（ssbk）
            ssbk = data.get('ssbk', [])
            result['industry_boards'] = ','.join(b.get('BOARD_NAME', '') for b in ssbk[:5])

            # 融资融券（rzrq 最新）
            rzrq = data.get('rzrq', [])
            if rzrq:
                result['margin_balance'] = rzrq[0].get('FIN_BALANCE', 0)
                result['short_balance'] = rzrq[0].get('LOAN_BALANCE', 0)
            else:
                result['margin_balance'] = 0
                result['short_balance'] = 0

            return result
        except Exception as e:
            logger.debug(f"解析基本面失败 {code}: {e}")
            return None

# ========== 数据库操作 ==========
def init_db_tables(conn):
    """创建新表（如果不存在）"""
    conn.executescript("""
        -- 基本面指标表
        CREATE TABLE IF NOT EXISTS em_fundamentals (
            code TEXT NOT NULL,
            date TEXT NOT NULL,
            report_date TEXT,
            eps REAL DEFAULT 0,
            bps REAL DEFAULT 0,
            roe REAL DEFAULT 0,
            gross_margin REAL DEFAULT 0,
            debt_ratio REAL DEFAULT 0,
            revenue REAL DEFAULT 0,
            net_profit REAL DEFAULT 0,
            revenue_yoy REAL DEFAULT 0,
            profit_yoy REAL DEFAULT 0,
            mg_gjj REAL DEFAULT 0,
            mg_wfplr REAL DEFAULT 0,
            holder_count INTEGER DEFAULT 0,
            avg_hold_amt REAL DEFAULT 0,
            margin_balance REAL DEFAULT 0,
            short_balance REAL DEFAULT 0,
            industry_boards TEXT DEFAULT '',
            PRIMARY KEY (code, date)
        );

        -- 市场面指标表
        CREATE TABLE IF NOT EXISTS em_market_metrics (
            code TEXT NOT NULL,
            date TEXT NOT NULL,
            close REAL DEFAULT 0,
            pct_chg REAL DEFAULT 0,
            volume_ratio REAL DEFAULT 0,
            turnover_rate REAL DEFAULT 0,
            amplitude REAL DEFAULT 0,
            speed_5m REAL DEFAULT 0,
            pe_ttm REAL DEFAULT 0,
            pb REAL DEFAULT 0,
            total_mv REAL DEFAULT 0,
            free_mv REAL DEFAULT 0,
            industry TEXT DEFAULT '',
            PRIMARY KEY (code, date)
        );

        -- 采集日志
        CREATE TABLE IF NOT EXISTS em_fetch_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetch_time TEXT NOT NULL,
            code TEXT,
            data_type TEXT,
            status TEXT,
            detail TEXT
        );
    """)
    conn.commit()

def write_fundamentals(conn, code, today_str, data):
    """写入基本面数据"""
    if data is None:
        return False
    try:
        conn.execute("""
            INSERT OR REPLACE INTO em_fundamentals
            (code, date, report_date, eps, bps, roe, gross_margin, debt_ratio,
             revenue, net_profit, revenue_yoy, profit_yoy,
             mg_gjj, mg_wfplr, holder_count, avg_hold_amt,
             margin_balance, short_balance, industry_boards)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            code, today_str, data.get('report_date', ''),
            data.get('eps', 0), data.get('bps', 0), data.get('roe', 0),
            data.get('gross_margin', 0), data.get('debt_ratio', 0),
            data.get('revenue', 0), data.get('net_profit', 0),
            data.get('revenue_yoy', 0), data.get('profit_yoy', 0),
            data.get('mg_gjj', 0), data.get('mg_wfplr', 0),
            data.get('holder_count', 0), data.get('avg_hold_amt', 0),
            data.get('margin_balance', 0), data.get('short_balance', 0),
            data.get('industry_boards', '')
        ))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"写入基本面失败 {code}: {e}")
        return False

def write_market_metrics(conn, code, today_str, data):
    """写入市场面数据"""
    if data is None:
        return False
    try:
        conn.execute("""
            INSERT OR REPLACE INTO em_market_metrics
            (code, date, close, pct_chg, volume_ratio, turnover_rate, amplitude,
             speed_5m, pe_ttm, pb, total_mv, free_mv, industry)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            code, today_str,
            float(data.get('NEW_PRICE', 0)),
            float(data.get('CHANGE_RATE', 0)),
            float(data.get('VOLUME_RATIO', 0)),
            float(data.get('TURNOVERRATE', 0)),
            float(data.get('AMPLITUDE', 0)),
            float(data.get('SPEED_INCREASE_5', 0)),
            float(data.get('PE9', 0)),
            float(data.get('PBNEWMRQ', 0)),
            int(data.get('TOTAL_MARKET_CAP', 0)),
            int(data.get('FREE_CAP', 0)),
            data.get('INDUSTRY', '')
        ))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"写入市场面失败 {code}: {e}")
        return False

def log_fetch(conn, code, data_type, status, detail=''):
    """记录采集日志"""
    try:
        conn.execute(
            "INSERT INTO em_fetch_log (fetch_time, code, data_type, status, detail) VALUES (?,?,?,?,?)",
            (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), code, data_type, status, str(detail)[:200])
        )
        conn.commit()
    except:
        pass

# ========== 采集流程 ==========
def fetch_all(em_source, conn, today_str):
    """全量采集30只股票"""
    results = {'fundamentals': 0, 'market': 0, 'fail': 0}

    for idx, code in enumerate(STOCK_CODES):
        name = STOCK_NAMES.get(code, code)

        # 选股器（市场面数据）
        sel = em_source.fetch_selection(code)
        if sel:
            if write_market_metrics(conn, code, today_str, sel):
                results['market'] += 1
                log_fetch(conn, code, 'market', 'OK')
        else:
            log_fetch(conn, code, 'market', 'FAIL', '选股器无返回')

        # 操盘必读（基本面数据）
        fund = em_source.fetch_fundamentals(code)
        if fund:
            if write_fundamentals(conn, code, today_str, fund):
                results['fundamentals'] += 1
                log_fetch(conn, code, 'fundamentals', 'OK')
        else:
            log_fetch(conn, code, 'fundamentals', 'FAIL', '操盘必读无返回')

        # 进度
        if (idx + 1) % 5 == 0:
            logger.info(f"  进度: {idx+1}/30, 基本面={results['fundamentals']}, 市场面={results['market']}")

        # 请求间隔，避免被限
        time.sleep(0.3)

    return results

def is_trading_day():
    return date.today().weekday() < 5

def is_trading_hour():
    h = datetime.now().hour
    return 9 <= h <= 14

def write_pid():
    with open(PID_FILE, 'w', encoding='utf-8') as f:
        f.write(str(os.getpid()))

def remove_pid():
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)

# ========== 主入口 ==========
def run_once():
    """单次采集"""
    today_str = datetime.now().strftime('%Y-%m-%d')
    logger.info(f"=" * 60)
    logger.info(f"东方财富数据采集 — {today_str}")
    logger.info(f"=" * 60)

    em = EMDataSource()
    conn = sqlite3.connect(DB_PATH)
    try:
        init_db_tables(conn)
        results = fetch_all(em, conn, today_str)
        total = results['fundamentals'] + results['market']
        logger.info(f"")
        logger.info(f"采集完成: 基本面{results['fundamentals']}/30, 市场面{results['market']}/30")
        logger.info(f"共写入 {total} 条记录")
        return results
    finally:
        conn.close()

def run_daemon(interval_minutes=60):
    """定时采集"""
    logger.info(f"定时采集模式启动，间隔={interval_minutes}分钟")
    write_pid()

    while True:
        now = datetime.now()
        if is_trading_day() and is_trading_hour():
            logger.info(f"交易日交易时段，开始采集")
            run_once()
        else:
            logger.info(f"非交易时段，跳过本轮")
        
        # 等待到下一个整点
        logger.info(f"等待 {interval_minutes} 分钟...")
        time.sleep(interval_minutes * 60)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='东方财富数据采集器')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--once', action='store_true', help='单次采集')
    group.add_argument('--daemon', action='store_true', help='定时采集模式')
    parser.add_argument('--interval', type=int, default=60, help='采集间隔（分钟，默认60）')
    args = parser.parse_args()

    if args.daemon:
        run_daemon(interval_minutes=args.interval)
    else:
        run_once()
