from backtest.data_loader import BacktestDataLoader
from backtest.strategy_adapter import run_backtest
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("="*60)
print("测试ETF兜底逻辑")
print("="*60)

loader = BacktestDataLoader('backtest_data')

stock_list = ["招商银行", "兴业银行", "工商银行", "双汇发展", "159307"]
start_date = "2024-01-01"
end_date = "2024-06-30"

print(f"\n正在加载历史数据...")
history_data = loader.load_price_history(stock_list, start_date, end_date)

if not history_data:
    print("ERROR: 历史数据加载失败")
    sys.exit(1)

print(f"成功加载 {len(history_data)} 只股票数据")

print("\n" + "="*60)
print("执行回测（完整周期）")
print("="*60)

result = run_backtest(history_data, monthly_budget=3000)

if not result:
    print("ERROR: 回测失败")
    sys.exit(1)

print(f"\n回测完成，共 {len(result)} 个交易日")

print("\n" + "="*60)
print("月度汇总")
print("="*60)

prev_month = None
monthly_results = []

for r in result:
    month = r['date'].month
    if month != prev_month:
        monthly_results.append({
            'date': r['date'],
            'cash': r['cash'],
            'holdings_value': r['holdings_value'],
            'total_value': r['total_value'],
            'holdings': r['holdings']
        })
        prev_month = month

print(f"{'日期':<12} {'现金':>10} {'持仓':>10} {'总市值':>10} {'持仓明细'}")
print("-" * 70)

for mr in monthly_results:
    date_str = mr['date'].strftime('%Y-%m-%d')
    holdings_str = ", ".join([f"{k}: {v}" for k, v in mr['holdings'].items()])
    print(f"{date_str:<12} {mr['cash']:>10.2f} {mr['holdings_value']:>10.2f} {mr['total_value']:>10.2f} {holdings_str}")

print("\n验证标准:")
print(f"1. 是否有股票买入: {'✅' if any('招商银行' in h['holdings'] or '兴业银行' in h['holdings'] for h in monthly_results) else '❌'}")
print(f"2. 是否有ETF买入: {'✅' if any('红利低波100ETF' in h['holdings'] for h in monthly_results) else '❌'}")
print(f"3. holdings是否同时包含股票和ETF: {'✅' if all(['红利低波100ETF' in h['holdings'] for h in monthly_results[-2:]]) and any(['招商银行' in h['holdings'] or '兴业银行' in h['holdings'] for h in monthly_results]) else '❌'}")
