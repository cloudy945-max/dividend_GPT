import sys
sys.stdout.reconfigure(encoding='utf-8')
import akshare as ak

print("Testing different ETF interfaces...")

print("\n1. fund_etf_hist_em:")
try:
    df = ak.fund_etf_hist_em(symbol="159307")
    print(f"   Shape: {df.shape}")
    print(f"   Columns: {df.columns.tolist()}")
    if not df.empty:
        print(f"   Date range: {df.iloc[0]['日期']} to {df.iloc[-1]['日期']}")
except Exception as e:
    print(f"   Error: {e}")

print("\n2. fund_etf_hist_em_sina:")
try:
    df = ak.fund_etf_hist_em_sina(symbol="159307")
    print(f"   Shape: {df.shape}")
    print(f"   Columns: {df.columns.tolist()}")
except Exception as e:
    print(f"   Error: {e}")

print("\n3. stock_zh_etf_hist:")
try:
    df = ak.stock_zh_etf_hist(symbol="159307", period="daily", start_date="20230101", end_date="20230131")
    print(f"   Shape: {df.shape}")
    print(f"   Columns: {df.columns.tolist()}")
    if not df.empty:
        print(f"   First rows:")
        print(df.head())
except Exception as e:
    print(f"   Error: {e}")
