#!/usr/bin/env python3

import sys
from datetime import datetime
import numpy as np
import pandas as pd
import scipy.stats as si
import yfinance as yf

# Set pandas options for clean terminal display
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)

def calculate_greeks(row, spot, r=0.045, is_call=True):
    """
    Calculates Black-Scholes Greeks for a single option row.
    r: Risk-free rate (assumed at 4.5% annual rate)
    """
    K = row['strike']
    sigma = row['impliedVolatility']
    T = row['timeToExpiration']
    
    # Safeguard against zero/invalid values
    if sigma <= 0 or pd.isna(sigma) or T <= 0:
        return pd.Series([np.nan]*5, index=['Delta', 'Gamma', 'Theta', 'Vega', 'Rho'])

    # Black-Scholes d1 and d2
    d1 = (np.log(spot / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)

    pdf_d1 = si.norm.pdf(d1)
    
    # 1. Delta
    delta = si.norm.cdf(d1) if is_call else si.norm.cdf(d1) - 1.0

    # 2. Gamma
    gamma = pdf_d1 / (spot * sigma * np.sqrt(T))

    # 3. Theta (daily decay)
    if is_call:
        theta = (- (spot * pdf_d1 * sigma) / (2 * np.sqrt(T)) - r * K * np.exp(-r * T) * si.norm.cdf(d2)) / 365.0
    else:
        theta = (- (spot * pdf_d1 * sigma) / (2 * np.sqrt(T)) + r * K * np.exp(-r * T) * si.norm.cdf(-d2)) / 365.0

    # 4. Vega (1% IV change)
    vega = (spot * pdf_d1 * np.sqrt(T)) / 100.0

    # 5. Rho (1% interest rate change)
    rho = (K * T * np.exp(-r * T) * si.norm.cdf(d2)) / 100.0 if is_call else (-K * T * np.exp(-r * T) * si.norm.cdf(-d2)) / 100.0

    return pd.Series([round(delta, 4), round(gamma, 4), round(theta, 4), round(vega, 4), round(rho, 4)],
                     index=['Delta', 'Gamma', 'Theta', 'Vega', 'Rho'])


def fetch_option_chain_with_greeks(symbol: str, expiration_index: int = 0):
    symbol = symbol.upper()
    ticker = yf.Ticker(symbol)

    # Fetch current underlying price
    history = ticker.history(period="1d")
    if history.empty:
        print(f"❌ Could not fetch market price for '{symbol}'.")
        return None, None

    spot_price = history['Close'].iloc[-1]
    expirations = ticker.options

    if not expirations:
        print(f"❌ No options data available for '{symbol}'.")
        return None, None

    selected_date = expirations[expiration_index]
    print(f"🎯 Symbol: {symbol} | Current Price: ${spot_price:.2f}")
    print(f"📅 Expiration Date: {selected_date}\n")

    # Time to expiration in years
    exp_date = datetime.strptime(selected_date, "%Y-%m-%d")
    days_to_exp = max((exp_date - datetime.now()).days, 1)
    T = days_to_exp / 365.0

    option_chain = ticker.option_chain(selected_date)
    cols = ['contractSymbol', 'strike', 'lastPrice', 'impliedVolatility']

    calls = option_chain.calls[cols].copy()
    puts = option_chain.puts[cols].copy()

    calls['timeToExpiration'] = T
    puts['timeToExpiration'] = T

    # Calculate Greeks
    call_greeks = calls.apply(calculate_greeks, axis=1, spot=spot_price, is_call=True)
    put_greeks = puts.apply(calculate_greeks, axis=1, spot=spot_price, is_call=False)

    calls = pd.concat([calls.drop(columns=['timeToExpiration']), call_greeks], axis=1)
    puts = pd.concat([puts.drop(columns=['timeToExpiration']), put_greeks], axis=1)

    return calls, puts


if __name__ == "__main__":
    ticker_symbol = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    calls_df, puts_df = fetch_option_chain_with_greeks(ticker_symbol, expiration_index=1)

    if calls_df is not None and puts_df is not None:
        print("=== CALL OPTIONS WITH GREEKS ===")
        print(calls_df.head(5))

        print("\n=== PUT OPTIONS WITH GREEKS ===")
        print(puts_df.head(5))
