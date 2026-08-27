"""
Stock Options Toolkit — put annualized-return scanner, technicals, and ETF
universe expansion (multi-ticker, portfolio-margin aware)
-----------------------------------------------------------------------------
By default, for one or more stocks/ETFs, pulls every option expiration whose days-to-
expiration falls within a configurable [--min-days, --max-days] window
(default 0-365 days out), and for each expiration, pulls every PUT strike within
a percentage band of the current stock price (or one specific strike, with
--strike). For every (ticker, expiration, strike) row, computes the
annualized return implied by the bid premium (what you'd receive selling the
put) and the ask premium (what you'd pay buying it), using an approximated
PORTFOLIO MARGIN capital requirement by default (see below) rather than the
full cash-secured-put strike. When multiple tickers are given, results are
combined and the top rows across ALL tickers are printed, sorted by
annualized bid return.

DEFAULT WATCHLIST: if -t/--ticker is omitted, the script scans a persisted
default watchlist stored in watchlist.json (created next to this script on
first run, seeded with SPCX, MU, SNDK, ALAB, NVDA, SKHY, META, TSLA, QQQ).
Use --add-ticker / --remove-ticker to edit that persisted list (saved for
all future runs), or --list-tickers to view it, without running a scan.

TECHNICALS-ONLY MODE: pass --technicals to skip the put-option scan
entirely and just print technicals for the requested ticker(s) — see
--technicals below and the "What it does" section.

UNIVERSE MODE: pass --universe ETF_TICKER to use that ETF's full component
holdings as the ticker list instead of -t/--ticker or the default
watchlist (e.g. --universe SPY scans every S&P 500 constituent). Currently
supports QQQ (via Invesco's own holdings API) and State Street SPDR ETFs
(SPY, DIA, MDY, the SPDR sector funds, ...) — see fetch_universe_tickers()
/ --universe below for why it isn't broader yet.

Requires: yfinance, pandas
    pip install yfinance pandas

Optional (for charts): matplotlib
    pip install matplotlib

Optional (for --universe): requests, openpyxl
    pip install requests openpyxl

Optional (for interactive hover tooltips showing expiry/strike/premium on
each plotted point): mplcursors
    pip install mplcursors
Hover only works with an interactive matplotlib backend (i.e. running the
script locally with plt.show() popping up a window) — it has no effect on
the saved PNG files themselves, which are static images.

Run:
    python stock_options_toolkit.py
    python stock_options_toolkit.py --ticker QQQ
    python stock_options_toolkit.py --ticker QQQ,AAPL,MSFT,NVDA
    python stock_options_toolkit.py -t QQQ AAPL MSFT --top 20
    python stock_options_toolkit.py -t AAPL --max-days 180
    python stock_options_toolkit.py -t AAPL --min-days 30 --max-days 90
    python stock_options_toolkit.py -t QQQ --pct-low 50 --pct-high 90
    python stock_options_toolkit.py -t QQQ --strike 580
    python stock_options_toolkit.py -t QQQ,AAPL --no-plot
    python stock_options_toolkit.py -t QQQ --output my_scan.csv
    python stock_options_toolkit.py -t QQQ --no-margin
    python stock_options_toolkit.py -t QQQ --margin-shock-pct 10
    python stock_options_toolkit.py -t QQQ --margin-floor-pct 7.5
    python stock_options_toolkit.py --add-ticker AAPL,GOOGL
    python stock_options_toolkit.py --remove-ticker SPCX
    python stock_options_toolkit.py --list-tickers
    python stock_options_toolkit.py --technicals -t AAPL MSFT
    python stock_options_toolkit.py --technicals rsi bollinger -t QQQ
    python stock_options_toolkit.py --technicals price,analyst-target
    python stock_options_toolkit.py --universe SPY --top 20
    python stock_options_toolkit.py --universe XLK --technicals rsi

Options:
    -t, --ticker     One or more stock/ETF ticker symbols. Accepts
                      comma-separated ("QQQ,AAPL,MSFT") or space-separated
                      ("-t QQQ AAPL MSFT") forms. If omitted entirely, scans
                      the persisted default watchlist (see --list-tickers).
                      Ignored if --universe is given.
    --universe       Use an ETF's full component holdings as the ticker
                      list instead of -t/--ticker or the default watchlist
                      (e.g. --universe SPY scans every S&P 500
                      constituent). Fetches the live holdings list from
                      the ETF provider's public API/spreadsheet — no API
                      key. Currently supports QQQ (via Invesco's own
                      holdings API) and State Street SPDR ETFs (SPY, DIA,
                      MDY, the SPDR sector funds
                      XLK/XLF/XLE/XLV/XLY/XLP/XLI/XLB/XLU/XLRE/XLC, and
                      similar); other providers/funds (iShares, Vanguard,
                      other Invesco funds, ...) don't publish a similarly
                      simple/stable download, and exit with a clear error
                      rather than silently falling back to a partial
                      list. Overrides -t/--ticker.
    --add-ticker     Add one or more tickers to the persisted default
                      watchlist (comma or space separated), save it, then
                      exit WITHOUT scanning. Combine with --remove-ticker to
                      swap tickers in one call.
    --remove-ticker  Remove one or more tickers from the persisted default
                      watchlist, save it, then exit WITHOUT scanning.
    --list-tickers   Print the current persisted default watchlist and exit
                      WITHOUT scanning.
    --technicals     Technicals-only mode: skip the put-option scan
                      entirely and print ONLY technicals for the requested
                      ticker(s) (-t/--ticker, or the default watchlist if
                      omitted), then exit. Optionally list which fields to
                      include (comma or space separated) from: price,
                      52w-range, analyst-target, ath, market-cap, rsi,
                      bollinger. Default when no fields are given: all of
                      them, always printed in that fixed order regardless
                      of the order given on the CLI.
    --min-days       Minimum days to expiration to include (default: 0, i.e.
                      no lower bound beyond excluding already-expired
                      contracts).
    --max-days       Maximum days to expiration to include (default: 365).
    --strike         Look at ONE specific strike price across all
                      expirations, instead of scanning a band of strikes.
                      Applies the same strike to every ticker given, each
                      snapped to its own nearest actually-listed strike per
                      expiration. Overrides --pct-low/--pct-high.
    --pct-low        Lower bound of the strike band, as % of current price
                      (default: 30, i.e. strikes down to 30% of spot).
                      Ignored if --strike is given.
    --pct-high       Upper bound of the strike band, as % of current price
                      (default: 100, i.e. strikes up to the current price).
                      Ignored if --strike is given.
    --output         Output CSV filename for the COMBINED result across all
                      tickers (default: combined_put_annualized_returns.csv,
                      or {ticker}_put_annualized_returns.csv for a single
                      ticker). Per-ticker CSVs/charts are always saved too,
                      individually named.
    --no-plot        Skip generating chart PNGs (heatmap in band mode, line
                      chart in --strike mode) for every ticker
    --top            How many top rows (by annualized bid return) to print
                      — both per-ticker and in the final combined ranking
                      across all tickers (default: 20)
    --no-fallback    Disable the lastPrice fallback (see below) — use raw
                      bid/ask of 0 as-is instead.
    --no-margin      Use full cash-secured-put capital (the strike price) as
                      the basis for annualized returns instead of the
                      portfolio-margin approximation (see below).
    --margin-shock-pct  Downside stress-test %% move used to approximate the
                      portfolio margin requirement (default: 15, the
                      standard minimum for individual stocks/ETFs/options).
    --margin-floor   Minimum per-share margin floor in dollars (default:
                      0.375, i.e. $37.50/contract).

What --technicals does (instead of the numbered flow below):
    For each requested ticker, fetches only the requested fields and prints
    them in one block, then moves to the next ticker. After every ticker is
    processed, prints ONE CONSOLIDATED TABLE with every successfully-
    fetched ticker as a row (multi-value fields like 52w-range split into
    separate columns, e.g. "52W High"/"52W Low"). When the rsi field is
    included, that table is sorted ascending by RSI (missing RSI values
    sort last); otherwise rows stay in the order the tickers were given.
    No option chain is pulled, no CSV or chart is saved, and none of the
    annualized-return/margin machinery below runs. A single bad/delisted
    ticker is skipped with a warning rather than stopping the run, same as
    normal scan mode.
    Fields, and where each comes from:
        price            current price (fast_info / .info / recent history)
        52w-range        52-week high and low
        analyst-target   mean analyst price target + number of analysts
                         covering the stock, from Yahoo's financialData
        ath              all-time high (max daily High over full history)
        market-cap       market cap
        rsi              14-day RSI over ~3 months of daily closes
        bollinger        Bollinger Bands(20, 2) position: %B, zone (above
                         upper band / upper half / lower half / below
                         lower band), and an explicit below-lower-band
                         Yes/No
    Any field Yahoo doesn't provide is shown as N/A rather than guessed.

What it does, per ticker (normal scan mode):
    1. Fetches the current stock price.
    2. Either:
       (a) BAND MODE (default): computes the strike band
           [price * pct_low/100, price * pct_high/100]. Default is 30%-100%
           of spot, i.e. put strikes greater than 30% of the current price
           and less than the current price (below-spot, OTM/ATM puts).
       (b) SINGLE-STRIKE MODE (--strike given): uses one specific strike,
           snapped to the nearest listed strike per expiration.
    3. Pulls every listed expiration with days-to-expiration in
       [--min-days, --max-days].
    4. For each expiration, pulls the put chain and keeps either every
       strike inside the band (band mode) or just the nearest match to
       --strike (single-strike mode).
    5. For every (expiration, strike) row, computes:
           days_to_expiration (DTE) = calendar days from today to expiration
           annualized_return_bid = (bid / capital_basis_bid) * (365 / DTE) * 100
           annualized_return_ask = (ask / capital_basis_ask) * (365 / DTE) * 100
       This is premium collected (or paid) divided by the capital required to
       hold the position, scaled to a 365-day rate. It's a simple linear
       annualization (no compounding), the common convention for comparing
       option premiums of different durations at a glance.

       CAPITAL BASIS — portfolio margin (default) vs. cash-secured:
       By default, capital_basis is an APPROXIMATION of a portfolio-margin
       requirement for a short put, not the full strike. Real portfolio
       margin (used by E*TRADE and other brokers offering PM accounts) is
       calculated using the OCC's TIMS methodology: the underlying price is
       stressed across a range of hypothetical moves (a minimum of +/-15%
       for individual stocks, ETFs, and options, divided into 10 equidistant
       points), the position is repriced at each point using an options
       pricing model, and the requirement equals the largest loss found
       across those scenarios. This script approximates that: it stresses
       the price down by --margin-shock-pct (default 15%, matching the
       standard minimum) and computes the resulting intrinsic loss net of
       premium collected, since the downside move is what drives a short
       put's worst-case loss:
           capital_basis_bid = max(
               max(strike - current_price*(1 - shock%/100), 0) - bid,
               floor
           )
       (analogous for the ask side, using ask as the premium).

       THE FLOOR (fixed after a bug found via QQQ testing): there's a
       documented risk-based minimum of $0.375/share ($37.50/contract) for
       a short option — but using that flat number alone breaks down for
       higher-priced underlyings. For QQQ (~$690/share), a 15% stress only
       reaches ~$586, so EVERY strike below that — from 30% moneyness all
       the way to 85% moneyness — showed zero stressed intrinsic loss and
       collapsed to the exact same $0.375/share floor, regardless of how
       far OTM the strike actually was. That produced absurd, undifferentiated
       annualized returns in the thousands of percent for most of the
       scanned strike range. The floor is now the GREATER of --margin-floor
       (the flat $0.375/share minimum, still relevant for lower-priced
       stocks) and --margin-floor-pct (default 5% of the CURRENT underlying
       price), so it scales with the position's notional size the way real
       margin does. This fixed the QQQ example: strikes 29%-90% moneyness
       now show gradated ~13%-385% annualized returns instead of a flat
       ~1,200%-29,000% plateau. This omits the full 10-point/options-
       pricing-model detail (in particular it doesn't model implied-
       volatility changes) but captures the dominant driver — the downside
       price move plus a notional-scaled floor — which is a much more
       reasonable estimate for a quick screen. --no-margin reverts
       capital_basis to the full strike (the traditional cash-secured-put
       convention) if you'd rather compare on that basis instead.

       IMPORTANT CAVEATS:
       - This is NOT your broker's exact real-time number. Actual portfolio
         margin also factors in your account's other positions/hedges,
         concentration rules, implied-volatility stress, and firm-specific
         overlays that can be stricter than the regulatory minimum. Check
         E*TRADE's own margin calculator for the figure that actually
         applies to your account. The --margin-floor-pct default (5%) is a
         heuristic to keep the numbers sane across different underlying
         price levels, not a cited regulatory figure — adjust it if you have
         a better estimate for your broker/product.
         applies to your account.
       - Some broad-based index-tracking ETFs get a narrower stress range
         (commonly ~8-10%) at some brokers/products; QQQ's exact treatment
         can vary by broker. Lower --margin-shock-pct if you want a more
         optimistic estimate for those, or leave at 15% for the standard/
         conservative assumption used for individual stocks.
       - The CSV keeps BOTH figures for every row: annualized_return_*_pct
         (the primary column, using capital_basis) and
         annualized_return_*_pct_cash_secured (always the full-strike
         basis), so you can compare margin-based vs. cash-secured returns
         side by side regardless of which mode you ran.
       - Because margin capital is much smaller than the full strike,
         margin-based annualized returns are dramatically higher than
         cash-secured ones for the same trade — this reflects real
         leverage, and real leveraged risk, not a better trade.

       IMPORTANT — lastPrice fallback: Yahoo's free feed frequently reports
       bid=0 and/or ask=0 for thinly-traded or far out-of-the-money
       contracts, which would otherwise make the annualized return 0% even
       though the option clearly has some value (it last traded at a real
       price). By default, whenever bid is 0 (and/or ask is 0) but
       lastPrice > 0, the calculation substitutes lastPrice for that side
       instead of using the raw 0. The CSV includes bid_used_fallback and
       ask_used_fallback boolean columns so you can see exactly which rows
       were adjusted, and the console/chart flag fallback rows too. Use
       --no-fallback to disable this and see the raw (possibly 0%)
       annualized returns instead.
    6. Saves that ticker's result set to its own CSV and, unless --no-plot
       is passed, renders its own chart with TWO SIDE-BY-SIDE PANELS by
       default — one using the portfolio-margin capital basis, one using
       the full cash-secured basis — so you can compare both at a glance
       regardless of which one --no-margin selected as "primary" for
       ranking. In band mode this is two heatmaps (expiration x strike);
       in single-strike mode it's two line charts (bid/ask vs expiration).
    7. Prints that ticker's top rows by annualized bid return to the console.
    8. Prints that ticker's snapshot: market cap, 52-week high/low, an
       approximate current implied volatility (from the nearest-term
       expiration's at-the-money put), current 14-day RSI, and the next
       earnings date. Any field Yahoo doesn't provide is shown as N/A rather
       than guessed.

After all tickers are processed:
    9. Combines every ticker's rows into one table, saves it to the combined
       output CSV, and prints the top --top rows (default 20) by annualized
       BID return across ALL tickers together — e.g. to answer "what are
       the best cash-secured-put yields across my whole watchlist right now."
    10. Prints one final consolidated summary table — one row per ticker —
        with current price, market cap, 52-week high/low, approximate ATM
        IV, current 14-day RSI, and next earnings date, so you can eyeball
        every ticker's fundamentals side by side at a glance.
    11. Renders one final combined chart (unless --no-plot) with two
        side-by-side scatter panels — portfolio-margin basis and
        cash-secured basis — plotting every row from the combined CSV,
        moneyness on the x-axis, annualized bid return on the y-axis,
        color-coded by ticker.

Notes:
    - Bid/ask reflect live market data at the time you run the script.
    - Annualized return here is a simplified estimate (linear scaling), not
      a precise IRR/XIRR calculation, and does not account for early
      assignment, dividends, taxes, or transaction costs.
    - Deep ITM or far OTM strikes, and very short-dated expirations, can
      produce misleadingly large annualized numbers from tiny premiums
      divided by very few days — sanity-check anything that looks extreme.
    - A single bad/delisted ticker won't stop the run — it's skipped with a
      warning and the rest continue.
    - This is data retrieval / analysis only — not investment advice.
"""

import argparse
import io
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

try:
    import requests
except ImportError:
    requests = None  # only required for --universe; rest of the script doesn't need it

try:
    import yfinance as yf
except ImportError:
    yf = None  # only required for actual scans; --list-tickers etc. don't need it

try:
    from stock_fall_detector.technicals import compute_bollinger
except ImportError:
    compute_bollinger = None  # only required for --technicals bollinger; rest of the script doesn't need it


# Seed watchlist used only the very first time the script runs (before the
# persisted watchlist file exists). After that, WATCHLIST_FILE is the single
# source of truth and --add-ticker/--remove-ticker modify it directly.
DEFAULT_TICKERS_SEED = ["SPCX", "MU", "SNDK", "ALAB", "NVDA", "SKHY", "META", "TSLA", "QQQ"]
WATCHLIST_FILE = Path(__file__).resolve().parent / "watchlist.json"

# Fields selectable via --technicals, in the fixed order they're always
# printed regardless of the order given on the CLI.
TECHNICALS_FIELD_ORDER = ["price", "52w-range", "analyst-target", "ath", "market-cap", "rsi", "bollinger"]
TECHNICALS_FIELD_LABELS = {
    "price": "Current Price",
    "52w-range": "52-Week High/Low",
    "analyst-target": "Mean Analyst Price Target",
    "ath": "All-Time High",
    "market-cap": "Market Cap",
    "rsi": "RSI (14d)",
    "bollinger": "Bollinger Band Position",
}


def load_default_tickers():
    """Load the persisted default watchlist, seeding the file on first run."""
    if WATCHLIST_FILE.exists():
        try:
            with open(WATCHLIST_FILE) as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                return [str(t).strip().upper() for t in data]
        except Exception:
            pass  # fall through to seed defaults if the file is missing/corrupt
    seed = list(DEFAULT_TICKERS_SEED)
    save_default_tickers(seed)
    return seed


def save_default_tickers(tickers):
    """Persist the default watchlist to WATCHLIST_FILE as JSON."""
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(tickers, f, indent=2)


def try_import_mplcursors():
    """Import mplcursors if available; return the module or None (never raises)."""
    try:
        import mplcursors
        return mplcursors
    except ImportError:
        return None


def attach_point_hover(mplcursors_mod, artist, df_subset, premium_col, value_col, value_label):
    """
    Attach a hover tooltip to a scatter/line artist showing Expiry, Strike,
    and Premium (plus the plotted value) for whichever point the cursor is
    over. df_subset must be in the same row order as the data passed to the
    artist (positional index alignment). No-ops silently if mplcursors_mod
    is None (not installed) or df_subset is empty.
    """
    if mplcursors_mod is None or df_subset.empty:
        return
    df_subset = df_subset.reset_index(drop=True)
    cursor = mplcursors_mod.cursor(artist, hover=True)

    @cursor.connect("add")
    def _(sel):
        idx = sel.index
        if isinstance(idx, tuple):
            idx = idx[0]
        idx = int(round(idx))
        idx = max(0, min(idx, len(df_subset) - 1))
        row = df_subset.iloc[idx]
        ticker_line = f"Ticker: {row['ticker']}\n" if "ticker" in df_subset.columns else ""
        sel.annotation.set_text(
            f"{ticker_line}"
            f"Expiry: {row['expiration']}\n"
            f"Strike: {row['strike']:g}\n"
            f"Premium: ${row[premium_col]:.2f}\n"
            f"{value_label}: {row[value_col]:.2f}%"
        )
        bbox = sel.annotation.get_bbox_patch()
        if bbox is not None:
            bbox.set(fc="lightyellow", alpha=0.95)


def attach_heatmap_hover(fig, ax, pivot_value, pivot_premium, value_label):
    """
    Attach a custom hover tooltip to a heatmap (imshow) axis, showing
    Expiry, Strike, the plotted value, and the actual premium for whichever
    cell the cursor is over. Pure matplotlib (no extra dependency) — only
    becomes visible with an interactive backend (plt.show()); has no effect
    on saved static PNGs.
    """
    annot = ax.annotate(
        "", xy=(0, 0), xytext=(15, 15), textcoords="offset points",
        bbox=dict(boxstyle="round", fc="lightyellow", ec="black", alpha=0.95),
        arrowprops=dict(arrowstyle="->"),
        fontsize=9, zorder=10,
    )
    annot.set_visible(False)

    n_rows, n_cols = pivot_value.shape

    def on_move(event):
        if event.inaxes != ax or event.xdata is None or event.ydata is None:
            if annot.get_visible():
                annot.set_visible(False)
                fig.canvas.draw_idle()
            return

        col = int(round(event.xdata))
        row = int(round(event.ydata))
        if not (0 <= col < n_cols and 0 <= row < n_rows):
            if annot.get_visible():
                annot.set_visible(False)
                fig.canvas.draw_idle()
            return

        value = pivot_value.values[row, col]
        if pd.isna(value):
            if annot.get_visible():
                annot.set_visible(False)
                fig.canvas.draw_idle()
            return

        expiration = pivot_value.columns[col]
        strike = pivot_value.index[row]
        text = f"Expiry: {expiration}\nStrike: {strike:g}\n{value_label}: {value:.2f}%"
        if pivot_premium is not None:
            premium = pivot_premium.values[row, col]
            if pd.notna(premium):
                text += f"\nPremium: ${premium:.2f}"

        annot.xy = (col, row)
        annot.set_text(text)
        annot.set_visible(True)
        fig.canvas.draw_idle()

    fig.canvas.mpl_connect("motion_notify_event", on_move)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Scan put option chains across expirations and strikes for one or more "
                    "tickers, computing annualized returns from bid/ask premiums."
    )
    parser.add_argument("-t", "--ticker", type=str, nargs="+", default=None,
                         help="One or more stock/ETF ticker symbols. Comma-separated "
                              "(\"QQQ,AAPL,MSFT\") or space-separated (\"QQQ AAPL MSFT\"). "
                              "If omitted, scans the persisted default watchlist "
                              "(see --list-tickers, --add-ticker, --remove-ticker). Ignored "
                              "if --universe is given.")
    parser.add_argument("--universe", type=str, default=None, metavar="ETF_TICKER",
                         help="Use an ETF's full component holdings as the ticker list instead "
                              "of -t/--ticker or the default watchlist. Fetches the live "
                              "holdings list for ETF_TICKER (e.g. SPY, XLK, XLF, DIA, MDY) from "
                              "its provider's public holdings spreadsheet. Currently only State "
                              "Street SPDR ETFs are supported (see docstring); other providers "
                              "exit with a clear error rather than silently returning a partial "
                              "list. Overrides -t/--ticker.")
    parser.add_argument("--add-ticker", type=str, nargs="+", default=None,
                         help="Add one or more tickers to the persisted default watchlist "
                              "(comma or space separated), save it, then exit without scanning.")
    parser.add_argument("--remove-ticker", type=str, nargs="+", default=None,
                         help="Remove one or more tickers from the persisted default watchlist, "
                              "save it, then exit without scanning.")
    parser.add_argument("--list-tickers", action="store_true",
                         help="Print the current persisted default watchlist and exit without "
                              "scanning.")
    parser.add_argument("--technicals", type=str, nargs="*", default=None, metavar="FIELD",
                         help="Technicals-only mode: skip the put-option scan entirely and print "
                              "only technicals for the requested ticker(s) (-t/--ticker, or the "
                              "default watchlist if omitted), then exit. Optionally list which "
                              "fields to include (comma or space separated) from: " +
                              ", ".join(TECHNICALS_FIELD_ORDER) +
                              ". Default when no fields are given: all of them, in that order.")
    parser.add_argument("--min-days", type=int, default=0,
                         help="Minimum days to expiration to include (default: 0, i.e. no "
                              "lower bound beyond excluding already-expired contracts).")
    parser.add_argument("--max-days", type=int, default=365,
                         help="Maximum days to expiration to include (default: 365).")
    parser.add_argument("--strike", type=float, default=None,
                         help="Look at one specific strike price across all expirations "
                              "(snapped to the nearest listed strike per expiration), instead "
                              "of scanning a band of strikes. Overrides --pct-low/--pct-high.")
    parser.add_argument("--pct-low", type=float, default=30.0,
                         help="Lower bound of strike band, as %% of current price (default: 30)")
    parser.add_argument("--pct-high", type=float, default=100.0,
                         help="Upper bound of strike band, as %% of current price (default: 100)")
    parser.add_argument("--output", type=str, default=None,
                         help="Output CSV filename for the COMBINED result across all tickers "
                              "(default: combined_put_annualized_returns.csv, or "
                              "{ticker}_put_annualized_returns.csv for a single ticker)")
    parser.add_argument("--no-plot", action="store_true",
                         help="Skip generating chart PNGs for every ticker")
    parser.add_argument("--top", type=int, default=20,
                         help="How many top rows (by annualized bid return) to print, both "
                              "per-ticker and in the final combined ranking (default: 20)")
    parser.add_argument("--no-fallback", action="store_true",
                         help="Disable the lastPrice fallback when bid/ask is 0 (see docstring). "
                              "Uses raw 0 values instead.")
    parser.add_argument("--no-margin", action="store_true",
                         help="Use full cash-secured-put capital (the strike price) as the basis "
                              "for annualized returns instead of the portfolio-margin approximation "
                              "(see docstring). This restores the original calculation method.")
    parser.add_argument("--margin-shock-pct", type=float, default=15.0,
                         help="Downside stress-test %% move used to approximate the portfolio "
                              "margin requirement for a short put (default: 15, the standard "
                              "minimum used for individual stocks/ETFs/options). Some broad-based "
                              "index-tracking ETFs get a narrower range (~8-10%%) at some brokers; "
                              "lower this if you want a more optimistic estimate for those.")
    parser.add_argument("--margin-floor", type=float, default=0.375,
                         help="Minimum per-share margin floor in dollars (default: 0.375, i.e. "
                              "$37.50/contract — the documented OCC risk-based minimum for a short "
                              "option contract). The final floor is the GREATER of this and "
                              "--margin-floor-pct, so it scales up for higher-priced underlyings.")
    parser.add_argument("--margin-floor-pct", type=float, default=5.0,
                         help="Minimum margin floor as a %% of the CURRENT underlying price "
                              "(default: 5.0). Fixes a flaw where the flat --margin-floor dollar "
                              "amount (designed for lower-priced stocks) collapses to an "
                              "unrealistically tiny requirement for higher-priced underlyings like "
                              "QQQ — every strike below the stress point would otherwise get the "
                              "exact same tiny floor regardless of how far OTM it is. The floor "
                              "used is whichever of --margin-floor or this is larger.")
    return parser.parse_args()


def parse_ticker_list(raw_tickers):
    """
    Flatten and clean the -t/--ticker argument into a deduplicated list of
    uppercase ticker symbols. Accepts a mix of comma-separated and
    space-separated tokens, e.g. ["QQQ,AAPL", "MSFT"] -> ["QQQ", "AAPL", "MSFT"].
    """
    tickers = []
    for token in raw_tickers:
        for piece in token.split(","):
            piece = piece.strip().upper()
            if piece and piece not in tickers:
                tickers.append(piece)
    return tickers


def parse_technicals_fields(raw_fields):
    """
    Validate and flatten the --technicals field arguments (comma or space
    separated, case-insensitive, "_"/"-" interchangeable) into a list using
    the fixed TECHNICALS_FIELD_ORDER, regardless of the order given on the
    CLI. Empty/None input (bare --technicals) means "all fields". Exits with
    a helpful error listing valid keys on an unrecognized field name.
    """
    if not raw_fields:
        return list(TECHNICALS_FIELD_ORDER)

    requested = set()
    for token in raw_fields:
        for piece in token.split(","):
            piece = piece.strip().lower().replace("_", "-")
            if not piece:
                continue
            if piece not in TECHNICALS_FIELD_LABELS:
                valid = ", ".join(TECHNICALS_FIELD_ORDER)
                sys.exit(f"Unknown --technicals field '{piece}'. Valid fields: {valid}")
            requested.add(piece)

    return [f for f in TECHNICALS_FIELD_ORDER if f in requested]


# --universe: base URL for State Street's public per-ETF daily holdings
# spreadsheet (no API key). {ticker} is the ETF's ticker, lowercased.
_SPDR_HOLDINGS_URL = (
    "https://www.ssga.com/us/en/intermediary/library-content/products/"
    "fund-data/etfs/us/holdings-daily-us-en-{ticker}.xlsx"
)
_TICKER_RE = r"^[A-Z]{1,5}(\.[A-Z])?$"  # real US equity ticker, e.g. AAPL, BF.B — rejects
                                        # internal identifiers some funds hold odd positions under


def fetch_spdr_holdings(etf_ticker):
    """
    Fetch the full equity holdings list for a State Street SPDR ETF from
    their public daily holdings spreadsheet (SPY, DIA, MDY, the SPDR
    sector funds, and similar) — no API key, no scraping library, just an
    XLSX download. Returns a deduplicated list of yfinance-style tickers
    ("." replaced with "-" for share classes, e.g. "BF.B" -> "BF-B"), or
    None if the ETF isn't an SPDR fund published this way, or the fetch/
    parse otherwise fails.
    """
    if requests is None:
        sys.exit("Missing dependency requests (needed for --universe). "
                  "Install with:  pip install requests")

    url = _SPDR_HOLDINGS_URL.format(ticker=etf_ticker.lower())
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    except Exception:
        return None

    content_type = resp.headers.get("content-type", "")
    if resp.status_code != 200 or "spreadsheet" not in content_type:
        return None  # 404, or an HTML page instead of the expected xlsx

    try:
        df = pd.read_excel(io.BytesIO(resp.content), header=4)
    except ImportError:
        sys.exit("Missing dependency openpyxl (needed for --universe to read the holdings "
                  "spreadsheet). Install with:  pip install openpyxl")
    except Exception:
        return None

    if "Ticker" not in df.columns:
        return None

    tickers = df["Ticker"].dropna().astype(str).str.strip()
    tickers = tickers[tickers.str.match(_TICKER_RE)]
    tickers = tickers.str.replace(".", "-", regex=False)
    result = tickers.drop_duplicates().tolist()
    return result or None


# --universe: Invesco's own public JSON API for QQQ's full holdings — the
# same endpoint that powers the "view all holdings" table on
# invesco.com/qqq-etf. Found by inspecting that page's HTML for the
# data-holding-api attribute on the all-holdings table (the top-10-only
# widget on the same page uses this URL PLUS "&loadType=initial", which is
# what caps it at 10 — omitting that param returns every holding).
# NOTE: this endpoint 500s for other Invesco tickers tried (QQQM, RSP,
# SPHQ) — it is NOT a general "any Invesco fund" endpoint, so this is
# intentionally QQQ-specific rather than generalized to a whole provider.
_INVESCO_QQQ_HOLDINGS_URL = (
    "https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/"
    "holdings/fund?idType=ticker&interval=monthly&productType=ETF"
)


def fetch_invesco_qqq_holdings():
    """
    Fetch QQQ's full holdings list from Invesco's own public JSON API — no
    API key. Keeps only common-stock lines (securityTypeCode == "COM"),
    dropping the index-future/cash/collateral lines the fund also reports
    (e.g. "NQU6" futures, "USD" cash, "CASH COLLATERAL"). Returns a
    deduplicated list of yfinance-style tickers, or None on failure.
    """
    if requests is None:
        sys.exit("Missing dependency requests (needed for --universe). "
                  "Install with:  pip install requests")

    try:
        resp = requests.get(_INVESCO_QQQ_HOLDINGS_URL, timeout=15,
                             headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception:
        return None

    tickers = []
    for h in data.get("holdings", []):
        if h.get("securityTypeCode") != "COM":
            continue
        ticker = h.get("ticker")
        if ticker and re.match(_TICKER_RE, ticker) and ticker not in tickers:
            tickers.append(ticker.replace(".", "-"))

    return tickers or None


def fetch_universe_tickers(etf_ticker):
    """
    Resolve --universe ETF_TICKER to its full list of component tickers.

    Supports:
      - QQQ specifically, via Invesco's own public holdings API
        (fetch_invesco_qqq_holdings()).
      - State Street SPDR equity ETFs (SPY, DIA, MDY, and the SPDR sector
        funds XLK/XLF/XLE/XLV/XLY/XLP/XLI/XLB/XLU/XLRE/XLC, among others),
        via fetch_spdr_holdings().
    Other providers/tickers (iShares, Vanguard, other Invesco funds, ...)
    don't publish a similarly simple/stable public download and aren't
    supported yet — this exits with a clear error rather than silently
    falling back to a partial (e.g. top-10-only) list.
    """
    if etf_ticker == "QQQ":
        tickers = fetch_invesco_qqq_holdings()
    else:
        tickers = fetch_spdr_holdings(etf_ticker)

    if not tickers:
        sys.exit(
            f"Could not fetch full holdings for '{etf_ticker}'. --universe currently "
            f"supports QQQ (via Invesco's own holdings API) and State Street SPDR ETFs "
            f"(e.g. SPY, DIA, MDY, XLK, XLF, XLE, XLV, XLY, XLP, XLI, XLB, XLU, XLRE, XLC) "
            f"via their public holdings spreadsheet. Other providers/funds (iShares, "
            f"Vanguard, other Invesco funds, ...) aren't supported. Pass explicit tickers "
            f"with -t/--ticker instead."
        )
    return tickers


def manage_watchlist(args):
    """
    Handle --add-ticker / --remove-ticker / --list-tickers: mutate the
    persisted default watchlist (WATCHLIST_FILE) as requested, print the
    result, and return. Does not run any market-data scan.
    """
    tickers = load_default_tickers()
    changed = False

    if args.remove_ticker:
        for t in parse_ticker_list(args.remove_ticker):
            if t in tickers:
                tickers.remove(t)
                changed = True
                print(f"Removed {t} from the default watchlist.")
            else:
                print(f"{t} was not in the default watchlist — nothing to remove.")

    if args.add_ticker:
        for t in parse_ticker_list(args.add_ticker):
            if t not in tickers:
                tickers.append(t)
                changed = True
                print(f"Added {t} to the default watchlist.")
            else:
                print(f"{t} is already in the default watchlist.")

    if changed:
        save_default_tickers(tickers)
        print(f"\nSaved updated default watchlist to {WATCHLIST_FILE}")

    print(f"\nCurrent default watchlist ({len(tickers)}): {', '.join(tickers)}")


def get_current_price(ticker_obj):
    """Fetch current/last stock price, trying a few yfinance sources in order."""
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
    sys.exit("Could not fetch the current stock price from Yahoo Finance. "
              "Check the ticker symbol or try again shortly.")


def get_expirations_within_range(ticker_obj, min_days_ahead=0, max_days_ahead=365):
    today = datetime.today().date()
    floor = today + timedelta(days=min_days_ahead)
    cutoff = today + timedelta(days=max_days_ahead)
    all_exps = ticker_obj.options
    return [e for e in all_exps if floor <= datetime.strptime(e, "%Y-%m-%d").date() <= cutoff]


def safe_num(val):
    return 0.0 if pd.isna(val) else float(val)


def find_nearest_put_row(puts_df, target_strike):
    """Return the put row whose strike is closest to target_strike, and whether it was an exact match."""
    if puts_df.empty:
        return None, False
    exact = puts_df[puts_df["strike"] == target_strike]
    if not exact.empty:
        return exact.iloc[0], True
    diffs = (puts_df["strike"] - target_strike).abs()
    return puts_df.loc[diffs.idxmin()], False


def estimate_portfolio_margin_requirement(current_price, strike, premium, shock_pct,
                                            floor_per_share, floor_pct_of_price):
    """
    Approximate the per-share portfolio-margin requirement for a SHORT put,
    following the OCC/TIMS-style methodology used by portfolio-margin brokers
    (including E*TRADE): stress the underlying price down by shock_pct%,
    value the resulting loss, and use that as the requirement (offset by the
    premium already collected). A floor is applied on top of that.

    This mirrors the real methodology's worst-case scenario for a short put
    (the largest loss occurs on the DOWNSIDE stress point, since a short put
    only loses value as the stock falls) rather than replicating the full
    10-point risk array with an options-pricing model — it uses intrinsic
    value at the stress point only, which is the dominant term for a
    short/naked put and a reasonable approximation for comparison purposes.
    It is NOT a substitute for your broker's actual real-time margin
    calculation, which also factors in implied volatility changes,
    concentration rules, and firm-specific overlays.

    FLOOR: real margin rules specify an absolute minimum per contract
    ($0.375/share, i.e. $37.50/contract) — but that flat number was designed
    for typical lower-priced individual stocks and is far too small relative
    to a higher-priced underlying (e.g. QQQ around $600-700/share): using
    intrinsic value alone, EVERY strike below the stress point collapses to
    that same tiny floor regardless of how far OTM it actually is, erasing
    any risk differentiation across most of a realistic strike band. To fix
    that, the floor here is the GREATER of the flat per-share minimum
    (floor_per_share) and a percentage of the current underlying price
    (floor_pct_of_price), so the floor scales with the position's notional
    size the way real margin requirements do.

    Returns the per-share dollar requirement (multiply by 100 for a
    per-contract dollar figure).
    """
    stressed_price = current_price * (1 - shock_pct / 100)
    stressed_loss = max(strike - stressed_price, 0)
    net_requirement = max(stressed_loss - premium, 0)
    floor = max(floor_per_share, floor_pct_of_price / 100 * current_price)
    return max(net_requirement, floor)


def get_market_cap(ticker_obj):
    """Fetch market cap, trying fast_info first, then the legacy .info dict."""
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


def get_52week_range(ticker_obj):
    """Fetch 52-week high/low, trying fast_info first, then .info, then computing from history."""
    try:
        hi = ticker_obj.fast_info.get("year_high")
        lo = ticker_obj.fast_info.get("year_low")
        if hi and lo:
            return float(hi), float(lo)
    except Exception:
        pass
    try:
        hi = ticker_obj.info.get("fiftyTwoWeekHigh")
        lo = ticker_obj.info.get("fiftyTwoWeekLow")
        if hi and lo:
            return float(hi), float(lo)
    except Exception:
        pass
    try:
        hist = ticker_obj.history(period="1y")
        if not hist.empty:
            return float(hist["High"].max()), float(hist["Low"].min())
    except Exception:
        pass
    return None, None


def compute_rsi(closes, period=14):
    """Standard Wilder RSI from a pandas Series of closing prices."""
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def get_current_rsi(ticker_obj, period=14):
    """Fetch ~3 months of daily closes and compute the latest RSI value."""
    try:
        hist = ticker_obj.history(period="3mo")
        if len(hist) < period + 1:
            return None
        rsi_series = compute_rsi(hist["Close"], period=period)
        val = rsi_series.iloc[-1]
        return float(val) if pd.notna(val) else None
    except Exception:
        return None


def get_atm_iv(ticker_obj, expirations, current_price):
    """
    Fetch implied volatility from the nearest-term expiration's put chain, at the
    strike closest to the current price (approximate at-the-money IV).
    """
    if not expirations:
        return None, None
    nearest_exp = expirations[0]
    try:
        chain = ticker_obj.option_chain(nearest_exp)
        puts = chain.puts
        if puts.empty or "impliedVolatility" not in puts.columns:
            return None, nearest_exp
        diffs = (puts["strike"] - current_price).abs()
        row = puts.loc[diffs.idxmin()]
        iv = row.get("impliedVolatility")
        return (float(iv) * 100 if pd.notna(iv) else None), nearest_exp
    except Exception:
        return None, nearest_exp


def get_next_earnings_date(ticker_obj):
    """Fetch the next upcoming earnings date, trying get_earnings_dates() then .calendar."""
    try:
        edates = ticker_obj.get_earnings_dates(limit=8)
        if edates is not None and not edates.empty:
            today = pd.Timestamp.now(tz=edates.index.tz) if edates.index.tz else pd.Timestamp.now()
            future = edates[edates.index >= today]
            if not future.empty:
                return future.index.min().strftime("%Y-%m-%d")
            return edates.index.max().strftime("%Y-%m-%d")  # most recent past, as fallback
    except Exception:
        pass
    try:
        cal = ticker_obj.calendar
        if isinstance(cal, dict):
            dates = cal.get("Earnings Date")
            if dates:
                d = dates[0] if isinstance(dates, list) else dates
                return pd.Timestamp(d).strftime("%Y-%m-%d")
        elif cal is not None and not cal.empty and "Earnings Date" in cal.index:
            d = cal.loc["Earnings Date"].iloc[0]
            return pd.Timestamp(d).strftime("%Y-%m-%d")
    except Exception:
        pass
    return None


def get_all_time_high(ticker_obj):
    """
    Fetch the all-time high price from the full available daily price
    history. Uses auto_adjust=False (raw traded prices) so this is
    consistent with the un-adjusted 52-week high/low and current price
    elsewhere in this file — yfinance's default dividend-adjustment can
    otherwise shrink recent historical highs just enough to come in BELOW
    the 52-week high, which shouldn't be possible.
    """
    try:
        hist = ticker_obj.history(period="max", auto_adjust=False)
        if not hist.empty:
            return float(hist["High"].max())
    except Exception:
        pass
    return None


def get_mean_analyst_target(ticker_obj):
    """Fetch the mean analyst price target and the number of analysts covering the stock."""
    try:
        info = ticker_obj.info
        target = info.get("targetMeanPrice")
        num_analysts = info.get("numberOfAnalystOpinions")
        if target:
            return float(target), (int(num_analysts) if num_analysts else None)
    except Exception:
        pass
    return None, None


def get_bollinger_position(ticker_obj):
    """Fetch ~3 months of daily closes and compute Bollinger Band(20, 2) position."""
    if compute_bollinger is None:
        return None
    try:
        hist = ticker_obj.history(period="3mo")
        closes = hist["Close"].tolist()
        return compute_bollinger(closes)
    except Exception:
        return None


def format_market_cap(market_cap):
    if not market_cap:
        return "N/A"
    if market_cap >= 1e12:
        return f"${market_cap / 1e12:.2f}T"
    elif market_cap >= 1e9:
        return f"${market_cap / 1e9:.2f}B"
    elif market_cap >= 1e6:
        return f"${market_cap / 1e6:.2f}M"
    return f"${market_cap:,.0f}"


def gather_snapshot(ticker_obj, ticker, current_price, expirations):
    """
    Fetch market cap, 52-week high/low, ATM IV, RSI, and next earnings date
    for one ticker. Returns a dict (never raises — missing fields are None).
    """
    market_cap = get_market_cap(ticker_obj)
    week_hi, week_lo = get_52week_range(ticker_obj)
    iv, iv_exp = get_atm_iv(ticker_obj, expirations, current_price)
    rsi = get_current_rsi(ticker_obj)
    next_earnings = get_next_earnings_date(ticker_obj)

    return {
        "ticker": ticker,
        "current_price": current_price,
        "market_cap": market_cap,
        "week52_high": week_hi,
        "week52_low": week_lo,
        "iv_pct": iv,
        "iv_expiry": iv_exp,
        "rsi": rsi,
        "next_earnings": next_earnings,
    }


def print_snapshot(snapshot):
    """Print a single ticker's snapshot dict (as produced by gather_snapshot)."""
    ticker = snapshot["ticker"]
    print(f"\n{'='*60}")
    print(f"{ticker} Snapshot")
    print(f"{'='*60}")
    print(f"Current Price:       ${snapshot['current_price']:.2f}")
    print(f"Market Cap:          {format_market_cap(snapshot['market_cap'])}")

    hi_str = f"${snapshot['week52_high']:.2f}" if snapshot['week52_high'] else "N/A"
    lo_str = f"${snapshot['week52_low']:.2f}" if snapshot['week52_low'] else "N/A"
    print(f"52-Week High/Low:    {hi_str} / {lo_str}")

    iv_str = f"{snapshot['iv_pct']:.1f}%" if snapshot['iv_pct'] is not None else "N/A"
    iv_suffix = f" (ATM put, {snapshot['iv_expiry']} expiry)" if snapshot['iv_expiry'] else ""
    print(f"Current IV:          {iv_str}{iv_suffix}")

    rsi_str = f"{snapshot['rsi']:.1f}" if snapshot['rsi'] is not None else "N/A"
    print(f"Current RSI (14d):   {rsi_str}")

    next_earnings = snapshot["next_earnings"]
    print(f"Next Earnings Date:  {next_earnings or 'N/A'}")
    print(f"{'='*60}")


def gather_technicals(ticker_obj, fields):
    """
    Fetch only the technical fields actually requested (see
    TECHNICALS_FIELD_ORDER) for one ticker. get_current_price() can raise
    SystemExit on total failure — that's intentionally left to propagate so
    the caller can skip this ticker and continue with the rest, matching the
    full-scan mode's per-ticker resilience.
    """
    data = {}

    if "price" in fields:
        data["price"] = get_current_price(ticker_obj)

    if "52w-range" in fields:
        data["week52_high"], data["week52_low"] = get_52week_range(ticker_obj)

    if "analyst-target" in fields:
        data["analyst_target"], data["num_analysts"] = get_mean_analyst_target(ticker_obj)

    if "ath" in fields:
        data["ath"] = get_all_time_high(ticker_obj)

    if "market-cap" in fields:
        data["market_cap"] = get_market_cap(ticker_obj)

    if "rsi" in fields:
        data["rsi"] = get_current_rsi(ticker_obj)

    if "bollinger" in fields:
        data["bollinger"] = get_bollinger_position(ticker_obj)

    return data


def print_technicals_report(ticker, data, fields):
    """Print one ticker's requested technicals, in TECHNICALS_FIELD_ORDER regardless of CLI order."""
    print(f"\n{'='*60}")
    print(f"{ticker} Technicals")
    print(f"{'='*60}")

    for key in fields:
        label = f"{TECHNICALS_FIELD_LABELS[key]}:"

        if key == "price":
            v = data.get("price")
            print(f"{label:<28}{f'${v:.2f}' if v is not None else 'N/A'}")

        elif key == "52w-range":
            hi, lo = data.get("week52_high"), data.get("week52_low")
            hi_str = f"${hi:.2f}" if hi else "N/A"
            lo_str = f"${lo:.2f}" if lo else "N/A"
            print(f"{label:<28}{hi_str} / {lo_str}")

        elif key == "analyst-target":
            target, num_analysts = data.get("analyst_target"), data.get("num_analysts")
            if target is None:
                print(f"{label:<28}N/A")
            else:
                analysts_str = f" ({num_analysts} analysts)" if num_analysts else ""
                print(f"{label:<28}${target:.2f}{analysts_str}")

        elif key == "ath":
            v = data.get("ath")
            print(f"{label:<28}{f'${v:.2f}' if v is not None else 'N/A'}")

        elif key == "market-cap":
            print(f"{label:<28}{format_market_cap(data.get('market_cap'))}")

        elif key == "rsi":
            v = data.get("rsi")
            print(f"{label:<28}{f'{v:.1f}' if v is not None else 'N/A'}")

        elif key == "bollinger":
            bb = data.get("bollinger")
            if bb is None:
                print(f"{label:<28}N/A")
            else:
                below = "Yes" if bb.percent_b < 0 else "No"
                print(f"{label:<28}%B {bb.percent_b:.2f} ({bb.zone}) | Below lower band: {below}")

    print(f"{'='*60}")


def build_technicals_row(ticker, data, fields):
    """
    Format one ticker's technicals into a flat dict of column label -> string
    value, for the consolidated end-of-run table. Multi-value fields
    (52w-range, analyst-target, bollinger) split into separate columns so
    the table stays one value per cell.
    """
    row = {"Ticker": ticker}

    if "price" in fields:
        v = data.get("price")
        row["Price"] = f"${v:.2f}" if v is not None else "N/A"

    if "52w-range" in fields:
        hi, lo = data.get("week52_high"), data.get("week52_low")
        row["52W High"] = f"${hi:.2f}" if hi else "N/A"
        row["52W Low"] = f"${lo:.2f}" if lo else "N/A"

    if "analyst-target" in fields:
        target, num_analysts = data.get("analyst_target"), data.get("num_analysts")
        row["Analyst Target"] = f"${target:.2f}" if target is not None else "N/A"
        row["# Analysts"] = str(num_analysts) if num_analysts else "N/A"

    if "ath" in fields:
        v = data.get("ath")
        row["ATH"] = f"${v:.2f}" if v is not None else "N/A"

    if "market-cap" in fields:
        row["Market Cap"] = format_market_cap(data.get("market_cap"))

    if "rsi" in fields:
        v = data.get("rsi")
        row["RSI"] = f"{v:.1f}" if v is not None else "N/A"

    if "bollinger" in fields:
        bb = data.get("bollinger")
        row["BB %B (Zone)"] = f"{bb.percent_b:.2f} ({bb.zone})" if bb is not None else "N/A"
        row["Below Lower Band"] = ("Yes" if bb.percent_b < 0 else "No") if bb is not None else "N/A"

    return row


def run_technicals_mode(tickers, fields):
    """
    --technicals: fetch and print only the requested technical fields for
    each ticker, skipping the put-option scan entirely. A single bad/
    delisted ticker is skipped with a warning rather than stopping the run.
    Prints each ticker's own block, then one consolidated table across all
    successfully-fetched tickers at the end.
    """
    field_labels = ", ".join(TECHNICALS_FIELD_LABELS[f] for f in fields)
    print(f"Technicals for {len(tickers)} ticker(s): {', '.join(tickers)}")
    print(f"Fields: {field_labels}")

    table_rows = []  # [(raw_rsi_or_None, row_dict), ...]
    for ticker in tickers:
        tk = yf.Ticker(ticker)
        try:
            data = gather_technicals(tk, fields)
        except SystemExit as e:
            print(f"\n{ticker}: {e} — skipping this ticker.")
            continue
        print_technicals_report(ticker, data, fields)
        table_rows.append((data.get("rsi"), build_technicals_row(ticker, data, fields)))

    if not table_rows:
        return

    # Sort ascending by RSI when it was requested (missing RSI values sort last);
    # otherwise keep the tickers in the order they were requested/scanned.
    if "rsi" in fields:
        table_rows.sort(key=lambda pair: (pair[0] is None, pair[0]))
    rows = [row for _, row in table_rows]

    print(f"\n{'='*100}")
    print("ALL TICKERS — TECHNICALS SUMMARY" + (" (sorted by RSI, ascending)" if "rsi" in fields else ""))
    print(f"{'='*100}")
    print(pd.DataFrame(rows).to_string(index=False))


def process_ticker(ticker, args):
    """
    Run the full scan for one ticker: fetch price/expirations, pull the put
    chain (band or single-strike mode), compute annualized returns, save
    that ticker's own CSV/chart, print its top rows and snapshot.

    Returns (df, snapshot) — the ticker's result DataFrame and its snapshot
    dict (see gather_snapshot) — or (None, None) if nothing could be fetched
    (e.g. bad ticker symbol) so the caller can skip it and continue with the
    rest of the list.
    """
    min_days_ahead = args.min_days
    max_days_ahead = args.max_days
    single_strike_mode = args.strike is not None

    print(f"\nFetching {ticker} current price and option expirations...")
    tk = yf.Ticker(ticker)
    try:
        current_price = get_current_price(tk)
    except SystemExit as e:
        print(f"  {ticker}: {e} — skipping this ticker.")
        return None, None

    if single_strike_mode:
        print(f"Current {ticker} price: ${current_price:.2f}  |  target strike: {args.strike:g}")
    else:
        price_low = current_price * args.pct_low / 100
        price_high = current_price * args.pct_high / 100
        print(f"Current {ticker} price: ${current_price:.2f}  |  "
              f"strike band {args.pct_low:g}%-{args.pct_high:g}% of price = "
              f"${price_low:.2f}-${price_high:.2f}")

    expirations = get_expirations_within_range(tk, min_days_ahead, max_days_ahead)
    if not expirations:
        print(f"  {ticker}: no expirations found between {min_days_ahead} and {max_days_ahead} "
              f"days out — skipping.")
        return None, None
    print(f"Found {len(expirations)} expirations between {min_days_ahead} and {max_days_ahead} "
          f"days out.\n")

    today = datetime.today().date()
    records = []

    for exp in expirations:
        exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
        dte = (exp_date - today).days
        if dte <= 0:
            continue  # expires today or already passed intraday; avoid divide-by-zero

        try:
            chain = tk.option_chain(exp)
        except Exception as e:
            print(f"  {exp}: failed to fetch chain ({e})")
            continue

        puts = chain.puts
        if puts.empty:
            print(f"  {exp}: no put data available")
            continue

        if single_strike_mode:
            row, exact = find_nearest_put_row(puts, args.strike)
            if row is None:
                print(f"  {exp}: no put data available")
                continue
            rows_to_process = [row]
            note = "" if exact else f" [nearest strike to {args.strike:g}]"
        else:
            band = puts[(puts["strike"] > price_low) & (puts["strike"] < price_high)]
            if band.empty:
                print(f"  {exp}: no strikes within the {args.pct_low:g}%-{args.pct_high:g}% band")
                continue
            rows_to_process = [r for _, r in band.iterrows()]
            note = ""

        for row in rows_to_process:
            strike = float(row["strike"])
            if strike <= 0:
                continue

            bid = safe_num(row.get("bid"))
            ask = safe_num(row.get("ask"))
            last = safe_num(row.get("lastPrice"))
            vol = safe_num(row.get("volume"))
            oi = safe_num(row.get("openInterest"))

            # Yahoo's free feed frequently reports 0 for bid/ask on thinly-traded
            # contracts. Fall back to lastPrice for the annualized-return calc so a
            # real-but-illiquid option doesn't show a misleading 0% return.
            bid_for_calc = bid
            ask_for_calc = ask
            bid_used_fallback = False
            ask_used_fallback = False
            if not args.no_fallback and last > 0:
                if bid == 0:
                    bid_for_calc = last
                    bid_used_fallback = True
                if ask == 0:
                    ask_for_calc = last
                    ask_used_fallback = True

            # Capital basis: full cash-secured (the strike) is always computed for
            # reference. By default, the PRIMARY annualized return instead uses an
            # approximated portfolio-margin requirement (much smaller than the full
            # strike, since margin accounts don't tie up 100% of the strike as
            # collateral) — see estimate_portfolio_margin_requirement() docstring.
            # --no-margin reverts the primary columns to the cash-secured basis.
            margin_req_bid = estimate_portfolio_margin_requirement(
                current_price, strike, bid_for_calc, args.margin_shock_pct,
                args.margin_floor, args.margin_floor_pct)
            margin_req_ask = estimate_portfolio_margin_requirement(
                current_price, strike, ask_for_calc, args.margin_shock_pct,
                args.margin_floor, args.margin_floor_pct)

            capital_basis_bid = strike if args.no_margin else margin_req_bid
            capital_basis_ask = strike if args.no_margin else margin_req_ask

            annualized_return_bid = (bid_for_calc / capital_basis_bid) * (365.0 / dte) * 100
            annualized_return_ask = (ask_for_calc / capital_basis_ask) * (365.0 / dte) * 100
            annualized_return_bid_cash_secured = (bid_for_calc / strike) * (365.0 / dte) * 100
            annualized_return_ask_cash_secured = (ask_for_calc / strike) * (365.0 / dte) * 100
            # Always compute the margin-basis figures too (independent of --no-margin), so
            # charts can show both bases side by side regardless of which one is "primary".
            annualized_return_bid_margin = (bid_for_calc / margin_req_bid) * (365.0 / dte) * 100
            annualized_return_ask_margin = (ask_for_calc / margin_req_ask) * (365.0 / dte) * 100

            records.append({
                "ticker": ticker,
                "expiration": exp,
                "days_to_expiration": dte,
                "strike": strike,
                "current_price": current_price,
                "moneyness_pct": strike / current_price * 100,
                "bid": bid,
                "ask": ask,
                "last_price": last,
                "volume": vol,
                "open_interest": oi,
                "bid_used_fallback": bid_used_fallback,
                "ask_used_fallback": ask_used_fallback,
                "margin_requirement_bid": margin_req_bid,
                "margin_requirement_ask": margin_req_ask,
                "capital_basis_bid": capital_basis_bid,
                "capital_basis_ask": capital_basis_ask,
                "annualized_return_bid_pct": annualized_return_bid,
                "annualized_return_ask_pct": annualized_return_ask,
                "annualized_return_bid_pct_cash_secured": annualized_return_bid_cash_secured,
                "annualized_return_ask_pct_cash_secured": annualized_return_ask_cash_secured,
                "annualized_return_bid_pct_margin": annualized_return_bid_margin,
                "annualized_return_ask_pct_margin": annualized_return_ask_margin,
            })

        if single_strike_mode:
            print(f"  {exp}: strike {rows_to_process[0]['strike']:g}{note} (DTE={dte})")
        else:
            print(f"  {exp}: {len(rows_to_process)} strikes in band (DTE={dte})")

    if not records:
        hint = ("Check the ticker symbol or try a different --strike." if single_strike_mode
                 else "Try widening --pct-low/--pct-high or check the ticker symbol.")
        print(f"  {ticker}: no data collected — skipping. {hint}")
        return None, None

    df = pd.DataFrame(records)
    df = df.sort_values(["expiration", "strike"]).reset_index(drop=True)

    if single_strike_mode:
        out_csv = f"{ticker}_{args.strike:g}_put_annualized_returns.csv"
    else:
        out_csv = f"{ticker}_put_annualized_returns.csv"
    df.to_csv(out_csv, index=False)
    print(f"\nSaved {len(df)} rows to {out_csv}")

    n_bid_fallback = int(df["bid_used_fallback"].sum())
    n_ask_fallback = int(df["ask_used_fallback"].sum())
    if n_bid_fallback or n_ask_fallback:
        print(f"Note: {n_bid_fallback} row(s) used lastPrice in place of a 0 bid, and "
              f"{n_ask_fallback} row(s) used lastPrice in place of a 0 ask (typical for "
              f"illiquid/far-OTM strikes). See bid_used_fallback / ask_used_fallback columns "
              f"in the CSV. Run --no-fallback to disable this and use raw 0 values instead.")

    margin_note = ("cash-secured (full strike)" if args.no_margin
                    else f"~portfolio margin (approx., {args.margin_shock_pct:g}% stress, "
                         f"floor=max(${args.margin_floor:g}/sh, {args.margin_floor_pct:g}% of price))")
    print(f"Capital basis for annualized_return_*_pct columns: {margin_note}. "
          f"See annualized_return_*_pct_cash_secured for the full-cash-basis comparison.")

    top_n = args.top
    print(f"\nTop {top_n} {ticker} rows by annualized BID return:")
    top = df.sort_values("annualized_return_bid_pct", ascending=False).head(top_n)
    print(top[["expiration", "strike", "moneyness_pct", "bid", "ask", "last_price",
               "days_to_expiration", "capital_basis_bid", "annualized_return_bid_pct",
               "annualized_return_bid_pct_cash_secured", "annualized_return_ask_pct",
               "bid_used_fallback", "ask_used_fallback"]]
          .to_string(index=False, float_format=lambda x: f"{x:.2f}"))

    snapshot = gather_snapshot(tk, ticker, current_price, expirations)
    print_snapshot(snapshot)

    if not args.no_plot:
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            print("\nmatplotlib not installed — skipping chart. "
                  "Install with: pip install matplotlib")
            return df, snapshot

        mplcursors_mod = try_import_mplcursors()
        out_png = out_csv.rsplit(".", 1)[0] + ("_lineplot.png" if single_strike_mode else "_heatmap.png")

        if single_strike_mode:
            df_sorted = df.sort_values("expiration").reset_index(drop=True)
            x_dates = pd.to_datetime(df_sorted["expiration"])
            bid_fb = df_sorted[df_sorted["bid_used_fallback"]]
            ask_fb = df_sorted[df_sorted["ask_used_fallback"]]

            fig, (ax_m, ax_c) = plt.subplots(1, 2, figsize=(18, 6))
            panels = [
                (ax_m, "annualized_return_bid_pct_margin", "annualized_return_ask_pct_margin",
                 f"Portfolio-Margin (approx., {args.margin_shock_pct:g}% stress)"),
                (ax_c, "annualized_return_bid_pct_cash_secured", "annualized_return_ask_pct_cash_secured",
                 "Cash-Secured (full strike)"),
            ]
            for ax, bid_col, ask_col, basis_label in panels:
                bid_line, = ax.plot(x_dates, df_sorted[bid_col], marker="o", label="Bid", color="tab:blue")
                ask_line, = ax.plot(x_dates, df_sorted[ask_col], marker="s", label="Ask", color="tab:orange")
                attach_point_hover(mplcursors_mod, bid_line, df_sorted, "bid", bid_col, "Ann. Return (Bid)")
                attach_point_hover(mplcursors_mod, ask_line, df_sorted, "ask", ask_col, "Ann. Return (Ask)")

                if not bid_fb.empty:
                    ax.scatter(pd.to_datetime(bid_fb["expiration"]), bid_fb[bid_col],
                               marker="^", s=100, color="tab:blue", edgecolors="black",
                               linewidths=0.8, zorder=5, label="Bid used lastPrice")
                if not ask_fb.empty:
                    ax.scatter(pd.to_datetime(ask_fb["expiration"]), ask_fb[ask_col],
                               marker="^", s=100, color="tab:orange", edgecolors="black",
                               linewidths=0.8, zorder=5, label="Ask used lastPrice")
                ax.set_xlabel("Expiration Date")
                ax.set_ylabel("Annualized Return (%)")
                ax.set_title(basis_label)
                ax.tick_params(axis="x", rotation=45)
                ax.grid(True, alpha=0.3)
                ax.legend()

            fig.suptitle(f"{ticker} {args.strike:g} Strike Put — Annualized Return by Expiration "
                         f"(Current price: ${current_price:.2f})")
            plt.tight_layout()
        else:
            fig, (ax_m, ax_c) = plt.subplots(1, 2, figsize=(20, max(6, df["strike"].nunique() * 0.35 + 2)))
            panels = [
                (ax_m, "annualized_return_bid_pct_margin",
                 f"Portfolio-Margin (approx., {args.margin_shock_pct:g}% stress)"),
                (ax_c, "annualized_return_bid_pct_cash_secured", "Cash-Secured (full strike)"),
            ]
            premium_pivot = df.pivot_table(index="strike", columns="expiration", values="bid", aggfunc="mean")
            for ax, value_col, basis_label in panels:
                pivot = df.pivot_table(index="strike", columns="expiration", values=value_col, aggfunc="mean")
                pivot = pivot.sort_index(ascending=False)  # higher strikes at top
                premium_pivot_sorted = premium_pivot.reindex(index=pivot.index, columns=pivot.columns)

                im = ax.imshow(pivot.values, aspect="auto", cmap="RdYlGn")
                ax.set_xticks(range(len(pivot.columns)))
                ax.set_xticklabels(pivot.columns, rotation=45, ha="right")
                ax.set_yticks(range(len(pivot.index)))
                ax.set_yticklabels([f"{s:g}" for s in pivot.index])
                ax.set_xlabel("Expiration")
                ax.set_ylabel("Strike")
                ax.set_title(basis_label)
                cbar = fig.colorbar(im, ax=ax)
                cbar.set_label("Annualized Return (Bid, %)")
                attach_heatmap_hover(fig, ax, pivot, premium_pivot_sorted, "Ann. Return (Bid)")

            fig.suptitle(f"{ticker} Put Annualized BID Return (%) — Strike x Expiration "
                         f"(Current price: ${current_price:.2f})")
            plt.tight_layout()

        plt.savefig(out_png, dpi=150)
        print(f"Saved chart to {out_png}")
        plt.close(fig)

    return df, snapshot


def main():
    args = parse_args()

    if args.add_ticker or args.remove_ticker or args.list_tickers:
        manage_watchlist(args)
        return

    if yf is None:
        sys.exit("Missing dependency yfinance (needed to run a scan). "
                  "Install with:  pip install yfinance pandas")

    if args.universe:
        universe_ticker = args.universe.upper()
        tickers = fetch_universe_tickers(universe_ticker)
        preview = ", ".join(tickers[:10]) + (", ..." if len(tickers) > 10 else "")
        print(f"Universe from {universe_ticker} holdings: {len(tickers)} ticker(s) — {preview}")
    else:
        raw_tickers = args.ticker if args.ticker is not None else load_default_tickers()
        tickers = parse_ticker_list(raw_tickers)

    if not tickers:
        sys.exit("No valid tickers provided.")

    if args.technicals is not None:
        fields = parse_technicals_fields(args.technicals)
        run_technicals_mode(tickers, fields)
        return

    if args.strike is None and args.pct_low >= args.pct_high:
        sys.exit(f"--pct-low ({args.pct_low}) must be less than --pct-high ({args.pct_high}).")

    if args.min_days > args.max_days:
        sys.exit(f"--min-days ({args.min_days}) must not exceed --max-days ({args.max_days}).")

    print(f"Scanning {len(tickers)} ticker(s): {', '.join(tickers)}")

    all_dfs = []
    all_snapshots = []
    skipped = []
    for ticker in tickers:
        df, snapshot = process_ticker(ticker, args)
        if df is not None:
            all_dfs.append(df)
            all_snapshots.append(snapshot)
        else:
            skipped.append(ticker)

    if not all_dfs:
        sys.exit("\nNo data collected for any ticker — nothing to save or rank.")

    combined = pd.concat(all_dfs, ignore_index=True)

    if args.output:
        combined_csv = args.output
    elif len(tickers) == 1:
        combined_csv = f"{tickers[0]}_put_annualized_returns.csv"
    else:
        combined_csv = "combined_put_annualized_returns.csv"
    combined.to_csv(combined_csv, index=False)

    print(f"\n{'='*70}")
    print(f"COMBINED RESULTS — {len(tickers) - len(skipped)}/{len(tickers)} tickers, "
          f"{len(combined)} total rows")
    if skipped:
        print(f"Skipped (no data): {', '.join(skipped)}")
    print(f"Saved combined data to {combined_csv}")
    print(f"{'='*70}")

    top_n = args.top
    margin_note = ("cash-secured (full strike)" if args.no_margin
                    else f"~portfolio margin (approx., {args.margin_shock_pct:g}% stress, "
                         f"floor=max(${args.margin_floor:g}/sh, {args.margin_floor_pct:g}% of price))")
    print(f"\nCapital basis for ranking: {margin_note}. Not your broker's exact live number — "
          f"see the docstring / --no-margin for details.")
    print(f"\nTop {top_n} PUT OPTIONS ACROSS ALL TICKERS by annualized BID return:")
    top = combined.sort_values("annualized_return_bid_pct", ascending=False).head(top_n)
    print(top[["ticker", "expiration", "strike", "moneyness_pct", "bid", "ask", "last_price",
               "days_to_expiration", "capital_basis_bid", "annualized_return_bid_pct",
               "annualized_return_bid_pct_cash_secured", "annualized_return_ask_pct",
               "bid_used_fallback", "ask_used_fallback"]]
          .to_string(index=False, float_format=lambda x: f"{x:.2f}"))

    print(f"\n{'='*100}")
    print("ALL TICKERS — SUMMARY (Current Price, Market Cap, 52W High/Low, IV, RSI, Next Earnings)")
    print(f"{'='*100}")
    summary_rows = []
    for s in all_snapshots:
        summary_rows.append({
            "Ticker": s["ticker"],
            "Price": f"${s['current_price']:.2f}",
            "Market Cap": format_market_cap(s["market_cap"]),
            "52W High": f"${s['week52_high']:.2f}" if s["week52_high"] else "N/A",
            "52W Low": f"${s['week52_low']:.2f}" if s["week52_low"] else "N/A",
            "IV%": f"{s['iv_pct']:.1f}" if s["iv_pct"] is not None else "N/A",
            "RSI": f"{s['rsi']:.1f}" if s["rsi"] is not None else "N/A",
            "Next Earnings": s["next_earnings"] or "N/A",
        })
    summary_df = pd.DataFrame(summary_rows)
    print(summary_df.to_string(index=False))

    if not args.no_plot:
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            print("\nmatplotlib not installed — skipping combined data plot. "
                  "Install with: pip install matplotlib")
            return

        tickers_in_data = combined["ticker"].unique()
        cmap = plt.get_cmap("tab10" if len(tickers_in_data) <= 10 else "tab20")
        mplcursors_mod = try_import_mplcursors()

        fig, (ax_m, ax_c) = plt.subplots(1, 2, figsize=(20, 7))
        panels = [
            (ax_m, "annualized_return_bid_pct_margin",
             f"Portfolio-Margin (approx., {args.margin_shock_pct:g}% stress)"),
            (ax_c, "annualized_return_bid_pct_cash_secured", "Cash-Secured (full strike)"),
        ]
        for ax, value_col, basis_label in panels:
            for i, tk_name in enumerate(tickers_in_data):
                sub = combined[combined["ticker"] == tk_name]
                scatter_artist = ax.scatter(sub["moneyness_pct"], sub[value_col],
                           label=tk_name, color=cmap(i % cmap.N), alpha=0.75, s=50,
                           edgecolors="black", linewidths=0.3)
                attach_point_hover(mplcursors_mod, scatter_artist, sub, "bid", value_col,
                                    "Ann. Return (Bid)")
            ax.set_xlabel("Strike as % of Current Price (Moneyness %)")
            ax.set_ylabel("Annualized Bid Return (%)")
            ax.set_title(basis_label)
            ax.grid(True, alpha=0.3)
            ax.legend(title="Ticker", bbox_to_anchor=(1.02, 1), loc="upper left")

        fig.suptitle(f"All Scanned Put Options — Annualized Bid Return vs Moneyness "
                      f"({len(combined)} rows across {len(tickers_in_data)} ticker(s))")
        plt.tight_layout()

        combined_png = combined_csv.rsplit(".", 1)[0] + "_scatter.png"
        plt.savefig(combined_png, dpi=150)
        print(f"\nSaved combined data plot to {combined_png}")
        plt.show()


if __name__ == "__main__":
    main()
