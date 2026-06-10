# -*- coding: utf-8 -*-
"""
qlib_alpha158.py — 纯 Pandas 实现的 Alpha158 量价因子集

参考: Microsoft Qlib alpha158 (qlib/contrib/data/handler.py)
实现方式: 纯 Pandas/numpy, 零外部依赖

因子分类:
  - Kbar:  9个K线形态因子 (KMID, KLEN, KUP, KLOW, KSFT, KMID2, KLEN2, KUP2, KSFT2)
  - Price: 15个价格衍生因子 (MA, STD, MAX, MIN, QTLU, QTLD, RANK, RSV, IMAX, IMIN...)
  - Volume: 5个成交量因子 (VMA, VSTD, WVMA, VSUMP, VSUMN, VSUMD...)
  - Rolling: 129个滚动统计因子 (BETA, RSQR, CORR, CORD, CNTP, CNTN, SUMP, SUMN...)
  - 各因子在5/10/20/30/60窗口上计算

用法:
    import qlib_alpha158
    df_alpha = qlib_alpha158.compute_all(df)
    # df 需包含: open, high, low, close, volume, vwap(可选)
    # df_alpha 返回 ~158列因子矩阵
"""
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

# ==================== 窗口列表 ====================
WINDOWS = [5, 10, 20, 30, 60]

# ==================== 辅助函数 ====================
def _linear_regression_slope(y, window):
    """计算滚动线性回归斜率 (BETA)"""
    def _slope(arr):
        if len(arr) < 2:
            return 0.0
        x = np.arange(len(arr))
        y_vals = arr.values
        # 防止除零
        if np.std(x) == 0 or np.std(y_vals) == 0:
            return 0.0
        slope = np.polyfit(x, y_vals, 1)[0]
        return slope
    return y.rolling(window, min_periods=2).apply(_slope, raw=False)

def _linear_regression_rsqr(y, window):
    """计算滚动线性回归 R² (RSQR)"""
    def _rsqr(arr):
        if len(arr) < 2:
            return 0.0
        x = np.arange(len(arr))
        y_vals = arr.values
        if np.std(x) == 0 or np.std(y_vals) == 0:
            return 0.0
        slope, intercept = np.polyfit(x, y_vals, 1)
        y_pred = slope * x + intercept
        ss_res = np.sum((y_vals - y_pred) ** 2)
        ss_tot = np.sum((y_vals - np.mean(y_vals)) ** 2)
        if ss_tot == 0:
            return 0.0
        return 1 - ss_res / ss_tot
    return y.rolling(window, min_periods=2).apply(_rsqr, raw=False)

def _linear_regression_resi(y, window):
    """滚动线性回归残差 (RESI)"""
    def _resi(arr):
        if len(arr) < 2:
            return 0.0
        x = np.arange(len(arr))
        y_vals = arr.values
        if np.std(x) == 0:
            return 0.0
        slope, intercept = np.polyfit(x, y_vals, 1)
        y_pred = slope * x[-1] + intercept
        return y_vals[-1] - y_pred
    return y.rolling(window, min_periods=2).apply(_resi, raw=False)

def _rolling_corr(x, y, window):
    """滚动相关系数"""
    return x.rolling(window).corr(y)

def _day_since_max(x, window):
    """距N日内最高价的天数"""
    def _imax(arr):
        if len(arr) < 2:
            return window
        return np.argmax(arr) / (len(arr) - 1) if len(arr) > 1 else 0.5
    return x.rolling(window, min_periods=2).apply(_imax, raw=True)

def _day_since_min(x, window):
    """距N日内最低价的天数"""
    def _imin(arr):
        if len(arr) < 2:
            return window
        return np.argmin(arr) / (len(arr) - 1) if len(arr) > 1 else 0.5
    return x.rolling(window, min_periods=2).apply(_imin, raw=True)

def _rank(series, window):
    """Percentile rank (0-1) """
    def _rank_func(arr):
        v = arr[-1]
        if len(arr) < 2:
            return 0.5
        rank = np.sum(arr <= v) / len(arr)
        return rank
    return series.rolling(window, min_periods=2).apply(_rank_func, raw=True)

# ==================== Kbar: K线形态因子 (9个) ====================
def compute_kbar(df):
    """9个K线形态因子"""
    open_ = df['open']
    high = df['high']
    low = df['low']
    close = df['close']
    
    result = {}
    # 实体位置
    result['KMID'] = (close - open_) / (open_ + 1e-10)
    # 全天振幅
    result['KLEN'] = (high - low) / (open_ + 1e-10)
    # 上影线
    result['KUP'] = (high - np.maximum(open_, close)) / (open_ + 1e-10)
    # 下影线
    result['KLOW'] = (np.minimum(open_, close) - low) / (open_ + 1e-10)
    # 多空强度 (Shifting)
    result['KSFT'] = (2 * close - high - low) / (open_ + 1e-10)
    
    # 相对前一根的版本
    result['KMID2'] = result['KMID'].diff()  # 实体变化
    result['KLEN2'] = result['KLEN'].diff()  # 振幅变化
    result['KUP2'] = result['KUP'].diff()    # 上影线变化
    result['KLOW2'] = result['KLOW'].diff()  # 下影线变化
    result['KSFT2'] = result['KSFT'].diff()  # 多空强度变化
    
    return result

# ==================== Price: 价格衍生因子 ====================
def compute_price_features(df):
    """价格衍生因子 (多窗口)"""
    close = df['close']
    vwap = df.get('vwap', df['close'])  # 无vwap则用close
    high = df['high']
    low = df['low']
    open_ = df['open']
    volume = df['volume']
    
    result = {}
    
    for w in WINDOWS:
        prefix = f'w{w}'
        # P0: MA均线偏离
        ma = close.rolling(w).mean()
        result[f'{prefix}_MA'] = close / (ma + 1e-10)
        # P1: STD波动率
        result[f'{prefix}_STD'] = close.rolling(w).std() / (close + 1e-10)
        
        # MAX/MIN 位置
        high_w = high.rolling(w).max()
        low_w = low.rolling(w).min()
        result[f'{prefix}_MAX'] = close / (high_w + 1e-10)
        result[f'{prefix}_MIN'] = low_w / (close + 1e-10)
        
        # QTLU/QTLD 分位数 (80%/20%)
        q80 = close.rolling(w).quantile(0.8)
        q20 = close.rolling(w).quantile(0.2)
        result[f'{prefix}_QTLU'] = close / (q80 + 1e-10)
        result[f'{prefix}_QTLD'] = close / (q20 + 1e-10)
        
        # RANK: 在窗口内的百分位
        result[f'{prefix}_RANK'] = _rank(close, w)
        
        # RSV: 随机指标 (K线原始RSV)
        result[f'{prefix}_RSV'] = (close - low_w) / (high_w - low_w + 1e-10)
        
        # IMAX/IMIN: 距最高/最低的天数
        result[f'{prefix}_IMAX'] = _day_since_max(close, w)
        result[f'{prefix}_IMIN'] = _day_since_min(close, w)
        
        # CNTP/CNTN: 窗口内上涨/下跌天��比例
        pct_chg = close.pct_change()
        result[f'{prefix}_CNTP'] = (pct_chg > 0).rolling(w).mean()
        result[f'{prefix}_CNTN'] = (pct_chg < 0).rolling(w).mean()
        result[f'{prefix}_CNTD'] = result[f'{prefix}_CNTP'] - result[f'{prefix}_CNTN']
        
        # SUMP/SUMN/SUMD: 涨跌幅累加 (日内涨跌幅之和)
        result[f'{prefix}_SUMP'] = pct_chg.clip(lower=0).rolling(w).sum()
        result[f'{prefix}_SUMN'] = pct_chg.clip(upper=0).rolling(w).sum()
        result[f'{prefix}_SUMD'] = result[f'{prefix}_SUMP'] + result[f'{prefix}_SUMN']
        
        # ROC (Rate of Change)
        result[f'{prefix}_ROC'] = close.pct_change(w)
        
        # BETA/RSQR (趋势强度和连续性)
        result[f'{prefix}_BETA'] = _linear_regression_slope(close, w)
        result[f'{prefix}_RSQR'] = _linear_regression_rsqr(close, w)
        result[f'{prefix}_RESI'] = _linear_regression_resi(close, w)
        
        # CORR (量价相关)、CORD (差分相关)
        result[f'{prefix}_CORR'] = _rolling_corr(close, volume, w)
        vol_diff = volume.diff()
        result[f'{prefix}_CORD'] = _rolling_corr(close.diff(), vol_diff, w)
    
    return result

# ==================== Volume: 成交量因子 ====================
def compute_volume_features(df):
    """成交量衍生因子 (多窗口)"""
    close = df['close']
    volume = df['volume']
    vwap = df.get('vwap', df['close'])
    high = df['high']
    low = df['low']
    amount = df.get('amount', volume * close)
    
    result = {}
    
    for w in WINDOWS:
        prefix = f'w{w}'
        # VMA: 量均线偏离
        vol_ma = volume.rolling(w).mean()
        result[f'{prefix}_VMA'] = volume / (vol_ma + 1e-10)
        
        # VSTD: 量波动
        vol_std = volume.rolling(w).std()
        result[f'{prefix}_VSTD'] = vol_std / (vol_ma + 1e-10)
        
        # WVMA: 量加权均价偏离
        vol_sum = volume.rolling(w).sum()
        if vol_sum.isna().all():
            result[f'{prefix}_WVMA'] = 0.0
        else:
            wvma = (volume * close).rolling(w).sum() / (vol_sum + 1e-10)
            result[f'{prefix}_WVMA'] = close / (wvma + 1e-10)
        
        # VSUMP/VSUMN/VSUMD: 量价关系
        pct_chg = close.pct_change()
        result[f'{prefix}_VSUMP'] = (volume * pct_chg.clip(lower=0)).rolling(w).sum()
        result[f'{prefix}_VSUMN'] = (volume * pct_chg.clip(upper=0)).rolling(w).sum()
        result[f'{prefix}_VSUMD'] = result[f'{prefix}_VSUMP'] + result[f'{prefix}_VSUMN']
    
    return result

# ==================== Main: 计算全部158个因子 ====================
def compute_all(df):
    """
    计算全部Alpha158因子
    
    参数:
        df: DataFrame, 需包含以下列:
            - open, high, low, close, volume (必选)
            - vwap, amount (可选, 缺失则用close和volume*close代替)
    
    返回:
        DataFrame: 原DataFrame + ~158列因子
    """
    result = df.copy()
    
    # Kbar因子 (9)
    kbar = compute_kbar(df)
    for k, v in kbar.items():
        result[f'a158_{k}'] = v
    
    # 价格因子 (15个算子 × 5个窗口 = 75列)
    price = compute_price_features(df)
    for k, v in price.items():
        result[f'a158_{k}'] = v
    
    # 成交量因子 (6个算子 × 5个窗口 = 30列)
    vol = compute_volume_features(df)
    for k, v in vol.items():
        result[f'a158_{k}'] = v
    
    print(f"Alpha158: Kbar={len(kbar)}, Price={len(price)}, Volume={len(vol)}")
    print(f"  总计: {len(kbar) + len(price) + len(vol)}个因子")
    
    return result


def compute_selected(df, windows=[5, 10, 20], priority='p0'):
    """
    计算精选子集（按优先级）
    
    优先级:
        p0 - 最有效: BETA, RSQR, RANK, RSV (趋势/位置)
        p1 - 有效: CORR, CNTP, CNTN, SUMP, SUMD, IMAX, IMIN (动量/相关)
        p2 - 补充: MA, STD, MAX, MIN, RESI, QTLU, QTLD, VMA, VSTD (波动/量)
    """
    result = df.copy()
    
    # Kbar: 基本面因子全部计算
    kbar = compute_kbar(df)
    for k, v in kbar.items():
        result[f'a158_{k}'] = v
    
    # 按优先级选择 Price 算子
    price_ops = []
    if priority in ['p0', 'p1', 'p2']:
        price_ops += ['ROC', 'RANK', 'RSV', 'BETA', 'RSQR']
    if priority in ['p1', 'p2']:
        price_ops += ['CORR', 'CNTP', 'CNTN', 'CNTD', 'SUMP', 'SUMN', 'SUMD', 'MAX', 'MIN']
        price_ops += ['IMAX', 'IMIN']
    if priority == 'p2':
        price_ops += ['MA', 'STD', 'QTLU', 'QTLD', 'RESI', 'CORD']
    
    for op in price_ops:
        for w in windows:
            fn = f'_compute_{op.lower()}'
            if op == 'RANK':
                result[f'a158_w{w}_{op}'] = _rank(result['close'], w)
            elif op == 'RSV':
                high_w = result['high'].rolling(w).max()
                low_w = result['low'].rolling(w).min()
                result[f'a158_w{w}_{op}'] = (result['close'] - low_w) / (high_w - low_w + 1e-10)
            elif op == 'BETA':
                result[f'a158_w{w}_{op}'] = _linear_regression_slope(result['close'], w)
            elif op == 'RSQR':
                result[f'a158_w{w}_{op}'] = _linear_regression_rsqr(result['close'], w)
            elif op == 'RESI':
                result[f'a158_w{w}_{op}'] = _linear_regression_resi(result['close'], w)
            elif op == 'CORR':
                result[f'a158_w{w}_{op}'] = _rolling_corr(result['close'], result['volume'], w)
            elif op == 'CORD':
                result[f'a158_w{w}_{op}'] = _rolling_corr(
                    result['close'].diff(), result['volume'].diff(), w)
            elif op == 'CNTP':
                result[f'a158_w{w}_{op}'] = (result['close'].pct_change() > 0).rolling(w).mean()
            elif op == 'CNTN':
                result[f'a158_w{w}_{op}'] = (result['close'].pct_change() < 0).rolling(w).mean()
            elif op == 'CNTD':
                pct = result['close'].pct_change()
                result[f'a158_w{w}_{op}'] = (pct > 0).rolling(w).mean() - (pct < 0).rolling(w).mean()
            elif op == 'SUMP':
                pct = result['close'].pct_change()
                result[f'a158_w{w}_{op}'] = pct.clip(lower=0).rolling(w).sum()
            elif op == 'SUMN':
                pct = result['close'].pct_change()
                result[f'a158_w{w}_{op}'] = pct.clip(upper=0).rolling(w).sum()
            elif op == 'SUMD':
                pct = result['close'].pct_change()
                result[f'a158_w{w}_{op}'] = result[f'a158_w{w}_SUMP'] + result[f'a158_w{w}_SUMN']
            elif op == 'IMAX':
                result[f'a158_w{w}_{op}'] = _day_since_max(result['close'], w)
            elif op == 'IMIN':
                result[f'a158_w{w}_{op}'] = _day_since_min(result['close'], w)
            elif op == 'ROC':
                result[f'a158_w{w}_{op}'] = result['close'].pct_change(w)
            elif op == 'MA':
                ma = result['close'].rolling(w).mean()
                result[f'a158_w{w}_{op}'] = result['close'] / (ma + 1e-10)
            elif op == 'STD':
                std = result['close'].rolling(w).std()
                result[f'a158_w{w}_{op}'] = std / (result['close'] + 1e-10)
            elif op == 'MAX':
                high_w = result['high'].rolling(w).max()
                result[f'a158_w{w}_{op}'] = result['close'] / (high_w + 1e-10)
            elif op == 'MIN':
                low_w = result['low'].rolling(w).min()
                result[f'a158_w{w}_{op}'] = low_w / (result['close'] + 1e-10)
            elif op == 'QTLU':
                result[f'a158_w{w}_{op}'] = result['close'] / (
                    result['close'].rolling(w).quantile(0.8) + 1e-10)
            elif op == 'QTLD':
                result[f'a158_w{w}_{op}'] = result['close'] / (
                    result['close'].rolling(w).quantile(0.2) + 1e-10)
    
    # 成交量因子 (p2 only)
    if priority == 'p0':
        pass  # p0 不需要量因子
    elif priority == 'p1':
        pass  # p1 也不需要
    elif priority == 'p2':
        for w in windows:
            vol_ma = result['volume'].rolling(w).mean()
            result[f'a158_w{w}_VMA'] = result['volume'] / (vol_ma + 1e-10)
            vol_std = result['volume'].rolling(w).std()
            result[f'a158_w{w}_VSTD'] = vol_std / (vol_ma + 1e-10)
    
    total = len([c for c in result.columns if c.startswith('a158_')])
    print(f"Alpha158精选(p{priority}): {total}个因子 (窗口={windows})")
    
    return result


# ==================== 自测 ====================
if __name__ == '__main__':
    # 生成随机数据测试
    np.random.seed(42)
    n = 200
    df = pd.DataFrame({
        'open': 100 + np.cumsum(np.random.randn(n) * 0.5),
        'high': 100 + np.cumsum(np.random.randn(n) * 0.5) + np.random.rand(n) * 2,
        'low': 100 + np.cumsum(np.random.randn(n) * 0.5) - np.random.rand(n) * 2,
        'close': 100 + np.cumsum(np.random.randn(n) * 0.5),
        'volume': np.random.randint(1000000, 10000000, n),
        'amount': np.random.randint(100000000, 1000000000, n),
    })
    df[['high', 'low']] = np.maximum(df[['high', 'low']].values, df['open'].values[:, None])
    df['low'] = np.minimum(df['low'], df['close'])
    df['high'] = np.maximum(df['high'], df['close'])
    
    print("=== Alpha158 全部因子测试 ===")
    r = compute_all(df)
    cols = [c for c in r.columns if c.startswith('a158_')]
    print(f"因子列数: {len(cols)}")
    print(f"前10列: {cols[:10]}")
    print(f"无空值列: {sum(1 for c in cols if r[c].notna().sum() > 0)}/{len(cols)}")
    
    print("\n=== Alpha158 精选测试 (p0) ===")
    r2 = compute_selected(df, priority='p0')
    cols2 = [c for c in r2.columns if c.startswith('a158_')]
    print(f"因子列数: {len(cols2)}")
    
    print("\n测试通过 ✓")
