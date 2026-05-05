from backtest.data_loader import BacktestDataLoader
from backtest.strategy_adapter import debug_backtest_step
import sys

# 设置默认编码
sys.stdout.reconfigure(encoding='utf-8')

print("="*60)
print("测试回测核心逻辑")
print("="*60)

loader = BacktestDataLoader('backtest_data')

stock_list = ["招商银行", "兴业银行"]
start_date = "2023-01-01"
end_date = "2023-01-31"

print(f"\n正在加载历史数据...")
history_data = loader.load_price_history(stock_list, start_date, end_date)

if not history_data:
    print("ERROR: 历史数据加载失败")
    sys.exit(1)

print(f"成功加载 {len(history_data)} 只股票数据")

print("\n" + "="*60)
print("执行调试步骤")
print("="*60)

debug_backtest_step(history_data)

print("\n" + "="*60)
print("调试完成")
print("="*60)
