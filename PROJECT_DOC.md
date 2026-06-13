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
E:\stock5\
├── ============================================================
│ 核心分析模块
│ ============================================================
├── analyzer_v5.py           # 【日线模型】主分析引擎 (v6内核)
├── analyzer_v5_minute.py    # 【5分钟模型】分析引擎
│
├── ============================================================
│ 回测模块
│ ============================================================
├── backtest_v5.py           # 日线模型回测
├── backtest_5minute.py      # 5分钟模型回测
├── backtest_result_v6.json  # 回测结果（历史模拟）
├── result_v5.json           # 5分钟模型最新结果
├── result_v5_minute.json    # 5分钟模型最���结果
├── result_v6.json           # 日线模型最新结果
│
├── ============================================================
│ 数据采集
│ ============================================================
├── realtime_fetcher.py      # 5分钟数据采集器
├── em_fetcher_daemon.py     # 每日数据采集守护进程
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
│ 核心库
│ ============================================================
├── v6/
│   ├── qlib_alpha158.py    # Alpha158因子计算库
│   ├── bull_bear.py        # LLM多空分��
│   └── analyzer_v6.py      # v6版分析器（备用）
│
├── llm_factors/
│   ├── factor_fusion.py    # 多因子融合
│   ├── factor_runner.py    # 因子运行器
│   └── qwen_bull_bear.py   # Qwen多空分析
│
├── kline_patterns.py       # K线形态识别（TA-Lib）
│
├── ============================================================
│ 缓存与输出
│ ============================================================
├── model_cache_v5/          # 5分钟模型缓存
├── model_cache_v6/          # 日线模型缓存
├── stocks.db                # SQLite数据库
│
├── ============================================================
│ 工具脚本
│ ============================================================
├── check_data_integrity.py  # 数据完整性校验
├── verify_accuracy.py       # 准确率验证
├── fix_kdj_and_score.py     # 修复KDJ和分数
├── run_analysis.py          # 运行分析入口
└── 脚本.bat                  # 批处理启动脚本
```

---

## 三、数据库结构

### 核心数据表

| 表名 | 用途 | 关键字段 |
|------|------|----------|
| `daily_price` | 日线K线数据 | code, date, open, high, low, close, volume, pct_chg, ma5/10/20, rsi6, macd, k, d, boll_* |
| `minute_5_price` | 5分钟K线数据 | code, datetime, open, high, low, close, volume, pct_chg, ma5/10/20, rsi6, macd, k, d, boll_* |
| `index_daily` | 大盘指数 | code(sh.000300等), date, close, pct_chg, ma5/10/20, trend |
| `macro_factors` | 宏观因子 | date, hs300_*, zz500_*, sector_rotation |
| `factor_signals` | LLM/基本面因子 | code, date, fin_score, llm_confidence |
| `prediction_logs_v5` | 历史预测日志 | predict_type, predict_date, stock_code, predict_score, actual_result |

### 表关系图

```
┌─────────────────────────────────────────────────────────────────┐
│                        数据流向图                                │
└─────────────────────────────────────────────────────────────────┘

数据源 (每日采集)
     ↓
┌──────────────────────────────────────────────────────────────┐
│                      stocks.db                                │
├─────────────────────────────────────────────────────────────���┤
│  minute_5_price  ←─ realtime_fetcher.py (5分钟采集)           │
│  daily_price     ←─ em_fetcher_daemon.py (日线采集)           │
│  index_daily     ←─ market_index_fetcher.py                   │
│  macro_factors   ←─ 计算生成                                   │
│  factor_signals  ←─ LLM分析结果                               │
│  prediction_logs_v5 ←─ 模型预测时写入                         │
└──────────────────────────────────────────────────────────────┘
     ↓
┌──────────────────────────────────────────────────────────────┐
│                    模型预测                                    │
├───────────────────────────────────────────���──────────────────┤
│  analyzer_v5.py        → 日线模型 (次日涨跌)                  │
│  analyzer_v5_minute.py → 5分钟模型 (5分钟后涨跌)              │
└────���─────────────────────────────────────────────────────────┘
     ↓
┌──────────────────────────────────────────────────────────────┐
│                    输出结果                                    │
├──────────────────────────────────────────────────────────────┤
│  result_v6.json        → 日线预测结果                         │
│  result_v5_minute.json → 5分钟预测结果                        │
│  prediction_logs_v5   → 历史记录（用于回测）                  │
└──────────────────────────────────────────────────────────────┘
```

---

## 四、核心模块详解

### 4.1 analyzer_v5.py（日线模型）

**用途**：基于Alpha158因子预测次日涨跌

**关键参数**：
```python
ALPHA158_PRIORITY = 'p2'      # p0=25因子, p1=55因子, p2=80因子
ALPHA158_WINDOWS = [5, 10, 20, 30]  # 滚动窗口
RISE_THRESHOLD = 0.01         # 上涨定义：涨幅>=1%
PREDICT_DAYS = 1              # 预测1天后
```

**预测流程**：
```
1. load_macro_factors()     → 加载宏观因子
2. train_models_v6()         → 训练XGB/LGB/CAT三模型
3. extract_features_v6()     → 提取基础特征
4. compute_alpha158()        → 计算Alpha158因子
5. add_macro_features()      → 添加宏观因子
6. predict_fusion_v6()       → 三模型融合预测
7. risk_check()              → 风控评分
8. final_score = tech_score * risk_mult * 0.9 + llm_factor * 0.1
```

**输出字段**：
- `score`: 最终评分 (0-100)
- `tech_score`: 技术评分 (未含llm和风控)
- `risk_mult`: 风控乘数 (0-1)
- `advice`: 买入/持有/卖出

### 4.2 analyzer_v5_minute.py（5分钟模型）

**用途**：基于5分钟K线预测5分钟后涨跌

**预测目标**：`pct_chg >= 1%` (5分钟后)

**流程与日线模型类似**，但：
- 数据源：`minute_5_price` 而非 `daily_price`
- 特征：基于5分钟周期的MA/RSI/KDJ/MACD

### 4.3 backtest_v5.py（日线回测）

**用途**：模拟历史预测，验证模型准确率

**注意**：此脚本**每次都重新训练模型**，不是从历史预测日志读取

**时间窗口**：
```python
train_end = '2026-05-07'  # 训练截止
test_end = '2026-06-06'   # 测试截止
```

**回测流程**：
```
1. 训练模型 (train_end前数据)
2. 对test_end期间的每一天:
   - 提取当日特征
   - 调用predict_fusion_v6预测
   - 获取PREDICT_DAYS天后的实际涨跌
   - 记录 score, actual_up/down
3. 按阈值统计准确率
```

### 4.4 v6/qlib_alpha158.py

**用途**：Alpha158因子计算库

**关键函数**：
```python
compute_selected(df, windows=[5,10,20], priority='p0')
# windows: 滚动窗口大小
# priority: 'p0'=25因子, 'p1'=55因子, 'p2'=80因子
```

---

## 五、关键配置对照表

| 配置项 | 日线模型 | 5分钟模型 | 说明 |
|--------|----------|-----------|------|
| 数据源 | `daily_price` | `minute_5_price` | 不同表 |
| 预测周期 | 1天 | 5分钟 | |
| 上涨阈值 | 1% | 1% |  |
| Alpha158 | p2, [5,10,20,30] | (未使用) | 日线专用因子 |
| 模型缓存 | `model_cache_v6/` | `model_cache_v5/` | 分开缓存 |
| 结果输出 | `result_v6.json` | `result_v5_minute.json` | |

---

## 六、常见错误与注意事项

### ❌ 错误1：混用模型参数

**问题**：backtest_v5.py 中使用 `compute_alpha158(df)` 默认参数(p0)，但训练时用 `ALPHA158_PRIORITY='p2'`

**正确做法**：
```python
# 保持一致
df_a = av6.compute_alpha158(df, windows=av6.ALPHA158_WINDOWS, priority=av6.ALPHA158_PRIORITY)
```

### ❌ 错误2：分数计算公式不一致

**问题**：生产环境和回测的 final_score 计算公式不同

| 场景 | 公式 |
|------|------|
| 生产 (analyze_stocks) | `tech_score * risk_mult * 0.9 + llm_factor * 0.1` |
| 回测 (backtest_v5.py) | `score * rm` 或 `score * rm * 0.9` |

**影响**：回测结果不能准确反映生产效果

### ❌ 错误3：概率校准公式语义反转

**位置**：`analyzer_v5.py:511` `predict_fusion_v6`

```python
power = 1.8
score_calibrated = np.power(score, power) if score >= 0.5 else 1 - np.power(1 - score, power)
```

**问题**：
- `power > 1` 实际是压缩概率到0端（反极化）
- 在 `score=0.5` 处不连续跳跃（60分→29分）
- 高概率被压低，低概率被抬高

**影响**：买入信号极少

### ❌ 错误4：LLM因子数据缺失

**问题**：factor_signals 表中大部分记录的 `llm_confidence=0`（占位默认值）

**影响**：LLM因子实际未生效

### ❌ 错误5：风控阈值过于保守

**位置**：`analyzer_v5.py` `risk_check()`

```python
if hs300_trend < -0.5: risk *= 0.6  # 过度惩罚
```

**影响**：`rm<0.8` 占比15.9%，信号被大量过滤

---

## 七、版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| v5.0 | 2026-05 | 初始5分钟模型 |
| v5.6 | 2026-06 | 日线模型Alpha158+v6内核 |
| v6 | - | 正在开发中 |

---

## 八、快速命令参考

```bash
# 日线模型
python analyzer_v5.py           # 运行日线分析
python backtest_v5.py           # 日线回测

# 5分钟模型  
python analyzer_v5_minute.py    # 运行5分钟分析
python backtest_5minute.py      # 5分钟回测

# 数据采集
python realtime_fetcher.py --daemon  # 5分钟数据采集
python em_fetcher_daemon.py          # 日线数据采集
```