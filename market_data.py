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
cash_pool = 0.0
MAX_CASH_POOL = 6000  # 最大资金池：2个月预算

def safe_float(value):
    if value is None or pd.isna(value) or value == '-':
        return None
    return float(value)

def calculate_buy_shares(price, budget):
    if price is None or price <= 0:
        return {
            "shares": 0,
            "cost": 0.0,
            "remaining_cash": float(budget) if budget is not None else 0.0
        }
    
    if budget is None or budget <= 0:
        return {
            "shares": 0,
            "cost": 0.0,
            "remaining_cash": 0.0
        }
    
    lot_price = price * 100
    max_lot = int(budget / lot_price)
    shares = max_lot * 100
    
    if shares < 100:
        shares = 0
        cost = 0.0
    else:
        cost = shares * price
    
    remaining_cash = budget - cost
    
    return {
        "shares": shares,
        "cost": float(cost),
        "remaining_cash": float(remaining_cash)
    }

ALLOWED_STOCKS = [
    "招商银行",
    "兴业银行",
    "工商银行",
    "双汇发展",
    "红利ETF"
]

ETF_NAME = "红利ETF"

def execute_single_buy(stock, budget):
    stock_name = stock.get("stock_name", "")
    price = stock.get("price")
    
    if price is None:
        return {
            "stock_name": stock_name,
            "action": "skip",
            "reason": "价格无效"
        }
    
    buy_result = calculate_buy_shares(price, budget)
    shares = buy_result.get("shares", 0)
    
    if shares == 0:
        return {
            "stock_name": stock_name,
            "action": "skip",
            "reason": "预算不足100股"
        }
    
    return {
        "stock_name": stock_name,
        "action": "buy",
        "shares": shares,
        "cost": buy_result.get("cost", 0.0),
        "remaining_cash": buy_result.get("remaining_cash", 0.0)
    }

def allocate_with_etf(plan, snapshot, monthly_budget, cash_pool_amount, strong_buy):
    actions_dict = {}
    
    # 计算可用于个股的总资金
    if strong_buy:
        stock_budget = monthly_budget + cash_pool_amount
    else:
        stock_budget = monthly_budget
    
    cash_left = stock_budget
    
    buy_list = plan.get("buy_list", [])
    target_stock_name = buy_list[0].get("stock_name") if buy_list else None
    
    etf_stock = None
    for stock in snapshot:
        if stock.get("stock_name") == ETF_NAME:
            etf_stock = stock
            break
    
    if etf_stock is None:
        etf_stock = {
            "stock_name": ETF_NAME,
            "price": None,
            "pb": None
        }
    
    target_stock = None
    if target_stock_name:
        for stock in snapshot:
            if stock.get("stock_name") == target_stock_name:
                target_stock = stock
                break
    
    force_buy_etf = False
    stock_spent = 0.0
    etf_spent = 0.0
    skip_etf_buy = False  # 是否跳过ETF购买
    
    if target_stock and cash_left > 0:
        buy_result = execute_single_buy(target_stock, cash_left)
        
        if buy_result.get("action") == "buy":
            stock_name = buy_result.get("stock_name")
            shares = buy_result.get("shares", 0)
            if stock_name in actions_dict:
                actions_dict[stock_name] += shares
            else:
                actions_dict[stock_name] = shares
            cash_left = max(0.0, buy_result.get("remaining_cash", 0.0))
            stock_spent = stock_budget - cash_left
        elif buy_result.get("action") == "skip":
            force_buy_etf = True
            cash_left = stock_budget
            stock_spent = 0.0
            # 如果是强买且个股买不起，不买ETF，保留资金
            if strong_buy:
                skip_etf_buy = True
    
    # 只有不跳过ETF购买时才执行
    if not skip_etf_buy:
        # 计算个股实际使用了多少月度预算
        monthly_spent = min(stock_spent, monthly_budget)
        monthly_remaining = max(0, monthly_budget - monthly_spent)
        
        # ETF只使用当月剩余资金
        if monthly_remaining > 800:
            if etf_stock and etf_stock.get("price") is not None:
                etf_buy = calculate_buy_shares(etf_stock.get("price"), monthly_remaining)
                if etf_buy.get("shares", 0) > 0:
                    shares = etf_buy.get("shares", 0)
                    if ETF_NAME in actions_dict:
                        actions_dict[ETF_NAME] += shares
                    else:
                        actions_dict[ETF_NAME] = shares
                    # 计算ETF花费
                    etf_cost = monthly_remaining - etf_buy["remaining_cash"]
                    etf_spent += etf_cost
                    # 现金计算：先减去ETF花费，再加回ETF剩余
                    cash_left -= monthly_remaining
                    cash_left += etf_buy["remaining_cash"]
    
    actions = [{"stock_name": name, "shares": shares} for name, shares in actions_dict.items()]
    
    # 现金流校验
    total_input = monthly_budget + (cash_pool_amount if strong_buy else 0)
    total_output = stock_spent + etf_spent + cash_left
    if abs(total_input - total_output) > 1:
        print(f"警告：现金流不平衡！输入: {total_input:.2f}, 输出: {total_output:.2f}")
    
    return {
        "actions": actions,
        "cash_left": float(cash_left),
        "stock_spent": float(stock_spent)
    }

def generate_execution_plan(plan, snapshot, monthly_budget=3000):
    global cash_pool
    
    # 获取目标买入标的
    buy_list = plan.get("buy_list", [])
    target_stock_name = buy_list[0].get("stock_name") if buy_list else None
    
    # 只针对目标买入标的检查强买信号
    strong_buy = False
    if target_stock_name:
        # 在snapshot中找到目标标的
        target_stock = None
        for stock in snapshot:
            if stock.get("stock_name") == target_stock_name:
                target_stock = stock
                break
        
        if target_stock:
            pb = target_stock.get("pb")
            if pb is not None:
                if target_stock_name == "招商银行" and pb <= 0.85:
                    strong_buy = True
                elif (target_stock_name == "兴业银行" or target_stock_name == "工商银行") and pb <= 0.75:
                    strong_buy = True
    
    # 保存初始资金池
    initial_cash_pool = cash_pool
    
    # 计算总可用资金（仅用于显示）
    total_budget = monthly_budget + cash_pool
    if strong_buy:
        stock_available = total_budget
    else:
        stock_available = monthly_budget
    
    # 第一次分配：正常分配
    allocation = allocate_with_etf(plan, snapshot, monthly_budget, cash_pool, strong_buy)
    
    # 检查是否需要处理资金池超出部分
    cash_left = allocation.get("cash_left", 0.0)
    total_actions = allocation.get("actions", [])
    
    if cash_left > MAX_CASH_POOL:
        # 超出部分
        excess_amount = cash_left - MAX_CASH_POOL
        
        # 创建只买ETF的计划
        etf_only_plan = {
            "buy_list": []
        }
        
        # 第二次分配：用超出部分只买ETF
        # 传入 monthly_budget = excess_amount, cash_pool_amount = 0, strong_buy = False
        etf_allocation = allocate_with_etf(etf_only_plan, snapshot, excess_amount, 0.0, False)
        
        # 合并ETF买入结果
        etf_actions = etf_allocation.get("actions", [])
        for etf_action in etf_actions:
            etf_name = etf_action.get("stock_name")
            etf_shares = etf_action.get("shares", 0)
            
            # 查找是否已有ETF买入
            found = False
            for i, action in enumerate(total_actions):
                if action.get("stock_name") == etf_name:
                    total_actions[i]["shares"] = action.get("shares", 0) + etf_shares
                    found = True
                    break
            if not found:
                total_actions.append(etf_action)
        
        # 更新剩余资金
        cash_left = MAX_CASH_POOL + etf_allocation.get("cash_left", 0.0)
    
    # 增强actions，增加price和cost
    enhanced_actions = []
    for action in total_actions:
        stock_name = action.get("stock_name")
        shares = action.get("shares", 0)
        
        price = None
        for stock in snapshot:
            if stock.get("stock_name") == stock_name:
                price = stock.get("price")
                break
        
        cost = None
        if price is not None and shares > 0:
            cost = price * shares
        
        enhanced_action = {
            "stock_name": stock_name,
            "shares": shares,
            "price": price,
            "cost": cost
        }
        enhanced_actions.append(enhanced_action)
    
    # 计算个股总花费
    stock_spent = allocation.get("stock_spent", 0.0)
    
    # 计算使用了多少资金池
    used_cash_pool = 0.0
    if strong_buy:
        # 强买时，个股实际使用资金超过月度预算的部分，就是使用的资金池
        if stock_spent > monthly_budget:
            used_cash_pool = stock_spent - monthly_budget
    
    # 更新资金池
    # 确保不超过最大资金池
    cash_pool = min(cash_left, MAX_CASH_POOL)
    remaining_cash_pool = cash_pool
    
    result = {
        "month_budget": monthly_budget,
        "cash_pool": cash_pool,
        "strong_buy": strong_buy,
        "actions": enhanced_actions,
        "cash_left": cash_left,
        "used_cash_pool": used_cash_pool,
        "remaining_cash_pool": remaining_cash_pool,
        "is_strong_buy": strong_buy
    }
    
    print(f"\n月度预算: {monthly_budget} 元")
    print(f"本月是否强买: {'是' if strong_buy else '否'}")
    print(f"使用资金池: {used_cash_pool:.2f} 元")
    print(f"当前资金池余额: {cash_pool:.2f} 元")
    print(f"资金池上限: {MAX_CASH_POOL:.2f} 元")
    print(f"个股可用资金: {stock_available:.2f} 元")
    print(f"ETF可用资金: 仅使用当月剩余")
    if extra_etf_budget > 0:
        print(f"资金池超支部分: {extra_etf_budget:.2f} 元")
    print("执行计划:")
    for action in result["actions"]:
        stock_name = action.get("stock_name")
        shares = action.get("shares", 0)
        price = action.get("price")
        cost = action.get("cost")
        
        if price is not None and cost is not None:
            print(f"  买入 {stock_name} {shares}股 @{price} = {cost}元")
        else:
            print(f"  买入 {stock_name} {shares}股")
    print(f"剩余资金: {result['cash_left']:.2f} 元")
    
    return result

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