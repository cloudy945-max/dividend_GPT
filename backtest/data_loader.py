#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
历史数据加载器 - 提供可靠的历史日线（前复权）+ PB数据获取功能
支持缓存机制、重试机制和数据校验
"""

import akshare as ak
import pandas as pd
import numpy as np
import os
import pickle
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from .config import (
    CACHE_DIR, LOG_DIR, STOCK_CODE_MAP, STOCK_CODE_MAPPING, 
    CODE_TO_NAME, CACHE_EXPIRE_DAYS, USE_CACHE_ONLY
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'data_loader.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def retry_on_failure(max_retries=3, delay=2):
    """重试装饰器 - 处理akshare接口不稳定问题"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logger.warning(f"尝试 {attempt + 1}/{max_retries} 失败: {e}")
                    if attempt < max_retries - 1:
                        import time
                        time.sleep(delay)
            logger.error(f"所有 {max_retries} 次尝试均失败: {last_exception}")
            raise last_exception
        return wrapper
    return decorator


def get_last_trading_day_of_month(year: int, month: int) -> datetime:
    """
    获取指定年月的最后一个交易日
    
    Args:
        year: 年份
        month: 月份
        
    Returns:
        最后一个交易日的datetime对象
    """
    # 获取当月最后一天
    if month == 12:
        last_day = datetime(year, month, 31)
    else:
        last_day = datetime(year, month + 1, 1) - timedelta(days=1)
    
    # 检查是否为周末，如果是则往前找最近的交易日
    while last_day.weekday() >= 5:  # 5=Saturday, 6=Sunday
        last_day -= timedelta(days=1)
    
    return last_day


def get_monthly_trading_dates(start_date: str, end_date: str,
                              price_data: Optional[Dict[str, pd.DataFrame]] = None) -> List[datetime]:
    """
    获取指定日期范围内每个月的最后一个交易日
    
    Args:
        start_date: 开始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        price_data: 价格数据字典，用于验证日期是否存在（可选）
        
    Returns:
        每月最后一个交易日的列表
    """
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    
    dates = []
    current_date = start_dt
    
    while current_date <= end_dt:
        # 获取当月最后一个交易日（考虑周末）
        last_trading_day = get_last_trading_day_of_month(current_date.year, current_date.month)
        
        if last_trading_day >= start_dt and last_trading_day <= end_dt:
            # 如果提供了价格数据，验证日期是否存在
            if price_data and len(price_data) > 0:
                # 检查至少一个股票在该日期有数据
                date_exists = False
                for stock_code, df in price_data.items():
                    if not df.empty:
                        df_dates = pd.to_datetime(df['date'])
                        if (df_dates == last_trading_day).any():
                            date_exists = True
                            break
                
                if not date_exists:
                    # 如果该日期不存在数据，向前找最近的交易日
                    for offset in range(1, 10):
                        adjusted_date = last_trading_day - timedelta(days=offset)
                        if adjusted_date >= start_dt:
                            for stock_code, df in price_data.items():
                                if not df.empty:
                                    df_dates = pd.to_datetime(df['date'])
                                    if (df_dates == adjusted_date).any():
                                        last_trading_day = adjusted_date
                                        date_exists = True
                                        break
                            if date_exists:
                                break
            
            dates.append(last_trading_day)
        
        # 移动到下个月
        if current_date.month == 12:
            current_date = datetime(current_date.year + 1, 1, 1)
        else:
            current_date = datetime(current_date.year, current_date.month + 1, 1)
    
    return dates


class BacktestDataLoader:
    """历史数据加载器类"""
    
    def __init__(self, use_cache_only: bool = USE_CACHE_ONLY):
        self.cache_dir = CACHE_DIR
        os.makedirs(self.cache_dir, exist_ok=True)
        self._price_history: Dict[str, pd.DataFrame] = {}
        self._pb_history: Dict[str, pd.DataFrame] = {}
        self.use_cache_only = use_cache_only
        # 存储 PB 历史数据的平均和最近值，用于 fallback
        self._pb_fallback_cache: Dict[str, Dict[str, Any]] = {}
    
    def _generate_cache_key(self, *args: Any) -> str:
        """
        生成智能缓存键 - 使用更细致的键，包括列表排序等
        
        Args:
            args: 用于生成缓存键的参数
            
        Returns:
            哈希缓存键字符串
        """
        # 对每个参数进行规范处理，确保相同内容的不同顺序生成相同键
        processed_args = []
        for arg in args:
            if isinstance(arg, list):
                processed_args.append(tuple(sorted(arg)))
            else:
                processed_args.append(arg)
        
        key_str = "_".join(str(arg) for arg in processed_args)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _get_cache_path(self, stock_code: str, start_date: str, end_date: str, data_type: str = 'price') -> str:
        """获取缓存文件路径 - 使用智能缓存键"""
        cache_key = self._generate_cache_key(stock_code, start_date, end_date)
        filename = f"{data_type}_{cache_key}.pkl"
        return os.path.join(self.cache_dir, filename)
    
    def _get_batch_cache_path(self, stock_list: List[str], start_date: str, end_date: str, data_type: str) -> str:
        """获取批量缓存文件路径"""
        cache_key = self._generate_cache_key(tuple(sorted(stock_list)), start_date, end_date, data_type)
        filename = f"batch_{cache_key}_{data_type}.pkl"
        return os.path.join(self.cache_dir, filename)
    
    def _is_cache_valid(self, cache_path: str) -> bool:
        """检查缓存是否有效（未过期）"""
        if not os.path.exists(cache_path):
            return False
        
        file_mtime = datetime.fromtimestamp(os.path.getmtime(cache_path))
        cache_age = (datetime.now() - file_mtime).days
        
        return cache_age <= CACHE_EXPIRE_DAYS
    
    def _load_from_cache(self, stock_code: str, start_date: str, end_date: str, data_type: str = 'price') -> Optional[pd.DataFrame]:
        """从缓存加载数据"""
        cache_path = self._get_cache_path(stock_code, start_date, end_date, data_type)
        
        if not self._is_cache_valid(cache_path):
            logger.debug(f"缓存已过期或不存在: {cache_path}")
            return None
        
        try:
            with open(cache_path, 'rb') as f:
                data = pickle.load(f)
            logger.debug(f"从缓存加载 {data_type} 数据: {stock_code}")
            return data
        except Exception as e:
            logger.warning(f"缓存文件损坏，重新获取: {e}")
            if os.path.exists(cache_path):
                os.remove(cache_path)
            return None
    
    def _save_to_cache(self, stock_code: str, start_date: str, end_date: str, data: pd.DataFrame, data_type: str = 'price') -> None:
        """保存数据到缓存"""
        cache_path = self._get_cache_path(stock_code, start_date, end_date, data_type)
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(data, f)
            logger.debug(f"保存 {data_type} 数据到缓存: {stock_code}")
            
            # 如果是 PB 数据，同时保存 fallback 信息
            if data_type == 'pb' and not data.empty:
                self._save_pb_fallback_data(stock_code, data)
        except Exception as e:
            logger.warning(f"保存缓存失败: {e}")
    
    def _save_pb_fallback_data(self, stock_code: str, pb_df: pd.DataFrame) -> None:
        """保存 PB fallback 数据（历史平均和最近值）"""
        if 'pb' in pb_df.columns and not pb_df.empty:
            valid_pbs = pb_df[(pb_df['pb'] > 0) & 
                             (pb_df['pb'] >= 0.1) & 
                             (pb_df['pb'] <= 20)]['pb']
            if len(valid_pbs) > 0:
                self._pb_fallback_cache[stock_code] = {
                    'mean': valid_pbs.mean(),
                    'median': valid_pbs.median(),
                    'last_valid': valid_pbs.iloc[-1],
                    'min': valid_pbs.min(),
                    'max': valid_pbs.max(),
                    'count': len(valid_pbs)
                }
    
    def _validate_price_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        校验价格数据 - 更严格的数据质量检查
        
        Args:
            df: 价格数据DataFrame
            
        Returns:
            校验后的DataFrame
        """
        if df is None or df.empty:
            return df
        
        # 移除价格为0或负数的记录
        if 'close' in df.columns:
            df = df[df['close'] > 0]
        
        # 移除异常波动（单日涨跌幅超过30%视为异常）
        if 'pct_change' in df.columns:
            df = df[abs(df['pct_change']) <= 30]
        
        # 填充缺失值
        if 'close' in df.columns:
            df['close'] = df['close'].ffill().bfill()
        
        return df
    
    def _validate_pb_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        校验PB数据 - 更严格的合理范围（0.1-20）
        
        Args:
            df: PB数据DataFrame
            
        Returns:
            校验后的DataFrame
        """
        if df is None or df.empty:
            return df
        
        # 移除PB为0或负数的记录
        if 'pb' in df.columns:
            df = df[df['pb'] > 0]
        
        # 移除异常值（PB > 20 或 PB < 0.1 视为异常）
        if 'pb' in df.columns:
            df = df[(df['pb'] >= 0.1) & (df['pb'] <= 20)]
        
        # 填充缺失值
        if 'pb' in df.columns:
            df['pb'] = df['pb'].ffill().bfill()
        
        return df
    
    def _apply_pb_fallback(self, stock_code: str, date: datetime) -> Optional[float]:
        """
        应用 PB fallback 机制
        
        Args:
            stock_code: 股票代码
            date: 日期
            
        Returns:
            PB 值（可能是历史平均或最近值）
        """
        # 优先使用内存缓存
        if stock_code in self._pb_fallback_cache:
            fb = self._pb_fallback_cache[stock_code]
            logger.info(f"使用 PB fallback 数据: {stock_code}, last_valid={fb['last_valid']:.2f}")
            return fb['last_valid']
        
        # 尝试从历史 PB 数据中找最近的有效值
        if stock_code in self._pb_history:
            pb_df = self._pb_history[stock_code]
            if not pb_df.empty and 'pb' in pb_df.columns:
                valid_pb = pb_df[(pb_df['pb'] >= 0.1) & 
                                (pb_df['pb'] <= 20) & 
                                (pb_df['date'] <= date)]
                if not valid_pb.empty:
                    last_pb = valid_pb.iloc[-1]['pb']
                    logger.info(f"使用历史 PB: {stock_code}, last={last_pb:.2f}")
                    return last_pb
        
        logger.warning(f"无法获取 {stock_code} 的 PB 数据，使用默认值 1.0")
        return 1.0
    
    @retry_on_failure(max_retries=3, delay=2)
    def _load_stock_daily(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """加载股票日线数据（前复权）"""
        df = ak.stock_zh_a_hist(
            symbol=symbol,
            start_date=start_date.replace('-', ''),
            end_date=end_date.replace('-', ''),
            adjust="qfq"
        )
        if df is None or df.empty:
            raise ValueError("获取日线数据为空")
        return df
    
    @retry_on_failure(max_retries=3, delay=2)
    def _load_etf_daily(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """加载ETF日线数据"""
        df = ak.fund_etf_hist_em(symbol=symbol)
        if df is None or df.empty:
            raise ValueError("获取ETF数据为空")
        df = df[(df['日期'] >= start_date) & (df['日期'] <= end_date)]
        return df
    
    @retry_on_failure(max_retries=3, delay=2)
    def _load_index_daily(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """加载指数日线数据"""
        df = ak.stock_zh_index_daily(symbol=symbol)
        if df is None or df.empty:
            raise ValueError("获取指数数据为空")
        df = df[(df['日期'] >= start_date) & (df['日期'] <= end_date)]
        return df
    
    def _fetch_price_data(self, stock_code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """获取价格数据"""
        if self.use_cache_only:
            logger.debug(f"use_cache_only=True，跳过网络请求: {stock_code}")
            return None
        
        try:
            if stock_code == "159307":
                df = self._load_etf_daily(stock_code, start_date, end_date)
                df = df.rename(columns={'日期': 'date', '收盘': 'close'})
            elif stock_code.startswith(('sh', 'sz')) and len(stock_code) == 9:
                # 指数代码
                df = self._load_index_daily(stock_code, start_date, end_date)
                df = df.rename(columns={'日期': 'date', '收盘': 'close'})
            else:
                symbol = STOCK_CODE_MAP.get(stock_code, stock_code)
                df = self._load_stock_daily(symbol, start_date, end_date)
                df = df.rename(columns={'日期': 'date', '收盘': 'close'})
            
            df['date'] = pd.to_datetime(df['date'])
            df = self._validate_price_data(df)
            return df[['date', 'close']]
        except Exception as e:
            logger.error(f"加载 {stock_code} 价格数据失败: {e}")
            return None
    
    def load_price_history(self, stock_list: List[str], start_date: str, end_date: str,
                          force_refresh: bool = False) -> Dict[str, pd.DataFrame]:
        """
        加载多个股票的价格历史数据（支持批量处理）
        
        Args:
            stock_list: 股票代码列表
            start_date: 开始日期
            end_date: 结束日期
            force_refresh: 是否强制刷新缓存
            
        Returns:
            股票代码到DataFrame的字典
        """
        result = {}
        raw_data = {}
        
        # 尝试批量加载缓存
        batch_cache_path = self._get_batch_cache_path(stock_list, start_date, end_date, 'price')
        if not force_refresh and self._is_cache_valid(batch_cache_path):
            try:
                with open(batch_cache_path, 'rb') as f:
                    cached_batch = pickle.load(f)
                logger.info(f"从批量缓存加载价格数据: {len(cached_batch)} 只股票")
                return cached_batch
            except Exception as e:
                logger.warning(f"批量缓存加载失败，单独加载: {e}")
        
        for stock_code in stock_list:
            cached = None if force_refresh else self._load_from_cache(stock_code, start_date, end_date, 'price')
            
            if cached is not None:
                df = cached
            else:
                df = self._fetch_price_data(stock_code, start_date, end_date)
                if df is not None:
                    self._save_to_cache(stock_code, start_date, end_date, df, 'price')
            
            if df is not None and not df.empty:
                df = df[['date', 'close']].copy()
                df['date'] = pd.to_datetime(df['date'])
                df = df.drop_duplicates(subset='date').set_index('date').sort_index()
                raw_data[stock_code] = df
                self._price_history[stock_code] = df
        
        if not raw_data:
            return result
        
        trading_dates = self._get_common_trading_dates(raw_data, start_date, end_date)
        
        for stock_code, df in raw_data.items():
            aligned_df = self._align_and_fill(df, trading_dates)
            result[stock_code] = aligned_df
        
        # 保存批量缓存
        if result:
            try:
                with open(batch_cache_path, 'wb') as f:
                    pickle.dump(result, f)
                logger.debug(f"保存批量价格缓存: {len(result)} 只股票")
            except Exception as e:
                logger.warning(f"保存批量缓存失败: {e}")
        
        return result
    
    def _fetch_pb_data(self, stock_code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """获取PB数据（优化后的 fallback 顺序）"""
        if self.use_cache_only:
            logger.debug(f"use_cache_only=True，跳过网络请求: {stock_code}")
            return None
        
        ak_code = STOCK_CODE_MAPPING.get(stock_code, stock_code)
        if ak_code.startswith('sh'):
            ak_code = ak_code[2:]
        elif ak_code.startswith('sz'):
            ak_code = ak_code[2:]
        
        # 优化后的 PB 获取顺序，优先使用最稳定的接口
        pb_methods = [
            # 1. 优先从日线数据获取（最稳定）
            ('daily', lambda: self._fetch_pb_from_daily(stock_code, start_date, end_date)),
            # 2. stock_a_lg_indicator (支持日期范围)
            ('stock_a_lg_indicator', lambda: ak.stock_a_lg_indicator(symbol=ak_code, start_date=start_date, end_date=end_date)),
            # 3. 从个股信息获取当前 PB（最可靠）
            ('stock_individual_info_em', lambda: self._fetch_pb_from_info(ak_code)),
            # 4. stock_a_indicator (简洁接口)
            ('stock_a_indicator', lambda: ak.stock_a_indicator(symbol=ak_code)),
            # 5. stock_financial_analysis_indicator (财务指标)
            ('stock_financial_analysis_indicator', lambda: ak.stock_financial_analysis_indicator(symbol=ak_code)),
        ]
        
        for method_name, method in pb_methods:
            try:
                df = method()
                if df is not None and not df.empty:
                    df = self._process_pb_df(df)
                    if df is not None:
                        logger.info(f"使用 {method_name} 获取到PB数据: {stock_code}")
                        return df
            except Exception as method_e:
                logger.debug(f"尝试 {method_name} 失败: {method_e}")
        
        # Fallback: 使用历史缓存数据
        if stock_code in self._pb_fallback_cache:
            fb = self._pb_fallback_cache[stock_code]
            logger.info(f"使用历史 PB fallback: {stock_code}, mean={fb['mean']:.2f}")
            return pd.DataFrame({
                'date': [pd.to_datetime(start_date)],
                'pb': [fb['mean']]
            })
        
        logger.warning(f"所有 PB 获取方法失败: {stock_code}")
        return None
    
    def _fetch_pb_from_info(self, symbol: str) -> Optional[pd.DataFrame]:
        """从个股信息中获取 PB 数据"""
        try:
            df = ak.stock_individual_info_em(symbol=symbol)
            if df is not None and not df.empty:
                pb_row = df[df['item'].str.contains('市净率', na=False)]
                if not pb_row.empty:
                    pb_value = float(pb_row.iloc[0]['value'])
                    return pd.DataFrame({
                        'date': [datetime.now()],
                        'pb': [pb_value]
                    })
        except Exception as e:
            logger.debug(f"从个股信息获取PB失败: {e}")
        return None
    
    def _process_pb_df(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """处理PB数据DataFrame"""
        # 查找PB列
        pb_col = None
        date_col = None
        
        for col in df.columns:
            if 'pb' in col.lower() or '市净' in col:
                pb_col = col
            if 'date' in col.lower() or '日期' in col or '报告日期' in col:
                date_col = col
        
        if pb_col is None:
            return None
        
        if date_col is None:
            date_col = 'date' if 'date' in df.columns else df.columns[0]
        
        df = df.rename(columns={date_col: 'date', pb_col: 'pb'})
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df = df.dropna(subset=['date', 'pb'])
        df = df[['date', 'pb']].sort_values('date').drop_duplicates(subset='date')
        df = self._validate_pb_data(df)
        
        return df
    
    def _fetch_pb_from_daily(self, stock_code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """从日线数据获取PB"""
        try:
            ak_code = STOCK_CODE_MAPPING.get(stock_code, stock_code)
            df = ak.stock_zh_a_hist(
                symbol=ak_code.replace('sh', '').replace('sz', ''),
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq"
            )
            
            if df is not None and not df.empty:
                if '市净率' in df.columns:
                    df = df.rename(columns={'日期': 'date', '市净率': 'pb'})
                    df['date'] = pd.to_datetime(df['date'])
                    df = df[['date', 'pb']].sort_values('date').drop_duplicates(subset='date')
                    df = self._validate_pb_data(df)
                    return df
        except Exception as e:
            logger.debug(f"尝试从日线获取PB失败: {e}")
        
        return None
    
    def load_pb_history(self, stock_list: List[str], start_date: str, end_date: str,
                        force_refresh: bool = False) -> Dict[str, pd.DataFrame]:
        """加载PB历史数据（支持批量缓存）"""
        result = {}
        
        # 尝试批量加载缓存
        batch_cache_path = self._get_batch_cache_path(stock_list, start_date, end_date, 'pb')
        if not force_refresh and self._is_cache_valid(batch_cache_path):
            try:
                with open(batch_cache_path, 'rb') as f:
                    cached_batch = pickle.load(f)
                logger.info(f"从批量缓存加载PB数据: {len(cached_batch)} 只股票")
                for stock_code, df in cached_batch.items():
                    self._pb_history[stock_code] = df
                return cached_batch
            except Exception as e:
                logger.warning(f"批量PB缓存加载失败，单独加载: {e}")
        
        for stock_code in stock_list:
            if stock_code == "159307":
                result[stock_code] = pd.DataFrame({'date': [], 'pb': []})
                continue
            
            cached = None if force_refresh else self._load_from_cache(stock_code, start_date, end_date, 'pb')
            
            if cached is not None:
                pb_df = cached
            else:
                pb_df = self._fetch_pb_data(stock_code, start_date, end_date)
                if pb_df is not None:
                    self._save_to_cache(stock_code, start_date, end_date, pb_df, 'pb')
            
            if pb_df is not None and not pb_df.empty:
                self._pb_history[stock_code] = pb_df
                result[stock_code] = pb_df
        
        # 保存批量缓存
        if result:
            try:
                with open(batch_cache_path, 'wb') as f:
                    pickle.dump(result, f)
                logger.debug(f"保存批量PB缓存: {len(result)} 只股票")
            except Exception as e:
                logger.warning(f"保存批量PB缓存失败: {e}")
        
        return result
    
    def _get_common_trading_dates(self, raw_data: Dict[str, pd.DataFrame], start_date: str, end_date: str) -> List[datetime]:
        """获取所有股票的共同交易日"""
        all_dates = []
        for df in raw_data.values():
            all_dates.extend(df.index.tolist())
        
        date_counts = pd.Series(all_dates).value_counts()
        common_dates = date_counts[date_counts == len(raw_data)].index
        common_dates = pd.to_datetime(common_dates)
        common_dates = common_dates[(common_dates >= pd.to_datetime(start_date)) &
                                   (common_dates <= pd.to_datetime(end_date))]
        return sorted(common_dates)
    
    def _align_and_fill(self, df: pd.DataFrame, trading_dates: List[datetime]) -> pd.DataFrame:
        """对齐并填充缺失数据"""
        aligned = pd.DataFrame(index=trading_dates)
        aligned.index.name = 'date'
        
        df_aligned = aligned.join(df, how='left')
        df_aligned['close'] = df_aligned['close'].ffill().bfill()
        
        df_aligned = df_aligned.reset_index()
        return df_aligned
    
    def get_monthly_snapshots(self, stock_list: List[str], start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """
        获取每月快照数据 - 增强数据质量校验
        
        Args:
            stock_list: 股票列表
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            快照列表
        """
        price_data = self.load_price_history(stock_list, start_date, end_date)
        pb_data = self.load_pb_history(stock_list, start_date, end_date)
        
        if not price_data:
            logger.warning("没有价格数据，无法生成快照")
            return []
        
        monthly_dates = get_monthly_trading_dates(start_date, end_date, price_data)
        
        snapshots = []
        for date in monthly_dates:
            snapshot = self._build_snapshot(date, price_data, pb_data)
            if snapshot:
                snapshots.append({
                    'date': date,
                    'snapshot': snapshot
                })
        
        return snapshots
    
    def _build_snapshot(self, date: datetime, price_data: Dict[str, pd.DataFrame],
                        pb_data: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        """
        构建指定日期的快照 - 增强数据质量校验
        
        Args:
            date: 日期
            price_data: 价格数据
            pb_data: PB数据
            
        Returns:
            快照列表
        """
        snapshot = []
        
        for stock_code in price_data.keys():
            price_df = price_data.get(stock_code)
            if price_df is None or price_df.empty:
                continue
            
            price_row = price_df[price_df['date'] == date]
            if price_row.empty:
                valid_dates = price_df[price_df['date'] <= date]
                if valid_dates.empty:
                    continue
                price_row = valid_dates.iloc[-1:]
            
            price = price_row['close'].iloc[0]
            price_date = price_row['date'].iloc[0]
            
            # 校验价格
            if price <= 0:
                logger.warning(f"价格异常: {stock_code}, price={price}")
                continue
            
            pb = None
            pb_df = pb_data.get(stock_code)
            if pb_df is not None and not pb_df.empty:
                pb_row = pb_df[pb_df['date'] <= date]
                if not pb_row.empty:
                    pb_row = pb_row.iloc[-1:]
                    pb = pb_row['pb'].iloc[0]
            
            # PB fallback 机制
            if pb is None or not (0.1 <= pb <= 20):
                pb = self._apply_pb_fallback(stock_code, date)
            
            price_percentile = self.get_price_percentile(stock_code, date)
            
            snapshot.append({
                'stock_code': stock_code,
                'stock_name': CODE_TO_NAME.get(stock_code, stock_code),
                'price': price,
                'pb': pb,
                'price_percentile': price_percentile,
                'data_date': price_date
            })
        
        return snapshot
    
    def get_snapshot_at_date(self, date: datetime,
                             price_data: Optional[Dict[str, pd.DataFrame]] = None,
                             pb_data: Optional[Dict[str, pd.DataFrame]] = None) -> List[Dict[str, Any]]:
        """获取指定日期的快照"""
        if price_data is None:
            price_data = self._price_history
        if pb_data is None:
            pb_data = self._pb_history
        
        snapshot = []
        date = pd.to_datetime(date)
        
        for stock_code in price_data.keys():
            df = price_data.get(stock_code)
            if df is None or df.empty:
                continue
            
            valid_dates = df[df['date'] <= date]
            if valid_dates.empty:
                continue
            
            row = valid_dates.iloc[-1]
            
            pb = None
            pb_df = pb_data.get(stock_code)
            if pb_df is not None and not pb_df.empty:
                pb_valid = pb_df[pb_df['date'] <= date]
                if not pb_valid.empty:
                    pb = pb_valid.iloc[-1]['pb']
            
            # PB fallback
            if pb is None or not (0.1 <= pb <= 20):
                pb = self._apply_pb_fallback(stock_code, date)
            
            price_percentile = self.get_price_percentile(stock_code, date)
            
            snapshot.append({
                'stock_code': stock_code,
                'stock_name': CODE_TO_NAME.get(stock_code, stock_code),
                'price': row['close'],
                'pb': pb,
                'price_percentile': price_percentile,
                'data_date': row['date']
            })
        
        return snapshot
    
    def get_price_percentile(self, stock_code: str, current_date: datetime, lookback_days: int = 250) -> Optional[float]:
        """获取当前价格在历史中的百分位"""
        if stock_code not in self._price_history:
            return None
        
        df = self._price_history[stock_code]
        current_date = pd.to_datetime(current_date)
        
        start_date = current_date - pd.Timedelta(days=lookback_days * 2)
        historical_prices = df[(df.index >= start_date) & (df.index <= current_date)]['close']
        
        if len(historical_prices) < 20:
            return None
        
        current_price = df[df.index == current_date]['close']
        if len(current_price) == 0:
            nearest_idx = df.index[df.index <= current_date]
            if len(nearest_idx) == 0:
                return None
            current_price = df.loc[nearest_idx[-1], 'close']
        else:
            current_price = current_price.iloc[0]
        
        percentile = (historical_prices < current_price).sum() / len(historical_prices)
        return percentile
    
    def get_price_at_date(self, price_data: Dict[str, pd.DataFrame], stock_code: str, date: datetime) -> Optional[float]:
        """获取指定日期的价格"""
        if stock_code not in price_data:
            return None
        df = price_data[stock_code]
        row = df[df['date'] == date]
        if not row.empty:
            return row.iloc[0]['close']
        
        valid_dates = df[df['date'] <= date]
        if not valid_dates.empty:
            return valid_dates.iloc[-1]['close']
        
        return None
    
    def get_pb_at_date(self, pb_data: Dict[str, pd.DataFrame], stock_code: str, date: datetime) -> Optional[float]:
        """获取指定日期的PB"""
        if stock_code not in pb_data:
            return self._apply_pb_fallback(stock_code, date)
        
        df = pb_data[stock_code]
        valid_dates = df[df['date'] <= date]
        if not valid_dates.empty:
            pb = valid_dates.iloc[-1]['pb']
            if 0.1 <= pb <= 20:
                return pb
        
        return self._apply_pb_fallback(stock_code, date)
