from backtest.data_loader import BacktestDataLoader
from backtest.strategy_adapter import run_backtest
import sys

sys.stdout.reconfigure(encoding='utf-8')

print("="*60)
print("测试完整资金演化系统")
print("="*60)

loader = BacktestDataLoader('backtest_data')

stock_list = ["招商银行", "兴业银行", "159307"]
start_date = "2024-01-01"
end_date = "2024-06-30"

print(f"\n正在加载历史数据（使用缓存）...")
history_data = loader.load_price_history(stock_list, start_date, end_date)

if not history_data:
    print("ERROR: 历史数据加载失败")
    sys.exit(1)

print(f"成功加载 {len(history_data)} 只股票数据")
print(f"股票列表: {list(history_data.keys())}")

print("\n检查历史数据:")
for stock, df in history_data.items():
    if df is not None and not df.empty:
        print(f"  {stock}: rows={len(df)}")

print("\n" + "="*60)
print("执行回测（只显示前10天）")
print("="*60)

result = run_backtest(history_data, monthly_budget=3000)

print("\n回测完成，共", len(result), "个交易日")
