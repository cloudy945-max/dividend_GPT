import pandas as pd
import os
from datetime import datetime


def calculate_irr(transactions, snapshot, current_date=None):
    """
    计算内部收益率 (IRR)
    
    Args:
        transactions: 交易记录DataFrame
        snapshot: 市场数据列表，用于计算当前市值
        current_date: 当前日期，默认使用datetime.now()
    
    Returns:
        dict: 包含整体IRR和分类IRR的字典
    """
    if current_date is None:
        current_date = datetime.now()
    
    if transactions.empty:
        return {
            'overall_irr': None,
            'new_cash_irr': None,
            'reinvest_irr': None,
            'total_invested': 0.0,
            'new_cash_invested': 0.0,
            'reinvest_amount': 0.0
        }
    
    transactions = transactions.sort_values('date')
    start_date = transactions['date'].min()
    
    start_months = start_date.year * 12 + start_date.month
    end_months = current_date.year * 12 + current_date.month
    total_months = end_months - start_months
    
    price_map = {}
    for stock in snapshot:
        stock_name = stock.get("stock_name")
        price = stock.get("price")
        if stock_name and price is not None:
            price_map[stock_name] = price
    
    holdings_value = 0.0
    holdings_shares = {}
    for _, row in transactions.iterrows():
        stock_name = row['stock_name']
        shares = row['shares']
        type_ = row['type']
        
        if stock_name not in holdings_shares:
            holdings_shares[stock_name] = 0
        
        if type_ in ['buy', 'dividend_reinvest']:
            holdings_shares[stock_name] += shares
        elif type_ == 'sell':
            holdings_shares[stock_name] -= shares
    
    for stock_name, shares in holdings_shares.items():
        if shares > 0 and stock_name in price_map:
            holdings_value += shares * price_map[stock_name]
    
    cash_flows = []
    cash_flows_new = []
    cash_flows_reinvest = []
    
    for _, row in transactions.iterrows():
        month_idx = (row['date'].year * 12 + row['date'].month) - start_months
        amount = row['cash_flow']
        
        cash_flows.append((month_idx, amount))
        
        source = row.get('source', 'new_cash')
        if source == 'new_cash':
            cash_flows_new.append((month_idx, amount))
        elif source == 'dividend_reinvest':
            cash_flows_reinvest.append((month_idx, amount))
    
    if total_months > 0 and holdings_value > 0:
        cash_flows.append((total_months, holdings_value))
    
    def npv(rate, flows):
        return sum(cf / (1 + rate) ** (t / 12) for t, cf in flows)
    
    def find_irr(flows):
        if len(flows) < 2:
            return None
        
        total_flows = sum(abs(cf) for _, cf in flows)
        if total_flows == 0:
            return None
        
        try:
            irr = brentq(npv, -0.99, 10.0, args=(flows,), maxiter=1000)
            return irr
        except:
            return None
    
    try:
        from scipy.optimize import brentq
    except ImportError:
        def find_irr_simple(flows):
            if len(flows) < 2:
                return None
            total_npv_pos = npv(0.01, flows)
            total_npv_neg = npv(-0.5, flows)
            if total_npv_pos * total_npv_neg > 0:
                return None
            low, high = -0.5, 0.5
            for _ in range(100):
                mid = (low + high) / 2
                if npv(mid, flows) == 0:
                    return mid
                elif npv(low, flows) * npv(mid, flows) < 0:
                    high = mid
                else:
                    low = mid
            return (low + high) / 2
        find_irr = find_irr_simple
    
    overall_irr = find_irr(cash_flows) if cash_flows else None
    new_cash_irr = find_irr(cash_flows_new) if cash_flows_new else None
    reinvest_irr = find_irr(cash_flows_reinvest) if cash_flows_reinvest else None
    
    total_invested = sum(tx['cash_flow'] for _, tx in transactions.iterrows() 
                         if tx['type'] in ['buy', 'dividend_reinvest'])
    new_cash_invested = sum(tx['cash_flow'] for _, tx in transactions.iterrows() 
                           if tx.get('source') == 'new_cash' and tx['type'] == 'buy')
    reinvest_amount = sum(tx['cash_flow'] for _, tx in transactions.iterrows() 
                         if tx['type'] == 'dividend_reinvest')
    
    return {
        'overall_irr': overall_irr,
        'new_cash_irr': new_cash_irr,
        'reinvest_irr': reinvest_irr,
        'total_invested': abs(total_invested),
        'new_cash_invested': abs(new_cash_invested),
        'reinvest_amount': abs(reinvest_amount),
        'total_months': total_months
    }


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


def analyze_portfolio(holdings, snapshot, dividends=None, transactions=None):
    """
    分析投资组合
    
    Args:
        holdings: 持仓DataFrame，包含列：stock_name, shares, cost_price, total_cost
        snapshot: 市场数据列表，每个元素包含：stock_name, price, pb
        dividends: 分红DataFrame（可选），包含列：date, stock_name, dividend_per_share
        transactions: 交易记录DataFrame（可选），用于计算IRR
    
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
    
    # 创建股票价格映射，方便查找（同时支持代码和名称）
    price_map = {}
    for stock in snapshot:
        stock_code = stock.get("stock_code")
        stock_name = stock.get("stock_name")
        price = stock.get("price")
        if stock_code and price is not None:
            price_map[stock_code] = price
        if stock_name and price is not None:
            price_map[stock_name] = price
    
    # 创建已收分红映射
    dividends_received_map = {}
    total_dividend_received = 0.0
    if dividends is not None and not dividends.empty:
        df_div = dividends.copy()
        holdings_shares = holdings.set_index('stock_name')['shares']
        df_div['shares'] = df_div['stock_name'].map(holdings_shares)
        df_div['total_dividend'] = df_div['dividend_per_share'] * df_div['shares']
        dividends_by_stock = df_div.groupby('stock_name')['total_dividend'].sum()
        for stock_name, div in dividends_by_stock.items():
            dividends_received_map[stock_name] = div
            total_dividend_received += div
    
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
        
        # 获取该持仓已收分红
        dividend_received = dividends_received_map.get(stock_name, 0.0)
        adjusted_cost = total_cost_this - dividend_received
        total_profit_with_div = market_value - adjusted_cost
        return_rate_with_div = total_profit_with_div / adjusted_cost if adjusted_cost != 0 else None
        
        position_info = {
            "stock_name": stock_name,
            "shares": shares,
            "cost_price": cost_price,
            "total_cost": total_cost_this,
            "price": price,
            "market_value": market_value,
            "profit": profit,
            "return_rate": return_rate,
            "dividend_received": dividend_received,
            "adjusted_cost": adjusted_cost,
            "total_profit_with_div": total_profit_with_div,
            "return_rate_with_div": return_rate_with_div
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
        print("Warning: 部分资产缺少价格，估值可能不准确")
    
    irr_analysis = None
    if transactions is not None and not transactions.empty:
        irr_analysis = calculate_irr(transactions, snapshot)
    
    return {
        "total_value": total_value,
        "total_cost": total_cost,
        "total_profit": total_profit,
        "total_return": total_return,
        "total_dividend_received": total_dividend_received,
        "annual_dividend": annual_dividend,
        "dividend_yield": dividend_yield,
        "cashflow_quality": cashflow_quality,
        "positions": positions,
        "allocation": allocation,
        "deviation": deviation,
        "deviation_map": deviation_map,
        "needs_rebalance": needs_rebalance,
        "has_warning": has_warning,
        "irr_analysis": irr_analysis
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

    total_div_received = analysis.get('total_dividend_received', 0.0)
    if total_div_received > 0:
        print(f"已收分红：+{total_div_received:.2f}")

    print(f"年现金流：{analysis['annual_dividend']:,.2f}")

    if analysis['dividend_yield'] is not None:
        print(f"股息率：{analysis['dividend_yield']*100:.1f}%")
    else:
        print("股息率：--")

    if analysis['cashflow_quality'] is not None:
        print(f"现金流质量：{analysis['cashflow_quality']*100:.1f}%")
    else:
        print("现金流质量：--")
    
    irr = analysis.get('irr_analysis')
    if irr:
        print("\n---- 内部收益率 (IRR) ----")
        if irr['overall_irr'] is not None:
            print(f"整体 IRR (年化): {irr['overall_irr']*100:.2f}%")
        else:
            print("整体 IRR: 暂无数据")
        
        if irr['new_cash_irr'] is not None:
            print(f"新增资金 IRR: {irr['new_cash_irr']*100:.2f}%")
        if irr['reinvest_irr'] is not None:
            print(f"红利再投资 IRR: {irr['reinvest_irr']*100:.2f}%")
        
        if irr['total_months'] and irr['total_months'] > 0:
            print(f"(持有期: {irr['total_months']}个月)")

    if analysis.get('needs_rebalance'):
        print("\n! 需要再平衡！")

    print("\n---- 资产分布 ----")
    deviation_map = analysis.get('deviation_map', {})
    for alloc in analysis['allocation']:
        stock_name = alloc['stock_name']
        diff = deviation_map.get(stock_name, 0.0)
        sign = "+" if diff >= 0 else ""
        print(f"{stock_name}：{alloc['weight']*100:.0f}%  ({sign}{diff*100:.0f}%)")

    print("\n---- 收益情况 ----")
    print(f"{'名称':<12} {'市值':>10} {'综合收益率':>10} {'已收分红':>10}")
    print("-" * 45)
    for pos in analysis['positions']:
        stock_name = pos['stock_name']
        market_value = pos.get('market_value', 0.0)
        return_rate_with_div = pos.get('return_rate_with_div')
        div_received = pos.get('dividend_received', 0.0)

        if return_rate_with_div is not None:
            sign = "+" if return_rate_with_div >= 0 else ""
            rate_str = f"{sign}{return_rate_with_div*100:.1f}%"
        else:
            rate_str = "--"

        div_str = f"+{div_received:.0f}元" if div_received > 0 else "--"

        print(f"{stock_name:<12} {market_value:>10.2f} {rate_str:>10} {div_str:>10}")

    print()
