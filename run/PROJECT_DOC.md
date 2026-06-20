# Stock5 项目完整技术文档

## 一、项目概述

Stock5 是一个**双模型量化交易系统**，同时支持两种预测周期：

| 模型 | 预测周期 | 数据源 | 文件 |
|------|----------|--------|------|
| 5分钟模型 | 5分钟后涨跌 | `minute_5_price` 表 | `analyzer_v5_minute.py` |
| 日线模型 | 次日涨跌 | `daily_price` 表 | `analyzer_v5.py` |

---

## 二、目录结构

```
E:\stock5\run\                          ← 项目主目录（2026-06 迁移）
├── ============================================================
│ 核心分析模块
│ ============================================================
├── analyzer_v5.py           # 【日线模型】主分析引擎 (v6内核)
├── analyzer_v5_minute.py    # 【5分钟模型】分析引擎
│
├── ============================================================
│ 回测模块
│ ============================================================
├── backtest_v5.py           # 日线模型回测（逐窗口独立训练）
├── backtest_5minute.py      # 5分钟模型回测
├── backtest_baseline_v5.py  # v5基准线回测 v2
├── daily_prediction_backtest.py  # 逐日回测（防泄露）
├── result_v5.json           # 日线模型最新结果
├── result_v5_minute.json    # 5分钟模型最新结果
├── result_v6.json           # v6结果
│
├── ============================================================
│ 数据采集（守护进程）
│ ============================================================
├── realtime_fetcher.py      # 5分钟数据采集器
├── em_fetcher_daemon.py     # 日线数据采集守护进程
├── market_index_fetcher.py  # 大盘指数采集
│
├── ============================================================
│ 配置与常量
│ ============================================================
├── config.py                # 全局配置（路径、阈值、参数）
├── config.json              # Web服务器配置
├── 波段股票Top30.csv        # 股票池（30只）
│
├── ============================================================
│ 核心库（子目录）
│ ============================================================
├── v6/
│   ├── qlib_alpha158.py    # Alpha158因子计算库
│   ├── bull_bear.py        # LLM多空分析
│   ├── analyzer_v6.py      # v6版分析器（备用）
│   └── fix_kdj.py          # v6 KDJ修复
│
├── llm_factors/
│   ├── factor_fusion.py    # 多因子融合
│   ├── factor_runner.py    # 因子运行器
│   └── qwen_bull_bear.py   # Qwen多空分析
│
├── kline_patterns.py       # K线形态识别（TA-Lib）
│
├── ============================================================
│ 缓存与数据
│ ============================================================
├── model_cache_v5/          # 5分钟模型缓存
├── model_cache_v6/          # 日线模型缓存（run/）
├── v6/model_cache_v6/       # v6模型缓存
├── stocks.db                # SQLite 数据库（266MB）
│
├── ============================================================
│ Web 服务
│ ============================================================
├── web_server.py            # Flask Web服务器 (端口5005)
├── index.html               # 主仪表板
├── stock5_gui_launcher.py   # 桌面GUI启动器
├── stock5_launcher.py       # 命令行启动器
│
├── ============================================================
│ 工具脚本
│ ============================================================
├── check_data_integrity.py  # 数据完整性校验
├── verify_accuracy.py       # 准确率验证
├── verify_predictions.py    # 预测结果验证
├── fix_kdj_and_score.py     # KDJ计算+评分权重修复
├── check_db.py              # 数据库表结构检查
├── check_predictions.py     # 预测结果统计
├── prediction_db.py         # 预测结果数据库管理
├── check_risk_impact.py     # 风控影响快速验证
├── market_detect.py         # 市场状态检测
├── init_src.py              # 初始化脚本（复制到 src/）
│
├── ============================================================
│ Autoresearch（参数优化）
│ ============================================================
├── autoresearch.py          # 信号表现分析
├── autoresearch_benchmark.py    # 兼容的回测（METRIC输出）
├── autoresearch_threshold.py    # 标签阈值优化
├── autoresearch.ps1         # PowerShell 自动研究脚本
│
├── ============================================================
│ 启动与维护
│ ============================================================
├── 脚本.bat                 # 批处理启动（web+采集+GUI）
├── setup_windows_task.ps1   # Windows 任务计划配置
├── temp_sync_files.ps1      # 临时同步脚本
│
├── ============================================================
│ 日志备份
│ ============================================================
├── logs/                    # 运行日志（轮转，保留30天）
├── backup/                  # 文件备份
└── __pycache__/             # Python 缓存
```

---

## 三、数据库结构

### 核心数据表

| 表名 | 用途 | 记录数 | 关键字段 |
|------|------|--------|----------|
| `daily_price` | 日线K线数据 | 30719 | code, date, open, high, low, close, volume, pct_chg |
| `minute_5_price` | 5分钟K线数据 | 29010 | code, datetime, open, high, low, close, volume |
| `index_daily` | 大盘指数 | 11651 | code, date, close, pct_chg, trend |
| `macro_factors` | 宏观因子 | 193 | date, hs300_*, zz500_*, sector_rotation |
| `factor_signals` | LLM/基本面因子 | 570 | code, date, fin_score, llm_confidence |
| `prediction_logs_v5` | 历史预测日志 | 5016 | predict_type, predict_date, stock_code, predict_score |
| `em_fundamentals` | 东方财富基本面 | 360 | code, report_date, pe, pb, roe |
| `em_market_metrics` | 东方财富行情指标 | 360 | code, trade_date, total_mv, circ_mv |
| `em_fetch_log` | 数据采集日志 | 7888 | code, fetch_date, status |
| `daily_predictions` | 逐日回测结果 | 7534 | code, prediction_date, score, actual_up |
| `prediction_results` | 预测结果存储 | 30 | code, score, advice, prediction_date |
| `backtest_history` | 回测历史 | 39 | - |
| `stocks` | 股票池 | 30 | code, name |
| `sqlite_sequence` | 自增ID | 7 | - |

### 数据流向图

```
数据采集层
    realtime_fetcher.py  ──→  minute_5_price (5分钟)
    em_fetcher_daemon.py ──→  daily_price (日线)
    market_index_fetcher.py ──→ index_daily (指数)
    factor_runner.py     ──→  factor_signals (LLM/基本面)
                                    ↓
模型分析层                              stocks.db
    analyzer_v5.py        ←──  读取日线数据
    analyzer_v5_minute.py  ←──  读取5分钟数据
    backtest_v5.py        ←──  读取历史数据
                                    ↓
输出层
    result_v5.json        ←──  日线预测结果
    result_v5_minute.json ←──  5分钟预测结果
    prediction_logs_v5    ←──  历史记录（回测用）
```

---

## 四、核心模块详解

### 4.1 analyzer_v5.py（日线模型）

**用途**：基于Alpha158因子预测次日涨跌

**关键参数**：
```python
ALPHA158_PRIORITY = 'p2'      # p0=25因子, p1=55因子, p2=80因子
ALPHA158_WINDOWS = [5, 10, 20, 30]
RISE_THRESHOLD = 0.01         # 上涨定义：涨幅>=1%
PREDICT_DAYS = 1
```

**预测流程**：
1. `load_macro_factors()` → 加载宏观因子
2. `train_models_v6()` → 训练XGB/LGB/CAT三模型
3. `extract_features_v6()` → 提取基础特征
4. `compute_alpha158()` → 计算Alpha158因子
5. `add_macro_features()` → 添加宏观因子
6. `predict_fusion_v6()` → 三模型融合预测
7. `risk_check()` → 风控评分
8. `final_score = tech_score * risk_mult * 0.9 + llm_factor * 0.1`

### 4.2 analyzer_v5_minute.py（5分钟模型）

**用途**：基于5分钟K线预测5分钟后涨跌
**预测目标**：`pct_chg >= 1%` (5分钟后)
**流程与日线模型类似**，但数据源为 `minute_5_price`

### 4.3 v6/qlib_alpha158.py

Alpha158因子计算库，关键函数：
```python
compute_selected(df, windows=[5,10,20], priority='p0')
# windows: 滚动窗口大小
# priority: 'p0'=25, 'p1'=55, 'p2'=80因���
```

---

## 五、关键配置对照表

| 配置项 | 日线模型 | 5分钟模型 | 说明 |
|--------|----------|-----------|------|
| 数据源 | `daily_price` | `minute_5_price` | 不同表 |
| 预测周期 | 1天 | 5分钟 | |
| 上涨阈值 | 1% | 1% | |
| Alpha158 | p2, [5,10,20,30] | (未使用) | 日线专用 |
| 模型缓存 | `model_cache_v6/` | `model_cache_v5/` | |
| 结果输出 | `result_v5.json` | `result_v5_minute.json` | |
| Web端口 | 5005 | 5005 | 同一服务 |

---

## 六、常见问题

### 路径相关
- **项目迁移到 `E:\stock5\run\` 后**，所有脚本使用 `pathlib.Path(__file__).parent` 相对路径
- 数据库路径：`E:\stock5\run\stocks.db`（266MB，14张表）
- `E:\stock5\stocks.db` 是空的（0B），旧文件已废弃

### 模型训练
- analyzer_v5.py 训练30只股票×3模型，耗时长（>120秒），web_server timeout可能不够
- 模型缓存在 `model_cache_v6/models_v6.pkl` 和 `v6/model_cache_v6/models_v6.pkl`

### 结果更新
- "执行预测"按钮 → `/api/run_predict` → 后台运行 analyzer_v5.py + analyzer_v5_minute.py
- 浏览器可能缓存 JSON 文件，需 `Ctrl+Shift+R` 强制刷新

---

## 七、快速命令参考

```bash
# 日线模型
python analyzer_v5.py           # 运行日线分析
python backtest_v5.py           # 日线回测
python daily_prediction_backtest.py  # 逐日回测

# 5分钟模型  
python analyzer_v5_minute.py    # 运行5分钟分析
python backtest_5minute.py      # 5分钟回测

# 数据采集
python realtime_fetcher.py --daemon  # 5分钟数据采集
python em_fetcher_daemon.py          # 日线数据采集

# 工具
python check_db.py              # 数据库检查
python verify_predictions.py    # 验证预测
python check_data_integrity.py  # 数据完整性
```
