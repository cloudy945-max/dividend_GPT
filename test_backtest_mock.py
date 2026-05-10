#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
使用模拟数据测试回测系统
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest.runner import generate_backtest_report
from backtest.metrics import calculate_metrics


def generate_mock_history():
    """生成模拟回测历史数据"""
    dates = []
    current_date = datetime(2023, 1, 1)
    end_date = datetime(2024, 12, 31)
    
    total_value = 3000
    monthly_budget = 3000
    
    history = []
    
    while current_date <= end_date:
        total_value += monthly_budget
        
        random_factor = 1 + np.random.normal(0, 0.05)
        total_value *= random_factor
        
        if np.random.random() < 0.05:
            total_value *= 0.9
        
        history.append({
            'date': current_date,
            'total_value': max(total_value, 3000),
            'cash': min(monthly_budget, total_value * 0.1),
            'cash_pool': min(monthly_budget * 2, total_value * 0.05),
            'holdings_value': max(total_value * 0.85, 0),
            'holdings': {
                '招商银行': 100,
                '兴业银行': 200,
                '工商银行': 150,
                '双汇发展': 80,
                '159307': 50
            }
        })
        
        current_date += timedelta(days=30)
    
    return history


def generate_mock_transactions():
    """生成模拟交易记录"""
    transactions = []
    dates = pd.date_range('2023-01-01', '2024-12-31', freq='MS')
    
    reasons = ['rebalance', 'strong_buy', 'etf_allocation']
    
    for date in dates:
        n_transactions = np.random.randint(1, 4)
        for _ in range(n_transactions):
            stock = np.random.choice(['招商银行', '兴业银行', '工商银行', '双汇发展', '159307'])
            transactions.append({
                'date': date,
                'type': 'buy',
                'stock_code': stock,
                'stock_name': stock,
                'shares': 100,
                'price': np.random.uniform(10, 100),
                'cost': np.random.uniform(1000, 10000),
                'commission': np.random.uniform(1, 10),
                'reason': np.random.choice(reasons)
            })
    
    return pd.DataFrame(transactions)


def test_with_mock_data():
    """使用模拟数据测试回测报告生成"""
    print("="*70)
    print("使用模拟数据测试回测系统")
    print("="*70)
    
    history = generate_mock_history()
    transactions_df = generate_mock_transactions()
    
    print(f"生成了 {len(history)} 个月的模拟数据")
    print(f"生成了 {len(transactions_df)} 条模拟交易记录")
    
    metrics = calculate_metrics(history)
    
    print("\n计算的绩效指标:")
    print(f"总收益率: {metrics['total_return']*100:.2f}%")
    print(f"年化收益率: {metrics['annual_return']*100:.2f}%")
    print(f"最大回撤: {metrics['max_drawdown']*100:.2f}%")
    print(f"波动率: {metrics['volatility']*100:.2f}%")
    print(f"夏普比率: {metrics['sharpe']:.2f}")
    print(f"Calmar比率: {metrics['calmar']:.2f}")
    print(f"IRR: {metrics['irr']*100:.2f}%")
    
    report_path = generate_backtest_report(
        history=history,
        metrics=metrics,
        transactions_df=transactions_df,
        benchmark_dates=None,
        benchmark_values=None,
        benchmark_name="等权重定投",
        start_date="2023-01-01",
        end_date="2024-12-31",
        monthly_budget=3000,
        output_dir='backtest_output'
    )
    
    print(f"\n[OK] 报告已生成: {report_path}")
    
    with open(report_path, 'r', encoding='utf-8') as f:
        content = f.read()
        lines = content.split('\n')[:30]
        print("\n报告预览 (前30行):")
        print("-"*50)
        for line in lines:
            print(line)
        print("-"*50)


def test_benchmark_comparison():
    """测试基准对比功能"""
    print("\n" + "="*70)
    print("测试基准对比功能")
    print("="*70)
    
    history = generate_mock_history()
    
    bench_dates = []
    bench_values = []
    
    current_value = 3000
    monthly_budget = 3000
    
    for record in history:
        bench_dates.append(record['date'])
        current_value += monthly_budget
        current_value *= (1 + np.random.normal(0.01, 0.04))
        bench_values.append(current_value)
    
    metrics = calculate_metrics(history)
    
    report_path = generate_backtest_report(
        history=history,
        metrics=metrics,
        transactions_df=pd.DataFrame(),
        benchmark_dates=bench_dates,
        benchmark_values=bench_values,
        benchmark_name="等权重定投",
        start_date="2023-01-01",
        end_date="2024-12-31",
        monthly_budget=3000,
        output_dir='backtest_output'
    )
    
    print(f"\n[OK] 包含基准对比的报告已生成: {report_path}")


if __name__ == '__main__':
    test_with_mock_data()
    test_benchmark_comparison()
    
    print("\n" + "="*70)
    print("模拟数据测试完成!")
    print("="*70)
    print("\n输出文件位置:")
    print("  - 回测报告: backtest_output/backtest_report.md")