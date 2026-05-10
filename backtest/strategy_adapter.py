import pandas as pd
import logging
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from market_data import (
    generate_execution_plan, 
    calculate_rebalance_buys,
    TARGET_WEIGHTS, 
    MIN_DEVIATION_TO_BUY,
    get_stock_name,
    CODE_TO_NAME
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
        self.cash_pool = 0.0
        self.tracking_months_no_stock = 0
        self.MONTHS_TO_ALLOW_ETF = 6

    def calculate_deviation(self, current_value, target_weight, total_value):
        if total_value <= 0:
            return 0
        current_weight = current_value / total_value
        return target_weight - current_weight

    def should_strong_buy(self, stock_code, snapshot):
        if stock_code not in self.pb_thresholds:
            return False

        pb = self._get_pb(snapshot, stock_code)
        if pb is not None:
            threshold = self.pb_thresholds[stock_code]
            if pb <= threshold:
                logger.info(f"强买触发: {stock_code}, PB={pb:.3f} <= 阈值{threshold}")
                return True

        price_percentile = self._get_price_percentile(snapshot, stock_code)
        if price_percentile is not None:
            threshold = self.price_percentile_thresholds.get(stock_code, 0.15)
            if price_percentile <= threshold:
                logger.info(f"强买触发: {stock_code}, 价格百分位={price_percentile:.3f} <= 阈值{threshold}")
                return True

        return False

    def get_strong_buy_stock(self, snapshot):
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

        return strong_buy_stock, strong_buy_pb

    def generate_monthly_buy_plan(self, snapshot, current_holdings, available_cash, monthly_budget):
        """
        生成月度买入计划（回测专用）
        
        Args:
            snapshot: 当前日期的快照数据（包含price、pb）
            current_holdings: 当前持仓市值字典 {stock_code: market_value}
            available_cash: 当前可用现金（资金池）
            monthly_budget: 月度预算
            
        Returns:
            {
                "actions": [
                    {
                        "stock_code": str,
                        "stock_name": str,
                        "shares": int,
                        "price": float,
                        "cost": float,
                        "reason": "strong_buy" | "rebalance" | "etf_allocation" | "fallback_etf"
                    }
                ],
                "cash_left": float,
                "cash_pool": float,
                "is_strong_buy": bool
            }
        """
        current_holdings = current_holdings or {}
        total_holdings_value = sum(current_holdings.values()) if current_holdings else 0.0
        
        strong_buy_stock, _ = self.get_strong_buy_stock(snapshot)
        strong_buy_flag = strong_buy_stock is not None
        
        MAX_CASH_POOL = monthly_budget * 4
        
        plan = {
            "buy_list": self._build_buy_list(snapshot, current_holdings, total_holdings_value + available_cash + monthly_budget)
        }

        execution_result = generate_execution_plan(
            plan=plan,
            snapshot=snapshot,
            monthly_budget=monthly_budget,
            current_holdings=current_holdings
        )

        actions_with_reason = []
        for action in execution_result.get("actions", []):
            stock_code = action.get("stock_code")
            reason = "rebalance"
            
            if action.get("is_strong_buy", False) or stock_code == strong_buy_stock:
                reason = "strong_buy"
            elif action.get("is_fallback_etf", False):
                reason = "fallback_etf"
            elif stock_code == "159307":
                reason = "etf_allocation"

            actions_with_reason.append({
                "stock_code": stock_code,
                "stock_name": action.get("stock_name", get_stock_name(stock_code)),
                "shares": action.get("shares", 0),
                "price": action.get("price"),
                "cost": action.get("cost", 0),
                "reason": reason,
                "current_weight": action.get("current_weight", 0),
                "target_weight": action.get("target_weight", 0),
                "deviation": action.get("deviation", 0)
            })

        self.cash_pool = execution_result.get("remaining_cash_pool", self.cash_pool)
        
        has_stock_action = any(a["stock_code"] != "159307" for a in actions_with_reason)
        if has_stock_action:
            self.tracking_months_no_stock = 0
        else:
            self.tracking_months_no_stock += 1

        return {
            "actions": actions_with_reason,
            "cash_left": execution_result.get("cash_left", 0.0),
            "cash_pool": self.cash_pool,
            "is_strong_buy": strong_buy_flag,
            "strong_buy_stock": strong_buy_stock
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

            reason = "strong_buy" if self.should_strong_buy(best_stock, snapshot) else "rebalance"

            success = simulator.buy(best_stock, shares, price)
            if success:
                actions.append({
                    'stock_code': best_stock,
                    'stock_name': get_stock_name(best_stock),
                    'shares': shares,
                    'price': price,
                    'cost': cost,
                    'action': 'buy',
                    'reason': reason
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
                        'stock_name': get_stock_name("159307"),
                        'shares': shares,
                        'price': etf_price,
                        'cost': cost,
                        'action': 'buy',
                        'reason': 'etf_allocation'
                    })
                    cash_pool -= cost

        return actions, cash_pool

    def select_stock_for_reinvest(self, snapshot, simulator, current_holdings, total_value):
        candidates = []
        
        for stock_code in self.target_weights.keys():
            if stock_code == "159307":
                continue

            price = self._get_price(snapshot, stock_code)
            if price is None or price <= 0:
                continue

            can_buy, lot_cost, total_cost = simulator.can_buy_one_lot(stock_code, {stock_code: price})
            if not can_buy:
                continue

            current_value = current_holdings.get(stock_code, 0.0)
            deviation = self.calculate_deviation(current_value, self.target_weights[stock_code], total_value)

            priority = 1.0
            if self.should_strong_buy(stock_code, snapshot):
                priority = 2.0

            score = deviation * priority
            
            candidates.append({
                'stock_code': stock_code,
                'stock_name': get_stock_name(stock_code),
                'price': price,
                'deviation': deviation,
                'priority': priority,
                'score': score,
                'lot_cost': lot_cost
            })
        
        if not candidates:
            return None
        
        candidates.sort(key=lambda x: x['score'], reverse=True)
        
        for candidate in candidates:
            if candidate['deviation'] >= MIN_DEVIATION_TO_BUY_DEFAULT * 0.5:
                return candidate
        
        return candidates[0] if candidates else None

    def reinvest_dividends(self, snapshot, simulator, current_holdings, total_value):
        reinvest_actions = []
        
        while True:
            best_candidate = self.select_stock_for_reinvest(
                snapshot, simulator, current_holdings, total_value
            )
            
            if best_candidate is None:
                break
            
            stock_code = best_candidate['stock_code']
            price = best_candidate['price']
            
            success = simulator.reinvest_dividend(stock_code, price)
            
            if success:
                reinvest_actions.append({
                    'stock_code': stock_code,
                    'stock_name': get_stock_name(stock_code),
                    'price': price,
                    'action': 'dividend_reinvest',
                    'reason': 'dividend_reinvest'
                })
                
                cost = best_candidate['lot_cost']
                current_holdings[stock_code] = current_holdings.get(stock_code, 0.0) + cost
                total_value += cost
            else:
                break
        
        return reinvest_actions

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

    def reset(self):
        self.cash_pool = 0.0
        self.tracking_months_no_stock = 0