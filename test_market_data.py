import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from market_data import get_multiple_market_data


STOCK_LIST = ["招商银行", "兴业银行", "工商银行", "双汇发展", "159307"]


def validate_snapshot(snapshot):
    results = []

    for stock in snapshot:
        stock_result = {"stock_name": stock.get("stock_name", "UNKNOWN"), "passed": True, "errors": []}

        if not isinstance(stock, dict):
            stock_result["passed"] = False
            stock_result["errors"].append("元素不是dict类型")
            results.append(stock_result)
            continue

        if "stock_name" not in stock:
            stock_result["passed"] = False
            stock_result["errors"].append("缺少 stock_name 字段")

        if "price" not in stock:
            stock_result["passed"] = False
            stock_result["errors"].append("缺少 price 字段")

        if "pb" not in stock:
            stock_result["passed"] = False
            stock_result["errors"].append("缺少 pb 字段")

        stock_name = stock.get("stock_name", "")

        if stock_name == "159307":
            if stock.get("price") is None:
                stock_result["passed"] = False
                stock_result["errors"].append("ETF价格不能为None")

            if stock.get("pb") is not None:
                stock_result["passed"] = False
                stock_result["errors"].append("ETF的PB必须为None，实际值: {}".format(stock.get("pb")))
        else:
            price = stock.get("price")
            if price is None:
                stock_result["passed"] = False
                stock_result["errors"].append("price不能为None")
            elif price <= 0:
                stock_result["passed"] = False
                stock_result["errors"].append("price必须大于0，实际值: {}".format(price))

            if stock_name in ["招商银行", "兴业银行", "工商银行"]:
                pb = stock.get("pb")
                if pb is not None and (pb < 0 or pb > 2):
                    stock_result["passed"] = False
                    stock_result["errors"].append("{} PB超出范围(0~2)，实际值: {}".format(stock_name, pb))

        results.append(stock_result)

    return results


def print_results(results):
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed

    print("\n" + "="*60)
    print("数据验证结果")
    print("="*60)

    for result in results:
        stock_name = result["stock_name"]
        if result["passed"]:
            print("[PASS] {}".format(stock_name))
        else:
            print("[FAIL] {}".format(stock_name))
            for error in result["errors"]:
                print("       - {}".format(error))
            print("       原始数据: {}".format(result))

    print("\n" + "-"*60)
    print("汇总:")
    print("  总数: {}".format(total))
    print("  通过: {}".format(passed))
    print("  失败: {}".format(failed))
    print("-"*60)

    if failed > 0:
        print("\n❌ 数据验证失败，请修复 market_data")
    else:
        print("\n✅ 数据验证通过，可以进入下一步策略验证")


def main():
    print("="*60)
    print("市场数据模块验证")
    print("="*60)
    print("测试标的: {}".format(STOCK_LIST))
    print("="*60)

    try:
        snapshot = get_multiple_market_data(STOCK_LIST)
    except Exception as e:
        print("\n❌ 数据获取失败: {}".format(str(e)))
        print("请检查 market_data 模块和网络连接")
        return

    if not snapshot:
        print("\n❌ 未获取到任何数据")
        return

    print("\n获取到 {} 条数据".format(len(snapshot)))

    results = validate_snapshot(snapshot)
    print_results(results)


if __name__ == "__main__":
    main()
