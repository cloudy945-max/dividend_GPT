#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
回测系统配置文件 - 集中管理所有可配置参数
"""

import os
from typing import Dict, List

# ==================== 基础配置 ====================
BACKTEST_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backtest_data')
CACHE_DIR = os.path.join(BACKTEST_DATA_DIR, 'cache')
LOG_DIR = os.path.join(BACKTEST_DATA_DIR, 'logs')
OUTPUT_DIR = 'backtest_output'

# 确保目录存在
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ==================== 回测参数 ====================
INITIAL_CASH = 100000.0  # 初始资金
MONTHLY_BUDGET = 3000.0   # 每月定投金额
COMMISSION_RATE = 0.0003  # 佣金费率 (万分之三)
MIN_COMMISSION = 5.0      # 最低佣金 (5元)

# ==================== 目标权重配置 ====================
TARGET_WEIGHTS: Dict[str, float] = {
    '招商银行': 0.25,
    '兴业银行': 0.25,
    '工商银行': 0.25,
    '双汇发展': 0.25,
}

# ETF配置
ETF_CODE = '159307'  # 红利低波100 ETF
ETF_NAME = '红利低波100'

# ==================== 强买机制配置 ====================
STRONG_BUY_PB_THRESHOLD = 1.0  # PB低于此值触发强买
STRONG_BUY_MULTIPLIER = 2.0    # 强买时投入金额为月度预算的倍数

# ==================== 资金池配置 ====================
MAX_CASH_POOL_RATIO = 4.0  # 最大资金池为月度预算的倍数
MIN_DEVIATION_TO_BUY = 0.05  # 最小偏离度触发再平衡

# ==================== 连续无成交配置 ====================
MAX_MONTHS_NO_STOCK = 3  # 连续无股票成交月份阈值，超过则购买ETF

# ==================== 分红配置 ====================
DIVIDEND_REINVEST_ENABLED = True  # 是否启用分红再投资

# ==================== 数据配置 ====================
DEFAULT_START_DATE = '2023-01-01'
DEFAULT_END_DATE = '2024-12-31'

# 股票代码映射
STOCK_CODE_MAPPING: Dict[str, str] = {
    '招商银行': 'sh600036',
    '兴业银行': 'sh601166',
    '工商银行': 'sh601398',
    '双汇发展': 'sz000895',
    '159307': 'sz159307',
    '红利低波100': 'sz159307',
    '沪深300': 'sh000300',
}

# 代码到名称的映射
CODE_TO_NAME: Dict[str, str] = {
    '招商银行': '招商银行',
    '兴业银行': '兴业银行',
    '工商银行': '工商银行',
    '双汇发展': '双汇发展',
    '159307': '红利低波100ETF',
}

# 名称到代码的映射
NAME_TO_CODE: Dict[str, str] = {
    '招商银行': '招商银行',
    '兴业银行': '兴业银行',
    '工商银行': '工商银行',
    '双汇发展': '双汇发展',
    '红利低波100ETF': '159307',
}

# 反向映射：akshare代码 -> 内部代码
STOCK_CODE_MAP: Dict[str, str] = {v: k for k, v in STOCK_CODE_MAPPING.items() if k != v}

# 基准配置
BENCHMARK_CODES: Dict[str, str] = {
    '沪深300': 'sh000300',
    '红利低波100': 'sz159307',
}

# ==================== 日志配置 ====================
LOG_LEVEL = 'INFO'
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# ==================== 性能配置 ====================
USE_CACHE_ONLY = False  # 是否仅使用缓存（不联网）
CACHE_EXPIRE_DAYS = 30  # 缓存有效期（天）

# ==================== 可视化配置 ====================
PLOT_WIDTH = 1200
PLOT_HEIGHT = 600
PLOT_DPI = 150  # 提高图表清晰度

# 图表配色方案（专业金融风格）
PLOT_COLORS = {
    'strategy': '#1f77b4',       # 策略曲线 - 蓝色
    'benchmark1': '#ff7f0e',     # 基准1 - 橙色
    'benchmark2': '#2ca02c',     # 基准2 - 绿色
    'benchmark3': '#d62728',     # 基准3 - 红色
    'drawdown': '#d62728',       # 回撤曲线 - 红色
    'drawdown_fill': '#ffcccc',  # 回撤填充 - 浅红色
    'equity_fill': '#e6f3ff',    # 权益曲线填充 - 浅蓝色
}

# 字体配置（支持中文显示）
FONT_FAMILIES = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS', 'DejaVu Sans']
FONT_SIZE = 12
TITLE_FONT_SIZE = 14
LABEL_FONT_SIZE = 11

# 图表风格
GRID_ALPHA = 0.3
LINE_WIDTH = 2.0
LINE_WIDTH_BENCHMARK = 1.5
MARKER_SIZE = 4

# ==================== 获取股票列表 ====================
def get_stock_list() -> List[str]:
    """获取目标股票列表"""
    return list(TARGET_WEIGHTS.keys())

def get_all_stocks_with_etf() -> List[str]:
    """获取包含ETF的完整股票列表"""
    return list(TARGET_WEIGHTS.keys()) + [ETF_CODE]

# ==================== 辅助函数 ====================
def validate_config() -> bool:
    """验证配置参数的合理性"""
    errors = []
    
    if INITIAL_CASH <= 0:
        errors.append("INITIAL_CASH 必须大于0")
    if MONTHLY_BUDGET <= 0:
        errors.append("MONTHLY_BUDGET 必须大于0")
    if COMMISSION_RATE < 0 or COMMISSION_RATE > 0.01:
        errors.append("COMMISSION_RATE 应在合理范围内(0-0.01)")
    if STRONG_BUY_PB_THRESHOLD <= 0:
        errors.append("STRONG_BUY_PB_THRESHOLD 必须大于0")
    
    total_weight = sum(TARGET_WEIGHTS.values())
    if abs(total_weight - 1.0) > 0.001:
        errors.append(f"TARGET_WEIGHTS 总和应为1.0，当前为{total_weight}")
    
    if errors:
        print("配置验证失败:")
        for error in errors:
            print(f"  - {error}")
        return False
    
    return True
