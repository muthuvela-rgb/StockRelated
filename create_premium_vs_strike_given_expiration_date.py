"""
Option Premium vs Strike Plot — configurable stock, expiration, put/call, bid/ask
-----------------------------------------------------------------------------
Requires: yfinance, pandas, matplotlib
    pip install yfinance pandas matplotlib

Run:
    python create_premium_vs_strike_given_expiration_date.py               # QQQ, nearest 3 expirations
    python create_premium_vs_strike_given_expiration_date.py --ticker QQQ --expiration 2026-01-16
    python create_premium_vs_strike_given_expiration_date.py -t AAPL -e 2026-03-20 --option-type call
    python create_premium_vs_strike_given_expiration_date.py -t QQQ -e 2026-01-16 --price-type ask
    python create_premium_vs_strike_given_expiration_date.py -t QQQ -e 2026-01-16 --strike-range 20
    python create_premium_vs_strike_given_expiration_date.py -t AAPL --num-expirations 5

Options:
    -t, --ticker         Stock/ETF ticker symbol (default: QQQ)
    -e, --expiration      Expiration date, "YYYY-MM-DD" (default: none — see
                          below). If given but not an actual listed
                          expiration, the closest listed expiration (by
                          calendar days, earlier or later) is used instead
                          and the substitution is printed.
    --num-expirations     When -e/--expiration is NOT given, how many of the
                          nearest expirations (by calendar-day distance from
                          today) to plot together (default: 3).
    --option-type         "put" or "call" (default: call)
    -p, --price-type      Which quote to plot: "bid" or "ask" (default: bid)
    --strike-range        Limit strikes to within +/- this percent of the
                          current stock price (default: show every listed
                          strike).
    --no-fallback         Disable the lastPrice fallback (see below), showing
                          raw 0 values instead.

What it does:
    1. Pulls the live list of option expiration dates for the given ticker
       from Yahoo Finance.
    2. Picks which expiration(s) to use:
         - If --expiration is given and listed, uses it as-is.
         - If --expiration is given but not listed, snaps to the single
           nearest listed expiration (by absolute calendar-day distance)
           and prints what it substituted.
         - If --expiration is NOT given at all, uses the --num-expirations
           (default 3) listed expirations nearest to today's date, and
           plots all of them together as separate lines on one chart.
    3. Pulls the put or call chain for each expiration in use.
    4. Optionally restricts to strikes within --strike-range percent of the
       current stock price, to keep far out-of-the-money noise off the
       chart.
    5. Prints a table with strike, bid, ask, lastPrice, volume, and open
       interest for every strike kept, so you can see exactly what data
       Yahoo returned.
    6. Plots the selected Bid or Ask ($) on the Y-axis vs Strike Price on
       the X-axis, one line per expiration. Yahoo's free feed frequently
       reports bid=0 / ask=0 for thinly-traded or far out-of-the-money
       contracts. When that happens, the script substitutes lastPrice
       instead (marked with an orange triangle on the chart and a
       "used_fallback" column in the CSV) so you don't just get a flat zero
       line. Use --no-fallback to see raw zeros.
    7. Saves the chart and the data (CSV) named after the ticker,
       option type, price type, and the expiration(s) used.

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
                    "ticker and expiration date(s)."
    )
    parser.add_argument("-t", "--ticker", type=str, default="QQQ",
                         help="Stock/ETF ticker symbol (default: QQQ)")
    parser.add_argument("-e", "--expiration", type=str, default=None,
                         help='Expiration date, "YYYY-MM-DD". If omitted, the nearest '
                              "--num-expirations expirations to today are plotted together. "
                              "If given but not an actual listed expiration, the nearest "
                              "listed one is used instead.")
    parser.add_argument("--num-expirations", type=int, default=3,
                         help="When --expiration is omitted, how many of the nearest "
                              "expirations to today to plot together (default: 3).")
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
    Resolve a single explicitly-requested expiration date to actually use.

    - all_exps: tuple/list of listed expiration date strings ("YYYY-MM-DD"),
      as returned by yfinance.
    - requested: the user-requested date string (not None).

    Returns (used_expiration, was_substituted). If requested isn't listed,
    the closest listed date by absolute calendar-day distance is used
    instead.
    """
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


def get_nearest_expirations(all_exps, today, n):
    """
    Return the n listed expirations closest to today (by absolute
    calendar-day distance), sorted ascending by date for consistent
    plotting/legend order.
    """
    by_distance = sorted(
        all_exps,
        key=lambda e: abs((datetime.strptime(e, "%Y-%m-%d").date() - today).days),
    )
    chosen = by_distance[:n]
    return sorted(chosen, key=lambda e: datetime.strptime(e, "%Y-%m-%d").date())


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


def safe_num(val):
    return 0.0 if pd.isna(val) else float(val)


def fetch_strike_records(tk, ticker, expiration, option_type, price_type, strike_low,
                          strike_high, no_fallback):
    """
    Pull the option chain for a single expiration, filter to the requested
    strike range (if any), print the per-strike table, and return a list of
    record dicts: {expiration, strike, <price_type>, used_fallback}.
    """
    chain = tk.option_chain(expiration)
    contracts = chain.puts if option_type == "put" else chain.calls

    if contracts.empty:
        print(f"  {expiration}: no {option_type} contracts available")
        return []

    contracts = contracts.copy()
    if strike_low is not None:
        contracts = contracts[(contracts["strike"] >= strike_low) & (contracts["strike"] <= strike_high)]
        if contracts.empty:
            print(f"  {expiration}: no strikes within the requested --strike-range")
            return []

    contracts = contracts.sort_values("strike")

    print(f"\n{expiration} ({len(contracts)} strikes):")
    print(f"{'Strike':>8} {'Bid':>8} {'Ask':>8} {'Last':>8} {'Vol':>8} {'OI':>8}")

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
        if (bid == 0 and ask == 0) and last > 0 and not no_fallback:
            price = last
            used_fallback = True

        fallback_flag = " [used lastPrice, bid/ask were 0]" if used_fallback else ""
        print(f"{strike:>8.2f} {bid:>8.2f} {ask:>8.2f} {last:>8.2f} {int(vol):>8} {int(oi):>8}"
              f"{fallback_flag}")

        if bid == 0 and ask == 0:
            zero_quote_count += 1

        records.append({"expiration": expiration, "strike": strike, price_type: price,
                         "used_fallback": used_fallback})

    if zero_quote_count:
        print(f"  Note: {zero_quote_count} of {len(records)} strikes had bid=0 and ask=0.")

    return records


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

    if args.expiration is None:
        if args.num_expirations < 1:
            sys.exit("--num-expirations must be at least 1.")
        today = datetime.today().date()
        expirations = get_nearest_expirations(all_exps, today, args.num_expirations)
        print(f"No expiration given — using the {len(expirations)} nearest expiration(s) to "
              f"today ({today}): {', '.join(expirations)}")
    else:
        expiration, substituted = find_expiration(all_exps, args.expiration)
        if substituted:
            print(f"Requested expiration '{args.expiration}' is not listed for {ticker}. "
                  f"Using nearest listed expiration instead: {expiration}")
        else:
            print(f"Using expiration: {expiration}")
        expirations = [expiration]

    strike_low = strike_high = None
    if args.strike_range is not None:
        current_price = get_current_price(tk)
        if current_price is None:
            print("Warning: could not fetch current stock price, ignoring --strike-range.")
        else:
            strike_low = current_price * (1 - args.strike_range / 100)
            strike_high = current_price * (1 + args.strike_range / 100)
            print(f"Current {ticker} price: ${current_price:.2f}  |  "
                  f"keeping strikes in [{strike_low:.2f}, {strike_high:.2f}] "
                  f"(+/-{args.strike_range:g}%)")

    print(f"\nPlotting {price_type} for each {option_type}...")

    all_records = []
    for expiration in expirations:
        all_records.extend(fetch_strike_records(
            tk, ticker, expiration, option_type, price_type, strike_low, strike_high,
            args.no_fallback,
        ))

    if not all_records:
        sys.exit("No data collected — nothing to plot.")

    df = pd.DataFrame(all_records).sort_values(["expiration", "strike"])

    # Plot: one line per expiration, sharing a single fallback-marker legend entry.
    plt.figure(figsize=(12, 6))
    color_cycle = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    fallback_labeled = False

    for i, expiration in enumerate(expirations):
        exp_df = df[df["expiration"] == expiration]
        if exp_df.empty:
            continue
        color = color_cycle[i % len(color_cycle)]
        line_label = expiration if len(expirations) > 1 else price_label

        plt.plot(exp_df["strike"], exp_df[price_type], linewidth=1.5, color=color, zorder=1)
        plt.scatter(exp_df["strike"], exp_df[price_type], color=color, label=line_label, zorder=2)

        fallback_pts = exp_df[exp_df["used_fallback"]]
        if not fallback_pts.empty:
            plt.scatter(fallback_pts["strike"], fallback_pts[price_type], color="tab:orange",
                        marker="^", zorder=3,
                        label=None if fallback_labeled else "lastPrice (bid/ask were 0)")
            fallback_labeled = True

    plt.legend()

    if len(expirations) == 1:
        title = f"{ticker} {expirations[0]} {option_label} — {price_label} Premium by Strike"
    else:
        title = (f"{ticker} {option_label} — {price_label} Premium by Strike "
                 f"({len(expirations)} nearest expirations)")
    plt.title(title)
    plt.xlabel("Strike Price ($)")
    plt.ylabel(f"{option_label} {price_label} Premium ($)")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()

    if len(expirations) == 1:
        exp_label = expirations[0]
    else:
        exp_label = f"{len(expirations)}exp_{expirations[0]}_to_{expirations[-1]}"

    out_png = f"{ticker}_{exp_label}_{option_type}_{price_type}s.png"
    plt.savefig(out_png, dpi=150)
    print(f"\nSaved chart to {out_png}")

    out_csv = f"{ticker}_{exp_label}_{option_type}_{price_type}s.csv"
    df.to_csv(out_csv, index=False)
    print(f"Saved data to {out_csv}")

    plt.show()


if __name__ == "__main__":
    main()
