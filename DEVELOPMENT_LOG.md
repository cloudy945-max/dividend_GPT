# 回测系统开发日志

---

## 规则章

### 基础规则

1. **时间戳**: 每次更新在末尾注明日期，格式 `YYYY-MM-DD`
2. **问题驱动**: 记录以问题/调试为导向，不记流水账
3. **代码优先**: 用代码片段说明问题
4. **上下文完整**: 记录错误修复过程，便于追溯

### 日志结构

```
# 回测系统开发日志

## 规则章
### 基础规则
### 内容分类
### 问题记录格式
### 代码片段规则
### 更新时机

---

## 项目概述

---

## 模块说明

---

## 调试记录

---

## AI上下文
```

### 内容分类

| 类型 | 说明 | 更新频率 |
|------|------|---------|
| 项目概述 | 项目背景、目标、目录结构 | 创建时写，不更新 |
| 模块说明 | 各模块功能、接口、返回格式 | 创建时写，不更新 |
| 调试记录 | 问题描述、根因、修复、验证 | 发现问题时写 |
| 设计原则 | 架构决策、约束条件 | 罕见更新 |
| AI上下文 | 供AI使用的关键信息 | 按需更新 |

### 问题记录格式

```
### [日期] 问题标题

**现象**: 一句话描述问题现象

**根因**: 分析导致问题的根本原因

**修复**:
```python
# 关键代码修改
```

**验证**:
| 测试用例 | 预期 | 实际 | 状态 |
|---------|------|------|------|
```

### 代码片段规则

1. 使用 ```python 等语言标签
2. 关键行添加中文注释
3. 不重要的部分用 ... 省略
4. 必要时标注行号

### 更新时机

| 事件 | 更新 |
|------|------|
| 新增模块 | 新增章节 |
| 发现并修复Bug | 调试记录 |
| 架构调整 | 调试记录 |
| 代码重构（无行为变化）| 不更新 |
| 新增测试用例 | 调试记录 |
| 修复测试失败 | 调试记录 |

---

## 项目概述

**日期**: 2026-05-04
**目标**: 建立完整的回测框架，支持策略验证和绩效评估

### 目录结构

```
backtest/
    __init__.py
    data_loader.py
    simulator.py
    strategy_adapter.py
    metrics.py
    runner.py

backtest_data/
    cache/

test_market_data.py
test_execution_plan.py
```

---

## 模块说明

### 数据加载 (data_loader.py)

**load_price_history**

使用 akshare 获取历史日线数据并对齐交易日。

- A股: `stock_zh_a_hist`
- ETF: `fund_etf_hist_em`

返回:
```python
{"招商银行": DataFrame(date, close), "159307": DataFrame(date, close)}
```

特性: 交易日对齐、停牌用前值填充、缓存到 `backtest_data/cache/`

**get_price_percentile**

计算当前价格在历史中的分位（0.0~1.0），用于估值代理。

---

### 策略适配器 (strategy_adapter.py)

**should_strong_buy 逻辑**

优先级: PB > 价格分位 > 禁用

阈值:
```python
PB_BUY_THRESHOLDS = {"招商银行": 0.85, "兴业银行": 0.75, "工商银行": 0.75}
PRICE_PERCENTILE_THRESHOLDS = {"招商银行": 0.15, "兴业银行": 0.25, "工商银行": 0.25}
```

**run_strategy**

调用现有 `generate_execution_plan()` 并适配数据格式。

输入: snapshot, current_holdings, cash_pool, monthly_budget
返回: {"actions": [...], "cash_left": float, "cash_pool": float}

---

### 回测引擎 (simulator.py)

**BacktestEngine.run_backtest**

月度循环:
```python
for each month:
    cash += monthly_budget
    snapshot = build_snapshot(month_date)
    strategy_result = run_strategy(...)
    execute_actions(...)
    record_history(...)
```

**无未来函数保证**: `_build_snapshot` 只使用 `<= current_date` 的数据

---

### 绩效指标 (metrics.py)

**calculate_metrics**

返回:
```python
{
    "total_return": 0.0,
    "annual_return": 0.0,
    "max_drawdown": 0.0,
    "volatility": 0.0,
    "sharpe": 0.0
}
```

年化按252交易日，回撤基于rolling max。

---

## 调试记录

### [2026-05-04] CASE1无买入 + CASE3误触发ETF

**问题**: CASE1无买入，CASE3误触发ETF兜底

**根因**: fallback逻辑不完善，未检查"是否真的买得起"

**修复**:
```python
can_afford_stock = False
for stock in snapshot:
    if stock["stock_code"] == "159307":
        continue  # 排除ETF
    price = stock.get("price")
    if price and monthly_budget >= price * 100:
        can_afford_stock = True
        break

if len(enhanced_actions) == 0:
    if can_afford_stock:
        # 买ETF
    else:
        # 保留现金
```

**验证**:
| Case | 条件 | 预期 | 状态 |
|------|------|------|------|
| CASE1 | 无持仓，无强买 | ETF兜底买 | ✅ |
| CASE2 | 强买pb=0.8 | 强买正常 | ✅ |
| CASE3 | 全部买不起100股 | 保留现金 | ✅ |
| CASE4 | 有持仓+再平衡 | 再平衡正常 | ✅ |

---

### [2026-05-04] 强买逻辑依赖plan.buy_list

**问题**: 原逻辑依赖 `plan.get("buy_list")`，应该独立判断

**修复**: 遍历snapshot中所有股票，基于PB独立判断强买标的

```python
strong_buy_stock = None
strong_buy_pb = None

for stock in snapshot:
    stock_code = stock.get("stock_code")
    pb = stock.get("pb")
    if pb is None:
        continue
    is_strong_buy = (
        (stock_code == "招商银行" and pb <= 0.85) or
        (stock_code in ["兴业银行", "工商银行"] and pb <= 0.75)
    )
    if is_strong_buy:
        if strong_buy_stock is None or pb < strong_buy_pb:
            strong_buy_stock = stock_code
            strong_buy_pb = pb
```

---

### [2026-05-04] 贪心补缺口算法排序

**修改**: 优先建仓当前为0的资产，再按gap排序

```python
gaps.sort(key=lambda x: (x["current_value"] == 0, x["gap"]), reverse=True)
```

---

### [2026-05-04] actions聚合逻辑

使用dict聚合，同一股票多次买入合并为一条记录

```python
actions_dict = {}
for buy in strong_buy_buys:
    if buy["stock_name"] in actions_dict:
        actions_dict[buy["stock_name"]]["shares"] += buy["shares"]
    else:
        actions_dict[buy["stock_name"]] = {...}

enhanced_actions = [v for v in actions_dict.values() if v["shares"] > 0]
```

---

## 设计原则

1. **单向依赖**: 回测模块只调用现有函数，不反向依赖
2. **无未来函数**: 所有数据严格使用 `<= current_date`
3. **ETF兜底**: 当策略无买入时，ETF作为安全资产
4. **最小交易单位**: 100股，不允许拆分
5. **边界约束**: 不允许"有预算但不投资"（除非真的买不起）

---

## 待优化项

1. 分红处理未实现
2. PB数据获取依赖外部接口
3. 回测结果可视化可增强
4. 交易成本模型可细化

---

## AI上下文

### 核心函数关系

```
generate_execution_plan (market_data.py)
    ├── calculate_rebalance_buys
    ├── allocate_with_etf
    └── calculate_buy_shares

BacktestEngine.run_backtest (backtest/simulator.py)
    ├── data_loader.load_price_history
    └── strategy_adapter.run_strategy
        └── generate_execution_plan (调用)
```

### 关键数据流

1. `load_price_history` → `price_data`
2. `_build_snapshot(price_data, month_date)` → `snapshot`
3. `run_strategy(snapshot, ...)` → `actions`
4. `execute_actions(actions)` → 更新 `holdings`

### snapshot数据结构

```python
{
    "stock_code": str,      # "招商银行" 或 "159307"
    "stock_name": str,
    "price": float,
    "pb": float | None,
    "price_percentile": float | None,
    "data_date": datetime
}
```

### CASE测试用例

| Case | 场景 | 验证点 |
|------|------|--------|
| CASE1 | 无持仓，无强买 | ETF兜底触发 |
| CASE2 | PB触发强买 | 强买标的优先 |
| CASE3 | 买不起100股 | 保留现金 |
| CASE4 | 有持仓再平衡 | 补缺口逻辑 |

### 已知陷阱

1. **ETF兜底条件**: 必须 `can_afford_stock == True`
2. **强买与再平衡**: 强买优先消耗 `total_budget`
3. **actions聚合**: `shares <= 0` 不加入

---

*最后更新: 2026-05-04*
