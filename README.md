# Stock-fall

Given a list of stocks, find any that fell more than a configurable percentage
(default 10%) within a configurable lookback window (default 1 week), limited
to stocks whose market cap **before** the fall exceeded a configurable
threshold (default $10B).

## Install

```bash
pip install -r requirements.txt
```

## Usage

```bash
python -m stock_fall_detector.cli AAPL MSFT TSLA NVDA
```

### Options

| Flag | Default | Meaning |
|---|---|---|
| `--days` | `7` | Lookback window in calendar days |
| `--fall-pct` | `10` | Minimum percentage drop to flag a stock |
| `--min-market-cap` | `10000000000` ($10B) | Minimum market cap at the *start* of the window |

### Example

```bash
python -m stock_fall_detector.cli AAPL MSFT TSLA NVDA META --days 7 --fall-pct 10 --min-market-cap 10000000000
```

Output lists each qualifying ticker with its start/end price, percentage
change, and market cap (in $B) before the fall, sorted worst-first.

## How it works

For each ticker, the tool fetches recent daily closing prices from Yahoo
Finance and shares outstanding. It computes:

- `market_cap_before = start_price * shares_outstanding`
- `pct_change = (end_price - start_price) / start_price * 100`

A stock is reported if `market_cap_before` exceeds `--min-market-cap` **and**
`pct_change` is a drop of at least `--fall-pct`.

## Tests

The core detection logic (`stock_fall_detector.detector.find_falling_stocks`)
is decoupled from the data source via a small `PriceDataSource` protocol, so
tests run offline against fake data:

```bash
pytest
```
