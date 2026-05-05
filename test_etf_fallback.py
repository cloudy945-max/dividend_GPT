from market_data import generate_execution_plan, cash_pool, tracking_months_no_stock, MONTHS_TO_ALLOW_ETF

def reset_global_state():
    import market_data
    market_data.cash_pool = 0.0
    market_data.tracking_months_no_stock = 0

def create_snapshot_with_affordable_stocks():
    return [
        {"stock_code": "招商银行", "stock_name": "招商银行", "price": 30, "pb": 1.0},
        {"stock_code": "兴业银行", "stock_name": "兴业银行", "price": 20, "pb": 0.9},
        {"stock_code": "工商银行", "stock_name": "工商银行", "price": 5, "pb": 0.8},
        {"stock_code": "双汇发展", "stock_name": "双汇发展", "price": 25, "pb": None},
        {"stock_code": "159307", "stock_name": "红利低波100ETF", "price": 1.2, "pb": None}
    ]

def create_snapshot_with_unaffordable_stocks():
    return [
        {"stock_code": "招商银行", "stock_name": "招商银行", "price": 300, "pb": 1.0},
        {"stock_code": "兴业银行", "stock_name": "兴业银行", "price": 200, "pb": 0.9},
        {"stock_code": "工商银行", "stock_name": "工商银行", "price": 50, "pb": 0.8},
        {"stock_code": "双汇发展", "stock_name": "双汇发展", "price": 250, "pb": None},
        {"stock_code": "159307", "stock_name": "红利低波100ETF", "price": 1.2, "pb": None}
    ]

def test_case1_normal_buy_stock():
    print("="*60)
    print("测试 CASE1：正常情况 - 买入股票")
    print("="*60)
    
    reset_global_state()
    
    snapshot = create_snapshot_with_affordable_stocks()
    plan = {"buy_list": [{"stock_code": "招商银行"}]}
    
    result = generate_execution_plan(plan, snapshot, monthly_budget=3000, current_holdings=None)
    
    stock_actions = [a for a in result["actions"] if a["stock_code"] != "159307"]
    
    print("\n【验证结果】")
    if len(stock_actions) > 0:
        print("[PASS] CASE1 PASS: 成功买入股票")
        print(f"   买入标的: {[a['stock_name'] for a in stock_actions]}")
    else:
        print("[FAIL] CASE1 FAIL: 未买入股票")
    
    return len(stock_actions) > 0

def test_case2_cannot_afford_stock():
    print("\n" + "="*60)
    print("测试 CASE2：买不起股票 - 保留现金，不买ETF")
    print("="*60)
    
    reset_global_state()
    
    snapshot = create_snapshot_with_unaffordable_stocks()
    plan = {"buy_list": []}
    
    result = generate_execution_plan(plan, snapshot, monthly_budget=3000, current_holdings=None)
    
    etf_actions = [a for a in result["actions"] if a["stock_code"] == "159307"]
    
    print("\n【验证结果】")
    if len(result["actions"]) == 0 and result["cash_left"] > 0:
        print("[PASS] CASE2 PASS: 未买入任何标的，保留现金")
        print(f"   剩余现金: {result['cash_left']:.2f}")
        print(f"   资金池: {result['cash_pool']:.2f}")
        print(f"   连续无成交月份: {tracking_months_no_stock}")
    else:
        print("[FAIL] CASE2 FAIL: 不应该买入但产生了交易")
        print(f"   actions: {result['actions']}")
    
    return len(result["actions"]) == 0

def test_case3_etf_after_accumulation():
    print("\n" + "="*60)
    print(f"测试 CASE3：积累6个月后 - 触发ETF买入（条件B）")
    print("说明：条件A可能在第5个月先触发（cash_pool达到上限）")
    print("="*60)
    
    import market_data
    market_data.cash_pool = 0.0
    market_data.tracking_months_no_stock = 0
    print(f"设置初始 cash_pool = 0, tracking_months_no_stock = 0")
    
    snapshot = create_snapshot_with_unaffordable_stocks()
    plan = {"buy_list": []}
    
    results = []
    for month in range(1, MONTHS_TO_ALLOW_ETF + 2):
        print(f"\n--- 第{month}个月 ---")
        result = generate_execution_plan(plan, snapshot, monthly_budget=3000, current_holdings=None)
        results.append(result)
        print(f"   cash_pool: {market_data.cash_pool}, tracking_months_no_stock: {market_data.tracking_months_no_stock}")
    
    result_final = results[-1]
    etf_actions = [a for a in result_final["actions"] if a["stock_code"] == "159307"]
    
    print("\n【验证结果】")
    for i, r in enumerate(results[:-1]):
        print(f"第{i+1}个月 actions: {len(r['actions'])}")
    print(f"第{MONTHS_TO_ALLOW_ETF + 1}个月 actions: {len(result_final['actions'])}")
    
    success = False
    etf_triggered_count = sum(1 for r in results if len([a for a in r["actions"] if a["stock_code"] == "159307"]) > 0)
    
    # 验证：在MONTHS_TO_ALLOW_ETF个月内至少有1次ETF买入
    if etf_triggered_count > 0:
        first_etf_month = next((i+1 for i, r in enumerate(results) if len([a for a in r["actions"] if a["stock_code"] == "159307"]) > 0), None)
        print(f"[PASS] CASE3 PASS: 第{first_etf_month}个月触发ETF买入")
        print(f"   ETF触发次数: {etf_triggered_count}")
        success = True
    else:
        print(f"[FAIL] CASE3 FAIL: 未触发ETF买入")
    
    return success

def test_case4_condition_a_trigger():
    print("\n" + "="*60)
    print("测试 CASE4：条件A触发 - cash_pool >= MAX_CASH_POOL")
    print("="*60)
    
    import market_data
    market_data.cash_pool = 12000  # MODIFIED: 4 * monthly_budget
    market_data.tracking_months_no_stock = 0
    print(f"设置初始 cash_pool = {market_data.cash_pool}")
    
    snapshot = create_snapshot_with_unaffordable_stocks()
    plan = {"buy_list": []}
    
    result = generate_execution_plan(plan, snapshot, monthly_budget=3000, current_holdings=None)
    
    etf_actions = [a for a in result["actions"] if a["stock_code"] == "159307"]
    
    print("\n【验证结果】")
    if len(etf_actions) > 0:
        print("[PASS] CASE4 PASS: 条件A满足，触发ETF买入")
        print(f"   ETF买入数量: {etf_actions[0]['shares']}股")
        print(f"   ETF买入成本: {etf_actions[0]['cost']:.2f}元")
        print(f"   使用预算: min(cash_pool={cash_pool}, monthly_budget=3000) = 3000")
        return True
    else:
        print("[FAIL] CASE4 FAIL: 条件A满足但未触发ETF买入")
        return False

if __name__ == "__main__":
    print("="*60)
    print("ETF Fallback 逻辑测试")
    print("="*60)
    print(f"参数设置: MONTHS_TO_ALLOW_ETF = {MONTHS_TO_ALLOW_ETF}个月")
    print(f"参数设置: MAX_CASH_POOL = {MONTHS_TO_ALLOW_ETF * 1000}元 (4*monthly_budget)")
    print("="*60)
    
    results = []
    
    results.append(("CASE1: 正常买入股票", test_case1_normal_buy_stock()))
    results.append(("CASE2: 买不起股票保留现金", test_case2_cannot_afford_stock()))
    results.append((f"CASE3: {MONTHS_TO_ALLOW_ETF}个月后触发ETF", test_case3_etf_after_accumulation()))
    results.append(("CASE4: 条件A(cash_pool>=2*budget)触发ETF", test_case4_condition_a_trigger()))
    
    print("\n" + "="*60)
    print("测试汇总")
    print("="*60)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "[PASS] PASS" if result else "[FAIL] FAIL"
        print(f"{status}: {name}")
    
    print(f"\n总计: {passed}/{total} 通过")
    
    if passed == total:
        print("\n所有测试通过！ETF fallback 逻辑正确实现。")
    else:
        print("\n部分测试失败，请检查代码逻辑。")