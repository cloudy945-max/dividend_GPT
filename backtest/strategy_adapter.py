#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
策略适配器 - 将生产环境的月度买入建议逻辑适配成回测可调用的函数
"""

import pandas as pd
import logging
from datetime import datetime
import sys
import os
from typing import Dict, List, Optional, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_data import (
    generate_execution_plan, 
    calculate_rebalance_buys,
    TARGET_WEIGHTS, 
    MIN_DEVIATION_TO_BUY,
    get_stock_name,
    CODE_TO_NAME
)

from .config import (
    TARGET_WEIGHTS as CONFIG_TARGET_WEIGHTS,
    MIN_DEVIATION_TO_BUY as CONFIG_MIN_DEVIATION_TO_BUY,
    STRONG_BUY_PB_THRESHOLD,
    STRONG_BUY_MULTIPLIER,
    MAX_CASH_POOL_RATIO,
    MAX_MONTHS_NO_STOCK,
    ETF_CODE,
    LOG_DIR
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'strategy_adapter.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class StrategyAdapter:
    """
    策略适配器类 - 将生产环境的月度买入建议逻辑适配成回测可调用的函数
    
    核心功能：
    1. 生成月度买入计划（包含强买判断）
    2. 管理资金池状态
    3. 跟踪连续无股票成交月份
    4. 执行再平衡逻辑
    """
    
    def __init__(self, target_weights: Optional[Dict[str, float]] = None):
        """
        初始化策略适配器
        
        Args:
            target_weights: 目标权重字典，如果为None则使用配置文件中的权重
        """
        self.target_weights = target_weights or CONFIG_TARGET_WEIGHTS.copy()
        self.min_deviation_to_buy = CONFIG_MIN_DEVIATION_TO_BUY
        
        # 强买配置（股票特定阈值，如果没有配置则使用全局阈值）
        self.pb_thresholds = {
            "招商银行": 0.85,
            "兴业银行": 0.75,
            "工商银行": 0.75,
            "双汇发展": 1.0
        }
        
        # 价格百分位阈值
        self.price_percentile_thresholds = {
            "招商银行": 0.15,
            "兴业银行": 0.25,
            "工商银行": 0.25,
            "双汇发展": 0.20
        }
        
        # 状态变量
        self.cash_pool = 0.0
        self.tracking_months_no_stock = 0
        
        logger.info("策略适配器初始化完成")

    def calculate_deviation(self, current_value: float, target_weight: float, total_value: float) -> float:
        """
        计算当前持仓与目标权重的偏差
        
        Args:
            current_value: 当前持仓市值
            target_weight: 目标权重
            total_value: 总资产
            
        Returns:
            偏差值（目标权重 - 当前权重）
        """
        if total_value <= 0:
            return 0
        current_weight = current_value / total_value
        return target_weight - current_weight

    def should_strong_buy(self, stock_code: str, snapshot: List[Dict[str, Any]]) -> bool:
        """
        判断是否应该强买某只股票
        
        Args:
            stock_code: 股票代码
            snapshot: 当前快照数据
            
        Returns:
            是否应该强买
        """
        # 获取PB值并判断
        pb = self._get_pb(snapshot, stock_code)
        if pb is not None:
            threshold = self.pb_thresholds.get(stock_code, STRONG_BUY_PB_THRESHOLD)
            if pb <= threshold:
                logger.info(f"强买触发(PB): {stock_code}, PB={pb:.3f} <= 阈值{threshold}")
                return True

        # 获取价格百分位并判断
        price_percentile = self._get_price_percentile(snapshot, stock_code)
        if price_percentile is not None:
            threshold = self.price_percentile_thresholds.get(stock_code, 0.15)
            if price_percentile <= threshold:
                logger.info(f"强买触发(价格百分位): {stock_code}, 百分位={price_percentile:.3f} <= 阈值{threshold}")
                return True

        return False

    def get_strong_buy_stock(self, snapshot: List[Dict[str, Any]]) -> tuple:
        """
        获取当前应该强买的股票（选择PB最低的）
        
        Args:
            snapshot: 当前快照数据
            
        Returns:
            (强买股票代码, PB值)，如果没有则返回(None, None)
        """
        strong_buy_stock = None
        strong_buy_pb = None

        for stock in snapshot:
            stock_code = stock.get("stock_code")
            pb = stock.get("pb")

            if pb is None:
                continue

            is_strong_buy = False
            threshold = self.pb_thresholds.get(stock_code, STRONG_BUY_PB_THRESHOLD)
            
            if pb <= threshold:
                is_strong_buy = True

            if is_strong_buy:
                if strong_buy_stock is None or pb < strong_buy_pb:
                    strong_buy_stock = stock_code
                    strong_buy_pb = pb

        return strong_buy_stock, strong_buy_pb

    def generate_monthly_buy_plan(self, snapshot: List[Dict[str, Any]], 
                                  current_holdings: Optional[Dict[str, float]], 
                                  available_cash: float, 
                                  monthly_budget: float) -> Dict[str, Any]:
        """
        生成月度买入计划（回测专用）
        
        Args:
            snapshot: 当前日期的快照数据（包含price、pb）
            current_holdings: 当前持仓市值字典 {stock_code: market_value}
            available_cash: 当前可用现金（资金池）
            monthly_budget: 月度预算
            
        Returns:
            {
                "actions": [
                    {
                        "stock_code": str,
                        "stock_name": str,
                        "shares": int,
                        "price": float,
                        "cost": float,
                        "reason": "strong_buy" | "rebalance" | "etf_allocation" | "fallback_etf"
                    }
                ],
                "cash_left": float,
                "cash_pool": float,
                "is_strong_buy": bool,
                "strong_buy_stock": str
            }
        """
        current_holdings = current_holdings or {}
        total_holdings_value = sum(current_holdings.values()) if current_holdings else 0.0
        
        # 检查强买
        strong_buy_stock, strong_buy_pb = self.get_strong_buy_stock(snapshot)
        strong_buy_flag = strong_buy_stock is not None
        
        # 最大资金池限制
        max_cash_pool = monthly_budget * MAX_CASH_POOL_RATIO
        
        logger.info(f"月度再平衡: 持仓价值={total_holdings_value:.2f}, 可用现金={available_cash:.2f}, "
                    f"月度预算={monthly_budget:.2f}, 资金池上限={max_cash_pool:.2f}")
        logger.info(f"强买检查: {strong_buy_stock} (PB={strong_buy_pb})")
        
        # 构建买入列表
        plan = {
            "buy_list": self._build_buy_list(snapshot, current_holdings, 
                                              total_holdings_value + available_cash + monthly_budget,
                                              strong_buy_flag)
        }

        # 执行计划
        execution_result = generate_execution_plan(
            plan=plan,
            snapshot=snapshot,
            monthly_budget=monthly_budget,
            current_holdings=current_holdings
        )

        # 为每个动作添加原因
        actions_with_reason = []
        for action in execution_result.get("actions", []):
            stock_code = action.get("stock_code")
            reason = "rebalance"
            
            if action.get("is_strong_buy", False) or stock_code == strong_buy_stock:
                reason = "strong_buy"
            elif action.get("is_fallback_etf", False):
                reason = "fallback_etf"
            elif stock_code == ETF_CODE:
                reason = "etf_allocation"

            actions_with_reason.append({
                "stock_code": stock_code,
                "stock_name": action.get("stock_name", get_stock_name(stock_code)),
                "shares": action.get("shares", 0),
                "price": action.get("price"),
                "cost": action.get("cost", 0),
                "reason": reason,
                "current_weight": action.get("current_weight", 0),
                "target_weight": action.get("target_weight", 0),
                "deviation": action.get("deviation", 0)
            })

        # 更新资金池状态
        self.cash_pool = min(execution_result.get("remaining_cash_pool", self.cash_pool), max_cash_pool)
        
        # 跟踪连续无股票成交月份
        has_stock_action = any(a["stock_code"] != ETF_CODE for a in actions_with_reason)
        if has_stock_action:
            self.tracking_months_no_stock = 0
            logger.info(f"本月有股票交易，重置连续无成交月份计数器")
        else:
            self.tracking_months_no_stock += 1
            logger.info(f"本月无股票交易，连续无成交月份: {self.tracking_months_no_stock}/{MAX_MONTHS_NO_STOCK}")

        # 如果连续无股票成交达到阈值，强制购买ETF
        if self.tracking_months_no_stock >= MAX_MONTHS_NO_STOCK:
            etf_price = self._get_price(snapshot, ETF_CODE)
            if etf_price is not None and etf_price > 0 and self.cash_pool >= etf_price * 100:
                max_lots = int(self.cash_pool / (etf_price * 100))
                shares = max_lots * 100
                cost = shares * etf_price
                
                actions_with_reason.append({
                    "stock_code": ETF_CODE,
                    "stock_name": get_stock_name(ETF_CODE),
                    "shares": shares,
                    "price": etf_price,
                    "cost": cost,
                    "reason": "fallback_etf",
                    "current_weight": 0,
                    "target_weight": 0,
                    "deviation": 0
                })
                self.cash_pool -= cost
                self.tracking_months_no_stock = 0
                logger.info(f"连续{MAX_MONTHS_NO_STOCK}个月无股票成交，触发ETF fallback购买")

        result = {
            "actions": actions_with_reason,
            "cash_left": execution_result.get("cash_left", 0.0),
            "cash_pool": self.cash_pool,
            "is_strong_buy": strong_buy_flag,
            "strong_buy_stock": strong_buy_stock
        }
        
        logger.info(f"月度买入计划生成完成: {len(actions_with_reason)}个动作, 剩余资金池={self.cash_pool:.2f}")
        
        return result

    def _build_buy_list(self, snapshot: List[Dict[str, Any]], 
                        current_holdings: Dict[str, float], 
                        total_value: float,
                        strong_buy_flag: bool = False) -> List[Dict[str, Any]]:
        """
        构建买入列表（按优先级排序）
        
        Args:
            snapshot: 当前快照数据
            current_holdings: 当前持仓
            total_value: 总资产
            strong_buy_flag: 是否有强买信号
            
        Returns:
            排序后的买入列表
        """
        sorted_stocks = []
        strong_buy_multiplier = STRONG_BUY_MULTIPLIER if strong_buy_flag else 1.0

        for stock_code in self.target_weights.keys():
            if stock_code == ETF_CODE:
                continue

            price = self._get_price(snapshot, stock_code)
            if price is None or price <= 0:
                continue

            current_value = current_holdings.get(stock_code, 0.0)
            deviation = self.calculate_deviation(current_value, self.target_weights[stock_code], total_value)

            # 强买优先级提升
            priority = 1.0
            if self.should_strong_buy(stock_code, snapshot):
                priority = 1.5 * strong_buy_multiplier

            effective_deviation = deviation * priority
            sorted_stocks.append((stock_code, effective_deviation, deviation))

        # 按有效偏差降序排序
        sorted_stocks.sort(key=lambda x: x[1], reverse=True)

        # 筛选出需要买入的股票
        buy_list = []
        for stock_code, effective_dev, original_dev in sorted_stocks:
            if original_dev >= self.min_deviation_to_buy:
                buy_list.append({
                    "stock_code": stock_code,
                    "deviation": original_dev,
                    "priority": effective_dev
                })
                logger.debug(f"加入买入列表: {stock_code}, 偏差={original_dev:.4f}, 有效偏差={effective_dev:.4f}")

        return buy_list

    def run_strategy(self, snapshot: List[Dict[str, Any]], 
                     current_holdings: Optional[Dict[str, float]], 
                     cash_pool: float, 
                     monthly_budget: float) -> Dict[str, Any]:
        """
        运行策略（简化版）
        
        Args:
            snapshot: 当前快照
            current_holdings: 当前持仓
            cash_pool: 资金池
            monthly_budget: 月度预算
            
        Returns:
            策略执行结果
        """
        if current_holdings is None:
            current_holdings = {}

        total_holdings_value = sum(current_holdings.values()) if current_holdings else 0.0
        total_value = total_holdings_value + cash_pool + monthly_budget

        buy_list = self._build_buy_list(snapshot, current_holdings, total_value)

        plan = {
            "buy_list": buy_list
        }

        result = generate_execution_plan(
            plan=plan,
            snapshot=snapshot,
            monthly_budget=monthly_budget,
            current_holdings=current_holdings
        )

        return {
            "actions": result.get("actions", []),
            "cash_left": result.get("cash_left", cash_pool),
            "cash_pool": result.get("remaining_cash_pool", cash_pool)
        }

    def select_stock_for_reinvest(self, snapshot: List[Dict[str, Any]], 
                                   current_holdings: Dict[str, float], 
                                   total_value: float) -> Optional[Dict[str, Any]]:
        """
        选择用于再投资的股票
        
        Args:
            snapshot: 当前快照
            current_holdings: 当前持仓
            total_value: 总资产
            
        Returns:
            最佳候选股票信息
        """
        candidates = []
        
        for stock_code in self.target_weights.keys():
            if stock_code == ETF_CODE:
                continue

            price = self._get_price(snapshot, stock_code)
            if price is None or price <= 0:
                continue

            lot_cost = price * 100  # 每手成本

            current_value = current_holdings.get(stock_code, 0.0)
            deviation = self.calculate_deviation(current_value, self.target_weights[stock_code], total_value)

            priority = 1.0
            if self.should_strong_buy(stock_code, snapshot):
                priority = 2.0

            score = deviation * priority
            
            candidates.append({
                'stock_code': stock_code,
                'stock_name': get_stock_name(stock_code),
                'price': price,
                'deviation': deviation,
                'priority': priority,
                'score': score,
                'lot_cost': lot_cost
            })
        
        if not candidates:
            return None
        
        # 按分数排序
        candidates.sort(key=lambda x: x['score'], reverse=True)
        
        # 返回第一个满足偏差要求的候选
        for candidate in candidates:
            if candidate['deviation'] >= self.min_deviation_to_buy * 0.5:
                return candidate
        
        # 如果都不满足，返回分数最高的
        return candidates[0] if candidates else None

    def _get_price(self, snapshot: List[Dict[str, Any]], stock_code: str) -> Optional[float]:
        """从快照中获取股票价格"""
        for stock in snapshot:
            if stock.get('stock_code') == stock_code:
                return stock.get('price')
        return None

    def _get_pb(self, snapshot: List[Dict[str, Any]], stock_code: str) -> Optional[float]:
        """从快照中获取股票PB"""
        for stock in snapshot:
            if stock.get('stock_code') == stock_code:
                return stock.get('pb')
        return None

    def _get_price_percentile(self, snapshot: List[Dict[str, Any]], stock_code: str) -> Optional[float]:
        """从快照中获取股票价格百分位"""
        for stock in snapshot:
            if stock.get('stock_code') == stock_code:
                return stock.get('price_percentile')
        return None

    def get_target_weights(self) -> Dict[str, float]:
        """获取目标权重"""
        return self.target_weights.copy()

    def set_target_weights(self, weights: Dict[str, float]) -> None:
        """设置目标权重"""
        self.target_weights = weights.copy()
        logger.info(f"目标权重已更新: {self.target_weights}")

    def reset(self) -> None:
        """重置状态"""
        self.cash_pool = 0.0
        self.tracking_months_no_stock = 0
        logger.info("策略适配器状态已重置")
