# Graph Report - stock5  (2026-05-31)

## Corpus Check
- 29 files · ~28,669 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 450 nodes · 560 edges · 33 communities (28 shown, 5 thin omitted)
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 32|Community 32]]

## God Nodes (most connected - your core abstractions)
1. `Stock5LauncherGUI` - 22 edges
2. `Stock5 - 5分钟流式数据分析系统` - 16 edges
3. `compute_selected()` - 10 edges
4. `analyze_stocks()` - 9 edges
5. `ModernButton` - 9 edges
6. `get_fusion_score()` - 9 edges
7. `run_once()` - 9 edges
8. `compute_price_features()` - 9 edges
9. `parameters` - 9 edges
10. `meta` - 9 edges

## Surprising Connections (you probably didn't know these)
- `analyze_stocks()` --calls--> `analyze()`  [EXTRACTED]
  analyzer_v5.py → v6/bull_bear.py
- `api_predict()` --calls--> `predict_minute_5()`  [EXTRACTED]
  web_server.py → analyzer_v5_minute.py
- `main()` --calls--> `analyze()`  [EXTRACTED]
  v6/analyzer_v6.py → v6/bull_bear.py

## Communities (33 total, 5 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (26): extract_minute_5_features(), predict_minute_5(), predict_minute_5_single(), 预测单只股票的5分钟走势          Args:         code: 股票代码          Returns:         d, 预测多只股票的5分钟走势          Args:         codes: 股票代码列表          Returns:, 从minute_5_price表提取5分钟周期特征          Args:         code: 股票代码         conn: 数据, run_minute_5_analysis(), save_predictions_to_db() (+18 more)

### Community 1 - "Community 1"
Cohesion: 0.05
Nodes (36): data_collection, frequency_minutes, source, stock_count, stock_pool, trading_hours, database, path (+28 more)

### Community 2 - "Community 2"
Cohesion: 0.13
Nodes (3): main(), ModernButton, Stock5LauncherGUI

### Community 3 - "Community 3"
Cohesion: 0.07
Nodes (26): 1. KDJ计算错误, 1. 提升预测准确率, 2. 优化评分分布, 2. 评分权重错误, 3. 引入时间特征, code:python (rsv = (current_close - lowest) / (highest - lowest) * 100), code:python (# RSV计算正确), code:block3 (涨跌幅权重：±20（最高）) (+18 more)

### Community 4 - "Community 4"
Cohesion: 0.06
Nodes (35): 1. 数据采集（单次）, 1. 简化架构, 2. 技术指标适配, 2. 数据采集（后台连续）, 3. 模型分析（单次）, 3. 流式实时分析, 4. 使用启动脚本, code:block1 (stock5/) (+27 more)

### Community 5 - "Community 5"
Cohesion: 0.13
Nodes (15): code_to_tx(), create_session_with_retries(), fetch_realtime(), FetcherMetrics, Save metrics to a JSON file for external monitoring, Decorator for retrying functions with exponential backoff, Create a requests session with retry strategy, 转腾讯格式: 600183 -> sh600183, 002460 -> sz002460 (+7 more)

### Community 6 - "Community 6"
Cohesion: 0.10
Nodes (19): 1. 正确的5分钟验证结果（30条样本）, 1. 流式数据积累, 2. 评分与收益关系, 2. 预测记录, Stock5 分析模型v5 评估报告, 一、数据概况, 三、根本问题诊断, 二、预测准确率分析 (+11 more)

### Community 7 - "Community 7"
Cohesion: 0.18
Nodes (13): calc_anomaly_score(), calc_llm_insight_score(), get_anomaly_signals(), get_fundamental_signals(), get_fusion_score(), get_tech_score(), 从 daily_features 表获取异动和 LLM 分析数据。, 从数据库获取当天因子信号。          资金流向信号从 fund_flow 表读取（实时采集），     不再依赖 factor_signals 的 (+5 more)

### Community 8 - "Community 8"
Cohesion: 0.11
Nodes (18): model_v5, features_count, models, parameters, target_description, target_threshold, weights, colsample_bytree (+10 more)

### Community 9 - "Community 9"
Cohesion: 0.12
Nodes (13): ANALYZER, ANALYZER_V5, { app, BrowserWindow, ipcMain }, data, DATA_FETCHER, fs, JSON_FILE, JSON_FILE_V5 (+5 more)

### Community 10 - "Community 10"
Cohesion: 0.18
Nodes (17): analyze_news_llm(), calc_fund_score(), call_llm(), collect_fund(), collect_fundamental(), collect_macro(), collect_news(), daemon_loop() (+9 more)

### Community 11 - "Community 11"
Cohesion: 0.18
Nodes (10): iterations, meta, iteration_count, launch_mode, learn_metrics, learn_sets, name, parameters (+2 more)

### Community 12 - "Community 12"
Cohesion: 0.20
Nodes (9): consecutive_failures, failure_count, fetch_count, last_failure_time, last_success_time, success_count, success_rate_percent, total_records_written (+1 more)

### Community 13 - "Community 13"
Cohesion: 0.27
Nodes (8): extract_minute_5_features(), predict_minute_5(), predict_minute_5_single(), 预测单只股票的5分钟走势          Args:         code: 股票代码          Returns:         d, # TODO: 训练专门的5分钟模型, 预测多只股票的5分钟走势          Args:         codes: 股票代码列表          Returns:, 从minute_5_price表提取5分钟周期特征          Args:         code: 股票代码         conn: 数据, run_minute_5_analysis()

### Community 14 - "Community 14"
Cohesion: 0.53
Nodes (9): is_process_running(), main(), read_pid(), show_status(), start_all_services(), start_data_collection(), start_web_server(), stop_all_services() (+1 more)

### Community 15 - "Community 15"
Cohesion: 0.17
Nodes (18): add_macro_features(), calculate_atr(), extract_features_v6(), extract_features_with_alpha158(), load_macro_factors(), main(), predict_fusion_v6(), v6特征提取：基准特征 + Alpha158 (+10 more)

### Community 17 - "Community 17"
Cohesion: 0.39
Nodes (7): backtest_with_new_score(), calculate_kdj_correct(), calculate_score_new(), fix_kdj_in_db(), main(), 正确的KDJ计算（带平滑处理）          Args:         high_prices: 最高价数组（最新在前）         low_pric, 新评分逻辑（基于相关性分析）          相关性分析结果：       - K/D值相关性: 0.41（最高） → 权重±15       - MACD相

### Community 18 - "Community 18"
Cohesion: 0.25
Nodes (7): feature_count, feature_names, feedback_enabled, model_count, stocks, timestamp, version

### Community 19 - "Community 19"
Cohesion: 0.40
Nodes (4): count, predictions, timestamp, version

### Community 25 - "Community 25"
Cohesion: 0.28
Nodes (15): compute_all(), compute_kbar(), compute_price_features(), compute_selected(), compute_volume_features(), _day_since_max(), _day_since_min(), _linear_regression_resi() (+7 more)

### Community 26 - "Community 26"
Cohesion: 0.12
Nodes (15): avg_buy_up_rate, avg_return_buy, avg_return_sell, buy_accuracy, buy_accuracy_rate, config, predict_days, rise_threshold (+7 more)

### Community 27 - "Community 27"
Cohesion: 0.25
Nodes (7): accuracy, buy_accuracy, config, predict_days, rise_threshold, sell_accuracy, total_samples

### Community 30 - "Community 30"
Cohesion: 0.16
Nodes (17): add_macro_features(), analyze_stocks(), calculate_atr(), extract_features_v5(), extract_features_v6(), extract_features_with_alpha158(), load_macro_factors(), main() (+9 more)

## Knowledge Gaps
- **157 isolated node(s):** `predict_days`, `rise_threshold`, `total_samples`, `accuracy`, `buy_accuracy` (+152 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `analyze()` connect `Community 15` to `Community 30`?**
  _High betweenness centrality (0.007) - this node is a cross-community bridge._
- **Why does `model_v5` connect `Community 8` to `Community 1`?**
  _High betweenness centrality (0.007) - this node is a cross-community bridge._
- **What connects `v6特征提取：基准特征 + Alpha158`, `训练：每只票独立模型 + Alpha158因子     Args:         train_end: 训练截止日期 (str 'YYYY-MM-DD')，用`, `多维度风控评分 (乘数0.0~1.0)     fine-r1意见: -2%一刀切太粗，增加板块轮动+个股波动率` to the rest of the system?**
  _209 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.05426356589147287 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.05405405405405406 - nodes in this community are weakly interconnected._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.13333333333333333 - nodes in this community are weakly interconnected._
- **Should `Community 3` be split into smaller, more focused modules?**
  _Cohesion score 0.07407407407407407 - nodes in this community are weakly interconnected._