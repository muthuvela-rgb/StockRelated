"""
Option Premium vs Strike Plot — configurable stock, expiration, put/call, bid/ask
-----------------------------------------------------------------------------
Requires: yfinance, pandas, matplotlib
    pip install yfinance pandas matplotlib

Run:
    python create_premium_vs_strike_given_expiration_date.py               # QQQ puts, nearest 3 expirations, 20%-150% of price
    python create_premium_vs_strike_given_expiration_date.py --ticker QQQ --expiration 2026-01-16
    python create_premium_vs_strike_given_expiration_date.py -t AAPL -e 2026-03-20 --option-type call
    python create_premium_vs_strike_given_expiration_date.py -t QQQ -e 2026-01-16 --price-type ask
    python create_premium_vs_strike_given_expiration_date.py -t QQQ -e 2026-01-16 --strike-range 50-150
    python create_premium_vs_strike_given_expiration_date.py -t QQQ --no-strike-range   # every listed strike
    python create_premium_vs_strike_given_expiration_date.py -t AAPL --num-expirations 5
    python create_premium_vs_strike_given_expiration_date.py -t QQQ --log-scale         # log-scale Y-axis

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
    --option-type         "put" or "call" (default: put)
    -p, --price-type      Which quote to plot: "bid" or "ask" (default: bid)
    --strike-range        Keep strikes whose price falls within this
                          "LOW-HIGH" percent range of the current stock
                          price (default: "20-150", i.e. 20% to 150% of the
                          current price).
    --no-strike-range     Disable strike filtering, showing every listed
                          strike regardless of --strike-range.
    --no-fallback         Disable the lastPrice fallback (see below), showing
                          raw 0 values instead.
    --log-scale           Plot the Y-axis (premium) on a log scale instead of
                          linear. Points priced at exactly $0 can't be shown
                          on a log scale and are dropped with a warning.

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
    4. Restricts to strikes whose price falls within --strike-range percent
       of the current stock price (default 20%-150%), to keep far
       out-of-the-money noise off the chart. Use --no-strike-range to see
       every listed strike instead.
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
       Hovering the mouse over any point in the interactive chart window
       pops up a tooltip with that contract's expiration, strike, bid,
       ask, last price, volume, open interest, and premium/strike ratio.
       (Hover only works in the live matplotlib window — the saved PNG is
       a static image.) A dotted vertical line marks the underlying's
       current price.
    7. Computes premium/strike for every plotted point (the "premium_to_strike"
       CSV column) and marks the single highest one — across every strike
       and expiration plotted — with a large hot-pink star, called out in
       the legend and printed to the console.
    8. When 2+ expirations are plotted, compares each pair of CONSECUTIVE
       expirations (adjacent by date — e.g. with 3 expirations, only
       1st-vs-2nd and 2nd-vs-3rd are compared, never 1st-vs-3rd) and, for
       EVERY such pair, finds the strike where the two curves are furthest
       apart vertically — marked with a solid purple double-headed arrow
       and a dollar-amount label — and the strike where they're CLOSEST
       together (excluding an exact $0 gap, i.e. curves that coincide
       exactly) — marked with a dashed teal double-headed arrow. So with
       3 expirations you'll see up to 2 purple and 2 teal arrows, one pair
       of markers per consecutive expiration pair. All printed to the
       console too.
    9. For EACH expiration curve, computes the slope (premium change per
       $1 of strike) between every pair of adjacent (consecutive-by-strike)
       strikes on that curve, and marks the single largest (steepest
       upward) slope with a thick green highlighted segment and a
       "slope X.XX" label — one marker per plotted expiration. Printed to
       the console too.
    10. Saves the chart and the data (CSV) named after the ticker,
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
    parser.add_argument("--option-type", type=str, default="put",
                         choices=["put", "call"],
                         help='Option type: "put" or "call" (default: put)')
    parser.add_argument("-p", "--price-type", type=str, default="bid",
                         choices=["bid", "ask"],
                         help='Which quote to plot: "bid" or "ask" (default: bid)')
    parser.add_argument("--strike-range", type=str, default="20-150",
                         help='Keep strikes priced within this "LOW-HIGH" percent range of the '
                              'current stock price, e.g. "20-150" (default: "20-150", i.e. 20%% '
                              "to 150%% of the current price).")
    parser.add_argument("--no-strike-range", action="store_true",
                         help="Disable strike filtering, showing every listed strike regardless "
                              "of --strike-range.")
    parser.add_argument("--log-scale", action="store_true",
                         help="Plot the Y-axis (premium) on a log scale instead of linear. "
                              "Useful when premiums span a wide range (e.g. far-OTM vs "
                              "near-the-money strikes). Points priced at exactly $0 can't be "
                              "shown on a log scale and are dropped with a warning.")
    parser.add_argument("--no-fallback", action="store_true",
                         help="Disable fallback to lastPrice when bid and ask are both 0 "
                              "(shows raw zeros instead).")
    return parser.parse_args()


def parse_strike_range(range_str):
    """
    Parse the --strike-range argument, a "LOW-HIGH" percent range (e.g.
    "20-150"), into (low_pct, high_pct) floats.
    """
    parts = range_str.strip().replace("%", "").split("-")
    if len(parts) != 2:
        sys.exit(f"Could not parse --strike-range '{range_str}'. Use a range like '20-150'.")
    try:
        low_pct, high_pct = float(parts[0]), float(parts[1])
    except ValueError:
        sys.exit(f"Could not parse --strike-range '{range_str}' as numbers.")
    if low_pct > high_pct:
        sys.exit(f"--strike-range '{range_str}': low end must not exceed the high end.")
    return low_pct, high_pct


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
    record dicts: {expiration, strike, premium, bid, ask, lastPrice, volume,
    openInterest, used_fallback}, where "premium" is the requested
    price_type (bid or ask), substituted with lastPrice when both bid and
    ask are 0 (unless no_fallback is set).
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

        records.append({"expiration": expiration, "strike": strike, "premium": price,
                         "bid": bid, "ask": ask, "lastPrice": last, "volume": vol,
                         "openInterest": oi, "used_fallback": used_fallback})

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

    current_price = get_current_price(tk)
    if current_price is None:
        print("Warning: could not fetch current stock price.")
    else:
        print(f"Current {ticker} price: ${current_price:.2f}")

    strike_low = strike_high = None
    if not args.no_strike_range:
        low_pct, high_pct = parse_strike_range(args.strike_range)
        if current_price is None:
            print("Ignoring --strike-range since the current price is unavailable.")
        else:
            strike_low = current_price * low_pct / 100
            strike_high = current_price * high_pct / 100
            print(f"Keeping strikes in [{strike_low:.2f}, {strike_high:.2f}] "
                  f"({low_pct:g}%-{high_pct:g}% of price)")

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
    df["premium_to_strike"] = df["premium"] / df["strike"]

    best_row = df.loc[df["premium_to_strike"].idxmax()]
    best_strike = best_row["strike"]
    best_expiration = best_row["expiration"]
    best_premium = best_row["premium"]
    best_ratio = best_row["premium_to_strike"]
    print(f"\nHighest {price_type}-to-strike ratio: {best_ratio:.2%}  |  "
          f"strike {best_strike:g}  |  expiration {best_expiration}  |  "
          f"{price_type} ${best_premium:.2f} / strike ${best_strike:g}")

    # For EACH pair of consecutive (adjacent-by-date) expirations, find the strike
    # where those two curves are furthest apart and closest together vertically.
    # Every adjacent pair gets its own widest/narrowest marker, not just one
    # overall winner across all pairs.
    def pair_gaps(exp_a, exp_b):
        a = df[df["expiration"] == exp_a][["strike", "premium"]].rename(columns={"premium": "premium_a"})
        b = df[df["expiration"] == exp_b][["strike", "premium"]].rename(columns={"premium": "premium_b"})
        merged = a.merge(b, on="strike", how="inner")
        if merged.empty:
            return None
        merged["gap"] = (merged["premium_b"] - merged["premium_a"]).abs()
        return merged

    def describe_gap(row, exp_a, exp_b):
        if row["premium_a"] <= row["premium_b"]:
            low_exp, low_p, high_exp, high_p = exp_a, row["premium_a"], exp_b, row["premium_b"]
        else:
            low_exp, low_p, high_exp, high_p = exp_b, row["premium_b"], exp_a, row["premium_a"]
        return {"strike": row["strike"], "gap": row["gap"], "low_premium": low_p, "high_premium": high_p,
                "low_expiration": low_exp, "high_expiration": high_exp}

    gap_markers = []  # [{"type": "widest"/"narrowest", ...describe_gap() fields}, ...]
    if len(expirations) < 2:
        print("Only one expiration is plotted — need at least two curves to compare a "
              "vertical gap between them.")
    else:
        for exp_a, exp_b in zip(expirations, expirations[1:]):
            merged = pair_gaps(exp_a, exp_b)
            if merged is None:
                print(f"No strikes are shared between {exp_a} and {exp_b} — can't compute a "
                      f"vertical gap between them.")
                continue

            widest_idx = merged["gap"].idxmax()
            widest = describe_gap(merged.loc[widest_idx], exp_a, exp_b)
            print(f"Widest gap {exp_a} vs {exp_b}: ${widest['gap']:.2f} at strike "
                  f"{widest['strike']:g}  |  {widest['low_expiration']} ${widest['low_premium']:.2f}  "
                  f"vs  {widest['high_expiration']} ${widest['high_premium']:.2f}")
            gap_markers.append({"type": "widest", "exp_a": exp_a, "exp_b": exp_b, **widest})

            # Ignore $0 gaps (curves exactly overlapping) when picking the narrowest —
            # a real, visible gap is more useful to call out than a coincidental tie.
            nonzero = merged[merged["gap"] > 0]
            if nonzero.empty:
                print(f"Every strike shared between {exp_a} and {exp_b} has an identical "
                      f"premium (gap $0) — skipping the narrowest-gap marker for this pair.")
            else:
                narrowest_idx = nonzero["gap"].idxmin()
                if narrowest_idx == widest_idx:
                    print(f"The only strike with a nonzero gap between {exp_a} and {exp_b} is "
                          f"also the widest-gap strike — skipping a separate narrowest marker "
                          f"for this pair to avoid overlapping arrows.")
                else:
                    narrowest = describe_gap(merged.loc[narrowest_idx], exp_a, exp_b)
                    print(f"Narrowest (nonzero) gap {exp_a} vs {exp_b}: ${narrowest['gap']:.2f} "
                          f"at strike {narrowest['strike']:g}  |  {narrowest['low_expiration']} "
                          f"${narrowest['low_premium']:.2f}  vs  {narrowest['high_expiration']} "
                          f"${narrowest['high_premium']:.2f}")
                    gap_markers.append({"type": "narrowest", "exp_a": exp_a, "exp_b": exp_b, **narrowest})

    # For EACH expiration curve, find the pair of adjacent (consecutive-by-strike)
    # strikes with the largest slope (premium change per $1 of strike) — the
    # steepest-rising segment of that curve. One marker per plotted expiration.
    def steepest_slope(exp_df):
        rows = list(exp_df.itertuples(index=False))
        best = None
        for a, b in zip(rows, rows[1:]):
            d_strike = b.strike - a.strike
            if d_strike == 0:
                continue  # duplicate strike, slope undefined
            slope = (b.premium - a.premium) / d_strike
            if best is None or slope > best["slope"]:
                best = {"strike_a": a.strike, "strike_b": b.strike,
                        "premium_a": a.premium, "premium_b": b.premium, "slope": slope}
        return best

    slope_markers = []  # [{"expiration": ..., "strike_a"/"strike_b"/"premium_a"/"premium_b"/"slope": ...}, ...]
    for expiration in expirations:
        exp_df = df[df["expiration"] == expiration].sort_values("strike")
        steepest = steepest_slope(exp_df)
        if steepest is None:
            print(f"{expiration}: fewer than two distinct strikes — can't compute a slope.")
            continue
        slope_markers.append({"expiration": expiration, **steepest})
        print(f"Steepest slope for {expiration}: {steepest['slope']:.4f} {price_type} $/strike "
              f"(strike {steepest['strike_a']:g} -> {steepest['strike_b']:g}, "
              f"{price_type} ${steepest['premium_a']:.2f} -> ${steepest['premium_b']:.2f})")

    # Plot: one line per expiration, sharing a single fallback-marker legend entry.
    fig, ax = plt.subplots(figsize=(12, 6))
    color_cycle = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    fallback_labeled = False
    hover_points = []  # {"strike", "price", "text"} for every plotted point, for hover lookup

    def add_hover_points(sub_df, expiration):
        for _, r in sub_df.iterrows():
            text = (
                f"{ticker} {option_label}  |  Exp: {expiration}\n"
                f"Strike: {r['strike']:g}\n"
                f"Bid: {r['bid']:.2f}   Ask: {r['ask']:.2f}\n"
                f"Last: {r['lastPrice']:.2f}\n"
                f"Vol: {int(r['volume'])}   OI: {int(r['openInterest'])}\n"
                f"{price_label}/Strike: {r['premium_to_strike']:.2%}"
            )
            if r["used_fallback"]:
                text += "\n(plotted lastPrice — bid/ask were 0)"
            if expiration == best_expiration and r["strike"] == best_strike:
                text = "★ HIGHEST PREMIUM/STRIKE RATIO\n" + text
            hover_points.append({"strike": r["strike"], "price": r["premium"], "text": text})

    for i, expiration in enumerate(expirations):
        exp_df = df[df["expiration"] == expiration]
        if exp_df.empty:
            continue
        color = color_cycle[i % len(color_cycle)]
        line_label = expiration if len(expirations) > 1 else price_label

        ax.plot(exp_df["strike"], exp_df["premium"], linewidth=1.5, color=color, zorder=1)
        ax.scatter(exp_df["strike"], exp_df["premium"], color=color, label=line_label, zorder=2)

        fallback_pts = exp_df[exp_df["used_fallback"]]
        if not fallback_pts.empty:
            ax.scatter(fallback_pts["strike"], fallback_pts["premium"], color="tab:orange",
                       marker="^", zorder=3,
                       label=None if fallback_labeled else "lastPrice (bid/ask were 0)")
            fallback_labeled = True

        add_hover_points(exp_df, expiration)

    # Highlight the strike with the single highest premium-to-strike ratio, in a
    # bold, high-contrast color/marker so it stands out from the regular line dots.
    ax.scatter([best_strike], [best_premium], s=400, color="#FF1493", edgecolor="black",
               linewidths=1.5, marker="*", zorder=6,
               label=f"Highest {price_label}/Strike: {best_ratio:.2%} (strike {best_strike:g})")

    # Highlight each pair's widest/narrowest vertical gap with a double-headed arrow
    # and dollar-amount label — solid purple for widest, dashed teal for narrowest,
    # colors/styles not used anywhere else on the chart, consistent across all pairs.
    for marker in gap_markers:
        gs = marker["strike"]
        y_lo, y_hi = marker["low_premium"], marker["high_premium"]
        is_widest = marker["type"] == "widest"
        color = "purple" if is_widest else "teal"
        style = dict(arrowstyle="<->", color=color, lw=2.5) if is_widest else \
            dict(arrowstyle="<->", color=color, lw=2.5, linestyle="dashed")
        kind = "Widest" if is_widest else "Narrowest"

        ax.annotate("", xy=(gs, y_hi), xytext=(gs, y_lo), arrowprops=style, zorder=7)
        pair_suffix = f", {marker['exp_a']} vs {marker['exp_b']}"
        ax.plot([], [], color=color, linewidth=2.5,
                linestyle="solid" if is_widest else "dashed",
                label=f"{kind} gap: ${marker['gap']:.2f} (strike {gs:g}{pair_suffix})")
        ax.annotate(f"${marker['gap']:.2f}", xy=(gs, (y_lo + y_hi) / 2),
                    xytext=(8, 0), textcoords="offset points", color=color,
                    fontweight="bold", va="center", zorder=8)

    # Highlight each expiration curve's steepest adjacent-strike slope with a
    # thick green segment and a "slope X.XX" label — a color/style not used
    # anywhere else on the chart, one marker per plotted expiration.
    SLOPE_COLOR = "forestgreen"
    for marker in slope_markers:
        sa, sb = marker["strike_a"], marker["strike_b"]
        pa, pb = marker["premium_a"], marker["premium_b"]
        mid_x, mid_y = (sa + sb) / 2, (pa + pb) / 2

        ax.plot([sa, sb], [pa, pb], color=SLOPE_COLOR, linewidth=4,
                solid_capstyle="round", alpha=0.85, zorder=5)
        ax.annotate(f"slope {marker['slope']:.2f}", xy=(mid_x, mid_y), xytext=(0, 10),
                    textcoords="offset points", ha="center", color=SLOPE_COLOR,
                    fontweight="bold", zorder=9)

        exp_suffix = f", {marker['expiration']}" if len(expirations) > 1 else ""
        ax.plot([], [], color=SLOPE_COLOR, linewidth=4,
                label=f"Steepest slope: {marker['slope']:.2f} $/strike "
                      f"(strike {sa:g}→{sb:g}{exp_suffix})")

    if current_price is not None:
        ax.axvline(current_price, color="gray", linestyle=":", linewidth=1.5, zorder=0,
                   label=f"Current price (${current_price:.2f})")

    ax.legend()

    if len(expirations) == 1:
        title = f"{ticker} {expirations[0]} {option_label} — {price_label} Premium by Strike"
    else:
        title = (f"{ticker} {option_label} — {price_label} Premium by Strike "
                 f"({len(expirations)} nearest expirations)")
    y_label = f"{option_label} {price_label} Premium ($)"
    if args.log_scale:
        title += " (log scale)"
        y_label += " — log scale"

        non_positive = df[df["premium"] <= 0]
        if not non_positive.empty:
            print(f"\nWarning: {len(non_positive)} point(s) have a premium of $0 and can't be "
                  f"shown on the log-scale Y-axis (log of 0/negative is undefined) — they'll be "
                  f"missing from the chart.")

        ax.set_yscale("log")
        ax.grid(True, which="both", alpha=0.3)
    else:
        ax.grid(True, alpha=0.3)

    ax.set_title(title)
    ax.set_xlabel("Strike Price ($)")
    ax.set_ylabel(y_label)
    fig.tight_layout()

    # Hover tooltip: shows the full option details for the nearest plotted point.
    annot = ax.annotate("", xy=(0, 0), xytext=(15, 15), textcoords="offset points",
                         bbox=dict(boxstyle="round", fc="lightyellow", ec="gray"),
                         arrowprops=dict(arrowstyle="->"), zorder=10)
    annot.set_visible(False)
    HOVER_RADIUS_PX = 15

    def on_hover(event):
        if event.inaxes != ax or not hover_points:
            if annot.get_visible():
                annot.set_visible(False)
                fig.canvas.draw_idle()
            return

        xy_pixels = ax.transData.transform([(p["strike"], p["price"]) for p in hover_points])
        best_idx, best_dist = None, None
        for idx, (px, py) in enumerate(xy_pixels):
            dist = (px - event.x) ** 2 + (py - event.y) ** 2
            if best_dist is None or dist < best_dist:
                best_dist, best_idx = dist, idx

        if best_dist is not None and best_dist <= HOVER_RADIUS_PX ** 2:
            point = hover_points[best_idx]
            annot.xy = (point["strike"], point["price"])
            annot.set_text(point["text"])
            annot.set_visible(True)
        else:
            annot.set_visible(False)
        fig.canvas.draw_idle()

    fig.canvas.mpl_connect("motion_notify_event", on_hover)

    if len(expirations) == 1:
        exp_label = expirations[0]
    else:
        exp_label = f"{len(expirations)}exp_{expirations[0]}_to_{expirations[-1]}"

    scale_suffix = "_log" if args.log_scale else ""

    out_png = f"{ticker}_{exp_label}_{option_type}_{price_type}s{scale_suffix}.png"
    fig.savefig(out_png, dpi=150)
    print(f"\nSaved chart to {out_png}")

    out_csv = f"{ticker}_{exp_label}_{option_type}_{price_type}s{scale_suffix}.csv"
    df.to_csv(out_csv, index=False)
    print(f"Saved data to {out_csv}")

    plt.show()


if __name__ == "__main__":
    main()
