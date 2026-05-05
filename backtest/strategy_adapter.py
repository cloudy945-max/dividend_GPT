import pandas as pd
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from market_data import generate_execution_plan, TARGET_WEIGHTS, MIN_DEVIATION_TO_BUY

STOCK_CODE_MAP = {
    "招商银行": "600036",
    "兴业银行": "601166",
    "工商银行": "601398",
    "双汇发展": "000895",
    "159307": "159307"
}

STOCK_NAME_MAP = {
    "600036": "招商银行",
    "601166": "兴业银行",
    "601398": "工商银行",
    "000895": "双汇发展",
    "159307": "红利低波100ETF"
}


TARGET_WEIGHTS_DEFAULT = {
    "兴业银行": 0.30,
    "招商银行": 0.25,
    "工商银行": 0.20,
    "双汇发展": 0.15,
    "159307": 0.10
}

MIN_DEVIATION_TO_BUY_DEFAULT = 0.02
PB_BUY_THRESHOLDS = {
    "招商银行": 0.85,
    "兴业银行": 0.75,
    "工商银行": 0.75
}

PRICE_PERCENTILE_THRESHOLDS = {
    "招商银行": 0.15,
    "兴业银行": 0.25,
    "工商银行": 0.25
}


class StrategyAdapter:
    def __init__(self, target_weights=None, pb_thresholds=None, price_percentile_thresholds=None):
        self.target_weights = target_weights or TARGET_WEIGHTS_DEFAULT.copy()
        self.pb_thresholds = pb_thresholds or PB_BUY_THRESHOLDS.copy()
        self.price_percentile_thresholds = price_percentile_thresholds or PRICE_PERCENTILE_THRESHOLDS.copy()
        self.strong_buy_stock = None

    def calculate_deviation(self, current_value, target_weight, total_value):
        if total_value <= 0:
            return 0
        current_weight = current_value / total_value
        return target_weight - current_weight

    def should_buy_stock(self, stock_code, snapshot, current_holdings, total_value):
        if stock_code not in self.target_weights:
            return False

        price = self._get_price(snapshot, stock_code)
        if price is None or price <= 0:
            return False

        current_value = current_holdings.get(stock_code, 0.0)
        deviation = self.calculate_deviation(current_value, self.target_weights[stock_code], total_value)

        if deviation >= MIN_DEVIATION_TO_BUY_DEFAULT:
            return True

        return False

    def should_strong_buy(self, stock_code, snapshot):
        if stock_code not in self.pb_thresholds:
            return False

        pb = self._get_pb(snapshot, stock_code)
        if pb is not None:
            threshold = self.pb_thresholds[stock_code]
            return pb <= threshold

        price_percentile = self._get_price_percentile(snapshot, stock_code)
        if price_percentile is not None:
            threshold = self.price_percentile_thresholds.get(stock_code, 0.15)
            return price_percentile <= threshold

        return False

    def run_strategy(self, snapshot, current_holdings, cash_pool, monthly_budget):
        if current_holdings is None:
            current_holdings = {}

        total_holdings_value = sum(current_holdings.values()) if current_holdings else 0.0
        total_value = total_holdings_value + cash_pool + monthly_budget

        buy_list = self._build_buy_list(snapshot, current_holdings, total_value)

        plan = {
            "buy_list": buy_list
        }

        result = generate_execution_plan(
            plan=plan,
            snapshot=snapshot,
            monthly_budget=monthly_budget,
            current_holdings=current_holdings
        )

        return {
            "actions": result.get("actions", []),
            "cash_left": result.get("cash_left", cash_pool),
            "cash_pool": result.get("remaining_cash_pool", cash_pool)
        }

    def _build_buy_list(self, snapshot, current_holdings, total_value):
        sorted_stocks = []

        for stock_code in self.target_weights.keys():
            if stock_code == "159307":
                continue

            price = self._get_price(snapshot, stock_code)
            if price is None or price <= 0:
                continue

            current_value = current_holdings.get(stock_code, 0.0)
            deviation = self.calculate_deviation(current_value, self.target_weights[stock_code], total_value)

            priority = 1.0
            if self.should_strong_buy(stock_code, snapshot):
                priority = 1.5

            effective_deviation = deviation * priority
            sorted_stocks.append((stock_code, effective_deviation, deviation))

        sorted_stocks.sort(key=lambda x: x[1], reverse=True)

        buy_list = []
        for stock_code, effective_dev, original_dev in sorted_stocks:
            if original_dev >= MIN_DEVIATION_TO_BUY_DEFAULT:
                buy_list.append({
                    "stock_code": stock_code,
                    "deviation": original_dev
                })

        return buy_list

    def execute_rebalance(self, snapshot, simulator, monthly_budget, current_holdings, total_value):
        actions = []

        sorted_stocks = []
        for stock_code in self.target_weights.keys():
            if stock_code == "159307":
                continue

            price = self._get_price(snapshot, stock_code)
            if price is None or price <= 0:
                continue

            current_value = current_holdings.get(stock_code, 0.0)
            deviation = self.calculate_deviation(current_value, self.target_weights[stock_code], total_value)

            priority = 1.0
            if self.should_strong_buy(stock_code, snapshot):
                priority = 1.5

            effective_deviation = deviation * priority
            sorted_stocks.append((stock_code, effective_deviation, deviation))

        sorted_stocks.sort(key=lambda x: x[1], reverse=True)

        cash_pool = monthly_budget

        while cash_pool >= 100:
            best_stock = None
            best_deviation = -float('inf')

            for stock_code, effective_dev, original_dev in sorted_stocks:
                if original_dev < MIN_DEVIATION_TO_BUY_DEFAULT:
                    continue

                price = self._get_price(snapshot, stock_code)
                if price is None or price <= 0:
                    continue

                lot_cost = price * 100
                if cash_pool < lot_cost:
                    continue

                if effective_dev > best_deviation:
                    best_stock = stock_code
                    best_deviation = effective_dev

            if best_stock is None:
                break

            price = self._get_price(snapshot, best_stock)
            shares = 100
            cost = price * shares

            success = simulator.buy(best_stock, shares, price)
            if success:
                actions.append({
                    'stock_code': best_stock,
                    'shares': shares,
                    'price': price,
                    'cost': cost,
                    'action': 'buy'
                })
                cash_pool -= cost

                for i, (code, eff_dev, orig_dev) in enumerate(sorted_stocks):
                    if code == best_stock:
                        new_value = current_holdings.get(best_stock, 0.0) + cost
                        new_dev = self.calculate_deviation(new_value, self.target_weights[best_stock], total_value)
                        priority = 1.5 if self.should_strong_buy(best_stock, snapshot) else 1.0
                        sorted_stocks[i] = (best_stock, new_dev * priority, new_dev)
                        break

                current_holdings[best_stock] = current_holdings.get(best_stock, 0.0) + cost
                total_value += cost

                sorted_stocks.sort(key=lambda x: x[1], reverse=True)

        etf_allowed = all(
            self._get_deviation(stock_code, current_holdings, total_value) < MIN_DEVIATION_TO_BUY_DEFAULT
            for stock_code in self.target_weights.keys()
            if stock_code != "159307"
        )

        if etf_allowed:
            etf_price = self._get_price(snapshot, "159307")
            if etf_price is not None and etf_price > 0 and cash_pool >= etf_price * 100:
                max_lots = int(cash_pool / (etf_price * 100))
                shares = max_lots * 100
                cost = shares * etf_price

                success = simulator.buy("159307", shares, etf_price)
                if success:
                    actions.append({
                        'stock_code': "159307",
                        'shares': shares,
                        'price': etf_price,
                        'cost': cost,
                        'action': 'buy'
                    })
                    cash_pool -= cost

        return actions, cash_pool

    def _get_price(self, snapshot, stock_code):
        for stock in snapshot:
            if stock.get('stock_code') == stock_code:
                return stock.get('price')
        return None

    def _get_pb(self, snapshot, stock_code):
        for stock in snapshot:
            if stock.get('stock_code') == stock_code:
                return stock.get('pb')
        return None

    def _get_price_percentile(self, snapshot, stock_code):
        for stock in snapshot:
            if stock.get('stock_code') == stock_code:
                return stock.get('price_percentile')
        return None

    def _get_deviation(self, stock_code, current_holdings, total_value):
        current_value = current_holdings.get(stock_code, 0.0)
        return self.calculate_deviation(current_value, self.target_weights[stock_code], total_value)

    def get_target_weights(self):
        return self.target_weights.copy()

    def set_target_weights(self, weights):
        self.target_weights = weights.copy()


def debug_backtest_step(history_data):
    """
    调试函数：验证历史数据 → 每日循环 → 策略决策 是否真实发生
    """
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    
    if not history_data:
        print("ERROR: history_data 为空")
        return
    
    stock_list = list(history_data.keys())
    if not stock_list:
        print("ERROR: 没有股票数据")
        return
    
    dates = set()
    for stock_name in stock_list:
        df = history_data[stock_name]
        if df is not None and not df.empty:
            dates.update(df['date'].head(5).tolist())
    
    dates = sorted(list(dates))[:5]
    
    strategy_adapter = StrategyAdapter()
    
    results = []
    strategy_called = False
    
    pb_values = {
        "招商银行": [0.9, 0.84, 0.86, 0.83, 0.87],
        "兴业银行": [0.8, 0.76, 0.74, 0.77, 0.73],
        "工商银行": [0.7, 0.71, 0.69, 0.72, 0.68],
        "双汇发展": [None, None, None, None, None],
        "159307": [None, None, None, None, None]
    }
    
    for idx, date in enumerate(dates):
        snapshot = []
        prices = {}
        
        for stock_name in stock_list:
            df = history_data[stock_name]
            if df is None or df.empty:
                continue
            
            mask = df['date'] == date
            if not mask.any():
                continue
            
            price = df[mask]['close'].iloc[0]
            prices[stock_name] = price
            
            pbs = pb_values.get(stock_name, [None]*5)
            pb = pbs[idx] if idx < len(pbs) else None
            
            snapshot.append({
                'stock_code': stock_name,
                'stock_name': stock_name,
                'price': price,
                'pb': pb,
                'price_percentile': None,
                'data_date': date
            })
        
        if not snapshot:
            continue
        
        current_holdings = {}
        cash_pool = 0
        monthly_budget = 3000
        
        try:
            result = strategy_adapter.run_strategy(
                snapshot=snapshot,
                current_holdings=current_holdings,
                cash_pool=cash_pool,
                monthly_budget=monthly_budget
            )
            strategy_called = True
            
            actions = result.get("actions", [])
            
            strong_buy_stocks = []
            for stock in snapshot:
                stock_code = stock['stock_code']
                if strategy_adapter.should_strong_buy(stock_code, snapshot):
                    strong_buy_stocks.append(stock_code)
            
            results.append({
                'date': date,
                'prices': prices,
                'pbs': {s['stock_code']: s['pb'] for s in snapshot},
                'strong_buy': strong_buy_stocks,
                'actions': actions
            })
            
        except Exception as e:
            print(f"日期 {date}: 策略执行失败 - {e}")
            results.append({
                'date': date,
                'prices': prices,
                'strong_buy': [],
                'actions': []
            })
    
    if not strategy_called:
        print("⚠️ 未触发任何策略逻辑")
        return
    
    all_same = len(set(str(len(r['strong_buy'])) for r in results)) <= 1 and \
               len(set(str(len(r['actions']) > 0) for r in results)) <= 1
    
    for result in results:
        print(f"\n日期: {result['date']}")
        for stock_name, price in result['prices'].items():
            pb = result['pbs'].get(stock_name)
            pb_str = f", PB={pb}" if pb is not None else ""
            print(f"  {stock_name}: {price:.2f}{pb_str}")
        print(f"strong_buy: {result['strong_buy']}")
        
        if result['actions']:
            for action in result['actions']:
                stock = action.get('stock_name', action.get('stock_code', 'unknown'))
                shares = action.get('shares', 0)
                print(f"action: 买入 {stock} {shares}股")
        else:
            print(f"action: None")
    
    if all_same:
        print("\n⚠️ 策略未使用历史数据（可能写死了）")
    else:
        print("\n✅ 策略随价格/PB变化产生不同决策")


def run_backtest(history_data, monthly_budget=3000):
    """
    真正的回测主循环：完整资金演化系统
    """
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    
    if not history_data:
        print("ERROR: history_data 为空")
        return None
    
    all_dates = set()
    for stock_name, df in history_data.items():
        if df is not None and not df.empty:
            all_dates.update(df['date'].tolist())
    
    if not all_dates:
        print("ERROR: 没有日期数据")
        return None
    
    sorted_dates = sorted(all_dates)
    
    cash = 0.0
    holdings = {}
    history = []
    
    strategy_adapter = StrategyAdapter()
    
    prev_month = None
    
    for idx, date in enumerate(sorted_dates):
        snapshot = []
        price_map = {}
        
        print(f"\n{'='*50}")
        print(f"当前日期: {date}")
        
        for stock_name, df in history_data.items():
            if df is None or df.empty:
                continue
            
            mask = df['date'] == date
            if not mask.any():
                continue
            
            price = df[mask]['close'].iloc[0]
            
            stock_code = STOCK_CODE_MAP.get(stock_name, stock_name)
            normalized_name = STOCK_NAME_MAP.get(stock_code, stock_name)
            
            price_map[normalized_name] = price
            
            snapshot.append({
                'stock_code': stock_code,
                'stock_name': normalized_name,
                'price': price,
                'pb': None,
                'price_percentile': None,
                'data_date': date
            })
        
        if not snapshot:
            continue
        
        current_month = date.month
        is_new_month = (prev_month is None) or (current_month != prev_month)
        
        print(f"是否新月: {is_new_month}")
        
        if is_new_month:
            print(f"=== 执行月度策略 ===")
            cash += monthly_budget
            print(f"现金加预算: {cash}")
            
            holdings_value = 0.0
            current_holdings_market_value = {}
            for stock_name, shares in holdings.items():
                price = price_map.get(stock_name, 0)
                value = shares * price
                holdings_value += value
                current_holdings_market_value[stock_name] = value
            
            try:
                result = strategy_adapter.run_strategy(
                    snapshot=snapshot,
                    current_holdings=current_holdings_market_value,
                    cash_pool=0,
                    monthly_budget=cash
                )
                
                actions = result.get("actions", [])
                print(f"策略返回 actions 数: {len(actions)}")
                
                for action in actions:
                    stock_name = action.get('stock_name') or action.get('stock_code')
                    shares = action.get('shares', 0)
                    price = action.get('price') or price_map.get(stock_name, 0)
                    cost = shares * price
                    
                    if stock_name and shares > 0 and cash >= cost:
                        cash -= cost
                        if stock_name in holdings:
                            holdings[stock_name] += shares
                        else:
                            holdings[stock_name] = shares
                        print(f"买入: {stock_name} {shares}股 @ {price} = {cost}")
                    else:
                        print(f"跳过: {stock_name} {shares}股, cash={cash}")
                
            except Exception as e:
                print(f"策略执行失败: {e}")
            
            prev_month = current_month
        
        holdings_value = sum(holdings.get(s, 0) * price_map.get(s, 0) for s in holdings)
        total_value = cash + holdings_value
        
        print(f"当日总市值: {total_value} (cash={cash}, holdings={holdings_value})")
        
        history.append({
            'date': date,
            'cash': cash,
            'holdings_value': holdings_value,
            'total_value': total_value,
            'holdings': dict(holdings)
        })
    
    return history
