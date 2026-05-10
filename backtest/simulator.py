import pandas as pd
import numpy as np
from datetime import datetime
from copy import deepcopy
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from portfolio import PortfolioManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('backtest_data/simulator.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


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
        self.current_date = pd.to_datetime(date)

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
            'stock_name': stock_code,
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
            'stock_name': stock_code,
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
            'stock_name': stock_code,
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

    def can_buy_one_lot(self, stock_code, price_map):
        price = price_map.get(stock_code, 0)
        if price <= 0:
            return False, 0, 0
        lot_cost = price * 100
        commission = lot_cost * self.commission_rate
        total_cost = lot_cost + commission
        if self.cash >= total_cost:
            return True, lot_cost, total_cost
        return False, lot_cost, total_cost

    def reinvest_dividend(self, stock_code, price):
        lot_cost = price * 100
        commission = lot_cost * self.commission_rate
        total_cost = lot_cost + commission
        
        if total_cost > self.cash:
            return False
        
        actual_lots = (int(self.cash // total_cost)) * 100
        if actual_lots < 100:
            return False
        
        actual_cost = actual_lots * price
        actual_commission = actual_cost * self.commission_rate
        total_actual_cost = actual_cost + actual_commission
        
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
            'type': 'dividend_reinvest',
            'stock_code': stock_code,
            'stock_name': stock_code,
            'shares': actual_lots,
            'price': price,
            'cost': actual_cost,
            'commission': actual_commission,
            'cash_after': self.cash,
            'source': 'dividend'
        })
        return True

    def get_accumulated_dividends(self):
        return sum(d['amount'] for d in self.dividends_received)

    def get_reinvest_stats(self):
        reinvest_txs = [tx for tx in self.transactions if tx.get('source') == 'dividend']
        if not reinvest_txs:
            return {'count': 0, 'total_amount': 0, 'stocks': []}
        
        total = sum(tx['cost'] for tx in reinvest_txs)
        stocks = list(set(tx['stock_code'] for tx in reinvest_txs))
        return {
            'count': len(reinvest_txs),
            'total_amount': total,
            'stocks': stocks
        }


class BacktestEngine:
    def __init__(self, data_loader, strategy_adapter, use_portfolio_manager=False, data_dir='backtest_data'):
        self.data_loader = data_loader
        self.strategy_adapter = strategy_adapter
        self.use_portfolio_manager = use_portfolio_manager
        self.data_dir = data_dir
        
        if use_portfolio_manager:
            self.portfolio_manager = PortfolioManager(data_dir=os.path.join(data_dir, 'portfolio'))
        else:
            self.portfolio_manager = None
        
        self.cash = 0
        self.cash_pool = 0
        self.holdings = {}
        self.history = []
        self.transactions = []
        self.monthly_records = []

    def reset(self):
        self.cash = 0
        self.cash_pool = 0
        self.holdings = {}
        self.history = []
        self.transactions = []
        self.monthly_records = []
        self.strategy_adapter.reset()
        
        if self.portfolio_manager:
            self.portfolio_manager.load_data()

    def run_backtest(self, stock_list, start_date, end_date, monthly_budget=3000):
        self.reset()

        logger.info(f"开始回测: {start_date} 至 {end_date}, 月度预算: {monthly_budget}")

        price_data = self.data_loader.load_price_history(stock_list, start_date, end_date)
        pb_data = self.data_loader.load_pb_history(stock_list, start_date, end_date)

        if not price_data:
            logger.error("未能加载价格数据")
            return self.history

        monthly_dates = self._get_monthly_dates(start_date, end_date)
        logger.info(f"共有 {len(monthly_dates)} 个调仓日期")

        for idx, month_date in enumerate(monthly_dates):
            logger.info(f"\n==== 第 {idx+1}/{len(monthly_dates)} 个月: {month_date.strftime('%Y-%m-%d')} ====")
            
            self.cash += monthly_budget
            
            snapshot = self._build_snapshot(price_data, pb_data, month_date)

            if not snapshot:
                logger.warning(f"无法构建 {month_date} 的快照")
                continue

            price_map = {s['stock_code']: s['price'] for s in snapshot}
            current_holdings_market_value = self._get_holdings_market_value(price_map)

            logger.info(f"当前现金: {self.cash:.2f}")
            logger.info(f"当前持仓市值: {sum(current_holdings_market_value.values()):.2f}")
            logger.info(f"当前资金池: {self.cash_pool:.2f}")

            strategy_result = self.strategy_adapter.generate_monthly_buy_plan(
                snapshot=snapshot,
                current_holdings=current_holdings_market_value,
                available_cash=self.cash_pool,
                monthly_budget=monthly_budget
            )

            actions = strategy_result.get('actions', [])
            self.cash_pool = strategy_result.get('cash_pool', self.cash_pool)
            
            logger.info(f"本月强买: {'是' if strategy_result.get('is_strong_buy') else '否'}")
            if strategy_result.get('strong_buy_stock'):
                logger.info(f"强买标的: {strategy_result['strong_buy_stock']}")

            self._execute_actions(actions, price_map, month_date)

            holdings_value = self._calculate_holdings_market_value(price_map)
            total_value = self.cash + self.cash_pool + holdings_value

            logger.info(f"本月操作: {len(actions)} 笔")
            for action in actions:
                reason = action.get('reason', 'unknown')
                logger.info(f"  - 买入 {action['stock_name']} {action['shares']}股 @ {action['price']:.2f} = {action['cost']:.2f} ({reason})")
            logger.info(f"月末总资产: {total_value:.2f} (现金: {self.cash:.2f}, 资金池: {self.cash_pool:.2f}, 持仓: {holdings_value:.2f})")

            self._record_monthly_snapshot(month_date, total_value, holdings_value)

        logger.info("\n==== 回测完成 ====")
        return self.history

    def _get_monthly_dates(self, start_date, end_date):
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        monthly_dates = pd.date_range(start, end, freq='MS')
        
        valid_dates = []
        for d in monthly_dates:
            if d <= end:
                valid_dates.append(d)
        
        return valid_dates

    def _build_snapshot(self, price_data, pb_data, date):
        snapshot = []
        current_date = pd.to_datetime(date)

        for stock_code in price_data.keys():
            if stock_code not in price_data:
                continue

            df = price_data[stock_code]
            if df.empty:
                continue

            df_dates = pd.to_datetime(df['date'])
            valid_dates = df_dates[df_dates <= current_date]

            if valid_dates.empty:
                continue

            closest_date = valid_dates[-1]
            row = df[df['date'] == closest_date].iloc[0]

            pb = None
            if stock_code in pb_data and not pb_data[stock_code].empty:
                pb_df = pb_data[stock_code]
                pb_dates = pd.to_datetime(pb_df['date'])
                pb_valid = pb_dates[pb_dates <= current_date]
                if not pb_valid.empty:
                    pb_row = pb_df[pb_dates == pb_valid[-1]].iloc[0]
                    pb = pb_row['pb']

            price_percentile = self.data_loader.get_price_percentile(stock_code, closest_date)

            snapshot.append({
                'stock_code': stock_code,
                'stock_name': self._get_stock_name(stock_code),
                'price': row['close'],
                'pb': pb,
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

    def _execute_actions(self, actions, price_map, date):
        for action in actions:
            stock_code = action.get('stock_code')
            shares = action.get('shares', 0)
            price = action.get('price')
            reason = action.get('reason', 'unknown')

            if shares <= 0 or price is None or price <= 0:
                continue

            cost = shares * price
            commission = cost * 0.0003
            total_cost = cost + commission

            if total_cost > self.cash:
                logger.warning(f"现金不足，跳过买入 {stock_code}")
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
                'date': date,
                'type': 'buy',
                'stock_code': stock_code,
                'stock_name': action.get('stock_name', stock_code),
                'shares': actual_lots,
                'price': price,
                'cost': actual_cost,
                'commission': actual_commission,
                'reason': reason
            })

            if self.portfolio_manager:
                self.portfolio_manager.add_transaction(
                    date=date,
                    type_='buy',
                    stock_name=action.get('stock_name', stock_code),
                    price=price,
                    shares=actual_lots,
                    source='new_cash'
                )

    def _record_monthly_snapshot(self, date, total_value, holdings_value):
        holdings_copy = deepcopy(self.holdings)
        
        monthly_record = {
            'date': date,
            'total_value': total_value,
            'cash': self.cash,
            'cash_pool': self.cash_pool,
            'holdings_value': holdings_value,
            'holdings': holdings_copy,
            'transactions_count': len(self.transactions)
        }
        
        self.monthly_records.append(monthly_record)
        self.history.append(monthly_record)

    def get_history_df(self):
        if not self.history:
            return pd.DataFrame()
        df = pd.DataFrame(self.history)
        df['date'] = pd.to_datetime(df['date'])
        return df

    def get_transactions_df(self):
        if not self.transactions:
            return pd.DataFrame()
        df = pd.DataFrame(self.transactions)
        df['date'] = pd.to_datetime(df['date'])
        return df

    def get_monthly_records(self):
        return self.monthly_records

    def get_summary(self):
        if not self.history:
            return {}
        
        first_record = self.history[0]
        last_record = self.history[-1]
        
        initial_value = first_record['total_value']
        final_value = last_record['total_value']
        total_return = (final_value - initial_value) / initial_value if initial_value > 0 else 0
        
        dates = [r['date'] for r in self.history]
        days = (dates[-1] - dates[0]).days
        years = days / 365.0 if days > 0 else 1.0
        annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
        
        values = [r['total_value'] for r in self.history]
        running_max = np.maximum.accumulate(values)
        drawdown = (np.array(values) - running_max) / running_max
        max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0
        
        return {
            'initial_value': initial_value,
            'final_value': final_value,
            'total_return': total_return,
            'annual_return': annual_return,
            'max_drawdown': max_drawdown,
            'total_transactions': len(self.transactions),
            'months': len(self.history)
        }