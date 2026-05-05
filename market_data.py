import akshare as ak
import pandas as pd
import time

# ========== 统一ETF标识：使用 stock_code + stock_name ==========

# A股股票使用中文名作为code（内部计算和展示统一）
STOCK_NAME_MAP = {
    "招商银行": "招商银行",
    "兴业银行": "兴业银行",
    "工商银行": "工商银行",
    "双汇发展": "双汇发展"
}

# ETF使用代码作为code，中文名作为展示名
ETF_INFO = {
    "159307": "红利低波100ETF"
}

# 统一标识：code -> name 映射
CODE_TO_NAME = {
    "招商银行": "招商银行",
    "兴业银行": "兴业银行",
    "工商银行": "工商银行",
    "双汇发展": "双汇发展",
    "159307": "红利低波100ETF"
}

# 统一标识：name -> code 映射
NAME_TO_CODE = {
    "招商银行": "招商银行",
    "兴业银行": "兴业银行",
    "工商银行": "工商银行",
    "双汇发展": "双汇发展",
    "红利低波100ETF": "159307",
    "红利低波": "159307"
}

# ALLOWED_STOCKS 使用 code（统一标识）
ALLOWED_STOCKS = [
    "招商银行",
    "兴业银行",
    "工商银行",
    "双汇发展",
    "159307"  # ETF使用代码
]

# TARGET_WEIGHTS 使用 stock_code 作为key
TARGET_WEIGHTS = {
    "兴业银行": 0.30,
    "招商银行": 0.25,
    "工商银行": 0.20,
    "双汇发展": 0.15,
    "159307": 0.10
}

# 再平衡参数
MIN_DEVIATION_TO_BUY = 0.02  # 偏离度阈值：低于此值才允许ETF补仓

_market_df_cache = None
_etf_df_cache = None
_last_update_date = None  # 记录缓存更新日期，格式：YYYY-MM-DD
CLOSE_TIME = 15  # 收盘时间：下午3点

cash_pool = 0.0
# MAX_CASH_POOL = 6000  # 最大资金池：2个月预算（已废弃，改用动态计算）
tracking_months_no_stock = 0  # 连续无股票成交月份计数器
MONTHS_TO_ALLOW_ETF = 6  # MODIFIED: 连续6个月无股票成交后允许ETF兜底


def need_refresh():
    """判断是否需要刷新数据"""
    global _last_update_date
    
    now = pd.Timestamp.now()
    today = now.strftime('%Y-%m-%d')
    current_hour = now.hour
    
    if _last_update_date is None:
        return True
    
    if current_hour >= CLOSE_TIME and _last_update_date != today:
        return True
    
    return False


def clear_cache():
    """手动清除缓存"""
    global _market_df_cache, _etf_df_cache, _last_update_date
    _market_df_cache = None
    _etf_df_cache = None
    _last_update_date = None


def set_market_cache(df):
    """设置A股市场数据缓存"""
    global _market_df_cache, _last_update_date
    _market_df_cache = df
    _last_update_date = pd.Timestamp.now().strftime('%Y-%m-%d')


def set_etf_cache(df):
    """设置ETF数据缓存"""
    global _etf_df_cache, _last_update_date
    _etf_df_cache = df
    _last_update_date = pd.Timestamp.now().strftime('%Y-%m-%d')


def get_stock_name(stock_code):
    """通过code获取统一的展示名称"""
    return CODE_TO_NAME.get(stock_code, stock_code)


def get_stock_code(stock_identifier):
    """通过名称或代码获取统一的code"""
    return NAME_TO_CODE.get(stock_identifier, stock_identifier)


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


def execute_single_buy(stock, budget):
    stock_code = stock.get("stock_code", "")
    stock_name = stock.get("stock_name", stock_code)
    price = stock.get("price")

    if price is None:
        return {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "action": "skip",
            "reason": "价格无效"
        }

    buy_result = calculate_buy_shares(price, budget)
    shares = buy_result.get("shares", 0)

    if shares == 0:
        return {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "action": "skip",
            "reason": "预算不足100股"
        }

    return {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "action": "buy",
        "shares": shares,
        "cost": buy_result.get("cost", 0.0),
        "remaining_cash": buy_result.get("remaining_cash", 0.0)
    }


def allocate_with_etf(plan, snapshot, monthly_budget, cash_pool_amount, strong_buy):
    # MODIFIED: 动态计算MAX_CASH_POOL
    MAX_CASH_POOL = monthly_budget * 4
    
    actions_dict = {}

    if strong_buy:
        stock_budget = monthly_budget + cash_pool_amount
    else:
        stock_budget = monthly_budget

    cash_left = stock_budget

    buy_list = plan.get("buy_list", [])
    target_stock_code = buy_list[0].get("stock_code") if buy_list else None
    
    print(f"[DEBUG] allocate_with_etf: buy_list={buy_list}, target_stock_code={target_stock_code}")

    etf_stock = None
    for stock in snapshot:
        if stock.get("stock_code") == "159307":
            etf_stock = stock
            break

    if etf_stock is None:
        etf_stock = {
            "stock_code": "159307",
            "stock_name": "红利低波100ETF",
            "price": None,
            "pb": None
        }

    target_stock = None
    if target_stock_code:
        for stock in snapshot:
            if stock.get("stock_code") == target_stock_code:
                target_stock = stock
                break

    force_buy_etf = False
    stock_spent = 0.0
    etf_spent = 0.0
    skip_etf_buy = False

    if target_stock and cash_left > 0:
        buy_result = execute_single_buy(target_stock, cash_left)

        if buy_result.get("action") == "buy":
            stock_code = buy_result.get("stock_code")
            shares = buy_result.get("shares", 0)
            if stock_code in actions_dict:
                actions_dict[stock_code] += shares
            else:
                actions_dict[stock_code] = shares
            cash_left = max(0.0, buy_result.get("remaining_cash", 0.0))
            stock_spent = stock_budget - cash_left
        elif buy_result.get("action") == "skip":
            force_buy_etf = True
            cash_left = stock_budget
            stock_spent = 0.0
            if strong_buy:
                skip_etf_buy = True

    if not skip_etf_buy:
        monthly_spent = min(stock_spent, monthly_budget)
        monthly_remaining = max(0, monthly_budget - monthly_spent)
        
        print(f"[DEBUG] monthly_spent={monthly_spent}, monthly_remaining={monthly_remaining}")

        if monthly_remaining > 800:
            allow_etf = False
            
            # MODIFIED: 增加ETF决策调试输出
            print("====== ETF 决策调试 ======")
            print(f"cash_pool: {cash_pool_amount}")
            print(f"monthly_budget: {monthly_budget}")
            print(f"tracking_months_no_stock: {tracking_months_no_stock}")
            print(f"MONTHS_TO_ALLOW_ETF: {MONTHS_TO_ALLOW_ETF}")
            print(f"MAX_CASH_POOL: {MAX_CASH_POOL}")
            print(f"条件A(cash_pool>=MAX): {cash_pool_amount >= MAX_CASH_POOL}")
            print(f"条件B(月数>=阈值): {tracking_months_no_stock >= MONTHS_TO_ALLOW_ETF}")
            
            # MODIFIED: 只有在buy_list为空时才允许ETF
            if buy_list:
                allow_etf = False
                print("  禁止ETF：有候选股票待买")
            elif stock_spent > 0:
                allow_etf = True
                print("  允许ETF：已有股票买入")
            else:
                if cash_pool_amount >= MAX_CASH_POOL:
                    allow_etf = True
                    print(f"  允许ETF：cash_pool >= MAX_CASH_POOL ({cash_pool_amount} >= {MAX_CASH_POOL})")
                elif tracking_months_no_stock >= MONTHS_TO_ALLOW_ETF:
                    allow_etf = True
                    print(f"  允许ETF：连续{tracking_months_no_stock}个月无股票成交 >= {MONTHS_TO_ALLOW_ETF}个月")
                else:
                    print(f"  不允许ETF：条件未满足")
            
            print(f"[DEBUG] allow_etf={allow_etf}")
            
            if allow_etf:
                if etf_stock and etf_stock.get("price") is not None:
                    # MODIFIED: ETF买入使用资金 = min(monthly_budget, cash_pool)
                    etf_budget = min(monthly_remaining, monthly_budget)
                    etf_buy = calculate_buy_shares(etf_stock.get("price"), etf_budget)
                    if etf_buy.get("shares", 0) > 0:
                        shares = etf_buy.get("shares", 0)
                        if "159307" in actions_dict:
                            actions_dict["159307"] += shares
                        else:
                            actions_dict["159307"] = shares
                        etf_cost = etf_budget - etf_buy["remaining_cash"]
                        etf_spent += etf_cost
                        cash_left -= etf_budget
                        cash_left += etf_buy["remaining_cash"]
            
            # TODO: 如果未来出现 strong_buy 机会，考虑卖出ETF换仓股票（ETF -> 股票切换机制）

    actions = []
    for stock_code, shares in actions_dict.items():
        actions.append({
            "stock_code": stock_code,
            "stock_name": get_stock_name(stock_code),
            "shares": shares
        })

    total_input = monthly_budget + (cash_pool_amount if strong_buy else 0)
    total_output = stock_spent + etf_spent + cash_left
    if abs(total_input - total_output) > 1:
        print(f"警告：现金流不平衡！输入: {total_input:.2f}, 输出: {total_output:.2f}")

    print(f"[DEBUG] allocate_with_etf returning {len(actions)} actions: {[a.get('stock_code') for a in actions]}")
    
    return {
        "actions": actions,
        "cash_left": float(cash_left),
        "stock_spent": float(stock_spent)
    }


def calculate_rebalance_buys(snapshot, current_holdings, total_budget, target_weights, strong_buy=None):
    """
    基于贪心补缺口算法的再平衡买入函数

    步骤：
    1. 计算每个资产的"缺口"：gap = target_value - current_value
    2. 过滤：只保留 gap > 0 的资产
    3. 按 gap 从大到小排序（最缺的优先）
    4. 遍历排序后的资产，贪心买入尽可能多的整手（100股）
    5. 强买标的优先级 +1

    Args:
        snapshot: 市场数据列表
        current_holdings: 当前持仓市值字典（key为stock_code）
        total_budget: 本次总预算
        target_weights: 目标权重字典（key为stock_code）
        strong_buy: 强买标的code（可选）

    Returns:
        {"buys": actions, "cash_left": 剩余现金}
    """
    price_map = {}
    for s in snapshot:
        stock_code = s.get("stock_code")
        price = s.get("price")
        if stock_code and price is not None and price > 0:
            price_map[stock_code] = price

    skipped_stocks = []
    for s in snapshot:
        stock_code = s.get("stock_code")
        if stock_code not in price_map:
            skipped_stocks.append(stock_code)

    if skipped_stocks:
        print(f"  [警告] 以下标的因价格无效未参与计算: {', '.join(skipped_stocks)}")

    current_holdings = dict(current_holdings) if current_holdings else {}
    for stock_code in target_weights.keys():
        if stock_code not in current_holdings:
            current_holdings[stock_code] = 0.0

    current_total = sum(current_holdings.values())
    plan_total = current_total + total_budget

    if plan_total <= 0:
        return {"buys": [], "cash_left": total_budget}

    gaps = []
    for stock_code in target_weights.keys():
        if stock_code == "159307":
            continue

        price = price_map.get(stock_code)
        if price is None or price <= 0:
            continue

        current_value = current_holdings.get(stock_code, 0.0)
        target_weight = target_weights[stock_code]
        target_value = plan_total * target_weight
        gap = target_value - current_value

        if gap > 0:
            priority = 1.5 if stock_code == strong_buy else 1.0
            effective_gap = gap * priority
            gaps.append({
                "stock_code": stock_code,
                "gap": gap,
                "effective_gap": effective_gap,
                "price": price,
                "target_weight": target_weight,
                "current_value": current_value
            })

    gaps.sort(key=lambda x: (x["current_value"] == 0, x["gap"]), reverse=True)

    buys = []
    cash_pool = total_budget

    for item in gaps:
        stock_code = item["stock_code"]
        price = item["price"]

        while cash_pool >= price * 100:
            shares = 100
            cost = shares * price

            buys.append({
                "stock_code": stock_code,
                "stock_name": get_stock_name(stock_code),
                "shares": shares,
                "cost": cost,
                "price": price,
                "gap_before": item["gap"]
            })

            cash_pool -= cost
            current_holdings[stock_code] = current_holdings.get(stock_code, 0.0) + cost
            item["gap"] -= cost

            if item["gap"] <= 0:
                break

    etf_allowed = True
    for stock_code in target_weights.keys():
        if stock_code == "159307":
            continue
        current_value = current_holdings.get(stock_code, 0.0)
        target_weight = target_weights[stock_code]
        target_value = plan_total * target_weight
        deviation = target_weight - (current_value / plan_total if plan_total > 0 else 0)
        if deviation >= MIN_DEVIATION_TO_BUY:
            etf_allowed = False
            break

    if etf_allowed:
        etf_price = price_map.get("159307")
        if etf_price is not None and etf_price > 0:
            min_lot_cost = etf_price * 100
            if cash_pool >= min_lot_cost:
                max_lots = int(cash_pool / min_lot_cost)
                shares = max_lots * 100
                cost = shares * etf_price

                buys.append({
                    "stock_code": "159307",
                    "stock_name": get_stock_name("159307"),
                    "shares": shares,
                    "cost": cost,
                    "price": etf_price
                })

                cash_pool -= cost

    return {
        "buys": buys,
        "cash_left": cash_pool
    }


def generate_execution_plan(plan, snapshot, monthly_budget=3000, current_holdings=None):
    """
    生成执行计划

    Args:
        plan: 原有计划字典
        snapshot: 市场数据列表
        monthly_budget: 月度预算
        current_holdings: 当前持仓市值字典（key为stock_code）
    """
    global cash_pool, tracking_months_no_stock

    strong_buy_stock = None
    strong_buy_pb = None

    for stock in snapshot:
        stock_code = stock.get("stock_code")
        pb = stock.get("pb")

        if pb is None:
            continue

        is_strong_buy = False
        if stock_code == "招商银行" and pb <= 0.85:
            is_strong_buy = True
        elif stock_code in ["兴业银行", "工商银行"] and pb <= 0.75:
            is_strong_buy = True

        if is_strong_buy:
            if strong_buy_stock is None or pb < strong_buy_pb:
                strong_buy_stock = stock_code
                strong_buy_pb = pb

    initial_cash_pool = cash_pool

    total_budget = monthly_budget
    strong_buy_flag = False
    if strong_buy_stock:
        total_budget = monthly_budget + cash_pool
        strong_buy_flag = True

    has_candidate = bool(plan.get("buy_list"))

    stock_available = total_budget

    strong_buy_buys = []
    if strong_buy_stock:
        for stock in snapshot:
            if stock.get("stock_code") == strong_buy_stock:
                price = stock.get("price")
                if price and price > 0:
                    max_lot = int(total_budget / (price * 100))
                    if max_lot > 0:
                        shares = max_lot * 100
                        cost = shares * price
                        strong_buy_buys.append({
                            "stock_code": strong_buy_stock,
                            "stock_name": get_stock_name(strong_buy_stock),
                            "shares": shares,
                            "cost": cost,
                            "price": price,
                            "is_strong_buy": True
                        })
                        total_budget -= cost
                break

    use_rebalance = current_holdings is not None and isinstance(current_holdings, dict) and len(current_holdings) > 0

    MAX_CASH_POOL = monthly_budget * 4  # MODIFIED: 动态计算

    if use_rebalance and any(current_holdings.get(k, 0) > 0 for k in current_holdings):
        rebalance_result = calculate_rebalance_buys(
            snapshot=snapshot,
            current_holdings=current_holdings,
            total_budget=total_budget,
            target_weights=TARGET_WEIGHTS,
            strong_buy=strong_buy_stock
        )
        total_buys = rebalance_result["buys"]
        cash_left = rebalance_result["cash_left"]
        stock_spent = total_budget - cash_left
    else:
        allocation = allocate_with_etf(plan, snapshot, monthly_budget, cash_pool, strong_buy_flag)
        cash_left = allocation.get("cash_left", 0.0)
        total_buys = allocation.get("actions", [])
        stock_spent = allocation.get("stock_spent", 0.0)
        
        print(f"[DEBUG] total_buys from allocate_with_etf: {len(total_buys)} actions")

    overflow_buys = []
    if cash_left > MAX_CASH_POOL:
        excess_amount = cash_left - MAX_CASH_POOL

        etf_only_plan = {"buy_list": []}
        etf_allocation = allocate_with_etf(etf_only_plan, snapshot, excess_amount, 0.0, False)
        etf_actions = etf_allocation.get("actions", [])

        for etf_action in etf_actions:
            etf_code = etf_action.get("stock_code")
            etf_shares = etf_action.get("shares", 0)
            overflow_buys.append({
                "stock_code": etf_code,
                "stock_name": etf_action.get("stock_name", get_stock_name(etf_code)),
                "shares": etf_shares,
                "is_overflow": True
            })

        cash_left = MAX_CASH_POOL + etf_allocation.get("cash_left", 0.0)

    actions_dict = {}
    current_total = sum(current_holdings.values()) if current_holdings else 0.0
    plan_total = current_total + total_budget

    for buy in strong_buy_buys:
        stock_code = buy.get("stock_code")
        stock_name = get_stock_name(stock_code)
        shares = buy.get("shares", 0)
        cost = buy.get("cost", 0)

        if stock_name in actions_dict:
            actions_dict[stock_name]["shares"] += shares
            actions_dict[stock_name]["cost"] += cost
        else:
            actions_dict[stock_name] = {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "shares": shares,
                "cost": cost,
                "is_strong_buy": True
            }

    for buy in total_buys:
        stock_code = buy.get("stock_code")
        stock_name = get_stock_name(stock_code)
        shares = buy.get("shares", 0)
        cost = buy.get("cost")

        if stock_name in actions_dict:
            actions_dict[stock_name]["shares"] += shares
            actions_dict[stock_name]["cost"] += cost if cost else 0
        else:
            actions_dict[stock_name] = {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "shares": shares,
                "cost": cost if cost else 0
            }

    for action in overflow_buys:
        stock_code = action.get("stock_code")
        stock_name = get_stock_name(stock_code)
        shares = action.get("shares", 0)
        cost = action.get("cost")

        if stock_name in actions_dict:
            actions_dict[stock_name]["shares"] += shares
            actions_dict[stock_name]["cost"] += cost if cost else 0
            actions_dict[stock_name]["is_overflow"] = True
        else:
            actions_dict[stock_name] = {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "shares": shares,
                "cost": cost if cost else 0,
                "is_overflow": True
            }

    enhanced_actions = []
    for stock_name, action_data in actions_dict.items():
        stock_code = action_data.get("stock_code")
        shares = action_data.get("shares", 0)
        cost = action_data.get("cost", 0)

        price = None
        for stock in snapshot:
            if stock.get("stock_code") == stock_code:
                price = stock.get("price")
                break

        if price is not None and shares > 0 and cost == 0:
            cost = price * shares

        current_value = current_holdings.get(stock_code, 0.0) if current_holdings else 0.0
        current_weight = current_value / plan_total if plan_total > 0 else 0.0
        target_weight = TARGET_WEIGHTS.get(stock_code, 0.0)
        deviation = target_weight - current_weight
        is_overflow = action_data.get("is_overflow", False)

        enhanced_action = {
            "stock_code": stock_code,
            "stock_name": stock_name,
            "shares": shares,
            "price": price,
            "cost": cost,
            "current_weight": current_weight,
            "target_weight": target_weight,
            "deviation": deviation
        }
        if is_overflow:
            enhanced_action["is_overflow"] = True

        if shares > 0:
            enhanced_actions.append(enhanced_action)

    used_cash_pool = max(0, total_budget - monthly_budget)

    total_spent = total_budget - cash_left
    if total_spent > 0:
        cash_pool = max(0, initial_cash_pool - used_cash_pool)
    else:
        cash_pool = min(initial_cash_pool + monthly_budget, MAX_CASH_POOL)
    remaining_cash_pool = cash_pool

    has_stock_action = False
    for action in enhanced_actions:
        if action.get("stock_code") != "159307":
            has_stock_action = True
            break

    if has_stock_action:
        tracking_months_no_stock = 0
    else:
        tracking_months_no_stock += 1

    can_afford_stock = False
    for stock in snapshot:
        stock_code = stock.get("stock_code")
        if stock_code == "159307":
            continue
        price = stock.get("price")
        if price is not None and price > 0:
            if monthly_budget >= price * 100:
                can_afford_stock = True
                break

    if len(enhanced_actions) == 0:
        # MODIFIED: 动态计算MAX_CASH_POOL
        MAX_CASH_POOL = monthly_budget * 4
        
        print("触发ETF检查:")
        print(f"  cash_pool: {cash_pool}")
        print(f"  tracking_months_no_stock: {tracking_months_no_stock}")
        print(f"  MONTHS_TO_ALLOW_ETF: {MONTHS_TO_ALLOW_ETF}")
        print(f"  MAX_CASH_POOL: {MAX_CASH_POOL}")
        
        allow_etf = False
        
        condition_a = initial_cash_pool >= MAX_CASH_POOL
        condition_b = tracking_months_no_stock >= MONTHS_TO_ALLOW_ETF
        
        if condition_a:
            print(f"  条件A满足: cash_pool >= MAX_CASH_POOL ({initial_cash_pool} >= {MAX_CASH_POOL})")
        if condition_b:
            print(f"  条件B满足: 连续{tracking_months_no_stock}个月无股票成交 >= {MONTHS_TO_ALLOW_ETF}个月")
        
        if condition_a or condition_b:
            allow_etf = True
        
        print(f"  是否允许ETF: {allow_etf}")
        
        if allow_etf:
            etf_stock = None
            for stock in snapshot:
                if stock.get("stock_code") == "159307":
                    etf_stock = stock
                    break

            if etf_stock and etf_stock.get("price") is not None:
                etf_name = get_stock_name("159307")
                etf_budget = min(cash_pool, monthly_budget)
                fallback_buy = calculate_buy_shares(etf_stock["price"], etf_budget)

                if fallback_buy["shares"] > 0:
                    enhanced_actions.append({
                        "stock_code": "159307",
                        "stock_name": etf_name,
                        "shares": fallback_buy["shares"],
                        "price": etf_stock["price"],
                        "cost": fallback_buy["shares"] * etf_stock["price"],
                        "current_weight": 0.0,
                        "target_weight": TARGET_WEIGHTS.get("159307", 0.0),
                        "deviation": TARGET_WEIGHTS.get("159307", 0.0),
                        "is_fallback_etf": True
                    })
                    cash_left = cash_pool - (fallback_buy["shares"] * etf_stock["price"])
                    tracking_months_no_stock = 0
        else:
            print("所有股票均无法买入（不足100股），保留现金")

    result = {
        "month_budget": monthly_budget,
        "cash_pool": cash_pool,
        "strong_buy": strong_buy_flag,
        "actions": enhanced_actions,
        "cash_left": cash_left,
        "used_cash_pool": used_cash_pool,
        "remaining_cash_pool": remaining_cash_pool,
        "is_strong_buy": strong_buy_flag
    }

    print(f"\n月度预算: {monthly_budget} 元")
    print(f"本月是否强买: {'是' if strong_buy_flag else '否'}")
    if strong_buy_flag and strong_buy_stock:
        print(f"强买标的: {get_stock_name(strong_buy_stock)}")
    print(f"使用资金池: {used_cash_pool:.2f} 元")
    print(f"当前资金池余额: {cash_pool:.2f} 元")
    print(f"资金池上限: {MAX_CASH_POOL:.2f} 元")
    print(f"个股可用资金: {stock_available:.2f} 元")

    if use_rebalance:
        print("\n目标权重再平衡买入计划：")
        for action in enhanced_actions:
            stock_code = action.get("stock_code")
            stock_name = action.get("stock_name", get_stock_name(stock_code))
            shares = action.get("shares", 0)
            price = action.get("price")
            cost = action.get("cost")
            current_weight = action.get("current_weight", 0.0)
            target_weight = action.get("target_weight", 0.0)
            deviation = action.get("deviation", 0.0)
            is_overflow = action.get("is_overflow", False)

            overflow_note = " (资金池溢出买入)" if is_overflow else ""

            dev_sign = "+" if deviation >= 0 else ""

            if price is not None and cost is not None:
                print(f"  {stock_name}: 当前 {current_weight*100:.1f}%, 目标 {target_weight*100:.1f}%, 偏离 {dev_sign}{deviation*100:.1f}% → 买入 {shares} 股 @{price:.2f} = {cost:.2f} 元{overflow_note}")
            else:
                print(f"  {stock_name}: 当前 {current_weight*100:.1f}%, 目标 {target_weight*100:.1f}%, 偏离 {dev_sign}{deviation*100:.1f}% → 买入 {shares} 股{overflow_note}")
    else:
        print("ETF可用资金: 仅使用当月剩余")
        print("执行计划:")
        for action in enhanced_actions:
            stock_code = action.get("stock_code")
            stock_name = action.get("stock_name", get_stock_name(stock_code))
            shares = action.get("shares", 0)
            price = action.get("price")
            cost = action.get("cost")
            is_overflow = action.get("is_overflow", False)

            overflow_note = " (资金池溢出买入)" if is_overflow else ""

            if price is not None and cost is not None:
                print(f"  买入 {stock_name} {shares} 股 @{price:.2f} = {cost:.2f} 元{overflow_note}")
            else:
                print(f"  买入 {stock_name} {shares} 股{overflow_note}")

    print(f"剩余资金: {cash_left:.2f} 元")

    return result


def get_market_data(stock_code: str) -> dict:
    """
    获取单个标的的市场数据

    Returns:
        {
            "stock_code": "159307",
            "stock_name": "红利低波100ETF",
            "price": price,
            "pb": pb
        }
    """
    global _market_df_cache, _etf_df_cache

    stock_code = get_stock_code(stock_code)

    if stock_code not in ALLOWED_STOCKS:
        raise ValueError(f"不支持的股票: {stock_code}")

    try:
        if stock_code == "159307":
            if _etf_df_cache is None or need_refresh():
                print(f"刷新ETF数据缓存: {stock_code}")
                _etf_df_cache = ak.fund_etf_spot_em()
                set_etf_cache(_etf_df_cache)
            else:
                print(f"使用缓存的ETF数据: {stock_code}")

            df = _etf_df_cache

            if df is None or df.empty:
                raise ValueError("ETF数据获取失败或为空")

            match = None
            for code_col in ['代码', '基金代码']:
                if code_col in df.columns:
                    code_series = df[code_col].astype(str)
                    match = df[code_series == stock_code]
                    if not match.empty:
                        break

            if match is None or match.empty:
                if '名称' in df.columns:
                    name_series = df['名称'].astype(str)
                    match = df[name_series.str.contains('红利低波', na=False)]

            if match is None or match.empty:
                raise ValueError(f"未找到ETF: {stock_code}")

            row = match.iloc[0]

            price = safe_float(row.get('最新价'))
            if price is None:
                price = safe_float(row.get('收盘价'))
            if price is not None and price <= 0:
                price = None

            return {
                "stock_code": stock_code,
                "stock_name": get_stock_name(stock_code),
                "price": price,
                "pb": None
            }
        else:
            if _market_df_cache is None or need_refresh():
                print("刷新市场数据缓存")
                _market_df_cache = ak.stock_zh_a_spot_em()
                set_market_cache(_market_df_cache)

            if _market_df_cache is None or _market_df_cache.empty:
                raise ValueError("市场数据获取失败或为空")

            df = _market_df_cache

            if '名称' not in df.columns:
                raise ValueError("数据源缺少'名称'字段")

            name_series = df['名称'].astype(str)

            lookup_name = STOCK_NAME_MAP.get(stock_code, stock_code)

            match = df[name_series == lookup_name]

            if match.empty and lookup_name != stock_code:
                match = df[name_series == stock_code]

            if match.empty:
                match = df[name_series.str.contains(stock_code, na=False)]

            if match.empty:
                raise ValueError(f"未找到股票: {stock_code}")

            row = match.iloc[0]

            price = safe_float(row.get('最新价'))
            if price is None:
                price = safe_float(row.get('收盘价'))
            if price is not None and price <= 0:
                price = None

            pb = safe_float(row.get('市净率'))

            return {
                "stock_code": stock_code,
                "stock_name": get_stock_name(stock_code),
                "price": price,
                "pb": pb
            }
    except ValueError:
        raise
    except Exception as e:
        print(f"获取数据失败: {e}")
        return None


def get_multiple_market_data(stock_list: list) -> list:
    """
    批量获取市场数据

    Args:
        stock_list: stock_code 列表

    Returns:
        市场数据列表，每个元素包含 stock_code, stock_name, price, pb
    """
    results = []

    for stock_code in stock_list:
        try:
            result = get_market_data(stock_code)
            if result is not None:
                results.append(result)
            else:
                print(f"获取 {stock_code} 数据失败: 返回None")
                results.append({"stock_code": stock_code, "stock_name": get_stock_name(stock_code), "error": "返回None"})
        except ValueError as e:
            print(f"获取 {stock_code} 数据失败: {e}")
            results.append({"stock_code": stock_code, "stock_name": get_stock_name(stock_code), "error": str(e)})
        except Exception as e:
            print(f"获取 {stock_code} 数据失败: {e}")
            results.append({"stock_code": stock_code, "stock_name": get_stock_name(stock_code), "error": str(e)})

    success_count = sum(1 for r in results if "error" not in r and (r.get("price") is not None or r.get("pb") is not None))
    fail_count = len(results) - success_count

    print(f"成功获取: {success_count} 条, 失败: {fail_count} 条")

    return results


if __name__ == "__main__":
    print("="*50)
    print("测试ETF查询")
    print("="*50)
    try:
        etf_result = get_market_data("159307")
        print(f"ETF查询结果:")
        print(f"  stock_code: {etf_result['stock_code']}")
        print(f"  stock_name: {etf_result['stock_name']}")
        print(f"  最新价: {etf_result['price']}")
        print(f"  PB: {etf_result['pb']}")
    except Exception as e:
        print(f"ETF查询失败: {e}")

    print("\n" + "="*50)
    print("测试A股查询")
    print("="*50)
    test_list = ["招商银行", "兴业银行", "工商银行"]
    results = get_multiple_market_data(test_list)
    print("\n批量查询结果:")
    for result in results:
        print(f"  {result['stock_code']} ({result['stock_name']}): 价格={result.get('price')}, PB={result.get('pb')}")
