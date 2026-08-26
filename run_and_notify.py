#!/usr/bin/env python3
"""
run_and_notify.py

Runs the short-dated put screener with your standard daily filters, saves
the full results to short_dated_put_screen.csv (overwritten each run),
writes the full console output (every line the screener printed — the
per-ticker scan and the full TOP N table) to a dated file under logs/, and
pops a macOS notification banner with a one-line summary of just the best
result (the CSV is too big and the notification can only fit one line —
the dated log file is the place to see everything), and copies that dated
log file into your Google Drive (via the Google Drive for desktop sync
folder — no API credentials involved, Drive's own background sync uploads
it from there). No email, no credentials stored anywhere.

Intended to be triggered by launchd every morning (see
com.muthuvela.stockscreener.plist) — you can also run it by hand any time
to test:

    python3 run_and_notify.py
"""
import csv
import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
SCREENER = os.path.join(ROOT, "short_dated_put_screener.py")
LOG_PATH = os.path.join(ROOT, "run_and_notify.log")
LOG_DIR = os.path.join(ROOT, "logs")

# The daily command: python short_dated_put_screener.py --max 90 --days 45
SCREENER_ARGS = ["--max-moneyness", "90", "--days", "45"]
OUTPUT_CSV = os.path.join(ROOT, "short_dated_put_screen.csv")

# Google Drive for desktop's local sync folder. Anything copied in here is
# uploaded automatically by Drive's own background sync — no API/OAuth
# credentials needed in this script. Adjust if your Drive account or the
# sync folder location ever changes.
DRIVE_ROOT = os.path.expanduser(
    "~/Library/CloudStorage/GoogleDrive-muthu.vela@gmail.com/My Drive"
)
DRIVE_LOG_DIR = os.path.join(DRIVE_ROOT, "stock_screener_logs")


def console_log_path(today_str):
    return os.path.join(LOG_DIR, f"screen_{today_str}.log")


def write_console_log(today_str, ok, output):
    """Appends the screener's full console output to a dated log file under
    logs/, so the complete per-ticker scan + full TOP N table is available
    without having to open the (large) CSV. Appends rather than overwrites
    so multiple runs on the same day (e.g. a manual test plus the scheduled
    run) are all preserved, most recent last."""
    os.makedirs(LOG_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "OK" if ok else "NO MATCHES / NON-ZERO EXIT"
    header = f"\n{'=' * 70}\nRun at {stamp} — {status}\nCommand: {sys.executable} short_dated_put_screener.py {' '.join(SCREENER_ARGS)}\n{'=' * 70}\n"
    path = console_log_path(today_str)
    with open(path, "a") as f:
        f.write(header)
        f.write(output + "\n")
    return path


def copy_to_drive(console_path):
    """Copies the day's console log into the Google Drive sync folder so
    Drive's background sync uploads it. Returns True on success, False if
    the Drive folder isn't there (e.g. Drive app not running/not signed in)
    or the copy otherwise fails — never raises, since a Drive hiccup
    shouldn't stop the notification from showing."""
    if not os.path.isdir(DRIVE_ROOT):
        log(f"Google Drive sync folder not found at {DRIVE_ROOT} — skipping Drive copy "
            f"(is Google Drive for desktop installed and signed in?).")
        return False
    try:
        os.makedirs(DRIVE_LOG_DIR, exist_ok=True)
        dest = os.path.join(DRIVE_LOG_DIR, os.path.basename(console_path))
        shutil.copy2(console_path, dest)
        log(f"Copied log to Drive: {dest}")
        return True
    except Exception:
        log("Failed to copy log to Drive:\n" + traceback.format_exc())
        return False


def log(msg):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {msg}"
    print(line)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")


def run_screener():
    """Runs the screener, capturing stdout/stderr. Returns (ok, output_text)."""
    result = subprocess.run(
        [sys.executable, SCREENER, *SCREENER_ARGS],
        cwd=ROOT, capture_output=True, text=True,
    )
    output = (result.stdout or "") + (("\n" + result.stderr) if result.stderr else "")
    ok = result.returncode == 0
    return ok, output.strip()


def top_row_summary():
    """Reads the freshly-written CSV (sorted by annualized_return_pct desc)
    and returns a one-line summary of the best row, or None if unavailable."""
    if not os.path.exists(OUTPUT_CSV):
        return None
    try:
        with open(OUTPUT_CSV, newline="") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            return None
        r = rows[0]
        return (f"{r['ticker']} ${r['strike']} put exp {r['expiration']} — "
                f"{r['annualized_return_pct']}% annualized, bid ${r['bid']}")
    except Exception:
        return None


def notify(title, message, subtitle=""):
    """Pops a macOS notification banner via AppleScript."""
    def esc(s):
        return s.replace("\\", "\\\\").replace('"', '\\"')

    script = f'display notification "{esc(message)}" with title "{esc(title)}"'
    if subtitle:
        script += f' subtitle "{esc(subtitle)}"'
    try:
        subprocess.run(["osascript", "-e", script], check=True)
    except Exception:
        log("Failed to show notification:\n" + traceback.format_exc())


def main():
    log("Starting daily short-dated put screen run.")
    today_str = datetime.now().strftime("%Y-%m-%d")

    try:
        ok, output = run_screener()
    except Exception:
        err = traceback.format_exc()
        log("Screener crashed:\n" + err)
        crash_log = write_console_log(today_str, False, "SCREENER CRASHED:\n" + err)
        copy_to_drive(crash_log)
        notify("Put screener FAILED", f"Crashed on {today_str} — see logs/screen_{today_str}.log")
        return

    console_path = write_console_log(today_str, ok, output)
    console_rel = os.path.relpath(console_path, ROOT)
    copy_to_drive(console_path)

    if ok:
        summary = top_row_summary()
        n_rows = 0
        if os.path.exists(OUTPUT_CSV):
            with open(OUTPUT_CSV, newline="") as f:
                n_rows = sum(1 for _ in csv.reader(f)) - 1  # minus header
        log(f"Screener succeeded, {n_rows} result(s). Top: {summary}. Full output: {console_rel}")
        if summary:
            notify("Put screener results", summary, subtitle=f"{n_rows} matches today")
        else:
            notify("Put screener results", f"{n_rows} matches today — see {console_rel}")
    else:
        # Non-zero exit usually means "no options matched the filters today"
        # (the script calls sys.exit with a message in that case) rather than
        # a real crash, but treat it as informational either way.
        log(f"Screener returned non-zero exit (likely no matches). Full output: {console_rel}")
        notify("Put screener", "No matches today", subtitle=today_str)


if __name__ == "__main__":
    main()
