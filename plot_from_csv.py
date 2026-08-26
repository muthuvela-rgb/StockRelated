"""
Plot Option Premium from CSV
-----------------------------------------------------------------------------
Standalone plotting script — no internet/API calls. Reads a CSV (like the
ones produced by qqq_580_put_bid_plot.py) and plots premium vs expiration.

Requires: pandas, matplotlib
    pip install pandas matplotlib

Run:
    python plot_from_csv.py --csv QQQ_580_put_bids.csv
    python plot_from_csv.py --csv MU_600_put_asks.csv --column ask
    python plot_from_csv.py --csv data.csv --column bid --x expiration --title "My Chart"
    python plot_from_csv.py --csv data.csv --output my_chart.png
    python plot_from_csv.py --csv data.csv --no-knee
    python plot_from_csv.py --csv data.csv --window-days 45
    python plot_from_csv.py --csv data.csv --method interpolate
    python plot_from_csv.py --csv data.csv --no-steepest
    python plot_from_csv.py --csv data.csv --by-month

Options:
    --csv          Path to the input CSV file (required)
    --x            Column name to use for the X-axis (default: auto-detect,
                   looks for "expiration" or "date")
    --column       Column name to use for the Y-axis / price (default:
                   auto-detect "bid" or "ask", whichever is present)
    --title        Custom chart title (default: auto-generated from filename)
    --output       Output PNG filename (default: <csv-name>_plot.png)
    --no-show      Don't open an interactive window, just save the PNG
    --no-knee      Skip knee-of-the-curve detection/annotation
    --no-steepest  Skip steepest-N-day-window detection/annotation
    --window-days  Window size in days for steepest-slope detection
                   (default: 30)
    --method       Steepest-window algorithm: "regression" (default) or
                   "interpolate" (see below)
    --min-points   Minimum real data points required in a window for
                   --method regression (default: 2)
    --by-month     Also compute slope for each calendar month (1st-to-1st)
                   and report the steepest one (see below)
    --month-min-points  Minimum real data points required inside a calendar
                   month for it to be eligible to win --by-month (default:
                   1). Use 0 to allow a purely-interpolated month to win.

Knee-of-the-curve detection:
    By default the script finds the "knee" (a.k.a. elbow) of the curve — the
    point where the curve bends most sharply away from a straight line drawn
    between its first and last points. For an option premium curve, this is
    often the expiration where time value starts accelerating (or where
    the growth rate visibly changes), which can be a useful reference point
    when comparing near-dated vs. far-dated contracts. The knee point is
    marked with a red star on the chart and printed to the console. Use
    --no-knee to turn this off.

    Method: classic "distance-to-chord" elbow detection. Both axes are
    normalized to [0, 1], a straight line ("chord") is drawn between the
    first and last data points, and the point with the maximum perpendicular
    distance from that chord is chosen as the knee. This works for both
    convex and concave curve shapes and needs no extra dependencies.
    Requires at least 3 data points.

Steepest N-day window detection:
    By default the script also finds the N-day period (30 days = ~1 month,
    configurable via --window-days) over which the curve rises fastest in
    $/day. This is where the premium is growing most quickly with time —
    useful for spotting, e.g., the month where extra time value gets priced
    in fastest. The window is shaded green on the chart with a dashed trend
    line and annotation. Use --no-steepest to turn this off.

    Two algorithms are available via --method:

    "regression" (default, recommended):
        Only uses REAL data points — no fabricated values. For every real
        data point, treat it as a candidate window start and collect all
        real points that fall within [start, start + window_days]. If at
        least --min-points real points fall in that window (default: 2), fit
        a least-squares regression line through them and take its slope as
        the window's $/day rate. Windows without enough real points are
        skipped. The result is always grounded in observed data, and the
        console/annotation report how many real points backed the answer.

    "interpolate" (legacy, for comparison):
        Linearly interpolates the curve onto a daily grid first, then slides
        a window across that grid. This can be misleading with sparse data
        (e.g. quarterly LEAPS expirations): the "steepest window" can end up
        reflecting an artifact of the straight-line interpolation between
        two distant real points rather than anything actually observed in
        the market. Kept available for comparison, but --method regression
        is the more defensible choice for irregularly-spaced option data.

Calendar-month slope detection (--by-month, off by default):
    Computes the slope from the 1st of each calendar month to the 1st of
    the next (e.g. 2027-03-01 to 2027-04-01), across every full calendar
    month contained in the data's date range, and reports the steepest one.
    This is a more intuitive framing than a sliding window if you think in
    terms of "which month" rather than "which 30-day span starting
    anywhere."

    Since real data points rarely land exactly on the 1st of a month, the
    value at each month boundary is estimated via linear interpolation
    between the two nearest real points. A full table of all months (with a
    "Real pts" / "Qualifies" column showing how many actual data points fall
    inside each month) is printed to the console, and the winning month is
    shaded purple on the chart.

    By default, a month must contain at least 1 real data point
    (--month-min-points, default: 1) to be eligible to win — this prevents a
    data-sparse gap (e.g. between two far-apart LEAPS expirations) from
    winning purely on interpolation with nothing real behind it. Raise
    --month-min-points for a stricter requirement (e.g. 2, to require the
    month's slope be backed by two real observed quotes), or set it to 0 to
    restore the old behavior of allowing any month — including a 0-point,
    pure-interpolation one — to win. Only months fully inside the data's
    date range are evaluated (no extrapolation past the first/last data
    point).

Expected CSV format (flexible):
    Must have a date-like column (e.g. "expiration") and a numeric price
    column (e.g. "bid" or "ask"). If present, a boolean "used_fallback"
    column will be used to highlight points where lastPrice was substituted
    for a zero bid/ask (matches the output of qqq_580_put_bid_plot.py), but
    the script works fine without it too — any two-column CSV with a date
    and a number will plot.
"""

import argparse
import sys
import os

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def parse_args():
    parser = argparse.ArgumentParser(
        description="Plot a price/expiration CSV (e.g. option bid or ask premiums) as a line+scatter chart."
    )
    parser.add_argument("--csv", type=str, required=True,
                         help="Path to the input CSV file")
    parser.add_argument("--x", type=str, default=None,
                         help='Column to use for X-axis (default: auto-detect "expiration" or "date")')
    parser.add_argument("--column", type=str, default=None,
                         help='Column to use for Y-axis (default: auto-detect "bid" or "ask")')
    parser.add_argument("--title", type=str, default=None,
                         help="Custom chart title")
    parser.add_argument("--output", type=str, default=None,
                         help="Output PNG filename (default: <csv-name>_plot.png)")
    parser.add_argument("--no-show", action="store_true",
                         help="Don't open an interactive window, just save the PNG")
    parser.add_argument("--no-knee", action="store_true",
                         help="Skip knee-of-the-curve detection/annotation")
    parser.add_argument("--no-steepest", action="store_true",
                         help="Skip steepest-N-day-window detection/annotation")
    parser.add_argument("--window-days", type=int, default=30,
                         help="Window size in days for steepest-slope detection (default: 30)")
    parser.add_argument("--method", type=str, default="regression",
                         choices=["regression", "interpolate"],
                         help='Steepest-window algorithm: "regression" (default) fits a line '
                              'through real data points only; "interpolate" fills gaps with a '
                              'linear-interpolated daily grid (can be misleading with sparse data).')
    parser.add_argument("--min-points", type=int, default=2,
                         help="Minimum real data points required in a window for --method regression "
                              "(default: 2)")
    parser.add_argument("--by-month", action="store_true",
                         help="Also compute slope for each calendar month (1st-to-1st) and report "
                              "the steepest one. Prints a per-month table and shades the winning "
                              "month in purple on the chart.")
    parser.add_argument("--month-min-points", type=int, default=1,
                         help="Minimum real data points required inside a calendar month for it to "
                              "be eligible to win --by-month (default: 1). Set to 0 to allow months "
                              "with no real data (pure interpolation) to win.")
    return parser.parse_args()


def detect_x_column(df):
    candidates = ["expiration", "date", "expiry", "exp_date"]
    for c in candidates:
        if c in df.columns:
            return c
    # fallback: first column that parses as a date
    for c in df.columns:
        try:
            pd.to_datetime(df[c])
            return c
        except Exception:
            continue
    sys.exit(f"Could not find a date/expiration column. Available columns: {list(df.columns)}. "
              f"Use --x to specify one.")


def detect_y_column(df, x_col):
    candidates = ["bid", "ask", "lastprice", "last", "price", "premium"]
    lower_map = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c in lower_map:
            return lower_map[c]
    # fallback: first numeric column that isn't the x column
    for c in df.columns:
        if c == x_col:
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            return c
    sys.exit(f"Could not find a numeric price column. Available columns: {list(df.columns)}. "
              f"Use --column to specify one.")


def find_knee_point(x_vals, y_vals):
    """
    Find the "knee" (elbow) of a curve using the distance-to-chord method:
    normalize both axes to [0, 1], draw a straight line ("chord") between
    the first and last points, and return the index of the point with the
    maximum perpendicular distance from that chord.

    Works for both convex and concave curve shapes. Returns None if there
    are fewer than 3 points (a knee isn't well-defined with 2 points).
    """
    n = len(x_vals)
    if n < 3:
        return None

    x = np.asarray(x_vals, dtype=float)
    y = np.asarray(y_vals, dtype=float)

    x_range = x.max() - x.min()
    y_range = y.max() - y.min()
    if x_range == 0 or y_range == 0:
        return None  # flat/degenerate data, no meaningful knee

    x_norm = (x - x.min()) / x_range
    y_norm = (y - y.min()) / y_range

    x1, y1 = x_norm[0], y_norm[0]
    x2, y2 = x_norm[-1], y_norm[-1]

    # Perpendicular distance of each point from the line through (x1,y1)-(x2,y2)
    numerator = np.abs((y2 - y1) * x_norm - (x2 - x1) * y_norm + x2 * y1 - y2 * x1)
    denominator = np.sqrt((y2 - y1) ** 2 + (x2 - x1) ** 2)
    distances = numerator / denominator

    return int(np.argmax(distances))


def find_steepest_window_interpolate(x_dates, y_vals, window_days=30):
    """
    Find the N-day window (default 30, i.e. ~1 month) where the curve rises
    fastest, in $/day, using linear interpolation onto a daily grid.

    CAVEAT: this method fabricates values between real data points via
    interpolation. If your data points are sparse (e.g. quarterly LEAPS
    expirations), the "steepest window" can end up reflecting an artifact of
    the straight-line interpolation between two distant real points rather
    than anything actually observed in the market. Prefer
    find_steepest_window_regression() when possible — this method is kept
    for comparison via --method interpolate.

    Returns a dict with start_date, end_date, y_start, y_end, slope_per_day,
    and slope_per_window (total $ change across the window) — or None if the
    data doesn't span at least `window_days`.
    """
    x_dates = pd.to_datetime(pd.Series(x_dates)).reset_index(drop=True)
    y_vals = np.asarray(y_vals, dtype=float)

    if len(x_dates) < 2:
        return None

    start_date = x_dates.min()
    end_date = x_dates.max()
    total_days = (end_date - start_date).days

    if total_days < window_days:
        return None  # curve doesn't span a full window

    # Interpolate onto a daily grid so the sliding window is well-defined
    # regardless of how irregularly the original expirations are spaced.
    x_days = (x_dates - start_date).dt.days.values.astype(float)
    grid_days = np.arange(0, total_days + 1)  # one point per calendar day
    grid_y = np.interp(grid_days, x_days, y_vals)

    n_windows = len(grid_days) - window_days
    if n_windows <= 0:
        return None

    slopes = (grid_y[window_days:window_days + n_windows] - grid_y[0:n_windows]) / window_days
    best_start_idx = int(np.argmax(slopes))

    win_start_date = start_date + pd.Timedelta(days=int(grid_days[best_start_idx]))
    win_end_date = start_date + pd.Timedelta(days=int(grid_days[best_start_idx]) + window_days)
    y_start = grid_y[best_start_idx]
    y_end = grid_y[best_start_idx + window_days]

    return {
        "start_date": win_start_date,
        "end_date": win_end_date,
        "y_start": y_start,
        "y_end": y_end,
        "slope_per_day": slopes[best_start_idx],
        "slope_per_window": y_end - y_start,
        "n_real_points": None,  # not tracked for this method
        "method": "interpolate",
    }


def find_steepest_window_regression(x_dates, y_vals, window_days=30, min_points=2):
    """
    Find the N-day window where the curve rises fastest, in $/day, using
    ONLY real data points (no fabricated/interpolated values).

    For every real data point, treat it as a candidate window start and
    collect all real points that fall within [start, start + window_days].
    If at least `min_points` real points fall in that window, fit a
    least-squares regression line through them (using actual elapsed days as
    x) and take its slope as the window's $/day rate. This smooths out noise
    when 3+ points are available and is exact (a simple two-point slope)
    when exactly 2 points are available. Windows with fewer than min_points
    real points are skipped, so the result is always grounded in observed
    data — never fabricated.

    Returns a dict with start_date, end_date, y_start, y_end (regression
    fitted values at the window edges), slope_per_day, slope_per_window,
    and n_real_points — or None if no window has enough real points.
    """
    x_dates = pd.to_datetime(pd.Series(x_dates)).reset_index(drop=True)
    y_vals = np.asarray(y_vals, dtype=float)
    n = len(x_dates)

    if n < min_points:
        return None

    start_ref = x_dates.min()
    x_days_all = (x_dates - start_ref).dt.days.values.astype(float)

    best = None
    for i in range(n):
        win_start_day = x_days_all[i]
        win_end_day = win_start_day + window_days

        mask = (x_days_all >= win_start_day) & (x_days_all <= win_end_day)
        n_pts = int(mask.sum())
        if n_pts < min_points:
            continue

        win_x = x_days_all[mask]
        win_y = y_vals[mask]

        if win_x.max() == win_x.min():
            continue  # all points on the same day, slope undefined

        # Least-squares line fit: y = m*x + b
        m, b = np.polyfit(win_x, win_y, 1)

        if best is None or m > best["slope_per_day"]:
            y_start = m * win_start_day + b
            y_end = m * win_end_day + b
            best = {
                "start_date": start_ref + pd.Timedelta(days=win_start_day),
                "end_date": start_ref + pd.Timedelta(days=win_end_day),
                "y_start": y_start,
                "y_end": y_end,
                "slope_per_day": m,
                "slope_per_window": y_end - y_start,
                "n_real_points": n_pts,
                "method": "regression",
            }

    return best


def find_steepest_calendar_month(x_dates, y_vals, min_points=1):
    """
    Compute the slope ($/day) across each calendar month (1st of month to
    1st of the following month) spanned by the data, and identify the
    steepest one AMONG MONTHS THAT HAVE AT LEAST `min_points` REAL DATA
    POINTS inside them.

    Since real data points rarely fall exactly on the 1st of a month, the
    value at each month boundary is estimated via linear interpolation
    between the two nearest real data points (using np.interp against all
    real points, sorted by date). Only months fully contained within the
    data's date range are evaluated — partial months at the very start or
    end of the data (where interpolation would require extrapolating beyond
    the real data) are skipped.

    A month can still have a computed slope with 0 real points inside it
    (pure interpolation across a data-sparse gap) — those months are
    included in `all_months` for transparency, but excluded from the
    "steepest" pick unless min_points=0. Set min_points=0 to allow any
    month, including data-sparse ones, to win.

    Returns (best, all_months):
        best       - dict for the steepest QUALIFYING month (>= min_points
                     real points), or None if no month qualifies.
        all_months - list of dicts (one per evaluated month, including
                     non-qualifying ones), each with month_label,
                     start_date, end_date, y_start, y_end, slope_per_day,
                     slope_per_month, days_in_month, n_real_points, and
                     qualifies (bool, whether it met min_points).
    """
    x_dates = pd.to_datetime(pd.Series(x_dates)).reset_index(drop=True)
    y_vals = np.asarray(y_vals, dtype=float)

    if len(x_dates) < 2:
        return None, []

    data_min = x_dates.min()
    data_max = x_dates.max()
    x_days_all = (x_dates - data_min).dt.days.values.astype(float)

    # Walk through every calendar month touched by the data range.
    months = []
    cursor = pd.Timestamp(year=data_min.year, month=data_min.month, day=1)
    while cursor <= data_max:
        month_end = cursor + pd.DateOffset(months=1)
        months.append((cursor, month_end))
        cursor = month_end

    all_months = []
    for month_start, month_end in months:
        if month_start < data_min or month_end > data_max:
            continue  # partial month at the edge of the data — would require extrapolation

        start_day = (month_start - data_min).days
        end_day = (month_end - data_min).days
        days_in_month = end_day - start_day
        if days_in_month <= 0:
            continue

        y_start = float(np.interp(start_day, x_days_all, y_vals))
        y_end = float(np.interp(end_day, x_days_all, y_vals))
        n_real_points = int(((x_days_all >= start_day) & (x_days_all <= end_day)).sum())

        all_months.append({
            "month_label": month_start.strftime("%Y-%m"),
            "start_date": month_start,
            "end_date": month_end,
            "y_start": y_start,
            "y_end": y_end,
            "slope_per_day": (y_end - y_start) / days_in_month,
            "slope_per_month": y_end - y_start,
            "days_in_month": days_in_month,
            "n_real_points": n_real_points,
            "qualifies": n_real_points >= min_points,
        })

    if not all_months:
        return None, []

    qualifying = [m for m in all_months if m["qualifies"]]
    if not qualifying:
        return None, all_months

    best = max(qualifying, key=lambda m: m["slope_per_day"])
    return best, all_months


def main():
    args = parse_args()

    if not os.path.isfile(args.csv):
        sys.exit(f"File not found: {args.csv}")

    df = pd.read_csv(args.csv)
    if df.empty:
        sys.exit("CSV file is empty — nothing to plot.")

    x_col = args.x or detect_x_column(df)
    y_col = args.column or detect_y_column(df, x_col)

    if x_col not in df.columns:
        sys.exit(f"X column '{x_col}' not found in CSV. Available columns: {list(df.columns)}")
    if y_col not in df.columns:
        sys.exit(f"Y column '{y_col}' not found in CSV. Available columns: {list(df.columns)}")

    df[x_col] = pd.to_datetime(df[x_col])
    df = df.sort_values(x_col)
    df[y_col] = pd.to_numeric(df[y_col], errors="coerce")
    df = df.dropna(subset=[y_col])

    if df.empty:
        sys.exit(f"No valid numeric data found in column '{y_col}' — nothing to plot.")

    has_fallback_flag = "used_fallback" in df.columns

    print(f"Plotting {len(df)} rows: X = '{x_col}', Y = '{y_col}'")

    knee_idx = None
    if not args.no_knee:
        x_numeric = pd.to_numeric(df[x_col])  # nanoseconds since epoch, for even spacing math
        knee_idx = find_knee_point(x_numeric.values, df[y_col].values)
        if knee_idx is not None:
            knee_row = df.iloc[knee_idx]
            knee_x = knee_row[x_col]
            knee_y = knee_row[y_col]
            knee_date_str = pd.Timestamp(knee_x).strftime("%Y-%m-%d")
            print(f"Knee of the curve: {x_col} = {knee_date_str}, {y_col} = {knee_y:.4f}")
        else:
            print("Knee detection skipped (need at least 3 points with non-flat data).")

    steepest = None
    if not args.no_steepest:
        if args.method == "regression":
            steepest = find_steepest_window_regression(
                df[x_col], df[y_col].values, window_days=args.window_days, min_points=args.min_points
            )
        else:
            steepest = find_steepest_window_interpolate(
                df[x_col], df[y_col].values, window_days=args.window_days
            )

        if steepest is not None:
            pts_note = f", {steepest['n_real_points']} real points" if steepest.get("n_real_points") else ""
            print(f"Steepest {args.window_days}-day window [{steepest['method']}]: "
                  f"{steepest['start_date'].strftime('%Y-%m-%d')} to "
                  f"{steepest['end_date'].strftime('%Y-%m-%d')}  "
                  f"({y_col} {steepest['y_start']:.4f} -> {steepest['y_end']:.4f}, "
                  f"+{steepest['slope_per_window']:.4f} total, "
                  f"{steepest['slope_per_day']:.5f}/day{pts_note})")
        else:
            reason = (f"need at least {args.min_points} real data points within some "
                      f"{args.window_days}-day span" if args.method == "regression"
                      else f"data doesn't span a full {args.window_days}-day period")
            print(f"Steepest-window detection skipped ({reason}).")

    best_month = None
    if args.by_month:
        best_month, all_months = find_steepest_calendar_month(
            df[x_col], df[y_col].values, min_points=args.month_min_points
        )
        if all_months:
            print(f"\nCalendar-month slopes ({y_col}, $/day), "
                  f"requiring >= {args.month_min_points} real point(s) to qualify:")
            print(f"{'Month':<10} {'Start':>10} {'End':>10} {y_col.capitalize()+' start':>14} "
                  f"{y_col.capitalize()+' end':>12} {'Slope/day':>12} {'Real pts':>9}  {'Qualifies':<9}")
            for m in all_months:
                marker = "  <== steepest" if m is best_month else ""
                qual = "yes" if m["qualifies"] else "no"
                print(f"{m['month_label']:<10} {m['start_date'].strftime('%Y-%m-%d'):>10} "
                      f"{m['end_date'].strftime('%Y-%m-%d'):>10} {m['y_start']:>14.4f} "
                      f"{m['y_end']:>12.4f} {m['slope_per_day']:>12.5f} {m['n_real_points']:>9}  "
                      f"{qual:<9}{marker}")
            if best_month is not None:
                print(f"\nSteepest calendar month: {best_month['month_label']} "
                      f"({y_col} {best_month['y_start']:.4f} -> {best_month['y_end']:.4f}, "
                      f"+{best_month['slope_per_month']:.4f} total, "
                      f"{best_month['slope_per_day']:.5f}/day, "
                      f"{best_month['n_real_points']} real points in that month)")
            else:
                print(f"\nNo calendar month has >= {args.month_min_points} real data point(s) — "
                      f"none qualify. Lower --month-min-points (e.g. --month-min-points 0) to allow "
                      f"a purely-interpolated month to win, or provide denser data.")
        else:
            print("Calendar-month detection skipped (no full calendar month is contained "
                  "within the data's date range).")

    plt.figure(figsize=(12, 6))
    plt.plot(df[x_col], df[y_col], linewidth=1.5, color="tab:blue", zorder=1)

    if has_fallback_flag:
        real_pts = df[~df["used_fallback"].astype(bool)]
        fallback_pts = df[df["used_fallback"].astype(bool)]
        plt.scatter(real_pts[x_col], real_pts[y_col], color="tab:blue", label=y_col.capitalize(), zorder=2)
        if not fallback_pts.empty:
            plt.scatter(fallback_pts[x_col], fallback_pts[y_col], color="tab:orange",
                        marker="^", label="lastPrice (bid/ask were 0)", zorder=3)
            plt.legend()
    else:
        plt.scatter(df[x_col], df[y_col], color="tab:blue", zorder=2)

    if knee_idx is not None:
        knee_row = df.iloc[knee_idx]
        plt.scatter([knee_row[x_col]], [knee_row[y_col]], color="red", marker="*",
                    s=300, zorder=4, label="Knee of curve",
                    edgecolors="black", linewidths=0.5)
        knee_date_str = pd.Timestamp(knee_row[x_col]).strftime("%Y-%m-%d")
        plt.annotate(
            f"Knee\n{knee_date_str}\n{y_col}={knee_row[y_col]:.2f}",
            xy=(knee_row[x_col], knee_row[y_col]),
            xytext=(15, 15), textcoords="offset points",
            fontsize=9, color="red",
            arrowprops=dict(arrowstyle="->", color="red", lw=1),
        )
        plt.legend()

    if steepest is not None:
        plt.axvspan(steepest["start_date"], steepest["end_date"],
                    color="green", alpha=0.15, zorder=0, label="Steepest window")
        plt.plot([steepest["start_date"], steepest["end_date"]],
                  [steepest["y_start"], steepest["y_end"]],
                  color="green", linewidth=2.5, zorder=3, linestyle="--")
        mid_date = steepest["start_date"] + (steepest["end_date"] - steepest["start_date"]) / 2
        mid_y = (steepest["y_start"] + steepest["y_end"]) / 2
        pts_note = f"\n({steepest['n_real_points']} real pts)" if steepest.get("n_real_points") else ""
        plt.annotate(
            f"Steepest {args.window_days}d window\n"
            f"{steepest['start_date'].strftime('%Y-%m-%d')} to {steepest['end_date'].strftime('%Y-%m-%d')}\n"
            f"+{steepest['slope_per_window']:.2f} ({steepest['slope_per_day']:.4f}/day){pts_note}",
            xy=(mid_date, mid_y),
            xytext=(-140, -40), textcoords="offset points",
            fontsize=9, color="green",
            arrowprops=dict(arrowstyle="->", color="green", lw=1),
        )
        plt.legend()

    if best_month is not None:
        plt.axvspan(best_month["start_date"], best_month["end_date"],
                    color="purple", alpha=0.15, zorder=0, label="Steepest calendar month")
        plt.plot([best_month["start_date"], best_month["end_date"]],
                  [best_month["y_start"], best_month["y_end"]],
                  color="purple", linewidth=2.5, zorder=3, linestyle=":")
        mid_date = best_month["start_date"] + (best_month["end_date"] - best_month["start_date"]) / 2
        mid_y = (best_month["y_start"] + best_month["y_end"]) / 2
        plt.annotate(
            f"Steepest month: {best_month['month_label']}\n"
            f"+{best_month['slope_per_month']:.2f} ({best_month['slope_per_day']:.4f}/day)\n"
            f"({best_month['n_real_points']} real pts)",
            xy=(mid_date, mid_y),
            xytext=(15, -40), textcoords="offset points",
            fontsize=9, color="purple",
            arrowprops=dict(arrowstyle="->", color="purple", lw=1),
        )
        plt.legend()

    csv_basename = os.path.splitext(os.path.basename(args.csv))[0]
    title = args.title or f"{csv_basename} — {y_col.capitalize()} by {x_col.capitalize()}"
    plt.title(title)
    plt.xlabel(x_col.capitalize())
    plt.ylabel(f"{y_col.capitalize()} ($)")
    plt.xticks(rotation=45, ha="right")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()

    output_png = args.output or f"{csv_basename}_plot.png"
    plt.savefig(output_png, dpi=150)
    print(f"Saved chart to {output_png}")

    if not args.no_show:
        plt.show()


if __name__ == "__main__":
    main()
