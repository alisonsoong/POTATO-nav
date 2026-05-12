from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable

import numpy as np
import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from particle_filter.calibration import evaluate_run, flatten_metrics, load_calibration
    from particle_filter.loaders import load_tag_map
    from particle_filter.metrics import interpolate_points
    from particle_filter.models import ARKitTrajectory, CalibrationResult, PFResult, TagMap
    from particle_filter.rfid_pipeline import RFID_MODE_SMOOTHED, RFID_MODES
else:
    from .calibration import evaluate_run, flatten_metrics, load_calibration
    from .loaders import load_tag_map
    from .metrics import interpolate_points
    from .models import ARKitTrajectory, CalibrationResult, PFResult, TagMap
    from .rfid_pipeline import RFID_MODE_SMOOTHED, RFID_MODES


DEFAULT_COMBINED_DIR = Path("particle_filter/results/directional_rssi_sweep2/weak_m80_strong_m45")
DEFAULT_RSSI_DIR = Path("particle_filter/results/test4rssionly")
DEFAULT_PHASE_DIR = Path("particle_filter/results/test4phase")
DEFAULT_EVAL_DIR = Path("Tests/Directional/Test2")
DEFAULT_TAG_MAP = Path("particle_filter/epc_to_tag_coordinates.csv")
DEFAULT_IMU_CHARACTERIZATION = Path("IMU Characterization/results/imu_characterization_results.json")
DEFAULT_OUT_DIR = Path("particle_filter/results/combined_overlays")


@dataclass(frozen=True)
class Scenario:
    key: str
    method: str
    label: str
    result_dir: Path
    color: str
    linestyle: str = "-"


@dataclass(frozen=True)
class ScenarioResult:
    scenario: Scenario
    calibration: CalibrationResult
    result: Dict[str, object]

    @property
    def pf_result(self) -> PFResult:
        return self.result["pf_result"]  # type: ignore[return-value]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Resimulate and overlay ARKit, IMU-only, PF RSSI+phase, PF RSSI-only, "
            "and PF phase-only trajectories."
        )
    )
    parser.add_argument("--eval-dir", type=Path, default=DEFAULT_EVAL_DIR, help="Evaluation run folder to resimulate.")
    parser.add_argument("--tag-map", type=Path, default=DEFAULT_TAG_MAP, help="CSV with epc,tag_id,x_cm,y_cm.")
    parser.add_argument(
        "--imu-characterization",
        type=Path,
        default=DEFAULT_IMU_CHARACTERIZATION,
        help="IMU characterization JSON used for gyro/PDR corrections.",
    )
    parser.add_argument(
        "--rfid-mode",
        choices=RFID_MODES,
        default=RFID_MODE_SMOOTHED,
        help="RFID input mode used when resimulating trajectories.",
    )
    parser.add_argument(
        "--combined-dir",
        type=Path,
        default=DEFAULT_COMBINED_DIR,
        help="Result folder for PF RSSI + phase combined.",
    )
    parser.add_argument("--rssi-dir", type=Path, default=DEFAULT_RSSI_DIR, help="Result folder for PF RSSI-only.")
    parser.add_argument("--phase-dir", type=Path, default=DEFAULT_PHASE_DIR, help="Result folder for PF phase-only.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Output directory.")
    parser.add_argument("--prefix", default="test4_overlay", help="Output filename prefix.")
    parser.add_argument("--video-fps", type=int, default=12, help="Simulation video frames per second.")
    parser.add_argument("--video-duration-s", type=float, default=18.0, help="Rendered video duration in seconds.")
    parser.add_argument("--no-video", action="store_true", help="Skip simulation video generation.")
    return parser


def _configure_matplotlib_cache() -> None:
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "matplotlib"))
    os.environ.setdefault("XDG_CACHE_HOME", str(Path(tempfile.gettempdir()) / "fontconfig-cache"))


def _interp_path(times: np.ndarray, points: np.ndarray, frame_times: np.ndarray) -> np.ndarray:
    if times.size < 2 or points.shape[0] < 2:
        return np.repeat(points[:1], len(frame_times), axis=0)
    mask = (frame_times >= times[0]) & (frame_times <= times[-1])
    out = np.full((len(frame_times), 2), np.nan, dtype=float)
    out[mask] = interpolate_points(times, points, frame_times[mask])
    return out


def _finite_points(points: np.ndarray) -> np.ndarray:
    if points.size == 0:
        return np.empty((0, 2), dtype=float)
    return points[np.isfinite(points).all(axis=1)]


def _axis_limits(point_sets: Iterable[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    finite_sets = [_finite_points(points) for points in point_sets]
    finite_sets = [points for points in finite_sets if points.size]
    if not finite_sets:
        raise ValueError("No finite points available for plotting.")
    combined = np.vstack(finite_sets)
    return np.nanmin(combined, axis=0) - 0.5, np.nanmax(combined, axis=0) + 0.5


def _tag_points(tag_map: TagMap) -> np.ndarray:
    return tag_map.tags[["x_m", "y_m"]].to_numpy(dtype=float)


def save_overlay_plot(
    path: Path,
    arkit: ARKitTrajectory,
    baseline_points: np.ndarray,
    scenario_results: list[ScenarioResult],
    tag_map: TagMap,
    title: str,
) -> None:
    _configure_matplotlib_cache()
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 8))

    ax.plot(arkit.points_map[:, 0], arkit.points_map[:, 1], color="tab:blue", linewidth=2.4, label="ARKit")
    ax.plot(
        baseline_points[:, 0],
        baseline_points[:, 1],
        color="tab:orange",
        linewidth=1.8,
        linestyle="--",
        marker="o",
        markersize=2,
        label="IMU-only",
    )
    for scenario_result in scenario_results:
        pf_points = scenario_result.pf_result.points
        scenario = scenario_result.scenario
        ax.plot(
            pf_points[:, 0],
            pf_points[:, 1],
            color=scenario.color,
            linewidth=1.9,
            linestyle=scenario.linestyle,
            marker="o",
            markersize=2,
            label=scenario.label,
        )

    ax.scatter([0.0], [0.0], color="black", s=40, label="start/end")
    tags = tag_map.tags
    ax.scatter(tags["x_m"], tags["y_m"], color="tab:red", marker="x", s=50, label="tags")
    for row in tags.itertuples(index=False):
        ax.text(float(row.x_m), float(row.y_m), str(row.tag_id), fontsize=8, ha="left", va="bottom")

    mins, maxs = _axis_limits(
        [arkit.points_map, baseline_points, _tag_points(tag_map)]
        + [scenario_result.pf_result.points for scenario_result in scenario_results]
    )
    ax.set_xlim(float(mins[0]), float(maxs[0]))
    ax.set_ylim(float(mins[1]), float(maxs[1]))
    ax.set_title(title)
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def best_pf_result(scenario_results: list[ScenarioResult]) -> ScenarioResult:
    return min(
        scenario_results,
        key=lambda scenario_result: float(scenario_result.result["pf_metrics"]["rmse_m"]),  # type: ignore[index]
    )


def save_best_pf_plot(
    path: Path,
    arkit: ARKitTrajectory,
    scenario_result: ScenarioResult,
    tag_map: TagMap,
    run_name: str,
) -> None:
    _configure_matplotlib_cache()
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 8))

    pf_points = scenario_result.pf_result.points
    rmse_m = float(scenario_result.result["pf_metrics"]["rmse_m"])  # type: ignore[index]
    scenario = scenario_result.scenario

    ax.plot(arkit.points_map[:, 0], arkit.points_map[:, 1], color="tab:blue", linewidth=2.5, label="ARKit")
    ax.plot(
        pf_points[:, 0],
        pf_points[:, 1],
        color=scenario.color,
        linewidth=2.2,
        linestyle=scenario.linestyle,
        marker="o",
        markersize=2,
        label=f"{scenario.label} (RMSE {rmse_m:.3f} m)",
    )

    tags = tag_map.tags
    ax.scatter(tags["x_m"], tags["y_m"], color="tab:red", marker="x", s=55, label="tags")
    for row in tags.itertuples(index=False):
        ax.text(float(row.x_m), float(row.y_m), str(row.tag_id), fontsize=8, ha="left", va="bottom")

    mins, maxs = _axis_limits([arkit.points_map, pf_points, _tag_points(tag_map)])
    ax.set_xlim(float(mins[0]), float(maxs[0]))
    ax.set_ylim(float(mins[1]), float(maxs[1]))
    ax.set_title(f"{run_name}: ARKit vs best PF trajectory")
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def save_overlay_video(
    path: Path,
    arkit: ARKitTrajectory,
    baseline_times: np.ndarray,
    baseline_points: np.ndarray,
    scenario_result: ScenarioResult,
    tag_map: TagMap,
    title: str,
    fps: int,
    duration_s: float,
) -> Path:
    _configure_matplotlib_cache()
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.animation import FFMpegWriter, FuncAnimation, PillowWriter

    path.parent.mkdir(parents=True, exist_ok=True)

    starts = [float(arkit.unix_t[0]), float(baseline_times[0])]
    ends = [float(arkit.unix_t[-1]), float(baseline_times[-1])]
    starts.append(float(scenario_result.pf_result.times_unix[0]))
    ends.append(float(scenario_result.pf_result.times_unix[-1]))

    start = max(starts)
    end = min(ends)
    if end <= start:
        raise ValueError("No overlapping time window for overlay simulation video.")

    frame_count = max(2, int(fps * duration_s))
    frame_times = np.linspace(start, end, frame_count)

    arkit_xy = _interp_path(arkit.unix_t, arkit.points_map, frame_times)
    baseline_xy = _interp_path(baseline_times, baseline_points, frame_times)
    pf_xy = _interp_path(
        scenario_result.pf_result.times_unix,
        scenario_result.pf_result.points,
        frame_times,
    )

    mins, maxs = _axis_limits(
        [arkit.points_map, baseline_points, _tag_points(tag_map)]
        + [scenario_result.pf_result.points]
    )

    fig, ax = plt.subplots(figsize=(8.5, 8.5))
    ax.set_xlim(float(mins[0]), float(maxs[0]))
    ax.set_ylim(float(mins[1]), float(maxs[1]))
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, alpha=0.25)
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_title(title)

    tags = tag_map.tags
    ax.scatter(tags["x_m"], tags["y_m"], color="tab:red", marker="x", s=45, label="RFID tags")
    for row in tags.itertuples(index=False):
        ax.text(float(row.x_m), float(row.y_m), str(row.tag_id), fontsize=8, ha="left", va="bottom")

    arkit_line, = ax.plot([], [], color="tab:blue", linewidth=2.2, label="ARKit")
    baseline_line, = ax.plot([], [], color="tab:orange", linewidth=1.8, linestyle="--", label="IMU-only")
    pf_line, = ax.plot(
        [],
        [],
        color=scenario_result.scenario.color,
        linewidth=2.0,
        linestyle=scenario_result.scenario.linestyle,
        label=scenario_result.scenario.label,
    )

    arkit_dot = ax.scatter([], [], color="tab:blue", s=55)
    baseline_dot = ax.scatter([], [], color="tab:orange", s=45)
    pf_dot = ax.scatter([], [], color=scenario_result.scenario.color, s=45)
    time_text = ax.text(0.02, 0.98, "", transform=ax.transAxes, va="top")
    ax.legend(loc="lower left", fontsize="small")

    def update(i: int):
        arkit_line.set_data(arkit_xy[: i + 1, 0], arkit_xy[: i + 1, 1])
        baseline_line.set_data(baseline_xy[: i + 1, 0], baseline_xy[: i + 1, 1])
        pf_line.set_data(pf_xy[: i + 1, 0], pf_xy[: i + 1, 1])
        arkit_dot.set_offsets([arkit_xy[i]])
        baseline_dot.set_offsets([baseline_xy[i]])
        pf_dot.set_offsets([pf_xy[i]])

        time_text.set_text(f"t = {frame_times[i] - start:.1f}s")
        return arkit_line, baseline_line, pf_line, arkit_dot, baseline_dot, pf_dot, time_text

    animation = FuncAnimation(fig, update, frames=frame_count, interval=1000 / fps, blit=False)

    output_path = path
    if path.suffix.lower() == ".mp4" and shutil.which("ffmpeg"):
        animation.save(path, writer=FFMpegWriter(fps=fps, bitrate=2200))
    else:
        if path.suffix.lower() != ".gif":
            output_path = path.with_suffix(".gif")
        animation.save(output_path, writer=PillowWriter(fps=fps))
    plt.close(fig)
    return output_path


def save_measurement_model_videos(
    out_dir: Path,
    prefix: str,
    arkit: ARKitTrajectory,
    baseline_times: np.ndarray,
    baseline_points: np.ndarray,
    scenario_results: list[ScenarioResult],
    tag_map: TagMap,
    run_name: str,
    fps: int,
    duration_s: float,
) -> list[Path]:
    saved_paths = []
    for scenario_result in scenario_results:
        video_path = out_dir / f"{prefix}_{scenario_result.scenario.key}_simulation.mp4"
        saved_paths.append(
            save_overlay_video(
                video_path,
                arkit,
                baseline_times,
                baseline_points,
                scenario_result,
                tag_map,
                f"{run_name}: ARKit, IMU-only, and {scenario_result.scenario.label}",
                fps=fps,
                duration_s=duration_s,
            )
        )
    return saved_paths


def _metric_row(
    run_label: str,
    source_label: str,
    source_dir: Path,
    method: str,
    display_name: str,
    metrics: Dict[str, float],
    calibration: CalibrationResult,
    accepted_rfid_count: int = 0,
) -> Dict[str, object]:
    row = flatten_metrics(
        run_label=run_label,
        method=method,
        metrics=metrics,
        calibration=calibration,
        accepted_rfid_count=accepted_rfid_count,
    )
    return {
        "source": source_label,
        "source_result_dir": str(source_dir),
        "display_name": display_name,
        "rfid_measurement_model": calibration.pf_config.rfid_measurement_model,
        **row,
    }


def write_merged_metrics(
    path: Path,
    reference: ScenarioResult,
    scenario_results: list[ScenarioResult],
) -> None:
    run_label = reference.result["run"].name  # type: ignore[union-attr]
    rows = [
        _metric_row(
            run_label=run_label,
            source_label=reference.scenario.key,
            source_dir=reference.scenario.result_dir,
            method="imu_only",
            display_name="IMU-only",
            metrics=reference.result["baseline_metrics"],  # type: ignore[arg-type]
            calibration=reference.calibration,
        )
    ]
    for scenario_result in scenario_results:
        scenario = scenario_result.scenario
        rows.append(
            _metric_row(
                run_label=run_label,
                source_label=scenario.key,
                source_dir=scenario.result_dir,
                method=scenario.method,
                display_name=scenario.label,
                metrics=scenario_result.result["pf_metrics"],  # type: ignore[arg-type]
                calibration=scenario_result.calibration,
                accepted_rfid_count=scenario_result.pf_result.accepted_rfid_count,
            )
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _alignment_delta(reference: ScenarioResult, other: ScenarioResult) -> float:
    ref_arkit = reference.result["run"].arkit  # type: ignore[union-attr]
    other_arkit = other.result["run"].arkit  # type: ignore[union-attr]
    return float(
        abs(ref_arkit.rotation_rad - other_arkit.rotation_rad)
        + np.linalg.norm(ref_arkit.translation_xy - other_arkit.translation_xy)
    )


def _make_scenarios(args: argparse.Namespace) -> list[Scenario]:
    return [
        Scenario(
            key="combined",
            method="pf_rssi_phase",
            label="PF RSSI + phase",
            result_dir=args.combined_dir,
            color="tab:green",
        ),
        Scenario(
            key="rssi_only",
            method="pf_rssi_only",
            label="PF RSSI only",
            result_dir=args.rssi_dir,
            color="tab:purple",
            linestyle="-.",
        ),
        Scenario(
            key="phase_only",
            method="pf_phase_only",
            label="PF phase only",
            result_dir=args.phase_dir,
            color="tab:brown",
            linestyle=":",
        ),
    ]


def main() -> None:
    args = build_parser().parse_args()
    out_dir = args.out_dir.expanduser().resolve()
    tag_map = load_tag_map(args.tag_map)

    scenario_results: list[ScenarioResult] = []
    for scenario in _make_scenarios(args):
        result_dir = scenario.result_dir.expanduser().resolve()
        calibration = load_calibration(result_dir / "calibration.json")
        result = evaluate_run(
            args.eval_dir,
            tag_map,
            calibration,
            imu_characterization_path=args.imu_characterization,
            rfid_mode=args.rfid_mode,
            trace_particles=False,
        )
        scenario_results.append(
            ScenarioResult(
                scenario=Scenario(
                    key=scenario.key,
                    method=scenario.method,
                    label=scenario.label,
                    result_dir=result_dir,
                    color=scenario.color,
                    linestyle=scenario.linestyle,
                ),
                calibration=calibration,
                result=result,
            )
        )

    reference = scenario_results[0]
    run = reference.result["run"]
    arkit = run.arkit  # type: ignore[union-attr]
    baseline_times = reference.result["baseline_times"]  # type: ignore[assignment]
    baseline_points = reference.result["baseline_points"]  # type: ignore[assignment]
    run_name = run.name  # type: ignore[union-attr]

    for scenario_result in scenario_results[1:]:
        delta = _alignment_delta(reference, scenario_result)
        if delta > 0.02:
            print(
                f"Note: {scenario_result.scenario.label} uses a slightly different ARKit alignment "
                f"(combined rotation/translation delta score {delta:.3f}). "
                "The overlay keeps a single ARKit/IMU reference and plots all PF paths in tag-map coordinates."
            )

    title = f"{run_name}: ARKit, IMU-only, and PF measurement modes"
    plot_path = out_dir / f"{args.prefix}_trajectory.png"
    best_plot_path = out_dir / f"{args.prefix}_best_trajectory.png"
    metrics_path = out_dir / f"{args.prefix}_metrics.csv"

    best_result = best_pf_result(scenario_results)
    save_overlay_plot(plot_path, arkit, baseline_points, scenario_results, tag_map, title)
    save_best_pf_plot(best_plot_path, arkit, best_result, tag_map, run_name)
    write_merged_metrics(metrics_path, reference, scenario_results)

    saved_videos: list[Path] = []
    if not args.no_video:
        saved_videos = save_measurement_model_videos(
            out_dir,
            args.prefix,
            arkit,
            baseline_times,
            baseline_points,
            scenario_results,
            tag_map,
            run_name,
            fps=args.video_fps,
            duration_s=args.video_duration_s,
        )

    print(f"Saved overlay plot: {plot_path}")
    print(f"Saved best PF plot: {best_plot_path} ({best_result.scenario.label})")
    print(f"Saved merged metrics: {metrics_path}")
    for saved_video in saved_videos:
        print(f"Saved measurement-model simulation: {saved_video}")


if __name__ == "__main__":
    main()
