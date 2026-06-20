# -*- coding: utf-8 -*-
"""
大盘指数日线采集 — 沪深300(sh.000300) + 中证500(sh.000905)
通过东方财富 API 拉取日K线，写入 index_daily 表
"""
import requests, sqlite3, time, logging, sys, os
from datetime import datetime, timedelta
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = Path(os.environ.get('STOCK5_DB_PATH', r'E:\stock5\stocks.db'))

# 指数配置: (东方财富secid, index_daily中的两种code格式)
INDEX_CONFIG = [
    ('1.000300', '000300.SH', 'sh.000300', '沪深300'),
    ('1.000905', '000905.SH', 'sh.000905', '中证500'),
]


def fetch_index_kline(secid: str, days: int = 120):
    """从东方财富拉取指数日K线，带重试"""
    url = (
        'https://push2his.eastmoney.com/api/qt/stock/kline/get'
        f'?secid={secid}'
        '&fields1=f1,f2,f3,f4,f5,f6'
        '&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61'
        f'&klt=101&fqt=1&end=20500101&lmt={days}'
    )
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://quote.eastmoney.com/',
        'Accept': 'application/json, text/plain, */*',
    })
    for attempt in range(3):
        try:
            resp = session.get(url, timeout=20)
            data = resp.json()
            if data.get('data') and data['data'].get('klines'):
                return data['data']['klines']
            logger.warning(f"  {secid} 第{attempt+1}次返回空数据")
        except Exception as e:
            logger.warning(f"  {secid} 第{attempt+1}次失败: {e}")
            time.sleep(2)
    return None


def sync_index_to_db(conn):
    """拉取指数日线并同步到 index_daily（增量更新）"""
    today = datetime.now()
    inserted_total = 0

    for secid, code_sh, code_alt, name in INDEX_CONFIG:
        # 查 index_daily 最新日期
        cur = conn.cursor()
        cur.execute("SELECT MAX(date) FROM index_daily WHERE code IN (?,?)", (code_sh, code_alt))
        max_date = cur.fetchone()[0]

        if max_date:
            # 只差一天以内（非交易日可能在同一天） 则认为是最新，跳过
            try:
                days_behind = (today - datetime.strptime(max_date, '%Y-%m-%d')).days
                if days_behind <= 1 and today.weekday() >= 5:
                    # 周末，��强制更新
                    logger.info(f"  [{name}] 已最新 ({max_date})，跳过")
                    continue
            except:
                pass

        logger.info(f"  正在拉取 {name} ({secid}) K线...")
        klines = fetch_index_kline(secid, days=120)
        if not klines:
            logger.warning(f"  [{name}] 拉取失败，跳过")
            continue

        inserted = 0
        for line in klines:
            parts = line.split(',')
            if len(parts) < 11:
                continue
            # 字段: date,open,close,high,low,volume,amount,amplitude,pct_chg,change,turnover
            date_str = parts[0]
            open_v = float(parts[1])
            close_v = float(parts[2])
            high_v = float(parts[3])
            low_v = float(parts[4])
            vol = float(parts[5])
            amount = float(parts[6])
            pct_chg = float(parts[8])
            turnover = float(parts[10]) if len(parts) > 10 else 0

            # 检查是否已存在
            existing = cur.execute(
                "SELECT 1 FROM index_daily WHERE code=? AND date=?", (code_sh, date_str)
            ).fetchone()
            if existing:
                continue  # 跳过已有

            for code_variant in (code_sh, code_alt):
                try:
                    cur.execute("""
                        INSERT INTO index_daily 
                        (code, date, open, high, low, close, volume, pct_chg, amount, prev_close, name)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        code_variant, date_str, open_v, high_v, low_v, close_v,
                        vol, pct_chg, amount, 0, name
                    ))
                    inserted += 1
                except Exception as e:
                    logger.debug(f"    插入 {code_variant} {date_str} 失败: {e}")

        conn.commit()
        logger.info(f"  [{name}] 新增 {inserted} 条 (双格式各{inserted//2 if inserted else 0})")
        inserted_total += inserted

    return inserted_total


def main():
    logger.info("=" * 56)
    logger.info(f"  大盘指数日线采集 | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    logger.info("=" * 56)

    conn = sqlite3.connect(str(DB_PATH))
    try:
        total = sync_index_to_db(conn)
        if total > 0:
            logger.info(f"\n✅ 共写入 {total} 条指数日线记录")
        else:
            logger.info(f"\n✅ 指数日线已是最新，无需更新")
    except Exception as e:
        logger.exception(f"采集异常: {e}")
        return 1
    finally:
        conn.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())
