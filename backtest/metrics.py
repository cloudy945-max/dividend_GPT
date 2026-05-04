import pandas as pd
import numpy as np
from datetime import datetime


def calculate_metrics(history):
    """
    根据回测历史计算绩效指标

    Args:
        history: 回测历史列表，每个元素包含 total_value, date 等字段

    Returns:
        {
            "total_return": 总收益率,
            "annual_return": 年化收益,
            "max_drawdown": 最大回撤,
            "volatility": 波动率,
            "sharpe": 夏普比率
        }
    """
    if not history or len(history) < 2:
        return {
            "total_return": 0.0,
            "annual_return": 0.0,
            "max_drawdown": 0.0,
            "volatility": 0.0,
            "sharpe": 0.0
        }

    df = pd.DataFrame(history)
    values = df['total_value'].values
    dates = pd.to_datetime(df['date'])

    initial_value = values[0]
    final_value = values[-1]

    total_return = (final_value - initial_value) / initial_value if initial_value > 0 else 0.0

    days = (dates.iloc[-1] - dates.iloc[0]).days
    years = days / 365.0 if days > 0 else 1.0
    annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0.0

    returns = np.diff(values) / values[:-1]
    returns = returns[~np.isnan(returns) & ~np.isinf(returns)]

    volatility = np.std(returns) * np.sqrt(252) if len(returns) > 0 else 0.0

    running_max = np.maximum.accumulate(values)
    drawdown = (values - running_max) / running_max
    max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0.0

    mean_return = np.mean(returns) * 252 if len(returns) > 0 else 0.0
    sharpe = (mean_return - 0.03) / volatility if volatility > 0 else 0.0

    return {
        "total_return": total_return,
        "annual_return": annual_return,
        "max_drawdown": max_drawdown,
        "volatility": volatility,
        "sharpe": sharpe
    }


class BacktestMetrics:
    def __init__(self):
        self.portfolio_values = []
        self.dates = []
        self.transactions = []
        self.dividends = []

    def add_daily_snapshot(self, date, portfolio_value, holdings_value, cash):
        self.dates.append(date)
        self.portfolio_values.append(portfolio_value)
        self.holdings_value = holdings_value
        self.cash = cash

    def add_transactions(self, transactions_df):
        if not transactions_df.empty:
            self.transactions.append(transactions_df)

    def add_dividends(self, dividends_df):
        if not dividends_df.empty:
            self.dividends.append(dividends_df)

    def calculate_returns(self):
        if len(self.portfolio_values) < 2:
            return {
                'total_return': 0.0,
                'annualized_return': 0.0
            }

        portfolio_values = np.array(self.portfolio_values)
        initial_value = portfolio_values[0]
        final_value = portfolio_values[-1]

        total_return = (final_value - initial_value) / initial_value if initial_value > 0 else 0.0

        dates = pd.to_datetime(self.dates)
        days = (dates[-1] - dates[0]).days
        if days > 0:
            years = days / 365.0
            annualized_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0.0
        else:
            annualized_return = 0.0

        return {
            'total_return': total_return,
            'annualized_return': annualized_return,
            'initial_value': initial_value,
            'final_value': final_value
        }

    def calculate_volatility(self):
        if len(self.portfolio_values) < 2:
            return 0.0

        portfolio_values = np.array(self.portfolio_values)
        returns = np.diff(portfolio_values) / portfolio_values[:-1]
        returns = returns[~np.isnan(returns) & ~np.isinf(returns)]

        if len(returns) == 0:
            return 0.0

        volatility = np.std(returns) if len(returns) > 1 else 0.0
        annualized_volatility = volatility * np.sqrt(252)

        return annualized_volatility

    def calculate_sharpe_ratio(self, risk_free_rate=0.03):
        if len(self.portfolio_values) < 2:
            return 0.0

        portfolio_values = np.array(self.portfolio_values)
        returns = np.diff(portfolio_values) / portfolio_values[:-1]
        returns = returns[~np.isnan(returns) & ~np.isinf(returns)]

        if len(returns) == 0:
            return 0.0

        mean_return = np.mean(returns) * 252
        volatility = np.std(returns) * np.sqrt(252)

        if volatility == 0:
            return 0.0

        sharpe = (mean_return - risk_free_rate) / volatility
        return sharpe

    def calculate_max_drawdown(self):
        if len(self.portfolio_values) < 2:
            return 0.0, None, None

        portfolio_values = np.array(self.portfolio_values)
        running_max = np.maximum.accumulate(portfolio_values)
        drawdown = (portfolio_values - running_max) / running_max

        max_dd = np.min(drawdown)
        max_dd_idx = np.argmin(drawdown)

        if max_dd_idx > 0:
            peak_idx = np.argmax(portfolio_values[:max_dd_idx])
            peak_date = self.dates[peak_idx]
            trough_date = self.dates[max_dd_idx]
        else:
            peak_date = self.dates[0]
            trough_date = self.dates[max_dd_idx]

        return max_dd, peak_date, trough_date

    def calculate_win_rate(self):
        if not self.transactions:
            return 0.0

        all_transactions = pd.concat(self.transactions, ignore_index=True)
        sell_transactions = all_transactions[all_transactions['type'] == 'sell']

        if sell_transactions.empty:
            return 0.0

        winning_trades = (sell_transactions['profit'] > 0).sum()
        total_trades = len(sell_transactions)

        return winning_trades / total_trades if total_trades > 0 else 0.0

    def calculate_profit_factor(self):
        if not self.transactions:
            return 0.0

        all_transactions = pd.concat(self.transactions, ignore_index=True)
        sell_transactions = all_transactions[all_transactions['type'] == 'sell']

        if sell_transactions.empty:
            return 0.0

        gross_profit = sell_transactions[sell_transactions['profit'] > 0]['profit'].sum()
        gross_loss = abs(sell_transactions[sell_transactions['profit'] < 0]['profit'].sum())

        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0.0

        return gross_profit / gross_loss

    def calculate_total_dividends(self):
        if not self.dividends:
            return 0.0

        all_dividends = pd.concat(self.dividends, ignore_index=True)
        return all_dividends['amount'].sum()

    def calculate_monthly_returns(self):
        if len(self.portfolio_values) < 2:
            return pd.DataFrame()

        df = pd.DataFrame({
            'date': self.dates,
            'portfolio_value': self.portfolio_values
        })
        df['date'] = pd.to_datetime(df['date'])
        df['month'] = df['date'].dt.to_period('M')
        df['return'] = df['portfolio_value'].pct_change()

        monthly_returns = df.groupby('month').agg({
            'portfolio_value': 'last',
            'return': 'sum'
        }).reset_index()

        return monthly_returns

    def get_summary(self):
        returns = self.calculate_returns()
        volatility = self.calculate_volatility()
        sharpe = self.calculate_sharpe_ratio()
        max_dd, peak_date, trough_date = self.calculate_max_drawdown()
        win_rate = self.calculate_win_rate()
        profit_factor = self.calculate_profit_factor()
        total_dividends = self.calculate_total_dividends()

        return {
            'total_return': returns['total_return'],
            'annualized_return': returns['annualized_return'],
            'initial_value': returns['initial_value'],
            'final_value': returns['final_value'],
            'volatility': volatility,
            'sharpe_ratio': sharpe,
            'max_drawdown': max_dd,
            'max_drawdown_peak': peak_date,
            'max_drawdown_trough': trough_date,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'total_dividends': total_dividends,
            'total_trades': len(pd.concat(self.transactions, ignore_index=True)) if self.transactions else 0
        }

    def print_summary(self):
        summary = self.get_summary()

        print("\n" + "="*60)
        print("回测绩效报告")
        print("="*60)

        print(f"\n收益率指标:")
        print(f"  总收益率: {summary['total_return']*100:.2f}%")
        print(f"  年化收益率: {summary['annualized_return']*100:.2f}%")

        print(f"\n风险指标:")
        print(f"  年化波动率: {summary['volatility']*100:.2f}%")
        print(f"  最大回撤: {summary['max_drawdown']*100:.2f}%")

        print(f"\n风险调整收益:")
        print(f"  夏普比率: {summary['sharpe_ratio']:.2f}")

        print(f"\n交易统计:")
        print(f"  总交易次数: {summary['total_trades']}")
        print(f"  胜率: {summary['win_rate']*100:.2f}%")
        print(f"  盈利因子: {summary['profit_factor']:.2f}")

        print(f"\n分红收入:")
        print(f"  总分红: {summary['total_dividends']:.2f}")

        print(f"\n资产变化:")
        print(f"  初始资产: {summary['initial_value']:,.2f}")
        print(f"  最终资产: {summary['final_value']:,.2f}")

        print("\n" + "="*60)
