# -*- coding: utf-8 -*-
"""
web_server.py - Stock5 Web服务器
功能：
  1. 提供Web API接口
  2. 实时数据查询
  3. 流式预测输出
  4. 系统状态监控

API端点：
  - /api/minute_5_data：获取5分钟数据
  - /api/predict：实时预测
  - /api/status：系统状态
  - /api/start_collection：启动数据采集
  - /api/stop_collection：停止数据采集

运行方式：
  python web_server.py
"""

import sys
import os
sys.stdout.reconfigure(encoding='utf-8')

# 将项目根目录添加到 Python 路径，确保模块可导入
_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from flask import Flask, jsonify, request, Response, stream_with_context, send_from_directory
import sqlite3
import json
import subprocess
import psutil
import os
from datetime import datetime, date, timedelta
import time
import socket
import logging
from logging.handlers import TimedRotatingFileHandler
from functools import wraps
import threading
import collections

app = Flask(__name__)

# Metrics collection for monitoring
class MetricsCollector:
    def __init__(self):
        self.request_count = collections.defaultdict(int)
        self.error_count = collections.defaultdict(int)
        self.latency_times = collections.defaultdict(list)
        self.last_reset = datetime.now()
        self._lock = threading.Lock()
    
    def record_request(self, endpoint, method, status_code, latency):
        with self._lock:
            self.request_count[f"{method}:{endpoint}"] += 1
            if status_code >= 400:
                self.error_count[f"{method}:{endpoint}"] += 1
            self.latency_times[f"{method}:{endpoint}"].append(latency)
            # Keep only last 100 latencies
            if len(self.latency_times[f"{method}:{endpoint}"]) > 100:
                self.latency_times[f"{method}:{endpoint}"] = self.latency_times[f"{method}:{endpoint}"][-100:]
    
    def get_metrics(self):
        with self._lock:
            metrics = {
                'requests': dict(self.request_count),
                'errors': dict(self.error_count),
                'latency': {},
                'timestamp': datetime.now().isoformat()
            }
            for key, times in self.latency_times.items():
                if times:
                    metrics['latency'][key] = {
                        'avg': sum(times) / len(times),
                        'min': min(times),
                        'max': max(times),
                        'count': len(times)
                    }
            return metrics
    
    def reset(self):
        with self._lock:
            self.request_count.clear()
            self.error_count.clear()
            self.latency_times.clear()
            self.last_reset = datetime.now()

metrics = MetricsCollector()

def monitor_request(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        start_time = time.time()
        try:
            result = f(*args, **kwargs)
            status_code = getattr(result, 'status_code', 200) if hasattr(result, 'status_code') else 200
            latency = time.time() - start_time
            metrics.record_request(request.path, request.method, status_code, latency)
            return result
        except Exception as e:
            latency = time.time() - start_time
            metrics.record_request(request.path, request.method, 500, latency)
            raise e
    return decorated_function

# 配置 - 使用相对路径
import pathlib
PROJECT_DIR = pathlib.Path(__file__).parent.absolute()
DB_PATH = PROJECT_DIR / "stocks.db"
PID_FILE = PROJECT_DIR / "collection.pid"
WEB_PORT = 5005

def check_port_available(port: int) -> bool:
    """检查端口是否可用"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', port))
            return True
    except OSError:
        return False

def is_collection_running() -> bool:
    """检查数据采集进程是否运行"""
    if not os.path.exists(PID_FILE):
        return False
    
    try:
        with open(PID_FILE, 'r', encoding='utf-8') as f:
            pid = int(f.read().strip())
        return psutil.pid_exists(pid)
    except:
        return False

# 检查端口
if not check_port_available(WEB_PORT):
    print(f"⚠ 端口 {WEB_PORT} 已被占用，尝试清理...")
    # 尝试杀掉占用端口的进程
    try:
        occupied = os.popen(f'netstat -ano | findstr ":{WEB_PORT} " | findstr LISTENING').read().strip().split()
        for item in occupied:
            pid = item.split()[-1]
            if pid.isdigit():
                os.kill(int(pid), 9)
                print(f"  已杀掉占用进程 PID: {pid}")
        import time; time.sleep(1)
    except:
        pass
    # 再次检查
    if not check_port_available(WEB_PORT):
        print(f"  ❌ 端口 {WEB_PORT} 仍无法释放，请手动关闭占用进程")
        print(f"  命令: netstat -ano | findstr :5005")
        sys.exit(1)
    else:
        print(f"  ✓ 端口 {WEB_PORT} 已释放")

print("=" * 70)
print("Stock5 Web服务器")
print(f"端口: {WEB_PORT}")
print("API: /api/minute_5_data, /api/predict, /api/status")
print("=" * 70)

# 配置日志（带日志轮转：每天切割，保留30天）
LOG_DIR = os.path.join(_project_root, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, 'web_server.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        TimedRotatingFileHandler(LOG_FILE, when='midnight', interval=1, backupCount=30, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('web_server')

# ========== 静态文件 ==========

JSON_FILES = {'result_v5_minute.json', 'result_v5.json'}

@app.route('/result_v5_minute.json')
@app.route('/result_v5.json')
def serve_result_json():
    """提供预测结果 JSON 文件"""
    filename = request.path.lstrip('/')
    filepath = os.path.join(PROJECT_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({'error': f'{filename} not found'}), 404
    resp = app.response_class(
        response=open(filepath, 'r', encoding='utf-8').read(),
        mimetype='application/json'
    )
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@monitor_request
@app.route('/')
def index():
    """返回前端页面"""
    try:
        with open(f'{PROJECT_DIR}/index.html', 'r', encoding='utf-8') as f:
            return f.read()
    except:
        return jsonify({'error': 'index.html not found'})

@monitor_request
@app.route('/health')
def health_check():
    """Liveness probe - checks if the service is running"""
    return jsonify({
        'status': 'alive',
        'timestamp': datetime.now().isoformat(),
        'service': 'stock5-web'
    })

@monitor_request
@app.route('/ready')
def readiness_check():
    """Readiness probe - checks if the service is ready to handle requests"""
    checks = {
        'database': False,
        'collection_process': False,
        'port_available': True
    }
    
    # Check database connection
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.execute('SELECT 1')
        conn.close()
        checks['database'] = True
    except Exception:
        checks['database'] = False
    
    # Check if data collection process is running
    checks['collection_process'] = is_collection_running()
    
    # Determine overall readiness
    ready = all(checks.values())
    
    status_code = 200 if ready else 503
    return jsonify({
        'status': 'ready' if ready else 'not ready',
        'timestamp': datetime.now().isoformat(),
        'checks': checks
    }), status_code

@monitor_request
@app.route('/api/status')
def api_status():
    """系统状态"""
    # 检查数据采集进程
    collection_running = False
    collection_pid = None
    
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r', encoding='utf-8') as f:
                pid_str = f.read().strip()
                if pid_str:
                    pid = int(pid_str)
                    collection_pid = pid
                    if psutil.pid_exists(pid):
                        collection_running = True
        except (ValueError, OSError):
            pass
    
    # 检查数据库
    conn = sqlite3.connect(DB_PATH)
    
    minute_5_count = conn.execute("SELECT COUNT(*) FROM minute_5_price").fetchone()[0]
    
    # Get latest data timestamp
    latest_timestamp = None
    try:
        latest_row = conn.execute("SELECT MAX(date) FROM minute_5_price").fetchone()
        if latest_row and latest_row[0]:
            latest_timestamp = latest_row[0]
    except Exception:
        pass
    
    conn.close()
    
    status = {
        'timestamp': datetime.now().isoformat(),
        'collection_running': collection_running,
        'collection_pid': collection_pid,
        'minute_5_data_count': minute_5_count,
        'latest_data_timestamp': latest_timestamp,
        'db_path': str(DB_PATH),  # 转换为字符串
        'status': 'ok' if collection_running and minute_5_count > 0 else 'warning',
        'uptime_seconds': None
    }
    
    return jsonify(status)

@monitor_request
@app.route('/api/metrics')
def get_metrics():
    """Prometheus-style metrics endpoint"""
    return jsonify(metrics.get_metrics())

@monitor_request
@app.route('/api/minute_5_data')
def api_minute_5_data():
    """获取5分钟数据"""
    conn = sqlite3.connect(DB_PATH)
    
    # 查询最近数据
    limit = request.args.get('limit', 50, type=int)
    
    data = conn.execute("""\
        SELECT code, date, close, pct_chg, ma5, ma10, ma20, rsi6, k, d, j, macd\
        FROM minute_5_price\
        ORDER BY date DESC\
        LIMIT ?\
    """, (limit,)).fetchall()
    
    conn.close()
    
    # 转换为JSON格式
    result = []
    
    for row in data:
        result.append({
            'code': row[0],
            'date': row[1],
            'close': row[2],
            'pct_chg': row[3],
            'ma5': row[4],
            'ma10': row[5],
            'ma20': row[6],
            'rsi6': row[7],
            'k': row[8],
            'd': row[9],
            'j': row[10],
            'macd': row[11]
        })
    
    return jsonify({
        'count': len(result),
        'data': result
    })

@app.route('/api/predict', methods=['POST'])
def api_predict():
    """实时预测"""
    try:
        from analyzer_v5_minute import predict_minute_5
        
        data = request.json or {}
        
        # 获取股票代码列表
        codes = data.get('codes', [])
        
        if not codes:
            # 如果没有指定股票，使用所有股票
            conn = sqlite3.connect(DB_PATH)
            
            codes = conn.execute("""
                SELECT DISTINCT code FROM minute_5_price
                ORDER BY date DESC
                LIMIT 30
            """).fetchall()
            
            codes = [code[0] for code in codes]
            
            conn.close()
        
        # 执行预测
        predictions = predict_minute_5(codes)
        
        # 同时写入结果 JSON
        result = {
            'timestamp': datetime.now().isoformat(),
            'version': 'v5_minute',
            'predictions': predictions,
            'count': len(predictions)
        }
        with open(f'{PROJECT_DIR}/result_v5_minute.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        return jsonify({
            'success': True,
            'count': len(predictions),
            'predictions': predictions,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"预测失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/run_predict', methods=['POST'])
def api_run_predict():
    """后台运行双引擎预测，输出JSON文件"""
    try:
        import subprocess as sp
        # 5分钟预测（引擎1）— 同步执行
        logger.info("执行5分钟预测引擎...")
        proc_minute = sp.Popen(
            ['python', f'{PROJECT_DIR}/analyzer_v5_minute.py'],
            cwd=PROJECT_DIR, stdout=sp.PIPE, stderr=sp.PIPE,
            encoding='utf-8', errors='replace'
        )
        stdout_m, stderr_m = proc_minute.communicate(timeout=60)
        if proc_minute.returncode != 0:
            logger.error(f"5分钟预测失败: {stderr_m[:200]}")
        
        # 日线预测（引擎2）— 同步执行
        logger.info("执行日线预测引擎...")
        proc_daily = sp.Popen(
            ['python', f'{PROJECT_DIR}/analyzer_v5.py'],
            cwd=PROJECT_DIR, stdout=sp.PIPE, stderr=sp.PIPE,
            encoding='utf-8', errors='replace'
        )
        stdout_d, stderr_d = proc_daily.communicate(timeout=120)
        if proc_daily.returncode != 0 and proc_daily.returncode != 124:
            logger.error(f"日线预测失败: {stderr_d[:200]}")
        
        return jsonify({
            'success': True,
            'minute_ok': proc_minute.returncode == 0,
            'daily_ok': proc_daily.returncode in (0, 124),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"run_predict失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/predict_stream', methods=['POST'])
def api_predict_stream():
    """流式预测"""
    def generate():
        from analyzer_v5_minute import predict_minute_5_single
        
        data = request.json
        
        codes = data.get('codes', [])
        
        if not codes:
            conn = sqlite3.connect(DB_PATH)
            
            codes = conn.execute("""
                SELECT DISTINCT code FROM minute_5_price
                ORDER BY date DESC
                LIMIT 30
            """).fetchall()
            
            codes = [code[0] for code in codes]
            
            conn.close()
        
        for code in codes:
            prediction = predict_minute_5_single(code)
            
            yield f'data: {json.dumps(prediction)}\n\n'
            
            time.sleep(0.1)
        
        yield f'data: {json.dumps({"done": True})}\n\n'
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream'
    )

@app.route('/api/start_collection', methods=['POST'])
def api_start_collection():
    """启动数据采集"""
    # 检查是否已经运行
    if os.path.exists(PID_FILE):
        with open(PID_FILE, 'r', encoding='utf-8') as f:
            pid = int(f.read().strip())
        
        if psutil.pid_exists(pid):
            return jsonify({
                'success': False,
                'message': '数据采集已在运行'
            })
    
    # 启动后台进程
    # 启动后台进程（使用python而不是pythonw，能看到输出）
    process = subprocess.Popen(
        ['python', f'{PROJECT_DIR}/realtime_fetcher.py', '--daemon', '--interval', '5'],
        cwd=PROJECT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding='utf-8',
        errors='replace',
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
    )
    
    # 写入PID文件
    with open(PID_FILE, 'w', encoding='utf-8') as f:
        f.write(str(process.pid))
    
    return jsonify({
        'success': True,
        'pid': process.pid,
        'message': '数据采集已启动'
    })

@app.route('/api/stop_collection', methods=['POST'])
def api_stop_collection():
    """停止数据采集"""
    if not os.path.exists(PID_FILE):
        return jsonify({
            'success': False,
            'message': '数据采集未运行'
        })
    
    with open(PID_FILE, 'r', encoding='utf-8') as f:
        pid = int(f.read().strip())
    
    if psutil.pid_exists(pid):
        try:
            process = psutil.Process(pid)
            process.terminate()
            
            # 删除PID文件
            os.remove(PID_FILE)
            
            return jsonify({
                'success': True,
                'message': '数据采集已停止'
            })
        except Exception as e:
            return jsonify({
                'success': False,
                'message': f'停止失败: {str(e)}'
            })
    else:
        # 删除过期PID文件
        os.remove(PID_FILE)
        
        return jsonify({
            'success': True,
            'message': '数据采集已停止（PID不存在）'
        })

@app.route('/api/run_strategy', methods=['POST'])
def api_run_strategy():
    """运行交易策略引擎，生成交易信号"""
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from strategy.strategy_engine import run_strategy
        
        # 运行策略
        result = run_strategy()
        
        return jsonify({
            'success': True,
            'message': '策略执行成功',
            'data': {
                'buy': len(result.get('recommendations', {}).get('buy', [])),
                'hold': len(result.get('recommendations', {}).get('hold', [])),
                'sell': len(result.get('recommendations', {}).get('sell', []))
            }
        })
    except Exception as e:
        logger.error(f"run_strategy失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/kline/<code>')
def api_kline(code):
    """获取K线数据：优先查 daily_price（个股），回退到 index_daily（指数）"""
    try:
        conn = sqlite3.connect(DB_PATH)
        
        # 处理代码格式
        code = code.strip().upper()
        
        # 标准化为不带后缀的纯数字代码
        code_num = code.replace('.SH', '').replace('.SZ', '')
        
        # 准备多种格式的查询
        code_sh = code_num + '.SH'
        code_sz = code_num + '.SZ'
        code_sh_lower = 'sh.' + code_num
        code_sz_lower = 'sz.' + code_num
        
        # 先查个股 daily_price
        data = conn.execute("""SELECT date,open,high,low,close,volume FROM daily_price 
            WHERE code IN (?, ?) ORDER BY date DESC LIMIT 60""", 
            (code_sh, code_sz)).fetchall()
        
        source = 'stock'
        if not data:
            # 尝试指数 index_daily - 支持多种格式: sh.000001, 000001.SH, 000001.SZ
            data = conn.execute("""SELECT date,open,high,low,close,volume FROM index_daily 
                WHERE code IN (?, ?, ?, ?, ?) ORDER BY date DESC LIMIT 60""", 
                (code_sh, code_sz, code_sh_lower, code_sz_lower, code_num + '.SH')).fetchall()
            source = 'index'
        
        conn.close()
        kline = []
        for row in reversed(data):
            kline.append({'date':row[0][:10] if row[0] else '','open':float(row[1]) if row[1] else 0,'high':float(row[2]) if row[2] else 0,'low':float(row[3]) if row[3] else 0,'close':float(row[4]) if row[4] else 0,'volume':float(row[5]) if row[5] else 0})
        return jsonify({'code':code,'kline':kline,'source':source})
    except Exception as e:
        return jsonify({'error':str(e)}),500
@app.route('/api/market_index')
def api_market_index():
    """获取大盘指数K线（默认沪深300 000300.SH，支持 ?code=000905.SH）"""
    try:
        code = request.args.get('code', '000300.SH')
        name_map = {'000300.SH': '沪深300', '000905.SH': '中证500'}
        name = name_map.get(code, code)
        
        conn = sqlite3.connect(DB_PATH)
        
        data = conn.execute("""
            SELECT date, open, high, low, close, volume
            FROM index_daily
            WHERE code = ?
            ORDER BY date DESC
            LIMIT 60
        """, (code,)).fetchall()
        
        conn.close()
        
        if not data:
            return jsonify({'code': code, 'name': name, 'kline': []})
        
        kline = []
        for row in reversed(data):
            kline.append({
                'date': row[0][:10] if row[0] else '',
                'open': float(row[1]) if row[1] else 0,
                'high': float(row[2]) if row[2] else 0,
                'low': float(row[3]) if row[3] else 0,
                'close': float(row[4]) if row[4] else 0,
                'volume': float(row[5]) if row[5] else 0
            })
        
        return jsonify({'code': code, 'name': name, 'kline': kline})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ========== 主程序 ==========

if __name__ == '__main__':
    print(f"\n启动Web服务器（端口{WEB_PORT}）")
    
    app.run(host='127.0.0.1', port=WEB_PORT, debug=False)
# ---- Frontend static serving configuration ----
import os

# 将前端构建产物放在 run/frontend 目录下，供生产环境使用
FRONTEND_STATIC = os.path.join(PROJECT_DIR, 'run', 'frontend')
# 如果 run/frontend 不存在则回退到 src/frontend（开发时直接访问）
if not os.path.isdir(FRONTEND_STATIC):
    FRONTEND_STATIC = os.path.join(PROJECT_DIR, 'src', 'frontend')

# 覆盖 Flask 的 static_folder，以便直接提供前端文件
app = Flask(__name__, static_folder=FRONTEND_STATIC, static_url_path='')

@app.route('/')
def index():
    # 直接返回前端的 index.html
    return send_from_directory(FRONTEND_STATIC, 'index.html')
