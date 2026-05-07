# 回测系统开发日志

***

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

| 类型    | 说明            | 更新频率     |
| ----- | ------------- | -------- |
| 项目概述  | 项目背景、目标、目录结构  | 创建时写，不更新 |
| 模块说明  | 各模块功能、接口、返回格式 | 创建时写，不更新 |
| 调试记录  | 问题描述、根因、修复、验证 | 发现问题时写   |
| 设计原则  | 架构决策、约束条件     | 罕见更新     |
| AI上下文 | 供AI使用的关键信息    | 按需更新     |

### 问题记录格式

````
### [日期] 问题标题

**现象**: 一句话描述问题现象

**根因**: 分析导致问题的根本原因

**修复**:
```python
# 关键代码修改
````

**验证**:

| 测试用例   | 预期     | 实际     | 状态     |
| ------ | ------ | ------ | ------ |
| <br /> | <br /> | <br /> | <br /> |

````

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

````

backtest/
__init__.py
data\_loader.py
simulator.py
strategy\_adapter.py
metrics.py
runner.py

backtest\_data/
cache/

test\_market\_data.py
test\_execution\_plan.py

````

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
````

特性: 交易日对齐、停牌用前值填充、缓存到 `backtest_data/cache/`

**get\_price\_percentile**

计算当前价格在历史中的分位（0.0\~1.0），用于估值代理。

***

### 策略适配器 (strategy\_adapter.py)

**should\_strong\_buy 逻辑**

优先级: PB > 价格分位 > 禁用

阈值:

```python
PB_BUY_THRESHOLDS = {"招商银行": 0.85, "兴业银行": 0.75, "工商银行": 0.75}
PRICE_PERCENTILE_THRESHOLDS = {"招商银行": 0.15, "兴业银行": 0.25, "工商银行": 0.25}
```

**run\_strategy**

调用现有 `generate_execution_plan()` 并适配数据格式。

输入: snapshot, current\_holdings, cash\_pool, monthly\_budget
返回: {"actions": \[...], "cash\_left": float, "cash\_pool": float}

***

### 回测引擎 (simulator.py)

**BacktestEngine.run\_backtest**

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

***

### 绩效指标 (metrics.py)

**calculate\_metrics**

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

***

## 调试记录

### \[2026-05-04] CASE1无买入 + CASE3误触发ETF

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

| Case  | 条件        | 预期     | 状态 |
| ----- | --------- | ------ | -- |
| CASE1 | 无持仓，无强买   | ETF兜底买 | ✅  |
| CASE2 | 强买pb=0.8  | 强买正常   | ✅  |
| CASE3 | 全部买不起100股 | 保留现金   | ✅  |
| CASE4 | 有持仓+再平衡   | 再平衡正常  | ✅  |

***

### \[2026-05-04] 强买逻辑依赖plan.buy\_list

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

***

### \[2026-05-04] 贪心补缺口算法排序

**修改**: 优先建仓当前为0的资产，再按gap排序

```python
gaps.sort(key=lambda x: (x["current_value"] == 0, x["gap"]), reverse=True)
```

***

### \[2026-05-04] actions聚合逻辑

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

***

## 设计原则

1. **单向依赖**: 回测模块只调用现有函数，不反向依赖
2. **无未来函数**: 所有数据严格使用 `<= current_date`
3. **ETF兜底**: 当策略无买入时，ETF作为安全资产
4. **最小交易单位**: 100股，不允许拆分
5. **边界约束**: 不允许"有预算但不投资"（除非真的买不起）

***

## 待优化项

1. 分红处理未实现
2. PB数据获取依赖外部接口
3. 回测结果可视化可增强
4. 交易成本模型可细化

***

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

| Case  | 场景      | 验证点     |
| ----- | ------- | ------- |
| CASE1 | 无持仓，无强买 | ETF兜底触发 |
| CASE2 | PB触发强买  | 强买标的优先  |
| CASE3 | 买不起100股 | 保留现金    |
| CASE4 | 有持仓再平衡  | 补缺口逻辑   |

### 已知陷阱

1. **ETF兜底条件**: 必须 `can_afford_stock == True`
2. **强买与再平衡**: 强买优先消耗 `total_budget`
3. **actions聚合**: `shares <= 0` 不加入

***

## \[2026-05-03] 统一ETF标识 + 表格显示修复

### 问题1: ETF标识不统一

**现象**: ETF在内部计算和展示时标识混乱

**修复**:

```python
# 引入两个字段
"stock_code": "159307",        # 内部计算用
"stock_name": "红利低波100ETF"  # 展示用

# 全局配置
ALLOWED_STOCKS = ["招商银行", "兴业银行", "工商银行", "双汇发展", "159307"]
ETF_CODE_MAP = {"159307": "红利低波100ETF"}
CODE_TO_NAME = {"159307": "红利低波100ETF", "招商银行": "招商银行", ...}
```

**验证**:

| 函数                        | stock\_code | stock\_name |
| ------------------------- | ----------- | ----------- |
| get\_market\_data         | ✅           | ✅           |
| generate\_execution\_plan | ✅           | ✅           |
| actions                   | ✅           | ✅           |

***

### 问题2: manage\_portfolio.py 表格显示不对齐

**现象**: 列标题和数据没有分隔，数据全部连在一起

**根因**: 使用字符串拼接没有添加分隔符

**修复**:

```python
# 列之间加2个空格分隔
header_parts = []
for col in df_copy.columns:
    header_parts.append(ljust_display(col, col_widths[col]))
print("  ".join(header_parts))  # 用2个空格连接
print("-" * (sum(col_widths.values()) + 2 * (len(col_widths) - 1)))
```

***

### 问题3: 日期显示格式不对

**现象**: `2026-04-28 00:00:00` 多了时间部分

**根因**: pandas Timestamp对象直接转字符串

**修复**:

```python
def format_date(value):
    import pandas as pd
    if value is None:
        return ""
    if hasattr(value, 'strftime'):
        return value.strftime('%Y-%m-%d')
    if isinstance(value, str):
        try:
            return pd.to_datetime(value).strftime('%Y-%m-%d')
        except:
            return value[:10] if len(value) >= 10 else value
    return str(value)[:10]
```

***

### 问题4: 列名是英文没有转中文

**修复**:

```python
COLUMN_NAMES_MAP = {
    'stock_name': '股票名称',
    'shares': '持仓股数',
    'cost_price': '成本价',
    'total_cost': '总成本',
    'date': '日期',
    'type': '类型',
    'price': '价格',
    'cash_flow': '现金流',
    'dividend_per_share': '每股分红'
}

# 转换列名为中文
df_copy.columns = [COLUMN_NAMES_MAP.get(col, col) for col in df_copy.columns]
```

***

## \[2026-05-03] 资金池统计 + 再平衡优化

### 问题: 资金池使用统计错误

**现象**: 再平衡模式下 `used_cash_pool` 计算不正确

**根因**: 旧逻辑只在 `current_holdings is None` 时才计算

**修复**:

```python
# 简化计算公式
used_cash_pool = max(0, total_budget - monthly_budget)

# 确保执行顺序
cash_pool = min(cash_left, MAX_CASH_POOL)
remaining_cash_pool = cash_pool  # 在更新后计算
```

***

### 优化: calculate\_rebalance\_buys 新策略

**旧策略**: 比例缩放

**新策略**:

```python
# Step1: 计算偏离度
deviation = target_weight - current_weight

# Step2: 按偏离度×优先级排序
sorted_stocks.sort(key=lambda x: x[1] * x[2], reverse=True)

# Step3: 循环买入100股
while cash_pool >= 100:
    # 找偏离度最大的标的
    # 买入100股
    # 更新状态
    # 重新计算偏离度
```

**强买优先级**: `effective_deviation = deviation * 1.5`

***

### 优化: ETF买入规则

**条件**: 只有当所有股票 `deviation < 0.02` 才允许买ETF

**最大化买入**:

```python
# 优化前：逐手买
while cash_pool >= etf_price * 100:
    shares += 100
    cash_pool -= cost

# 优化后：最大化一次买
min_lot_cost = etf_price * 100
if cash_pool >= min_lot_cost:
    max_lots = int(cash_pool / min_lot_cost)
    shares = max_lots * 100
    cost = shares * etf_price
```

***

## \[2026-05-03] 健壮性增强

### 问题: price为None导致计算错误

**修复**:

```python
# 统一过滤 price_map
price_map = {}
for s in snapshot:
    stock_code = s.get("stock_code")
    price = s.get("price")
    if stock_code and price is not None and price > 0:
        price_map[stock_code] = price

# 检查有效标的
valid_stocks_for_buy = [code for code in target_weights.keys() if code in price_map]
if not valid_stocks_for_buy:
    print(f"  [警告] 没有有效的标的可以交易")
    return {"buys": [], "cash_left": total_budget}
```

***

### 问题: current\_holdings允许缺失

**修复**:

```python
# 自动补0
current_holdings = dict(current_holdings) if current_holdings else {}
for stock_code in target_weights.keys():
    if stock_code not in current_holdings:
        current_holdings[stock_code] = 0.0
```

***

### 日志记录

```python
skipped_stocks = []
for s in snapshot:
    if s.get("stock_code") not in price_map:
        skipped_stocks.append(s.get("stock_code"))

if skipped_stocks:
    print(f"  [警告] 以下标的因价格无效未参与计算: {', '.join(skipped_stocks)}")
```

***

## \[2026-05-03] 市场数据缓存优化

### 问题: 频繁刷新数据

**原逻辑**: 每60秒刷新一次

**新逻辑**: 每天收盘后第一次需要时刷新

```python
_last_update_date = None  # 格式：YYYY-MM-DD
CLOSE_TIME = 15  # 下午3点

def need_refresh():
    now = pd.Timestamp.now()
    today = now.strftime('%Y-%m-%d')
    current_hour = now.hour

    if _last_update_date is None:
        return True

    if current_hour >= CLOSE_TIME and _last_update_date != today:
        return True

    return False
```

**缓存策略**:

| 时间          | 行为      |
| ----------- | ------- |
| 第一次运行       | 刷新并缓存   |
| 15:00 之前    | 使用缓存    |
| 15:00 之后第一次 | 刷新并更新缓存 |
| 15:00 之后后续  | 使用当天缓存  |

**ETF缓存**:

```python
_etf_df_cache = None  # ETF独立缓存
def need_refresh():    # A股和ETF共用刷新判断
```

***

## \[2026-05-03] README文档编写

新增 `README.md`，包含：

- 功能特点
- 文件结构
- 安装依赖
- 使用方法
- 支持的标的
- 分析指标
- 再平衡策略
- 配置参数
- 示例输出
- 数据格式
- 刷新机制

***

***

## \[2026-05-03] 持仓管理增强 + 数据结构扩展

### 增强1: 日期类型转换

**需求**: transactions 和 dividends 的 date 字段需要转换为 datetime 类型

**修复**:

```python
def load_data(self):
    if os.path.exists(self.transactions_path):
        self.transactions = pd.read_csv(self.transactions_path)
        if 'cash_flow' not in self.transactions.columns:
            self.transactions['cash_flow'] = 0.0
        if not self.transactions.empty:  # 空DataFrame时不报错
            self.transactions['date'] = pd.to_datetime(self.transactions['date'])
    # ... dividends 同理
```

***

### 增强2: 卖出股数校验

**需求**: 防止卖出超过持仓

**修复**:

```python
def _update_holdings_sell(self, stock_name, shares):
    if stock_name in self.holdings['stock_name'].values:
        idx = self.holdings[self.holdings['stock_name'] == stock_name].index[0]
        old_shares = self.holdings.at[idx, 'shares']
        if shares > old_shares:  # 新增校验
            raise ValueError("卖出股数超过持仓")
        # ... 原有逻辑
```

***

### 增强3: 现金流字段 cash\_flow

**需求**: 记录每笔交易的现金流

**修复**:

```python
def add_transaction(self, date, type_, stock_name, price, shares):
    if type_ == 'buy':
        cash_flow = - price * shares
    elif type_ == 'sell':
        cash_flow = price * shares
    else:
        cash_flow = 0.0
    
    new_transaction = pd.DataFrame({
        'date': [date],
        'type': [type_],
        'stock_name': [stock_name],
        'price': [price],
        'shares': [shares],
        'cash_flow': [cash_flow]  # 新增字段
    })
    # ...
```

**兼容性**: 旧数据自动补 `cash_flow = 0.0`

***

### 增强4: 总成本字段 total\_cost

**需求**: 记录持仓总成本 = 股数 × 成本价

**修复**:

```python
# 买入时更新
self.holdings.at[idx, 'shares'] = new_shares
self.holdings.at[idx, 'cost_price'] = new_cost
self.holdings.at[idx, 'total_cost'] = new_shares * new_cost

# 部分卖出时按比例减少
self.holdings.at[idx, 'total_cost'] = old_total_cost * (new_shares / old_shares)
```

***

### 新增: 按日期排序的交易

**需求**: 获取按日期升序排序的交易记录

**新增**:

```python
def get_transactions_sorted(self):
    return self.transactions.sort_values('date').copy()
```

***

## \[2026-05-03] 市场数据模块增强

### 增强1: 股票名称映射机制

**问题**: akshare 返回的名称与输入可能不一致

**修复**:

```python
STOCK_NAME_MAP = {
    "招商银行": "招商银行",
    "兴业银行": "兴业银行",
    "工商银行": "工商银行",
    "双汇发展": "双汇发展",
    "红利ETF": "红利ETF"
}

def get_market_data(stock_name: str) -> dict:
    lookup_name = STOCK_NAME_MAP.get(stock_name, stock_name)
    # ... 优先用映射名匹配，失败再用原名称，最后模糊匹配
```

***

### 增强2: 缓存机制优化

**问题**: 每次调用都重新获取全市场数据

**修复**:

```python
_market_df_cache = None
_last_update_time = None
CACHE_TTL = 60  # 60秒

def get_market_data(stock_name: str) -> dict:
    current_time = time.time()
    if _market_df_cache is None or _last_update_time is None or (current_time - _last_update_time) > CACHE_TTL:
        print("刷新市场数据缓存")
        _market_df_cache = ak.stock_zh_a_spot_em()
        _last_update_time = current_time
    # ...
```

***

### 增强3: 字段读取安全

**问题**: akshare 字段可能变化，导致 KeyError

**修复**:

```python
# 使用 .get() 而不是直接访问
price = row.get('最新价')
if price is None or pd.isna(price) or price == '-':
    price = row.get('收盘价')

# 检查名称字段是否存在
if '名称' not in df.columns:
    raise ValueError("数据源缺少'名称'字段")

# 名称转换为字符串，防止 str.contains 报错
name_series = df['名称'].astype(str)
```

***

### 增强4: 批量获取函数

**需求**: 一次获取多个股票的数据

**新增**:

```python
def get_multiple_market_data(stock_list: list) -> list:
    results = []
    for stock_name in stock_list:
        try:
            result = get_market_data(stock_name)
            if result is not None:
                results.append(result)
            else:
                results.append({"stock_name": stock_name, "error": "返回None"})
        except Exception as e:
            results.append({"stock_name": stock_name, "error": str(e)})
    # 统计
    success_count = sum(1 for r in results if "error" not in r)
    print(f"成功获取: {success_count} 条, 失败: {len(results) - success_count} 条")
    return results
```

***

### 增强5: 安全辅助函数

**新增**:

```python
def safe_float(value):
    if value is None or pd.isna(value) or value == '-':
        return None
    return float(value)
```

***

### 增强6: 输入校验

**需求**: 防止误输入不支持的股票

**新增**:

```python
ALLOWED_STOCKS = ["招商银行", "兴业银行", "工商银行", "双汇发展", "红利ETF"]

def get_market_data(stock_name: str) -> dict:
    if stock_name not in ALLOWED_STOCKS:
        raise ValueError(f"不支持的股票: {stock_name}")
    # ...
```

***

## \[2026-05-03] 执行计划模块

### 新增1: 买入股数计算

**需求**: 计算在100股限制下最多能买多少股

**新增**:

```python
def calculate_buy_shares(price, budget):
    if price is None or price <= 0 or budget is None or budget <= 0:
        return {"shares": 0, "cost": 0.0, "remaining_cash": float(budget)}
    lot_price = price * 100
    max_lots = int(budget / lot_price)
    shares = max_lots * 100
    cost = shares * price if shares >= 100 else 0.0
    return {
        "shares": shares,
        "cost": float(cost),
        "remaining_cash": float(budget - cost)
    }
```

***

### 新增2: 单次买入执行

**需求**: 执行单次买入决策

**新增**:

```python
def execute_single_buy(stock, budget):
    if stock.get("price") is None:
        return {"stock_name": stock.get("stock_name"), "action": "skip", "reason": "价格无效"}
    buy = calculate_buy_shares(stock["price"], budget)
    if buy["shares"] == 0:
        return {"stock_name": stock.get("stock_name"), "action": "skip", "reason": "预算不足100股"}
    return {
        "stock_name": stock.get("stock_name"),
        "action": "buy",
        "shares": buy["shares"],
        "cost": buy["cost"],
        "remaining_cash": buy["remaining_cash"]
    }
```

***

### 新增3: ETF兜底分配

**需求**: 优先买目标股票，剩余买ETF

**核心逻辑**:

```python
def allocate_with_etf(plan, snapshot, monthly_budget, cash_pool_amount, strong_buy):
    # ... 个股买入
    if buy_result.get("action") == "skip":
        if strong_buy:
            skip_etf_buy = True  # 强买但买不起，不买ETF，攒钱
    
    # ETF只使用当月剩余资金
    monthly_spent = min(stock_spent, monthly_budget)
    monthly_remaining = max(0, monthly_budget - monthly_spent)
    if monthly_remaining > 800 and not skip_etf_buy:
        # ... 买ETF
    
    # 使用dict聚合actions，防止重复
    actions_dict = {}
    # ...
    
    # 现金流校验
    total_input = monthly_budget + (cash_pool_amount if strong_buy else 0)
    total_output = stock_spent + etf_spent + cash_left
    if abs(total_input - total_output) > 1:
        print(f"警告: 现金流不平衡! 输入: {total_input:.2f}, 输出: {total_output:.2f}")
```

***

### 新增4: 生成执行计划

**需求**: 整合所有逻辑，生成可执行计划

**新增**:

```python
def generate_execution_plan(plan, snapshot, monthly_budget=3000):
    # 1. 只针对目标买入标的判断强买
    target_stock_name = buy_list[0].get("stock_name") if buy_list else None
    strong_buy = False
    if target_stock_name and target_stock:
        pb = target_stock.get("pb")
        if pb is not None:
            if target_stock_name == "招商银行" and pb <= 0.85:
                strong_buy = True
            elif (target_stock_name == "兴业银行" or target_stock_name == "工商银行") and pb <= 0.75:
                strong_buy = True
    
    # 2. 正常分配
    allocation = allocate_with_etf(plan, snapshot, monthly_budget, cash_pool, strong_buy)
    
    # 3. 资金池超限时，超出部分买ETF
    cash_left = allocation.get("cash_left", 0.0)
    total_actions = allocation.get("actions", [])
    if cash_left > MAX_CASH_POOL:
        excess_amount = cash_left - MAX_CASH_POOL
        etf_only_plan = {"buy_list": []}
        etf_allocation = allocate_with_etf(etf_only_plan, snapshot, excess_amount, 0.0, False)
        # 合并ETF买入结果
        # ...
        cash_left = MAX_CASH_POOL + etf_allocation.get("cash_left", 0.0)
    
    # 4. 增强actions，增加price和cost
    enhanced_actions = []
    for action in total_actions:
        stock_name = action.get("stock_name")
        shares = action.get("shares", 0)
        price = None
        for stock in snapshot:
            if stock.get("stock_name") == stock_name:
                price = stock.get("price")
                break
        cost = price * shares if price is not None and shares > 0 else None
        enhanced_action = {
            "stock_name": stock_name,
            "shares": shares,
            "price": price,
            "cost": cost
        }
        enhanced_actions.append(enhanced_action)
    
    # 5. 计算资金池使用情况
    used_cash_pool = 0.0
    if strong_buy and stock_spent > monthly_budget:
        used_cash_pool = stock_spent - monthly_budget
    
    return {
        "month_budget": monthly_budget,
        "actions": enhanced_actions,
        "cash_left": cash_left,
        "cash_pool": cash_pool,
        "used_cash_pool": used_cash_pool,
        "remaining_cash_pool": remaining_cash_pool,
        "is_strong_buy": strong_buy
    }
```

***

## \[2026-05-04] 投资组合分析模块

### 新增1: 基础分析功能

**需求**: 计算市值、成本、收益、收益率

**新增**:

```python
def analyze_portfolio(holdings, snapshot, dividends=None):
    positions = []
    total_value = 0.0
    total_cost = 0.0
    
    # 创建股票价格映射
    price_map = {}
    for stock in snapshot:
        stock_name = stock.get("stock_name")
        price = stock.get("price")
        if stock_name and price is not None:
            price_map[stock_name] = price
    
    # 遍历持仓
    for _, row in holdings.iterrows():
        stock_name = row.get("stock_name")
        shares = row.get("shares", 0)
        cost_price = row.get("cost_price", 0)
        total_cost_this = row.get("total_cost", shares * cost_price)
        
        price = price_map.get(stock_name)
        market_value = shares * price if price is not None and shares > 0 else 0.0
        
        profit = market_value - total_cost_this if total_cost_this > 0 else 0.0
        return_rate = profit / total_cost_this if total_cost_this > 0 else None
        
        positions.append({
            "stock_name": stock_name,
            "shares": shares,
            "cost_price": cost_price,
            "total_cost": total_cost_this,
            "price": price,
            "market_value": market_value,
            "profit": profit,
            "return_rate": return_rate
        })
        
        total_value += market_value
        total_cost += total_cost_this
    
    total_profit = total_value - total_cost
    total_return = total_profit / total_cost if total_cost > 0 else None
    
    return {
        "total_value": total_value,
        "total_cost": total_cost,
        "total_profit": total_profit,
        "total_return": total_return,
        "positions": positions
    }
```

***

### 新增2: 年分红现金流

**需求**: 计算年分红现金流 = sum(每个股票 分红 × 当前持仓股数)

**新增**:

```python
def calculate_annual_dividend(holdings, dividends):
    annual_dividend = 0.0
    
    # 创建持仓股数映射
    shares_map = {}
    for _, row in holdings.iterrows():
        stock_name = row.get("stock_name")
        shares = row.get("shares", 0)
        if stock_name:
            shares_map[stock_name] = shares
    
    # 遍历分红记录
    for _, row in dividends.iterrows():
        stock_name = row.get("stock_name")
        dividend_per_share = row.get("dividend_per_share", 0)
        if stock_name in shares_map:
            shares = shares_map[stock_name]
            annual_dividend += dividend_per_share * shares
    
    return annual_dividend
```

**修改 analyze\_portfolio**:

```python
# 计算年分红现金流
annual_dividend = 0.0
dividend_yield = None

if dividends is not None:
    annual_dividend = calculate_annual_dividend(holdings, dividends)
    if total_value > 0:
        dividend_yield = annual_dividend / total_value

return {
    # ... 原有字段
    "annual_dividend": annual_dividend,
    "dividend_yield": dividend_yield,
    "positions": positions
}
```

***

### 新增3: 打印分析结果

**需求**: 格式化输出分析结果

**新增**:

```python
def print_analysis(analysis):
    print("\n" + "="*60)
    print("投资组合分析报告")
    print("="*60)
    
    print(f"\n总资产: {analysis['total_value']:,.2f}")
    print(f"总成本: {analysis['total_cost']:,.2f}")
    print(f"总收益: {analysis['total_profit']:,.2f}")
    if analysis['total_return'] is not None:
        print(f"总收益率: {analysis['total_return']*100:.2f}%")
    
    print(f"\n年分红现金流: {analysis['annual_dividend']:,.2f}")
    if analysis['dividend_yield'] is not None:
        print(f"组合股息率: {analysis['dividend_yield']*100:.2f}%")
    
    print("\n" + "-"*60)
    print("持仓明细:")
    print("-"*60)
    
    for pos in analysis['positions']:
        print(f"\n{pos['stock_name']}")
        print(f"  持仓数量: {pos['shares']}")
        print(f"  成本价: {pos['cost_price']:.2f}")
        print(f"  总成本: {pos['total_cost']:.2f}")
        if pos['price'] is not None:
            print(f"  当前价格: {pos['price']:.2f}")
            print(f"  市值: {pos['market_value']:.2f}")
            print(f"  浮动收益: {pos['profit']:.2f}")
            if pos['return_rate'] is not None:
                print(f"  收益率: {pos['return_rate']*100:.2f}%")
        else:
            print(f"  当前价格: --")
            print(f"  市值: --")
            print(f"  浮动收益: --")
            print(f"  收益率: --")
    
    print("\n" + "="*60)
```

***

## 设计原则更新

### 资金池管理

1. **资金池上限**: `MAX_CASH_POOL = 6000` (2个月预算)
2. **强买资金**: 强买时可以使用资金池
3. **ETF资金**: ETF只使用当月预算剩余，不使用资金池
4. **强买买不起**: 不买ETF，资金全部进入资金池，等下个月
5. **超额处理**: 资金池超过上限时，超出部分自动买ETF

### 安全保障

1. **现金流校验**: `abs(total_input - total_output) <= 1`
2. **字段访问安全**: 全部使用 `.get()`，防止 KeyError
3. **空值处理**: price/pb 为 None 时不报错
4. **actions聚合**: 使用dict防止重复标的

***

## AI上下文更新

### 核心函数关系

```
portfolio_analysis.py
    ├── calculate_annual_dividend
    └── analyze_portfolio
        └── print_analysis

generate_execution_plan (market_data.py)
    ├── calculate_buy_shares
    ├── execute_single_buy
    ├── allocate_with_etf
    └── (返回结构包含 cash_pool, used_cash_pool, is_strong_buy)

PortfolioManager (portfolio.py)
    ├── load_data
    ├── add_transaction
    ├── _update_holdings_buy
    ├── _update_holdings_sell
    └── get_transactions_sorted
```

### 关键数据流

1. `get_market_data` / `get_multiple_market_data` → `snapshot`
2. `generate_execution_plan(plan, snapshot, ...)` → `execution_plan`
3. `analyze_portfolio(holdings, snapshot, dividends)` → `analysis_result`

### 返回结构示例

**generate\_execution\_plan**:

```python
{
    "month_budget": 3000,
    "actions": [
        {"stock_name": "招商银行", "shares": 100, "price": 35.0, "cost": 3500.0}
    ],
    "cash_left": 1500.0,
    "cash_pool": 1500.0,
    "used_cash_pool": 500.0,
    "remaining_cash_pool": 1500.0,
    "is_strong_buy": True
}
```

**analyze\_portfolio**:

```python
{
    "total_value": 50000.0,
    "total_cost": 45000.0,
    "total_profit": 5000.0,
    "total_return": 0.1111,
    "annual_dividend": 1200.0,
    "dividend_yield": 0.024,
    "positions": [...]
}
```

***

*最后更新: 2026-05-04*

<br />

***

## \[2026-05-05] ETF Fallback 策略优化

现象 : ETF吞噬全部资金，策略退化为ETF定投

根因 : 原有ETF触发条件太宽松，只要没有股票买入就立即执行ETF兜底

修复 :

1. 参数调整:

```
MONTHS_TO_ALLOW_ETF = 6  # 原为3，延
长等待时间
# MAX_CASH_POOL 改为动态计算
MAX_CASH_POOL = monthly_budget * 4  
# 原为2倍
```

1. 新增安全限制:

```
# 只有在 buy_list 为空时，才允许触发ETF
买入
if buy_list:
    allow_etf = False
    print("  禁止ETF：有候选股票待买")
```

1. ETF买入金额限制:

```
# ETF买入使用资金 = min
(monthly_budget, cash_pool)
etf_budget = min(monthly_remaining, 
monthly_budget)
```

1. 增加调试输出:

```
print("====== ETF 决策调试 ======")
print(f"cash_pool: 
{cash_pool_amount}")
print(f"MONTHS_TO_ALLOW_ETF: 
{MONTHS_TO_ALLOW_ETF}")
print(f"MAX_CASH_POOL: 
{MAX_CASH_POOL}")
print(f"条件A(cash_pool>=MAX): 
{cash_pool_amount >= MAX_CASH_POOL}
")
print(f"条件B(月数>=阈值): 
{tracking_months_no_stock >= 
MONTHS_TO_ALLOW_ETF}")
```

1. 未来扩展钩子:

```
# TODO: 如果未来出现 strong_buy 机会，
考虑卖出ETF换仓股票（ETF -> 股票切换机
制）
```

修改文件 : market\_data.py (全局参数、allocate\_with\_etf、generate\_execution\_plan)

验证 :

测试用例 预期 实际 状态 CASE1 正常买入股票 成功买入股票 ✅ CASE2 买不起股票保留现金 保留现金不买ETF ✅ CASE3 积累后触发ETF 第5个月触发ETF买入 ✅ CASE4 条件A触发 cash\_pool达12000时触发 ✅

## \[2026-05-05] 删除冗余测试文件

现象 : 项目中存在多个功能重复的测试文件

根因 : 开发过程中创建的临时测试文件未及时清理

修复 :

删除以下冗余文件:

- test\_etf.py - 早期探索性测试，已过时
- test\_etf\_logic.py - 与 test\_backtest\_full.py 功能重复
- test\_backtest\_logic.py - 调试功能测试
  保留的核心测试文件:

文件 用途 test\_etf\_fallback.py ETF fallback 逻辑测试 test\_backtest\_full.py 完整资金演化系统测试 test\_history\_data.py 历史数据加载测试 test\_market\_data.py 市场数据结构验证 test\_execution\_plan.py 策略决策逻辑验证

最后更新: 2026-05-05

***

## \[2026-05-06] A股市场数据接口修复

现象 : 选择7运行分析时，ETF数据获取成功但A股股票数据全部失败

根因 : ak.stock\_zh\_a\_spot\_em() 接口返回 Connection aborted: Remote end closed connection without response ，而 ak.fund\_etf\_spot\_em() 接口正常工作

修复 :

```
# market_data.py

# 新增股票代码映射，用于备选接口
STOCK_CODE_MAPPING = {
    "招商银行": "sh600036",
    "兴业银行": "sh601166",
    "工商银行": "sh601398",
    "双汇发展": "sz000895"
}

# 主接口失败时，备选使用日线接口
except Exception as primary_e:
    print(f"主接口获取失败: 
    {primary_e}，尝试备选接口...")
    ak_code = STOCK_CODE_MAPPING.get
    (stock_code)
    if ak_code:
        df_daily = ak.
        stock_zh_a_daily
        (symbol=ak_code, 
        start_date=start_date, 
        end_date=end_date, 
        adjust='qfq')
        # 获取最新收盘价
```

验证 :

标的 预期 实际 状态 招商银行 获取成功 price=41.04 (前复权) ✅ 兴业银行 获取成功 price=20.45 (前复权) ✅ 工商银行 获取成功 price=7.93 (前复权) ✅ 双汇发展 获取成功 price=25.74 (前复权) ✅

## \[2026-05-06] ETF收益显示-100%问题

现象 : 159307收益显示为-100%，其他股票正常

根因 : 持仓中ETF存储的是代码 159307 ，但市场数据返回的名称是 红利低波100ETF ，导致 price\_map.get("159307") 返回 None

修复 :

```
# portfolio_analysis.py

# 创建股票价格映射，方便查找（同时支持代码
和名称）
price_map = {}
for stock in snapshot:
    stock_code = stock.get
    ("stock_code")
    stock_name = stock.get
    ("stock_name")
    price = stock.get("price")
    if stock_code and price is not 
    None:
        price_map[stock_code] = 
        price  # 新增：用代码作为key
    if stock_name and price is not 
    None:
        price_map[stock_name] = 
        price  # 保留：用名称作为key
```

验证 :

标的 修复前收益率 修复后收益率 状态 159307 -100% +0.28% ✅ 其他股票 正常 正常 ✅

## \[2026-05-06] 日线数据前复权 + 缓存机制

现象 : 备选接口获取的日线数据是不复权的，与用户输入的前复权成本价不匹配

根因 : ak.stock\_zh\_a\_daily() 默认返回不复权数据

修复 :

```
# market_data.py

# 1. 日线数据缓存
_daily_cache = {}  # key为股票代码

# 2. 备选接口使用前复权 + 动态日期范围
df_daily = ak.stock_zh_a_daily(
    symbol=ak_code, 
    start_date=(pd.Timestamp.now() 
    - pd.Timedelta(days=30)).
    strftime('%Y%m%d'),
    end_date=pd.Timestamp.now().
    strftime('%Y%m%d'), 
    adjust='qfq'  # 前复权
)

# 3. 缓存机制：每天只刷新一次
need_daily_refresh = True
if ak_code in _daily_cache:
    cached_date = _daily_cache
    [ak_code].get('date')
    if cached_date == pd.Timestamp.
    now().strftime('%Y-%m-%d'):
        need_daily_refresh = False
```

验证 :

操作 日志输出 状态 第一次获取 备选接口获取成功... ✅ 从网络获取 第二次获取 使用缓存的日线数据... ✅ 使用缓存 清除缓存后 备选接口获取成功... ✅ 重新获取

## \[2026-05-06] 分红收益直观展示

现象 : 分红只是记录到系统中，没有直观展示给用户

根因 : 原系统只计算股价波动收益，分红现金虽已发放但未计入收益展示

修复 :

```
# portfolio_analysis.py

# 1. 计算每个持仓已收分红
dividends_received_map = {}
for stock_name, div in 
dividends_by_stock.items():
    dividends_received_map
    [stock_name] = div

# 2. 计算综合收益（扣除分红后的成本）
dividend_received = 
dividends_received_map.get
(stock_name, 0.0)
adjusted_cost = total_cost_this - 
dividend_received
total_profit_with_div = 
market_value - adjusted_cost
return_rate_with_div = 
total_profit_with_div / 
adjusted_cost

# 3. 展示修改
print(f"{'名称':<12} {'市值':>10} {'
综合收益率':>10} {'已收分红':>10}")
print("-" * 45)
for pos in analysis['positions']:
    print(f"{stock_name:<12} 
    {market_value:>10.2f} 
    {rate_str:>10} {div_str:>10}")
```

验证 :

```
---- 收益情况 ----
名称                   市值      综合
收益率       已收分红
------------------------------------
---------
双汇发展            5542.00     +17.
3%      +160元
兴业银行            5337.00      -2.
7%         --
工商银行            2208.00      -1.
6%         --
红利低波100ETF      1927.80      +0.
3%         --
```

最后更新: 2026-05-06

***

## \[2026-05-07] IRR计算异常修复

现象 : 总收益率为正（+2.53%），但IRR显示为负数（-31.8%）

根因 :

1. 最后一次买入和当前市值计算在同一个月
2. IRR是年化指标，7个月持有期太短
   修复 :

```
# portfolio_analysis.py

# 修复1：时间点冲突处理
if last_trans_month == total_months:
    cash_flows.append((total_months 
    + 1, holdings_value))

# 修复2：设置IRR计算门槛（持有期≥1年）
if total_months < 12:
    return {'overall_irr': 
    None, ...}
```

验证 :

指标 修复前 修复后 总收益率 +2.53% +2.53% IRR -31.8% 暂无数据

## \[2026-05-07] 添加记录退出机制

需求 : 用户误触添加记录后，无法中途退出返回到主菜单

修复 :

```
# manage_portfolio.py

# 修改输入函数，添加退出检测
def get_valid_date(prompt):
    while True:
        date_str = input(prompt)
        if date_str.lower() in 
        ['q', 'quit']:
            return None

# 在各菜单函数中添加退出检测
def menu_add_buy(portfolio):
    date = get_valid_date("日期 
    (YYYY-MM-DD): ")
    if date is None:
        print("已取消操作")
        return
```

验证 :

测试场景 结果 日期输入 q ✅ 退出并返回主菜单 股票名称输入 q ✅ 退出并返回主菜单 正常输入数据 ✅ 成功添加记录

最后更新: 2026-05-07

