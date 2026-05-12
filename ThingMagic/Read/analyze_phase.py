#!/usr/bin/env python3

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

import math

def load_rfid_csv(
    csv_path: str,
    tag_col: str,
    antenna_col: str,
    time_col: str,
    phase_col: str,
) -> pd.DataFrame:
    df = pd.read_csv(csv_path)

    required = [tag_col, antenna_col, time_col, phase_col]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = df[required].copy()

    df[time_col] = pd.to_datetime(df[time_col], unit="ms", errors="coerce")
    df[phase_col] = pd.to_numeric(df[phase_col], errors="coerce")

    df = df.dropna(subset=[tag_col, antenna_col, time_col, phase_col])
    df = df.sort_values([tag_col, antenna_col, time_col])

    return df


def normalize_phase_to_radians(phase_values: pd.Series, input_unit: str) -> np.ndarray:
    phase = phase_values.to_numpy(dtype=float)

    if input_unit == "radians":
        return phase
    if input_unit == "degrees":
        return np.deg2rad(phase)

    raise ValueError("input_unit must be either 'radians' or 'degrees'")


def analyze_phase_changes(
    df: pd.DataFrame,
    tag_col: str,
    antenna_col: str,
    time_col: str,
    phase_col: str,
    input_unit: str,
) -> pd.DataFrame:
    analyzed_groups = []

    for (tag, antenna), group in df.groupby([tag_col, antenna_col], sort=False):
        group = group.sort_values(time_col).copy()

        phase_rad = normalize_phase_to_radians(group[phase_col], input_unit)

        # Unwrap phase so boundary crossings do not look like huge jumps.
        unwrapped_rad = np.unwrap(phase_rad, period=math.pi)

        if input_unit == "degrees":
            group["phase_unwrapped"] = np.rad2deg(unwrapped_rad)
        else:
            group["phase_unwrapped"] = unwrapped_rad

        group["phase_delta"] = group["phase_unwrapped"].diff()
        group["phase_delta_from_start"] = (
            group["phase_unwrapped"] - group["phase_unwrapped"].iloc[0]
        )
        group["time_delta_seconds"] = group[time_col].diff().dt.total_seconds()
        group["phase_rate_per_second"] = (
            group["phase_delta"] / group["time_delta_seconds"]
        )

        analyzed_groups.append(group)

    return pd.concat(analyzed_groups, ignore_index=True)


def average_phase_over_time_windows(
    analyzed: pd.DataFrame,
    tag_col: str,
    antenna_col: str,
    time_col: str,
    window: str,
) -> pd.DataFrame:
    averaged_groups = []

    for (tag, antenna), group in analyzed.groupby([tag_col, antenna_col], sort=False):
        group = group.sort_values(time_col).copy()
        group = group.set_index(time_col)

        averaged = (
            group["phase_unwrapped"]
            .resample(window)
            .agg(["mean", "std", "count"])
            .rename(
                columns={
                    "mean": "phase_avg",
                    "std": "phase_std",
                    "count": "read_count",
                }
            )
            .dropna(subset=["phase_avg"])
            .reset_index()
        )

        averaged[tag_col] = tag
        averaged[antenna_col] = antenna

        averaged["phase_avg_delta"] = averaged["phase_avg"].diff()
        averaged["phase_avg_delta_from_start"] = (
            averaged["phase_avg"] - averaged["phase_avg"].iloc[0]
        )
        averaged["window"] = window

        averaged_groups.append(averaged)

    if not averaged_groups:
        return pd.DataFrame()

    return pd.concat(averaged_groups, ignore_index=True)

def rolling_average_phase_over_time_window(
    analyzed: pd.DataFrame,
    tag_col: str,
    antenna_col: str,
    time_col: str,
    window: str,
) -> pd.DataFrame:
    rolling_groups = []

    for (tag, antenna), group in analyzed.groupby([tag_col, antenna_col], sort=False):
        group = group.sort_values(time_col).copy()

        # Pandas time-based rolling requires the timestamp as the index.
        group = group.set_index(time_col)

        rolling_stats = (
            group["phase_unwrapped"]
            .rolling(window=window, min_periods=1)
            .agg(["mean", "std", "count"])
            .rename(
                columns={
                    "mean": "phase_rolling_avg",
                    "std": "phase_rolling_std",
                    "count": "rolling_read_count",
                }
            )
        )

        group = group.join(rolling_stats)

        group["phase_rolling_avg_delta"] = group["phase_rolling_avg"].diff()
        group["phase_rolling_avg_delta_from_start"] = (
            group["phase_rolling_avg"] - group["phase_rolling_avg"].iloc[0]
        )

        group["rolling_window"] = window

        group = group.reset_index()

        rolling_groups.append(group)

    return pd.concat(rolling_groups, ignore_index=True)

def summarize_phase_changes(
    analyzed: pd.DataFrame,
    tag_col: str,
    antenna_col: str,
    time_col: str,
) -> pd.DataFrame:
    summary = (
        analyzed.groupby([tag_col, antenna_col])
        .agg(
            read_count=("phase_unwrapped", "size"),
            first_timestamp=(time_col, "min"),
            last_timestamp=(time_col, "max"),
            phase_start=("phase_unwrapped", "first"),
            phase_end=("phase_unwrapped", "last"),
            total_phase_change=("phase_delta_from_start", "last"),
            mean_abs_step_change=("phase_delta", lambda x: x.abs().mean()),
            max_abs_step_change=("phase_delta", lambda x: x.abs().max()),
            mean_phase_rate=("phase_rate_per_second", "mean"),
            max_abs_phase_rate=("phase_rate_per_second", lambda x: x.abs().max()),
        )
        .reset_index()
    )

    return summary


def plot_phase_by_group(
    analyzed: pd.DataFrame,
    output_dir: Path,
    tag_col: str,
    antenna_col: str,
    time_col: str,
    phase_unit_label: str,
):
    plots_dir = output_dir / "plots_raw_unwrapped"
    plots_dir.mkdir(parents=True, exist_ok=True)

    for (tag, antenna), group in analyzed.groupby([tag_col, antenna_col], sort=False):
        group = group.sort_values(time_col)

        safe_tag = str(tag).replace("/", "_").replace("\\", "_")
        safe_antenna = str(antenna).replace("/", "_").replace("\\", "_")

        plt.figure(figsize=(10, 5))
        plt.plot(group[time_col], group["phase_unwrapped"], marker="o", linewidth=1)
        plt.xlabel("Time")
        plt.ylabel(f"Unwrapped phase ({phase_unit_label})")
        plt.title(f"Raw unwrapped phase — tag={tag}, antenna={antenna}")
        plt.xticks(rotation=30)
        plt.tight_layout()

        plot_path = plots_dir / f"raw_phase_tag_{safe_tag}_antenna_{safe_antenna}.png"
        plt.savefig(plot_path, dpi=150)
        plt.close()


def plot_window_averaged_phase(
    averaged: pd.DataFrame,
    output_dir: Path,
    tag_col: str,
    antenna_col: str,
    time_col: str,
    phase_unit_label: str,
    window: str,
):
    plots_dir = output_dir / "plots_window_averaged"
    plots_dir.mkdir(parents=True, exist_ok=True)

    for (tag, antenna), group in averaged.groupby([tag_col, antenna_col], sort=False):
        group = group.sort_values(time_col)

        safe_tag = str(tag).replace("/", "_").replace("\\", "_")
        safe_antenna = str(antenna).replace("/", "_").replace("\\", "_")

        plt.figure(figsize=(10, 5))
        plt.plot(group[time_col], group["phase_avg"], marker="o", linewidth=1)

        plt.xlabel("Time")
        plt.ylabel(f"Average unwrapped phase ({phase_unit_label})")
        plt.title(f"{window} averaged phase — tag={tag}, antenna={antenna}")
        plt.xticks(rotation=30)
        plt.tight_layout()

        plot_path = (
            plots_dir
            / f"avg_phase_{window}_tag_{safe_tag}_antenna_{safe_antenna}.png"
        )
        plt.savefig(plot_path, dpi=150)
        plt.close()


def plot_window_averaged_phase_change(
    averaged: pd.DataFrame,
    output_dir: Path,
    tag_col: str,
    antenna_col: str,
    time_col: str,
    phase_unit_label: str,
    window: str,
):
    plots_dir = output_dir / "plots_window_averaged_delta"
    plots_dir.mkdir(parents=True, exist_ok=True)

    for (tag, antenna), group in averaged.groupby([tag_col, antenna_col], sort=False):
        group = group.sort_values(time_col)

        safe_tag = str(tag).replace("/", "_").replace("\\", "_")
        safe_antenna = str(antenna).replace("/", "_").replace("\\", "_")

        plt.figure(figsize=(10, 5))
        plt.plot(
            group[time_col],
            group["phase_avg_delta_from_start"],
            marker="o",
            linewidth=1,
        )

        plt.xlabel("Time")
        plt.ylabel(f"Average phase change from start ({phase_unit_label})")
        plt.title(
            f"{window} averaged phase change from start — tag={tag}, antenna={antenna}"
        )
        plt.xticks(rotation=30)
        plt.tight_layout()

        plot_path = (
            plots_dir
            / f"avg_phase_delta_{window}_tag_{safe_tag}_antenna_{safe_antenna}.png"
        )
        plt.savefig(plot_path, dpi=150)
        plt.close()

def plot_rolling_averaged_phase(
    averaged: pd.DataFrame,
    output_dir: Path,
    tag_col: str,
    antenna_col: str,
    time_col: str,
    phase_unit_label: str,
    window: str,
):
    plots_dir = output_dir / "plots_rolling_window_average"
    plots_dir.mkdir(parents=True, exist_ok=True)

    for (tag, antenna), group in averaged.groupby([tag_col, antenna_col], sort=False):
        group = group.sort_values(time_col)

        safe_tag = str(tag).replace("/", "_").replace("\\", "_")
        safe_antenna = str(antenna).replace("/", "_").replace("\\", "_")

        plt.figure(figsize=(10, 5))

        plt.plot(
            group[time_col],
            group["phase_unwrapped"],
            linewidth=0.75,
            alpha=0.35,
            label="Raw unwrapped phase",
        )

        plt.plot(
            group[time_col],
            group["phase_rolling_avg"],
            marker="o",
            markersize=3,
            linewidth=1.5,
            label=f"Rolling average, window={window}",
        )

        plt.xlabel("Time")
        plt.ylabel(f"Phase ({phase_unit_label})")
        plt.title(f"Rolling time-window phase average — tag={tag}, antenna={antenna}")
        plt.xticks(rotation=30)
        plt.legend()
        plt.tight_layout()

        plot_path = (
            plots_dir
            / f"rolling_avg_phase_{window}_tag_{safe_tag}_antenna_{safe_antenna}.png"
        )
        plt.savefig(plot_path, dpi=150)
        plt.close()

def main():
    parser = argparse.ArgumentParser(
        description="Analyze RFID phase changes by tag and antenna port."
    )

    parser.add_argument("csv_path", help="Path to input RFID CSV file")

    parser.add_argument("--tag-col", default="EPC")
    parser.add_argument("--antenna-col", default="antenna")
    parser.add_argument("--time-col", default="timestamp")
    parser.add_argument("--phase-col", default="phase")

    parser.add_argument(
        "--phase-unit",
        choices=["radians", "degrees"],
        default="degrees",
        help="Unit of phase column. Default: degrees",
    )

    parser.add_argument(
        "--window",
        default="1s",
        help="Time window for averaging, e.g. 100ms, 500ms, 1s, 5s, 1min. Default: 1s",
    )

    parser.add_argument(
        "--output-dir",
        default="rfid_phase_analysis",
        help="Directory for output files. Default: rfid_phase_analysis",
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = load_rfid_csv(
        args.csv_path,
        args.tag_col,
        args.antenna_col,
        args.time_col,
        args.phase_col,
    )

    analyzed = analyze_phase_changes(
        df,
        args.tag_col,
        args.antenna_col,
        args.time_col,
        args.phase_col,
        args.phase_unit,
    )

    averaged = rolling_average_phase_over_time_window(
        analyzed,
        args.tag_col,
        args.antenna_col,
        args.time_col,
        args.window,
    )

    summary = summarize_phase_changes(
        analyzed,
        args.tag_col,
        args.antenna_col,
        args.time_col,
    )

    analyzed_csv = output_dir / "phase_analysis_timeseries.csv"
    averaged_csv = output_dir / f"phase_analysis_window_averaged_{args.window}.csv"
    summary_csv = output_dir / "phase_analysis_summary.csv"

    analyzed.to_csv(analyzed_csv, index=False)
    averaged.to_csv(averaged_csv, index=False)
    summary.to_csv(summary_csv, index=False)

    phase_unit_label = "degrees" if args.phase_unit == "degrees" else "radians"

    # plot_phase_by_group(
    #     analyzed,
    #     output_dir,
    #     args.tag_col,
    #     args.antenna_col,
    #     args.time_col,
    #     phase_unit_label,
    # )

    # plot_window_averaged_phase(
    #     averaged,
    #     output_dir,
    #     args.tag_col,
    #     args.antenna_col,
    #     args.time_col,
    #     phase_unit_label,
    #     args.window,
    # )

    # plot_window_averaged_phase_change(
    #     averaged,
    #     output_dir,
    #     args.tag_col,
    #     args.antenna_col,
    #     args.time_col,
    #     phase_unit_label,
    #     args.window,
    # )

    plot_rolling_averaged_phase(
        averaged,
        output_dir,
        args.tag_col,
        args.antenna_col,
        args.time_col,
        phase_unit_label,
        args.window,
    )

    print(f"Saved detailed time series to: {analyzed_csv}")
    print(f"Saved window-averaged time series to: {averaged_csv}")
    print(f"Saved summary statistics to: {summary_csv}")
    print(f"Saved plots under: {output_dir}")


if __name__ == "__main__":
    main()