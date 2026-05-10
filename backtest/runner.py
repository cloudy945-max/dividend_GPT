#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
回测运行器 - 提供完整回测流程和报告生成功能
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import sys
import logging
from typing import Dict, List, Optional, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.data_loader import BacktestDataLoader
from backtest.simulator import BacktestEngine
from backtest.strategy_adapter import StrategyAdapter
from backtest.metrics import calculate_metrics
from backtest.config import (
    LOG_DIR, OUTPUT_DIR, get_stock_list, ETF_CODE, BENCHMARK_CODES, 
    MONTHLY_BUDGET, PLOT_WIDTH, PLOT_HEIGHT, PLOT_DPI,
    PLOT_COLORS, FONT_FAMILIES, FONT_SIZE, TITLE_FONT_SIZE, LABEL_FONT_SIZE,
    GRID_ALPHA, LINE_WIDTH, LINE_WIDTH_BENCHMARK
)

# ==================== 可视化辅助函数 ====================
def setup_matplotlib_chinese():
    """设置matplotlib支持中文显示"""
    try:
        import matplotlib.pyplot as plt
        from matplotlib import rcParams
        
        # 设置字体
        rcParams['font.sans-serif'] = FONT_FAMILIES
        rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
        
        # 设置默认字体大小
        rcParams['font.size'] = FONT_SIZE
        rcParams['axes.titlesize'] = TITLE_FONT_SIZE
        rcParams['axes.labelsize'] = LABEL_FONT_SIZE
        rcParams['xtick.labelsize'] = FONT_SIZE
        rcParams['ytick.labelsize'] = FONT_SIZE
        rcParams['legend.fontsize'] = FONT_SIZE
        
        logger.info("matplotlib中文显示设置成功")
        return True
    except ImportError:
        logger.warning("matplotlib未安装，跳过中文显示设置")
        return False
    except Exception as e:
        logger.warning(f"设置matplotlib中文显示失败: {e}")
        return False

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'runner.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def run_backtest(start_date: str, end_date: str, monthly_budget: float = MONTHLY_BUDGET) -> Optional[Dict[str, Any]]:
    """
    简单回测接口
    
    Args:
        start_date: 开始日期
        end_date: 结束日期
        monthly_budget: 月度预算
        
    Returns:
        回测结果
    """
    stock_list = get_stock_list() + [ETF_CODE]

    print("="*60)
    print("开始回测")
    print("="*60)
    print(f"股票列表: {stock_list}")
    print(f"回测期间: {start_date} 至 {end_date}")
    print(f"月度预算: {monthly_budget}")
    print("="*60)

    data_loader = BacktestDataLoader()
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


def generate_benchmark_equally_weighted(start_date: str, end_date: str, monthly_budget: float, 
                                         price_data: Dict[str, pd.DataFrame]) -> tuple:
    """
    生成等权重定投基准
    
    Args:
        start_date: 开始日期
        end_date: 结束日期
        monthly_budget: 月度预算
        price_data: 价格数据
        
    Returns:
        (日期列表, 价值列表)
    """
    dates = []
    values = []
    
    holdings = {}
    cash = 0
    
    stock_list = list(price_data.keys())
    n_stocks = len([s for s in stock_list if s != ETF_CODE])
    
    for stock in stock_list:
        holdings[stock] = 0
    
    from backtest.data_loader import get_monthly_trading_dates
    monthly_dates = get_monthly_trading_dates(start_date, end_date)
    
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
            if stock_code == ETF_CODE:
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


def generate_benchmark_index(start_date: str, end_date: str, index_code: str, 
                             data_loader: BacktestDataLoader) -> tuple:
    """
    生成指数基准（如沪深300）
    
    Args:
        start_date: 开始日期
        end_date: 结束日期
        index_code: 指数代码
        data_loader: 数据加载器
        
    Returns:
        (日期列表, 价值列表)
    """
    dates = []
    values = []
    
    price_data = data_loader.load_price_history([index_code], start_date, end_date)
    
    if index_code not in price_data:
        logger.warning(f"无法加载 {index_code} 数据")
        return dates, values
    
    df = price_data[index_code]
    if df.empty:
        return dates, values
    
    initial_price = df.iloc[0]['close']
    
    from backtest.data_loader import get_monthly_trading_dates
    monthly_dates = get_monthly_trading_dates(start_date, end_date)
    
    for date in monthly_dates:
        valid_dates = df[df['date'] <= date]
        if not valid_dates.empty:
            current_price = valid_dates.iloc[-1]['close']
            dates.append(date)
            values.append(current_price / initial_price)
    
    return dates, values


def calculate_excess_metrics(strategy_history: List[Dict[str, Any]], 
                              benchmark_values: List[float]) -> Dict[str, float]:
    """
    计算超额收益指标
    
    Args:
        strategy_history: 策略历史
        benchmark_values: 基准价值序列
        
    Returns:
        超额收益指标
    """
    if not strategy_history or not benchmark_values:
        return {}
    
    strategy_values = [h['total_value'] for h in strategy_history]
    
    # 确保两个序列长度相同
    min_length = min(len(strategy_values), len(benchmark_values))
    if min_length < 2:
        return {}
    
    strategy_values = strategy_values[:min_length]
    benchmark_values = benchmark_values[:min_length]
    
    initial_strategy = strategy_values[0]
    initial_benchmark = benchmark_values[0]
    
    # 标准化到相同起点
    strategy_normalized = [v / initial_strategy for v in strategy_values]
    benchmark_normalized = [v / initial_benchmark for v in benchmark_values]
    
    # 超额收益
    excess_returns = np.array(strategy_normalized) - np.array(benchmark_normalized)
    
    # 累计超额收益
    total_excess_return = excess_returns[-1] if len(excess_returns) > 0 else 0
    
    # 超额收益波动率
    excess_volatility = np.std(excess_returns) * np.sqrt(12)  # 年化
    
    # 信息比率
    information_ratio = total_excess_return / excess_volatility if excess_volatility > 0 else 0
    
    # 超额最大回撤
    excess_cumulative = np.cumsum(excess_returns)
    excess_running_max = np.maximum.accumulate(excess_cumulative)
    excess_drawdown = (excess_cumulative - excess_running_max) / excess_running_max if excess_running_max[0] != 0 else excess_cumulative - excess_running_max
    max_excess_drawdown = np.min(excess_drawdown) if len(excess_drawdown) > 0 else 0
    
    return {
        'total_excess_return': total_excess_return,
        'excess_volatility': excess_volatility,
        'information_ratio': information_ratio,
        'max_excess_drawdown': max_excess_drawdown
    }


def plot_equity_curve(history: List[Dict[str, Any]], 
                      benchmark_data: Dict[str, tuple],
                      output_path: str) -> None:
    """
    绘制权益曲线（优化版）
    
    Args:
        history: 策略历史
        benchmark_data: 基准数据 {name: (dates, values)}
        output_path: 输出路径
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        
        # 设置中文显示
        setup_matplotlib_chinese()
        
        fig, ax = plt.subplots(figsize=(PLOT_WIDTH/100, PLOT_HEIGHT/100), dpi=PLOT_DPI)
        
        # 策略曲线
        dates = [h['date'] for h in history]
        values = [h['total_value'] for h in history]
        initial_value = values[0]
        normalized_values = [v / initial_value for v in values]
        
        # 绘制策略曲线（带填充效果）
        ax.plot(dates, normalized_values, label='策略', 
                linewidth=LINE_WIDTH, color=PLOT_COLORS['strategy'], zorder=3)
        ax.fill_between(dates, normalized_values, 1, 
                        color=PLOT_COLORS['equity_fill'], alpha=0.3, zorder=2)
        
        # 基准曲线
        benchmark_colors = ['benchmark1', 'benchmark2', 'benchmark3']
        color_idx = 0
        
        for name, (bench_dates, bench_values) in benchmark_data.items():
            if bench_dates and bench_values:
                bench_initial = bench_values[0]
                bench_normalized = [v / bench_initial for v in bench_values]
                ax.plot(bench_dates, bench_normalized, label=name, 
                        linewidth=LINE_WIDTH_BENCHMARK, 
                        color=PLOT_COLORS.get(benchmark_colors[color_idx % len(benchmark_colors)], '#9467bd'),
                        linestyle='--', zorder=2)
                color_idx += 1
        
        # 添加基准线
        ax.axhline(y=1, color='gray', linestyle=':', linewidth=1, alpha=0.5, zorder=1)
        
        # 设置坐标轴和标题
        ax.set_title('策略与基准权益曲线对比', fontsize=TITLE_FONT_SIZE, fontweight='bold')
        ax.set_xlabel('日期', fontsize=LABEL_FONT_SIZE)
        ax.set_ylabel('累计收益 (归一化)', fontsize=LABEL_FONT_SIZE)
        
        # 设置图例
        ax.legend(fontsize=FONT_SIZE, loc='upper left', framealpha=0.9)
        
        # 设置网格
        ax.grid(True, alpha=GRID_ALPHA, linestyle='-', zorder=0)
        ax.set_axisbelow(True)  # 确保网格在曲线下方
        
        # 设置日期格式
        fig.autofmt_xdate()
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=PLOT_DPI, bbox_inches='tight', facecolor='white')
        plt.close()
        
        logger.info(f"权益曲线图表已保存: {output_path}")
        
    except ImportError:
        logger.warning("matplotlib未安装，跳过图表生成")


def plot_drawdown_curve(history: List[Dict[str, Any]], output_path: str) -> None:
    """
    绘制回撤曲线（优化版）
    
    Args:
        history: 策略历史
        output_path: 输出路径
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        
        # 设置中文显示
        setup_matplotlib_chinese()
        
        fig, ax = plt.subplots(figsize=(PLOT_WIDTH/100, PLOT_HEIGHT/100), dpi=PLOT_DPI)
        
        values = [h['total_value'] for h in history]
        dates = [h['date'] for h in history]
        
        running_max = np.maximum.accumulate(values)
        drawdown = (np.array(values) - running_max) / running_max
        
        # 计算最大回撤值和位置
        max_dd_value = np.min(drawdown)
        max_dd_idx = np.argmin(drawdown)
        max_dd_date = dates[max_dd_idx]
        
        # 绘制回撤曲线
        ax.fill_between(dates, drawdown, 0, where=drawdown < 0, 
                         color=PLOT_COLORS['drawdown_fill'], alpha=0.5, 
                         label='回撤', zorder=2)
        ax.plot(dates, drawdown, color=PLOT_COLORS['drawdown'], 
                linewidth=LINE_WIDTH, zorder=3)
        
        # 标注最大回撤点
        ax.scatter(max_dd_date, max_dd_value, color=PLOT_COLORS['drawdown'], 
                   s=50, zorder=4, edgecolor='black', linewidth=1)
        ax.annotate(f'最大回撤: {max_dd_value*100:.2f}%',
                    xy=(max_dd_date, max_dd_value),
                    xytext=(max_dd_date, max_dd_value - 0.05),
                    arrowprops=dict(arrowstyle='->', color='black'),
                    fontsize=FONT_SIZE,
                    ha='center', va='top')
        
        # 添加基准线
        ax.axhline(y=0, color='gray', linestyle='-', linewidth=1, alpha=0.5, zorder=1)
        
        # 设置坐标轴和标题
        ax.set_title('策略回撤曲线', fontsize=TITLE_FONT_SIZE, fontweight='bold')
        ax.set_xlabel('日期', fontsize=LABEL_FONT_SIZE)
        ax.set_ylabel('回撤率', fontsize=LABEL_FONT_SIZE)
        
        # 设置Y轴为百分比格式
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x*100:.0f}%'))
        
        # 设置图例
        ax.legend(fontsize=FONT_SIZE, loc='upper right', framealpha=0.9)
        
        # 设置网格
        ax.grid(True, alpha=GRID_ALPHA, linestyle='-', zorder=0)
        ax.set_axisbelow(True)
        
        # 设置日期格式
        fig.autofmt_xdate()
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=PLOT_DPI, bbox_inches='tight', facecolor='white')
        plt.close()
        
        logger.info(f"回撤曲线图表已保存: {output_path}")
        
    except ImportError:
        logger.warning("matplotlib未安装，跳过图表生成")


def plot_asset_allocation(history: List[Dict[str, Any]], output_path: str, 
                          price_data: Optional[Dict[str, pd.DataFrame]] = None) -> None:
    """
    绘制资产配置变化图（堆叠面积图）
    
    Args:
        history: 策略历史
        output_path: 输出路径
        price_data: 价格数据字典，用于计算持仓市值
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        from matplotlib.colors import ListedColormap
        
        # 设置中文显示
        setup_matplotlib_chinese()
        
        if not history:
            logger.warning("历史数据为空，跳过资产配置图表生成")
            return
        
        dates = [h['date'] for h in history]
        all_stocks = set()
        
        # 收集所有出现过的持仓股票
        for record in history:
            all_stocks.update(record['holdings'].keys())
        
        stocks = sorted(list(all_stocks))
        
        if not stocks:
            logger.warning("无持仓数据，添加现金类目")
        
        # 确保包含现金分类
        categories = stocks.copy()
        if '现金' not in categories:
            categories.append('现金')
        
        # 构建专业配色方案
        colors = [
            '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', 
            '#9467bd', '#8c564b', '#e377c2', '#7f7f7f',
            '#bcbd22', '#17becf'
        ]
        cmap = ListedColormap(colors[:len(categories)])
        
        # 计算各分类的市值
        allocation_data = []
        for record in history:
            total_value = record['total_value']
            if total_value <= 0:
                # 如果总资产为0，全部为现金
                row = {cat: 0.0 for cat in categories}
                row['现金'] = 1.0
                allocation_data.append(row)
                continue
            
            row = {}
            
            # 计算各持仓占比（注意：这里假设history记录中有详细市值）
            # 我们需要用外推的方式计算各股票市值
            # 首先计算总持仓市值
            holdings_value = record.get('holdings_value', 0)
            
            # 计算现金和资金池占比
            cash_total = record.get('cash', 0) + record.get('cash_pool', 0)
            row['现金'] = cash_total / total_value if total_value > 0 else 0.0
            
            # 估算各股票占比（基于持仓股数平均分配，实际应该用price_data）
            total_shares = sum(record['holdings'].values())
            for stock in stocks:
                if stock in record['holdings'] and total_shares > 0:
                    # 用简单比例估算，实际可以根据price_data精确计算
                    row[stock] = (holdings_value * record['holdings'][stock] / total_shares) / total_value
                else:
                    row[stock] = 0.0
            
            allocation_data.append(row)
        
        # 转换为numpy数组用于绘图
        plot_data = []
        for cat in categories:
            plot_data.append([row.get(cat, 0.0) for row in allocation_data])
        
        plot_data = np.array(plot_data)
        
        # 创建图表
        fig, ax = plt.subplots(figsize=(PLOT_WIDTH/100, PLOT_HEIGHT/100), dpi=PLOT_DPI)
        
        # 绘制堆叠面积图
        ax.stackplot(dates, plot_data, labels=categories, alpha=0.85, colors=cmap.colors)
        
        # 设置标题和标签
        ax.set_title('资产配置变化图', fontsize=TITLE_FONT_SIZE, fontweight='bold', pad=15)
        ax.set_xlabel('日期', fontsize=LABEL_FONT_SIZE, labelpad=10)
        ax.set_ylabel('资产占比', fontsize=LABEL_FONT_SIZE, labelpad=10)
        
        # 设置Y轴为百分比
        ax.set_ylim(0, 1.0)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x*100:.0f}%'))
        
        # 设置图例，放在图表外避免遮挡
        ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1), fontsize=FONT_SIZE*0.8, borderaxespad=0)
        
        # 设置网格
        ax.grid(True, alpha=GRID_ALPHA, linestyle='-', zorder=0)
        ax.set_axisbelow(True)
        
        # 设置日期格式
        fig.autofmt_xdate()
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=PLOT_DPI, bbox_inches='tight', facecolor='white')
        plt.close()
        
        logger.info(f"资产配置图表已保存: {output_path}")
        
    except ImportError:
        logger.warning("matplotlib未安装，跳过图表生成")
    except Exception as e:
        logger.error(f"资产配置图表生成失败: {str(e)}", exc_info=True)


def run_full_backtest(start_date: str, end_date: str, 
                      initial_cash: float = 100000, monthly_budget: float = MONTHLY_BUDGET, 
                      output_dir: str = OUTPUT_DIR, use_cache_only: bool = False) -> Optional[Dict[str, Any]]:
    """
    完整回测主函数
    
    Args:
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        initial_cash: 初始现金（已废弃，保留兼容性）
        monthly_budget: 月度预算
        output_dir: 输出目录
        use_cache_only: 是否仅使用缓存（不联网）
        
    Returns:
        {
            'history': 回测历史记录,
            'metrics': 绩效指标,
            'transactions': 交易记录DataFrame,
            'report_path': 报告路径
        }
    """
    os.makedirs(output_dir, exist_ok=True)
    
    stock_list = get_stock_list() + [ETF_CODE]
    
    logger.info(f"="*60)
    logger.info("开始完整回测")
    logger.info(f"股票列表: {stock_list}")
    logger.info(f"回测期间: {start_date} 至 {end_date}")
    logger.info(f"月度预算: {monthly_budget}")
    logger.info(f"输出目录: {output_dir}")
    logger.info(f"仅使用缓存: {use_cache_only}")
    logger.info("="*60)
    
    # 导入进度条库
    try:
        from tqdm import tqdm
        TQDM_AVAILABLE = True
    except ImportError:
        TQDM_AVAILABLE = False
        logger.info("tqdm未安装，不显示进度条")

    data_loader = BacktestDataLoader(use_cache_only=use_cache_only)
    strategy_adapter = StrategyAdapter()
    engine = BacktestEngine(data_loader, strategy_adapter)

    # 显示数据加载进度
    if TQDM_AVAILABLE:
        with tqdm(total=100, desc="加载数据", unit="%", ncols=80) as pbar:
            pbar.update(20)
            history = engine.run_backtest(
                stock_list=stock_list,
                start_date=start_date,
                end_date=end_date,
                monthly_budget=monthly_budget
            )
            pbar.update(60)
    else:
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
    
    # 生成基准数据
    benchmark_data = {}
    
    # 等权重定投基准
    bench_dates_eq, bench_values_eq = generate_benchmark_equally_weighted(start_date, end_date, monthly_budget, price_data)
    if bench_dates_eq and bench_values_eq:
        benchmark_data['等权重定投'] = (bench_dates_eq, bench_values_eq)
    
    # 沪深300基准
    hs300_code = BENCHMARK_CODES.get('沪深300')
    if hs300_code:
        bench_dates_hs300, bench_values_hs300 = generate_benchmark_index(start_date, end_date, hs300_code, data_loader)
        if bench_dates_hs300 and bench_values_hs300:
            benchmark_data['沪深300'] = (bench_dates_hs300, bench_values_hs300)
    
    # 红利低波100基准
    low_vol_code = BENCHMARK_CODES.get('红利低波100')
    if low_vol_code:
        bench_dates_lowvol, bench_values_lowvol = generate_benchmark_index(start_date, end_date, low_vol_code, data_loader)
        if bench_dates_lowvol and bench_values_lowvol:
            benchmark_data['红利低波100'] = (bench_dates_lowvol, bench_values_lowvol)
    
    # 计算指标
    metrics = calculate_metrics(history)
    
    # 计算超额收益指标
    if '等权重定投' in benchmark_data:
        excess_metrics = calculate_excess_metrics(history, benchmark_data['等权重定投'][1])
        metrics.update(excess_metrics)
    
    transactions_df = engine.get_transactions_df()
    history_df = engine.get_history_df()
    monthly_decisions_df = engine.get_monthly_decisions_df()

    # 生成可视化图表
    equity_curve_path = os.path.join(output_dir, 'equity_curve.png')
    drawdown_curve_path = os.path.join(output_dir, 'drawdown_curve.png')
    allocation_path = os.path.join(output_dir, 'asset_allocation.png')
    
    if TQDM_AVAILABLE:
        with tqdm(total=3, desc="生成图表", unit="张", ncols=80) as pbar:
            plot_equity_curve(history, benchmark_data, equity_curve_path)
            pbar.update(1)
            plot_drawdown_curve(history, drawdown_curve_path)
            pbar.update(1)
            plot_asset_allocation(history, allocation_path, price_data)
            pbar.update(1)
    else:
        plot_equity_curve(history, benchmark_data, equity_curve_path)
        plot_drawdown_curve(history, drawdown_curve_path)
        plot_asset_allocation(history, allocation_path, price_data)

    # 生成报告
    report_path = generate_backtest_report(
        history=history,
        metrics=metrics,
        transactions_df=transactions_df,
        monthly_decisions_df=monthly_decisions_df,
        benchmark_data=benchmark_data,
        start_date=start_date,
        end_date=end_date,
        monthly_budget=monthly_budget,
        output_dir=output_dir,
        figure_paths={
            'equity_curve': equity_curve_path,
            'drawdown_curve': drawdown_curve_path,
            'asset_allocation': allocation_path
        },
        transactions=transactions_df
    )
    
    logger.info(f"\n回测完成！报告已保存至: {report_path}")

    return {
        'history': history,
        'metrics': metrics,
        'transactions': transactions_df,
        'history_df': history_df,
        'report_path': report_path,
        'benchmark_data': benchmark_data
    }


def generate_backtest_report(history: List[Dict[str, Any]], 
                             metrics: Dict[str, float], 
                             transactions_df: pd.DataFrame,
                             monthly_decisions_df: Optional[pd.DataFrame] = None,
                             benchmark_data: Dict[str, tuple] = None,
                             start_date: Optional[str] = None, 
                             end_date: Optional[str] = None, 
                             monthly_budget: Optional[float] = None,
                             output_dir: str = OUTPUT_DIR,
                             figure_paths: Optional[Dict[str, str]] = None,
                             transactions: Optional[pd.DataFrame] = None) -> str:
    """
    生成回测报告（Markdown格式）
    
    Args:
        history: 回测历史
        metrics: 绩效指标
        transactions_df: 交易记录
        monthly_decisions_df: 每月决策明细
        benchmark_data: 基准数据
        start_date: 开始日期
        end_date: 结束日期
        monthly_budget: 月度预算
        output_dir: 输出目录
        figure_paths: 图表路径
        transactions: 完整交易记录（用于计算分红再投资）
        
    Returns:
        报告路径
    """
    report_lines = []
    
    report_lines.append("# 回测绩效报告")
    report_lines.append("")
    
    # 添加目录
    report_lines.append("## 目录")
    report_lines.append("")
    report_lines.append("- [回测概览](#回测概览)")
    report_lines.append("- [绩效指标](#绩效指标)")
    report_lines.append("- [收益曲线](#收益曲线)")
    report_lines.append("- [回撤曲线](#回撤曲线)")
    report_lines.append("- [资产配置](#资产配置)")
    report_lines.append("- [交易记录](#交易记录)")
    report_lines.append("- [买入原因统计](#买入原因统计)")
    report_lines.append("- [基准对比](#基准对比)")
    report_lines.append("- [每月决策明细](#每月决策明细)")
    report_lines.append("")
    
    # 回测概览
    report_lines.append("## 回测概览")
    report_lines.append("")
    
    if start_date and end_date:
        report_lines.append(f"- **回测期间**: {start_date} 至 {end_date}")
    if monthly_budget:
        report_lines.append(f"- **月度预算**: {monthly_budget:,.2f} 元")
    if history:
        report_lines.append(f"- **回测月份**: {len(history)} 个月")
        report_lines.append(f"- **总交易次数**: {len([t for t in history for _ in range(t.get('transactions_count', 0))])} 笔")
    
    report_lines.append("")
    
    # 绩效指标 - 增加高亮
    report_lines.append("## 绩效指标")
    report_lines.append("")
    report_lines.append("| 指标 | 值 |")
    report_lines.append("|------|-----|")
    
    # 高亮重要指标
    total_return = metrics.get('total_return', 0)
    annual_return = metrics.get('annual_return', 0)
    max_drawdown = metrics.get('max_drawdown', 0)
    sharpe = metrics.get('sharpe', 0)
    
    # 添加颜色标记（使用HTML标签）
    total_return_str = f"**{total_return*100:.2f}%**" if total_return > 0 else f"{total_return*100:.2f}%"
    annual_return_str = f"**{annual_return*100:.2f}%**" if annual_return > 0 else f"{annual_return*100:.2f}%"
    max_drawdown_str = f"**{max_drawdown*100:.2f}%**" if abs(max_drawdown) < 0.1 else f"{max_drawdown*100:.2f}%"
    sharpe_str = f"**{sharpe:.2f}**" if sharpe > 1.0 else f"{sharpe:.2f}"
    
    report_lines.append(f"| 总收益率 | {total_return_str} |")
    report_lines.append(f"| 年化收益率 | {annual_return_str} |")
    report_lines.append(f"| 最大回撤 | {max_drawdown_str} |")
    report_lines.append(f"| 波动率 | {metrics.get('volatility', 0)*100:.2f}% |")
    report_lines.append(f"| 夏普比率 | {sharpe_str} |")
    report_lines.append(f"| Calmar比率 | {metrics.get('calmar', 0):.2f} |")
    report_lines.append(f"| IRR | {metrics.get('irr', 0)*100:.2f}% |")
    report_lines.append(f"| Sortino比率 | {metrics.get('sortino', 0):.2f} |")
    report_lines.append(f"| 胜率 | {metrics.get('win_rate', 0)*100:.2f}% |")
    report_lines.append(f"| 盈利因子 | {metrics.get('profit_factor', 0):.2f} |")
    
    if 'total_excess_return' in metrics:
        excess_return = metrics['total_excess_return']
        excess_str = f"**{excess_return*100:.2f}%**" if excess_return > 0 else f"{excess_return*100:.2f}%"
        report_lines.append(f"| 累计超额收益 | {excess_str} |")
        report_lines.append(f"| 超额收益波动率 | {metrics['excess_volatility']*100:.2f}% |")
        report_lines.append(f"| 信息比率 | {metrics['information_ratio']:.2f} |")
        report_lines.append(f"| 超额最大回撤 | {metrics['max_excess_drawdown']*100:.2f}% |")
    
    if history:
        first_value = history[0]['total_value']
        last_value = history[-1]['total_value']
        report_lines.append(f"| 初始资产 | {first_value:,.2f} |")
        report_lines.append(f"| 最终资产 | **{last_value:,.2f}** |")
        report_lines.append(f"| 累计投入 | {len(history) * monthly_budget:,.2f} |")
        report_lines.append(f"| 累计收益 | **{(last_value - len(history) * monthly_budget):,.2f}** |")
    
    report_lines.append("")
    report_lines.append("## 收益曲线")
    report_lines.append("")
    
    if figure_paths and 'equity_curve' in figure_paths and os.path.exists(figure_paths['equity_curve']):
        report_lines.append(f"![权益曲线]({os.path.basename(figure_paths['equity_curve'])})")
    else:
        report_lines.append("### 收益曲线数据")
        report_lines.append("")
        report_lines.append("| 日期 | 总资产 | 持仓价值 | 现金 | 资金池 |")
        report_lines.append("|------|--------|----------|------|--------|")
        
        for record in history:
            date_str = record['date'].strftime('%Y-%m-%d') if hasattr(record['date'], 'strftime') else str(record['date'])[:10]
            report_lines.append(f"| {date_str} | {record['total_value']:,.2f} | {record['holdings_value']:,.2f} | {record['cash']:,.2f} | {record['cash_pool']:,.2f} |")
    
    report_lines.append("")
    report_lines.append("## 回撤曲线")
    report_lines.append("")
    
    if figure_paths and 'drawdown_curve' in figure_paths and os.path.exists(figure_paths['drawdown_curve']):
        report_lines.append(f"![回撤曲线]({os.path.basename(figure_paths['drawdown_curve'])})")
    
    report_lines.append("")
    report_lines.append("## 资产配置")
    report_lines.append("")
    
    if figure_paths and 'asset_allocation' in figure_paths and os.path.exists(figure_paths['asset_allocation']):
        report_lines.append(f"![资产配置]({os.path.basename(figure_paths['asset_allocation'])})")
    
    report_lines.append("")
    report_lines.append("## 交易记录")
    report_lines.append("")
    
    if transactions_df is not None and not transactions_df.empty:
        report_lines.append("| 日期 | 类型 | 标的 | 股数 | 价格 | 成本 | 佣金 | 原因 |")
        report_lines.append("|------|------|------|------|------|------|------|------|")
        
        for _, row in transactions_df.iterrows():
            date_str = row['date'].strftime('%Y-%m-%d') if hasattr(row['date'], 'strftime') else str(row['date'])[:10]
            reason = row.get('reason', '')
            commission = row.get('commission', 0)
            report_lines.append(f"| {date_str} | {row['type']} | {row['stock_name']} | {row['shares']} | {row['price']:.2f} | {row['cost']:,.2f} | {commission:.2f} | {reason} |")
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
    else:
        report_lines.append("无交易记录")
    
    report_lines.append("")
    report_lines.append("## 基准对比")
    report_lines.append("")
    
    if benchmark_data:
        report_lines.append("| 指标 | 策略 | " + " | ".join(benchmark_data.keys()) + " |")
        report_lines.append("|------|------|" + "------|" * len(benchmark_data))
        
        # 总收益率
        strat_total_return = metrics.get('total_return', 0)
        bench_total_returns = []
        for name, (dates, values) in benchmark_data.items():
            if values:
                initial = values[0]
                final = values[-1]
                bench_total_returns.append((final - initial) / initial if initial > 0 else 0)
            else:
                bench_total_returns.append(0)
        
        report_lines.append(f"| 总收益率 | {strat_total_return*100:.2f}% | " + " | ".join([f"{r*100:.2f}%" for r in bench_total_returns]) + " |")
        
        # 年化收益率
        strat_annual_return = metrics.get('annual_return', 0)
        bench_annual_returns = []
        for name, (dates, values) in benchmark_data.items():
            if dates and values:
                days = (dates[-1] - dates[0]).days
                years = days / 365.0 if days > 0 else 1.0
                initial = values[0]
                final = values[-1]
                total_return = (final - initial) / initial if initial > 0 else 0
                bench_annual_returns.append((1 + total_return) ** (1 / years) - 1 if years > 0 else 0)
            else:
                bench_annual_returns.append(0)
        
        report_lines.append(f"| 年化收益率 | {strat_annual_return*100:.2f}% | " + " | ".join([f"{r*100:.2f}%" for r in bench_annual_returns]) + " |")
        
        # 最大回撤
        strat_max_dd = metrics.get('max_drawdown', 0)
        report_lines.append(f"| 最大回撤 | {strat_max_dd*100:.2f}% | " + " | ".join(["-" for _ in benchmark_data]) + " |")
    else:
        report_lines.append("无基准数据")
    
    report_lines.append("")
    report_lines.append("## 每月决策明细")
    report_lines.append("")
    
    # 计算每月分红再投资金额
    monthly_dividend = {}
    if transactions is not None and not transactions.empty:
        # 按日期分组计算分红再投资
        for date in pd.to_datetime(transactions['date']).dt.date.unique():
            date_trans = transactions[pd.to_datetime(transactions['date']).dt.date == date]
            div_reinvest = date_trans[date_trans['type'] == 'dividend_reinvest']
            monthly_dividend[date] = div_reinvest['cost'].sum() if not div_reinvest.empty else 0.0
    
    if monthly_decisions_df is not None and not monthly_decisions_df.empty:
        report_lines.append("| 日期 | 总资产 | 现金 | 资金池 | 再平衡前偏离最大标的 | 买入标的 | 买入股数 | 买入原因 | 资金池变化 | 本月执行金额 | 分红再投资金额 |")
        report_lines.append("|------|--------|------|--------|---------------------|----------|----------|----------|------------|--------------|----------------|")
        
        for _, row in monthly_decisions_df.iterrows():
            date_str = row['date'].strftime('%Y-%m-%d') if hasattr(row['date'], 'strftime') else str(row['date'])[:10]
            max_dev_stock = row.get('max_deviation_stock', '-')
            max_dev = row.get('max_deviation', 0)
            bought_stocks = row.get('bought_stocks', '-')
            total_shares = row.get('total_shares', 0)
            buy_reason = row.get('buy_reason', '-')
            cash_pool_change = row.get('cash_pool_change', 0)
            executed_amount = row.get('executed_amount', 0)
            
            # 获取分红再投资金额
            date_key = pd.to_datetime(row['date']).date()
            div_amount = monthly_dividend.get(date_key, 0.0)
            
            deviation_str = f"{max_dev_stock} ({max_dev*100:.1f}%)" if max_dev_stock else "-"
            
            report_lines.append(f"| {date_str} | {row['total_value']:,.2f} | {row['cash']:,.2f} | {row['cash_pool']:,.2f} | {deviation_str} | {bought_stocks} | {total_shares} | {buy_reason} | {cash_pool_change:+,.2f} | {executed_amount:,.2f} | {div_amount:,.2f} |")
    else:
        report_lines.append("无决策明细数据")
    
    report_lines.append("")
    report_lines.append("---")
    report_lines.append(f"报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    report_content = "\n".join(report_lines)
    report_path = os.path.join(output_dir, 'backtest_report.md')
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_content)
    
    logger.info(f"回测报告已保存: {report_path}")
    return report_path


class BacktestRunner:
    """回测运行器类"""
    
    def __init__(self, data_loader=None, simulator=None, strategy_adapter=None):
        self.data_loader = data_loader or BacktestDataLoader()
        self.strategy_adapter = strategy_adapter or StrategyAdapter()
        self.simulator = simulator

    def run(self, stock_codes: List[str], start_date: str, end_date: str, 
            initial_cash: float = 100000.0, monthly_budget: float = MONTHLY_BUDGET, 
            rebalance_frequency: str = 'monthly', output_dir: str = OUTPUT_DIR):
        """运行回测"""
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
        """生成交易日期"""
        from backtest.data_loader import get_monthly_trading_dates
        
        if frequency == 'daily':
            date_range = pd.date_range(start, end, freq='B')
            return date_range.tolist()
        elif frequency == 'weekly':
            date_range = pd.date_range(start, end, freq='W')
            return date_range.tolist()
        elif frequency == 'monthly':
            return get_monthly_trading_dates(start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
        else:
            return get_monthly_trading_dates(start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))

    def _process_date(self, date, historical_data, monthly_budget):
        """处理单日"""
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

        actions = []
        if self.simulator:
            actions, _ = self.strategy_adapter.execute_rebalance(
                snapshot=snapshot,
                simulator=self.simulator,
                monthly_budget=monthly_budget,
                current_holdings=holdings,
                total_value=total_value
            )

        if actions:
            tx_df = self.simulator.get_transactions_df() if self.simulator else None
            if tx_df is not None and not tx_df.empty:
                pass

    def _get_snapshot_at_date(self, historical_data, date):
        """获取指定日期的快照"""
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
        """获取股票名称"""
        name_map = {
            "招商银行": "招商银行",
            "兴业银行": "兴业银行",
            "工商银行": "工商银行",
            "双汇发展": "双汇发展",
            ETF_CODE: "红利低波100ETF"
        }
        return name_map.get(stock_code, stock_code)

    def _generate_results(self, output_dir):
        """生成结果"""
        transactions_df = pd.DataFrame()
        if self.simulator:
            transactions_df = self.simulator.get_transactions_df()

        if not transactions_df.empty:
            transactions_df.to_csv(os.path.join(output_dir, 'transactions.csv'), index=False)

        return {
            'transactions': transactions_df
        }


if __name__ == '__main__':
    result = run_backtest(
        start_date="2023-01-01",
        end_date="2023-12-31",
        monthly_budget=MONTHLY_BUDGET
    )

    print("\n回测完成")
