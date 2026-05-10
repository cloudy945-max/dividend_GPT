import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backtest.data_loader import BacktestDataLoader
from backtest.simulator import BacktestEngine
from backtest.strategy_adapter import StrategyAdapter
from backtest.metrics import calculate_metrics, BacktestMetrics

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('backtest_data/runner.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def run_backtest(start_date, end_date, monthly_budget=3000):
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
        date_str = record['date'].strftime('%Y-%m-%d') if hasattr(record['date'], 'strftime') else str(record['date'])[:10]
        print(f"{date_str} | 总市值: {record['total_value']:,.2f} | "
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
        "final_value": final_value,
        "transactions": engine.get_transactions_df()
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

    try:
        import visualization
        visualization.plot_backtest_result(history, metrics, output_dir='backtest_data')
        print(f"\n图表已保存至: backtest_data/")
    except ImportError:
        print("\n可视化模块未安装，跳过图表生成")

    return history, metrics


def generate_benchmark_equally_weighted(start_date, end_date, monthly_budget, price_data):
    dates = []
    values = []
    
    holdings = {}
    cash = 0
    
    stock_list = list(price_data.keys())
    n_stocks = len([s for s in stock_list if s != "159307"])
    
    for stock in stock_list:
        holdings[stock] = 0
    
    monthly_dates = pd.date_range(start_date, end_date, freq='MS')
    
    for date in monthly_dates:
        cash += monthly_budget
        
        price_map = {}
        for stock_code in stock_list:
            df = price_data.get(stock_code)
            if df is not None and not df.empty:
                valid_dates = df[df['date'] <= date]
                if not valid_dates.empty:
                    price_map[stock_code] = valid_dates.iloc[-1]['close']
        
        budget_per_stock = cash / n_stocks
        
        for stock_code in stock_list:
            if stock_code == "159307":
                continue
            
            price = price_map.get(stock_code, 0)
            if price > 0 and budget_per_stock >= price * 100:
                shares = int(budget_per_stock // (price * 100)) * 100
                cost = shares * price
                holdings[stock_code] += shares
                cash -= cost
        
        total_value = cash
        for stock_code, shares in holdings.items():
            price = price_map.get(stock_code, 0)
            total_value += shares * price
        
        dates.append(date)
        values.append(total_value)
    
    return dates, values


def generate_benchmark_simple_hold(start_date, end_date, initial_cash, price_data):
    dates = []
    values = []
    
    stock_list = list(price_data.keys())
    n_stocks = len(stock_list)
    
    holdings = {}
    cash = initial_cash
    
    first_date = pd.to_datetime(start_date)
    price_map = {}
    for stock_code in stock_list:
        df = price_data.get(stock_code)
        if df is not None and not df.empty:
            valid_dates = df[df['date'] >= first_date]
            if not valid_dates.empty:
                price_map[stock_code] = valid_dates.iloc[0]['close']
    
    budget_per_stock = cash / n_stocks
    for stock_code in stock_list:
        price = price_map.get(stock_code, 0)
        if price > 0 and budget_per_stock >= price * 100:
            shares = int(budget_per_stock // (price * 100)) * 100
            cost = shares * price
            holdings[stock_code] = shares
            cash -= cost
    
    all_dates = []
    for stock_code in stock_list:
        df = price_data.get(stock_code)
        if df is not None and not df.empty:
            all_dates.extend(df['date'].tolist())
    
    unique_dates = sorted(set(all_dates))
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    valid_dates = [d for d in unique_dates if start_dt <= pd.to_datetime(d) <= end_dt]
    
    for date in valid_dates:
        date_dt = pd.to_datetime(date)
        price_map = {}
        for stock_code in stock_list:
            df = price_data.get(stock_code)
            if df is not None and not df.empty:
                valid_dates_df = df[df['date'] <= date_dt]
                if not valid_dates_df.empty:
                    price_map[stock_code] = valid_dates_df.iloc[-1]['close']
        
        total_value = cash
        for stock_code, shares in holdings.items():
            price = price_map.get(stock_code, 0)
            total_value += shares * price
        
        dates.append(date_dt)
        values.append(total_value)
    
    return dates, values


def run_full_backtest(start_date, end_date, initial_cash=100000, monthly_budget=3000, output_dir='backtest_output'):
    """
    完整回测主函数
    
    Args:
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        initial_cash: 初始现金（已废弃，保留兼容性）
        monthly_budget: 月度预算
        output_dir: 输出目录
    
    Returns:
        {
            'history': 回测历史记录,
            'metrics': 绩效指标,
            'transactions': 交易记录DataFrame,
            'report': 报告路径
        }
    """
    os.makedirs(output_dir, exist_ok=True)
    
    stock_list = ["招商银行", "兴业银行", "工商银行", "双汇发展", "159307"]
    
    logger.info(f"="*60)
    logger.info("开始完整回测")
    logger.info(f"股票列表: {stock_list}")
    logger.info(f"回测期间: {start_date} 至 {end_date}")
    logger.info(f"月度预算: {monthly_budget}")
    logger.info(f"输出目录: {output_dir}")
    logger.info("="*60)

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
        logger.error("回测失败：未生成历史数据")
        return None

    price_data = data_loader.load_price_history(stock_list, start_date, end_date)
    
    bench_dates_eq, bench_values_eq = generate_benchmark_equally_weighted(start_date, end_date, monthly_budget, price_data)
    
    metrics = calculate_metrics(history)
    
    transactions_df = engine.get_transactions_df()
    history_df = engine.get_history_df()

    report_path = generate_backtest_report(
        history=history,
        metrics=metrics,
        transactions_df=transactions_df,
        benchmark_dates=bench_dates_eq,
        benchmark_values=bench_values_eq,
        benchmark_name="等权重定投",
        start_date=start_date,
        end_date=end_date,
        monthly_budget=monthly_budget,
        output_dir=output_dir
    )
    
    logger.info(f"\n回测完成！报告已保存至: {report_path}")

    return {
        'history': history,
        'metrics': metrics,
        'transactions': transactions_df,
        'history_df': history_df,
        'report_path': report_path
    }


def generate_backtest_report(history, metrics, transactions_df, benchmark_dates=None, 
                            benchmark_values=None, benchmark_name="基准",
                            start_date=None, end_date=None, monthly_budget=None,
                            output_dir='backtest_output'):
    report_lines = []
    
    report_lines.append("# 回测绩效报告")
    report_lines.append("")
    report_lines.append("## 回测概览")
    report_lines.append("")
    
    if start_date and end_date:
        report_lines.append(f"- **回测期间**: {start_date} 至 {end_date}")
    if monthly_budget:
        report_lines.append(f"- **月度预算**: {monthly_budget:,.2f} 元")
    
    report_lines.append("")
    report_lines.append("## 绩效指标")
    report_lines.append("")
    report_lines.append("| 指标 | 值 |")
    report_lines.append("|------|-----|")
    report_lines.append(f"| 总收益率 | {metrics['total_return']*100:.2f}% |")
    report_lines.append(f"| 年化收益率 | {metrics['annual_return']*100:.2f}% |")
    report_lines.append(f"| 最大回撤 | {metrics['max_drawdown']*100:.2f}% |")
    report_lines.append(f"| 波动率 | {metrics['volatility']*100:.2f}% |")
    report_lines.append(f"| 夏普比率 | {metrics['sharpe']:.2f} |")
    
    if 'calmar' in metrics:
        report_lines.append(f"| Calmar比率 | {metrics['calmar']:.2f} |")
    if 'irr' in metrics:
        report_lines.append(f"| IRR | {metrics['irr']*100:.2f}% |")
    
    if history:
        first_value = history[0]['total_value']
        last_value = history[-1]['total_value']
        report_lines.append(f"| 初始资产 | {first_value:,.2f} |")
        report_lines.append(f"| 最终资产 | {last_value:,.2f} |")
        report_lines.append(f"| 累计投入 | {len(history) * monthly_budget:,.2f} |")
    
    report_lines.append("")
    report_lines.append("## 收益曲线数据")
    report_lines.append("")
    report_lines.append("| 日期 | 总资产 | 持仓价值 | 现金 | 资金池 |")
    report_lines.append("|------|--------|----------|------|--------|")
    
    for record in history:
        date_str = record['date'].strftime('%Y-%m-%d') if hasattr(record['date'], 'strftime') else str(record['date'])[:10]
        report_lines.append(f"| {date_str} | {record['total_value']:,.2f} | {record['holdings_value']:,.2f} | {record['cash']:,.2f} | {record['cash_pool']:,.2f} |")
    
    report_lines.append("")
    report_lines.append("## 交易记录")
    report_lines.append("")
    
    if transactions_df is not None and not transactions_df.empty:
        report_lines.append("| 日期 | 类型 | 标的 | 股数 | 价格 | 成本 | 原因 |")
        report_lines.append("|------|------|------|------|------|------|------|")
        
        for _, row in transactions_df.iterrows():
            date_str = row['date'].strftime('%Y-%m-%d') if hasattr(row['date'], 'strftime') else str(row['date'])[:10]
            reason = row.get('reason', '')
            report_lines.append(f"| {date_str} | {row['type']} | {row['stock_name']} | {row['shares']} | {row['price']:.2f} | {row['cost']:,.2f} | {reason} |")
    else:
        report_lines.append("无交易记录")
    
    report_lines.append("")
    report_lines.append("## 买入原因统计")
    report_lines.append("")
    
    if transactions_df is not None and not transactions_df.empty:
        reason_counts = transactions_df['reason'].value_counts().to_dict()
        total_txs = len(transactions_df)
        
        report_lines.append("| 原因 | 次数 | 占比 |")
        report_lines.append("|------|------|------|")
        
        for reason, count in reason_counts.items():
            report_lines.append(f"| {reason} | {count} | {(count/total_txs*100):.1f}% |")
    
    report_lines.append("")
    report_lines.append("## 基准对比")
    report_lines.append("")
    
    if benchmark_dates and benchmark_values and len(benchmark_dates) > 0:
        bench_initial = benchmark_values[0]
        bench_final = benchmark_values[-1]
        bench_total_return = (bench_final - bench_initial) / bench_initial if bench_initial > 0 else 0
        
        days = (benchmark_dates[-1] - benchmark_dates[0]).days
        bench_years = days / 365.0 if days > 0 else 1.0
        bench_annual_return = (1 + bench_total_return) ** (1 / bench_years) - 1 if bench_years > 0 else 0
        
        report_lines.append("| 指标 | 策略 | 基准 |")
        report_lines.append("|------|------|------|")
        report_lines.append(f"| 总收益率 | {metrics['total_return']*100:.2f}% | {bench_total_return*100:.2f}% |")
        report_lines.append(f"| 年化收益率 | {metrics['annual_return']*100:.2f}% | {bench_annual_return*100:.2f}% |")
        
        if 'max_drawdown' in metrics:
            report_lines.append(f"| 最大回撤 | {metrics['max_drawdown']*100:.2f}% | - |")
    else:
        report_lines.append("无基准数据")
    
    report_lines.append("")
    report_lines.append("---")
    report_lines.append(f"报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    report_content = "\n".join(report_lines)
    report_path = os.path.join(output_dir, 'backtest_report.md')
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_content)
    
    return report_path


class BacktestRunner:
    def __init__(self, data_loader=None, simulator=None, strategy_adapter=None):
        self.data_loader = data_loader or BacktestDataLoader('backtest_data')
        self.strategy_adapter = strategy_adapter or StrategyAdapter()
        self.simulator = simulator
        self.metrics = BacktestMetrics()

    def run(self, stock_codes, start_date, end_date, initial_cash=100000.0,
            monthly_budget=3000.0, rebalance_frequency='monthly', output_dir='backtest_data'):
        os.makedirs(output_dir, exist_ok=True)

        if self.simulator:
            self.simulator.reset(initial_cash)

        logger.info(f"加载历史数据...")
        historical_data = self.data_loader.load_multiple_stocks(stock_codes, start_date, end_date)

        if not historical_data:
            logger.warning("未能加载任何历史数据")
            return None

        for code in stock_codes:
            if code not in historical_data:
                logger.warning(f"{code} 数据加载失败")

        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)

        dates = self._generate_trading_dates(start, end, rebalance_frequency)

        logger.info(f"\n开始回测...")
        logger.info(f"回测期间: {start_date} 至 {end_date}")
        logger.info(f"初始资金: {initial_cash:,.2f}")
        logger.info(f"月度预算: {monthly_budget:,.2f}")
        logger.info(f"调仓频率: {rebalance_frequency}")

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
        if self.simulator:
            self.simulator.set_date(date)

        snapshot = self._get_snapshot_at_date(historical_data, date)
        if not snapshot:
            return

        price_map = {}
        for stock in snapshot:
            price_map[stock['stock_code']] = stock.get('price', 0)

        holdings = {}
        if self.simulator:
            holdings = self.simulator.get_current_holdings()
        total_value = 0
        if self.simulator:
            total_value = self.simulator.get_portfolio_value(price_map)

        self._process_dividends(snapshot, holdings)

        dividend_reinvest_actions = []
        if self.simulator:
            dividend_reinvest_actions = self.strategy_adapter.reinvest_dividends(
                snapshot=snapshot,
                simulator=self.simulator,
                current_holdings=holdings,
                total_value=total_value
            )

        if dividend_reinvest_actions:
            logger.info(f"\n【分红再投资】日期: {date.strftime('%Y-%m-%d')}")
            for action in dividend_reinvest_actions:
                logger.info(f"  - 分红再投资买入: {action['stock_name']} @ {action['price']:.2f}")

        actions = []
        if self.simulator:
            actions, _ = self.strategy_adapter.execute_rebalance(
                snapshot=snapshot,
                simulator=self.simulator,
                monthly_budget=monthly_budget,
                current_holdings=holdings,
                total_value=total_value
            )

        holdings_value = {}
        if self.simulator:
            holdings_value = self.simulator.get_holdings_value(price_map)
        portfolio_value = 0
        if self.simulator:
            portfolio_value = self.simulator.get_portfolio_value(price_map)
        cash = 0
        if self.simulator:
            cash = self.simulator.cash

        self.metrics.add_daily_snapshot(date, portfolio_value, holdings_value, cash)

        if actions:
            tx_df = None
            if self.simulator:
                tx_df = self.simulator.get_transactions_df()
            if tx_df is not None and not tx_df.empty:
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
        transactions_df = pd.DataFrame()
        if self.simulator:
            transactions_df = self.simulator.get_transactions_df()
        dividends_df = pd.DataFrame()
        if self.simulator:
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