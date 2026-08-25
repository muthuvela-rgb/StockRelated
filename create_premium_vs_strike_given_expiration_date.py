"""
Option Premium vs Strike Plot — configurable stock, expiration, put/call, bid/ask
-----------------------------------------------------------------------------
Requires: yfinance, pandas, matplotlib
    pip install yfinance pandas matplotlib

Run:
    python create_premium_vs_strike_given_expiration_date.py --ticker QQQ --expiration 2026-01-16
    python create_premium_vs_strike_given_expiration_date.py -t AAPL -e 2026-03-20 --option-type call
    python create_premium_vs_strike_given_expiration_date.py -t QQQ -e 2026-01-16 --price-type ask
    python create_premium_vs_strike_given_expiration_date.py -t QQQ -e 2026-01-16 --strike-range 20
    python create_premium_vs_strike_given_expiration_date.py -t QQQ            # nearest expiration, all strikes

Options:
    -t, --ticker       Stock/ETF ticker symbol (default: QQQ)
    -e, --expiration    Expiration date, "YYYY-MM-DD" (default: the nearest
                        upcoming expiration). If the given date isn't an
                        actual listed expiration, the closest listed
                        expiration (by calendar days, earlier or later) is
                        used instead and the substitution is printed.
    --option-type       "put" or "call" (default: call)
    -p, --price-type    Which quote to plot: "bid" or "ask" (default: bid)
    --strike-range      Limit strikes to within +/- this percent of the
                        current stock price (default: show every listed
                        strike).
    --no-fallback       Disable the lastPrice fallback (see below), showing
                        raw 0 values instead.

What it does:
    1. Pulls the live list of option expiration dates for the given ticker
       from Yahoo Finance.
    2. Picks the requested expiration if it's listed; otherwise snaps to the
       nearest listed expiration (by absolute calendar-day distance) and
       tells you what it substituted. With no --expiration given, the
       nearest upcoming expiration is used.
    3. Pulls the put or call chain for that expiration.
    4. Optionally restricts to strikes within --strike-range percent of the
       current stock price, to keep far out-of-the-money noise off the
       chart.
    5. Prints a table with strike, bid, ask, lastPrice, volume, and open
       interest for every strike kept, so you can see exactly what data
       Yahoo returned.
    6. Plots the selected Bid or Ask ($) on the Y-axis vs Strike Price on
       the X-axis. Yahoo's free feed frequently reports bid=0 / ask=0 for
       thinly-traded or far out-of-the-money contracts. When that happens,
       the script substitutes lastPrice instead (marked with an orange
       triangle on the chart and a "used_fallback" column in the CSV) so you
       don't just get a flat zero line. Use --no-fallback to see raw zeros.
    7. Saves the chart as {ticker}_{expiration}_{option_type}_{price_type}s.png
       and the data as {ticker}_{expiration}_{option_type}_{price_type}s.csv.

Notes:
    - Bid/ask prices reflect current/live market data at the time you run
      the script — they will differ every time you run it, especially for
      short-dated or illiquid contracts.
    - Strikes far from the current stock price, or short-dated contracts on
      a slow trading day, are the most likely to show bid=0/ask=0 — that's a
      market-liquidity/data-feed characteristic, not a bug.
    - This is data retrieval / visualization only — not investment advice.
"""

import argparse
import sys
from datetime import datetime

import pandas as pd
import matplotlib.pyplot as plt

try:
    import yfinance as yf
except ImportError:
    sys.exit("Missing dependency. Install with:  pip install yfinance pandas matplotlib")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Plot put/call option bid or ask premiums across strikes for a given "
                    "ticker and expiration date."
    )
    parser.add_argument("-t", "--ticker", type=str, default="QQQ",
                         help="Stock/ETF ticker symbol (default: QQQ)")
    parser.add_argument("-e", "--expiration", type=str, default=None,
                         help='Expiration date, "YYYY-MM-DD" (default: nearest upcoming '
                              "expiration). If not an actual listed expiration, the nearest "
                              "listed one is used instead.")
    parser.add_argument("--option-type", type=str, default="call",
                         choices=["put", "call"],
                         help='Option type: "put" or "call" (default: call)')
    parser.add_argument("-p", "--price-type", type=str, default="bid",
                         choices=["bid", "ask"],
                         help='Which quote to plot: "bid" or "ask" (default: bid)')
    parser.add_argument("--strike-range", type=float, default=None,
                         help="Limit strikes to within +/- this percent of the current stock "
                              "price (default: show every listed strike).")
    parser.add_argument("--no-fallback", action="store_true",
                         help="Disable fallback to lastPrice when bid and ask are both 0 "
                              "(shows raw zeros instead).")
    return parser.parse_args()


def find_expiration(all_exps, requested):
    """
    Resolve the expiration date to actually use.

    - all_exps: tuple/list of listed expiration date strings ("YYYY-MM-DD"),
      as returned by yfinance, assumed sorted ascending.
    - requested: the user-requested date string, or None.

    Returns (used_expiration, was_substituted). With no request, the
    earliest (nearest upcoming) listed expiration is used. With a request
    that isn't listed, the closest listed date by absolute calendar-day
    distance is used instead.
    """
    if not all_exps:
        return None, False

    if requested is None:
        return all_exps[0], False

    if requested in all_exps:
        return requested, False

    try:
        target = datetime.strptime(requested, "%Y-%m-%d").date()
    except ValueError:
        sys.exit(f"Could not parse --expiration '{requested}'. Use the format YYYY-MM-DD.")

    nearest = min(
        all_exps,
        key=lambda e: abs((datetime.strptime(e, "%Y-%m-%d").date() - target).days),
    )
    return nearest, True


def get_current_price(ticker_obj):
    """
    Fetch the current/last stock price, trying a few yfinance data sources
    in order of preference since availability varies by ticker and by
    yfinance version.
    """
    try:
        price = ticker_obj.fast_info.get("last_price")
        if price:
            return float(price)
    except Exception:
        pass

    try:
        price = ticker_obj.info.get("regularMarketPrice") or ticker_obj.info.get("currentPrice")
        if price:
            return float(price)
    except Exception:
        pass

    try:
        hist = ticker_obj.history(period="5d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass

    return None


def main():
    args = parse_args()
    ticker = args.ticker.upper()
    option_type = args.option_type  # "put" or "call"
    price_type = args.price_type  # "bid" or "ask"
    price_label = price_type.capitalize()
    option_label = option_type.capitalize()

    print(f"Fetching {ticker} option expirations...")
    tk = yf.Ticker(ticker)
    all_exps = tk.options  # tuple of date strings 'YYYY-MM-DD', sorted ascending

    if not all_exps:
        sys.exit(f"No listed option expirations found for {ticker}. Check the ticker symbol, "
                  f"or Yahoo may be rate-limiting — try again shortly.")

    expiration, substituted = find_expiration(all_exps, args.expiration)
    if substituted:
        print(f"Requested expiration '{args.expiration}' is not listed for {ticker}. "
              f"Using nearest listed expiration instead: {expiration}")
    else:
        print(f"Using expiration: {expiration}")

    chain = tk.option_chain(expiration)
    contracts = chain.puts if option_type == "put" else chain.calls

    if contracts.empty:
        sys.exit(f"No {option_type} contracts available for {ticker} at expiration {expiration}.")

    contracts = contracts.copy()

    if args.strike_range is not None:
        current_price = get_current_price(tk)
        if current_price is None:
            print("Warning: could not fetch current stock price, ignoring --strike-range.")
        else:
            low = current_price * (1 - args.strike_range / 100)
            high = current_price * (1 + args.strike_range / 100)
            contracts = contracts[(contracts["strike"] >= low) & (contracts["strike"] <= high)]
            print(f"Current {ticker} price: ${current_price:.2f}  |  "
                  f"keeping strikes in [{low:.2f}, {high:.2f}] "
                  f"(+/-{args.strike_range:g}%)")
            if contracts.empty:
                sys.exit(f"No strikes fall within +/-{args.strike_range:g}% of the current price. "
                          f"Try a wider --strike-range.")

    contracts = contracts.sort_values("strike")

    print(f"\nFound {len(contracts)} strikes. Plotting {price_type} for each {option_type}...\n")
    print(f"{'Strike':>8} {'Bid':>8} {'Ask':>8} {'Last':>8} {'Vol':>8} {'OI':>8}")

    def safe_num(val):
        return 0.0 if pd.isna(val) else float(val)

    records = []
    zero_quote_count = 0
    for _, row in contracts.iterrows():
        strike = safe_num(row.get("strike"))
        bid = safe_num(row.get("bid"))
        ask = safe_num(row.get("ask"))
        last = safe_num(row.get("lastPrice"))
        vol = safe_num(row.get("volume"))
        oi = safe_num(row.get("openInterest"))

        price = bid if price_type == "bid" else ask
        used_fallback = False
        # yfinance often reports 0 bid/ask on thinly traded contracts.
        # Fall back to lastPrice so the chart isn't just a flat zero line.
        if (bid == 0 and ask == 0) and last > 0 and not args.no_fallback:
            price = last
            used_fallback = True

        fallback_flag = " [used lastPrice, bid/ask were 0]" if used_fallback else ""
        print(f"{strike:>8.2f} {bid:>8.2f} {ask:>8.2f} {last:>8.2f} {int(vol):>8} {int(oi):>8}"
              f"{fallback_flag}")

        if bid == 0 and ask == 0:
            zero_quote_count += 1

        records.append({"strike": strike, price_type: price, "used_fallback": used_fallback})

    if zero_quote_count:
        print(f"\nNote: {zero_quote_count} of {len(records)} strikes had bid=0 and ask=0 "
              f"from Yahoo's feed (typical for far-OTM / low-volume contracts, or when markets "
              f"are closed). Where possible, those points were plotted using lastPrice instead — "
              f"see the 'used_fallback' column in the CSV. Run --no-fallback to disable this and "
              f"see raw zeros.")

    df = pd.DataFrame(records).sort_values("strike")

    # Plot
    plt.figure(figsize=(12, 6))
    plt.plot(df["strike"], df[price_type], linewidth=1.5, color="tab:blue", zorder=1)

    real_pts = df[~df["used_fallback"]]
    fallback_pts = df[df["used_fallback"]]
    plt.scatter(real_pts["strike"], real_pts[price_type], color="tab:blue",
                label=price_label, zorder=2)
    if not fallback_pts.empty:
        plt.scatter(fallback_pts["strike"], fallback_pts[price_type], color="tab:orange",
                    marker="^", label="lastPrice (bid/ask were 0)", zorder=3)
        plt.legend()

    plt.title(f"{ticker} {expiration} {option_label} — {price_label} Premium by Strike")
    plt.xlabel("Strike Price ($)")
    plt.ylabel(f"{option_label} {price_label} Premium ($)")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()

    out_png = f"{ticker}_{expiration}_{option_type}_{price_type}s.png"
    plt.savefig(out_png, dpi=150)
    print(f"\nSaved chart to {out_png}")

    out_csv = f"{ticker}_{expiration}_{option_type}_{price_type}s.csv"
    df.to_csv(out_csv, index=False)
    print(f"Saved data to {out_csv}")

    plt.show()


if __name__ == "__main__":
    main()
