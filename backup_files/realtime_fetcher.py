# -*- coding: utf-8 -*-
"""
realtime_fetcher_minute5.py — 5分钟数据采集写入器
功能：
  1. 从腾讯API获取实时数据
  2. 直接写入minute_5_price表（5分钟K线）
  3. 计算技术指标（MA5基于5个5分钟周期）
  4. 不需要聚合，直接写入

运行方式：
  python realtime_fetcher_minute5.py --once   # 单次采集
  python realtime_fetcher_minute5.py --daemon # 后台每5分钟采集
"""

import sys
sys.stdout.reconfigure(encoding='utf-8')

import requests
import time
import json
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import argparse
import os
import signal
import logging
from logging.handlers import TimedRotatingFileHandler
from functools import wraps
import threading
import traceback
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configuration
DB_PATH = r'E:\\stock5\\stocks.db'
PID_FILE = r'E:\\stock5\\collection.pid'
LOG_DIR = r'E:\\stock5\\logs'
LOG_FILE = os.path.join(LOG_DIR, 'collection.log')

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)

# Configure logging (带日志轮转：每天切割，保留30天)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        TimedRotatingFileHandler(LOG_FILE, when='midnight', interval=1, backupCount=30, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
running = True

# Metrics collection for monitoring
class FetcherMetrics:
    def __init__(self):
        self.fetch_count = 0
        self.success_count = 0
        self.failure_count = 0
        self.last_success_time = None
        self.last_failure_time = None
        self.consecutive_failures = 0
        self.total_records_written = 0
        self.start_time = datetime.now()
        self._lock = threading.Lock()
    
    def record_fetch_attempt(self, success: bool, records_written: int = 0):
        with self._lock:
            self.fetch_count += 1
            if success:
                self.success_count += 1
                self.last_success_time = datetime.now()
                self.consecutive_failures = 0
                self.total_records_written += records_written
            else:
                self.failure_count += 1
                self.last_failure_time = datetime.now()
                self.consecutive_failures += 1
    
    def get_metrics(self):
        with self._lock:
            uptime = (datetime.now() - self.start_time).total_seconds()
            success_rate = (self.success_count / self.fetch_count * 100) if self.fetch_count > 0 else 0
            return {
                'uptime_seconds': uptime,
                'fetch_count': self.fetch_count,
                'success_count': self.success_count,
                'failure_count': self.failure_count,
                'success_rate_percent': round(success_rate, 2),
                'last_success_time': self.last_success_time.isoformat() if self.last_success_time else None,
                'last_failure_time': self.last_failure_time.isoformat() if self.last_failure_time else None,
                'consecutive_failures': self.consecutive_failures,
                'total_records_written': self.total_records_written
            }
    
    def save_metrics_to_file(self, filepath: str = r'E:\\stock5\\logs\\fetcher_metrics.json'):
        """Save metrics to a JSON file for external monitoring"""
        try:
            metrics = self.get_metrics()
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(metrics, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save fetcher metrics to file: {e}")
    
    def reset(self):
        with self._lock:
            self.__init__()

fetcher_metrics = FetcherMetrics()

def with_retry(max_retries=3, backoff_factor=1, status_forcelist=(500, 502, 503, 504)):
    """Decorator for retrying functions with exponential backoff"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            url = kwargs.get('url', args[0] if args else None)
            for attempt in range(max_retries):
                try:
                    result = func(*args, **kwargs)
                    if attempt > 0:
                        logger.info(f"Attempt {attempt + 1} succeeded for {url}")
                    return result
                except Exception as e:
                    if attempt == max_retries - 1:
                        logger.error(f"All {max_retries} attempts failed for {url}: {e}")
                        raise e
                    wait_time = backoff_factor * (2 ** attempt)
                    logger.warning(f"Attempt {attempt + 1} failed for {url}: {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
            return None
        return wrapper
    return decorator

def create_session_with_retries():
    """Create a requests session with retry strategy"""
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def signal_handler(signum, frame):
    """处理退出信号（Windows兼容）"""
    global running
    logger.info(f"收到退出信号，准备停止...")
    running = False
    # Windows下直接退出，避免信号处理问题
    if os.name == 'nt':
        logger.info("Windows环境，直接退出")
        sys.exit(0)
def write_pid():
    """写入PID文件"""
    pid = os.getpid()
    with open(PID_FILE, 'w', encoding='utf-8') as f:
        f.write(str(pid))
    logger.info(f"PID文件已写入: {pid}")

def remove_pid():
    """删除PID文件"""
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)
        logger.info("PID文件已删除")

def is_process_running(pid_file: str) -> bool:
    """检查是否有进程在运行"""
    if not os.path.exists(pid_file):
        return False
    
    try:
        with open(pid_file, 'r', encoding='utf-8') as f:
            pid = int(f.read().strip())
        
        # 检查进程是否存在
        try:
            os.kill(pid, 0)  # 信号0不会杀死进程，只检查是否存在
            return True
        except OSError:
            return False
    except:
        return False

# 30只股票
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

logger.info("=" * 70)
logger.info("CSI10 5分钟数据采集写入器")
logger.info("功能：实时数据 → minute_5_price表 + 技术指标")
logger.info("=" * 70)

# ========== 核心函数 ==========

def code_to_tx(code):
    """转腾讯格式: 600183 -> sh600183, 002460 -> sz002460"""
    if code.startswith(('6','5')):
        return f"sh{code}"
    elif code.startswith(('0','3')):
        return f"sz{code}"
    return code

def fetch_realtime(codes: List[str] = None) -> Dict:
    """从腾讯API获取实时行情"""
    if codes is None:
        codes = STOCK_CODES
    
    tx_codes = [code_to_tx(c) for c in codes]
    
    url = f"http://qt.gtimg.cn/q={','.join(tx_codes)}"
    
    try:
        # 使用带重试的会话
        session = create_session_with_retries()
        resp = session.get(url, timeout=15)
        if resp.status_code != 200:
            logger.error(f"API返回错误状态码: {resp.status_code}")
            return {}
        lines = resp.text.strip().split('\n')
    except requests.Timeout:
        logger.error("API请求超时（15秒）")
        return {}
    except requests.ConnectionError:
        logger.error("API连接失败")
        return {}
    except Exception as e:
        logger.error(f"API请求异常: {e}")
        return {}
    results = {}
    for line in lines:
        if not line.startswith('v_'):
            continue
        parts = line.split('~')
        if len(parts) < 40:
            continue
        
        code = parts[2]
        if len(code) != 6:
            continue
        
        try:
            price = float(parts[3]) if parts[3] else 0
            prev_close = float(parts[4]) if parts[4] else 0
            open_ = float(parts[5]) if parts[5] else 0
            high = float(parts[33]) if len(parts) > 33 and parts[33] else price
            low = float(parts[34]) if len(parts) > 34 and parts[34] else price
            volume_hand = float(parts[36]) if len(parts) > 36 and parts[36] else 0
            amount = float(parts[37]) if len(parts) > 37 and parts[37] else 0
            name = parts[1]
            
            pct = (price - prev_close) / prev_close * 100 if prev_close > 0 else 0
            
            buy_pct = parts[10] if len(parts) > 10 else '0%'
            sell_pct = parts[20] if len(parts) > 21 else '0%'
            
            results[code] = {
                'name': name,
                'price': price,
                'prev_close': prev_close,
                'pct_change': round(pct, 2),
                'high': high,
                'low': low,
                'open': open_,
                'volume': int(volume_hand * 100),
                'amount': amount,
                'buy_ratio': buy_pct,
                'sell_ratio': sell_pct,
            }
        except (ValueError, IndexError):
            continue
    
    return results

def write_minute_5_to_db(data: Dict, db_path: str = DB_PATH) -> int:
    """
    将实时数据写入minute_5_price表（5分钟K线）
    直接从实时数据构建5分钟K线，同时计算技术指标
    完全重写：使用独立 dict，避免任何 pandas/numpy 副作用
    """
    if not data:
        return 0
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 计算5分钟整点时间
    now = datetime.now()
    minute_5_time = now.replace(
        minute=now.minute // 5 * 5,
        second=0,
        microsecond=0
    )
    
    written_count = 0
    
    for code, d in data.items():
        try:
            # 将 d 的所有值转为 Python 原生类型
            item = {k: float(v) if not isinstance(v, str) else v for k, v in d.items()}
            item['volume'] = int(d['volume'])
            
            # 获取历史数据（用于计算技术指标）
            query = """
                SELECT datetime, close, high, low, volume
                FROM minute_5_price
                WHERE code = ?
                ORDER BY datetime DESC
                LIMIT 50
            """
            
            historical_data = pd.read_sql_query(query, conn, params=(code,))
            
            # 计算技术指标
            indicators = {}
            
            if len(historical_data) > 0:
                current_close = item['price']
                current_high = item['high']
                current_low = item['low']
                
                # 安全获取历史收盘价列表
                hist_close_col = historical_data['close']
                if isinstance(hist_close_col, pd.Series):
                    hist_close = hist_close_col.tolist()
                else:
                    hist_close = [float(hist_close_col)]
                
                hist_high_col = historical_data['high']
                hist_high_l = hist_high_col.tolist() if isinstance(hist_high_col, pd.Series) else [float(hist_high_col)]
                
                hist_low_col = historical_data['low']
                hist_low_l = hist_low_col.tolist() if isinstance(hist_low_col, pd.Series) else [float(hist_low_col)]
                
                close_prices = [current_close] + hist_close
                high_prices = [current_high] + hist_high_l
                low_prices = [current_low] + hist_low_l
                
                # MA5（基于5个5分钟周期）
                if len(close_prices) >= 5:
                    indicators['ma5'] = float(np.mean(close_prices[:5]))
                else:
                    indicators['ma5'] = current_close
                
                # MA10
                if len(close_prices) >= 10:
                    indicators['ma10'] = float(np.mean(close_prices[:10]))
                else:
                    indicators['ma10'] = indicators['ma5']
                
                # MA20
                if len(close_prices) >= 20:
                    indicators['ma20'] = float(np.mean(close_prices[:20]))
                else:
                    indicators['ma20'] = indicators['ma10']
                
                # RSI6
                if len(close_prices) >= 7:
                    arr = [float(x) for x in close_prices[:7]]
                    deltas = np.diff(arr)
                    gains = np.where(deltas > 0, deltas, 0)
                    losses = np.where(deltas < 0, -deltas, 0)
                    
                    avg_gain = float(np.mean(gains))
                    avg_loss = float(np.mean(losses))
                    
                    if avg_loss == 0:
                        indicators['rsi6'] = 100.0
                    else:
                        rs = avg_gain / avg_loss
                        indicators['rsi6'] = float(100.0 - (100.0 / (1.0 + rs)))
                else:
                    indicators['rsi6'] = 50.0
                
                # KDJ（正确平滑计算）
                if len(high_prices) >= 9:
                    h_rev = high_prices[::-1]
                    l_rev = low_prices[::-1]
                    c_rev = close_prices[::-1]
                    
                    rsv_list = []
                    for i in range(8, len(c_rev)):
                        highest_n = float(np.max(h_rev[i-8:i+1]))
                        lowest_n = float(np.min(l_rev[i-8:i+1]))
                        close_n = float(c_rev[i])
                        
                        if highest_n != lowest_n:
                            rsv = (close_n - lowest_n) / (highest_n - lowest_n) * 100
                        else:
                            rsv = 50.0
                        rsv_list.append(rsv)
                    
                    k_list = [50.0]
                    for rsv in rsv_list:
                        k = 2.0/3.0 * k_list[-1] + 1.0/3.0 * rsv
                        k_list.append(k)
                    
                    d_list = [50.0]
                    for k in k_list[1:]:
                        d = 2.0/3.0 * d_list[-1] + 1.0/3.0 * k
                        d_list.append(d)
                    
                    if len(k_list) > 0 and len(d_list) > 0:
                        indicators['k'] = round(k_list[-1], 2)
                        indicators['d'] = round(d_list[-1], 2)
                        indicators['j'] = round(3.0 * k_list[-1] - 2.0 * d_list[-1], 2)
                    else:
                        indicators['k'] = 50.0
                        indicators['d'] = 50.0
                        indicators['j'] = 50.0
                else:
                    indicators['k'] = 50.0
                    indicators['d'] = 50.0
                    indicators['j'] = 50.0
                
                # MACD
                if len(close_prices) >= 26:
                    ema12 = float(np.mean(close_prices[:12]))
                    ema26 = float(np.mean(close_prices[:26]))
                    
                    indicators['macd'] = ema12 - ema26
                    indicators['macd_signal'] = indicators['macd']
                    indicators['macd_hist'] = indicators['macd'] - indicators['macd_signal']
                else:
                    indicators['macd'] = 0.0
                    indicators['macd_signal'] = 0.0
                    indicators['macd_hist'] = 0.0
                
                # 布林带
                if len(close_prices) >= 20:
                    mid = float(np.mean(close_prices[:20]))
                    std = float(np.std(close_prices[:20]))
                    
                    indicators['boll_upper'] = mid + 2.0 * std
                    indicators['boll_mid'] = mid
                    indicators['boll_lower'] = mid - 2.0 * std
                else:
                    indicators['boll_upper'] = current_close * 1.05
                    indicators['boll_mid'] = current_close
                    indicators['boll_lower'] = current_close * 0.95
            else:
                # 第一条数据
                current_close = item['price']
                indicators = {
                    'ma5': current_close,
                    'ma10': current_close,
                    'ma20': current_close,
                    'rsi6': 50.0,
                    'macd': 0.0,
                    'macd_signal': 0.0,
                    'macd_hist': 0.0,
                    'k': 50.0,
                    'd': 50.0,
                    'j': 50.0,
                    'boll_upper': current_close * 1.05,
                    'boll_mid': current_close,
                    'boll_lower': current_close * 0.95
                }
            
            # 插入/更新数据（UPSERT）
            upsert_query = """
                INSERT INTO minute_5_price (
                    code, datetime, open, high, low, close, volume, amount, pct_chg,
                    turnover, buy_ratio, sell_ratio,
                    ma5, ma10, ma20, rsi6,
                    macd, macd_signal, macd_hist,
                    k, d, j,
                    boll_upper, boll_mid, boll_lower,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code, datetime) DO UPDATE SET
                    open=excluded.open, high=excluded.high, low=excluded.low,
                    close=excluded.close, volume=excluded.volume, amount=excluded.amount,
                    pct_chg=excluded.pct_chg, ma5=excluded.ma5, ma10=excluded.ma10,
                    ma20=excluded.ma20, rsi6=excluded.rsi6,
                    macd=excluded.macd, macd_signal=excluded.macd_signal, macd_hist=excluded.macd_hist,
                    k=excluded.k, d=excluded.d, j=excluded.j,
                    boll_upper=excluded.boll_upper, boll_mid=excluded.boll_mid,
                    boll_lower=excluded.boll_lower
            """
            
            cursor.execute(upsert_query, (
                code, minute_5_time.strftime('%Y-%m-%d %H:%M:%S'),
                item['open'], item['high'], item['low'], item['price'],
                item['volume'], item['amount'], item['pct_change'],
                0.0, item.get('buy_ratio', '0%'), item.get('sell_ratio', '0%'),
                indicators['ma5'], indicators['ma10'], indicators['ma20'], indicators['rsi6'],
                indicators['macd'], indicators['macd_signal'], indicators['macd_hist'],
                indicators['k'], indicators['d'], indicators['j'],
                indicators['boll_upper'], indicators['boll_mid'], indicators['boll_lower'],
                now.strftime('%Y-%m-%d %H:%M:%S')
            ))
            
            written_count += 1
            
        except Exception as e:
            import traceback
            logger.error(f"  ❌ {code} 写入失败: {e}")
            logger.error(f"  traceback: {traceback.format_exc()[:300]}")
            continue
    
    conn.commit()
    conn.close()
    
    return written_count

# ========== 主流程 ==========

def run_fetch_once():
    """单次采集写入"""
    logger.info(f"\n[采集时间] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 采集实时数据
    data = fetch_realtime()
    
    if not data:
        logger.error(f"\n❌ 采集失败")
        return 0
    
    # 写入数据库
    written = write_minute_5_to_db(data)
    
    logger.info(f"\n✅ 写入minute_5_price表: {written}条")

    # 同时更新 daily_price 表（日线用）
    try:
        from datetime import datetime as dt
        db = DB_PATH
        mconn = sqlite3.connect(db)
        today_s = dt.now().strftime('%Y-%m-%d')
        for code, d in data.items():
            # 统一code格式: 6位 + 后缀
            if not code.endswith(('.SH','.SZ')):
                suffix = '.SH' if code.startswith(('6','5')) else '.SZ'
                code_full = code + suffix
            else:
                code_full = code
            prev_close = float(d.get('prev_close', 0) or 0)
            close_val = float(d['price'])
            pct_val = float(d.get('pct_change', 0) or 0)
            if pct_val == 0.0 and prev_close > 0:
                pct_val = round((close_val - prev_close) / prev_close * 100, 2)
            # UPSERT
            mconn.execute("""
                INSERT INTO daily_price (code, date, close, pct_chg, volume, prev_close, amount, open, high, low)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code, date) DO UPDATE SET 
                    close=excluded.close, pct_chg=excluded.pct_chg, volume=excluded.volume, 
                    prev_close=excluded.prev_close, amount=excluded.amount,
                    open=excluded.open, high=excluded.high, low=excluded.low
            """, (
                code_full, today_s, float(d['price']),
                pct_val, int(d.get('volume', 0)), prev_close,
                float(d.get('amount', 0)), float(d.get('open', d['price'])),
                float(d.get('high', d['price'])), float(d.get('low', d['price']))
            ))
        mconn.commit()
        mconn.close()
        logger.info(f"📅 同步写入daily_price表: {written}条 ({today_s})")
    except Exception as e:
        logger.warning(f"daily_price同步跳过: {e}")

    # 显示前5只股票
    for i, (code, d) in enumerate(list(data.items())[:5], 1):
        logger.info(f"  {i}. {STOCK_NAMES.get(code, code)}({code}): close={d['price']:.2f} | pct={d['pct_change']:+.2f}%")
    
    return written

def run_fetch_continuous(interval_minutes=5):
    """连续采集写入（每5分钟）"""
    global running
    
    logger.info(f"\n启动连续采集模式（每{interval_minutes}分钟）")
    
    # 注册信号处理（Windows兼容）
    try:
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    except Exception as e:
        logger.warning(f"Windows信号注册警告: {e}（可忽略）")
    
    # Windows下使用控制台事件处理
    if os.name == 'nt':
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # 设置控制台事件处理（Ctrl+C等）
            kernel32.SetConsoleCtrlHandler(None, True)
        except:
            logger.warning("Windows控制台事件处理失败（不影响运行）")
    
    # 写入PID文件
    write_pid()
    
    try:
        consecutive_errors = 0  # 连续错误计数
        max_consecutive_errors = 3  # 最大连续错误数
        metrics_save_interval = 300  # Save metrics every 5 minutes (300 seconds)
        last_metrics_save = time.time()
        
        while running:
            try:
                # 判断是否是交易时间（精确判断：9:30-11:30, 13:00-15:00）
                now = datetime.now()
                
                is_weekday = now.weekday() < 5  # 周一至周五
                hour = now.hour
                minute = now.minute
                
                # 上午交易时间：9:30-11:30
                morning_trading = (hour == 9 and minute >= 30) or (hour == 10) or (hour == 11) or (hour == 12 and minute == 0)
                # 下午交易时间：13:00-15:00
                afternoon_trading = (hour == 13) or (hour == 14) or (hour == 15 and minute == 0)
                
                is_trading_hours = morning_trading or afternoon_trading
                
                if is_weekday and is_trading_hours:
                    # 尝试采集，失败则重试
                    try:
                        result = run_fetch_once()
                        if result > 0:
                            consecutive_errors = 0  # 成功，重置错误计数
                            fetcher_metrics.record_fetch_attempt(True, result)
                        else:
                            consecutive_errors += 1
                            fetcher_metrics.record_fetch_attempt(False)
                            logger.warning(f"采集返回0条数据（连续错误: {consecutive_errors}/{max_consecutive_errors}）")
                    except Exception as e:
                        consecutive_errors += 1
                        fetcher_metrics.record_fetch_attempt(False)
                        logger.error(f"采集异常: {e}（连续错误: {consecutive_errors}/{max_consecutive_errors}）")
                        
                        # 连续错误过多，等待更长时间
                        if consecutive_errors >= max_consecutive_errors:
                            logger.error("连续错误过多，等待10分钟后重试")
                            time.sleep(10 * 60)
                            consecutive_errors = 0  # 重置计数
                else:
                    logger.info(f"[非交易时间] {now.strftime('%Y-%m-%d %H:%M:%S')}, 跳过采集")
                
                # 等待下一轮
                next_time = (now + timedelta(minutes=interval_minutes)).strftime('%H:%M')
                logger.info(f"等待{interval_minutes}分钟（下一轮 ≈ {next_time}）")
                
                # 使用更稳定的sleep方式（Windows兼容）
                sleep_seconds = interval_minutes * 60
                while sleep_seconds > 0 and running:
                    sleep_chunk = min(sleep_seconds, 30)  # 每30秒检查一次
                    time.sleep(sleep_chunk)
                    sleep_seconds -= sleep_chunk
                    
                    # Periodically save metrics
                    current_time = time.time()
                    if current_time - last_metrics_save >= metrics_save_interval:
                        fetcher_metrics.save_metrics_to_file()
                        last_metrics_save = current_time
                        
            except KeyboardInterrupt:
                logger.info("用户中断，停止采集")
                running = False
                break
            except Exception as e:
                logger.error(f"采集循环异常: {e}，等待60秒后继续")
                time.sleep(60)
                consecutive_errors = 0
                fetcher_metrics.record_fetch_attempt(False)
                
    except KeyboardInterrupt:
        logger.info("收到中断信号，停止服务")
    finally:
        # 保存最终指标
        fetcher_metrics.save_metrics_to_file()
        # 清理
        remove_pid()
        logger.info("数据采集服务已停止")
# ========== 入口 ==========

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='CSI10 5分钟数据采集写入器')
    parser.add_argument('--once', action='store_true', help='单次采集')
    parser.add_argument('--daemon', action='store_true', help='后台连续采集')
    parser.add_argument('--interval', type=int, default=5, help='采集间隔（分钟）')
    
    args = parser.parse_args()
    
    # 检查是否已有进程运行
    if args.daemon and is_process_running(PID_FILE):
        logger.error(f"已有数据采集进程在运行（PID文件: {PID_FILE}）")
        logger.error("请先停止现有进程，或删除PID文件")
        sys.exit(1)
    
    if args.once:
        run_fetch_once()
    elif args.daemon:
        run_fetch_continuous(args.interval)
    else:
        # 默认使用daemon模式（避免误解为'闪退'）
        logger.info("未指定模式参数，默认使用daemon模式（连续采集）")
        logger.info("提示：使用 --once 参数执行单次采集")
        run_fetch_continuous(args.interval)
