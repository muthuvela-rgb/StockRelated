#!/usr/bin/env python3
"""
stock_earnings_report.py

Pulls recent earnings-related SEC filings (10-K, 10-Q, 8-K) and structured
XBRL earnings facts (Revenue, Net Income, EPS) for a list of stock tickers.
Defaults to the current Invesco QQQ ETF holdings (Nasdaq-100 constituents),
but works for any list of US-listed tickers passed via --tickers.

Data source: SEC EDGAR (free, no API key required).
  - https://www.sec.gov/files/company_tickers.json   -> ticker -> CIK mapping
  - https://data.sec.gov/submissions/CIK##########.json -> filing history
  - https://data.sec.gov/api/xbrl/companyconcept/CIK##########/us-gaap/{TAG}.json
    -> structured historical financial facts (revenue, EPS, net income, etc.)

Usage:
    python stock_earnings_report.py                # pulls latest filings + EPS for default ticker list
    python stock_earnings_report.py --tickers AAPL MSFT NVDA   # limit to a subset
    python stock_earnings_report.py --out stock_earnings.csv   # change output file

Notes:
  - SEC requires a descriptive User-Agent header with contact info on every
    request. Edit SEC_USER_AGENT below before running.
  - SEC EDGAR rate limit is 10 requests/second. This script sleeps briefly
    between requests to stay well under that.
  - Non-financial/ETF-internal rows (cash, futures contracts, etc.) are
    excluded from the DEFAULT_TICKERS list below since they aren't operating
    companies with earnings reports.
"""

import argparse
import csv
import sys
import time
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# CONFIG — edit this before running (SEC blocks requests without a real UA)
# ---------------------------------------------------------------------------
SEC_USER_AGENT = "muthu.vela@gmail.com"  # <-- REQUIRED: replace this

HEADERS = {
    "User-Agent": SEC_USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
}

REQUEST_DELAY_SEC = 0.15  # ~6-7 req/sec, safely under SEC's 10 req/sec limit

# ---------------------------------------------------------------------------
# Default ticker universe: QQQ / Nasdaq-100 constituents (as of Aug 2026).
# Update periodically since the index reconstitutes annually and rebalances
# quarterly. Override any time with --tickers to run against a different list.
# Source: slickcharts.com/symbol/QQQ/holdings
# ---------------------------------------------------------------------------
DEFAULT_TICKERS = [
    "NVDA", "AAPL", "MSFT", "MU", "AMZN", "AMD", "GOOGL", "GOOG", "AVGO", "TSLA",
    "META", "WMT", "INTC", "CSCO", "COST", "PLTR", "AMAT", "LRCX", "NFLX", "PANW",
    "KLAC", "TXN", "SNDK", "AMGN", "LIN", "MRVL", "TMUS", "PEP", "CRWD", "STX",
    "ADI", "SHOP", "GILD", "QCOM", "BKNG", "WDC", "ASML", "VRTX", "ISRG", "SBUX",
    "ADP", "FTNT", "ADBE", "ARM", "INTU", "CEG", "MELI", "CSX", "APP", "MAR",
    "CMCSA", "MNST", "DASH", "CDNS", "REGN", "MDLZ", "CTAS", "ABNB", "DDOG", "SNPS",
    "ORLY", "ROST", "WBD", "HON", "AEP", "LITE", "PCAR", "MPWR", "BKR", "TER",
    "PDD", "FANG", "FAST", "NXPI", "PYPL", "ADSK", "ALAB", "AXON", "XEL", "NBIS",
    "CCEP", "EXC", "FER", "TTWO", "PAYX", "KDP", "IDXX", "ODFL", "RKLB", "ROP",
    "MCHP", "TRI", "CRWV", "WDAY", "MSTR", "DXCM", "GEHC", "CPRT", "ALNY", "KHC",
]
# Note: GOOGL/GOOG are dual share classes of the same company (Alphabet);
# HONA (Honeywell Aerospace) is a recent spin-off with limited filing history
# and is intentionally left out here — add it back once it has its own CIK.

SEC_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SEC_CONCEPT_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/{tag}.json"

# XBRL tags to try, in priority order, for "headline EPS"
EPS_TAGS = ["EarningsPerShareDiluted", "EarningsPerShareBasic"]
REVENUE_TAGS = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"]

EARNINGS_FORMS = {"10-K", "10-Q", "8-K"}


def get_ticker_to_cik_map() -> dict:
    """Download SEC's official ticker -> CIK mapping."""
    resp = requests.get(SEC_TICKER_MAP_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    # data is a dict of dicts: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
    return {row["ticker"].upper(): row["cik_str"] for row in data.values()}


def get_latest_filings(cik: int, limit: int = 5) -> list:
    """Return the most recent 10-K/10-Q/8-K filings for a company."""
    url = SEC_SUBMISSIONS_URL.format(cik=cik)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    recent = data.get("filings", {}).get("recent", {})

    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accns = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])

    results = []
    for form, date, accn, doc in zip(forms, dates, accns, primary_docs):
        if form in EARNINGS_FORMS:
            accn_nodash = accn.replace("-", "")
            filing_url = (
                f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn_nodash}/{doc}"
            )
            results.append({"form": form, "date": date, "url": filing_url})
        if len(results) >= limit:
            break
    return results


def get_latest_concept_value(cik: int, tags: list) -> Optional[dict]:
    """Fetch the most recent reported value for the first tag that has data."""
    for tag in tags:
        url = SEC_CONCEPT_URL.format(cik=cik, tag=tag)
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            continue
        data = resp.json()
        units = data.get("units", {})
        # units is usually {"USD": [...]} or {"USD/shares": [...]}
        for unit_name, entries in units.items():
            if not entries:
                continue
            # Prefer quarterly (10-Q) or annual (10-K) filed values, most recent first
            entries_sorted = sorted(entries, key=lambda e: e.get("end", ""), reverse=True)
            latest = entries_sorted[0]
            return {
                "tag": tag,
                "unit": unit_name,
                "value": latest.get("val"),
                "period_end": latest.get("end"),
                "fiscal_period": latest.get("fp"),
                "fiscal_year": latest.get("fy"),
                "form": latest.get("form"),
                "filed": latest.get("filed"),
            }
    return None


def format_number(value) -> str:
    """Format large numeric values with thousands separators; pass through non-numerics."""
    if value in (None, ""):
        return "N/A"
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def print_console_report(companies: list) -> None:
    """Print a human-readable summary of the collected earnings data to the console."""
    print("\n" + "=" * 78)
    print("STOCK EARNINGS REPORT".center(78))
    print("=" * 78)

    for c in companies:
        ticker = c["ticker"]
        cik = c.get("cik", "N/A")

        print(f"\n{ticker}  (CIK: {cik})")
        print("-" * 78)

        if c.get("error"):
            print(f"  {c['error']}")
            continue

        eps = c.get("eps")
        revenue = c.get("revenue")

        eps_str = format_number(eps["value"]) if eps else "N/A"
        eps_period = eps["period_end"] if eps else "N/A"
        rev_str = format_number(revenue["value"]) if revenue else "N/A"
        rev_period = revenue["period_end"] if revenue else "N/A"

        print(f"  Latest EPS:      {eps_str}  (period end: {eps_period})")
        print(f"  Latest Revenue:  {rev_str}  (period end: {rev_period})")

        filings = c.get("filings") or []
        if filings:
            print("  Recent filings:")
            for f in filings:
                print(f"    - {f['form']:<5} filed {f['date']}  ->  {f['url']}")
        else:
            print("  Recent filings:  none found")

    print("\n" + "=" * 78)
    print(f"Total companies reported: {len(companies)}")
    print("=" * 78 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Pull stock earnings reports from SEC EDGAR")
    parser.add_argument("--tickers", nargs="*", help="Limit to specific tickers (default: current QQQ/Nasdaq-100 holdings)")
    parser.add_argument("--out", default="stock_earnings.csv", help="Output CSV path")
    parser.add_argument("--filings-per-company", type=int, default=3, help="How many recent filings to list per company")
    parser.add_argument("--no-console", action="store_true", help="Skip the readable console report and only write CSV")
    args = parser.parse_args()

    if SEC_USER_AGENT.startswith("Your Name"):
        print("ERROR: Edit SEC_USER_AGENT at the top of this script with your real name/email before running.")
        sys.exit(1)

    tickers = [t.upper() for t in (args.tickers or DEFAULT_TICKERS)]

    print("Fetching SEC ticker -> CIK mapping...")
    ticker_to_cik = get_ticker_to_cik_map()

    rows = []
    companies = []  # per-company structured data, used for the console report
    for i, ticker in enumerate(tickers, 1):
        cik = ticker_to_cik.get(ticker)
        if cik is None:
            print(f"[{i}/{len(tickers)}] {ticker}: no CIK found (may be foreign private issuer, filed as 20-F/6-K) — skipping")
            companies.append({"ticker": ticker, "error": "No CIK found (may be a foreign private issuer, e.g. files 20-F/6-K)."})
            continue

        print(f"[{i}/{len(tickers)}] {ticker} (CIK {cik}): fetching filings + EPS...")
        try:
            filings = get_latest_filings(cik, limit=args.filings_per_company)
            time.sleep(REQUEST_DELAY_SEC)
            eps = get_latest_concept_value(cik, EPS_TAGS)
            time.sleep(REQUEST_DELAY_SEC)
            revenue = get_latest_concept_value(cik, REVENUE_TAGS)
            time.sleep(REQUEST_DELAY_SEC)
        except requests.RequestException as e:
            print(f"    ERROR fetching data for {ticker}: {e}")
            companies.append({"ticker": ticker, "cik": cik, "error": f"Request failed: {e}"})
            continue

        companies.append({
            "ticker": ticker,
            "cik": cik,
            "filings": filings,
            "eps": eps,
            "revenue": revenue,
        })

        for f in filings:
            rows.append({
                "ticker": ticker,
                "cik": cik,
                "filing_form": f["form"],
                "filing_date": f["date"],
                "filing_url": f["url"],
                "latest_eps_tag": eps["tag"] if eps else "",
                "latest_eps_value": eps["value"] if eps else "",
                "latest_eps_period_end": eps["period_end"] if eps else "",
                "latest_revenue_value": revenue["value"] if revenue else "",
                "latest_revenue_period_end": revenue["period_end"] if revenue else "",
            })

        if not filings:
            rows.append({
                "ticker": ticker, "cik": cik, "filing_form": "", "filing_date": "",
                "filing_url": "", "latest_eps_tag": eps["tag"] if eps else "",
                "latest_eps_value": eps["value"] if eps else "",
                "latest_eps_period_end": eps["period_end"] if eps else "",
                "latest_revenue_value": revenue["value"] if revenue else "",
                "latest_revenue_period_end": revenue["period_end"] if revenue else "",
            })

    if not args.no_console and companies:
        print_console_report(companies)

    if rows:
        with open(args.out, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"Done. Wrote {len(rows)} rows to {args.out}")
    else:
        print("No data collected.")


if __name__ == "__main__":
    main()
