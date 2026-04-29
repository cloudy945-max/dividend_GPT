import akshare as ak
import pandas as pd
import time

STOCK_NAME_MAP = {
    "招商银行": "招商银行",
    "兴业银行": "兴业银行",
    "工商银行": "工商银行",
    "双汇发展": "双汇发展",
    "红利ETF": "红利ETF"
}

_market_df_cache = None
_last_update_time = None
CACHE_TTL = 60

def safe_float(value):
    if value is None or pd.isna(value) or value == '-':
        return None
    return float(value)

ALLOWED_STOCKS = [
    "招商银行",
    "兴业银行",
    "工商银行",
    "双汇发展",
    "红利ETF"
]

def get_market_data(stock_name: str) -> dict:
    global _market_df_cache, _last_update_time
    
    if stock_name not in ALLOWED_STOCKS:
        raise ValueError(f"不支持的股票: {stock_name}")
    
    try:
        current_time = time.time()
        
        if _market_df_cache is None or _last_update_time is None or (current_time - _last_update_time) > CACHE_TTL:
            print("刷新市场数据缓存")
            _market_df_cache = ak.stock_zh_a_spot_em()
            _last_update_time = current_time
        
        if _market_df_cache is None or _market_df_cache.empty:
            raise ValueError("市场数据获取失败或为空")
        
        df = _market_df_cache
        
        if '名称' not in df.columns:
            raise ValueError("数据源缺少'名称'字段")
        
        name_series = df['名称'].astype(str)
        
        lookup_name = STOCK_NAME_MAP.get(stock_name, stock_name)
        
        match = df[name_series == lookup_name]
        
        if match.empty and lookup_name != stock_name:
            match = df[name_series == stock_name]
        
        if match.empty:
            match = df[name_series.str.contains(stock_name, na=False)]
        
        if match.empty:
            raise ValueError(f"未找到股票: {stock_name}")
        
        row = match.iloc[0]

        code = row.get('代码')
        
        price = safe_float(row.get('最新价'))
        if price is None:
            price = safe_float(row.get('收盘价'))
        if price is not None and price <= 0:
            price = None
        
        pb = safe_float(row.get('市净率'))
        
        return {
            "stock_name": stock_name,
            "price": price,
            "pb": pb
        }
    except ValueError:
        raise
    except Exception as e:
        print(f"获取数据失败: {e}")
        return None

def clear_cache():
    global _market_df_cache, _last_update_time
    _market_df_cache = None
    _last_update_time = None

def get_multiple_market_data(stock_list: list) -> list:
    results = []
    
    for stock_name in stock_list:
        try:
            result = get_market_data(stock_name)
            if result is not None:
                results.append(result)
            else:
                print(f"获取 {stock_name} 数据失败: 返回None")
                results.append({"stock_name": stock_name, "error": "返回None"})
        except ValueError as e:
            print(f"获取 {stock_name} 数据失败: {e}")
            results.append({"stock_name": stock_name, "error": str(e)})
        except Exception as e:
            print(f"获取 {stock_name} 数据失败: {e}")
            results.append({"stock_name": stock_name, "error": str(e)})
    
    success_count = sum(1 for r in results if "error" not in r and (r.get("price") is not None or r.get("pb") is not None))
    fail_count = len(results) - success_count
    
    print(f"成功获取: {success_count} 条, 失败: {fail_count} 条")
    
    return results

if __name__ == "__main__":
    test_list = ["招商银行", "兴业银行", "工商银行"]
    results = get_multiple_market_data(test_list)
    print("\n批量查询结果:")
    for result in results:
        print(result)