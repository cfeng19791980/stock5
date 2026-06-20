# -*- coding: utf-8 -*-
"""
数据校验脚本 — 验证 stock5 数据库的完整性、时效性、一致性
输出：JSON 格式检查报告（既用于命令行也用于 GUI 展示）
"""
import json, sqlite3, sys, os, logging
from datetime import datetime, timedelta
from pathlib import Path

# ========== 告警配置 ==========
# 告警方式：Windows 弹窗（MessageBox）
# 告警冷却（同一类型告警在冷却期内不重复弹窗，单位：秒）
ALERT_COOLDOWN = int(os.environ.get('STOCK5_ALERT_COOLDOWN', '3600'))
ALERT_STATE_FILE = Path(os.environ.get('STOCK5_ALERT_STATE', r'E:\stock5\logs\.alert_state.json'))

logger = logging.getLogger(__name__)

def _load_alert_state():
    """加载告警冷却状态"""
    try:
        if ALERT_STATE_FILE.exists():
            return json.loads(ALERT_STATE_FILE.read_text(encoding='utf-8'))
    except Exception:
        pass
    return {}

def _save_alert_state(state):
    """保存告警冷却状态"""
    try:
        ALERT_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        ALERT_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
    except Exception as e:
        logger.warning(f"保存告警状态失败: {e}")

def _should_alert(alert_key):
    """检查是否应该发送告警（冷却期内不重复）"""
    state = _load_alert_state()
    last_sent = state.get(alert_key, 0)
    return (datetime.now().timestamp() - last_sent) > ALERT_COOLDOWN

def _mark_alerted(alert_key):
    """标记告警已发送"""
    state = _load_alert_state()
    state[alert_key] = datetime.now().timestamp()
    _save_alert_state(state)

def _send_windows_popup(title, content):
    """发送 Windows 弹窗告警（使用 ctypes MessageBoxW，无需额外依赖）"""
    try:
        import ctypes
        # MB_ICONWARNING=0x30, MB_OK=0x00, MB_SYSTEMMODAL=0x1000（置顶）
        ctypes.windll.user32.MessageBoxW(
            0,                              # hWnd = NULL
            content,                        # 消息内容
            title,                          # 标题栏
            0x30 | 0x1000                   # MB_ICONWARNING | MB_SYSTEMMODAL
        )
        return True
    except Exception as e:
        logger.warning(f"Windows弹窗发送失败: {e}")
        # 降级：输出到 stderr
        print(f"[ALERT] {title}\n{content}", file=sys.stderr)
        return False

def send_alert(report):
    """根据校验报告发送 Windows 弹窗告警（仅在有 ERROR 时触发）"""
    errors = [c for c in report['checks'] if c['status'] == 'ERROR']
    if not errors:
        return

    # 生成告警键（基于错误名称集合，避免同类告警刷屏）
    alert_key = 'errors:' + ','.join(sorted(e['name'] for e in errors))
    if not _should_alert(alert_key):
        logger.info("告警冷却中，跳过弹窗")
        return

    # 构建告警内容（纯文本，适合弹窗显示）
    ts = report.get('timestamp', datetime.now().isoformat())
    s = report['summary']
    title = f"Stock5 数据校验异常 ({s['errors']}项错误)"
    lines = [f"时间: {ts}", "", "错误:"]
    for e in errors:
        lines.append(f"  [X] {e['name']}: {e['detail']}")
    # 附加警告
    warns = [c for c in report['checks'] if c['status'] == 'WARN']
    if warns:
        lines.append(f"\n警告 ({len(warns)}项):")
        for w in warns:
            lines.append(f"  [!] {w['name']}: {w['detail']}")
    content = '\n'.join(lines)

    # 弹窗
    if _send_windows_popup(title, content):
        logger.info("Windows弹窗告警已发送")
        _mark_alerted(alert_key)

# Paths can be configured via environment variables to avoid hardcoded E:\ paths
DB_PATH = Path(os.environ.get('STOCK5_DB_PATH', r'E:\stock5\stocks.db'))
CSV_PATH = Path(os.environ.get('STOCK5_CSV_PATH', r'E:\stock5\波段股票Top30.csv'))
RESULT_PATH = Path(os.environ.get('STOCK5_RESULT_PATH', r'E:\stock5\result_v5.json'))


def _safe_one(cursor, query, params=()):
    try:
        row = cursor.execute(query, params).fetchone()
        return row[0] if row and len(row) > 0 else None
    except Exception:
        return None

def check():
    report = {
        'timestamp': datetime.now().isoformat(),
        'passed': 0, 'warnings': 0, 'errors': 0,
        'checks': [],
    }
    def _check(name, status, detail):
        report['checks'].append({'name': name, 'status': status, 'detail': detail})
        if status == 'PASS': report['passed'] += 1
        elif status == 'WARN': report['warnings'] += 1
        else: report['errors'] += 1
    
    # 前置检查：确认文件存在
    try:
        if not DB_PATH.exists():
            _check('数据库文件', 'ERROR', f'未找到数据库文件: {DB_PATH}')
            return report
    except Exception:
        _check('数据库文件', 'ERROR', f'路径不可访问: {DB_PATH}')
        return report

    conn = sqlite3.connect(str(DB_PATH))
    today = datetime.now().strftime('%Y-%m-%d')
    today_ts = datetime.now()
    
    # ─── 1. 基础完整性 ───
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    required = ['daily_price', 'index_daily', 'macro_factors', 'factor_signals']
    for t in required:
        if t in tables:
            cnt = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
            _check(f'表存在: {t}', 'PASS', f'{cnt}条')
        else:
            _check(f'表存在: {t}', 'FAIL', '表缺失')
    
    # ─── 2. 大盘数据时效性 ───
    idx_formats = ['sh.000300', 'sh.000905', '000300.SH', '000905.SH']
    idx_latest = {}
    for c in idx_formats:
        r = _safe_one(conn, "SELECT MAX(date) FROM index_daily WHERE code=?", (c,))
        if r:
            idx_latest[c] = r
    max_idx_date = max(idx_latest.values()) if idx_latest else None
    
    if max_idx_date:
        days_diff = (today_ts - datetime.strptime(max_idx_date, '%Y-%m-%d')).days
        status = 'PASS' if days_diff <= 3 else ('WARN' if days_diff <= 10 else 'ERROR')
        _check('大盘日线数据时效性', status,
               f'最新日期: {max_idx_date} ({days_diff}天前)')
    else:
        _check('大盘日线数据', 'ERROR', '无数据')
    
    # sh.格式是否有pct_chg
        sh300_latest = _safe_one(conn, "SELECT MAX(date) FROM index_daily WHERE code=? AND pct_chg IS NOT NULL", ('sh.000300',))
        _check('sh.000300 pct_chg覆盖', 'PASS' if sh300_latest else 'WARN',
            f'最新pct_chg日期: {sh300_latest or "无数据"}')
    
    # ─── 3. macro_factors 时效性 ───
    mf_max = _safe_one(conn, "SELECT MAX(date) FROM macro_factors")
    if mf_max:
        try:
            days_diff = (today_ts - datetime.strptime(mf_max, '%Y-%m-%d')).days
        except Exception:
            days_diff = 9999
        status = 'PASS' if days_diff <= 2 else ('WARN' if days_diff <= 7 else 'ERROR')
        mf_cnt = _safe_one(conn, "SELECT COUNT(*) FROM macro_factors WHERE date=?", (mf_max,)) or 0
        # 检查趋势字段
        has_trend = _safe_one(conn, "SELECT COUNT(*) FROM macro_factors WHERE date=? AND hs300_trend IS NOT NULL", (mf_max,)) or 0
        trend_ok = has_trend > 0
        _check('宏观因子时效性', status,
               f'最新日期: {mf_max} ({days_diff}天前, {mf_cnt}条, 趋势字段{"有" if trend_ok else "无"})')
    else:
        _check('宏观因子', 'ERROR', '无数据')
    
    # ─── 4. 30只股票数据完整性 ───
    import csv
    codes = []
    if not CSV_PATH.exists():
        _check('股票池CSV', 'ERROR', f'CSV 文件未找到: {CSV_PATH}')
        conn.close()
        return report
    with open(CSV_PATH, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        # 支持多种可能的列名
        for row in reader:
            code = row.get('股票代码') or row.get('代码') or row.get('code') or row.get('stock_code')
            if not code:
                # 忽略格式错误的行，但记录警告
                _check('股票池CSV 行', 'WARN', f'CSV 行缺少代码字段: {row}')
                continue
            codes.append(code.strip())
    missing = []
    short_data = []
    for c in codes:
        cnt = _safe_one(conn, "SELECT COUNT(*) FROM daily_price WHERE code=?", (c,)) or 0
        if cnt == 0: missing.append(c)
        elif cnt < 100: short_data.append(c)
    
    _check('股票池完整性', 'PASS' if not missing else 'ERROR',
           f'{len(codes)}只中{len(missing)}只缺失' if missing else f'{len(codes)}只全部有数据')
    
    # 每只股票最新日期
    late_codes = []
    for c in codes:
        dt = _safe_one(conn, "SELECT MAX(date) FROM daily_price WHERE code=?", (c,))
        if dt and dt < (today_ts - timedelta(days=7)).strftime('%Y-%m-%d'):
            late_codes.append(f'{c}({dt})')
    _check('股票数据时效性', 'PASS' if not late_codes else 'WARN',
           f'{len(late_codes)}只股票数据滞后7天以上' if late_codes else '全部在7天内')
    
    # ─── 5. 基本面因子 ───
    fs_cnt = _safe_one(conn, "SELECT COUNT(*) FROM factor_signals") or 0
    fs_codes = _safe_one(conn, "SELECT COUNT(DISTINCT code) FROM factor_signals") or 0
    fs_dates_row = None
    try:
        fs_dates_row = conn.execute("SELECT MIN(date), MAX(date) FROM factor_signals").fetchone()
    except Exception:
        fs_dates_row = (None, None)
    _check('基本面因子', 'PASS' if fs_cnt >= len(codes) else 'WARN',
           f'{fs_cnt}条({fs_codes}只股票), 日期{fs_dates_row[0]}~{fs_dates_row[1]}')
    
    # ─── 6. 各股票日线行数一致性 ───
    counts = [(_safe_one(conn, "SELECT COUNT(*) FROM daily_price WHERE code=?", (c,)) or 0) for c in codes]
    if counts:
        min_c, max_c = min(counts), max(counts)
        _check('日线数据量一致性', 'PASS' if max_c - min_c < 20 else 'WARN',
               f'行数范围 {min_c}~{max_c} (差异{max_c-min_c}天)')
    
    # ─── 7. 最近一次分析结果 ───
    try:
        with open(RESULT_PATH, encoding='utf-8') as f:
            result = json.load(f)
        rs = result.get('stocks', [])
        rdate = result.get('timestamp', '?')
        rs_scores = [s['score'] for s in rs if 'score' in s]
        if not rs_scores:
            _check('最近分析结果', 'WARN', f'{len(rs)}只股票但无评分数据')
        else:
            _check('最近分析结果', 'PASS' if len(rs) > 0 else 'WARN',
                   f'{len(rs)}只, 时间{rdate}, 评分范围{min(rs_scores)}~{max(rs_scores)}')
    except Exception as e:
        _check('最近分析结果', 'WARN', f'result_v5.json 不存在或解析失败: {e}')
    
    # ─── 8. 大盘data一致性：sh.000300和000300.SH收盘价差异 ───
    for code_pair, name in [(('sh.000300','000300.SH'),'沪深300'), (('sh.000905','000905.SH'),'中证500')]:
        common_dates = conn.execute("""
            SELECT a.date, a.close, b.close 
            FROM index_daily a JOIN index_daily b ON a.date=b.date
            WHERE a.code=? AND b.code=?
            AND ABS(a.close - b.close) > 1
        """, (code_pair[0], code_pair[1])).fetchall()
        if common_dates:
            _check(f'{name}双格式一致性', 'WARN', f'{len(common_dates)}天差异>1点')
        else:
            _check(f'{name}双格式一致性', 'PASS', '两种格式收盘价一致')
    
    conn.close()
    
    # 汇总
    report['summary'] = {
        'total': len(report['checks']),
        'passed': report['passed'],
        'warnings': report['warnings'],
        'errors': report['errors'],
        'all_pass': report['errors'] == 0,
    }
    return report

if __name__ == '__main__':
    report = check()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    # 有 ERROR 时弹出 Windows 告警
    send_alert(report)
