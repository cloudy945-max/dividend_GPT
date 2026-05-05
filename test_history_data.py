from backtest.data_loader import BacktestDataLoader
import sys

# 设置默认编码
sys.stdout.reconfigure(encoding='utf-8')

loader = BacktestDataLoader('backtest_data')

stock_list = ["招商银行", "兴业银行"]
start_date = "2023-01-01"
end_date = "2023-03-01"

print("Testing load_price_history...")
data = loader.load_price_history(stock_list, start_date, end_date)

print("\n===== 数据结构检查 =====")

if not data:
    print("ERROR: data 是空的")
else:
    print(f"股票数量: {len(data)}")

for stock, df in data.items():
    print(f"\n====== {stock} ======")
    
    if df is None:
        print("ERROR: DataFrame 是 None")
        continue
    
    print("行数:", len(df))
    print("列名:", list(df.columns))
    
    if len(df) > 0:
        print("前3行:")
        print(df.head(3))
    else:
        print("ERROR: DataFrame 是空的")
