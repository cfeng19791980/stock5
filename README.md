# Stock5 - 5分钟流式数据分析系统

## 项目概述

**项目名称**：stock5
**项目功能**：5分钟频率流式数据分析系统
**核心特点**：
- ✅ 5分钟数据采集频率（实时写入）
- ✅ 技术指标实时计算（MA5基于5个5分钟周期）
- ✅ v5模型流式预测（XGBoost+LightGBM+CatBoost融合）
- ✅ 简化架构（直接写入，不需要聚合）

## 项目架构

```
stock5/
├── realtime_fetcher.py        # 5分钟数据采集写入器
├── analyzer_v5.py             # v5预测模型（已修复过拟合）
├── stocks.db                  # 数据库（包含minute_5_price表）
├── 波段股票Top30.csv          # 股票池（30只股票）
├── llm_factors/               # 因子分析模块
│   ├── factor_fusion.py       # 多因子融合
│   ├── qwen_bull_bear.py      # 简化版多空分析
│   └── llm_analyzer.py        # LLM因子分析
├── model_cache_v5/            # v5模型缓存
├── logs/                      # 日志文件夹
├── data/                      # 数据文件夹
├── README.md                  # 项目说明文档
├── 启动_数据采集.bat          # 启动数据采集
├── 启动_模型分析.bat          # 启动模型分析
└── config.json                # 配置文件
```

## 数据表结构

### minute_5_price表（5分钟K线数据）

| 字段 | 类型 | 说明 |
|------|------|------|
| code | TEXT | 股票代码 |
| datetime | TEXT | 5分钟整点时间（YYYY-MM-DD HH:MM:00） |
| open | REAL | 开盘价 |
| high | REAL | 最高价 |
| low | REAL | 最低价 |
| close | REAL | 收盘价 |
| volume | REAL | 成交量（股） |
| amount | REAL | 成交额 |
| pct_chg | REAL | 涨跌幅（%） |
| turnover | REAL | 换手率 |
| ma5 | REAL | 5分钟均线（基于5个5分钟周期） |
| ma10 | REAL | 10分钟均线（基于10个5分钟周期） |
| ma20 | REAL | 20分钟均线（基于20个5分钟周期） |
| rsi6 | REAL | RSI指标（基于6个5分钟周期） |
| macd | REAL | MACD指标 |
| macd_signal | REAL | MACD信号线 |
| macd_hist | REAL | MACD柱状图 |
| k | REAL | KDJ-K值 |
| d | REAL | KDJ-D值 |
| j | REAL | KDJ-J值 |
| boll_upper | REAL | 布林带上轨 |
| boll_mid | REAL | 布林带中轨 |
| boll_lower | REAL | 布林带下轨 |
| score | INTEGER | v5预测评分（0-100） |
| prediction | TEXT | v5预测结果 |
| buy_ratio | REAL | 买盘比例 |
| sell_ratio | REAL | 卖盘比例 |
| created_at | TEXT | 创建时间 |

## 技术指标计算逻辑

### MA均线（基于5分钟周期）
- MA5 = 最近5个5分钟周期的close平均值
- MA10 = 最近10个5分钟周期的close平均值
- MA20 = 最近20个5分钟周期的close平均值

### RSI指标（基于6个5分钟周期）
- 计算最近6个5分钟周期的价格波动
- RSI6 = 100 - (100 / (1 + RS))
- RS = 平均涨幅 / 平均跌幅

### KDJ指标（基于9个5分钟周期）
- RSV = (当前close - 最低价) / (最高价 - 最低价) × 100
- K = RSV（简化版本）
- D = RSV（简化版本）
- J = 3K - 2D

### MACD指标（基于26个5分钟周期）
- EMA12 = 最近12个5分钟周期close平均值
- EMA26 = 最近26个5分钟周期close平均值
- MACD = EMA12 - EMA26

### 布林带（基于20个5分钟周期）
- MID = 最近20个5分钟周期close平均值
- STD = 最近20个5分钟周期close标准差
- UPPER = MID + 2×STD
- LOWER = MID - 2×STD

## v5模型参数（已修复过拟合）

| 参数 | 值 | 说明 |
|------|------|------|
| max_depth | 3 | 树深度（平衡复杂度） |
| n_estimators | 25 | 树数量 |
| learning_rate | 0.03 | 学习速度 |
| min_child_weight | 4 | 正则化参数 |
| subsample | 0.75 | 样本采样比例 |
| colsample_bytree | 0.75 | 特征采样比例 |
| reg_alpha | 0.1 | L1正则化 |
| reg_lambda | 1.0 | L2正则化 |

**修复效果**：
- ✅ 评分分布正常（高分0只、中分6只、低分24只）
- ✅ 最高分73分（不再95分极端）
- ✅ 平均分23.2分（合理分布）

## 使用方法

### 1. 数据采集（单次）
```bash
python realtime_fetcher.py --once
```

### 2. 数据采集（后台连续）
```bash
python realtime_fetcher.py --daemon --interval 5
```

### 3. 模型分析（单次）
```bash
python analyzer_v5.py
```

### 4. 使用启动脚本
```bash
启动_数据采集.bat  # 启动后台数据采集
启动_模型分析.bat  # 启动模型分析
```

## 数据采集频率

**采集间隔**：5分钟
**采集时间**：交易日 9:30-11:30, 13:00-15:00
**数据写入**：每5分钟写入minute_5_price表
**技术指标**：实时计算，无需聚合

## 预测目标

**目标定义**：5分钟后涨幅>=1%
**预测输出**：score（0-100分）
**评分解读**：
- >=80分：强烈买入信号
- 50-79分：中性信号
- <50分：卖出信号

## 数据流向

```
腾讯API实时数据（每5分钟）
    ↓
realtime_fetcher.py
    ├─ 解析实时行情数据
    ├─ 计算技术指标（MA5/RSI6/KDJ/MACD/BOLL）
    └─ 写入minute_5_price表
    ↓
analyzer_v5.py
    ├─ 读取minute_5_price数据
    ├─ 提取25个特征
    ├─ 多模型融合预测
    └─ 输出评分结果
```

## 项目特点

### 1. 简化架构
- ❌ 不需要1分钟数据
- ❌ 不需要聚合器
- ✅ 直接5分钟采集写入

### 2. 技术指标适配
- ✅ MA5基于5个5分钟周期（而不是5天）
- ✅ RSI6基于6个5分钟周期
- ✅ KDJ基于9个5分钟周期

### 3. 流式实时分析
- ✅ 每5分钟更新预测评分
- ✅ 实时技术指标计算
- ✅ 无延迟数据流

## 待完成功能

- [ ] analyzer_v5_minute.py（5分钟周期预测模块）
- [ ] 流式输出格式（result_v5_minute.json）
- [ ] 前端实时展示界面

## 项目优势

1. **数据频率适中**：5分钟频率，既能捕捉短期波动，又不至于过于密集
2. **技术指标合理**：基于5分钟周期计算，适配短线分析
3. **架构简单**：直接采集写入，不需要中间聚合
4. **模型可靠**：v5模型已修复过拟合，评分分布正常

## 版本历史

- v1.0 (2026-05-15): 初始版本，5分钟数据采集写入功能完成
- v1.1 (待发布): 完成5分钟预测模块

## 作者

CSI10项目组

## 许可证

内部使用项目