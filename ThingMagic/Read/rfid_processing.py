#!/usr/bin/env python3
"""
Process RFID phase-read CSV files with zero-lag, centered smoothing.

This version intentionally avoids causal exponential smoothing lag. It is meant for
OFFLINE CSV analysis: each smoothed point may use reads before and after that point.

For each input CSV, it:
  1. Parses timestamps, including Unix epoch milliseconds.
  2. Groups reads by tag/EPC and antenna.
  3. Sorts reads by time within each group.
  4. Unwraps phase measurements.
  5. Optionally removes isolated spikes with a centered Hampel filter.
  6. Applies centered time-window smoothing, defaulting to a Gaussian-weighted mean.
  7. Writes one processed CSV per input CSV.
  8. Writes one plot per input CSV + antenna, with all tags on one plot.

Example:
    python process_rfid_phase_zero_lag.py "reads*.csv" \
      --output-dir rfid_processed_zero_lag \
      --timestamp-unit ms \
      --smooth-window 1500ms \
      --smooth-sigma 500ms \
      --show-raw-in-plots

Good starting point for the files you uploaded:
    --phase-unit degrees --wrap-period 180 --hampel-window 750ms \
    --smooth-method gaussian --smooth-window 1500ms --smooth-sigma 500ms
"""

from __future__ import annotations

import argparse
import glob
import math
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def expand_input_paths(patterns: Iterable[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        matches = glob.glob(pattern)
        if matches:
            paths.extend(Path(m) for m in matches)
        else:
            paths.append(Path(pattern))

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        path = path.expanduser()
        if path not in seen:
            unique.append(path)
            seen.add(path)
    return unique


def safe_name(value: object) -> str:
    text = str(value)
    for ch in ['/', '\\', ':', '*', '?', '"', '<', '>', '|', ' ']:
        text = text.replace(ch, '_')
    return text


def parse_duration_seconds(duration: str) -> float:
    seconds = pd.Timedelta(duration).total_seconds()
    if seconds <= 0:
        raise ValueError(f"Duration must be positive, got {duration!r}")
    return seconds


def parse_timestamps(
    values: pd.Series,
    timestamp_unit: str | None = "auto",
    timestamp_format: str | None = None,
    dayfirst: bool = False,
) -> pd.Series:
    if timestamp_unit and timestamp_unit != "auto":
        numeric = pd.to_numeric(values, errors="coerce")
        return pd.to_datetime(numeric, unit=timestamp_unit, errors="coerce")

    if timestamp_format is not None:
        return pd.to_datetime(values, format=timestamp_format, errors="coerce")

    if timestamp_unit == "auto":
        numeric = pd.to_numeric(values, errors="coerce")
        if numeric.notna().mean() >= 0.90 and numeric.dropna().size:
            median_value = float(numeric.dropna().median())
            if median_value >= 1e17:
                return pd.to_datetime(numeric, unit="ns", errors="coerce")
            if median_value >= 1e14:
                return pd.to_datetime(numeric, unit="us", errors="coerce")
            if median_value >= 1e11:
                return pd.to_datetime(numeric, unit="ms", errors="coerce")
            if median_value >= 1e8:
                return pd.to_datetime(numeric, unit="s", errors="coerce")

    return pd.to_datetime(values, errors="coerce", dayfirst=dayfirst)


def unwrap_phase(values: pd.Series, phase_unit: str, wrap_period: float | None) -> np.ndarray:
    x = values.to_numpy(dtype=float)
    if wrap_period is None:
        wrap_period = 2.0 * math.pi if phase_unit == "radians" else 360.0
    return np.unwrap(x, period=wrap_period)


def centered_hampel_filter(
    times_seconds: np.ndarray,
    values: np.ndarray,
    window_seconds: float,
    n_sigmas: float,
    min_periods: int = 3,
) -> np.ndarray:
    """Centered Hampel spike replacement for irregular timestamps."""
    values = np.asarray(values, dtype=float)
    out = values.copy()
    half = window_seconds / 2.0
    n = len(values)

    left = 0
    right = 0
    for i in range(n):
        t = times_seconds[i]
        while left < n and times_seconds[left] < t - half:
            left += 1
        while right < n and times_seconds[right] <= t + half:
            right += 1

        local = values[left:right]
        local = local[np.isfinite(local)]
        if len(local) < min_periods:
            continue

        med = float(np.median(local))
        mad = float(np.median(np.abs(local - med)))
        if mad <= 0 or not np.isfinite(mad):
            continue

        threshold = n_sigmas * 1.4826 * mad
        if abs(values[i] - med) > threshold:
            out[i] = med

    return out


def centered_time_smooth(
    times_seconds: np.ndarray,
    values: np.ndarray,
    window_seconds: float,
    method: str = "gaussian",
    sigma_seconds: float | None = None,
    min_periods: int = 1,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Zero-lag centered smoothing for irregular timestamps.

    For each sample at time t, use samples in [t - window/2, t + window/2].
    This preserves one output point per input point and does not introduce the
    delay caused by causal filters.

    Returns:
        smoothed values, number of samples used at each point
    """
    values = np.asarray(values, dtype=float)
    n = len(values)
    smoothed = np.full(n, np.nan, dtype=float)
    counts = np.zeros(n, dtype=int)

    if n == 0:
        return smoothed, counts

    half = window_seconds / 2.0
    if sigma_seconds is None:
        sigma_seconds = window_seconds / 3.0
    if sigma_seconds <= 0:
        raise ValueError("sigma_seconds must be positive")

    left = 0
    right = 0
    for i in range(n):
        t = times_seconds[i]
        while left < n and times_seconds[left] < t - half:
            left += 1
        while right < n and times_seconds[right] <= t + half:
            right += 1

        idx = np.arange(left, right)
        local_values = values[idx]
        finite = np.isfinite(local_values)
        idx = idx[finite]
        local_values = local_values[finite]
        counts[i] = len(local_values)

        if len(local_values) < min_periods:
            continue

        if method == "mean":
            smoothed[i] = float(np.mean(local_values))
        elif method == "median":
            smoothed[i] = float(np.median(local_values))
        elif method == "gaussian":
            dt = times_seconds[idx] - t
            weights = np.exp(-0.5 * (dt / sigma_seconds) ** 2)
            weight_sum = float(np.sum(weights))
            if weight_sum > 0:
                smoothed[i] = float(np.sum(weights * local_values) / weight_sum)
        else:
            raise ValueError(f"Unknown smoothing method: {method!r}")

    # If a point could not be smoothed, fall back to original value.
    missing = ~np.isfinite(smoothed)
    smoothed[missing] = values[missing]
    return smoothed, counts


def load_rfid_csv(
    csv_path: Path,
    tag_col: str,
    antenna_col: str,
    time_col: str,
    phase_col: str,
    timestamp_unit: str | None,
    timestamp_format: str | None,
    dayfirst: bool,
) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    required = [tag_col, antenna_col, time_col, phase_col]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{csv_path.name}: missing required columns: {missing}")

    df = df.copy()
    df["timestamp_raw"] = df[time_col]
    df[time_col] = parse_timestamps(
        df[time_col],
        timestamp_unit=timestamp_unit,
        timestamp_format=timestamp_format,
        dayfirst=dayfirst,
    )
    df[phase_col] = pd.to_numeric(df[phase_col], errors="coerce")

    before = len(df)
    df = df.dropna(subset=[tag_col, antenna_col, time_col, phase_col]).copy()
    dropped = before - len(df)
    if dropped:
        print(f"  Dropped {dropped} rows with missing/unparseable required values.")

    return df.sort_values([tag_col, antenna_col, time_col]).reset_index(drop=True)


def process_group(
    group: pd.DataFrame,
    time_col: str,
    phase_col: str,
    phase_unit: str,
    wrap_period: float | None,
    disable_hampel: bool,
    hampel_window: str,
    hampel_sigmas: float,
    smooth_method: str,
    smooth_window: str,
    smooth_sigma: str | None,
    min_smooth_points: int,
) -> pd.DataFrame:
    group = group.sort_values(time_col).copy().reset_index(drop=True)

    group["phase_unwrapped"] = unwrap_phase(
        group[phase_col],
        phase_unit=phase_unit,
        wrap_period=wrap_period,
    )

    group["phase_unwrapped_delta"] = group["phase_unwrapped"].diff()
    group["phase_unwrapped_delta_from_start"] = (
        group["phase_unwrapped"] - group["phase_unwrapped"].iloc[0]
    )
    group["time_delta_seconds"] = group[time_col].diff().dt.total_seconds()
    group["sample_rate_hz_instant"] = 1.0 / group["time_delta_seconds"]
    group.loc[group["time_delta_seconds"] <= 0, "sample_rate_hz_instant"] = np.nan

    times_seconds = (
        group[time_col] - group[time_col].iloc[0]
    ).dt.total_seconds().to_numpy(dtype=float)
    raw = group["phase_unwrapped"].to_numpy(dtype=float)

    if disable_hampel:
        despiked = raw.copy()
    else:
        despiked = centered_hampel_filter(
            times_seconds=times_seconds,
            values=raw,
            window_seconds=parse_duration_seconds(hampel_window),
            n_sigmas=hampel_sigmas,
        )
    group["phase_despiked"] = despiked

    sigma_seconds = None if smooth_sigma is None else parse_duration_seconds(smooth_sigma)
    smoothed, counts = centered_time_smooth(
        times_seconds=times_seconds,
        values=despiked,
        window_seconds=parse_duration_seconds(smooth_window),
        method=smooth_method,
        sigma_seconds=sigma_seconds,
        min_periods=min_smooth_points,
    )

    group["phase_smooth"] = smoothed
    group["smooth_read_count"] = counts
    group["phase_smooth_delta"] = group["phase_smooth"].diff()
    group["phase_smooth_delta_from_start"] = (
        group["phase_smooth"] - group["phase_smooth"].iloc[0]
    )

    return group


def spacing_summary_for_group(
    group: pd.DataFrame,
    tag_col: str,
    antenna_col: str,
    time_col: str,
    tag: object,
    antenna: object,
) -> dict[str, object]:
    dt_ms = group[time_col].diff().dt.total_seconds().dropna() * 1000.0
    return {
        tag_col: tag,
        antenna_col: antenna,
        "read_count": len(group),
        "median_spacing_ms": float(dt_ms.median()) if len(dt_ms) else np.nan,
        "p25_spacing_ms": float(dt_ms.quantile(0.25)) if len(dt_ms) else np.nan,
        "p75_spacing_ms": float(dt_ms.quantile(0.75)) if len(dt_ms) else np.nan,
        "p90_spacing_ms": float(dt_ms.quantile(0.90)) if len(dt_ms) else np.nan,
        "max_spacing_ms": float(dt_ms.max()) if len(dt_ms) else np.nan,
    }


def plot_file_by_antenna(
    processed: pd.DataFrame,
    csv_stem: str,
    plot_dir: Path,
    tag_col: str,
    antenna_col: str,
    time_col: str,
    phase_unit: str,
    show_raw: bool,
) -> None:
    plot_dir.mkdir(parents=True, exist_ok=True)

    for antenna, antenna_df in processed.groupby(antenna_col, sort=True):
        antenna_df = antenna_df.sort_values(time_col).copy()
        plt.figure(figsize=(14, 7))

        for tag, tag_df in antenna_df.groupby(tag_col, sort=True):
            tag_df = tag_df.sort_values(time_col)
            label = str(tag)

            if show_raw:
                plt.plot(
                    tag_df[time_col],
                    tag_df["phase_unwrapped"],
                    linewidth=0.6,
                    alpha=0.20,
                )

            plt.plot(
                tag_df[time_col],
                tag_df["phase_smooth"],
                linewidth=1.8,
                label=label,
            )

        plt.xlabel("Time")
        plt.ylabel(f"Zero-lag smoothed unwrapped phase ({phase_unit})")
        plt.title(f"{csv_stem} — antenna {antenna} — all tags")
        plt.xticks(rotation=30)
        plt.legend(fontsize="small", loc="best")
        plt.tight_layout()

        out = plot_dir / f"{csv_stem}_antenna_{safe_name(antenna)}_all_tags.png"
        plt.savefig(out, dpi=150)
        plt.close()


def process_file(
    csv_path: Path,
    output_dir: Path,
    args: argparse.Namespace,
) -> tuple[Path, Path, Path | None]:
    print(f"Processing {csv_path.name}...")
    df = load_rfid_csv(
        csv_path=csv_path,
        tag_col=args.tag_col,
        antenna_col=args.antenna_col,
        time_col=args.time_col,
        phase_col=args.phase_col,
        timestamp_unit=args.timestamp_unit,
        timestamp_format=args.timestamp_format,
        dayfirst=args.dayfirst,
    )

    processed_groups: list[pd.DataFrame] = []
    spacing_rows: list[dict[str, object]] = []

    for (tag, antenna), group in df.groupby([args.tag_col, args.antenna_col], sort=False):
        group: pd.DataFrame = group.sort_values(args.time_col).copy()
        spacing_rows.append(
            spacing_summary_for_group(
                group=group,
                tag_col=args.tag_col,
                antenna_col=args.antenna_col,
                time_col=args.time_col,
                tag=tag,
                antenna=antenna,
            )
        )
        processed_groups.append(
            process_group(
                group=group,
                time_col=args.time_col,
                phase_col=args.phase_col,
                phase_unit=args.phase_unit,
                wrap_period=args.wrap_period,
                disable_hampel=args.disable_hampel,
                hampel_window=args.hampel_window,
                hampel_sigmas=args.hampel_sigmas,
                smooth_method=args.smooth_method,
                smooth_window=args.smooth_window,
                smooth_sigma=args.smooth_sigma,
                min_smooth_points=args.min_smooth_points,
            )
        )

    processed = pd.concat(processed_groups, ignore_index=True)
    spacing = pd.DataFrame(spacing_rows)

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_out = output_dir / f"{csv_path.stem}_processed.csv"
    spacing_out = output_dir / f"{csv_path.stem}_sample_spacing_summary.csv"
    processed.to_csv(csv_out, index=False)
    spacing.to_csv(spacing_out, index=False)

    plot_dir = None
    if not args.no_plots:
        plot_dir = output_dir / "plots" / csv_path.stem
        plot_file_by_antenna(
            processed=processed,
            csv_stem=csv_path.stem,
            plot_dir=plot_dir,
            tag_col=args.tag_col,
            antenna_col=args.antenna_col,
            time_col=args.time_col,
            phase_unit=args.phase_unit,
            show_raw=args.show_raw_in_plots,
        )

    return csv_out, spacing_out, plot_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Process RFID phase CSV files with zero-lag centered smoothing."
    )
    parser.add_argument("csv_files", nargs="+", help="Input CSV paths or glob patterns, e.g. 'reads*.csv'.")
    parser.add_argument("--output-dir", default="rfid_processed_zero_lag")

    parser.add_argument("--tag-col", default="EPC")
    parser.add_argument("--antenna-col", default="antenna")
    parser.add_argument("--time-col", default="timestamp")
    parser.add_argument("--phase-col", default="phase")

    parser.add_argument("--timestamp-unit", default="auto", choices=["auto", "s", "ms", "us", "ns"])
    parser.add_argument("--timestamp-format", default=None)
    parser.add_argument("--dayfirst", action="store_true")

    parser.add_argument("--phase-unit", choices=["degrees", "radians"], default="degrees")
    parser.add_argument(
        "--wrap-period",
        type=float,
        default=180.0,
        help="Phase wrap period. Your uploaded files look like 0-180 degrees, so default is 180.",
    )

    parser.add_argument("--disable-hampel", action="store_true")
    parser.add_argument("--hampel-window", default="750ms")
    parser.add_argument("--hampel-sigmas", type=float, default=3.5)

    parser.add_argument(
        "--smooth-method",
        choices=["gaussian", "mean", "median"],
        default="gaussian",
        help="Centered zero-lag smoothing method. Default: gaussian.",
    )
    parser.add_argument(
        "--smooth-window",
        default="1500ms",
        help="Centered smoothing window width. Default: 1500ms, about ±750ms around each read.",
    )
    parser.add_argument(
        "--smooth-sigma",
        default="500ms",
        help="Gaussian sigma. Only used with --smooth-method gaussian. Default: 500ms.",
    )
    parser.add_argument(
        "--min-smooth-points",
        type=int,
        default=1,
        help="Minimum reads required inside smoothing window. Default: 1.",
    )

    parser.add_argument("--no-plots", action="store_true")
    parser.add_argument("--show-raw-in-plots", action="store_true")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    input_paths = expand_input_paths(args.csv_files)
    missing = [p for p in input_paths if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Missing input files: {[str(p) for p in missing]}")

    output_dir = Path(args.output_dir)
    outputs = []
    for path in input_paths:
        outputs.append(process_file(path, output_dir, args))

    print("\nDone. Outputs:")
    for csv_out, spacing_out, plot_dir in outputs:
        print(f"  Processed CSV: {csv_out}")
        print(f"  Spacing summary: {spacing_out}")
        if plot_dir is not None:
            print(f"  Plots: {plot_dir}")


if __name__ == "__main__":
    main()
