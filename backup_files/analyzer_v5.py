# -*- coding: utf-8 -*-
"""
analyzer_v5.py — Stock5 分析引擎 (v6 内核)
基于 Alpha158 因子 + 多模型融合 + 多维度风控
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import json, os, pickle, math, warnings, traceback
import pandas as pd
import numpy as np
import sqlite3
from datetime import datetime, timedelta
import xgboost as xgb
import lightgbm as lgb
from catboost import CatBoostClassifier
warnings.filterwarnings('ignore')

# 同级目录引用 qlib_alpha158
import importlib.util
_v6_dir = os.path.dirname(os.path.abspath(__file__))
_qlib_path = os.path.join(_v6_dir, "v6", "qlib_alpha158.py")
spec = importlib.util.spec_from_file_location("qlib_alpha158", _qlib_path)
qlib_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qlib_mod)
compute_alpha158 = qlib_mod.compute_selected

DB_PATH = r'E:\stock5\stocks.db'
CSV_PATH = r'E:\stock5\波段股票Top30.csv'
OUTPUT_JSON = r'E:\stock5\result_v5.json'
MODEL_CACHE_DIR = r'E:\stock5\model_cache_v6'

RISE_THRESHOLD = 0.01
PREDICT_DAYS = 1

# 特征配置
ALPHA158_PRIORITY = 'p2'  # p0=25个 p1=55个 p2=80个
ALPHA158_WINDOWS = [5, 10, 20, 30]

# 基准特征 (v5剪枝后保留的13个高MI特征中我们保留核心的)
BASE_FEATURES = [
    'atr_20', 'high_low_ratio', 'ma10_ratio', 'ma20_ratio',
    'macd', 'rsi6', 'atr_5', 'position_60', 'boll_ratio',
    'volume_ratio', 'pct_chg', 'k', 'd',
]

# 宏观因子
MACRO_FEATURES = [
    'index_rs', 'hs300_trend_val', 'zz500_trend_val',
    'hs300_ma_position', 'zz500_ma_position', 'sector_rotation',
    'fundamental_score', 'llm_confidence',
]

STOCK_NAMES = {
    '605196.SH': '华通线缆', '688028.SH': '沃尔德', '688195.SH': '腾景科技',
    '688233.SH': '神工股份', '688519.SH': '南亚新材', '002353.SZ': '杰瑞股份',
    '002384.SZ': '东山精密', '600183.SH': '生益科技', '603876.SH': '鼎胜新材',
    '603986.SH': '兆易创新', '688416.SH': '恒烁股份', '688521.SH': '芯原股份',
    '688676.SH': '金盘科技', '300136.SZ': '信维通信', '603225.SH': '新凤鸣',
    '688308.SH': '欧科亿', '688388.SH': '嘉元科技', '688556.SH': '高测股份',
    '600118.SH': '中国卫星', '601231.SH': '环旭电子', '688658.SH': '悦康药业',
    '688668.SH': '鼎通科技', '688788.SH': '科思股份', '002202.SZ': '金风科技',
    '002916.SZ': '深南电路', '300604.SZ': '长川科技', '603228.SH': '景旺电子',
    '688698.SH': '伟创电气', '002460.SZ': '赣锋锂业', '300476.SZ': '胜宏科技',
}

# ==================== 特征提取 ====================

# ==================== 市场环境检测 ====================
def detect_market_condition(conn):
    try:
        df_idx = pd.read_sql("SELECT date, close FROM index_daily WHERE code='000300.SH' ORDER BY date DESC LIMIT 30", conn)
        if len(df_idx) < 20:
            return 'normal'
        df_idx = df_idx.iloc[::-1]
        df_idx['pct_chg'] = df_idx['close'].pct_change() * 100
        volatility = df_idx['pct_chg'].tail(20).std()
        current_price = df_idx['close'].iloc[-1]
        up_days = (df_idx['pct_chg'].tail(5) > 0).sum()
        sentiment = up_days / 5
        print("  市场检测: 波动率={:.2f}%, 大盘={:.0f}, 情绪={:.0f}%".format(volatility, current_price, sentiment*100))
        if volatility > 3.5 or current_price > 5200:
            print("  -> 保守模式")
            return 'conservative'
        elif volatility > 1.5 and sentiment < 0.4:
            print("  -> 保守模式")
            return 'conservative'
        else:
            print("  -> 正常模式")
            return 'normal'
    except Exception as e:
        print("  市场检测异常: {}".format(e))
        return 'normal'

MODEL_PARAMS = {
    'normal': {'xgb': {'n_estimators': 180, 'max_depth': 2, 'learning_rate': 0.008}, 'lgb': {'n_estimators': 180, 'max_depth': 2, 'learning_rate': 0.008}, 'cat': {'iterations': 250, 'depth': 3, 'learning_rate': 0.008}},
    'conservative': {'xgb': {'n_estimators': 250, 'max_depth': 2, 'learning_rate': 0.03}, 'lgb': {'n_estimators': 250, 'max_depth': 2, 'learning_rate': 0.03}, 'cat': {'iterations': 280, 'depth': 3, 'learning_rate': 0.03}}
}
# 买入阈值
BUY_THRESHOLDS = {'normal': 54, 'conservative': 65}

def calculate_atr(df, i, window):
    tr_list = []
    for j in range(i - window + 1, i + 1):
        if j > 0:
            high = df['high'].iloc[j]
            low = df['low'].iloc[j]
            pc = df['close'].iloc[j - 1]
            tr = max(high - low, abs(high - pc), abs(low - pc))
            tr_list.append(tr)
    return np.mean(tr_list) if tr_list else 0

def extract_features_v6(df_reversed, i):
    """v6特征提取：基准特征 + Alpha158"""
    if i < 0 or i >= len(df_reversed):
        return None
    
    row = df_reversed.iloc[i]
    close = row['close']
    high = row['high']
    low = row['low']
    volume = row['volume']
    code = row['code']
    
    # ---- 基准特征 ----
    feat = {
        'pct_chg': float(row['pct_chg']),
        'ma5_ratio': float(close / row['ma5']) if row['ma5'] > 0 else 1.0,
        'ma10_ratio': float(close / row['ma10']) if row['ma10'] > 0 else 1.0,
        'rsi6': float(row['rsi6']) if pd.notna(row['rsi6']) else 50,
        'macd': float(row['macd']) if pd.notna(row['macd']) else 0,
        'ma20_ratio': float(close / row['ma20']) if pd.notna(row['ma20']) and row['ma20'] > 0 else 1.0,
        'k': float(row['k']) if pd.notna(row['k']) else 50,
        'd': float(row['d']) if pd.notna(row['d']) else 50,
        'boll_ratio': float(close / row['boll_upper']) if pd.notna(row['boll_upper']) and row['boll_upper'] > 0 else 1.0,
        'bias10': float(row['bias10']) if pd.notna(row['bias10']) else 0,
        'amplitude': float(row['amplitude']) if pd.notna(row['amplitude']) else 0,
    }
    
    # ATR
    if i >= 5:
        feat['atr_5'] = calculate_atr(df_reversed, i, 5)
    else:
        feat['atr_5'] = 0
    if i >= 20:
        feat['atr_20'] = calculate_atr(df_reversed, i, 20)
        feat['volatility_ratio'] = feat['atr_5'] / feat['atr_20'] if feat['atr_20'] > 0 else 1.0
    else:
        feat['atr_20'] = 0
        feat['volatility_ratio'] = 1
    
    # 量比
    if i >= 5:
        vol_ma5 = df_reversed['volume'].iloc[i - 5:i].mean()
        feat['volume_ratio'] = volume / vol_ma5 if vol_ma5 > 0 else 1.0
    else:
        feat['volume_ratio'] = 1.0
    
    # 高位低位位置
    if i >= 20:
        low_20 = df_reversed['low'].iloc[i - 20:i].min()
        high_20 = df_reversed['high'].iloc[i - 20:i].max()
        feat['position_20'] = (close - low_20) / (high_20 - low_20 + 0.01)
    else:
        feat['position_20'] = 0.5
    if i >= 60:
        low_60 = df_reversed['low'].iloc[i - 60:i].min()
        high_60 = df_reversed['high'].iloc[i - 60:i].max()
        feat['position_60'] = (close - low_60) / (high_60 - low_60 + 0.01)
    else:
        feat['position_60'] = 0.5
    
    feat['high_low_ratio'] = high / low if low > 0 else 1.0
    
    # 时间特征
    try:
        date_val = pd.to_datetime(row['date'])
        feat['day_of_week'] = date_val.dayofweek
        feat['month'] = date_val.month
    except:
        feat['day_of_week'] = 2
        feat['month'] = 4
    
    # 动量
    if i >= 3:
        feat['pct_chg_3d'] = (close - df_reversed['close'].iloc[i - 3]) / df_reversed['close'].iloc[i - 3] * 100
    else:
        feat['pct_chg_3d'] = 0
    if i >= 5:
        feat['pct_chg_5d'] = (close - df_reversed['close'].iloc[i - 5]) / df_reversed['close'].iloc[i - 5] * 100
    else:
        feat['pct_chg_5d'] = 0
    feat['momentum'] = feat['pct_chg'] + feat['pct_chg_3d'] + feat['pct_chg_5d']
    
    # ---- K线形态特征 (v6.2新增) ----
    # 需要至少20根K线数据才能稳定识别形态
    if i >= 20:
        try:
            from kline_patterns import add_kline_pattern_features
            # 取最近20根K线的OHLC数据 (最新在前)
            lookback = min(i + 1, 30)  # 最多取30根
            open_prices = df_reversed['open'].iloc[i - lookback + 1:i + 1].tolist()
            high_prices = df_reversed['high'].iloc[i - lookback + 1:i + 1].tolist()
            low_prices = df_reversed['low'].iloc[i - lookback + 1:i + 1].tolist()
            close_prices = df_reversed['close'].iloc[i - lookback + 1:i + 1].tolist()
            feat = add_kline_pattern_features(feat, open_prices, high_prices, low_prices, close_prices)
        except Exception:
            # 形态识别失败时补0
            for name in ['cdl_hammer', 'cdl_hanging_man', 'cdl_engulfing',
                         'cdl_morning_star', 'cdl_evening_star', 'cdl_doji',
                         'cdl_shooting_star', 'cdl_inverted_hammer', 'cdl_piercing',
                         'cdl_dark_cloud_cover', 'cdl_3_white_soldiers', 'cdl_3_black_crows',
                         'cdl_rising_3_methods', 'cdl_long_legged_doji', 'cdl_marubozu']:
                feat[name] = 0
            feat['cdl_buy_strength'] = 0
            feat['cdl_sell_strength'] = 0
            feat['cdl_net_signal'] = 0
            feat['cdl_strong_reversal'] = 0
            feat['cdl_doji_present'] = 0
    else:
        # 数据不足时补0
        for name in ['cdl_hammer', 'cdl_hanging_man', 'cdl_engulfing',
                     'cdl_morning_star', 'cdl_evening_star', 'cdl_doji',
                     'cdl_shooting_star', 'cdl_inverted_hammer', 'cdl_piercing',
                     'cdl_dark_cloud_cover', 'cdl_3_white_soldiers', 'cdl_3_black_crows',
                     'cdl_rising_3_methods', 'cdl_long_legged_doji', 'cdl_marubozu']:
            feat[name] = 0
        feat['cdl_buy_strength'] = 0
        feat['cdl_sell_strength'] = 0
        feat['cdl_net_signal'] = 0
        feat['cdl_strong_reversal'] = 0
        feat['cdl_doji_present'] = 0
    
    # ---- Stock7 因子特征 (v7新增) ----
    # 基于反向因子分析发现的有效因子
    try:
        # 取最近60条正序数据（stock7需要正序）
        lookback = min(i + 1, 60)
        df_subset = df_reversed.iloc[i - lookback + 1:i + 1].iloc[::-1].reset_index(drop=True)
        from stock7_trend_predictor import get_stock7_features, get_stock7_risk_multiplier
        stock7_feat = get_stock7_features(df_subset)
        stock7_feat['stock7_risk_mult'] = get_stock7_risk_multiplier(df_subset)
        feat.update(stock7_feat)
    except Exception:
        # Stock7 特征不可用时补默认值
        feat['stock7_score'] = 0.5
        feat['stock7_risk_mult'] = 1.0
        for name in ['amplitude', 'boll_ratio', 'kdj_momentum', 'rsi_momentum',
                     'macd_momentum', 'volume_momentum', 'amount_momentum', 'trend_position']:
            feat[f'stock7_{name}'] = 0.5
            feat[f'stock7_{name}_bullish'] = 0.0
            feat[f'stock7_{name}_bearish'] = 0.0
    
    return feat

def extract_features_with_alpha158(df_reversed, i, alpha158_row):
    """提取基础特征 + Alpha158因子"""
    feat = extract_features_v6(df_reversed, i)
    if feat is None:
        return None
    
    # 添加Alpha158因子
    if alpha158_row is not None:
        for col in alpha158_row.index:
            if col.startswith('a158_'):
                val = alpha158_row[col]
                feat[col] = float(val) if pd.notna(val) else 0.0
    
    return feat


# ==================== 宏观因子 ====================
def load_macro_factors(conn, date_limit=None):
    """加载大盘/板块/基本面因子"""
    date_filter = f" AND date <= '{date_limit}'" if date_limit else ""
    try:
        idx = pd.read_sql(f"""
            SELECT * FROM index_daily 
            WHERE code IN ('sh.000300','sh.000905','000300.SH','000905.SH') {date_filter}
            ORDER BY date
        """, conn)
        macro = None
        if not idx.empty:
            idx['date'] = pd.to_datetime(idx['date']).dt.strftime('%Y-%m-%d')
            
            def build_series(idx_df, sh_code, code_sh, prefix):
                sh = idx_df[idx_df['code'] == sh_code][['date','close','pct_chg','ma20','ma5']].copy()
                sh.columns = ['date', f'{prefix}_close', f'{prefix}_pct', f'{prefix}_ma20', f'{prefix}_ma5']
                extra = idx_df[idx_df['code'] == code_sh][['date','close']].copy()
                extra = extra[~extra['date'].isin(sh['date'])]
                if not extra.empty:
                    extra = extra.sort_values('date')
                    last_sh = sh.sort_values('date').iloc[-1] if len(sh) > 0 else None
                    prev = last_sh[f'{prefix}_close'] if last_sh is not None else extra.iloc[0]['close']
                    pcts = []
                    for _, r in extra.iterrows():
                        pct = (r['close'] - prev) / prev * 100 if prev > 0 else 0
                        pcts.append(pct)
                        prev = r['close']
                    extra['pct_chg'] = pcts
                    extra[f'{prefix}_ma20'] = extra['close'] / 1.0
                    extra[f'{prefix}_ma5'] = extra['close'] / 1.0
                    extra.columns = ['date', f'{prefix}_close', f'{prefix}_pct', f'{prefix}_ma20', f'{prefix}_ma5']
                    combined = pd.concat([sh, extra]).sort_values('date').drop_duplicates('date')
                else:
                    combined = sh
                return combined
            
            hs300 = build_series(idx, 'sh.000300', '000300.SH', 'hs300')
            zz500 = build_series(idx, 'sh.000905', '000905.SH', 'zz500')
            macro = hs300.merge(zz500, on='date', how='left').set_index('date')
            macro['zz500_close'] = macro['zz500_close'].fillna(macro['hs300_close'])
            macro['zz500_pct'] = macro['zz500_pct'].fillna(0)
            print(f"  大盘因子: {len(macro)}条")
    except:
        macro = None
    
    # macro_factors 补充
    try:
        mf = pd.read_sql("SELECT * FROM macro_factors", conn)
        if not mf.empty and macro is not None:
            mf['date'] = pd.to_datetime(mf['date']).dt.strftime('%Y-%m-%d')
            mf = mf.sort_values('date').drop_duplicates('date', keep='last').set_index('date')
            for dt in mf.index:
                if dt not in macro.index and any(pd.notna(mf.loc[dt].get(c)) for c in mf.columns if c in ['hs300_close','hs300_pct']):
                    macro.loc[dt] = {c: mf.loc[dt].get(c, 0) for c in macro.columns}
            macro = macro.sort_index()
    except:
        pass
    
    if macro is not None and 'sector_rotation' not in macro.columns:
        macro['sector_rotation'] = 0.0
    
    # 基本面
    fund = None
    try:
        fund = pd.read_sql(f"SELECT * FROM factor_signals{date_filter.replace('AND date','WHERE date') if date_limit else ''}", conn)
        if not fund.empty:
            fund['date'] = pd.to_datetime(fund['date']).dt.strftime('%Y-%m-%d')
            print(f"  基本面因子: {len(fund)}条{'(限制至'+date_limit+')' if date_limit else ''}")
    except:
        pass
    
    return macro, fund


def add_macro_features(feat, row_date, code, macro, fund):
    """添加宏观因子"""
    if macro is not None and row_date in macro.index:
        m = macro.loc[row_date]
        if isinstance(m, pd.DataFrame):
            m = m.iloc[0]
        feat['index_rs'] = feat.get('pct_chg', 0) - m.get('zz500_pct', 0)
        trend_map = {'up': 1.0, 'sideways': 0.0, 'down': -1.0}
        feat['hs300_trend_val'] = trend_map.get(m.get('hs300_trend', ''), 0.0)
        feat['zz500_trend_val'] = trend_map.get(m.get('zz500_trend', ''), 0.0)
        feat['hs300_ma_position'] = m['hs300_close'] / m['hs300_ma20'] if m.get('hs300_ma20', 0) > 0 else 1.0
        feat['zz500_ma_position'] = m['zz500_close'] / m['zz500_ma20'] if m.get('zz500_ma20', 0) > 0 else 1.0
        feat['sector_rotation'] = float(m.get('sector_rotation', 0)) if pd.notna(m.get('sector_rotation', 0)) else 0.0
    else:
        for k in ['index_rs', 'hs300_trend_val', 'zz500_trend_val', 'sector_rotation']:
            feat[k] = 0.0
        feat['hs300_ma_position'] = 1.0
        feat['zz500_ma_position'] = 1.0
    
    if fund is not None:
        frow = fund[(fund['code'] == code) & (fund['date'] == row_date)]
        if not frow.empty:
            feat['fundamental_score'] = float(frow['fin_score'].iloc[0])
            feat['llm_confidence'] = float(frow['llm_confidence'].iloc[0])
        else:
            feat['fundamental_score'] = 50.0
            feat['llm_confidence'] = 0.0
    else:
        feat['fundamental_score'] = 50.0
        feat['llm_confidence'] = 0.0
    
    return feat


# ==================== 训练 ====================
def train_models_v6(stock_pool, conn, train_end=None):
    """训练：每只票独立模型 + Alpha158因子
    Args:
        train_end: 训练截止日期 (str 'YYYY-MM-DD')，用于回测防止数据泄露
    """
    market_mode = detect_market_condition(conn)
    params = MODEL_PARAMS[market_mode]
    print(f"\n训练v6模型 (每只票独立)...{' 训练截止: ' + train_end if train_end else ''}")
    macro, fund = load_macro_factors(conn, date_limit=train_end if train_end else None)
    
    models = {'xgb': {}, 'lgb': {}, 'cat': {}}
    
    date_filter = f" AND date <= '{train_end}'" if train_end else ""
    
    for code in stock_pool:
        try:
            df = pd.read_sql(f"SELECT * FROM daily_price WHERE code='{code}'{date_filter} ORDER BY date", conn)
            if len(df) < 100:
                continue
            
            # 计算Alpha158因子 (一次性)
            df_alpha = compute_alpha158(df, windows=ALPHA158_WINDOWS, priority=ALPHA158_PRIORITY)
            
            # 构建特征标签
            features = []
            df_rev = df.iloc[::-1].reset_index(drop=True)
            df_alpha_rev = df_alpha.iloc[::-1].reset_index(drop=True)
            
            for i in range(60, len(df) - PREDICT_DAYS):
                alpha_row = df_alpha_rev.iloc[len(df) - 1 - i] if len(df_alpha_rev) > 0 else None
                feat = extract_features_with_alpha158(df_rev, len(df) - i - 1, alpha_row)
                if not feat:
                    continue
                
                close_today = df.iloc[i]['close']
                close_fut = df.iloc[i + PREDICT_DAYS]['close']
                rise = (close_fut - close_today) / close_today if close_today > 0 else 0
                feat['target'] = 1 if rise >= RISE_THRESHOLD else 0
                
                try:
                    row_date = str(df.iloc[i]['date'])
                    feat = add_macro_features(feat, row_date, code, macro, fund)
                except:
                    for k in MACRO_FEATURES:
                        feat[k] = 0.0 if k not in ['fundamental_score'] else 50.0
                
                features.append(feat)
            
            if len(features) < 30:
                continue
            
            ds = pd.DataFrame(features)
            n = len(ds)
            split_idx = int(n * 0.8)
            
            train_ds = ds.iloc[:split_idx]
            val_ds = ds.iloc[split_idx:]
            
            # 自动特征选择：去除target和空值列
            drop_cols = ['target']
            feature_cols = [c for c in ds.columns if c not in drop_cols]
            
            X_train = train_ds[feature_cols].fillna(0)
            y_train = train_ds['target']
            X_val = val_ds[feature_cols].fillna(0)
            y_val = val_ds['target']
            
            # XGBoost (v6.1: 加大正则防过拟合，收紧早停) - GPU加速
            xgb_model = xgb.XGBClassifier(
                n_estimators= params['xgb']['n_estimators'], max_depth=params['xgb']['max_depth'], random_state=42,
                learning_rate= params['xgb']['learning_rate'], min_child_weight=8, subsample=0.6,
                colsample_bytree=0.5, reg_alpha= 0.1, reg_lambda= 1.0,
                early_stopping_rounds=15, eval_metric='logloss',
                verbosity=0,
                tree_method='hist', device='cuda',  # GPU加速
            )
            xgb_model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
            models['xgb'][code] = xgb_model
            
            # LightGBM (v6.1: 更大正则) - GPU加速
            lgb_model = lgb.LGBMClassifier(
                n_estimators= params['xgb']['n_estimators'], max_depth=params['xgb']['max_depth'], random_state=42,
                learning_rate= params['xgb']['learning_rate'], min_child_weight=8, subsample=0.6,
                colsample_bytree=0.5, reg_alpha= 0.1, reg_lambda= 1.0,
                min_split_gain=0.1,
                device='gpu', gpu_use_dp=True,  # GPU加速
                verbose=-1,
            )
            lgb_model.fit(X_train, y_train, eval_set=[(X_val, y_val)],
                          callbacks=[lgb.early_stopping(15), lgb.log_evaluation(0)])
            models['lgb'][code] = lgb_model
            
            # CatBoost (v6.1: 更大正则) - GPU加速
            cat_model = CatBoostClassifier(
                iterations= params['cat']['iterations'], depth=params['cat']['depth'], random_state=42,
                learning_rate= params['cat']['learning_rate'], min_child_samples=8,
                l2_leaf_reg= 3.0, early_stopping_rounds=15,
                bootstrap_type='MVS', subsample=0.6,  # GPU兼容的bootstrap
                task_type='GPU', devices='0',  # GPU加速
                verbose=False,
            )
            cat_model.fit(X_train, y_train, eval_set=(X_val, y_val), verbose=False)
            models['cat'][code] = cat_model
            
            print(f"  {code} ✓ (特征:{len(feature_cols)})")
            
        except Exception as e:
            print(f"  {code}: ✗ {e}")
            continue
    
    print(f"训练完成: XGB {len(models['xgb'])}, LGB {len(models['lgb'])}, CAT {len(models['cat'])}")
    return models


def predict_fusion_v6(models, code, feat):
    """三模型融合预测，缺失特征自动补0"""
    try:
        if code in models['xgb']:
            train_feats = models['xgb'][code].get_booster().feature_names
        else:
            train_feats = list(feat.keys())
        
        # 构建特征向量，缺失特征补0
        feat_arr = np.array([[feat.get(k, 0.0) for k in train_feats]])
        
        xgb_p = models['xgb'][code].predict_proba(feat_arr)[0][1] if code in models['xgb'] else 0.5
        lgb_p = models['lgb'][code].predict_proba(feat_arr)[0][1] if code in models['lgb'] else 0.5
        cat_p = models['cat'][code].predict_proba(feat_arr)[0][1] if code in models['cat'] else 0.5
        
        score = xgb_p * 0.5 + lgb_p * 0.3 + cat_p * 0.2
        # 返回真实概率（0-100分）
        return int(np.clip(score * 100, 0, 100))
    except Exception as e:
        print(f"    predict error: {e}")
        return 50


# ==================== 风控引擎 ====================
def risk_check(feat, macro=None, row_date=None):
    """
    多维度风控评分 (乘数0.0~1.0)
    fine-r1意见: -2%一刀切太粗，增加板块轮动+个股波动率
    """
    risk = 1.0
    
    # 1. 大盘风控 (权重0.4) - 放宽阈值
    hs300_trend = feat.get('hs300_trend_val', 0)
    zz500_trend = feat.get('zz500_trend_val', 0)
    index_rs = feat.get('index_rs', 0)
    
    if hs300_trend < -1.0:  # 大盘向下 (从-0.5放宽到-1.0)
        risk *= 0.7
    elif hs300_trend < 0:   # 大盘偏弱
        risk *= 0.9
    
    if index_rs < -5:       # 个股大幅跑输大盘 (从-3放宽到-5)
        risk *= 0.8
    
    # 2. 板块轮动 (权重0.3) - 放宽阈值
    sector = feat.get('sector_rotation', 0)
    if sector < -0.5:
        risk *= 0.85
    elif sector < -0.2:
        risk *= 0.95
    
    # 3. 个股波动率风控 (权重0.3) - 放���阈值
    volatility = feat.get('volatility_ratio', 1.0)
    if volatility > 2.5:    # 波动异常放大 (从2.0放宽到2.5)
        risk *= 0.8
    elif volatility > 1.8:
        risk *= 0.95
    
    # 4. Stock7 因子风控 (v7新增)
    stock7_risk = feat.get('stock7_risk_mult', 1.0)
    risk *= stock7_risk
    
    return risk


# ==================== 分析预测函数 ====================
def analyze_stocks(models, conn, pool):
    """分析股票池，返回结果列表。后续升级只改此函数即可"""
    macro_analysis, fund_analysis = load_macro_factors(conn)
    results = []
    for code in pool:
        if code not in models['xgb']:
            continue
        try:
            df = pd.read_sql(f"SELECT * FROM daily_price WHERE code='{code}' ORDER BY date DESC LIMIT 60", conn)
            df_alpha = compute_alpha158(df.iloc[::-1], windows=ALPHA158_WINDOWS, priority=ALPHA158_PRIORITY)
            
            feat = extract_features_with_alpha158(
                df.iloc[::-1], len(df) - 1,
                df_alpha.iloc[-1] if len(df_alpha) > 0 else None
            )
            if not feat:
                continue
            
            latest = df.iloc[0]
            prev = df.iloc[1] if len(df) > 1 else None
            name = STOCK_NAMES.get(code, code)
            
            close_val = float(latest['close'])
            pct_val = float(latest['pct_chg']) if pd.notna(latest.get('pct_chg')) else 0
            if pct_val == 0 and prev is not None and prev['close'] > 0:
                pct_val = round((close_val - float(prev['close'])) / float(prev['close']) * 100, 2)
            
            latest_date = str(latest['date'])
            feat = add_macro_features(feat, latest_date, code, macro_analysis, fund_analysis)
            
            # 技术评分
            tech_score = predict_fusion_v6(models, code, feat)
            
            # 风控乘数
            risk_mult = risk_check(feat)
            
            # Bull/Bear LLM 因子 (可选)
            try:
                from v6.bull_bear import analyze as bull_bear_analyze
                indicators_str = f"收盘{close_val:.2f}, 涨幅{pct_val}%, RSI={feat.get('rsi6',50):.0f}"
                bb = bull_bear_analyze(code, name, indicators_str, "", "normal")
                if bb['success']:
                    llm_net = bb['bull']['score'] - bb['bear']['score']
                    llm_conf = bb['confidence']
                else:
                    llm_net, llm_conf = 0, 0
            except Exception:
                llm_net, llm_conf = 0, 0
            
            llm_factor = (llm_net + 100) / 200 * 100
            final_score = int(tech_score * risk_mult * 0.9 + llm_factor * 0.1)
            
            results.append({
                'code': code,
                'name': name,
                'score': final_score,
                'tech_score': tech_score,
                'risk_mult': round(risk_mult, 2),
                'close': round(close_val, 2),
                'pct_chg': pct_val,
                'date': str(latest['date']),
                'advice': '买入' if final_score >= 58 else ('卖出' if final_score < 35 else '持有'),
                'buy_signal': final_score >= 58,
                'sell_signal': final_score < 35,
                'volume': float(latest['volume']) if pd.notna(latest.get('volume')) else 0,
                'feature_count': len(feat),
                'alpha158_count': sum(1 for k in feat if k.startswith('a158_')),
            })
        except Exception as e:
            print(f"  {code}: ✗ {e}")
            continue
    return results

def main():
    conn = sqlite3.connect(DB_PATH)
    pool = pd.read_csv(CSV_PATH, encoding='utf-8-sig')['股票代码'].tolist()
    print(f"股票池: {len(pool)}只")
    
    # 训练模型
    models = train_models_v6(pool, conn)
    
    # 缓存
    os.makedirs(MODEL_CACHE_DIR, exist_ok=True)
    with open(os.path.join(MODEL_CACHE_DIR, 'models_v6.pkl'), 'wb') as f:
        pickle.dump(models, f)
    print(f"模型缓存已保存 ✅")
    
    # 分析
    print("\n分析股票池...")
    results = analyze_stocks(models, conn, pool)
    conn.close()
    
    # 输出
    result = {
        'version': 'v5.6',
        'timestamp': datetime.now().isoformat(),
        'model': f'Alpha158({ALPHA158_PRIORITY}, w={ALPHA158_WINDOWS})',
        'baseline_features': BASE_FEATURES,
        'macro_features': MACRO_FEATURES,
        'stocks': sorted(results, key=lambda x: x['score'], reverse=True),
    }
    
    def _clean(v):
        if isinstance(v, dict):  return {k: _clean(v) for k, v in v.items()}
        if isinstance(v, list):  return [_clean(x) for x in v]
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)): return None
        return v
    
    result = _clean(result)
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print(f"v5.6 分析完成: {len(results)}只股票")
    print(f"结果: {OUTPUT_JSON}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
