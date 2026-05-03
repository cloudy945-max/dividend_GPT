#!/usr/bin/env python3
"""
主程序：一键生成投资组合分析和图表
"""

from portfolio import PortfolioManager
from market_data import get_multiple_market_data
from portfolio_analysis import analyze_portfolio, print_dashboard
from visualization import generate_all_charts


def main():
    print("="*50)
    print("  投资组合分析工具")
    print("="*50)
    
    # 1. 获取持仓
    print("\n[1/5] 加载持仓数据...")
    portfolio = PortfolioManager()
    holdings = portfolio.get_holdings()
    dividends = portfolio.get_dividends()
    
    if holdings.empty:
        print("警告：持仓为空")
        return
    
    print(f"持仓加载完成，共 {len(holdings)} 只股票")
    
    # 2. 获取市场数据
    print("\n[2/5] 获取市场数据...")
    stock_names = holdings['stock_name'].tolist()
    snapshot = get_multiple_market_data(stock_names)
    
    # 过滤掉失败的数据
    valid_snapshot = [s for s in snapshot if 'error' not in s]
    print(f"市场数据获取完成，有效 {len(valid_snapshot)} 条")
    
    # 3. 调用分析
    print("\n[3/5] 分析投资组合...")
    analysis = analyze_portfolio(holdings, valid_snapshot, dividends)
    print("分析完成")
    
    # 4. 调用 print_dashboard
    print("\n[4/5] 生成仪表盘...")
    print_dashboard(analysis)
    
    # 5. 调用 generate_charts
    print("\n[5/5] 生成图表...")
    generate_all_charts(analysis, output_dir='output')
    print("图表已保存到 output/ 目录")
    
    print("\n" + "="*50)
    print("  分析完成！")
    print("="*50)


if __name__ == "__main__":
    main()
