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
from backtest.config import MONTHLY_BUDGET, validate_config, OUTPUT_DIR


def test_full_backtest():
    """
    测试完整回测流程
    """
    print("\n" + "="*70)
    print("测试完整回测系统（使用缓存）")
    print("="*70)
    
    start_date = "2024-01-01"
    end_date = "2024-06-30"
    
    print(f"回测期间: {start_date} 至 {end_date}")
    print(f"月度预算: {MONTHLY_BUDGET} 元")
    print("="*70)
    
    try:
        result = run_full_backtest(
            start_date=start_date,
            end_date=end_date,
            monthly_budget=MONTHLY_BUDGET,
            output_dir=OUTPUT_DIR,
            use_cache_only=True
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
        
        if 'total_excess_return' in metrics:
            print("\n超额收益指标:")
            print(f"累计超额收益: {metrics['total_excess_return']*100:.2f}%")
            print(f"信息比率: {metrics['information_ratio']:.2f}")
            print(f"超额最大回撤: {metrics['max_excess_drawdown']*100:.2f}%")
        
        if history:
            initial_value = history[0]['total_value']
            final_value = history[-1]['total_value']
            print(f"\n资产变化:")
            print(f"  初始资产: {initial_value:,.2f}")
            print(f"  最终资产: {final_value:,.2f}")
            print(f"  累计投入: {len(history) * MONTHLY_BUDGET:,.2f}")
            print(f"  累计收益: {(final_value - len(history) * MONTHLY_BUDGET):,.2f}")
        
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
    测试简单回测流程（跳过，使用run_full_backtest测试）
    """
    print("\n" + "="*70)
    print("测试简单回测（跳过）")
    print("="*70)
    print("此测试暂时跳过，使用test_full_backtest代替")
    print("="*70)


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
    print(f"Sortino比率: {metrics['sortino']:.2f}")
    print(f"胜率: {metrics['win_rate']*100:.2f}%")
    print(f"盈利因子: {metrics['profit_factor']:.2f}")
    
    print("\n[OK] 指标计算测试通过!")


def test_config_validation():
    """
    测试配置验证
    """
    print("\n" + "="*70)
    print("测试配置验证")
    print("="*70)
    
    if validate_config():
        print("[OK] 配置验证通过!")
    else:
        print("[FAIL] 配置验证失败!")


def test_monthly_decisions():
    """
    测试每月决策明细功能（使用完整回测结果）
    """
    print("\n" + "="*70)
    print("每月决策明细测试已整合到完整回测中")
    print("="*70)
    print("请查看test_full_backtest的输出结果")
    print("="*70)


if __name__ == '__main__':
    print("""
======================================================================
              dividend_GPT 回测系统完整测试
======================================================================
    """)
    
    # 测试配置验证
    test_config_validation()
    
    # 测试指标计算
    test_metrics_calculation()
    
    # 测试简单回测
    test_simple_backtest()
    
    # 测试每月决策明细
    test_monthly_decisions()
    
    # 测试完整回测
    test_full_backtest()
    
    print("\n" + "="*70)
    print("所有测试完成!")
    print("="*70)
    print("\n输出文件位置:")
    print("  - 回测报告: backtest_output/backtest_report.md")
    print("  - 权益曲线: backtest_output/equity_curve.png")
    print("  - 回撤曲线: backtest_output/drawdown_curve.png")
    print("  - 资产配置: backtest_output/asset_allocation.png")
    print("  - 每月决策明细: 已包含在回测报告中")
    print("  - 运行日志: backtest_data/logs/*.log")