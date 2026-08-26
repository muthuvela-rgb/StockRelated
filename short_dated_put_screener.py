"""
Short-Dated Put Screener — Top 10 by Annualized Return
-----------------------------------------------------------------------------
Scans a universe of stocks/ETFs and reports the TOP 10 put options ranked by
annualized return, subject to these filters:

    * Expiration within the next N days (default 15) from when the script runs
    * Bid premium strictly greater than --min-premium (default $2.00)
    * Moneyness % strictly less than --max-moneyness (user specified, required)
    * Underlying market cap strictly greater than --min-market-cap (default $5B)

"Moneyness %" here is strike / current_price * 100. For puts, a LOWER
moneyness means the strike is further below the current price (further
out-of-the-money). So --max-moneyness 90 keeps only strikes below 90% of the
current price, i.e. at least 10% OTM.

Requires: yfinance, pandas
    pip install yfinance pandas

Run:
    python short_dated_put_screener.py --max-moneyness 90
    python short_dated_put_screener.py --max-moneyness 85 --days 15
    python short_dated_put_screener.py -t QQQ,AAPL,MSFT --max-moneyness 95
    python short_dated_put_screener.py --max-moneyness 90 --min-premium 3 --top 20
    python short_dated_put_screener.py --max-moneyness 90 --min-market-cap 10e9

By default (no -t) the screen runs over the QQQ / Nasdaq-100 constituents
bundled in this script (--universe qqq). The market-cap > $5B filter is still
applied on top, so lower-cap constituents are dropped automatically.

Options:
    -t, --ticker        Explicit universe of ticker symbols to scan. Comma-
                         or space-separated. Overrides --universe. NOTE: the
                         screen is only applied to the tickers you give it (or
                         the --universe list) — the script does not discover
                         every $5B+ name in the market on its own.
    --universe          Named universe to scan when -t is omitted. Currently
                         "qqq" (default): the ~100 Nasdaq-100 / QQQ
                         constituents bundled in this script as a snapshot
                         (membership drifts over time; refresh periodically).
    --max-moneyness     REQUIRED. Keep only strikes whose moneyness
                         (strike/price*100) is strictly less than this. E.g.
                         90 = at least 10% out-of-the-money.
    --days              Only include expirations within this many days from
                         today (default: 15).
    --min-premium       Minimum bid premium, exclusive (default: 2.0).
    --min-market-cap    Minimum underlying market cap in dollars, exclusive
                         (default: 5e9 = $5 billion). Accepts scientific
                         notation like 5e9 or plain 5000000000.
    --top               How many rows to report (default: 10).
    --no-margin         Rank by cash-secured annualized return (premium /
                         strike) instead of the portfolio-margin approximation.
    --margin-shock-pct  Downside stress % for the margin approximation
                         (default: 15).
    --margin-floor-pct  Notional floor as % of underlying price (default: 5).
    --margin-premium-buffer-pct  Extra % buffer above the premium floor
                         (default: 0). See annualized-return notes below.
    --output            CSV filename for the full (pre-top-N) filtered set
                         (default: short_dated_put_screen.csv).

Annualized return:
        annualized_return = (premium / capital_basis) * (365 / DTE) * 100
    where capital_basis is, by default, an approximated portfolio-margin
    requirement for a short put (stress the price down --margin-shock-pct%,
    take the intrinsic loss net of premium, floored at the GREATER of a
    notional %-of-price floor and the option's own premium — since a short
    option's requirement can never be less than the cost to close it — plus
    an optional calibration buffer). --no-margin uses the full strike
    (cash-secured) instead. This is a simplified linear annualization for
    screening/comparison; it is NOT a broker-exact margin figure and does not
    account for assignment, dividends, taxes, IV changes, or fees.

    This is data retrieval / analysis only — not investment advice.
"""

import argparse
import sys
from datetime import datetime, timedelta

import pandas as pd

try:
    import yfinance as yf
except ImportError:
    sys.exit("Missing dependency. Install with:  pip install yfinance pandas")


DEFAULT_TICKERS = "SPCX,MU,SNDK,ALAB,NVDA,SKHY,META,TSLA,QQQ"

# QQQ (Invesco QQQ Trust / Nasdaq-100) equity constituents, snapshot as of
# 2026-08-19 (source: public QQQ holdings listing). Non-equity lines from the
# ETF (cash, index futures, collateral) are excluded. Nasdaq-100 membership is
# reconstituted annually and rebalanced quarterly, so this list WILL drift over
# time — refresh it periodically if you need it current. GOOGL and GOOG are
# both included (Alphabet has two share classes in the basket).
QQQ_CONSTITUENTS = [
    "NVDA", "AAPL", "MSFT", "MU", "AMZN", "AMD", "GOOGL", "GOOG", "TSLA", "AVGO",
    "META", "WMT", "INTC", "CSCO", "COST", "PLTR", "AMAT", "LRCX", "NFLX", "PANW",
    "SPCX", "KLAC", "TXN", "AMGN", "SNDK", "LIN", "MRVL", "CRWD", "TMUS", "PEP",
    "STX", "GILD", "ADI", "SHOP", "QCOM", "BKNG", "ASML", "WDC", "ISRG", "VRTX",
    "SBUX", "FTNT", "ADP", "ADBE", "ARM", "CEG", "INTU", "MELI", "APP", "MAR",
    "CMCSA", "CSX", "MNST", "DASH", "CDNS", "REGN", "MDLZ", "CTAS", "ABNB", "DDOG",
    "SNPS", "ROST", "ORLY", "WBD", "HON", "AEP", "PCAR", "LITE", "BKR", "MPWR",
    "PDD", "TER", "FAST", "FANG", "NXPI", "PYPL", "HONA", "ADSK", "AXON", "XEL",
    "ALAB", "NBIS", "CCEP", "FER", "EXC", "IDXX", "PAYX", "TTWO", "RKLB", "ODFL",
    "KDP", "MCHP", "ROP", "CRWV", "TRI", "WDAY", "DXCM", "MSTR", "GEHC", "ALNY",
    "CPRT", "KHC",
]

# Named universes selectable via --universe (see build_universe()).
UNIVERSES = {
    "qqq": QQQ_CONSTITUENTS,
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Screen short-dated puts and report the top N by annualized return."
    )
    parser.add_argument("-t", "--ticker", type=str, nargs="+", default=None,
                         help="Explicit universe of tickers (comma or space separated). "
                              "Overrides --universe when given.")
    parser.add_argument("--universe", type=str, default="qqq",
                         choices=sorted(UNIVERSES.keys()),
                         help="Named ticker universe to scan when -t is not given "
                              "(default: qqq = the ~100 Nasdaq-100 / QQQ constituents bundled in "
                              "this script). Ignored if -t is provided.")
    parser.add_argument("--max-moneyness", type=float, required=True,
                         help="REQUIRED. Keep strikes with moneyness (strike/price*100) strictly "
                              "less than this. E.g. 90 = at least 10%% OTM.")
    parser.add_argument("--days", type=int, default=15,
                         help="Only include expirations within this many days from today (default: 15).")
    parser.add_argument("--min-premium", type=float, default=2.0,
                         help="Minimum bid premium, exclusive (default: 2.0).")
    parser.add_argument("--min-market-cap", type=float, default=5e9,
                         help="Minimum market cap in dollars, exclusive (default: 5e9 = $5B).")
    parser.add_argument("--top", type=int, default=10,
                         help="How many rows to report (default: 10).")
    parser.add_argument("--no-margin", action="store_true",
                         help="Rank by cash-secured annualized return instead of margin approximation.")
    parser.add_argument("--margin-shock-pct", type=float, default=15.0,
                         help="Downside stress %% for the margin approximation (default: 15).")
    parser.add_argument("--margin-floor-pct", type=float, default=5.0,
                         help="Notional floor as %% of underlying price (default: 5).")
    parser.add_argument("--margin-floor", type=float, default=0.375,
                         help="Flat per-share floor in dollars (default: 0.375).")
    parser.add_argument("--margin-premium-buffer-pct", type=float, default=0.0,
                         help="Extra %% buffer above the premium floor (default: 0).")
    parser.add_argument("--output", type=str, default="short_dated_put_screen.csv",
                         help="CSV filename for the full filtered set (default: short_dated_put_screen.csv).")
    return parser.parse_args()


def parse_ticker_list(raw_tickers):
    tickers = []
    for token in raw_tickers:
        for piece in token.split(","):
            piece = piece.strip().upper()
            if piece and piece not in tickers:
                tickers.append(piece)
    return tickers


def safe_num(val):
    return 0.0 if pd.isna(val) else float(val)


def get_current_price(ticker_obj):
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


def get_market_cap(ticker_obj):
    try:
        mc = ticker_obj.fast_info.get("market_cap")
        if mc:
            return float(mc)
    except Exception:
        pass
    try:
        mc = ticker_obj.info.get("marketCap")
        if mc:
            return float(mc)
    except Exception:
        pass
    return None


def format_market_cap(market_cap):
    if not market_cap:
        return "N/A"
    if market_cap >= 1e12:
        return f"${market_cap / 1e12:.2f}T"
    if market_cap >= 1e9:
        return f"${market_cap / 1e9:.2f}B"
    if market_cap >= 1e6:
        return f"${market_cap / 1e6:.2f}M"
    return f"${market_cap:,.0f}"


def estimate_portfolio_margin_requirement(current_price, strike, premium, shock_pct,
                                            floor_per_share, floor_pct_of_price,
                                            premium_buffer_pct=0.0):
    """
    Approximate per-share portfolio-margin requirement for a short put:
    stress price down shock_pct%, take intrinsic loss net of premium, then
    floor at the GREATER of (a) a notional floor = max(flat $/share, % of
    price) and (b) the option's own premium (+ optional buffer), since a
    short option can never require less capital than the cost to close it.
    """
    stressed_price = current_price * (1 - shock_pct / 100)
    stressed_loss = max(strike - stressed_price, 0)
    net_requirement = max(stressed_loss - premium, 0)
    notional_floor = max(floor_per_share, floor_pct_of_price / 100 * current_price)
    premium_floor = premium * (1 + premium_buffer_pct / 100)
    floor = max(notional_floor, premium_floor)
    return max(net_requirement, floor)


def get_expirations_within_days(ticker_obj, days_ahead):
    today = datetime.today().date()
    cutoff = today + timedelta(days=days_ahead)
    try:
        all_exps = ticker_obj.options
    except Exception:
        return []
    kept = []
    for e in all_exps:
        try:
            d = datetime.strptime(e, "%Y-%m-%d").date()
        except ValueError:
            continue
        if today <= d <= cutoff:
            kept.append(e)
    return kept


def main():
    args = parse_args()
    if args.ticker is not None:
        tickers = parse_ticker_list(args.ticker)
        universe_label = "custom (-t)"
    else:
        tickers = parse_ticker_list(UNIVERSES[args.universe])
        universe_label = f"{args.universe} universe"
    if not tickers:
        sys.exit("No valid tickers provided.")

    today = datetime.today().date()
    print(f"Screening {len(tickers)} ticker(s) from {universe_label}: {', '.join(tickers)}")
    print(f"Filters: expiration <= {args.days} days out | bid > ${args.min_premium:g} | "
          f"moneyness < {args.max_moneyness:g}% | market cap > {format_market_cap(args.min_market_cap)}\n")

    records = []
    for ticker in tickers:
        tk = yf.Ticker(ticker)

        market_cap = get_market_cap(tk)
        if market_cap is None:
            print(f"  {ticker}: market cap unavailable — skipping.")
            continue
        if market_cap <= args.min_market_cap:
            print(f"  {ticker}: market cap {format_market_cap(market_cap)} "
                  f"<= {format_market_cap(args.min_market_cap)} — filtered out.")
            continue

        current_price = get_current_price(tk)
        if current_price is None:
            print(f"  {ticker}: price unavailable — skipping.")
            continue

        expirations = get_expirations_within_days(tk, args.days)
        if not expirations:
            print(f"  {ticker}: no expirations within {args.days} days — skipping.")
            continue

        moneyness_price_cap = current_price * args.max_moneyness / 100
        kept_here = 0
        for exp in expirations:
            exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
            dte = (exp_date - today).days
            if dte <= 0:
                continue
            try:
                chain = tk.option_chain(exp)
            except Exception as e:
                print(f"  {ticker} {exp}: failed to fetch chain ({e})")
                continue
            puts = chain.puts
            if puts.empty:
                continue

            # moneyness < max  <=>  strike < price * max/100
            band = puts[puts["strike"] < moneyness_price_cap]
            for _, row in band.iterrows():
                strike = float(row["strike"])
                if strike <= 0:
                    continue
                bid = safe_num(row.get("bid"))
                if bid <= args.min_premium:
                    continue

                ask = safe_num(row.get("ask"))
                last = safe_num(row.get("lastPrice"))
                moneyness = strike / current_price * 100

                if args.no_margin:
                    capital_basis = strike
                else:
                    capital_basis = estimate_portfolio_margin_requirement(
                        current_price, strike, bid, args.margin_shock_pct,
                        args.margin_floor, args.margin_floor_pct, args.margin_premium_buffer_pct)

                annualized_return = (bid / capital_basis) * (365.0 / dte) * 100

                records.append({
                    "ticker": ticker,
                    "expiration": exp,
                    "days_to_expiration": dte,
                    "strike": strike,
                    "current_price": round(current_price, 2),
                    "moneyness_pct": round(moneyness, 2),
                    "bid": bid,
                    "ask": ask,
                    "last_price": last,
                    "market_cap": market_cap,
                    "capital_basis": round(capital_basis, 2),
                    "annualized_return_pct": round(annualized_return, 2),
                })
                kept_here += 1

        print(f"  {ticker}: market cap {format_market_cap(market_cap)}, price ${current_price:.2f}, "
              f"{len(expirations)} expiration(s) <= {args.days}d, {kept_here} strike(s) passed all filters")

    if not records:
        sys.exit("\nNo options matched all the filters. Try relaxing --max-moneyness, "
                  "--min-premium, --days, or --min-market-cap.")

    df = pd.DataFrame(records).sort_values("annualized_return_pct", ascending=False).reset_index(drop=True)
    df.to_csv(args.output, index=False)

    basis = "cash-secured (full strike)" if args.no_margin else \
            f"~portfolio margin (approx., {args.margin_shock_pct:g}% stress)"
    print(f"\n{'='*70}")
    print(f"{len(df)} option(s) passed all filters. Capital basis for return: {basis}")
    print(f"Full filtered set saved to {args.output}")
    print(f"{'='*70}")
    print(f"\nTOP {min(args.top, len(df))} SHORT-DATED PUTS BY ANNUALIZED RETURN:")
    top = df.head(args.top).copy()
    top["market_cap"] = top["market_cap"].apply(format_market_cap)
    print(top[["ticker", "expiration", "days_to_expiration", "strike", "current_price",
               "moneyness_pct", "bid", "ask", "capital_basis", "annualized_return_pct",
               "market_cap"]].to_string(index=False, float_format=lambda x: f"{x:.2f}"))


if __name__ == "__main__":
    main()
