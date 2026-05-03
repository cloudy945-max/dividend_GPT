import pandas as pd
import os


def calculate_annual_dividend(holdings, dividends):
    """
    计算年分红现金流（真实年化现金流）
    
    Args:
        holdings: 持仓DataFrame，包含列：stock_name, shares, cost_price, total_cost
        dividends: 分红DataFrame，包含列：date, stock_name, dividend_per_share
    
    Returns:
        float: 年分红现金流
    """
    from datetime import datetime, timedelta
    
    annual_dividend = 0.0
    
    # 创建持仓股数映射
    shares_map = {}
    for _, row in holdings.iterrows():
        stock_name = row.get("stock_name")
        shares = row.get("shares", 0)
        if stock_name:
            shares_map[stock_name] = shares
    
    if dividends.empty:
        return 0.0
    
    df = dividends.copy()
    
    # 1. 过滤：date 为空的记录
    df = df[df['date'].notna()]
    
    # 2. 过滤：dividend_per_share 为 None 或 0 的记录
    df = df[df['dividend_per_share'].notna() & (df['dividend_per_share'] > 0)]
    
    # 3. 将 dividends['date'] 转为 datetime
    df['date'] = pd.to_datetime(df['date'])
    
    # 4. 获取当前日期
    current_date = datetime.now()
    
    # 5. 过滤出最近365天的分红记录
    one_year_ago = current_date - timedelta(days=365)
    recent_dividends = df[df['date'] >= one_year_ago]
    
    # 6. 计算每只股票最近一年总分红
    stock_dividends = recent_dividends.groupby('stock_name')['dividend_per_share'].sum()
    
    # 7. 只计算当前仍持仓且 shares > 0 的股票
    for stock_name, total_dividend in stock_dividends.items():
        if stock_name in shares_map:
            shares = shares_map[stock_name]
            if shares > 0:
                annual_dividend += total_dividend * shares
    
    return annual_dividend


def analyze_portfolio(holdings, snapshot, dividends=None):
    """
    分析投资组合
    
    Args:
        holdings: 持仓DataFrame，包含列：stock_name, shares, cost_price, total_cost
        snapshot: 市场数据列表，每个元素包含：stock_name, price, pb
        dividends: 分红DataFrame（可选），包含列：date, stock_name, dividend_per_share
    
    Returns:
        dict: 包含汇总和各持仓详细信息的分析结果
    """
    # 目标权重配置
    TARGET_WEIGHTS = {
        "兴业银行": 0.30,
        "招商银行": 0.25,
        "工商银行": 0.20,
        "双汇发展": 0.15,
        "红利ETF": 0.10
    }
    
    positions = []
    total_value = 0.0
    total_cost = 0.0
    
    # 创建股票价格映射，方便查找
    price_map = {}
    for stock in snapshot:
        stock_name = stock.get("stock_name")
        price = stock.get("price")
        if stock_name and price is not None:
            price_map[stock_name] = price
    
    # 遍历每个持仓
    for _, row in holdings.iterrows():
        stock_name = row.get("stock_name")
        shares = row.get("shares", 0)
        cost_price = row.get("cost_price", 0)
        total_cost_this = row.get("total_cost")
        if pd.isna(total_cost_this) or total_cost_this is None:
            total_cost_this = shares * cost_price
        
        price = price_map.get(stock_name)
        
        # 计算市值
        if price is not None and shares > 0:
            market_value = shares * price
        else:
            market_value = 0.0
        
        # 计算浮动收益
        profit = 0.0
        return_rate = None
        
        if total_cost_this > 0:
            profit = market_value - total_cost_this
            return_rate = profit / total_cost_this if total_cost_this != 0 else None
        
        position_info = {
            "stock_name": stock_name,
            "shares": shares,
            "cost_price": cost_price,
            "total_cost": total_cost_this,
            "price": price,
            "market_value": market_value,
            "profit": profit,
            "return_rate": return_rate
        }
        
        positions.append(position_info)
        
        # 累加汇总数据
        total_value += market_value
        total_cost += total_cost_this
    
    # 计算总收益和总收益率
    total_profit = total_value - total_cost
    total_return = None
    if total_cost > 0:
        total_return = total_profit / total_cost
    
    # 计算年分红现金流
    annual_dividend = 0.0
    dividend_yield = None
    
    if dividends is not None:
        annual_dividend = calculate_annual_dividend(holdings, dividends)
        if total_value > 0:
            dividend_yield = annual_dividend / total_value
    
    # 计算各资产配置占比
    allocation = []
    if total_value > 0:
        for pos in positions:
            weight = pos["market_value"] / total_value if total_value != 0 else 0.0
            allocation.append({
                "stock_name": pos["stock_name"],
                "weight": weight
            })
    
    # 计算权重偏差
    deviation = []
    deviation_map = {}
    needs_rebalance = False
    
    for alloc in allocation:
        stock_name = alloc["stock_name"]
        actual_weight = alloc["weight"]
        target_weight = TARGET_WEIGHTS.get(stock_name, 0.0)
        diff = actual_weight - target_weight
        
        deviation.append({
            "stock_name": stock_name,
            "diff": diff
        })
        deviation_map[stock_name] = diff
        
        if abs(diff) > 0.10:
            needs_rebalance = True
    
    # 计算现金流质量
    cashflow_quality = None
    if total_cost > 0:
        cashflow_quality = annual_dividend / total_cost
    
    # 检查数据完整性检查
    has_warning = False
    
    # 1. 检查是否有持仓但没有价格
    holding_stocks = set(holdings['stock_name'].tolist())
    price_stocks = set(stock['stock_name'] for stock in snapshot if 'error' not in stock and stock.get('price') is not None)
    
    stocks_without_price = holding_stocks - price_stocks
    if stocks_without_price:
        has_warning = True
    
    # 2. 检查是否有价格但没有持仓
    stocks_without_holding = price_stocks - holding_stocks
    # 这个不影响估值，不需要警告
    
    if has_warning:
        print("⚠️  部分资产缺少价格，估值可能不准确")
    
    return {
        "total_value": total_value,
        "total_cost": total_cost,
        "total_profit": total_profit,
        "total_return": total_return,
        "annual_dividend": annual_dividend,
        "dividend_yield": dividend_yield,
        "cashflow_quality": cashflow_quality,
        "positions": positions,
        "allocation": allocation,
        "deviation": deviation,
        "deviation_map": deviation_map,
        "needs_rebalance": needs_rebalance,
        "has_warning": has_warning
    }


def print_analysis(analysis):
    """
    打印投资组合分析结果
    
    Args:
        analysis: analyze_portfolio 返回的分析结果
    """
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


def print_dashboard(analysis):
    """
    打印投资组合仪表盘（简洁版）
    
    Args:
        analysis: analyze_portfolio 返回的分析结果
    """
    print("\n==== 投资组合总览 ====\n")
    
    print(f"总资产：{analysis['total_value']:,.2f}")
    
    if analysis['total_return'] is not None:
        sign = "+" if analysis['total_return'] >= 0 else ""
        print(f"总收益率：{sign}{analysis['total_return']*100:.1f}%")
    else:
        print("总收益率：--")
    
    print(f"年现金流：{analysis['annual_dividend']:,.2f}")
    
    if analysis['dividend_yield'] is not None:
        print(f"股息率：{analysis['dividend_yield']*100:.1f}%")
    else:
        print("股息率：--")
    
    if analysis['cashflow_quality'] is not None:
        print(f"现金流质量：{analysis['cashflow_quality']*100:.1f}%")
    else:
        print("现金流质量：--")
    
    if analysis.get('needs_rebalance'):
        print("\n⚠️  需要再平衡！")
    
    print("\n---- 资产分布 ----")
    deviation_map = analysis.get('deviation_map', {})
    for alloc in analysis['allocation']:
        stock_name = alloc['stock_name']
        diff = deviation_map.get(stock_name, 0.0)
        sign = "+" if diff >= 0 else ""
        print(f"{stock_name}：{alloc['weight']*100:.0f}%  ({sign}{diff*100:.0f}%)")
    
    print("\n---- 收益情况 ----")
    for pos in analysis['positions']:
        if pos['return_rate'] is not None:
            sign = "+" if pos['return_rate'] >= 0 else ""
            print(f"{pos['stock_name']}：{sign}{pos['return_rate']*100:.1f}%")
        else:
            print(f"{pos['stock_name']}：--")
    
    print()
