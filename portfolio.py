import pandas as pd
from datetime import datetime
import os

class PortfolioManager:
    def __init__(self, data_dir='data'):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        
        self.holdings_path = os.path.join(data_dir, 'holdings.csv')
        self.transactions_path = os.path.join(data_dir, 'transactions.csv')
        self.dividends_path = os.path.join(data_dir, 'dividends.csv')
        
        self.load_data()
    
    def load_data(self):
        if os.path.exists(self.holdings_path):
            self.holdings = pd.read_csv(self.holdings_path, encoding='utf-8-sig')
            if 'total_cost' not in self.holdings.columns:
                self.holdings['total_cost'] = self.holdings['shares'] * self.holdings['cost_price']
        else:
            self.holdings = pd.DataFrame(columns=['stock_name', 'shares', 'cost_price', 'total_cost'])
        
        if os.path.exists(self.transactions_path):
            self.transactions = pd.read_csv(self.transactions_path, encoding='utf-8-sig')
            if 'cash_flow' not in self.transactions.columns:
                self.transactions['cash_flow'] = 0.0
            if 'source' not in self.transactions.columns:
                self.transactions['source'] = 'new_cash'
            if 'dividend_amount' not in self.transactions.columns:
                self.transactions['dividend_amount'] = 0.0
            if 'dividend_stock' not in self.transactions.columns:
                self.transactions['dividend_stock'] = ''
            if not self.transactions.empty:
                self.transactions['date'] = pd.to_datetime(self.transactions['date'])
        else:
            self.transactions = pd.DataFrame(columns=['date', 'type', 'stock_name', 'price', 'shares', 'cash_flow', 'source', 'dividend_amount', 'dividend_stock'])
        
        if os.path.exists(self.dividends_path):
            self.dividends = pd.read_csv(self.dividends_path, encoding='utf-8-sig')
            if not self.dividends.empty:
                self.dividends['date'] = pd.to_datetime(self.dividends['date'])
        else:
            self.dividends = pd.DataFrame(columns=['date', 'stock_name', 'dividend_per_share'])
        
        self.dividend_pool = 0.0
        self._calculate_dividend_pool()
    
    def _calculate_dividend_pool(self):
        if self.dividends.empty or self.holdings.empty:
            self.dividend_pool = 0.0
            return
        
        holdings_shares = {}
        for _, row in self.holdings.iterrows():
            holdings_shares[row['stock_name']] = row['shares']
        
        total_dividend = 0.0
        for _, row in self.dividends.iterrows():
            stock_name = row['stock_name']
            if stock_name in holdings_shares:
                total_dividend += row['dividend_per_share'] * holdings_shares[stock_name]
        
        reinvested = self.transactions[self.transactions['type'] == 'dividend_reinvest']['dividend_amount'].sum()
        
        self.dividend_pool = total_dividend - reinvested
    
    def get_dividend_pool(self):
        return self.dividend_pool
    
    def get_dividend_pool_breakdown(self):
        if self.dividends.empty or self.holdings.empty:
            return {'total': 0.0, 'reinvested': 0.0, 'available': 0.0, 'by_stock': {}}
        
        holdings_shares = {}
        for _, row in self.holdings.iterrows():
            holdings_shares[row['stock_name']] = row['shares']
        
        by_stock = {}
        for _, row in self.dividends.iterrows():
            stock_name = row['stock_name']
            if stock_name in holdings_shares:
                amount = row['dividend_per_share'] * holdings_shares[stock_name]
                by_stock[stock_name] = by_stock.get(stock_name, 0.0) + amount
        
        total = sum(by_stock.values())
        reinvested = self.transactions[self.transactions['type'] == 'dividend_reinvest']['dividend_amount'].sum()
        
        return {
            'total': total,
            'reinvested': reinvested,
            'available': total - reinvested,
            'by_stock': by_stock
        }
    
    def save_data(self):
        self.holdings.to_csv(self.holdings_path, index=False, encoding='utf-8-sig')
        self.transactions.to_csv(self.transactions_path, index=False, encoding='utf-8-sig')
        self.dividends.to_csv(self.dividends_path, index=False, encoding='utf-8-sig')
    
    def add_transaction(self, date, type_, stock_name, price, shares, source='new_cash', dividend_amount=0.0, dividend_stock=''):
        date = pd.to_datetime(date)
        if type_ == 'buy':
            cash_flow = - price * shares
        elif type_ == 'sell':
            cash_flow = price * shares
        elif type_ == 'dividend_reinvest':
            cash_flow = - price * shares
        else:
            cash_flow = 0.0
        new_transaction = pd.DataFrame({
            'date': [date],
            'type': [type_],
            'stock_name': [stock_name],
            'price': [price],
            'shares': [shares],
            'cash_flow': [cash_flow],
            'source': [source],
            'dividend_amount': [dividend_amount],
            'dividend_stock': [dividend_stock]
        })
        self.transactions = pd.concat([self.transactions, new_transaction], ignore_index=True)
        
        if type_ == 'buy':
            self._update_holdings_buy(stock_name, shares, price)
        elif type_ == 'sell':
            self._update_holdings_sell(stock_name, shares)
        elif type_ == 'dividend_reinvest':
            self.dividend_pool -= dividend_amount
            self._update_holdings_buy(stock_name, shares, price)
        
        self.save_data()
    
    def _update_holdings_buy(self, stock_name, shares, price):
        if stock_name in self.holdings['stock_name'].values:
            idx = self.holdings[self.holdings['stock_name'] == stock_name].index[0]
            old_shares = self.holdings.at[idx, 'shares']
            old_cost = self.holdings.at[idx, 'cost_price']
            new_shares = old_shares + shares
            new_cost = ((old_shares * old_cost) + (shares * price)) / new_shares
            self.holdings.at[idx, 'shares'] = new_shares
            self.holdings.at[idx, 'cost_price'] = new_cost
            self.holdings.at[idx, 'total_cost'] = new_shares * new_cost
        else:
            new_holding = pd.DataFrame({
                'stock_name': [stock_name],
                'shares': [shares],
                'cost_price': [price],
                'total_cost': [shares * price]
            })
            self.holdings = pd.concat([self.holdings, new_holding], ignore_index=True)
    
    def _update_holdings_sell(self, stock_name, shares):
        if stock_name in self.holdings['stock_name'].values:
            idx = self.holdings[self.holdings['stock_name'] == stock_name].index[0]
            old_shares = self.holdings.at[idx, 'shares']
            if shares > old_shares:
                raise ValueError("卖出股数超过持仓")
            new_shares = old_shares - shares
            if new_shares <= 0:
                self.holdings = self.holdings.drop(idx).reset_index(drop=True)
            else:
                self.holdings.at[idx, 'shares'] = new_shares
                old_total_cost = self.holdings.at[idx, 'total_cost']
                self.holdings.at[idx, 'total_cost'] = old_total_cost * (new_shares / old_shares)
    
    def add_dividend(self, date, stock_name, dividend_per_share):
        date = pd.to_datetime(date)
        new_dividend = pd.DataFrame({
            'date': [date],
            'stock_name': [stock_name],
            'dividend_per_share': [dividend_per_share]
        })
        self.dividends = pd.concat([self.dividends, new_dividend], ignore_index=True)
        self._calculate_dividend_pool()
        self.save_data()
    
    def get_holdings(self):
        return self.holdings
    
    def get_transactions(self):
        return self.transactions

    def get_transactions_sorted(self):
        if self.transactions.empty:
            return self.transactions.copy()
        return self.transactions.sort_values('date').copy()
    
    def get_dividends(self):
        return self.dividends

def initialize_sample_data():
    portfolio = PortfolioManager()
    
    portfolio.add_transaction('2024-01-15', 'buy', '贵州茅台', 1800, 100)
    portfolio.add_transaction('2024-02-20', 'buy', '招商银行', 35, 500)
    portfolio.add_transaction('2024-03-10', 'buy', '贵州茅台', 1750, 50)
    portfolio.add_transaction('2024-04-05', 'sell', '招商银行', 38, 200)
    
    portfolio.add_dividend('2024-06-15', '贵州茅台', 25)
    portfolio.add_dividend('2024-07-20', '招商银行', 1.5)
    
    return portfolio

if __name__ == '__main__':
    print('初始化示例数据...')
    portfolio = initialize_sample_data()
    
    print('\n当前持仓:')
    print(portfolio.get_holdings())
    
    print('\n交易记录:')
    print(portfolio.get_transactions())
    
    print('\n分红记录:')
    print(portfolio.get_dividends())
