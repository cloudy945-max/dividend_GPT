#!/usr/bin/env python3
"""
投资组合管理工具 - 交互式脚本
"""

import sys
from portfolio import PortfolioManager
from market_data import get_multiple_market_data, generate_execution_plan, ALLOWED_STOCKS, get_stock_name
from portfolio_analysis import analyze_portfolio, print_dashboard
from visualization import generate_all_charts
import os


def print_separator():
    print("\n" + "="*50)


def format_date(value):
    """格式化日期，只显示 YYYY-MM-DD"""
    import pandas as pd

    if value is None:
        return ""

    # 如果是pandas Timestamp或datetime对象
    if hasattr(value, 'strftime'):
        return value.strftime('%Y-%m-%d')

    # 如果是字符串，尝试转换
    if isinstance(value, str):
        try:
            return pd.to_datetime(value).strftime('%Y-%m-%d')
        except:
            return value[:10] if len(value) >= 10 else value

    return str(value)[:10]


def str_width(s):
    """计算字符串在Windows命令行中的显示宽度（中文2，英文1）"""
    width = 0
    for c in str(s):
        if '\u4e00' <= c <= '\u9fff':  # 中文
            width += 2
        elif c == '\t':
            width += 8
        else:
            width += 1
    return width


# 列名映射：英文 → 中文
COLUMN_NAMES_MAP = {
    'stock_name': '股票名称',
    'shares': '持仓股数',
    'cost_price': '成本价',
    'total_cost': '总成本',
    'date': '日期',
    'type': '类型',
    'price': '价格',
    'cash_flow': '现金流',
    'dividend_per_share': '每股分红'
}


def ljust_display(text, width):
    """左对齐文本到指定的显示宽度（中文=2字符）"""
    text = str(text)
    current_width = str_width(text)
    if current_width >= width:
        return text
    return text + " " * (width - current_width)


def print_table(df, chinese_columns=True):
    """打印表格，自动处理中文字符宽度对齐"""
    if df.empty:
        print("  暂无数据")
        return

    # 复制df避免修改原数据
    df_copy = df.copy()

    # 转换列名为中文
    if chinese_columns:
        df_copy.columns = [COLUMN_NAMES_MAP.get(col, col) for col in df_copy.columns]

    # 格式化日期列（只显示日期）
    for col in df_copy.columns:
        if '日期' in col or 'date' in col.lower():
            df_copy[col] = df_copy[col].apply(format_date)

    # 计算每列的最大显示宽度
    col_widths = {}
    for col in df_copy.columns:
        if len(df_copy[col]) > 0:
            max_val_width = max(str_width(str(v)) for v in df_copy[col])
        else:
            max_val_width = 0
        col_widths[col] = max(str_width(col), max_val_width)

    # 打印表头（列之间加2个空格分隔）
    header_parts = []
    for col in df_copy.columns:
        header_parts.append(ljust_display(col, col_widths[col]))
    print("  ".join(header_parts))
    print("-" * (sum(col_widths.values()) + 2 * (len(col_widths) - 1)))

    # 打印数据行（列之间加2个空格分隔）
    for _, row in df_copy.iterrows():
        line_parts = []
        for col in df_copy.columns:
            line_parts.append(ljust_display(row[col], col_widths[col]))
        print("  ".join(line_parts))


def get_valid_date(prompt):
    """获取有效的日期输入"""
    from datetime import datetime
    while True:
        date_str = input(prompt)
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            return date_str
        except ValueError:
            print("❌ 日期格式错误，请输入 YYYY-MM-DD 格式")


def get_valid_float(prompt):
    """获取有效的浮点数输入"""
    while True:
        try:
            value = float(input(prompt))
            if value < 0:
                print("❌ 值不能为负数")
                continue
            return value
        except ValueError:
            print("❌ 请输入有效的数字")


def get_valid_int(prompt):
    """获取有效的整数输入"""
    while True:
        try:
            value = int(input(prompt))
            if value < 0:
                print("❌ 值不能为负数")
                continue
            return value
        except ValueError:
            print("❌ 请输入有效的整数")


def menu_view_holdings(portfolio):
    """查看持仓"""
    holdings = portfolio.get_holdings()
    print("\n当前持仓：")
    if holdings.empty:
        print("  暂无持仓")
    else:
        print_table(holdings)


def menu_view_transactions(portfolio):
    """查看交易记录"""
    transactions = portfolio.get_transactions_sorted()
    print("\n交易记录：")
    if transactions.empty:
        print("  暂无交易记录")
    else:
        print_table(transactions)


def menu_view_dividends(portfolio):
    """查看分红记录"""
    dividends = portfolio.get_dividends()
    print("\n分红记录：")
    if dividends.empty:
        print("  暂无分红记录")
    else:
        print_table(dividends)


def menu_add_buy(portfolio):
    """添加买入记录"""
    print("\n添加买入记录")
    print("-"*30)

    date = get_valid_date("日期 (YYYY-MM-DD): ")
    stock_name = input("股票名称：").strip()

    if not stock_name:
        print("❌ 股票名称不能为空")
        return

    price = get_valid_float("买入价格：")
    shares = get_valid_int("买入股数：")

    try:
        portfolio.add_transaction(date, 'buy', stock_name, price, shares)
        print(f"✅ 成功添加买入记录：{stock_name} {shares}股 @{price}")
    except Exception as e:
        print(f"❌ 添加失败：{e}")


def menu_add_sell(portfolio):
    """添加卖出记录"""
    print("\n添加卖出记录")
    print("-"*30)

    date = get_valid_date("日期 (YYYY-MM-DD): ")
    stock_name = input("股票名称：").strip()

    if not stock_name:
        print("❌ 股票名称不能为空")
        return

    price = get_valid_float("卖出价格：")
    shares = get_valid_int("卖出股数：")

    try:
        portfolio.add_transaction(date, 'sell', stock_name, price, shares)
        print(f"✅ 成功添加卖出记录：{stock_name} {shares}股 @{price}")
    except ValueError as e:
        print(f"❌ {e}")
    except Exception as e:
        print(f"❌ 添加失败：{e}")


def menu_add_dividend(portfolio):
    """添加分红记录"""
    print("\n添加分红记录")
    print("-"*30)

    date = get_valid_date("日期 (YYYY-MM-DD): ")
    stock_name = input("股票名称：").strip()

    if not stock_name:
        print("❌ 股票名称不能为空")
        return

    dividend_per_share = get_valid_float("每股分红：")

    try:
        portfolio.add_dividend(date, stock_name, dividend_per_share)
        print(f"✅ 成功添加分红记录：{stock_name} 每股分红 {dividend_per_share} 元")
    except Exception as e:
        print(f"❌ 添加失败：{e}")


def menu_run_analysis(portfolio):
    """运行分析"""
    print("\n运行投资组合分析")
    print("-"*30)

    holdings = portfolio.get_holdings()
    if holdings.empty:
        print("❌ 没有持仓数据，无法分析")
        return

    dividends = portfolio.get_dividends()

    try:
        stock_list = holdings['stock_name'].tolist()
        print(f"正在获取 {len(stock_list)} 只股票的市场数据...")
        snapshot = get_multiple_market_data(stock_list)

        print("\n分析结果：")
        analysis = analyze_portfolio(holdings, snapshot, dividends)
        print_dashboard(analysis)

        # 生成图表
        output_dir = 'output'
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        generate_all_charts(analysis, output_dir=output_dir)
        print(f"\n📊 图表已保存到 {output_dir} 文件夹")

    except Exception as e:
        print(f"❌ 分析失败：{e}")


def menu_buy_suggestion(portfolio):
    """查看月度买入建议"""
    print("\n📈 月度买入建议")
    print("-"*30)

    try:
        print("正在获取市场数据...")
        snapshot = get_multiple_market_data(ALLOWED_STOCKS)

        # 过滤有效数据
        valid_snapshot = [s for s in snapshot if 'error' not in s and s.get('price') is not None]

        monthly_budget = get_valid_float("请输入月度预算金额：")

        print("\n生成买入建议...")
        plan = {
            "buy_list": []
        }

        # 根据PB筛选买入标的
        buy_candidates = []
        for stock in valid_snapshot:
            stock_code = stock.get("stock_code")
            stock_name = stock.get("stock_name", get_stock_name(stock_code))
            pb = stock.get("pb")

            if pb is not None:
                if stock_code == "招商银行" and pb <= 1.0:
                    buy_candidates.append(stock)
                elif (stock_code == "兴业银行" or stock_code == "工商银行") and pb <= 0.9:
                    buy_candidates.append(stock)
                elif stock_code == "双汇发展" and pb <= 1.5:
                    buy_candidates.append(stock)

        # 如果有候选标的，按PB排序
        if buy_candidates:
            buy_candidates.sort(key=lambda x: x.get("pb", float('inf')))
            plan["buy_list"] = [{"stock_code": buy_candidates[0]["stock_code"]}]
            stock_name = buy_candidates[0].get("stock_name", get_stock_name(buy_candidates[0]["stock_code"]))
            print(f"当前估值较低的标的：{stock_name} (PB: {buy_candidates[0]['pb']:.2f})")
        else:
            print("当前没有明显低估的标的")

        # 获取当前持仓市值
        holdings = portfolio.get_holdings()
        current_holdings = {}

        if not holdings.empty:
            # 计算每个持仓的市值
            holdings_list = holdings['stock_name'].tolist()
            holdings_snapshot = get_multiple_market_data(holdings_list)
            price_map = {}
            for s in holdings_snapshot:
                if 'error' not in s and s.get('price') is not None:
                    price_map[s['stock_code']] = s['price']

            for _, row in holdings.iterrows():
                stock_name = row['stock_name']
                shares = row['shares']
                # 尝试用name找code
                stock_code = stock_name
                price = price_map.get(stock_code)
                
                # 如果持仓名称是中文，可能需要转换
                if price is None:
                    # 尝试直接匹配
                    for code, name in [(s['stock_code'], s['stock_name']) for s in holdings_snapshot]:
                        if name == stock_name or code == stock_name:
                            price = price_map.get(code)
                            stock_code = code
                            break

                if price is not None:
                    current_holdings[stock_code] = shares * price
                else:
                    current_holdings[stock_code] = row['total_cost']

        # 生成执行计划（传入current_holdings）
        result = generate_execution_plan(
            plan,
            valid_snapshot,
            monthly_budget,
            current_holdings=current_holdings
        )

        # 询问是否执行建议
        confirm = input("\n是否要将此建议添加到交易记录？(y/n): ").strip().lower()
        if confirm == 'y':
            from datetime import datetime
            today = datetime.now().strftime('%Y-%m-%d')
            actions = result.get("actions", [])
            for action in actions:
                stock_code = action.get("stock_code")
                stock_name = action.get("stock_name", get_stock_name(stock_code))
                shares = action.get("shares", 0)
                price = action.get("price")
                if stock_code and shares > 0 and price:
                    portfolio.add_transaction(today, 'buy', stock_code, price, shares)
                    print(f"已添加：买入 {stock_name} {shares}股")
            print("✅ 已完成")

    except Exception as e:
        print(f"❌ 生成买入建议失败：{e}")


def menu_clear_data(portfolio):
    """清空数据（谨慎使用）"""
    print("\n⚠️  此操作将清空所有数据！")
    confirm = input("确定要清空吗？输入 YES 确认：")
    if confirm == "YES":
        portfolio.holdings = portfolio.holdings.iloc[0:0]
        portfolio.transactions = portfolio.transactions.iloc[0:0]
        portfolio.dividends = portfolio.dividends.iloc[0:0]
        portfolio.save_data()
        print("✅ 已清空所有数据")
    else:
        print("取消操作")


def main():
    print("="*50)
    print("  投资组合管理工具")
    print("="*50)

    portfolio = PortfolioManager()

    while True:
        print_separator()
        print("请选择操作：")
        print("1. 查看当前持仓")
        print("2. 添加买入记录")
        print("3. 添加卖出记录")
        print("4. 添加分红记录")
        print("5. 查看交易记录")
        print("6. 查看分红记录")
        print("7. 📊 运行分析")
        print("8. 📈 月度买入建议")
        print("9. ⚠️  清空所有数据")
        print("0. 退出")
        print_separator()

        choice = input("输入选项编号：").strip()

        if choice == "1":
            menu_view_holdings(portfolio)
        elif choice == "2":
            menu_add_buy(portfolio)
        elif choice == "3":
            menu_add_sell(portfolio)
        elif choice == "4":
            menu_add_dividend(portfolio)
        elif choice == "5":
            menu_view_transactions(portfolio)
        elif choice == "6":
            menu_view_dividends(portfolio)
        elif choice == "7":
            menu_run_analysis(portfolio)
        elif choice == "8":
            menu_buy_suggestion(portfolio)
        elif choice == "9":
            menu_clear_data(portfolio)
        elif choice == "0":
            print("\n👋 再见！")
            sys.exit(0)
        else:
            print("❌ 无效选项，请重新输入")

        input("\n按回车键继续...")


if __name__ == "__main__":
    main()
