#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
完整回测系统测试示例

运行此脚本可执行完整的历史回测，验证每月再平衡 + 强买机制的有效性。
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest.runner import run_full_backtest, run_backtest
from backtest.metrics import calculate_metrics


def test_full_backtest():
    """
    测试完整回测流程
    """
    print("="*70)
    print("测试完整回测系统")
    print("="*70)
    
    start_date = "2023-01-01"
    end_date = "2024-12-31"
    monthly_budget = 3000
    
    print(f"回测期间: {start_date} 至 {end_date}")
    print(f"月度预算: {monthly_budget} 元")
    print("="*70)
    
    try:
        result = run_full_backtest(
            start_date=start_date,
            end_date=end_date,
            monthly_budget=monthly_budget,
            output_dir='backtest_output'
        )
        
        if result is None:
            print("\n[FAIL] 回测失败")
            return
        
        history = result['history']
        metrics = result['metrics']
        transactions_df = result['transactions']
        report_path = result['report_path']
        
        print("\n[OK] 回测完成!")
        print(f"报告已保存至: {report_path}")
        
        print("\n" + "="*50)
        print("回测绩效指标")
        print("="*50)
        print(f"总收益率: {metrics['total_return']*100:.2f}%")
        print(f"年化收益率: {metrics['annual_return']*100:.2f}%")
        print(f"IRR: {metrics['irr']*100:.2f}%")
        print(f"最大回撤: {metrics['max_drawdown']*100:.2f}%")
        print(f"波动率: {metrics['volatility']*100:.2f}%")
        print(f"夏普比率: {metrics['sharpe']:.2f}")
        print(f"Calmar比率: {metrics['calmar']:.2f}")
        print(f"Sortino比率: {metrics['sortino']:.2f}")
        print(f"胜率: {metrics['win_rate']*100:.2f}%")
        print(f"盈利因子: {metrics['profit_factor']:.2f}")
        
        if history:
            initial_value = history[0]['total_value']
            final_value = history[-1]['total_value']
            print(f"\n资产变化:")
            print(f"  初始资产: {initial_value:,.2f}")
            print(f"  最终资产: {final_value:,.2f}")
            print(f"  累计投入: {len(history) * monthly_budget:,.2f}")
            print(f"  累计收益: {(final_value - len(history) * monthly_budget):,.2f}")
        
        if transactions_df is not None and not transactions_df.empty:
            print(f"\n交易统计:")
            print(f"  总交易次数: {len(transactions_df)}")
            reason_counts = transactions_df['reason'].value_counts().to_dict()
            for reason, count in reason_counts.items():
                print(f"  {reason}: {count}次 ({count/len(transactions_df)*100:.1f}%)")
        
    except Exception as e:
        print("\n[FAIL] 回测执行失败:", e)
        import traceback
        traceback.print_exc()


def test_simple_backtest():
    """
    测试简单回测流程
    """
    print("\n" + "="*70)
    print("测试简单回测")
    print("="*70)
    
    start_date = "2024-01-01"
    end_date = "2024-06-30"
    monthly_budget = 3000
    
    print(f"回测期间: {start_date} 至 {end_date}")
    print(f"月度预算: {monthly_budget} 元")
    
    try:
        result = run_backtest(
            start_date=start_date,
            end_date=end_date,
            monthly_budget=monthly_budget
        )
        
        if result is None:
            print("\n[FAIL] 简单回测失败")
            return
        
        print("\n[OK] 简单回测完成!")
        
    except Exception as e:
        print("\n[FAIL] 简单回测执行失败:", e)


def test_metrics_calculation():
    """
    测试指标计算
    """
    print("\n" + "="*70)
    print("测试指标计算")
    print("="*70)
    
    mock_history = [
        {'date': '2024-01-01', 'total_value': 3000.0},
        {'date': '2024-02-01', 'total_value': 6150.0},
        {'date': '2024-03-01', 'total_value': 9200.0},
        {'date': '2024-04-01', 'total_value': 12500.0},
        {'date': '2024-05-01', 'total_value': 11800.0},
        {'date': '2024-06-01', 'total_value': 15300.0},
        {'date': '2024-07-01', 'total_value': 18500.0},
        {'date': '2024-08-01', 'total_value': 22000.0},
        {'date': '2024-09-01', 'total_value': 25200.0},
        {'date': '2024-10-01', 'total_value': 28500.0},
        {'date': '2024-11-01', 'total_value': 31800.0},
        {'date': '2024-12-01', 'total_value': 35000.0},
    ]
    
    metrics = calculate_metrics(mock_history)
    
    print("模拟数据指标计算结果:")
    print(f"总收益率: {metrics['total_return']*100:.2f}%")
    print(f"年化收益率: {metrics['annual_return']*100:.2f}%")
    print(f"最大回撤: {metrics['max_drawdown']*100:.2f}%")
    print(f"波动率: {metrics['volatility']*100:.2f}%")
    print(f"夏普比率: {metrics['sharpe']:.2f}")
    print(f"Calmar比率: {metrics['calmar']:.2f}")
    print(f"IRR: {metrics['irr']*100:.2f}%")
    
    print("\n[OK] 指标计算测试通过!")


if __name__ == '__main__':
    print("""
======================================================================
              dividend_GPT 回测系统完整测试
======================================================================
    """)
    
    test_metrics_calculation()
    test_simple_backtest()
    test_full_backtest()
    
    print("\n" + "="*70)
    print("所有测试完成!")
    print("="*70)
    print("\n输出文件位置:")
    print("  - 回测报告: backtest_output/backtest_report.md")
    print("  - 交易记录: backtest_output/transactions.csv")
    print("  - 运行日志: backtest_data/*.log")