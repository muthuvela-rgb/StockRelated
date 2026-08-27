# StockRelated

A collection of independent Python scripts for screening, plotting, and
reporting on stocks and their options, plus a small `stock_fall_detector`
package with test coverage. Everything reads free public data (Yahoo
Finance, SEC EDGAR, StockTwits) — no API keys, no brokerage credentials, and
none of it executes trades. This is data retrieval / analysis tooling, not
investment advice.

## Getting Started (new to GitHub? start here)

This is a GitHub repository — a folder of code hosted online that you copy
("clone") down to your own computer to run. Here's the full path from zero.

### 1. Install the prerequisites

- **Python 3** — check if you already have it by opening a terminal
  (Terminal on Mac, Command Prompt/PowerShell on Windows) and running
  `python3 --version` (or `python --version` on Windows). If that fails,
  download it from [python.org/downloads](https://www.python.org/downloads/).
- **Git** — check with `git --version`. If it's missing, get it from
  [git-scm.com/downloads](https://git-scm.com/downloads) (Mac users can
  also just run `git --version` once — macOS will offer to install it for
  you). You technically don't need Git if you use the ZIP download in step
  2 instead, but installing it now makes it much easier to get future
  updates to this repo.

### 2. Get the code onto your computer

**Option A — clone with Git (recommended):** open a terminal, navigate to
wherever you want the folder to live (e.g. `cd ~/Documents`), then run:

```bash
git clone https://github.com/muthuvela-rgb/StockRelated.git
cd StockRelated
```

This creates a `StockRelated` folder with the full project, connected to
GitHub so you can pull future updates with `git pull`.

**Option B — download a ZIP (no Git required):** on the repository's GitHub
page, click the green **Code** button, choose **Download ZIP**, then unzip
it and open a terminal in that unzipped folder. This is a one-time snapshot
— you'll need to re-download the ZIP to get future updates instead of
`git pull`.

### 3. Install the Python dependencies

From inside the project folder:

```bash
pip install -r requirements.txt
```

(If `pip` isn't found, try `pip3` instead.)

### 4. Try running something

```bash
python3 stock_earnings_report.py --tickers AAPL
```

If that prints a report for AAPL, you're set up correctly. See the [Tools](#tools)
section below for what every script in this repo does and how to run it.

## Tools

### `stock_fall_detector` — find stocks that fell sharply

Given a list of stocks, find any that fell more than a configurable percentage
(default 10%) within a configurable lookback window (default 1 week), limited
to stocks whose market cap **before** the fall exceeded a configurable
threshold (default $10B).

```bash
python -m stock_fall_detector.cli AAPL MSFT TSLA NVDA
```

Tickers are optional. Run with none and it scans QQQ's holdings (the
Nasdaq-100, ~100 tickers) instead:

```bash
python -m stock_fall_detector.cli
```

`stock_fall_detector/qqq_components.py` holds that list as a point-in-time
snapshot — the index is periodically reconstituted, so it will drift out of
date. Pass explicit tickers to bypass it, or edit that file to refresh it.

#### Options

| Flag | Default | Meaning |
|---|---|---|
| `--days` | `7` | Lookback window in calendar days |
| `--fall-pct` | `10` | Minimum percentage drop to flag a stock |
| `--min-market-cap` | `10000000000` ($10B) | Minimum market cap at the *start* of the window |
| `--no-context` | off | Skip the news/analyst/social section below the summary table (faster) |
| `--no-technicals` | off | Skip the RSI/volatility/Bollinger/high-low section below the summary table (faster) |

#### Example

```bash
python -m stock_fall_detector.cli AAPL MSFT TSLA NVDA META --days 7 --fall-pct 10 --min-market-cap 10000000000
```

Output starts with a titled summary table — the title states the actual
comparison window (start date to end date) so it's clear which prices are
being compared. Unless `--no-technicals` is set, the table also includes
RSI, implied volatility, Bollinger %B, and the current price's distance from
its 52-week high and all-time high, so you can screen at a glance without
reading the detail section below:

```
Fall report: 2026-08-14 to 2026-08-21 (Current = last close)
Ticker     Start  Current   Chg %  MktCap($B)    RSI    IV%   BB %B  vs52wkHi%   vsATH%
INTC      102.50    90.07  -12.13      541.83   39.6   61.0    0.27      -36.7    -36.7
WMT       115.27   103.70  -10.04      917.33   29.6   24.2   -0.16      -23.3    -23.3
```

(With `--no-technicals`, the table falls back to just Ticker/Start/Current/Change %/Mkt Cap.)

Rows are sorted worst-first (biggest drop at top); market cap shown is the
cap *before* the fall (at the start price). For each qualifying stock, it
then prints:

- **Recent headlines** — up to 5 ticker-tagged news items from Yahoo Finance,
  most recent first, as a starting point for *why* it may have fallen
  (correlation, not a confirmed cause — read the articles)
- **Analyst view** — consensus recommendation, mean analyst price target and
  implied upside/downside vs. the current price, and the most recent
  upgrade/downgrade actions, from Yahoo Finance
- **Social sentiment** — bullish/bearish split from StockTwits' most recent
  sentiment-tagged posts for the ticker
- **Technicals** — RSI(14), ~30-day at-the-money implied volatility (from the
  options chain), Bollinger Bands(20,2) position, 52-week high/low, and
  all-time high with the current price's distance from it

Any section can come back empty (thin news coverage, no analyst coverage, no
tagged StockTwits posts, no options chain) — that's reported as "unavailable"
rather than guessed at.

For each ticker, the tool fetches recent daily closing prices from Yahoo
Finance's public chart/quoteSummary endpoints (via plain `requests`, no
scraping library) and shares outstanding. It computes:

- `market_cap_before = start_price * shares_outstanding`
- `pct_change = (end_price - start_price) / start_price * 100`

A stock is reported if `market_cap_before` exceeds `--min-market-cap` **and**
`pct_change` is a drop of at least `--fall-pct`.

The core detection logic (`stock_fall_detector.detector.find_falling_stocks`)
is decoupled from the data source via a small `PriceDataSource` protocol, and
the news/analyst/social report formatting (`stock_fall_detector.cli.format_context_report`)
is decoupled from fetching via a `ContextSource` protocol, so tests run
offline against fake data:

```bash
pytest
```

### `stock_options_toolkit.py` — put annualized-return scanner, technicals, and ETF universe expansion

A multi-ticker, multi-mode toolkit built around a persisted watchlist. By
default it scans put options; `--technicals` and `--universe` switch it to
other jobs entirely, all sharing the same ticker-selection and watchlist
machinery.

**Default mode — put annualized-return scan:** pulls every option
expiration whose days-to-expiration falls within a `--min-days`/`--max-days`
window (default 0-365 days out), and for each expiration, scans every put
strike within a percentage band of the current price (or one specific
`--strike`), computing an annualized return from both the bid and ask
premium — using an approximated portfolio-margin capital basis by default
(`--no-margin` for cash-secured/full-strike instead). With multiple tickers,
results are combined and the top rows across all of them are printed
together.

```bash
python stock_options_toolkit.py
python stock_options_toolkit.py --ticker QQQ,AAPL,MSFT
python stock_options_toolkit.py -t QQQ --min-days 30 --max-days 90
python stock_options_toolkit.py -t QQQ --strike 580
python stock_options_toolkit.py -t QQQ --pct-low 50 --pct-high 90
```

If `-t/--ticker` is omitted, it scans a persisted default watchlist stored
in `watchlist.json` (seeded on first run with SPCX, MU, SNDK, ALAB, NVDA,
SKHY, META, TSLA, QQQ). Manage that list without running a scan via
`--add-ticker`, `--remove-ticker`, and `--list-tickers`. Run with `-h` for
the full option list (`--min-days`, `--max-days`, `--strike`, `--pct-low`,
`--pct-high`, `--output`, `--no-plot`, `--top`, `--no-fallback`,
`--no-margin`, `--margin-shock-pct`, `--margin-floor`, `--margin-floor-pct`).
Saves a per-ticker CSV/chart plus a combined CSV and chart across all
tickers scanned. Per-ticker chart type depends on the scan: single-strike
mode plots annualized return vs. expiration; band mode with 2+ tickers
plots a strike x expiration heatmap. **Band mode with exactly one
ticker** is a special case: it plots actual bid premium ($) vs. actual
strike price ($) instead, one line per expiration — hovering a point
shows its expiration date, strike, and bid/ask (interactive hover needs
`mplcursors` and a live matplotlib window; has no effect on the saved
PNG). That chart also pops up interactively when it's done (like the
combined chart does for multi-ticker runs), and the redundant
combined-across-tickers chart is skipped in this single-ticker case
since it would just duplicate the same data on different axes.

**Technicals-only mode (`--technicals`)** skips the put-option scan entirely
and just reports technicals for the requested ticker(s):

```bash
python stock_options_toolkit.py --technicals -t AAPL MSFT
python stock_options_toolkit.py --technicals rsi bollinger -t QQQ
python stock_options_toolkit.py --technicals price,analyst-target
python stock_options_toolkit.py --technicals fibonacci -t AAPL
```

Fields are user-configurable — pick any subset (comma or space separated)
from `price`, `52w-range`, `analyst-target`, `ath`, `market-cap`, `rsi`,
`bollinger`, `iv`, `stddev`, `fibonacci`. Bare `--technicals` (no fields)
reports all of them, for any number of tickers. `iv` is ~30-day at-the-
money implied volatility from the option chain. `stddev` is the
annualized standard deviation of daily returns over ~3 months (historical/
realized volatility, a backward-looking complement to `iv`), reported two
ways: as a % (standard 252-trading-day convention) and in dollars (daily
std dev scaled by √365 CALENDAR days and applied to the most recent close
— an approximate 1-standard-deviation dollar move over a year). `fibonacci`
is the 0%/23.6%/38.2%/50%/61.8%/100% retracement levels between the
52-week low and high. Prints one block per ticker, then a single
consolidated table across every ticker at the end (multi-value fields
split into their own columns, e.g. `Fib 23.6%`, `Std Dev $/yr`) — sorted
ascending by RSI when `rsi` is included, otherwise in request order.

**ETF universe expansion (`--universe`)** replaces `-t/--ticker`/the
watchlist with an ETF's full component holdings, fetched live (no API key)
— e.g. scan every S&P 500 or QQQ constituent in one shot:

```bash
python stock_options_toolkit.py --universe SPY --top 20
python stock_options_toolkit.py --universe QQQ --technicals rsi
python stock_options_toolkit.py --universe XLK --strike 200
```

Currently supports **QQQ** (via Invesco's own holdings API) and **State
Street SPDR ETFs** (SPY, DIA, MDY, and the SPDR sector funds
XLK/XLF/XLE/XLV/XLY/XLP/XLI/XLB/XLU/XLRE/XLC, among others) via their
public holdings spreadsheet. Other providers (iShares, Vanguard, other
Invesco funds, ...) don't publish a similarly simple/stable public
download and exit with a clear error rather than silently returning a
partial (e.g. top-10-only) list — pass explicit tickers with `-t/--ticker`
for those instead. Combines with `--technicals` or the default scan mode.

**Every run's full console output is also logged** to a timestamped file
under `logs/` (e.g. `logs/stock_options_toolkit_20260826_224027.log`), in
addition to the terminal. Each run gets its own file — nothing is ever
overwritten or appended to, so every past run's complete output is kept.

### `short_dated_put_screener.py` — top short-dated puts by annualized return

Scans a universe of stocks/ETFs (by default the QQQ / Nasdaq-100
constituents bundled in the script) and reports the top N put options ranked
by annualized return, subject to filters on expiration window, minimum bid
premium, moneyness (how far out-of-the-money), and underlying market cap.
"Annualized return" is computed against an approximated portfolio-margin
capital basis by default (`--no-margin` switches to a cash-secured/full-strike
basis instead) — this is a simplified linear estimate for screening, not a
broker-exact figure.

```bash
python short_dated_put_screener.py --max-moneyness 90
python short_dated_put_screener.py --max-moneyness 85 --days 15
python short_dated_put_screener.py -t QQQ,AAPL,MSFT --max-moneyness 95
python short_dated_put_screener.py --max-moneyness 90 --min-premium 3 --top 20
```

`--max-moneyness` is required. Run `python short_dated_put_screener.py -h`
for the full option list (`--days`, `--min-premium`, `--min-market-cap`,
`--top`, `--no-margin`, `--margin-shock-pct`, `--margin-floor-pct`,
`--margin-floor`, `--margin-premium-buffer-pct`, `--output`). Results are
printed to the console and written in full to a CSV
(`short_dated_put_screen.csv` by default).

### `run_and_notify.py` — daily screener run + macOS notification

Wraps `short_dated_put_screener.py` for a scheduled/cron-style daily run: runs
it with a fixed set of filters, saves the full results CSV, appends the full
console output to a dated file under `logs/`, pops a macOS notification
banner (via `osascript`) with a one-line summary of the best result, and
copies the dated log into a local Google Drive for Desktop sync folder (no
API credentials — Drive's own background sync uploads it). Intended to be
triggered by `launchd` every morning; also safe to run by hand:

```bash
python3 run_and_notify.py
```

macOS-specific (uses `osascript` for notifications); the Google Drive copy
step is skipped gracefully if the sync folder isn't found.

### `create_premium_vs_expiration_date_given_strike_price.py` — premium vs. expiration plot

For a fixed ticker and strike, plots put (or call) option premium against
expiration date across all listed expirations over the next N months.

```bash
python create_premium_vs_expiration_date_given_strike_price.py --ticker QQQ --strike 580
python create_premium_vs_expiration_date_given_strike_price.py -t AAPL -s 200 --months 6
python create_premium_vs_expiration_date_given_strike_price.py -t QQQ --pct-of-price 55
```

Strike can be given as a fixed dollar amount (`-s/--strike`) or as a
percentage of the current stock price (`--pct-of-price`, which snaps to the
nearest actually-listed strike). Run with `-h` for the full option list.

### `create_premium_vs_strike_given_expiration_date.py` — premium vs. strike plot

For a fixed ticker and expiration (or the nearest few expirations), plots put
or call option premium against strike price.

```bash
python create_premium_vs_strike_given_expiration_date.py
python create_premium_vs_strike_given_expiration_date.py --ticker QQQ --expiration 2026-01-16
python create_premium_vs_strike_given_expiration_date.py -t AAPL -e 2026-03-20 --option-type call
python create_premium_vs_strike_given_expiration_date.py -t QQQ --num-expirations 5
```

If `-e/--expiration` is omitted, it plots the nearest few expirations
together (`--num-expirations`, default 3) so gaps between adjacent
expiration curves can be compared. Run with `-h` for the full option list.

For each plotted expiration curve, the script also marks where premium rises
fastest, two ways:

- **Steepest adjacent-strike slope** — the single pair of consecutive listed
  strikes with the largest premium change per $1 of strike, highlighted with
  a green segment and a `slope X.XX` label.
- **Widest 20-bin (5%-of-price) premium difference** — splits the strike
  axis from $0 to the current price into 20 equal-width bins and finds the
  bin with the largest premium difference between its highest- and
  lowest-strike point, highlighted with a shaded price band and a crimson
  `bin Δ$X.XX` label. A coarser, fixed-width view of where premium jumps
  most, complementing the adjacent-strike marker above.

Both are printed to the console too, one marker per plotted expiration.

### `plot_from_csv.py` — offline plot from a saved CSV

Standalone plotting script — no internet/API calls. Reads a CSV like the ones
produced by the two scripts above and plots premium vs. expiration, with
optional knee-of-the-curve and steepest-N-day-window annotations.

```bash
python plot_from_csv.py --csv QQQ_580_put_bids.csv
python plot_from_csv.py --csv MU_600_put_asks.csv --column ask
python plot_from_csv.py --csv data.csv --no-knee --window-days 45
```

Run with `-h` for the full option list.

### `option_chain_fetcher.py` — option chain with Black-Scholes Greeks

Fetches the option chain for a ticker (default: the second-nearest
expiration) and computes Black-Scholes Greeks (Delta, Gamma, Theta, Vega,
Rho) for every call and put using each contract's implied volatility.

```bash
python option_chain_fetcher.py AAPL
```

Prints the first 5 rows of calls and puts with their Greeks to the console.
The risk-free rate is currently hardcoded (4.5%) in `calculate_greeks`.

### `stock_earnings_report.py` — SEC EDGAR filings + EPS/revenue

Pulls recent earnings-related SEC filings (10-K, 10-Q, 8-K) and structured
XBRL facts (latest EPS, latest revenue) for a list of tickers, straight from
SEC EDGAR's free JSON APIs (no API key). Defaults to the QQQ/Nasdaq-100
constituents bundled in the script.

```bash
python stock_earnings_report.py
python stock_earnings_report.py --tickers AAPL MSFT NVDA
python stock_earnings_report.py --out stock_earnings.csv
```

SEC requires a descriptive `User-Agent` on every request — edit
`SEC_USER_AGENT` near the top of the script to your own name/email before
running. The script rate-limits itself to stay under SEC's 10 requests/sec
limit. Prints a console summary per ticker and writes the full result set to
CSV (`stock_earnings.csv` by default); pass `--no-console` to skip the
console summary.

### `generate_dashboard.py` — HTML dashboard of generated output

Scans this folder for the CSV/PNG output produced by the plotting scripts
above and builds an `index.html` dashboard that groups everything by ticker
(with thumbnail links to heatmap/scatter images and the underlying CSV),
plus sections for scripts and other misc files. No dependencies beyond the
standard library.

```bash
python3 generate_dashboard.py
```

Re-run any time after generating new output to refresh `index.html`.

## Notes

- All scripts that hit Yahoo Finance do so via `yfinance` or plain
  `requests` against public endpoints — no authentication, no scraping
  library, no paid data feed.
- Ticker universes bundled in these scripts (QQQ/Nasdaq-100 constituents) are
  point-in-time snapshots; the index reconstitutes annually and rebalances
  quarterly, so refresh them periodically or pass explicit tickers.
- Nothing in this repo places trades or stores credentials — it's read-only
  data retrieval, analysis, and plotting.
- [notes.txt](notes.txt) has a few example commands (commented out) for
  quick copy-paste reference — not runnable as a script itself.
