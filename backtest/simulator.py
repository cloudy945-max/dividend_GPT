import pandas as pd
from datetime import datetime
from copy import deepcopy


class TradeSimulator:
    def __init__(self, initial_cash=100000.0, commission_rate=0.0003):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.commission_rate = commission_rate
        self.positions = {}
        self.transactions = []
        self.dividends_received = []
        self.current_date = None

    def reset(self, initial_cash=None):
        if initial_cash is not None:
            self.initial_cash = initial_cash
        self.cash = self.initial_cash
        self.positions = {}
        self.transactions = []
        self.dividends_received = []
        self.current_date = None

    def set_date(self, date):
        self.current_date = date

    def buy(self, stock_code, shares, price):
        if shares <= 0 or price <= 0:
            return False
        cost = shares * price
        commission = cost * self.commission_rate
        total_cost = cost + commission

        if total_cost > self.cash:
            return False

        lot_price = price * 100
        if shares < 100:
            return False
        actual_lots = (shares // 100) * 100

        actual_cost = actual_lots * price
        actual_commission = actual_cost * self.commission_rate
        total_actual_cost = actual_cost + actual_commission

        if total_actual_cost > self.cash:
            return False

        if stock_code in self.positions:
            old_shares = self.positions[stock_code]['shares']
            old_cost = self.positions[stock_code]['cost']
            new_cost = old_cost + actual_cost
            new_shares = old_shares + actual_lots
            new_avg_price = new_cost / new_shares
            self.positions[stock_code] = {
                'shares': new_shares,
                'cost': new_cost,
                'avg_price': new_avg_price
            }
        else:
            self.positions[stock_code] = {
                'shares': actual_lots,
                'cost': actual_cost,
                'avg_price': price
            }

        self.cash -= total_actual_cost

        self.transactions.append({
            'date': self.current_date,
            'type': 'buy',
            'stock_code': stock_code,
            'shares': actual_lots,
            'price': price,
            'cost': actual_cost,
            'commission': actual_commission,
            'cash_after': self.cash
        })
        return True

    def sell(self, stock_code, shares, price):
        if stock_code not in self.positions:
            return False

        position = self.positions[stock_code]
        if shares > position['shares']:
            shares = position['shares']

        if shares <= 0:
            return False

        lot_price = price * 100
        sell_lots = (shares // 100) * 100

        if sell_lots <= 0:
            return False

        proceeds = sell_lots * price
        commission = proceeds * self.commission_rate
        tax = proceeds * 0.001
        net_proceeds = proceeds - commission - tax

        if sell_lots == position['shares']:
            profit = proceeds - commission - tax - position['cost']
            del self.positions[stock_code]
        else:
            ratio = sell_lots / position['shares']
            cost_sold = position['cost'] * ratio
            profit = proceeds - commission - tax - cost_sold
            position['shares'] -= sell_lots
            position['cost'] -= cost_sold

        self.cash += net_proceeds

        self.transactions.append({
            'date': self.current_date,
            'type': 'sell',
            'stock_code': stock_code,
            'shares': sell_lots,
            'price': price,
            'proceeds': proceeds,
            'commission': commission,
            'tax': tax,
            'profit': profit,
            'cash_after': self.cash
        })
        return True

    def receive_dividend(self, stock_code, dividend_per_share, shares):
        if stock_code not in self.positions:
            return 0.0
        position = self.positions[stock_code]
        if shares > position['shares']:
            shares = position['shares']
        dividend_amount = shares * dividend_per_share
        self.cash += dividend_amount
        self.dividends_received.append({
            'date': self.current_date,
            'stock_code': stock_code,
            'dividend_per_share': dividend_per_share,
            'shares': shares,
            'amount': dividend_amount
        })
        return dividend_amount

    def get_portfolio_value(self, price_map):
        total_value = self.cash
        for stock_code, position in self.positions.items():
            price = price_map.get(stock_code, 0)
            if price > 0:
                total_value += position['shares'] * price
        return total_value

    def get_holdings_value(self, price_map):
        holdings_value = {}
        for stock_code, position in self.positions.items():
            price = price_map.get(stock_code, 0)
            holdings_value[stock_code] = position['shares'] * price if price > 0 else 0
        return holdings_value

    def get_transactions_df(self):
        if not self.transactions:
            return pd.DataFrame()
        return pd.DataFrame(self.transactions)

    def get_dividends_df(self):
        if not self.dividends_received:
            return pd.DataFrame()
        return pd.DataFrame(self.dividends_received)

    def get_positions_snapshot(self):
        return deepcopy(self.positions)

    def get_current_holdings(self):
        holdings = {}
        for stock_code, position in self.positions.items():
            holdings[stock_code] = position['shares'] * position['avg_price']
        return holdings

    def get_stock_count(self, stock_code):
        if stock_code not in self.positions:
            return 0
        return self.positions[stock_code]['shares']


class BacktestEngine:
    def __init__(self, data_loader, strategy_adapter):
        self.data_loader = data_loader
        self.strategy_adapter = strategy_adapter
        self.cash = 0
        self.cash_pool = 0
        self.holdings = {}
        self.history = []
        self.transactions = []

    def reset(self):
        self.cash = 0
        self.cash_pool = 0
        self.holdings = {}
        self.history = []
        self.transactions = []

    def run_backtest(self, stock_list, start_date, end_date, monthly_budget=3000):
        self.reset()

        price_data = self.data_loader.load_price_history(stock_list, start_date, end_date)

        if not price_data:
            return self.history

        monthly_dates = self._get_monthly_dates(start_date, end_date)

        for month_date in monthly_dates:
            self.cash += monthly_budget

            snapshot = self._build_snapshot(price_data, month_date)

            if not snapshot:
                continue

            price_map = {s['stock_code']: s['price'] for s in snapshot}

            current_holdings_market_value = self._get_holdings_market_value(price_map)

            strategy_result = self.strategy_adapter.run_strategy(
                snapshot=snapshot,
                current_holdings=current_holdings_market_value,
                cash_pool=self.cash_pool,
                monthly_budget=monthly_budget
            )

            self._execute_actions(strategy_result.get('actions', []), price_map)

            self.cash_pool = strategy_result.get('cash_pool', self.cash_pool)

            holdings_value = self._calculate_holdings_market_value(price_map)
            total_value = self.cash + self.cash_pool + holdings_value

            self.history.append({
                'date': month_date,
                'total_value': total_value,
                'cash': self.cash,
                'cash_pool': self.cash_pool,
                'holdings_value': holdings_value,
                'holdings': deepcopy(self.holdings)
            })

        return self.history

    def _get_monthly_dates(self, start_date, end_date):
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        monthly_dates = pd.date_range(start, end, freq='MS')
        valid_dates = [d for d in monthly_dates if d <= end]
        return valid_dates

    def _build_snapshot(self, price_data, date):
        snapshot = []
        current_date = pd.to_datetime(date)

        for stock_code, df in price_data.items():
            if df.empty:
                continue

            df_dates = pd.to_datetime(df['date'])
            valid_dates = df_dates[df_dates <= current_date]

            if valid_dates.empty:
                continue

            closest_date = valid_dates[-1]
            row = df[df['date'] == closest_date].iloc[0]

            price_percentile = self.data_loader.get_price_percentile(stock_code, closest_date)

            snapshot.append({
                'stock_code': stock_code,
                'stock_name': self._get_stock_name(stock_code),
                'price': row['close'],
                'pb': None,
                'price_percentile': price_percentile,
                'data_date': closest_date
            })

        return snapshot

    def _get_stock_name(self, stock_code):
        name_map = {
            "招商银行": "招商银行",
            "兴业银行": "兴业银行",
            "工商银行": "工商银行",
            "双汇发展": "双汇发展",
            "159307": "红利低波100ETF"
        }
        return name_map.get(stock_code, stock_code)

    def _get_holdings_market_value(self, price_map):
        holdings_market_value = {}
        for stock_code, shares in self.holdings.items():
            price = price_map.get(stock_code, 0)
            if price > 0:
                holdings_market_value[stock_code] = shares * price
        return holdings_market_value

    def _calculate_holdings_market_value(self, price_map):
        total = 0.0
        for stock_code, shares in self.holdings.items():
            price = price_map.get(stock_code, 0)
            if price > 0:
                total += shares * price
        return total

    def _execute_actions(self, actions, price_map):
        for action in actions:
            stock_code = action.get('stock_code')
            shares = action.get('shares', 0)
            price = price_map.get(stock_code, 0)

            if shares <= 0 or price <= 0:
                continue

            cost = shares * price
            commission = cost * 0.0003
            total_cost = cost + commission

            if total_cost > self.cash:
                continue

            actual_lots = (shares // 100) * 100
            if actual_lots <= 0:
                continue

            actual_cost = actual_lots * price
            actual_commission = actual_cost * 0.0003
            total_actual_cost = actual_cost + actual_commission

            if total_actual_cost > self.cash:
                continue

            if stock_code in self.holdings:
                self.holdings[stock_code] += actual_lots
            else:
                self.holdings[stock_code] = actual_lots

            self.cash -= total_actual_cost

            self.transactions.append({
                'date': self.history[-1]['date'] if self.history else None,
                'type': 'buy',
                'stock_code': stock_code,
                'shares': actual_lots,
                'price': price,
                'cost': actual_cost,
                'commission': actual_commission
            })

    def get_history_df(self):
        if not self.history:
            return pd.DataFrame()
        return pd.DataFrame(self.history)

    def get_transactions_df(self):
        if not self.transactions:
            return pd.DataFrame()
        return pd.DataFrame(self.transactions)
