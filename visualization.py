import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
import os
import platform

# 配置中文字体支持
system = platform.system()
if system == 'Windows':
    # Windows系统
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'SimSun']
elif system == 'Darwin':
    # macOS系统
    plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'PingFang SC', 'Heiti TC']
else:
    # Linux系统
    plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei', 'SimHei']

plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题


def plot_allocation(analysis, save_path='allocation.png'):
    """
    绘制资产分布饼图
    
    Args:
        analysis: analyze_portfolio 返回的分析结果
        save_path: 保存路径
    """
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
    """
    绘制收益柱状图
    
    Args:
        analysis: analyze_portfolio 返回的分析结果
        save_path: 保存路径
    """
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
    """
    绘制资金增长曲线
    
    Args:
        history_data: 历史数据列表，每个元素包含 date 和 total_value
        save_path: 保存路径
    """
    if not history_data:
        return
    
    dates = [item.get('date', '') for item in history_data]
    total_values = [item.get('total_value', 0) for item in history_data]
    
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
    """
    绘制定期分红现金流图
    
    Args:
        analysis: analyze_portfolio 返回的分析结果
        save_path: 保存路径
    """
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


def generate_all_charts(analysis, history_data=None, output_dir='.'):
    """
    生成所有图表
    
    Args:
        analysis: analyze_portfolio 返回的分析结果
        history_data: 历史数据列表（可选）
        output_dir: 输出目录
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    plot_allocation(analysis, os.path.join(output_dir, 'allocation.png'))
    plot_returns(analysis, os.path.join(output_dir, 'returns.png'))
    
    if history_data:
        plot_growth(history_data, os.path.join(output_dir, 'growth.png'))
    
    plot_dividend(analysis, os.path.join(output_dir, 'dividend.png'))
