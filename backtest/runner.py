import pandas as pd
from datetime import datetime, timedelta
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backtest.data_loader import BacktestDataLoader
from backtest.simulator import BacktestEngine
from backtest.strategy_adapter import StrategyAdapter
from backtest.metrics import calculate_metrics
import visualization


def run_backtest(start_date, end_date, monthly_budget):
    stock_list = ["招商银行", "兴业银行", "工商银行", "双汇发展", "159307"]

    print("="*60)
    print("开始回测")
    print("="*60)
    print(f"股票列表: {stock_list}")
    print(f"回测期间: {start_date} 至 {end_date}")
    print(f"月度预算: {monthly_budget}")
    print("="*60)

    data_loader = BacktestDataLoader('backtest_data')
    strategy_adapter = StrategyAdapter()
    engine = BacktestEngine(data_loader, strategy_adapter)

    history = engine.run_backtest(
        stock_list=stock_list,
        start_date=start_date,
        end_date=end_date,
        monthly_budget=monthly_budget
    )

    if not history:
        print("回测失败：未生成历史数据")
        return None

    for record in history:
        print(f"{record['date'][:10]} | 总市值: {record['total_value']:,.2f} | "
              f"持仓: {record['holdings_value']:,.2f} | 现金: {record['cash']:,.2f}")

    metrics = calculate_metrics(history)

    print("\n" + "="*60)
    print("回测绩效指标")
    print("="*60)
    print(f"总收益率: {metrics['total_return']*100:.2f}%")
    print(f"年化收益率: {metrics['annual_return']*100:.2f}%")
    print(f"最大回撤: {metrics['max_drawdown']*100:.2f}%")
    print(f"波动率: {metrics['volatility']*100:.2f}%")
    print(f"夏普比率: {metrics['sharpe']:.2f}")

    final_value = history[-1]['total_value'] if history else 0
    print(f"\n最终资产: {final_value:,.2f}")

    return {
        "history": history,
        "metrics": metrics,
        "final_value": final_value
    }


def run_backtest_demo():
    stock_list = ["招商银行", "兴业银行", "工商银行", "双汇发展", "159307"]

    start_date = "2018-01-01"
    end_date = "2024-12-31"

    monthly_budget = 3000

    print("="*60)
    print("开始回测演示")
    print("="*60)
    print(f"股票列表: {stock_list}")
    print(f"回测期间: {start_date} 至 {end_date}")
    print(f"月度预算: {monthly_budget}")
    print("="*60)

    data_loader = BacktestDataLoader('backtest_data')
    strategy_adapter = StrategyAdapter()
    engine = BacktestEngine(data_loader, strategy_adapter)

    history = engine.run_backtest(
        stock_list=stock_list,
        start_date=start_date,
        end_date=end_date,
        monthly_budget=monthly_budget
    )

    if not history:
        print("回测失败：未生成历史数据")
        return

    metrics = calculate_metrics(history)

    print("\n" + "="*60)
    print("回测绩效指标")
    print("="*60)
    print(f"总收益率: {metrics['total_return']*100:.2f}%")
    print(f"年化收益率: {metrics['annual_return']*100:.2f}%")
    print(f"最大回撤: {metrics['max_drawdown']*100:.2f}%")
    print(f"波动率: {metrics['volatility']*100:.2f}%")
    print(f"夏普比率: {metrics['sharpe']:.2f}")

    final_value = history[-1]['total_value'] if history else 0
    print(f"\n最终资产: {final_value:,.2f}")

    visualization.plot_backtest_result(history, metrics, output_dir='backtest_data')
    print(f"\n图表已保存至: backtest_data/")

    return history, metrics


class BacktestRunner:
    def __init__(self, data_loader, simulator, strategy_adapter, metrics):
        self.data_loader = data_loader
        self.simulator = simulator
        self.strategy_adapter = strategy_adapter
        self.metrics = metrics

    def run(self, stock_codes, start_date, end_date, initial_cash=100000.0,
            monthly_budget=3000.0, rebalance_frequency='monthly', output_dir='backtest_data'):
        os.makedirs(output_dir, exist_ok=True)

        self.simulator.reset(initial_cash)

        print(f"加载历史数据...")
        historical_data = self.data_loader.load_multiple_stocks(stock_codes, start_date, end_date)

        if not historical_data:
            print("警告：未能加载任何历史数据")
            return None

        for code in stock_codes:
            if code not in historical_data:
                print(f"警告：{code} 数据加载失败")

        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)

        dates = self._generate_trading_dates(start, end, rebalance_frequency)

        print(f"\n开始回测...")
        print(f"回测期间: {start_date} 至 {end_date}")
        print(f"初始资金: {initial_cash:,.2f}")
        print(f"月度预算: {monthly_budget:,.2f}")
        print(f"调仓频率: {rebalance_frequency}")

        for date in dates:
            self._process_date(date, historical_data, monthly_budget)

        results = self._generate_results(output_dir)
        return results

    def _generate_trading_dates(self, start, end, frequency):
        if frequency == 'daily':
            date_range = pd.date_range(start, end, freq='B')
            return date_range.tolist()
        elif frequency == 'weekly':
            date_range = pd.date_range(start, end, freq='W')
            return date_range.tolist()
        elif frequency == 'monthly':
            date_range = pd.date_range(start, end, freq='MS')
            return date_range.tolist()
        else:
            date_range = pd.date_range(start, end, freq='MS')
            return date_range.tolist()

    def _process_date(self, date, historical_data, monthly_budget):
        date = pd.to_datetime(date)
        self.simulator.set_date(date)

        snapshot = self._get_snapshot_at_date(historical_data, date)
        if not snapshot:
            return

        price_map = {}
        for stock in snapshot:
            price_map[stock['stock_code']] = stock.get('price', 0)

        holdings = self.simulator.get_current_holdings()
        total_value = self.simulator.get_portfolio_value(price_map)

        self._process_dividends(snapshot, holdings)

        dividend_reinvest_actions = self.strategy_adapter.reinvest_dividends(
            snapshot=snapshot,
            simulator=self.simulator,
            current_holdings=holdings,
            total_value=total_value
        )

        if dividend_reinvest_actions:
            print(f"\n【分红再投资】日期: {date.strftime('%Y-%m-%d')}")
            for action in dividend_reinvest_actions:
                print(f"  - 分红再投资买入: {action['stock_code']} @ {action['price']:.2f}")

        actions, _ = self.strategy_adapter.execute_rebalance(
            snapshot=snapshot,
            simulator=self.simulator,
            monthly_budget=monthly_budget,
            current_holdings=holdings,
            total_value=total_value
        )

        holdings_value = self.simulator.get_holdings_value(price_map)
        portfolio_value = self.simulator.get_portfolio_value(price_map)
        cash = self.simulator.cash

        self.metrics.add_daily_snapshot(date, portfolio_value, holdings_value, cash)

        if actions:
            tx_df = self.simulator.get_transactions_df()
            if not tx_df.empty:
                self.metrics.add_transactions(tx_df)

    def _get_snapshot_at_date(self, historical_data, date):
        snapshot = []
        current_date = pd.to_datetime(date)

        for stock_code, df in historical_data.items():
            df_dates = pd.to_datetime(df['date'])
            valid_dates = df_dates[df_dates <= current_date]

            if valid_dates.empty:
                continue

            closest_date = valid_dates[-1]
            row = df[df['date'] == closest_date].iloc[0]
            snapshot.append({
                'stock_code': stock_code,
                'stock_name': self._get_stock_name(stock_code),
                'price': row['close'],
                'open': row.get('open', row['close']),
                'high': row.get('high', row['close']),
                'low': row.get('low', row['close']),
                'volume': row.get('volume', 0),
                'pct_change': row.get('pct_change', 0),
                'turnover_rate': row.get('turnover_rate', 0),
                'pb': None,
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

    def _process_dividends(self, snapshot, holdings):
        pass

    def _generate_results(self, output_dir):
        transactions_df = self.simulator.get_transactions_df()
        dividends_df = self.simulator.get_dividends_df()

        if not transactions_df.empty:
            transactions_df.to_csv(os.path.join(output_dir, 'transactions.csv'), index=False)

        if not dividends_df.empty:
            dividends_df.to_csv(os.path.join(output_dir, 'dividends.csv'), index=False)

        portfolio_values = pd.DataFrame({
            'date': self.metrics.dates,
            'portfolio_value': self.metrics.portfolio_values
        })
        portfolio_values.to_csv(os.path.join(output_dir, 'portfolio_values.csv'), index=False)

        summary = self.metrics.get_summary()
        summary_df = pd.DataFrame([summary])
        summary_df.to_csv(os.path.join(output_dir, 'summary.csv'), index=False)

        self.metrics.print_summary()

        return {
            'summary': summary,
            'transactions': transactions_df,
            'dividends': dividends_df,
            'portfolio_values': portfolio_values
        }


if __name__ == '__main__':
    result = run_backtest(
        start_date="2023-01-01",
        end_date="2023-12-31",
        monthly_budget=3000
    )

    print("\n回测完成")
