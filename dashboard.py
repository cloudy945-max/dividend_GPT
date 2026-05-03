import streamlit as st
import pandas as pd
import os

from portfolio_analysis import analyze_portfolio
from market_data import get_multiple_market_data
from portfolio import PortfolioManager
from visualization import generate_all_charts

st.set_page_config(page_title="投资组合仪表盘", layout="wide")

st.title("📊 投资组合仪表盘")

# 初始化数据
try:
    portfolio = PortfolioManager()
    holdings = portfolio.get_holdings()
    dividends = portfolio.get_dividends()
    
    if holdings.empty:
        st.warning("当前没有持仓数据！请先添加持仓。")
        st.stop()
    
    # 获取市场数据
    stock_list = holdings['stock_name'].tolist()
    snapshot = get_multiple_market_data(stock_list)
    
    # 分析组合
    analysis = analyze_portfolio(holdings, snapshot, dividends)
    
    # ===== 核心指标 =====
    st.subheader("核心指标")
    col1, col2, col3, col4, col5 = st.columns(5)
    
    col1.metric("总资产", f"{analysis['total_value']:,.0f}")
    
    if analysis['total_return'] is not None:
        sign = "+" if analysis['total_return'] >= 0 else ""
        col2.metric("收益率", f"{sign}{analysis['total_return']*100:.1f}%")
    else:
        col2.metric("收益率", "--")
    
    col3.metric("年现金流", f"{analysis['annual_dividend']:,.0f}")
    
    if analysis['dividend_yield'] is not None:
        col4.metric("股息率", f"{analysis['dividend_yield']*100:.1f}%")
    else:
        col4.metric("股息率", "--")
    
    if analysis['cashflow_quality'] is not None:
        col5.metric("现金流质量", f"{analysis['cashflow_quality']*100:.1f}%")
    else:
        col5.metric("现金流质量", "--")
    
    # 显示警告
    if analysis.get('needs_rebalance'):
        st.warning("⚠️ 需要再平衡！")
    if analysis.get('has_warning'):
        st.warning("⚠️ 部分资产缺少价格，估值可能不准确")
    
    st.divider()
    
    # ===== 资产配置和收益情况 =====
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.subheader("资产配置")
        alloc_df = pd.DataFrame(analysis["allocation"])
        if not alloc_df.empty:
            alloc_df['weight'] = alloc_df['weight'] * 100
            st.bar_chart(alloc_df.set_index("stock_name"))
            st.dataframe(alloc_df.rename(columns={'stock_name': '股票名称', 'weight': '权重(%)'}), hide_index=True)
    
    with col_right:
        st.subheader("收益情况")
        pos_df = pd.DataFrame(analysis["positions"])
        if not pos_df.empty:
            return_df = pos_df[['stock_name', 'return_rate']].copy()
            return_df['return_rate'] = return_df['return_rate'] * 100
            return_df = return_df.set_index('stock_name')
            st.bar_chart(return_df)
    
    # ===== 持仓明细 =====
    st.subheader("持仓明细")
    display_df = pos_df[['stock_name', 'shares', 'cost_price', 'total_cost', 'price', 'market_value', 'profit', 'return_rate']].copy()
    display_df['return_rate'] = (display_df['return_rate'] * 100).round(1) if 'return_rate' in display_df.columns else None
    display_df.columns = ['股票名称', '持仓股数', '成本价', '总成本', '现价', '市值', '盈亏', '收益率(%)']
    st.dataframe(display_df, hide_index=True)
    
    # ===== 生成图表按钮 =====
    st.divider()
    if st.button("📷 生成可视化图表"):
        output_dir = 'output'
        generate_all_charts(analysis, output_dir=output_dir)
        st.success(f"图表已生成到 {output_dir}/ 文件夹！")
        
        # 显示已生成的图表
        chart_files = ['allocation.png', 'returns.png', 'dividend.png']
        for file in chart_files:
            file_path = os.path.join(output_dir, file)
            if os.path.exists(file_path):
                st.image(file_path, use_container_width=True)
    
except Exception as e:
    st.error(f"发生错误：{str(e)}")
    st.exception(e)
