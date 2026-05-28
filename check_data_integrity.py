# -*- coding: utf-8 -*-
"""
数据校验脚本 — 验证 stock5 数据库的完整性、时效性、一致性
输出：JSON 格式检查报告（既用于命令行也用于 GUI 展示）
"""
import json, sqlite3, sys
from datetime import datetime, timedelta

DB_PATH = r'E:\stock5\stocks.db'
CSV_PATH = r'e:\stock5\波段股票Top30.csv'
RESULT_PATH = r'e:\stock5\result_v5.json'

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
    
    conn = sqlite3.connect(DB_PATH)
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
        r = conn.execute(f"SELECT MAX(date) FROM index_daily WHERE code='{c}'").fetchone()[0]
        if r: idx_latest[c] = r
    max_idx_date = max(idx_latest.values()) if idx_latest else None
    
    if max_idx_date:
        days_diff = (today_ts - datetime.strptime(max_idx_date, '%Y-%m-%d')).days
        status = 'PASS' if days_diff <= 2 else ('WARN' if days_diff <= 7 else 'ERROR')
        _check('大盘日线数据时效性', status,
               f'最新日期: {max_idx_date} ({days_diff}天前)')
    else:
        _check('大盘日线数据', 'ERROR', '无数据')
    
    # sh.格式是否有pct_chg
    sh300_latest = conn.execute("SELECT MAX(date) FROM index_daily WHERE code='sh.000300' AND pct_chg IS NOT NULL").fetchone()[0]
    _check('sh.000300 pct_chg覆盖', 'PASS' if sh300_latest else 'WARN',
           f'最新pct_chg日期: {sh300_latest or "无数据"}')
    
    # ─── 3. macro_factors 时效性 ───
    mf_max = conn.execute("SELECT MAX(date) FROM macro_factors").fetchone()[0]
    if mf_max:
        days_diff = (today_ts - datetime.strptime(mf_max, '%Y-%m-%d')).days
        status = 'PASS' if days_diff <= 2 else ('WARN' if days_diff <= 7 else 'ERROR')
        mf_cnt = conn.execute("SELECT COUNT(*) FROM macro_factors WHERE date=?", (mf_max,)).fetchone()[0]
        # 检查趋势字段
        has_trend = conn.execute(f"SELECT COUNT(*) FROM macro_factors WHERE date='{mf_max}' AND hs300_trend IS NOT NULL").fetchone()[0]
        trend_ok = has_trend > 0
        _check('宏观因子时效性', status,
               f'最新日期: {mf_max} ({days_diff}天前, {mf_cnt}条, 趋势字段{"有" if trend_ok else "无"})')
    else:
        _check('宏观因子', 'ERROR', '无数据')
    
    # ─── 4. 30只股票数据完整性 ───
    import csv
    codes = []
    with open(CSV_PATH, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            codes.append(row['股票代码'])
    missing = []
    short_data = []
    for c in codes:
        cnt = conn.execute(f"SELECT COUNT(*) FROM daily_price WHERE code='{c}'").fetchone()[0]
        if cnt == 0: missing.append(c)
        elif cnt < 100: short_data.append(c)
    
    _check('股票池完整性', 'PASS' if not missing else 'ERROR',
           f'{len(codes)}只中{len(missing)}只缺失' if missing else f'{len(codes)}只全部有数据')
    
    # 每只股票最新日期
    late_codes = []
    for c in codes:
        dt = conn.execute(f"SELECT MAX(date) FROM daily_price WHERE code='{c}'").fetchone()[0]
        if dt and dt < (today_ts - timedelta(days=7)).strftime('%Y-%m-%d'):
            late_codes.append(f'{c}({dt})')
    _check('股票数据时效性', 'PASS' if not late_codes else 'WARN',
           f'{len(late_codes)}只股票数据滞后7天以上' if late_codes else '全部在7天内')
    
    # ─── 5. 基本面因子 ───
    fs_cnt = conn.execute("SELECT COUNT(*) FROM factor_signals").fetchone()[0]
    fs_codes = conn.execute("SELECT COUNT(DISTINCT code) FROM factor_signals").fetchone()[0]
    fs_dates = conn.execute("SELECT MIN(date), MAX(date) FROM factor_signals").fetchone()
    _check('基本面因子', 'PASS' if fs_cnt >= len(codes) else 'WARN',
           f'{fs_cnt}条({fs_codes}只股票), 日期{fs_dates[0]}~{fs_dates[1]}')
    
    # ─── 6. 各股票日线行数一致性 ───
    counts = [conn.execute(f"SELECT COUNT(*) FROM daily_price WHERE code='{c}'").fetchone()[0] for c in codes]
    if counts:
        min_c, max_c = min(counts), max(counts)
        _check('日线数据量一致性', 'PASS' if max_c - min_c < 20 else 'WARN',
               f'行数范围 {min_c}~{max_c} (差异{max_c-min_c}天)')
    
    # ─── 7. 最近一次分析结果 ───
    try:
        with open(RESULT_PATH) as f:
            result = json.load(f)
        rs = result.get('stocks', [])
        rdate = result.get('timestamp', '?')
        rs_scores = [s['score'] for s in rs]
        _check('最近分析结果', 'PASS' if len(rs) > 0 else 'WARN',
               f'{len(rs)}只, 时间{rdate}, 评分范围{min(rs_scores)}~{max(rs_scores)}')
    except:
        _check('最近分析结果', 'WARN', 'result_v5.json 不存在或解析失败')
    
    # ─── 8. 大盘data一致性：sh.000300和000300.SH收盘价差异 ───
    for code_pair, name in [(('sh.000300','000300.SH'),'沪深300'), (('sh.000905','000905.SH'),'中证500')]:
        common_dates = conn.execute(f"""
            SELECT a.date, a.close, b.close 
            FROM index_daily a JOIN index_daily b ON a.date=b.date
            WHERE a.code='{code_pair[0]}' AND b.code='{code_pair[1]}'
            AND ABS(a.close - b.close) > 1
        """).fetchall()
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
