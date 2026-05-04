import pandas as pd
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from market_data import generate_execution_plan, TARGET_WEIGHTS, MIN_DEVIATION_TO_BUY


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
