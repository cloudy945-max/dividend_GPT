import akshare as ak
import pandas as pd
import numpy as np
import os
from datetime import datetime


STOCK_CODE_MAP = {
    "招商银行": "600036",
    "兴业银行": "601166",
    "工商银行": "601398",
    "双汇发展": "000895"
}


class BacktestDataLoader:
    def __init__(self, data_dir='backtest_data'):
        self.data_dir = data_dir
        self.cache_dir = os.path.join(data_dir, 'cache')
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        self.cache = {}
        self._price_history = {}

    def _get_cache_path(self, stock_code, start_date, end_date):
        return os.path.join(self.cache_dir, f"{stock_code}_{start_date}_{end_date}.pkl")

    def _load_from_cache(self, stock_code, start_date, end_date):
        cache_path = self._get_cache_path(stock_code, start_date, end_date)
        if os.path.exists(cache_path):
            return pd.read_pickle(cache_path)
        return None

    def _save_to_cache(self, stock_code, start_date, end_date, df):
        cache_path = self._get_cache_path(stock_code, start_date, end_date)
        df.to_pickle(cache_path)

    def load_price_history(self, stock_list, start_date, end_date, force_refresh=False):
        result = {}
        raw_data = {}

        for stock_code in stock_list:
            df = self._load_from_cache(stock_code, start_date, end_date) if not force_refresh else None

            if df is None:
                if stock_code == "159307":
                    df = self._load_etf_historical(stock_code, start_date, end_date)
                else:
                    df = self._load_stock_historical(stock_code, start_date, end_date)

                if df is not None:
                    self._save_to_cache(stock_code, start_date, end_date, df)

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

    def _load_stock_historical(self, stock_code, start_date, end_date):
        try:
            symbol = STOCK_CODE_MAP.get(stock_code, stock_code)
            
            # 转换日期格式: YYYY-MM-DD -> YYYYMMDD
            start_date_fmt = start_date.replace('-', '')
            end_date_fmt = end_date.replace('-', '')
            
            df = ak.stock_zh_a_hist(symbol=symbol, start_date=start_date_fmt, end_date=end_date_fmt, adjust="qfq")
            if df is not None and not df.empty:
                df = df.rename(columns={
                    '日期': 'date',
                    '收盘': 'close'
                })
                df['date'] = pd.to_datetime(df['date'])
                return df[['date', 'close']]
        except Exception as e:
            print(f"加载股票历史数据失败 {stock_code}: {e}")
        return None

    def _load_etf_historical(self, stock_code, start_date, end_date):
        try:
            df = ak.fund_etf_hist_em(symbol=stock_code)
            if df is not None and not df.empty:
                df = df.rename(columns={
                    '日期': 'date',
                    '收盘': 'close'
                })
                df['date'] = pd.to_datetime(df['date'])
                df = df[['date', 'close']].copy()
                df = df[(df['date'] >= pd.to_datetime(start_date)) & (df['date'] <= pd.to_datetime(end_date))]
                return df
        except Exception as e:
            print(f"加载ETF历史数据失败 {stock_code}: {e}")
        return None

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

    def load_multiple_stocks(self, stock_codes, start_date, end_date, force_refresh=False):
        all_data = {}
        for code in stock_codes:
            df = self.load_historical_data(code, start_date, end_date, force_refresh)
            if df is not None:
                all_data[code] = df
        return all_data

    def get_snapshot_at_date(self, historical_data, date):
        snapshot = []
        for stock_code, df in historical_data.items():
            row = df[df['date'] == date]
            if not row.empty:
                row = row.iloc[0]
                snapshot.append({
                    'stock_code': stock_code,
                    'stock_name': self._get_stock_name(stock_code),
                    'price': row['close'],
                    'open': row.get('open', row['close']),
                    'high': row.get('high', row['close']),
                    'low': row.get('low', row['close']),
                    'volume': row.get('volume', 0),
                    'pct_change': row.get('pct_change', 0),
                    'turnover_rate': row.get('turnover_rate', 0)
                })
        return snapshot

    def _get_stock_name(self, stock_code):
        name_map = {
            "招商银行": "招商银行",
            "兴业银行": "兴业银行",
            "工商银行": "工商银行",
            "双汇发展": "双汇发展",
            "159307": "红利低波100ETF"
        }
        return name_map.get(stock_code, stock_code)

    def get_price_at_date(self, historical_data, stock_code, date):
        if stock_code not in historical_data:
            return None
        df = historical_data[stock_code]
        row = df[df['date'] == date]
        if not row.empty:
            return row.iloc[0]['close']
        return None
