from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from config import PDRConfig
from helpers import run_pdr_with_step_lengths
from pdr_run import CONFIG, build_step_lengths
from step_detection.step_detection import detect_steps
from turn_detection.heading import load_step_heading_data
from turn_detection.turn_detection import detect_turns_with_config, step_turn_mask, summarize_turns


ALIGNMENT_START = "start"
ALIGNMENT_BEST_FIT = "best-fit"
ALIGNMENT_CHOICES = (ALIGNMENT_START, ALIGNMENT_BEST_FIT)


@dataclass(frozen=True)
class BundlePaths:
    folder: Path
    metadata_csv_or_json: Optional[Path]
    arkit_csv: Path
    imu_csv: Optional[Path]


@dataclass(frozen=True)
class ARKitTrajectory:
    t: np.ndarray
    points: np.ndarray
    tracking_state: np.ndarray
    tracking_reason: np.ndarray
    raw_dataframe: pd.DataFrame


@dataclass(frozen=True)
class PDRTrajectory:
    t: np.ndarray
    points: np.ndarray
    step_count: int
    turn_step_count: int
    path_length_m: float
    turn_summary: Sequence[str]


@dataclass(frozen=True)
class TrimConfig:
    start_s: float = 0.0
    end_s: float = 0.0

    @property
    def enabled(self) -> bool:
        return self.start_s > 0.0 or self.end_s > 0.0


def resolve_bundle_paths(path: Path) -> BundlePaths:
    path = path.expanduser().resolve()
    if path.is_dir():
        folder = path
    else:
        folder = path.parent

    arkit_csv = folder / "arkit.csv"
    if path.name.endswith("arkit.csv"):
        arkit_csv = path

    if not arkit_csv.is_file():
        candidates = sorted(folder.glob("*arkit*.csv"))
        if candidates:
            arkit_csv = candidates[0]

    if not arkit_csv.is_file():
        raise FileNotFoundError(f"Could not find arkit.csv in {folder}")

    imu_csv = folder / "imu.csv"
    if not imu_csv.is_file():
        candidates = sorted(folder.glob("*imu*.csv"))
        imu_csv = candidates[0] if candidates else None

    metadata = folder / "metadata.json"
    if not metadata.is_file():
        json_candidates = sorted(folder.glob("*.json"))
        metadata = json_candidates[0] if json_candidates else None

    return BundlePaths(folder=folder, metadata_csv_or_json=metadata, arkit_csv=arkit_csv, imu_csv=imu_csv)


def load_arkit_csv(path: Path, include_non_normal: bool = False) -> ARKitTrajectory:
    df = pd.read_csv(path)
    df.columns = [column.strip() for column in df.columns]

    required = ("timestamp_s", "x_m", "z_m")
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise KeyError(f"Missing required ARKit columns in {path}: {', '.join(missing)}")

    t = pd.to_numeric(df["timestamp_s"], errors="coerce").to_numpy(dtype=float)
    x = pd.to_numeric(df["x_m"], errors="coerce").to_numpy(dtype=float)
    z = pd.to_numeric(df["z_m"], errors="coerce").to_numpy(dtype=float)
    state = df["tracking_state"].fillna("unknown").astype(str).to_numpy() if "tracking_state" in df else np.full(len(df), "unknown")
    reason = df["tracking_reason"].fillna("").astype(str).to_numpy() if "tracking_reason" in df else np.full(len(df), "")

    valid = np.isfinite(t) & np.isfinite(x) & np.isfinite(z)
    if not include_non_normal and np.any(state == "normal"):
        valid &= state == "normal"

    t = t[valid]
    points = np.column_stack([x[valid], -z[valid]])
    state = state[valid]
    reason = reason[valid]

    order = np.argsort(t)
    t = t[order]
    points = points[order]
    state = state[order]
    reason = reason[order]

    if t.size < 2:
        raise ValueError("At least two valid ARKit frames are required.")

    return ARKitTrajectory(
        t=t,
        points=points,
        tracking_state=state,
        tracking_reason=reason,
        raw_dataframe=df,
    )


def trim_arkit_trajectory(arkit: ARKitTrajectory, trim: TrimConfig) -> ARKitTrajectory:
    if trim.start_s < 0 or trim.end_s < 0:
        raise ValueError("Trim durations must be non-negative.")
    if not trim.enabled:
        return arkit

    start_time = arkit.t[0] + trim.start_s
    end_time = arkit.t[-1] - trim.end_s
    if end_time <= start_time:
        raise ValueError(
            f"Trim window is empty: start={start_time:.3f}s, end={end_time:.3f}s. "
            "Reduce --trim-start-s or --trim-end-s."
        )

    keep = (arkit.t >= start_time) & (arkit.t <= end_time)
    if int(keep.sum()) < 2:
        raise ValueError("Fewer than two ARKit frames remain after trimming.")

    return ARKitTrajectory(
        t=arkit.t[keep],
        points=arkit.points[keep],
        tracking_state=arkit.tracking_state[keep],
        tracking_reason=arkit.tracking_reason[keep],
        raw_dataframe=arkit.raw_dataframe,
    )


def tracking_counts(states: Iterable[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for state in states:
        counts[state] = counts.get(state, 0) + 1
    return counts


def path_length(points: np.ndarray) -> float:
    if points.shape[0] < 2:
        return 0.0
    return float(np.sum(np.linalg.norm(np.diff(points, axis=0), axis=1)))


def displacement(points: np.ndarray) -> float:
    if points.shape[0] < 2:
        return 0.0
    return float(np.linalg.norm(points[-1] - points[0]))


def run_pdr_from_imu_csv(csv_path: Path, config: PDRConfig = CONFIG) -> PDRTrajectory:
    t, user_ax, user_ay, user_az, heading = load_step_heading_data(
        csv_path,
        config.turn_detection.heading_mode,
    )
    peaks, amag_f, fs = detect_steps(
        t,
        user_ax,
        user_ay,
        user_az,
        low=config.step_detection.low_hz,
        high=config.step_detection.high_hz,
        min_step_gap_s=config.step_detection.min_step_gap_s,
        prominence=config.step_detection.prominence,
    )
    turns = detect_turns_with_config(t, heading, config.turn_detection)
    step_lengths, _ = build_step_lengths(peaks, amag_f, fs, config)
    xs, ys, step_times = run_pdr_with_step_lengths(
        t,
        peaks,
        heading,
        step_lengths,
        start_x=config.start_point.x_m,
        start_y=config.start_point.y_m,
    )
    turn_steps = step_turn_mask(t, peaks, turns)
    return PDRTrajectory(
        t=step_times,
        points=np.column_stack([xs, ys]),
        step_count=len(peaks),
        turn_step_count=int(turn_steps.sum()),
        path_length_m=float(step_lengths.sum()),
        turn_summary=summarize_turns(turns),
    )


def interpolate_points(source_t: np.ndarray, source_points: np.ndarray, target_t: np.ndarray) -> np.ndarray:
    if source_t.size < 2:
        raise ValueError("At least two source samples are required for interpolation.")
    x = np.interp(target_t, source_t, source_points[:, 0])
    y = np.interp(target_t, source_t, source_points[:, 1])
    return np.column_stack([x, y])


def paired_trajectories(
    arkit: ARKitTrajectory,
    pdr: PDRTrajectory,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mask = (pdr.t >= arkit.t[0]) & (pdr.t <= arkit.t[-1])
    pdr_times = pdr.t[mask]
    pdr_points = pdr.points[mask]
    if pdr_times.size < 2:
        raise ValueError("Not enough overlapping ARKit/PDR points for evaluation.")
    arkit_points = interpolate_points(arkit.t, arkit.points, pdr_times)
    return pdr_times, arkit_points, pdr_points


def rotation_matrix(theta: float) -> np.ndarray:
    c = np.cos(theta)
    s = np.sin(theta)
    return np.array([[c, -s], [s, c]], dtype=float)


def initial_heading(points: np.ndarray, min_displacement_m: float = 0.05) -> float:
    if points.shape[0] < 2:
        return 0.0
    origin = points[0]
    for point in points[1:]:
        delta = point - origin
        if np.linalg.norm(delta) >= min_displacement_m:
            return float(np.arctan2(delta[1], delta[0]))
    delta = points[-1] - origin
    return float(np.arctan2(delta[1], delta[0]))


def align_start_only(pdr_points: np.ndarray, arkit_points: np.ndarray) -> np.ndarray:
    theta = initial_heading(arkit_points) - initial_heading(pdr_points)
    r = rotation_matrix(theta)
    return pdr_points @ r.T + (arkit_points[0] - pdr_points[0] @ r.T)


def align_best_fit(pdr_points: np.ndarray, arkit_points: np.ndarray) -> np.ndarray:
    if pdr_points.shape != arkit_points.shape:
        raise ValueError("PDR and ARKit point arrays must have the same shape.")
    pdr_center = np.mean(pdr_points, axis=0)
    arkit_center = np.mean(arkit_points, axis=0)
    x = pdr_points - pdr_center
    y = arkit_points - arkit_center
    h = x.T @ y
    u, _, vt = np.linalg.svd(h)
    r = vt.T @ u.T
    if np.linalg.det(r) < 0:
        vt[-1, :] *= -1
        r = vt.T @ u.T
    return pdr_points @ r.T + (arkit_center - pdr_center @ r.T)


def align_pdr_to_arkit(
    pdr_points: np.ndarray,
    arkit_points: np.ndarray,
    alignment: str,
) -> np.ndarray:
    if alignment == ALIGNMENT_START:
        return align_start_only(pdr_points, arkit_points)
    if alignment == ALIGNMENT_BEST_FIT:
        return align_best_fit(pdr_points, arkit_points)
    raise ValueError(f"Unknown alignment mode: {alignment}")


def error_metrics(
    times: np.ndarray,
    arkit_points: np.ndarray,
    aligned_pdr_points: np.ndarray,
    original_pdr_points: np.ndarray,
) -> Dict[str, float]:
    errors = np.linalg.norm(aligned_pdr_points - arkit_points, axis=1)
    arkit_distance = path_length(arkit_points)
    pdr_distance = path_length(original_pdr_points)
    return {
        "paired_points": float(errors.size),
        "duration_s": float(times[-1] - times[0]),
        "mean_error_m": float(np.mean(errors)),
        "median_error_m": float(np.median(errors)),
        "rmse_m": float(np.sqrt(np.mean(errors**2))),
        "p95_error_m": float(np.percentile(errors, 95)),
        "max_error_m": float(np.max(errors)),
        "endpoint_error_m": float(errors[-1]),
        "arkit_path_length_m": arkit_distance,
        "pdr_path_length_m": pdr_distance,
        "path_length_ratio_pdr_over_arkit": float(pdr_distance / arkit_distance) if arkit_distance > 0 else np.nan,
        "endpoint_drift_per_meter": float(errors[-1] / arkit_distance) if arkit_distance > 0 else np.nan,
    }


def print_metrics(title: str, metrics: Dict[str, float]) -> None:
    print(title)
    for key, value in metrics.items():
        if key in {"paired_points", "frame_count"}:
            print(f"{key}: {int(value)}")
        else:
            print(f"{key}: {value:.6f}")


def evaluate_arkit_only(
    paths: BundlePaths,
    include_non_normal: bool,
    show_plot: bool,
    save_plot: Optional[Path],
    trim: TrimConfig,
) -> None:
    arkit = load_arkit_csv(paths.arkit_csv, include_non_normal=include_non_normal)
    original_frame_count = arkit.t.size
    arkit = trim_arkit_trajectory(arkit, trim)
    metrics = {
        "duration_s": float(arkit.t[-1] - arkit.t[0]),
        "frame_count": float(arkit.t.size),
        "arkit_path_length_m": path_length(arkit.points),
        "start_end_displacement_m": displacement(arkit.points),
    }

    print(f"ARKit CSV: {paths.arkit_csv}")
    if trim.enabled:
        print(
            f"Trim: start={trim.start_s:.3f}s, end={trim.end_s:.3f}s "
            f"({arkit.t.size}/{original_frame_count} ARKit frames kept)"
        )
    print(f"Tracking counts: {tracking_counts(arkit.tracking_state)}")
    print_metrics("ARKit-only path summary", metrics)

    if show_plot or save_plot is not None:
        fig, ax = plt.subplots(figsize=(8, 8))
        plot_2d_path(
            ax,
            arkit.points,
            label="ARKit path",
            title="ARKit Top-Down Path",
            color="tab:blue",
        )
        subtitle = f"distance={metrics['arkit_path_length_m']:.2f} m, displacement={metrics['start_end_displacement_m']:.2f} m"
        ax.text(0.02, 0.98, subtitle, transform=ax.transAxes, va="top")
        fig.tight_layout()
        finish_plot(fig, show_plot=show_plot, save_plot=save_plot)


def evaluate_combined(
    paths: BundlePaths,
    alignment: str,
    include_non_normal: bool,
    show_plot: bool,
    save_plot: Optional[Path],
    trim: TrimConfig,
) -> None:
    if paths.imu_csv is None:
        raise FileNotFoundError("Combined evaluation requires imu.csv in the bundle.")

    arkit = load_arkit_csv(paths.arkit_csv, include_non_normal=include_non_normal)
    original_frame_count = arkit.t.size
    arkit = trim_arkit_trajectory(arkit, trim)
    pdr = run_pdr_from_imu_csv(paths.imu_csv)
    paired_times, arkit_points, pdr_points = paired_trajectories(arkit, pdr)
    aligned_pdr = align_pdr_to_arkit(pdr_points, arkit_points, alignment=alignment)
    metrics = error_metrics(paired_times, arkit_points, aligned_pdr, pdr_points)

    print(f"Bundle: {paths.folder}")
    print(f"IMU CSV: {paths.imu_csv}")
    print(f"ARKit CSV: {paths.arkit_csv}")
    print(f"Alignment: {alignment}")
    if trim.enabled:
        print(
            f"Trim: start={trim.start_s:.3f}s, end={trim.end_s:.3f}s "
            f"({arkit.t.size}/{original_frame_count} ARKit frames kept)"
        )
    print(f"Detected PDR steps: {pdr.step_count}")
    print(f"Steps during turns: {pdr.turn_step_count}")
    print(f"Tracking counts: {tracking_counts(arkit.tracking_state)}")
    for line in pdr.turn_summary:
        print(line)
    print_metrics("PDR vs ARKit drift metrics", metrics)

    if show_plot or save_plot is not None:
        errors = np.linalg.norm(aligned_pdr - arkit_points, axis=1)
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        plot_2d_path(
            axes[0],
            arkit_points,
            label="ARKit",
            title=f"Top-Down Trajectory ({alignment})",
            color="tab:blue",
        )
        axes[0].plot(aligned_pdr[:, 0], aligned_pdr[:, 1], marker="o", label="PDR aligned", color="tab:orange")
        axes[0].legend()

        axes[1].plot(paired_times, errors, marker="o")
        axes[1].set_xlabel("time [s]")
        axes[1].set_ylabel("position error [m]")
        axes[1].set_title("Error Over Time")
        axes[1].grid(True, alpha=0.3)

        fig.tight_layout()
        finish_plot(fig, show_plot=show_plot, save_plot=save_plot)


def plot_2d_path(
    ax: plt.Axes,
    points: np.ndarray,
    label: str,
    title: str,
    color: str,
) -> None:
    ax.plot(points[:, 0], points[:, 1], marker="o", label=label, color=color)
    ax.scatter(points[0, 0], points[0, 1], color="tab:green", label="start", zorder=3)
    ax.scatter(points[-1, 0], points[-1, 1], color="tab:red", label="end", zorder=3)
    ax.axis("equal")
    ax.set_xlabel("x [m]")
    ax.set_ylabel("-z [m]")
    ax.set_title(title)
    ax.grid(True, alpha=0.3)


def finish_plot(fig: plt.Figure, show_plot: bool, save_plot: Optional[Path]) -> None:
    if save_plot is not None:
        save_plot.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_plot, dpi=160)
        print(f"Saved plot: {save_plot}")
    if show_plot:
        plt.show()
    else:
        plt.close(fig)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate ARKit-only paths or PDR drift against ARKit.")
    parser.add_argument("bundle", help="Path to a bundle directory, arkit.csv, or any file inside the exported bundle.")
    parser.add_argument(
        "--arkit-only",
        action="store_true",
        help="Validate ARKit logging by plotting/reporting the ARKit path only.",
    )
    parser.add_argument(
        "--alignment",
        choices=ALIGNMENT_CHOICES,
        default=ALIGNMENT_START,
        help="Rigid PDR-to-ARKit alignment for combined evaluation.",
    )
    parser.add_argument(
        "--include-non-normal",
        action="store_true",
        help="Include limited/not_available ARKit frames instead of using normal frames when available.",
    )
    parser.add_argument("--no-plot", action="store_true", help="Print metrics without showing a matplotlib figure.")
    parser.add_argument("--save-plot", type=Path, default=None, help="Optional path to save the generated figure.")
    parser.add_argument(
        "--trim-start-s",
        type=float,
        default=0.0,
        help="Drop this many seconds from the beginning of the valid ARKit time window before computing metrics.",
    )
    parser.add_argument(
        "--trim-end-s",
        type=float,
        default=0.0,
        help="Drop this many seconds from the end of the valid ARKit time window before computing metrics.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    paths = resolve_bundle_paths(Path(args.bundle))
    show_plot = not args.no_plot
    trim = TrimConfig(start_s=args.trim_start_s, end_s=args.trim_end_s)

    if args.arkit_only:
        evaluate_arkit_only(
            paths,
            include_non_normal=args.include_non_normal,
            show_plot=show_plot,
            save_plot=args.save_plot,
            trim=trim,
        )
    else:
        evaluate_combined(
            paths,
            alignment=args.alignment,
            include_non_normal=args.include_non_normal,
            show_plot=show_plot,
            save_plot=args.save_plot,
            trim=trim,
        )


if __name__ == "__main__":
    main()
