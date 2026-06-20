# ==================== 市场环境检测 ====================
def detect_market_condition(conn):
    """
    检测当前市场环境，返回 ('conservative' | 'normal')
    """
    try:
        df_idx = pd.read_sql("""
            SELECT date, close FROM index_daily 
            WHERE code='000001.SH' ORDER BY date DESC LIMIT 30
        """, conn)
        
        if len(df_idx) < 20:
            print("  市场检测: 数据不足，默认normal")
            return 'normal'
        
        df_idx = df_idx.iloc[::-1]
        df_idx['pct_chg'] = df_idx['close'].pct_change() * 100
        
        volatility = df_idx['pct_chg'].tail(20).std()
        current_price = df_idx['close'].iloc[-1]
        up_days = (df_idx['pct_chg'].tail(5) > 0).sum()
        sentiment = up_days / 5
        
        print(f"  市场检测: 波动率={volatility:.2f}%, 大盘={current_price:.0f}, 情绪={sentiment*100:.0f}%")
        
        if volatility > 3.5 or current_price > 3400:
            print("  市场检测: 高波动/高位 -> 保守模式")
            return 'conservative'
        elif volatility > 2.5 and sentiment < 0.4:
            print("  市场检测: 中波动+弱情绪 -> 保守模式")
            return 'conservative'
        else:
            print("  市场检测: 正常模式")
            return 'normal'
    except Exception as e:
        print(f"  市场检测异常: {e}, 默认normal")
        return 'normal'


MODEL_PARAMS = {
    'normal': {
        'xgb': {'n_estimators': 200, 'max_depth': 2, 'learning_rate': 0.01},
        'lgb': {'n_estimators': 200, 'max_depth': 2, 'learning_rate': 0.01},
        'cat': {'iterations': 300, 'depth': 3, 'learning_rate': 0.01},
    },
    'conservative': {
        'xgb': {'n_estimators': 300, 'max_depth': 2, 'learning_rate': 0.05},
        'lgb': {'n_estimators': 300, 'max_depth': 2, 'learning_rate': 0.05},
        'cat': {'iterations': 300, 'depth': 3, 'learning_rate': 0.05},
    }
}

BUY_THRESHOLDS = {'normal': 60, 'conservative': 70}
