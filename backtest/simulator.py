#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
回测模拟器 - 模拟每月再平衡策略执行，更新持仓和交易记录
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from copy import deepcopy
import logging
import sys
import os
from typing import Dict, List, Optional, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from portfolio import PortfolioManager

from .config import (
    INITIAL_CASH, COMMISSION_RATE, MIN_COMMISSION, 
    DIVIDEND_REINVEST_ENABLED, ETF_CODE, LOG_DIR
)
from .data_loader import get_monthly_trading_dates

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'simulator.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TradeSimulator:
    """交易模拟器 - 模拟真实交易执行"""
    
    def __init__(self, initial_cash: float = INITIAL_CASH, commission_rate: float = COMMISSION_RATE):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.commission_rate = commission_rate
        self.positions: Dict[str, Dict[str, float]] = {}  # {stock_code: {'shares', 'cost', 'avg_price'}}
        self.transactions: List[Dict[str, Any]] = []
        self.dividends_received: List[Dict[str, Any]] = []
        self.current_date: Optional[datetime] = None

    def reset(self, initial_cash: Optional[float] = None) -> None:
        """重置模拟器状态"""
        if initial_cash is not None:
            self.initial_cash = initial_cash
        self.cash = self.initial_cash
        self.positions = {}
        self.transactions = []
        self.dividends_received = []
        self.current_date = None
        logger.info("交易模拟器已重置")

    def set_date(self, date: datetime) -> None:
        """设置当前日期"""
        self.current_date = pd.to_datetime(date)

    def _calculate_commission(self, cost: float) -> float:
        """计算佣金（考虑最低佣金）"""
        commission = cost * self.commission_rate
        return max(commission, MIN_COMMISSION)

    def buy(self, stock_code: str, shares: int, price: float, reason: str = 'unknown') -> bool:
        """
        买入股票
        
        Args:
            stock_code: 股票代码
            shares: 股数（应为100的整数倍）
            price: 买入价格
            reason: 买入原因
            
        Returns:
            是否买入成功
        """
        if shares <= 0 or price <= 0:
            return False
        
        # 确保是整手交易
        actual_lots = (shares // 100) * 100
        if actual_lots <= 0:
            return False
        
        actual_cost = actual_lots * price
        actual_commission = self._calculate_commission(actual_cost)
        total_actual_cost = actual_cost + actual_commission

        if total_actual_cost > self.cash:
            logger.warning(f"现金不足，无法买入 {stock_code}: 需{total_actual_cost:.2f}, 有{self.cash:.2f}")
            return False

        # 更新持仓
        if stock_code in self.positions:
            old_shares = self.positions[stock_code]['shares']
            old_cost = self.positions[stock_code]['cost']
            new_cost = old_cost + actual_cost
            new_shares = old_shares + actual_lots
            new_avg_price = new_cost / new_shares
            self.positions[stock_code] = {
                'shares': new_shares,
                'cost': new_cost,
                'avg_price': new_avg_price
            }
        else:
            self.positions[stock_code] = {
                'shares': actual_lots,
                'cost': actual_cost,
                'avg_price': price
            }

        self.cash -= total_actual_cost

        # 记录交易
        self.transactions.append({
            'date': self.current_date,
            'type': 'buy',
            'stock_code': stock_code,
            'stock_name': stock_code,
            'shares': actual_lots,
            'price': price,
            'cost': actual_cost,
            'commission': actual_commission,
            'cash_after': self.cash,
            'reason': reason
        })
        
        logger.debug(f"买入成功: {stock_code} {actual_lots}股 @ {price:.2f}, 花费{total_actual_cost:.2f}")
        return True

    def sell(self, stock_code: str, shares: int, price: float) -> bool:
        """卖出股票"""
        if stock_code not in self.positions:
            return False

        position = self.positions[stock_code]
        if shares > position['shares']:
            shares = position['shares']

        if shares <= 0:
            return False

        sell_lots = (shares // 100) * 100
        if sell_lots <= 0:
            return False

        proceeds = sell_lots * price
        commission = self._calculate_commission(proceeds)
        tax = proceeds * 0.001  # 印花税
        net_proceeds = proceeds - commission - tax

        if sell_lots == position['shares']:
            profit = proceeds - commission - tax - position['cost']
            del self.positions[stock_code]
        else:
            ratio = sell_lots / position['shares']
            cost_sold = position['cost'] * ratio
            profit = proceeds - commission - tax - cost_sold
            position['shares'] -= sell_lots
            position['cost'] -= cost_sold

        self.cash += net_proceeds

        self.transactions.append({
            'date': self.current_date,
            'type': 'sell',
            'stock_code': stock_code,
            'stock_name': stock_code,
            'shares': sell_lots,
            'price': price,
            'proceeds': proceeds,
            'commission': commission,
            'tax': tax,
            'profit': profit,
            'cash_after': self.cash
        })
        return True

    def receive_dividend(self, stock_code: str, dividend_per_share: float, shares: Optional[int] = None) -> float:
        """
        接收分红
        
        Args:
            stock_code: 股票代码
            dividend_per_share: 每股分红
            shares: 分红股数（默认使用全部持仓）
            
        Returns:
            分红金额
        """
        if stock_code not in self.positions:
            return 0.0
            
        position = self.positions[stock_code]
        actual_shares = shares if shares is not None else position['shares']
        
        if actual_shares > position['shares']:
            actual_shares = position['shares']
            
        dividend_amount = actual_shares * dividend_per_share
        self.cash += dividend_amount
        
        self.dividends_received.append({
            'date': self.current_date,
            'stock_code': stock_code,
            'stock_name': stock_code,
            'dividend_per_share': dividend_per_share,
            'shares': actual_shares,
            'amount': dividend_amount
        })
        
        logger.info(f"收到分红: {stock_code} {dividend_amount:.2f}元")
        return dividend_amount

    def reinvest_dividend(self, stock_code: str, price: float) -> bool:
        """
        分红再投资
        
        Args:
            stock_code: 股票代码
            price: 当前价格
            
        Returns:
            是否再投资成功
        """
        lot_cost = price * 100
        commission = self._calculate_commission(lot_cost)
        total_cost = lot_cost + commission
        
        if total_cost > self.cash:
            return False
        
        max_lots = int(self.cash // total_cost)
        actual_lots = max_lots * 100
        
        if actual_lots < 100:
            return False
        
        actual_cost = actual_lots * price
        actual_commission = self._calculate_commission(actual_cost)
        total_actual_cost = actual_cost + actual_commission
        
        # 更新持仓
        if stock_code in self.positions:
            old_shares = self.positions[stock_code]['shares']
            old_cost = self.positions[stock_code]['cost']
            new_cost = old_cost + actual_cost
            new_shares = old_shares + actual_lots
            new_avg_price = new_cost / new_shares
            self.positions[stock_code] = {
                'shares': new_shares,
                'cost': new_cost,
                'avg_price': new_avg_price
            }
        else:
            self.positions[stock_code] = {
                'shares': actual_lots,
                'cost': actual_cost,
                'avg_price': price
            }
        
        self.cash -= total_actual_cost
        
        self.transactions.append({
            'date': self.current_date,
            'type': 'dividend_reinvest',
            'stock_code': stock_code,
            'stock_name': stock_code,
            'shares': actual_lots,
            'price': price,
            'cost': actual_cost,
            'commission': actual_commission,
            'cash_after': self.cash,
            'source': 'dividend',
            'reason': 'dividend_reinvest'
        })
        
        logger.info(f"分红再投资: {stock_code} {actual_lots}股 @ {price:.2f}")
        return True

    def get_portfolio_value(self, price_map: Dict[str, float]) -> float:
        """获取总资产价值"""
        total_value = self.cash
        for stock_code, position in self.positions.items():
            price = price_map.get(stock_code, 0)
            if price > 0:
                total_value += position['shares'] * price
        return total_value

    def get_holdings_value(self, price_map: Dict[str, float]) -> Dict[str, float]:
        """获取各持仓市值"""
        holdings_value = {}
        for stock_code, position in self.positions.items():
            price = price_map.get(stock_code, 0)
            holdings_value[stock_code] = position['shares'] * price if price > 0 else 0
        return holdings_value

    def get_transactions_df(self) -> pd.DataFrame:
        """获取交易记录DataFrame"""
        if not self.transactions:
            return pd.DataFrame()
        return pd.DataFrame(self.transactions)

    def get_dividends_df(self) -> pd.DataFrame:
        """获取分红记录DataFrame"""
        if not self.dividends_received:
            return pd.DataFrame()
        return pd.DataFrame(self.dividends_received)

    def get_positions_snapshot(self) -> Dict[str, Dict[str, float]]:
        """获取持仓快照"""
        return deepcopy(self.positions)

    def get_current_holdings(self) -> Dict[str, float]:
        """获取当前持仓市值（按成本价计算）"""
        holdings = {}
        for stock_code, position in self.positions.items():
            holdings[stock_code] = position['shares'] * position['avg_price']
        return holdings

    def get_stock_count(self, stock_code: str) -> int:
        """获取持仓股数"""
        if stock_code not in self.positions:
            return 0
        return self.positions[stock_code]['shares']

    def can_buy_one_lot(self, stock_code: str, price_map: Dict[str, float]) -> tuple:
        """判断是否可以买入一手"""
        price = price_map.get(stock_code, 0)
        if price <= 0:
            return False, 0, 0
        lot_cost = price * 100
        commission = self._calculate_commission(lot_cost)
        total_cost = lot_cost + commission
        if self.cash >= total_cost:
            return True, lot_cost, total_cost
        return False, lot_cost, total_cost

    def get_accumulated_dividends(self) -> float:
        """获取累计分红金额"""
        return sum(d['amount'] for d in self.dividends_received)

    def get_reinvest_stats(self) -> Dict[str, Any]:
        """获取再投资统计"""
        reinvest_txs = [tx for tx in self.transactions if tx.get('source') == 'dividend']
        if not reinvest_txs:
            return {'count': 0, 'total_amount': 0, 'stocks': []}
        
        total = sum(tx['cost'] for tx in reinvest_txs)
        stocks = list(set(tx['stock_code'] for tx in reinvest_txs))
        return {
            'count': len(reinvest_txs),
            'total_amount': total,
            'stocks': stocks
        }


class BacktestEngine:
    """回测引擎 - 执行完整的回测流程"""
    
    def __init__(self, data_loader, strategy_adapter, use_portfolio_manager: bool = False, 
                 data_dir: str = 'backtest_data'):
        self.data_loader = data_loader
        self.strategy_adapter = strategy_adapter
        self.use_portfolio_manager = use_portfolio_manager
        self.data_dir = data_dir
        
        if use_portfolio_manager:
            self.portfolio_manager = PortfolioManager(data_dir=os.path.join(data_dir, 'portfolio'))
        else:
            self.portfolio_manager = None
        
        self.cash = 0.0
        self.cash_pool = 0.0
        self.holdings: Dict[str, int] = {}  # {stock_code: shares}
        self.history: List[Dict[str, Any]] = []
        self.transactions: List[Dict[str, Any]] = []
        self.monthly_records: List[Dict[str, Any]] = []
        self.monthly_decisions: List[Dict[str, Any]] = []  # 新增：存储每月决策明细
        
        logger.info("回测引擎初始化完成")

    def reset(self) -> None:
        """重置回测状态"""
        self.cash = 0.0
        self.cash_pool = 0.0
        self.holdings = {}
        self.history = []
        self.transactions = []
        self.monthly_records = []
        self.monthly_decisions = []  # 新增
        self.strategy_adapter.reset()
        
        if self.portfolio_manager:
            self.portfolio_manager.load_data()
        
        logger.info("回测引擎已重置")

    def run_backtest(self, stock_list: List[str], start_date: str, end_date: str, 
                     monthly_budget: float = 3000.0) -> List[Dict[str, Any]]:
        """
        运行回测
        
        Args:
            stock_list: 股票列表
            start_date: 开始日期
            end_date: 结束日期
            monthly_budget: 月度预算
            
        Returns:
            历史记录列表
        """
        self.reset()

        logger.info(f"="*60)
        logger.info(f"开始回测: {start_date} 至 {end_date}")
        logger.info(f"月度预算: {monthly_budget:.2f}")
        logger.info(f"股票列表: {stock_list}")
        logger.info(f"="*60)

        # 加载数据
        price_data = self.data_loader.load_price_history(stock_list, start_date, end_date)
        pb_data = self.data_loader.load_pb_history(stock_list, start_date, end_date)

        if not price_data:
            logger.error("未能加载价格数据")
            return self.history

        # 获取每月最后一个交易日（传入价格数据以验证日期有效性）
        monthly_dates = get_monthly_trading_dates(start_date, end_date, price_data)
        logger.info(f"共有 {len(monthly_dates)} 个调仓日期")

        for idx, month_date in enumerate(monthly_dates):
            logger.info(f"\n==== 第 {idx+1}/{len(monthly_dates)} 个月: {month_date.strftime('%Y-%m-%d')} ====")
            
            # 记录本月初始状态
            initial_cash = self.cash
            initial_cash_pool = self.cash_pool
            
            # 增加月度预算
            self.cash += monthly_budget
            logger.info(f"新增月度预算: {monthly_budget:.2f}, 当前现金: {self.cash:.2f}")
            
            # 构建快照
            snapshot = self._build_snapshot(price_data, pb_data, month_date)

            if not snapshot:
                logger.warning(f"无法构建 {month_date} 的快照")
                continue

            price_map = {s['stock_code']: s['price'] for s in snapshot}
            current_holdings_market_value = self._get_holdings_market_value(price_map)
            total_value_before = self.cash + self.cash_pool + sum(current_holdings_market_value.values())

            logger.info(f"当前持仓市值: {sum(current_holdings_market_value.values()):.2f}")
            logger.info(f"当前资金池: {self.cash_pool:.2f}")

            # 计算再平衡前的偏离度
            max_deviation, max_deviation_stock = self._calculate_max_deviation(
                snapshot, current_holdings_market_value, total_value_before
            )

            # 执行分红再投资（如果启用）
            if DIVIDEND_REINVEST_ENABLED and self.cash_pool > 0:
                self._process_dividend_reinvestment(snapshot, price_map, month_date)

            # 生成买入计划
            strategy_result = self.strategy_adapter.generate_monthly_buy_plan(
                snapshot=snapshot,
                current_holdings=current_holdings_market_value,
                available_cash=self.cash_pool,
                monthly_budget=monthly_budget
            )

            actions = strategy_result.get('actions', [])
            cash_pool_before = self.cash_pool
            self.cash_pool = strategy_result.get('cash_pool', self.cash_pool)
            cash_pool_change = self.cash_pool - cash_pool_before
            
            logger.info(f"本月强买: {'是' if strategy_result.get('is_strong_buy') else '否'}")
            if strategy_result.get('strong_buy_stock'):
                logger.info(f"强买标的: {strategy_result['strong_buy_stock']}")

            # 执行买入动作
            self._execute_actions(actions, price_map, month_date)

            # 计算月末资产
            holdings_value = self._calculate_holdings_market_value(price_map)
            total_value = self.cash + self.cash_pool + holdings_value

            # 计算本月执行金额
            executed_amount = self._calculate_monthly_executed_amount(month_date)

            # 记录本月操作
            logger.info(f"本月操作: {len(actions)} 笔")
            for action in actions:
                reason = action.get('reason', 'unknown')
                logger.info(f"  - 买入 {action['stock_name']} {action['shares']}股 @ {action['price']:.2f} = {action['cost']:.2f} ({reason})")
            
            logger.info(f"月末总资产: {total_value:.2f}")
            logger.info(f"  - 现金: {self.cash:.2f}")
            logger.info(f"  - 资金池: {self.cash_pool:.2f}")
            logger.info(f"  - 持仓: {holdings_value:.2f}")

            # 记录月度决策明细（新增）
            self._record_monthly_decision(
                date=month_date,
                total_value=total_value,
                cash=self.cash,
                cash_pool=self.cash_pool,
                cash_pool_change=cash_pool_change,
                max_deviation_stock=max_deviation_stock,
                max_deviation=max_deviation,
                actions=actions,
                executed_amount=executed_amount,
                is_strong_buy=strategy_result.get('is_strong_buy', False),
                strong_buy_stock=strategy_result.get('strong_buy_stock')
            )

            self._record_monthly_snapshot(month_date, total_value, holdings_value)

        logger.info("\n" + "="*60)
        logger.info("回测完成")
        logger.info("="*60)
        
        return self.history

    def _calculate_max_deviation(self, snapshot: List[Dict[str, Any]], 
                                holdings_market_value: Dict[str, float],
                                total_value: float) -> tuple:
        """
        计算再平衡前的最大偏离度
        
        Args:
            snapshot: 快照数据
            holdings_market_value: 持仓市值
            total_value: 总资产
            
        Returns:
            (最大偏离度, 偏离最大的标的)
        """
        if total_value <= 0:
            return 0.0, None
        
        target_weights = self.strategy_adapter.target_weights
        max_deviation = 0.0
        max_deviation_stock = None
        
        for stock in snapshot:
            stock_code = stock['stock_code']
            target_weight = target_weights.get(stock_code, 0)
            
            if target_weight > 0:
                current_market_value = holdings_market_value.get(stock_code, 0)
                current_weight = current_market_value / total_value
                deviation = current_weight - target_weight
                
                if abs(deviation) > max_deviation:
                    max_deviation = abs(deviation)
                    max_deviation_stock = stock_code
        
        return max_deviation, max_deviation_stock

    def _calculate_monthly_executed_amount(self, month_date: datetime) -> float:
        """
        计算本月执行金额
        
        Args:
            month_date: 月度日期
            
        Returns:
            本月执行金额
        """
        monthly_transactions = [
            tx for tx in self.transactions 
            if pd.to_datetime(tx['date']).date() == month_date.date()
        ]
        return sum(tx['cost'] for tx in monthly_transactions)

    def _record_monthly_decision(self, date: datetime, total_value: float, cash: float, 
                                cash_pool: float, cash_pool_change: float,
                                max_deviation_stock: Optional[str], max_deviation: float,
                                actions: List[Dict[str, Any]], executed_amount: float,
                                is_strong_buy: bool, strong_buy_stock: Optional[str]) -> None:
        """
        记录每月决策明细（新增）
        
        Args:
            date: 日期
            total_value: 总资产
            cash: 现金
            cash_pool: 资金池
            cash_pool_change: 资金池变化
            max_deviation_stock: 偏离最大的标的
            max_deviation: 最大偏离度
            actions: 买入操作
            executed_amount: 本月执行金额
            is_strong_buy: 是否强买
            strong_buy_stock: 强买标的
        """
        # 整理买入标的
        bought_stocks = []
        total_shares = 0
        buy_reasons = []
        
        for action in actions:
            bought_stocks.append(action.get('stock_name', action.get('stock_code')))
            total_shares += action.get('shares', 0)
            reason = action.get('reason', 'unknown')
            if reason not in buy_reasons:
                buy_reasons.append(reason)
        
        # 主要买入原因
        main_reason = buy_reasons[0] if buy_reasons else 'none'
        
        decision_record = {
            'date': date,
            'total_value': total_value,
            'cash': cash,
            'cash_pool': cash_pool,
            'cash_pool_change': cash_pool_change,
            'max_deviation_stock': max_deviation_stock,
            'max_deviation': max_deviation,
            'bought_stocks': ','.join(bought_stocks),
            'total_shares': total_shares,
            'buy_reason': main_reason,
            'executed_amount': executed_amount,
            'is_strong_buy': is_strong_buy,
            'strong_buy_stock': strong_buy_stock,
            'transaction_count': len(actions)
        }
        
        self.monthly_decisions.append(decision_record)

    def _process_dividend_reinvestment(self, snapshot: List[Dict[str, Any]], 
                                       price_map: Dict[str, float], 
                                       date: datetime) -> None:
        """
        处理分红再投资
        
        Args:
            snapshot: 当前快照
            price_map: 价格映射
            date: 当前日期
        """
        if self.cash_pool <= 0:
            return
        
        logger.info(f"执行分红再投资，可用资金: {self.cash_pool:.2f}")
        
        # 选择最佳再投资标的
        best_candidate = self.strategy_adapter.select_stock_for_reinvest(
            snapshot, self.holdings, self._calculate_holdings_market_value(price_map)
        )
        
        if best_candidate is None:
            logger.info("没有合适的再投资标的")
            return
        
        stock_code = best_candidate['stock_code']
        price = best_candidate['price']
        lot_cost = best_candidate['lot_cost']
        
        commission = self._calculate_commission(lot_cost)
        total_cost = lot_cost + commission
        
        if total_cost > self.cash_pool:
            logger.info("资金池不足，无法再投资")
            return
        
        # 执行再投资
        max_lots = int(self.cash_pool // total_cost)
        actual_lots = max_lots * 100
        
        if actual_lots > 0:
            actual_cost = actual_lots * price
            actual_commission = self._calculate_commission(actual_cost)
            
            # 更新持仓
            if stock_code in self.holdings:
                self.holdings[stock_code] += actual_lots
            else:
                self.holdings[stock_code] = actual_lots
            
            self.cash_pool -= (actual_cost + actual_commission)
            
            # 记录交易
            self.transactions.append({
                'date': date,
                'type': 'dividend_reinvest',
                'stock_code': stock_code,
                'stock_name': best_candidate['stock_name'],
                'shares': actual_lots,
                'price': price,
                'cost': actual_cost,
                'commission': actual_commission,
                'reason': 'dividend_reinvest'
            })
            
            logger.info(f"分红再投资: {stock_code} {actual_lots}股 @ {price:.2f}, 花费{actual_cost + actual_commission:.2f}")

    def _calculate_commission(self, cost: float) -> float:
        """计算佣金"""
        commission = cost * COMMISSION_RATE
        return max(commission, MIN_COMMISSION)

    def _build_snapshot(self, price_data: Dict[str, pd.DataFrame], 
                        pb_data: Dict[str, pd.DataFrame], 
                        date: datetime) -> List[Dict[str, Any]]:
        """构建指定日期的快照"""
        snapshot = []
        current_date = pd.to_datetime(date)

        for stock_code in price_data.keys():
            if stock_code not in price_data:
                continue

            df = price_data[stock_code]
            if df.empty:
                continue

            df_dates = pd.to_datetime(df['date'])
            valid_dates = df_dates[df_dates <= current_date]

            if valid_dates.empty:
                logger.debug(f"股票 {stock_code} 在 {current_date} 之前没有有效数据")
                continue

            # 使用iloc[-1]而不是[-1]来避免KeyError
            closest_date = valid_dates.iloc[-1]
            row = df[df['date'] == closest_date].iloc[0]

            pb = None
            if stock_code in pb_data and not pb_data[stock_code].empty:
                pb_df = pb_data[stock_code]
                pb_dates = pd.to_datetime(pb_df['date'])
                pb_valid = pb_dates[pb_dates <= current_date]
                if not pb_valid.empty:
                    pb_row = pb_df[pb_dates == pb_valid.iloc[-1]].iloc[0]
                    pb = pb_row['pb']

            price_percentile = self.data_loader.get_price_percentile(stock_code, closest_date)

            snapshot.append({
                'stock_code': stock_code,
                'stock_name': self._get_stock_name(stock_code),
                'price': row['close'],
                'pb': pb,
                'price_percentile': price_percentile,
                'data_date': closest_date
            })

        return snapshot

    def _get_stock_name(self, stock_code: str) -> str:
        """获取股票名称"""
        name_map = {
            "招商银行": "招商银行",
            "兴业银行": "兴业银行",
            "工商银行": "工商银行",
            "双汇发展": "双汇发展",
            "159307": "红利低波100ETF",
            ETF_CODE: "红利低波100ETF"
        }
        return name_map.get(stock_code, stock_code)

    def _get_holdings_market_value(self, price_map: Dict[str, float]) -> Dict[str, float]:
        """获取持仓市值"""
        holdings_market_value = {}
        for stock_code, shares in self.holdings.items():
            price = price_map.get(stock_code, 0)
            if price > 0:
                holdings_market_value[stock_code] = shares * price
        return holdings_market_value

    def _calculate_holdings_market_value(self, price_map: Dict[str, float]) -> float:
        """计算持仓总市值"""
        total = 0.0
        for stock_code, shares in self.holdings.items():
            price = price_map.get(stock_code, 0)
            if price > 0:
                total += shares * price
        return total

    def _execute_actions(self, actions: List[Dict[str, Any]], 
                         price_map: Dict[str, float], 
                         date: datetime) -> None:
        """执行买入动作"""
        for action in actions:
            stock_code = action.get('stock_code')
            shares = action.get('shares', 0)
            price = action.get('price')
            reason = action.get('reason', 'unknown')

            if shares <= 0 or price is None or price <= 0:
                continue

            cost = shares * price
            commission = self._calculate_commission(cost)
            total_cost = cost + commission

            # 优先使用资金池，再使用现金
            available_funds = self.cash_pool + self.cash
            
            if total_cost > available_funds:
                logger.warning(f"资金不足，跳过买入 {stock_code}: 需{total_cost:.2f}, 有{available_funds:.2f}")
                continue

            actual_lots = (shares // 100) * 100
            if actual_lots <= 0:
                continue

            actual_cost = actual_lots * price
            actual_commission = self._calculate_commission(actual_cost)
            total_actual_cost = actual_cost + actual_commission

            # 更新持仓
            if stock_code in self.holdings:
                self.holdings[stock_code] += actual_lots
            else:
                self.holdings[stock_code] = actual_lots

            # 优先使用资金池
            if self.cash_pool >= total_actual_cost:
                self.cash_pool -= total_actual_cost
            else:
                remaining = total_actual_cost - self.cash_pool
                self.cash_pool = 0
                self.cash -= remaining

            # 记录交易
            self.transactions.append({
                'date': date,
                'type': 'buy',
                'stock_code': stock_code,
                'stock_name': action.get('stock_name', stock_code),
                'shares': actual_lots,
                'price': price,
                'cost': actual_cost,
                'commission': actual_commission,
                'reason': reason
            })

            # 更新PortfolioManager
            if self.portfolio_manager:
                self.portfolio_manager.add_transaction(
                    date=date,
                    type_='buy',
                    stock_name=action.get('stock_name', stock_code),
                    price=price,
                    shares=actual_lots,
                    source='new_cash'
                )

    def _record_monthly_snapshot(self, date: datetime, total_value: float, holdings_value: float) -> None:
        """记录月度快照"""
        holdings_copy = deepcopy(self.holdings)
        
        monthly_record = {
            'date': date,
            'total_value': total_value,
            'cash': self.cash,
            'cash_pool': self.cash_pool,
            'holdings_value': holdings_value,
            'holdings': holdings_copy,
            'transactions_count': len(self.transactions)
        }
        
        self.monthly_records.append(monthly_record)
        self.history.append(monthly_record)

    def get_history_df(self) -> pd.DataFrame:
        """获取历史记录DataFrame"""
        if not self.history:
            return pd.DataFrame()
        df = pd.DataFrame(self.history)
        df['date'] = pd.to_datetime(df['date'])
        return df

    def get_transactions_df(self) -> pd.DataFrame:
        """获取交易记录DataFrame"""
        if not self.transactions:
            return pd.DataFrame()
        df = pd.DataFrame(self.transactions)
        df['date'] = pd.to_datetime(df['date'])
        return df

    def get_monthly_records(self) -> List[Dict[str, Any]]:
        """获取月度记录"""
        return self.monthly_records

    def get_monthly_decisions(self) -> List[Dict[str, Any]]:
        """获取每月决策明细（新增）"""
        return self.monthly_decisions

    def get_monthly_decisions_df(self) -> pd.DataFrame:
        """获取每月决策明细DataFrame（新增）"""
        if not self.monthly_decisions:
            return pd.DataFrame()
        df = pd.DataFrame(self.monthly_decisions)
        df['date'] = pd.to_datetime(df['date'])
        return df

    def get_summary(self) -> Dict[str, Any]:
        """获取回测概要"""
        if not self.history:
            return {}
        
        first_record = self.history[0]
        last_record = self.history[-1]
        
        initial_value = first_record['total_value']
        final_value = last_record['total_value']
        total_return = (final_value - initial_value) / initial_value if initial_value > 0 else 0
        
        dates = [r['date'] for r in self.history]
        days = (dates[-1] - dates[0]).days
        years = days / 365.0 if days > 0 else 1.0
        annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
        
        values = [r['total_value'] for r in self.history]
        running_max = np.maximum.accumulate(values)
        drawdown = (np.array(values) - running_max) / running_max
        max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0
        
        return {
            'initial_value': initial_value,
            'final_value': final_value,
            'total_return': total_return,
            'annual_return': annual_return,
            'max_drawdown': max_drawdown,
            'total_transactions': len(self.transactions),
            'months': len(self.history)
        }
