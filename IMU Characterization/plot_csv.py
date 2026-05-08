from __future__ import annotations

import argparse
import csv
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
TESTS_DIR = SCRIPT_DIR / "input"


@dataclass(frozen=True)
class SensorCSV:
    comments: list[str]
    headers: list[str]
    rows: list[dict[str, str]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plot gravity_x, gravity_y, and gravity_z from an IMU CSV. Row ranges are "
            "1-based data rows, so comment metadata and the CSV header are not counted."
        ),
        allow_abbrev=False,
    )
    parser.add_argument(
        "csv_file",
        nargs="?",
        help="CSV filename in IMU Characterization/input, or an explicit CSV path.",
    )
    parser.add_argument(
        "--start-row",
        type=int,
        help="First data row to include, starting at 1 after the header/comments.",
    )
    parser.add_argument(
        "--end-row",
        type=int,
        help="Last data row to include, inclusive. Defaults to the final data row.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Optional path for a CSV copy containing only the selected data rows.",
    )
    parser.add_argument(
        "--plot-output",
        type=Path,
        help="Optional path to save the gravity plot image.",
    )
    parser.add_argument(
        "--no-show",
        action="store_true",
        help="Save/prepare the plot without opening an interactive plot window.",
    )
    parser.add_argument(
        "--prompt-cut",
        action="store_true",
        help="Prompt for a row range and optional output CSV after loading the file.",
    )

    argv = normalize_option_values_with_leading_dash(sys.argv[1:])
    args, unknown = parser.parse_known_args(argv)
    if args.csv_file is None and unknown:
        args.csv_file = unknown.pop(0)
    if unknown:
        parser.error(f"unrecognized arguments: {' '.join(unknown)}")
    if args.csv_file is None:
        parser.error("csv_file is required")
    return args


def normalize_option_values_with_leading_dash(argv: Sequence[str]) -> list[str]:
    """Normalize option-value pairs where the value starts with '-' (e.g. -o -x.csv)."""
    options_with_values = {"-o", "--output", "--plot-output"}
    normalized: list[str] = []
    index = 0

    while index < len(argv):
        token = argv[index]
        if token in options_with_values and index + 1 < len(argv):
            value = argv[index + 1]
            if value.startswith("-") and value != "--":
                normalized.append(f"{token}={value}")
                index += 2
                continue

        normalized.append(token)
        index += 1

    return normalized


def resolve_csv_path(csv_file: str) -> Path:
    candidate = Path(csv_file).expanduser()
    if candidate.is_file():
        return candidate

    tests_candidate = TESTS_DIR / csv_file
    if tests_candidate.is_file():
        return tests_candidate

    if tests_candidate.suffix == "":
        tests_candidate = tests_candidate.with_suffix(".csv")
        if tests_candidate.is_file():
            return tests_candidate

    raise FileNotFoundError(
        f"Could not find {csv_file!r} as a path or inside {TESTS_DIR}."
    )


def read_sensor_csv(csv_path: Path) -> SensorCSV:
    comments: list[str] = []

    with csv_path.open("r", encoding="utf-8", newline="") as file:
        header_line: Optional[str] = None
        for line in file:
            if line.startswith("#"):
                comments.append(line)
                continue
            if line.strip():
                header_line = line
                break

        if header_line is None:
            raise ValueError(f"CSV file has no header row: {csv_path}")

        headers = next(csv.reader([header_line]))
        headers = [header.strip() for header in headers]
        reader = csv.DictReader(file, fieldnames=headers)
        rows = [
            {key.strip(): value for key, value in row.items() if key is not None}
            for row in reader
        ]

    if not rows:
        raise ValueError(f"CSV file has no data rows: {csv_path}")
    return SensorCSV(comments=comments, headers=headers, rows=rows)


def prompt_for_cut(args: argparse.Namespace, total_rows: int, csv_path: Path) -> None:
    answer = input("Cut to a specific data-row range before plotting? [y/N]: ").strip()
    if answer.lower() not in {"y", "yes"}:
        return

    args.start_row = prompt_int("Start row", args.start_row or 1)
    args.end_row = prompt_int("End row", args.end_row or total_rows)

    save_answer = input("Write a cut CSV with that row range? [y/N]: ").strip()
    if save_answer.lower() in {"y", "yes"} and args.output is None:
        default_path = csv_path.with_name(f"{csv_path.stem}_rows_{args.start_row}_{args.end_row}.csv")
        value = input(f"Output CSV [{default_path}]: ").strip()
        args.output = Path(value).expanduser() if value else default_path


def prompt_int(label: str, default: int) -> int:
    while True:
        value = input(f"{label} [{default}]: ").strip()
        if not value:
            return default
        try:
            return int(value)
        except ValueError:
            print("Please enter a whole number.")


def row_slice(total_rows: int, start_row: Optional[int], end_row: Optional[int]) -> slice:
    start = 1 if start_row is None else start_row
    end = total_rows if end_row is None else end_row

    if start < 1:
        raise ValueError("--start-row must be 1 or greater.")
    if end < start:
        raise ValueError("--end-row must be greater than or equal to --start-row.")
    if start > total_rows:
        raise ValueError(f"--start-row is past the end of the file ({total_rows} data rows).")
    if end > total_rows:
        raise ValueError(f"--end-row is past the end of the file ({total_rows} data rows).")

    return slice(start - 1, end)


def column_name(headers: Sequence[str], requested: str) -> str:
    normalized = {header.strip().lower(): header for header in headers}
    try:
        return normalized[requested.lower()]
    except KeyError as error:
        raise KeyError(f"Could not find required column: {requested}") from error


def numeric_column(rows: Sequence[dict[str, str]], column: str) -> list[float]:
    values: list[float] = []
    for index, row in enumerate(rows, start=1):
        try:
            values.append(float(row[column]))
        except (TypeError, ValueError) as error:
            raise ValueError(f"Row {index} has a non-numeric {column!r} value.") from error
    return values


def write_cut_csv(data: SensorCSV, selected_rows: Sequence[dict[str, str]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as file:
        file.writelines(data.comments)
        writer = csv.DictWriter(file, fieldnames=data.headers)
        writer.writeheader()
        writer.writerows(selected_rows)


def resolve_output_path(output: Path) -> Path:
    expanded = output.expanduser()
    if expanded.is_absolute():
        return expanded
    return TESTS_DIR / expanded


def configure_plot_cache() -> None:
    cache_root = Path(tempfile.gettempdir()) / "plot_gravity_csv_cache"
    matplotlib_cache = cache_root / "matplotlib"
    xdg_cache = cache_root / "xdg"
    matplotlib_cache.mkdir(parents=True, exist_ok=True)
    (xdg_cache / "fontconfig").mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(matplotlib_cache))
    os.environ.setdefault("XDG_CACHE_HOME", str(xdg_cache))


def plot_gravity(
    data: SensorCSV,
    rows: Sequence[dict[str, str]],
    csv_path: Path,
    selected_range: slice,
    plot_output: Optional[Path],
    no_show: bool,
) -> None:
    configure_plot_cache()

    if no_show:
        import matplotlib

        matplotlib.use("Agg")

    import matplotlib.pyplot as plt

    time_column = "timestamp"
    if "timestamp_s" in {header.lower() for header in data.headers}:
        time_column = column_name(data.headers, "timestamp_s")
    elif "timestamp" in {header.lower() for header in data.headers}:
        time_column = column_name(data.headers, "timestamp")

    x_values = numeric_column(rows, time_column)
    gravity_x = numeric_column(rows, column_name(data.headers, "gravity_x"))
    gravity_y = numeric_column(rows, column_name(data.headers, "gravity_y"))
    gravity_z = numeric_column(rows, column_name(data.headers, "gravity_z"))

    first_row = selected_range.start + 1
    last_row = selected_range.stop

    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    series = [
        ("gravity_x", gravity_x, "tab:blue"),
        ("gravity_y", gravity_y, "tab:orange"),
        ("gravity_z", gravity_z, "tab:green"),
    ]

    fig.suptitle(f"{csv_path.name} gravity rows {first_row}-{last_row}")
    for axis, (label, values, color) in zip(axes, series):
        axis.plot(x_values, values, color=color)
        axis.set_title(label)
        axis.set_ylabel("g")
        axis.grid(True, alpha=0.3)

    axes[-1].set_xlabel(f"{time_column} [s]")
    fig.tight_layout()

    if plot_output is not None:
        plot_output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(plot_output, dpi=150)
        print(f"Wrote plot: {plot_output}")

    if not no_show:
        plt.show()
    else:
        plt.close(fig)


def main() -> None:
    args = parse_args()
    csv_path = resolve_csv_path(args.csv_file)
    data = read_sensor_csv(csv_path)

    if args.prompt_cut:
        prompt_for_cut(args, len(data.rows), csv_path)

    selected_range = row_slice(len(data.rows), args.start_row, args.end_row)
    selected_rows = data.rows[selected_range]

    if args.output is not None:
        output_path = resolve_output_path(args.output)
        write_cut_csv(data, selected_rows, output_path)
        print(f"Wrote cut CSV: {output_path}")

    plot_gravity(
        data=data,
        rows=selected_rows,
        csv_path=csv_path,
        selected_range=selected_range,
        plot_output=args.plot_output,
        no_show=args.no_show,
    )


if __name__ == "__main__":
    main()
