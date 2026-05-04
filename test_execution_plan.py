import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from market_data import generate_execution_plan


CASE1_SNAPSHOT = [
    {"stock_name": "招商银行", "stock_code": "招商银行", "price": 30, "pb": 1.0},
    {"stock_name": "兴业银行", "stock_code": "兴业银行", "price": 20, "pb": 0.9},
    {"stock_name": "工商银行", "stock_code": "工商银行", "price": 5, "pb": 0.8},
    {"stock_name": "双汇发展", "stock_code": "双汇发展", "price": 25, "pb": None},
    {"stock_name": "红利低波100ETF", "stock_code": "159307", "price": 1.2, "pb": None}
]

CASE2_SNAPSHOT = [
    {"stock_name": "招商银行", "stock_code": "招商银行", "price": 30, "pb": 0.8},
    {"stock_name": "兴业银行", "stock_code": "兴业银行", "price": 20, "pb": 0.9},
    {"stock_name": "工商银行", "stock_code": "工商银行", "price": 5, "pb": 0.8},
    {"stock_name": "双汇发展", "stock_code": "双汇发展", "price": 25, "pb": None},
    {"stock_name": "红利低波100ETF", "stock_code": "159307", "price": 1.2, "pb": None}
]

CASE3_SNAPSHOT = [
    {"stock_name": "招商银行", "stock_code": "招商银行", "price": 300, "pb": 1.0},
    {"stock_name": "兴业银行", "stock_code": "兴业银行", "price": 200, "pb": 0.9},
    {"stock_name": "工商银行", "stock_code": "工商银行", "price": 50, "pb": 0.8},
    {"stock_name": "双汇发展", "stock_code": "双汇发展", "price": 250, "pb": None},
    {"stock_name": "红利低波100ETF", "stock_code": "159307", "price": 10, "pb": None}
]

CASE4_SNAPSHOT = [
    {"stock_name": "招商银行", "stock_code": "招商银行", "price": 30, "pb": 1.0},
    {"stock_name": "兴业银行", "stock_code": "兴业银行", "price": 20, "pb": 0.9},
    {"stock_name": "工商银行", "stock_code": "工商银行", "price": 5, "pb": 0.8},
    {"stock_name": "双汇发展", "stock_code": "双汇发展", "price": 25, "pb": None},
    {"stock_name": "红利低波100ETF", "stock_code": "159307", "price": 1.2, "pb": None}
]

CASE4_HOLDINGS = {
    "招商银行": 30000,
    "兴业银行": 5000,
    "工商银行": 5000,
    "双汇发展": 0,
    "159307": 0
}


def make_plan():
    return {"buy_list": []}


def test_case1():
    print("\n==== CASE 1: 正常估值，无强买 ====")
    plan = make_plan()
    result = generate_execution_plan(plan, CASE1_SNAPSHOT, monthly_budget=3000, current_holdings={})

    passed = True
    reasons = []

    if result.get("is_strong_buy", False):
        passed = False
        reasons.append("CASE1: 不应触发 strong_buy，实际触发了")

    actions = result.get("actions", [])
    has_buy = any(a.get("action") == "buy" or "shares" in a for a in actions)
    if not has_buy:
        passed = False
        reasons.append("CASE1: 应有至少一个买入操作")

    if result.get("used_cash_pool", 0) > 0:
        passed = False
        reasons.append("CASE1: 不应使用资金池，实际使用了 {:.2f}".format(result.get("used_cash_pool", 0)))

    if passed:
        print("[PASS]")
    else:
        print("[FAIL]")
        for reason in reasons:
            print("  原因: {}".format(reason))

    return passed


def test_case2():
    print("\n==== CASE 2: 触发强买（招商银行 pb=0.8） ====")
    plan = make_plan()
    result = generate_execution_plan(plan, CASE2_SNAPSHOT, monthly_budget=3000, current_holdings={})

    passed = True
    reasons = []

    if not result.get("is_strong_buy", False):
        passed = False
        reasons.append("CASE2: 应触发 strong_buy，实际未触发")

    zsy_action = None
    for action in result.get("actions", []):
        if action.get("stock_code") == "招商银行":
            zsy_action = action
            break

    if zsy_action is None:
        passed = False
        reasons.append("CASE2: 招商银行应有买入")

    if result.get("used_cash_pool", 0) > 0:
        reasons.append("CASE2: 可能使用了资金池 {:.2f}（可接受）".format(result.get("used_cash_pool", 0)))

    if passed:
        print("[PASS]")
    else:
        print("[FAIL]")
        for reason in reasons:
            print("  原因: {}".format(reason))

    return passed


def test_case3():
    print("\n==== CASE 3: 全部买不起100股 ====")
    plan = make_plan()
    result = generate_execution_plan(plan, CASE3_SNAPSHOT, monthly_budget=3000, current_holdings={})

    passed = True
    reasons = []

    actions = result.get("actions", [])
    cash_left = result.get("cash_left", 0)

    has_valid_buy = False
    for action in actions:
        shares = action.get("shares", 0)
        if shares > 0:
            has_valid_buy = True
            break

    if has_valid_buy:
        passed = False
        reasons.append("CASE3: 资金不足3000元，不应有有效买入")

    if abs(cash_left - 3000) > 100:
        reasons.append("CASE3: cash_left 应接近 3000，实际 {:.2f}".format(cash_left))

    if passed:
        print("[PASS]")
    else:
        print("[FAIL]")
        for reason in reasons:
            print("  原因: {}".format(reason))

    return passed


def test_case4():
    print("\n==== CASE 4: 已有持仓 + 再平衡 ====")
    plan = make_plan()
    result = generate_execution_plan(plan, CASE4_SNAPSHOT, monthly_budget=3000, current_holdings=CASE4_HOLDINGS)

    passed = True
    reasons = []

    actions = result.get("actions", [])

    if len(actions) < 2:
        passed = False
        reasons.append("CASE4: 再平衡应有多个买入，当前只有 {} 个".format(len(actions)))

    stock_codes = [a.get("stock_code") for a in actions]
    if "双汇发展" not in stock_codes and "159307" not in stock_codes:
        passed = False
        reasons.append("CASE4: 应偏向买入低配资产（双汇发展 或 ETF）")

    zsy_holdings = CASE4_HOLDINGS.get("招商银行", 0)
    zsy_action = None
    for action in actions:
        if action.get("stock_code") == "招商银行":
            zsy_action = action
            break

    if zsy_action is not None and zsy_holdings > 0:
        passed = False
        reasons.append("CASE4: 招商银行已超配(30000)，不应继续买入")

    if passed:
        print("[PASS]")
    else:
        print("[FAIL]")
        for reason in reasons:
            print("  原因: {}".format(reason))

    return passed


def main():
    print("="*60)
    print("策略决策逻辑验证")
    print("="*60)

    results = []

    try:
        results.append(("CASE1", test_case1()))
    except Exception as e:
        print("[FAIL] CASE1 异常: {}".format(str(e)))
        results.append(("CASE1", False))

    try:
        results.append(("CASE2", test_case2()))
    except Exception as e:
        print("[FAIL] CASE2 异常: {}".format(str(e)))
        results.append(("CASE2", False))

    try:
        results.append(("CASE3", test_case3()))
    except Exception as e:
        print("[FAIL] CASE3 异常: {}".format(str(e)))
        results.append(("CASE3", False))

    try:
        results.append(("CASE4", test_case4()))
    except Exception as e:
        print("[FAIL] CASE4 异常: {}".format(str(e)))
        results.append(("CASE4", False))

    print("\n" + "="*60)
    print("汇总")
    print("="*60)

    passed_count = sum(1 for _, p in results if p)
    failed_count = len(results) - passed_count

    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print("  {}: {}".format(name, status))

    print("\n" + "-"*60)

    if failed_count == 0:
        print("✅ 策略决策逻辑验证通过")
    else:
        print("❌ 策略存在逻辑问题，请修复")


if __name__ == "__main__":
    main()
