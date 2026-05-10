import akshare as ak
import pandas as pd
import numpy as np
import os
import pickle
import logging
from datetime import datetime, timedelta
from functools import lru_cache

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('backtest_data/data_loader.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

STOCK_CODE_MAP = {
    "招商银行": "600036",
    "兴业银行": "601166",
    "工商银行": "601398",
    "双汇发展": "000895"
}

STOCK_CODE_MAPPING = {
    "招商银行": "sh600036",
    "兴业银行": "sh601166",
    "工商银行": "sh601398",
    "双汇发展": "sz000895"
}

CODE_TO_NAME = {
    "招商银行": "招商银行",
    "兴业银行": "兴业银行",
    "工商银行": "工商银行",
    "双汇发展": "双汇发展",
    "159307": "红利低波100ETF"
}


def retry_on_failure(max_retries=3, delay=2):
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


class BacktestDataLoader:
    def __init__(self, data_dir='backtest_data'):
        self.data_dir = data_dir
        self.cache_dir = os.path.join(data_dir, 'cache')
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        self._price_history = {}
        self._pb_history = {}

    def _get_cache_path(self, stock_code, start_date, end_date, data_type='price'):
        filename = f"{stock_code}_{start_date}_{end_date}_{data_type}.pkl"
        return os.path.join(self.cache_dir, filename)

    def _load_from_cache(self, stock_code, start_date, end_date, data_type='price'):
        cache_path = self._get_cache_path(stock_code, start_date, end_date, data_type)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'rb') as f:
                    data = pickle.load(f)
                logger.debug(f"从缓存加载 {data_type} 数据: {stock_code} {start_date} - {end_date}")
                return data
            except Exception as e:
                logger.warning(f"缓存文件损坏，重新获取: {e}")
                os.remove(cache_path)
        return None

    def _save_to_cache(self, stock_code, start_date, end_date, data, data_type='price'):
        cache_path = self._get_cache_path(stock_code, start_date, end_date, data_type)
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(data, f)
            logger.debug(f"保存 {data_type} 数据到缓存: {stock_code} {start_date} - {end_date}")
        except Exception as e:
            logger.warning(f"保存缓存失败: {e}")

    @retry_on_failure(max_retries=3, delay=2)
    def _load_stock_daily(self, symbol, start_date, end_date):
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
    def _load_etf_daily(self, symbol, start_date, end_date):
        df = ak.fund_etf_hist_em(symbol=symbol)
        if df is None or df.empty:
            raise ValueError("获取ETF数据为空")
        df = df[(df['日期'] >= start_date) & (df['日期'] <= end_date)]
        return df

    def _load_stock_fundamental(self, stock_code):
        try:
            ak_code = STOCK_CODE_MAPPING.get(stock_code, stock_code)
            if ak_code.startswith('sh'):
                ak_code = ak_code[2:]
            elif ak_code.startswith('sz'):
                ak_code = ak_code[2:]

            df = ak.stock_financial_report_sina(symbol=ak_code)
            if df is not None and not df.empty:
                df['date'] = pd.to_datetime(df['报告日期'])
                df = df.sort_values('date')
                return df
        except Exception as e:
            logger.warning(f"获取基本面数据失败 {stock_code}: {e}")
        
        try:
            df = ak.stock_zh_a_lg(symbol=ak_code)
            if df is not None and not df.empty:
                return df
        except Exception as e:
            logger.warning(f"备选接口获取基本面数据失败 {stock_code}: {e}")
        
        return None

    def load_price_history(self, stock_list, start_date, end_date, force_refresh=False):
        result = {}
        raw_data = {}

        for stock_code in stock_list:
            cached = self._load_from_cache(stock_code, start_date, end_date, 'price') if not force_refresh else None
            
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

        return result

    def _fetch_price_data(self, stock_code, start_date, end_date):
        try:
            if stock_code == "159307":
                df = self._load_etf_daily(stock_code, start_date, end_date)
                df = df.rename(columns={'日期': 'date', '收盘': 'close'})
            else:
                symbol = STOCK_CODE_MAP.get(stock_code, stock_code)
                df = self._load_stock_daily(symbol, start_date, end_date)
                df = df.rename(columns={'日期': 'date', '收盘': 'close'})
            
            df['date'] = pd.to_datetime(df['date'])
            return df[['date', 'close']]
        except Exception as e:
            logger.error(f"加载 {stock_code} 价格数据失败: {e}")
            return None

    def load_pb_history(self, stock_list, start_date, end_date, force_refresh=False):
        result = {}
        
        for stock_code in stock_list:
            if stock_code == "159307":
                result[stock_code] = pd.DataFrame({'date': [], 'pb': []})
                continue
            
            cached = self._load_from_cache(stock_code, start_date, end_date, 'pb') if not force_refresh else None
            
            if cached is not None:
                pb_df = cached
            else:
                pb_df = self._fetch_pb_data(stock_code, start_date, end_date)
                if pb_df is not None:
                    self._save_to_cache(stock_code, start_date, end_date, pb_df, 'pb')

            if pb_df is not None and not pb_df.empty:
                self._pb_history[stock_code] = pb_df
                result[stock_code] = pb_df
        
        return result

    def _fetch_pb_data(self, stock_code, start_date, end_date):
        try:
            df = self._fetch_pb_from_daily(stock_code, start_date, end_date)
            if df is not None and not df.empty:
                return df
        except Exception as e:
            logger.debug(f"从日线数据获取PB失败 {stock_code}: {e}")

        try:
            ak_code = STOCK_CODE_MAPPING.get(stock_code, stock_code)
            if ak_code.startswith('sh'):
                ak_code = ak_code[2:]
            elif ak_code.startswith('sz'):
                ak_code = ak_code[2:]

            pb_methods = [
                lambda: ak.stock_a_lg_indicator(symbol=ak_code, start_date=start_date, end_date=end_date),
                lambda: ak.stock_financial_report_sina(symbol=ak_code),
            ]
            
            for method in pb_methods:
                try:
                    df = method()
                    if df is not None and not df.empty:
                        if '市净率' in df.columns:
                            df = df.rename(columns={'日期': 'date', '市净率': 'pb'})
                        elif '市净率(倍)' in df.columns:
                            df = df.rename(columns={'日期': 'date', '市净率(倍)': 'pb'})
                        elif 'pb' in df.columns.lower():
                            for col in df.columns:
                                if 'pb' in col.lower() or '市净' in col:
                                    df = df.rename(columns={col: 'pb'})
                                    break
                        
                        if 'pb' in df.columns:
                            if '日期' in df.columns:
                                df = df.rename(columns={'日期': 'date'})
                            df['date'] = pd.to_datetime(df['date'])
                            df = df[['date', 'pb']].sort_values('date').drop_duplicates(subset='date')
                            return df
                except Exception as method_e:
                    logger.debug(f"尝试PB接口失败: {method_e}")
                    
        except Exception as e:
            logger.debug(f"获取PB数据失败 {stock_code}: {e}")

        return None

    def _fetch_pb_from_daily(self, stock_code, start_date, end_date):
        try:
            ak_code = STOCK_CODE_MAPPING.get(stock_code, stock_code)
            df = ak.stock_zh_a_hist(
                symbol=ak_code.replace('sh', '').replace('sz', ''),
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq"
            )
            
            if df is not None and not df.empty and '市净率' in df.columns:
                df = df.rename(columns={'日期': 'date', '市净率': 'pb'})
                df['date'] = pd.to_datetime(df['date'])
                return df[['date', 'pb']].sort_values('date').drop_duplicates(subset='date')
        except Exception as e:
            logger.debug(f"尝试从日线获取PB失败: {e}")
        
        return None

    def get_price_percentile(self, stock_code, current_date, lookback_days=250):
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

    def _get_common_trading_dates(self, raw_data, start_date, end_date):
        all_dates = []
        for df in raw_data.values():
            all_dates.extend(df.index.tolist())

        date_counts = pd.Series(all_dates).value_counts()
        common_dates = date_counts[date_counts == len(raw_data)].index
        common_dates = pd.to_datetime(common_dates)
        common_dates = common_dates[(common_dates >= pd.to_datetime(start_date)) &
                                   (common_dates <= pd.to_datetime(end_date))]
        return sorted(common_dates)

    def _align_and_fill(self, df, trading_dates):
        aligned = pd.DataFrame(index=trading_dates)
        aligned.index.name = 'date'

        df_aligned = aligned.join(df, how='left')
        df_aligned['close'] = df_aligned['close'].ffill()
        df_aligned['close'] = df_aligned['close'].bfill()

        df_aligned = df_aligned.reset_index()
        return df_aligned

    def get_monthly_snapshots(self, stock_list, start_date, end_date):
        price_data = self.load_price_history(stock_list, start_date, end_date)
        pb_data = self.load_pb_history(stock_list, start_date, end_date)

        if not price_data:
            return []

        all_dates = set()
        for df in price_data.values():
            all_dates.update(df['date'].tolist())
        
        monthly_dates = self._get_month_end_dates(sorted(all_dates), start_date, end_date)

        snapshots = []
        for date in monthly_dates:
            snapshot = self._build_snapshot(date, price_data, pb_data)
            if snapshot:
                snapshots.append({
                    'date': date,
                    'snapshot': snapshot
                })

        return snapshots

    def _get_month_end_dates(self, all_dates, start_date, end_date):
        dates = pd.to_datetime(all_dates)
        dates = dates[(dates >= pd.to_datetime(start_date)) & (dates <= pd.to_datetime(end_date))]
        
        monthly_groups = dates.groupby([dates.year, dates.month])
        month_end_dates = []
        for (year, month), group in monthly_groups:
            month_end_dates.append(group.max())
        
        return sorted(month_end_dates)

    def _build_snapshot(self, date, price_data, pb_data):
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

            pb = None
            pb_df = pb_data.get(stock_code)
            if pb_df is not None and not pb_df.empty:
                pb_row = pb_df[pb_df['date'] <= date]
                if not pb_row.empty:
                    pb_row = pb_row.iloc[-1:]
                    pb = pb_row['pb'].iloc[0]

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

    def get_snapshot_at_date(self, date, price_data=None, pb_data=None):
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

    def load_historical_data(self, stock_code, start_date, end_date, force_refresh=False):
        cache_file = os.path.join(self.data_dir, f"{stock_code}_{start_date}_{end_date}.csv")

        if not force_refresh and os.path.exists(cache_file):
            return pd.read_csv(cache_file, parse_dates=['date'])

        if stock_code == "159307":
            df = self._load_etf_historical(stock_code, start_date, end_date)
        else:
            df = self._load_stock_historical(stock_code, start_date, end_date)

        if df is not None and not df.empty:
            df.to_csv(cache_file, index=False)
        return df

    def _load_stock_historical(self, stock_code, start_date, end_date):
        try:
            symbol = STOCK_CODE_MAP.get(stock_code, stock_code)
            df = self._load_stock_daily(symbol, start_date, end_date)
            if df is not None and not df.empty:
                df = df.rename(columns={'日期': 'date', '收盘': 'close', '开盘': 'open', 
                                       '最高': 'high', '最低': 'low', '成交量': 'volume',
                                       '涨跌幅': 'pct_change', '换手率': 'turnover_rate'})
                df['date'] = pd.to_datetime(df['date'])
                return df
        except Exception as e:
            logger.error(f"加载股票历史数据失败 {stock_code}: {e}")
        return None

    def _load_etf_historical(self, stock_code, start_date, end_date):
        try:
            df = self._load_etf_daily(stock_code, start_date, end_date)
            if df is not None and not df.empty:
                df = df.rename(columns={'日期': 'date', '收盘': 'close', '开盘': 'open',
                                       '最高': 'high', '最低': 'low', '成交量': 'volume',
                                       '涨跌幅': 'pct_change'})
                df['date'] = pd.to_datetime(df['date'])
                return df[['date', 'close', 'open', 'high', 'low', 'volume', 'pct_change']]
        except Exception as e:
            logger.error(f"加载ETF历史数据失败 {stock_code}: {e}")
        return None

    def load_multiple_stocks(self, stock_codes, start_date, end_date, force_refresh=False):
        all_data = {}
        for code in stock_codes:
            df = self.load_historical_data(code, start_date, end_date, force_refresh)
            if df is not None:
                all_data[code] = df
        return all_data

    def get_price_at_date(self, price_data, stock_code, date):
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

    def get_pb_at_date(self, pb_data, stock_code, date):
        if stock_code not in pb_data:
            return None
        df = pb_data[stock_code]
        valid_dates = df[df['date'] <= date]
        if not valid_dates.empty:
            return valid_dates.iloc[-1]['pb']
        return None