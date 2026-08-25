"""
Put Option Bid Premium Plot — configurable stock & strike, all expirations over next N months
-----------------------------------------------------------------------------
Requires: yfinance, pandas, matplotlib
    pip install yfinance pandas matplotlib

Run:
    python qqq_580_put_bid_plot.py --ticker QQQ --strike 580
    python qqq_580_put_bid_plot.py -t AAPL -s 200 --months 6
    python qqq_580_put_bid_plot.py -t QQQ -s 580 --price-type ask
    python qqq_580_put_bid_plot.py -t QQQ -s 580 --no-fallback
    python qqq_580_put_bid_plot.py -t QQQ --pct-of-price 55
    python qqq_580_put_bid_plot.py -t QQQ --pct-of-price 50-60

Options:
    -t, --ticker      Stock/ETF ticker symbol (default: QQQ)
    -s, --strike      Put option strike price (default: 580). Ignored if
                       --pct-of-price is given.
    --pct-of-price    Pick the strike as a percentage of the CURRENT stock
                       price instead of a fixed dollar strike. Accepts a
                       single number ("55" -> 55% of current price) or a
                       range ("50-60" -> uses the midpoint, 55%). The
                       nearest actually-listed strike to that target is used.
                       Overrides -s/--strike when provided.
    -m, --months      How many months ahead to include (default: 12)
    -p, --price-type  Which quote to plot: "bid" or "ask" (default: bid)
    --no-fallback     Disable the lastPrice fallback (see below), showing
                       raw 0 values instead.

What it does:
    1. Pulls the live list of option expiration dates for the given ticker
       from Yahoo Finance.
    2. Keeps expirations from today through the requested number of months
       ahead.
    3. If --pct-of-price was given: fetches the current stock price, computes
       the target dollar strike as pct% of that price, and finds the
       nearest strike actually listed on the option chain (using the
       nearest-term expiration's strike list) — that becomes the strike used
       for every expiration below.
    4. For each expiration, pulls the put chain and grabs the row where
       strike == the requested/derived strike (falls back to nearest strike
       per-expiration if that exact strike isn't listed there, and tells you
       when it does — strike spacing can occasionally differ by expiration).
    5. Prints a table with bid, ask, lastPrice, volume, and open interest for
       every expiration, so you can see exactly what data Yahoo returned.
    6. Plots the selected Bid or Ask ($) on the Y-axis vs Expiration Date on
       the X-axis. Yahoo's free feed frequently reports bid=0 / ask=0 for
       thinly-traded or far out-of-the-money contracts. When that happens,
       the script substitutes lastPrice instead (marked with an orange
       triangle on the chart and a "used_fallback" column in the CSV) so you
       don't just get a flat zero line. Use --no-fallback to see raw zeros.
    7. Saves the chart as {ticker}_{strike}_put_{price_type}s.png and the
       data as {ticker}_{strike}_put_{price_type}s.csv.

Notes:
    - Bid/ask prices reflect current/live market data at the time you run
      the script — they will differ every time you run it, especially for
      short-dated or illiquid contracts.
    - A strike far from the current stock price, or short-dated contracts on
      a slow trading day, are the most likely to show bid=0/ask=0 — that's a
      market-liquidity/data-feed characteristic, not a bug.
    - Not all expirations will have a listed strike matching exactly what you
      requested (weeklies sometimes have different strike spacing). The
      script flags any expiration where it had to use the nearest available
      strike instead.
    - This is data retrieval / visualization only — not investment advice.
"""

import argparse
import sys
from datetime import datetime, timedelta

import pandas as pd
import matplotlib.pyplot as plt

try:
    import yfinance as yf
except ImportError:
    sys.exit("Missing dependency. Install with:  pip install yfinance pandas matplotlib")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Plot put option bid premiums across expirations for a given ticker and strike."
    )
    parser.add_argument("-t", "--ticker", type=str, default="QQQ",
                         help="Stock/ETF ticker symbol (default: QQQ)")
    parser.add_argument("-s", "--strike", type=float, default=580.0,
                         help="Put option strike price (default: 580). Ignored if --pct-of-price is given.")
    parser.add_argument("--pct-of-price", type=str, default=None,
                         help='Pick the strike as a %% of the current stock price instead of a fixed '
                              'dollar amount. Accepts a single number ("55") or a range ("50-60", '
                              'midpoint used). Overrides -s/--strike.')
    parser.add_argument("-m", "--months", type=int, default=12,
                         help="Months ahead to include (default: 12)")
    parser.add_argument("-p", "--price-type", type=str, default="bid",
                         choices=["bid", "ask"],
                         help='Which quote to plot: "bid" or "ask" (default: bid)')
    parser.add_argument("--no-fallback", action="store_true",
                         help="Disable fallback to lastPrice when bid and ask are both 0 "
                              "(shows raw zeros instead).")
    return parser.parse_args()


def get_expirations_within_range(ticker_obj, months_ahead=12):
    today = datetime.today().date()
    cutoff = today + timedelta(days=months_ahead * 30)  # approx 1 year
    all_exps = ticker_obj.options  # tuple of date strings 'YYYY-MM-DD'
    kept = [e for e in all_exps if today <= datetime.strptime(e, "%Y-%m-%d").date() <= cutoff]
    return kept


def get_put_row_at_strike(ticker_obj, expiration, target_strike):
    chain = ticker_obj.option_chain(expiration)
    puts = chain.puts
    if puts.empty:
        return None

    exact = puts[puts["strike"] == target_strike]
    if not exact.empty:
        return exact.iloc[0]

    # fallback: nearest available strike
    puts = puts.copy()
    puts["diff"] = (puts["strike"] - target_strike).abs()
    return puts.sort_values("diff").iloc[0]


def parse_pct_of_price(pct_str):
    """
    Parse the --pct-of-price argument. Accepts a single number ("55") or a
    range ("50-60"), returning (low_pct, high_pct, target_pct) as floats.
    For a single value, low == high == target. For a range, target is the
    midpoint.
    """
    pct_str = pct_str.strip().replace("%", "")
    if "-" in pct_str:
        parts = pct_str.split("-")
        if len(parts) != 2:
            sys.exit(f"Could not parse --pct-of-price '{pct_str}'. Use a number like '55' "
                      f"or a range like '50-60'.")
        try:
            low_pct, high_pct = float(parts[0]), float(parts[1])
        except ValueError:
            sys.exit(f"Could not parse --pct-of-price '{pct_str}' as numbers.")
        target_pct = (low_pct + high_pct) / 2
    else:
        try:
            low_pct = high_pct = target_pct = float(pct_str)
        except ValueError:
            sys.exit(f"Could not parse --pct-of-price '{pct_str}' as a number.")
    return low_pct, high_pct, target_pct


def get_current_price(ticker_obj):
    """
    Fetch the current/last stock price, trying a few yfinance data sources
    in order of preference since availability varies by ticker and by
    yfinance version.
    """
    # Preferred: fast_info, cheap and usually reliable
    try:
        price = ticker_obj.fast_info.get("last_price")
        if price:
            return float(price)
    except Exception:
        pass

    # Fallback: legacy .info dict
    try:
        price = ticker_obj.info.get("regularMarketPrice") or ticker_obj.info.get("currentPrice")
        if price:
            return float(price)
    except Exception:
        pass

    # Last resort: most recent close from daily history
    try:
        hist = ticker_obj.history(period="5d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass

    sys.exit("Could not fetch the current stock price from Yahoo Finance (all methods failed). "
              "Check the ticker symbol or try again shortly.")


def find_nearest_listed_strike(ticker_obj, expiration, target_price):
    """
    Look up the put chain for a single expiration and return the strike
    closest to target_price. Used to snap a %-of-price target onto an
    actually-listed strike before pulling the full year of expirations.
    """
    chain = ticker_obj.option_chain(expiration)
    puts = chain.puts
    if puts.empty:
        return None
    diffs = (puts["strike"] - target_price).abs()
    return float(puts.loc[diffs.idxmin(), "strike"])


def main():
    args = parse_args()
    ticker = args.ticker.upper()
    target_strike = args.strike
    months_ahead = args.months
    price_type = args.price_type  # "bid" or "ask"
    price_label = price_type.capitalize()

    print(f"Fetching {ticker} option expirations...")
    tk = yf.Ticker(ticker)
    expirations = get_expirations_within_range(tk, months_ahead)

    if not expirations:
        sys.exit(f"No expirations found in the next {months_ahead} months. "
                  f"Check the ticker symbol, or Yahoo may be rate-limiting — try again shortly.")

    if args.pct_of_price:
        low_pct, high_pct, target_pct = parse_pct_of_price(args.pct_of_price)
        current_price = get_current_price(tk)
        target_price = current_price * target_pct / 100

        nearest_strike = find_nearest_listed_strike(tk, expirations[0], target_price)
        if nearest_strike is None:
            sys.exit(f"Could not find any listed put strikes for expiration {expirations[0]} "
                      f"to snap the %-of-price target onto.")

        if low_pct == high_pct:
            print(f"Current {ticker} price: ${current_price:.2f}  |  "
                  f"{target_pct:g}% of price = ${target_price:.2f}  |  "
                  f"nearest listed strike = {nearest_strike:g}")
        else:
            price_low = current_price * low_pct / 100
            price_high = current_price * high_pct / 100
            print(f"Current {ticker} price: ${current_price:.2f}  |  "
                  f"{low_pct:g}%-{high_pct:g}% of price = ${price_low:.2f}-${price_high:.2f} "
                  f"(midpoint target ${target_price:.2f})  |  "
                  f"nearest listed strike = {nearest_strike:g}")

        target_strike = nearest_strike

    print(f"Found {len(expirations)} expirations. Pulling {target_strike} put {price_type} for each...\n")
    print(f"{'Expiration':<12} {'Strike':>8} {'Bid':>8} {'Ask':>8} {'Last':>8} {'Vol':>8} {'OI':>8}")

    records = []
    zero_quote_count = 0
    for exp in expirations:
        try:
            row = get_put_row_at_strike(tk, exp, target_strike)
        except Exception as e:
            print(f"  {exp}: failed to fetch ({e})")
            continue

        if row is None:
            print(f"  {exp}: no put data available")
            continue

        used_strike = row["strike"]

        def safe_num(val):
            return 0.0 if pd.isna(val) else float(val)

        bid = safe_num(row.get("bid"))
        ask = safe_num(row.get("ask"))
        last = safe_num(row.get("lastPrice"))
        vol = safe_num(row.get("volume"))
        oi = safe_num(row.get("openInterest"))

        price = safe_num(row.get(price_type))
        used_fallback = False
        # yfinance often reports 0 bid/ask on thinly traded contracts.
        # Fall back to lastPrice so the chart isn't just a flat zero line.
        if (bid == 0 and ask == 0) and last > 0 and not args.no_fallback:
            price = last
            used_fallback = True

        strike_flag = "" if used_strike == target_strike else f" [nearest strike: {used_strike}]"
        fallback_flag = " [used lastPrice, bid/ask were 0]" if used_fallback else ""
        print(f"  {str(exp):<10} {used_strike:>8} {bid:>8.2f} {ask:>8.2f} {last:>8.2f} {int(vol):>8} {int(oi):>8}"
              f"{strike_flag}{fallback_flag}")

        if bid == 0 and ask == 0:
            zero_quote_count += 1

        records.append({"expiration": exp, price_type: price, "strike_used": used_strike,
                         "used_fallback": used_fallback})

    if not records:
        sys.exit("No data collected — nothing to plot.")

    if zero_quote_count:
        print(f"\nNote: {zero_quote_count} of {len(records)} expirations had bid=0 and ask=0 "
              f"from Yahoo's feed (typical for this far-OTM / low-volume strike, or when markets "
              f"are closed). Where possible, those points were plotted using lastPrice instead — "
              f"see the 'used_fallback' column in the CSV. Run --no-fallback to disable this and "
              f"see raw zeros.")

    df = pd.DataFrame(records)
    df["expiration"] = pd.to_datetime(df["expiration"])
    df = df.sort_values("expiration")

    # Plot
    plt.figure(figsize=(12, 6))
    plt.plot(df["expiration"], df[price_type], linewidth=1.5, color="tab:blue", zorder=1)

    real_pts = df[~df["used_fallback"]]
    fallback_pts = df[df["used_fallback"]]
    plt.scatter(real_pts["expiration"], real_pts[price_type], color="tab:blue",
                label=price_label, zorder=2)
    if not fallback_pts.empty:
        plt.scatter(fallback_pts["expiration"], fallback_pts[price_type], color="tab:orange",
                    marker="^", label="lastPrice (bid/ask were 0)", zorder=3)
        plt.legend()

    plt.title(f"{ticker} {target_strike:g} Strike Put — {price_label} Premium by Expiration")
    plt.xlabel("Expiration Date")
    plt.ylabel(f"Put {price_label} Premium ($)")
    plt.xticks(rotation=45, ha="right")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()

    strike_label = f"{target_strike:g}"
    out_png = f"{ticker}_{strike_label}_put_{price_type}s.png"
    plt.savefig(out_png, dpi=150)
    print(f"\nSaved chart to {out_png}")

    out_csv = f"{ticker}_{strike_label}_put_{price_type}s.csv"
    df.to_csv(out_csv, index=False)
    print(f"Saved data to {out_csv}")

    plt.show()


if __name__ == "__main__":
    main()
