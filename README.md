# 分红投资组合管理系统

一个基于 Python 的分红投资组合管理和分析工具，支持自动获取市场数据、计算收益、生成买入建议和可视化图表。

## 📊 功能特点

### 核心功能

- **持仓管理**: 记录买入、卖出、分红等交易记录
- **市场数据**: 自动获取 A 股和 ETF 实时行情
- **投资分析**: 计算总资产、收益率、年分红现金流
- **再平衡建议**: 基于目标权重的智能买入建议
- **可视化**: 生成资产分布、收益、现金流等图表

### 高级功能

- **目标权重再平衡**: 支持自定义目标权重配置
- **强买机制**: 基于 PB 估值的低吸策略
- **资金池管理**: 自动累积和使用闲置资金
- **智能缓存**: 每天收盘后自动刷新数据

## 📁 文件结构

```
dividend_GPT/
├── main.py                 # 主程序入口
├── manage_portfolio.py     # 交互式持仓管理脚本
├── portfolio.py            # 持仓管理模块
├── market_data.py          # 市场数据获取模块
├── portfolio_analysis.py   # 投资组合分析模块
├── visualization.py        # 可视化模块
├── dashboard.py            # Streamlit 仪表盘
├── requirements.txt        # 依赖列表
├── data/                   # 数据目录
│   ├── holdings.csv        # 持仓数据
│   ├── transactions.csv    # 交易记录
│   └── dividends.csv       # 分红记录
└── output/                 # 输出目录（图表）
    ├── allocation.png
    ├── returns.png
    ├── growth.png
    └── dividend.png
```

## 🛠️ 安装依赖

```bash
pip install -r requirements.txt
```

主要依赖：

- pandas >= 1.0
- akshare >= 1.0
- matplotlib >= 3.0
- streamlit >= 1.0（可选，用于仪表盘）

## 🚀 使用方法

### 方法一：交互式管理

```bash
python manage_portfolio.py
```

功能菜单：

1. 查看当前持仓
2. 添加买入记录
3. 添加卖出记录
4. 添加分红记录
5. 查看交易记录
6. 查看分红记录
7. 运行分析
8. 月度买入建议
9. 清空所有数据

### 方法二：一键分析

```bash
python main.py
```

自动执行：

1. 加载持仓数据
2. 获取市场数据
3. 分析投资组合
4. 显示仪表盘
5. 生成可视化图表

### 方法三：Streamlit 仪表盘

```bash
streamlit run dashboard.py
```

## 📈 支持的标的

| 标的代码   | 标的名称       | 目标权重 |
| ------ | ---------- | ---- |
| 招商银行   | 招商银行       | 25%  |
| 兴业银行   | 兴业银行       | 30%  |
| 工商银行   | 工商银行       | 20%  |
| 双汇发展   | 双汇发展       | 15%  |
| 159307 | 红利低波100ETF | 10%  |

## 📊 分析指标

| 指标    | 说明                 |
| ----- | ------------------ |
| 总资产   | 当前持仓市值总和           |
| 总收益率  | (当前市值 - 总成本) / 总成本 |
| 年现金流  | 最近12个月分红 × 当前持仓股数  |
| 股息率   | 年现金流 / 总资产         |
| 现金流质量 | 年现金流 / 总成本         |
| 资产分布  | 各标的占比              |
| 偏离度   | 实际权重与目标权重的差异       |

## 🎯 再平衡策略

### 核心算法

1. **计算偏离度**: deviation = target\_weight - current\_weight
2. **按偏离度排序**: 从大到小排列
3. **逐手买入**: 每次买入100股，更新状态后重新计算
4. **强买机制**: 强买标的优先级提高50%
5. **ETF规则**: 所有股票偏离 < 2% 才允许买ETF

### 强买触发条件

- 招商银行 PB <= 1.0
- 兴业银行 PB <= 0.9
- 工商银行 PB <= 0.9

## 🔧 配置参数

```python
# 目标权重
TARGET_WEIGHTS = {
    "兴业银行": 0.30,
    "招商银行": 0.25,
    "工商银行": 0.20,
    "双汇发展": 0.15,
    "159307": 0.10
}

# 资金池配置
MAX_CASH_POOL = 6000  # 最大资金池（2个月预算）

# 偏离度阈值
MIN_DEVIATION_TO_BUY = 0.02  # ETF买入门槛

# 收盘时间
CLOSE_TIME = 15  # 下午3点
```

## 📋 示例输出

### 投资组合总览

```
==== 投资组合总览 ====

总资产：150,000.00
总收益率：+8.5%
年现金流：2,400.00
股息率：1.6%
现金流质量：3.2%

---- 资产分布 ----
招商银行：25% (+5%)
兴业银行：30% (-5%)
工商银行：20%
双汇发展：15%
红利低波100ETF：10%

---- 收益情况 ----
招商银行：+12%
兴业银行：+5%
工商银行：+3%
双汇发展：-2%
红利低波100ETF：+8%
```

### 月度买入建议

```
月度预算：3000.00 元
本月是否强买：是
使用资金池：2000.00 元

目标权重再平衡买入计划：
  招商银行：当前 23.0%，目标 25.0%，偏离 +2.0% → 买入 100 股 @35.00 = 3500.00 元
  红利低波100ETF：当前 8.0%，目标 10.0%，偏离 +2.0% → 买入 200 股 @1.50 = 300.00 元
剩余资金：200.00 元
```

## 📝 使用示例代码

```python
from portfolio import PortfolioManager
from market_data import get_multiple_market_data
from portfolio_analysis import analyze_portfolio, print_dashboard
from visualization import generate_all_charts

# 加载组合
portfolio = PortfolioManager()
holdings = portfolio.get_holdings()
dividends = portfolio.get_dividends()

# 获取市场数据
snapshot = get_multiple_market_data(holdings['stock_name'].tolist())

# 分析
analysis = analyze_portfolio(holdings, snapshot, dividends)
print_dashboard(analysis)

# 生成图表
generate_all_charts(analysis, output_dir='output')
```

## 🗂️ 数据文件格式

### holdings.csv

```csv
stock_name,shares,cost_price,total_cost
招商银行,500,35.0,17500.0
兴业银行,1000,18.0,18000.0
```

### transactions.csv

```csv
date,type,stock_name,price,shares,cash_flow
2024-01-15,buy,招商银行,35.0,500,-17500.0
2024-02-20,buy,兴业银行,18.0,1000,-18000.0
```

### dividends.csv

```csv
date,stock_name,dividend_per_share
2024-06-15,招商银行,1.50
2024-07-20,兴业银行,0.80
```

## 🔄 数据刷新机制

- **A股数据**: 每天收盘后（15:00）第一次调用时刷新
- **ETF数据**: 与A股数据相同的刷新逻辑
- **缓存有效期**: 当天有效，次日自动刷新

## 📌 注意事项

1. 首次运行需要联网获取市场数据
2. 持仓数据保存在 `data/` 目录下，请定期备份
3. ETF数据使用 `ak.fund_etf_spot_em()` 接口
4. A股数据使用 `ak.stock_zh_a_spot_em()` 接口

## 📧 联系方式

如有问题或建议，请提交 Issue。

***

**版本**: v1.0\
**最后更新**: 2026年5月\
**作者**: Edward
