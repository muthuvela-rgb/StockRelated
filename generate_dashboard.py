#!/usr/bin/env python3
"""
generate_dashboard.py

Scans this folder for put-annualized-return CSV/PNG output and builds an
index.html dashboard that groups everything by ticker, plus a section for
misc/one-off files (strike-specific bid/ask screenshots, scripts, etc).

Run this from inside the stock_project folder any time you want to refresh
the dashboard after new files are generated:

    python3 generate_dashboard.py

Then (re)start the server + tunnel as described in TUNNEL_README.md.
"""
import os
import re
import html
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))

# Files/dirs never shown on the dashboard
EXCLUDE_EXACT = {
    "Claude.dmg", "index.html", "generate_dashboard.py",
    "TUNNEL_README.md", ".DS_Store",
    # Noisy operational files — never list these on a shared dashboard.
    "run_and_notify.log", "launchd_stdout.log", "launchd_stderr.log",
    "DAILY_NOTIFY_SETUP.md", "run_and_notify.py",
    "com.muthuvela.stockscreener.plist",
    # Superseded email-based files, in case they're still around.
    "email_config.json", "email_config.example.json",
    "run_and_email.log", "DAILY_EMAIL_SETUP.md", "run_and_email.py",
}
EXCLUDE_DIRS = {"stock_env", ".git", "__pycache__"}
EXCLUDE_EXT_AS_MAIN = {".py"}  # scripts get their own small section

TICKER_RE = re.compile(
    r"^([A-Z]{1,6})_put_annualized_returns(_heatmap|_scatter)?\.(csv|png)$"
)

def human_size(n):
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def collect():
    tickers = {}  # ticker -> {"csv": name, "heatmap": name, "scatter": name}
    scripts = []
    misc = []

    entries = sorted(os.listdir(ROOT))
    for name in entries:
        full = os.path.join(ROOT, name)
        if name in EXCLUDE_EXACT:
            continue
        if os.path.isdir(full):
            continue  # skip dirs like stock_env entirely
        if name.startswith("."):
            continue

        m = TICKER_RE.match(name)
        if m:
            ticker, kind, ext = m.group(1), m.group(2), m.group(3)
            tickers.setdefault(ticker, {})
            if ext == "csv":
                tickers[ticker]["csv"] = name
            elif kind == "_heatmap":
                tickers[ticker]["heatmap"] = name
            elif kind == "_scatter":
                tickers[ticker]["scatter"] = name
            continue

        ext = os.path.splitext(name)[1].lower()
        if ext in EXCLUDE_EXT_AS_MAIN:
            scripts.append(name)
        else:
            misc.append(name)

    return tickers, scripts, misc


def card_for_ticker(ticker, files):
    csv_link = ""
    if files.get("csv"):
        csv_link = f'<a class="pill" href="{html.escape(files["csv"])}">CSV data</a>'

    imgs = ""
    for key, label in (("heatmap", "Heatmap"), ("scatter", "Scatter")):
        if files.get(key):
            src = html.escape(files[key])
            imgs += f"""
            <a href="{src}" target="_blank" class="thumb">
              <img src="{src}" alt="{ticker} {label}" loading="lazy">
              <span>{label}</span>
            </a>"""

    if not imgs:
        imgs = '<div class="no-chart">No chart image</div>'

    return f"""
    <div class="card">
      <div class="card-head">
        <h3>{html.escape(ticker)}</h3>
        {csv_link}
      </div>
      <div class="thumbs">{imgs}</div>
    </div>"""


def section_list(title, names):
    if not names:
        return ""
    items = "\n".join(
        f'<li><a href="{html.escape(n)}">{html.escape(n)}</a> '
        f'<span class="size">{human_size(os.path.getsize(os.path.join(ROOT, n)))}</span></li>'
        for n in names
    )
    return f"""
    <section class="misc">
      <h2>{html.escape(title)}</h2>
      <ul>{items}</ul>
    </section>"""


def build_html(tickers, scripts, misc):
    cards = "\n".join(
        card_for_ticker(t, files) for t, files in sorted(tickers.items())
    )
    misc_section = section_list("Other files", misc)
    scripts_section = section_list("Scripts", scripts)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Stock Project Dashboard</title>
<style>
  :root {{
    --bg: #0b0d12; --panel: #12151c; --border: #232735; --text: #e7e9ee;
    --muted: #8b93a7; --accent: #5b8def;
  }}
  @media (prefers-color-scheme: light) {{
    :root {{ --bg:#f6f7f9; --panel:#fff; --border:#e3e5ea; --text:#1a1d24; --muted:#5b6270; --accent:#3563e0; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 32px 24px 64px; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  }}
  header {{ max-width: 1200px; margin: 0 auto 28px; }}
  h1 {{ font-size: 1.6rem; margin: 0 0 4px; }}
  .meta {{ color: var(--muted); font-size: 0.85rem; }}
  .grid {{
    max-width: 1200px; margin: 0 auto; display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px;
  }}
  .card {{
    background: var(--panel); border: 1px solid var(--border); border-radius: 12px;
    padding: 14px; display: flex; flex-direction: column; gap: 10px;
  }}
  .card-head {{ display: flex; align-items: center; justify-content: space-between; }}
  .card-head h3 {{ margin: 0; font-size: 1.05rem; letter-spacing: 0.02em; }}
  .pill {{
    font-size: 0.72rem; color: var(--accent); border: 1px solid var(--accent);
    padding: 3px 8px; border-radius: 999px; text-decoration: none; white-space: nowrap;
  }}
  .thumbs {{ display: flex; gap: 8px; flex-wrap: wrap; }}
  .thumb {{
    flex: 1 1 45%; text-decoration: none; color: var(--muted); font-size: 0.72rem;
    display: flex; flex-direction: column; gap: 4px; align-items: center;
  }}
  .thumb img {{
    width: 100%; height: 110px; object-fit: cover; border-radius: 8px; border: 1px solid var(--border);
    background: #fff;
  }}
  .no-chart {{ color: var(--muted); font-size: 0.8rem; padding: 20px 0; }}
  .misc {{ max-width: 1200px; margin: 40px auto 0; }}
  .misc h2 {{ font-size: 1.1rem; border-bottom: 1px solid var(--border); padding-bottom: 8px; }}
  .misc ul {{ list-style: none; margin: 0; padding: 0; columns: 3; column-gap: 24px; }}
  .misc li {{ break-inside: avoid; padding: 4px 0; font-size: 0.85rem; display: flex; justify-content: space-between; gap: 8px; }}
  .misc a {{ color: var(--text); text-decoration: none; }}
  .misc a:hover {{ color: var(--accent); }}
  .size {{ color: var(--muted); font-size: 0.72rem; white-space: nowrap; }}
  @media (max-width: 700px) {{ .misc ul {{ columns: 1; }} }}
</style>
</head>
<body>
<header>
  <h1>Stock Project Dashboard</h1>
  <div class="meta">Put annualized-return screening output &middot; generated {generated} &middot; {len(tickers)} tickers</div>
</header>
<div class="grid">
{cards}
</div>
{misc_section}
{scripts_section}
</body>
</html>"""


def main():
    tickers, scripts, misc = collect()
    out = build_html(tickers, scripts, misc)
    out_path = os.path.join(ROOT, "index.html")
    with open(out_path, "w") as f:
        f.write(out)
    print(f"Wrote {out_path} with {len(tickers)} ticker cards, "
          f"{len(misc)} misc files, {len(scripts)} scripts.")


if __name__ == "__main__":
    main()
