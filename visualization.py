import matplotlib.pyplot as plt
import matplotlib
import pandas as pd
import numpy as np

matplotlib.use('Agg')
import os
import platform

system = platform.system()
if system == 'Windows':
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'SimSun']
elif system == 'Darwin':
    plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'PingFang SC', 'Heiti TC']
else:
    plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei', 'SimHei']

plt.rcParams['axes.unicode_minus'] = False


def plot_allocation(analysis, save_path='allocation.png'):
    allocation = analysis.get('allocation', [])

    if not allocation:
        return

    stock_names = [item['stock_name'] for item in allocation]
    weights = [item['weight'] for item in allocation]

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.pie(weights, labels=stock_names, autopct='%1.1f%%', startangle=90)
    ax.axis('equal')
    plt.title('资产分布', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()


def plot_returns(analysis, save_path='returns.png'):
    positions = analysis.get('positions', [])

    if not positions:
        return

    stock_names = []
    return_rates = []

    for pos in positions:
        stock_names.append(pos['stock_name'])
        rate = pos['return_rate']
        return_rates.append(rate * 100 if rate is not None else 0)

    fig, ax = plt.subplots(figsize=(10, 6))

    colors = ['green' if r >= 0 else 'red' for r in return_rates]
    bars = ax.bar(stock_names, return_rates, color=colors)

    ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax.set_ylabel('收益率 (%)', fontsize=12)
    ax.set_title('各标的收益率', fontsize=14, fontweight='bold')
    ax.grid(axis='y', alpha=0.3)

    for bar in bars:
        height = bar.get_height()
        ax.annotate(f'{height:.1f}%',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3 if height >= 0 else -15),
                    textcoords="offset points",
                    ha='center', va='bottom')

    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()


def plot_growth(history_data, save_path='growth.png'):
    if not history_data:
        return

    if isinstance(history_data, list) and len(history_data) > 0:
        first_item = history_data[0]
        if isinstance(first_item, dict) and 'total_value' in first_item:
            dates = [item.get('date', '') for item in history_data]
            total_values = [item.get('total_value', 0) for item in history_data]
        elif isinstance(first_item, tuple) and len(first_item) == 2:
            dates = [item[0] for item in history_data]
            total_values = [item[1] for item in history_data]
        else:
            return
    else:
        return

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(dates, total_values, marker='o', linewidth=2, color='#2e86ab')

    ax.set_xlabel('日期', fontsize=12)
    ax.set_ylabel('总资产', fontsize=12)
    ax.set_title('资金增长曲线', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3)

    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()


def plot_dividend(analysis, save_path='dividend.png'):
    annual_dividend = analysis.get('annual_dividend', 0)

    fig, ax = plt.subplots(figsize=(8, 6))

    categories = ['年分红现金流']
    values = [annual_dividend]

    bars = ax.bar(categories, values, color='#f4a261', width=0.4)

    ax.set_ylabel('金额', fontsize=12)
    ax.set_title('年分红现金流', fontsize=14, fontweight='bold')
    ax.grid(axis='y', alpha=0.3)

    for bar in bars:
        height = bar.get_height()
        ax.annotate(f'{height:,.2f}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha='center', va='bottom')

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()


def plot_backtest_result(history, metrics=None, output_dir='backtest_data'):
    """
    绘制回测结果图表

    Args:
        history: 回测历史列表，每个元素包含 date 和 total_value
        metrics: 绩效指标字典（可选）
        output_dir: 输出目录
    """
    if not history:
        return

    os.makedirs(output_dir, exist_ok=True)

    if isinstance(history, list) and len(history) > 0:
        first_item = history[0]
        if isinstance(first_item, dict) and 'total_value' in first_item:
            dates = [item.get('date', '') for item in history]
            total_values = [item.get('total_value', 0) for item in history]
        elif isinstance(first_item, tuple) and len(first_item) == 2:
            dates = [item[0] for item in history]
            total_values = [item[1] for item in history]
        else:
            return
    else:
        return

    values = np.array(total_values)
    dates_str = dates

    running_max = np.maximum.accumulate(values)
    drawdown = (values - running_max) / running_max

    fig, axes = plt.subplots(2, 1, figsize=(12, 10))

    axes[0].plot(dates_str, values, marker='o', linewidth=2, color='#2e86ab')
    axes[0].set_xlabel('日期', fontsize=12)
    axes[0].set_ylabel('总资产', fontsize=12)
    axes[0].set_title('资金增长曲线', fontsize=14, fontweight='bold')
    axes[0].grid(True, alpha=0.3)
    axes[0].tick_params(axis='x', rotation=45)

    if metrics is not None:
        total_return = metrics.get('total_return', 0)
        annual_return = metrics.get('annual_return', 0)
        sharpe = metrics.get('sharpe', 0)
        info_text = f"总收益率: {total_return*100:.2f}%  |  年化收益: {annual_return*100:.2f}%  |  夏普比率: {sharpe:.2f}"
        axes[0].text(0.5, 0.02, info_text, transform=axes[0].transAxes, fontsize=10,
                     verticalalignment='bottom', horizontalalignment='center',
                     bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    axes[1].fill_between(range(len(dates_str)), drawdown * 100, 0, alpha=0.3, color='red')
    axes[1].plot(range(len(dates_str)), drawdown * 100, color='red', linewidth=1)
    axes[1].set_xlabel('日期', fontsize=12)
    axes[1].set_ylabel('回撤 (%)', fontsize=12)
    axes[1].set_title('回撤曲线', fontsize=14, fontweight='bold')
    axes[1].grid(True, alpha=0.3)

    max_dd = np.min(drawdown) * 100 if len(drawdown) > 0 else 0
    axes[1].text(0.5, 0.02, f"最大回撤: {max_dd:.2f}%", transform=axes[1].transAxes, fontsize=10,
                 verticalalignment='bottom', horizontalalignment='center',
                 bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    tick_positions = np.linspace(0, len(dates_str) - 1, min(10, len(dates_str)), dtype=int)
    axes[1].set_xticks(tick_positions)
    axes[1].set_xticklabels([dates_str[i] for i in tick_positions], rotation=45)

    plt.tight_layout()
    growth_path = os.path.join(output_dir, 'growth.png')
    drawdown_path = os.path.join(output_dir, 'drawdown.png')
    plt.savefig(growth_path, dpi=150, bbox_inches='tight')
    plt.close()

    fig_dd, ax_dd = plt.subplots(figsize=(12, 4))
    ax_dd.fill_between(range(len(dates_str)), drawdown * 100, 0, alpha=0.3, color='red')
    ax_dd.plot(range(len(dates_str)), drawdown * 100, color='red', linewidth=1)
    ax_dd.set_xlabel('日期', fontsize=12)
    ax_dd.set_ylabel('回撤 (%)', fontsize=12)
    ax_dd.set_title('回撤曲线', fontsize=14, fontweight='bold')
    ax_dd.grid(True, alpha=0.3)
    ax_dd.text(0.5, 0.02, f"最大回撤: {max_dd:.2f}%", transform=ax_dd.transAxes, fontsize=10,
               verticalalignment='bottom', horizontalalignment='center',
               bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    ax_dd.set_xticks(tick_positions)
    ax_dd.set_xticklabels([dates_str[i] for i in tick_positions], rotation=45)
    plt.tight_layout()
    plt.savefig(drawdown_path, dpi=150, bbox_inches='tight')
    plt.close()

    print(f"增长曲线已保存至: {growth_path}")
    print(f"回撤曲线已保存至: {drawdown_path}")


def generate_all_charts(analysis, history_data=None, output_dir='.'):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    plot_allocation(analysis, os.path.join(output_dir, 'allocation.png'))
    plot_returns(analysis, os.path.join(output_dir, 'returns.png'))

    if history_data:
        plot_growth(history_data, os.path.join(output_dir, 'growth.png'))

    plot_dividend(analysis, os.path.join(output_dir, 'dividend.png'))
