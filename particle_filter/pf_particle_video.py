from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from particle_filter.calibration import evaluate_run, load_calibration
    from particle_filter.loaders import load_tag_map
    from particle_filter.metrics import interpolate_points
    from particle_filter.models import ARKitTrajectory, PFResult
    from particle_filter.rfid_pipeline import RFID_MODE_SMOOTHED, RFID_MODES
else:
    from .calibration import evaluate_run, load_calibration
    from .loaders import load_tag_map
    from .metrics import interpolate_points
    from .models import ARKitTrajectory, PFResult
    from .rfid_pipeline import RFID_MODE_SMOOTHED, RFID_MODES


DEFAULT_RESULT_DIR = Path("particle_filter/results/directional_rssi_sweep2/weak_m80_strong_m45")
DEFAULT_EVAL_DIR = Path("Tests/Directional/Test2")
DEFAULT_TAG_MAP = Path("particle_filter/epc_to_tag_coordinates.csv")
DEFAULT_IMU_CHARACTERIZATION = Path("IMU Characterization/results/imu_characterization_results.json")
DEFAULT_OUTPUT = Path("particle_filter/results/combined_overlays/test4_rssi_phase_particles_simulation.mp4")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render ARKit + PF RSSI/phase estimate + PF particle cloud.")
    parser.add_argument("--result-dir", type=Path, default=DEFAULT_RESULT_DIR, help="Result folder containing calibration.json.")
    parser.add_argument("--eval-dir", type=Path, default=DEFAULT_EVAL_DIR, help="Evaluation run folder.")
    parser.add_argument("--tag-map", type=Path, default=DEFAULT_TAG_MAP, help="CSV with epc,tag_id,x_cm,y_cm.")
    parser.add_argument(
        "--imu-characterization",
        type=Path,
        default=DEFAULT_IMU_CHARACTERIZATION,
        help="IMU characterization JSON used while resimulating the PF.",
    )
    parser.add_argument("--rfid-mode", choices=RFID_MODES, default=RFID_MODE_SMOOTHED, help="RFID input mode.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT, help="Output video path.")
    parser.add_argument("--fps", type=int, default=12, help="Animation frames per second.")
    parser.add_argument("--duration-s", type=float, default=18.0, help="Rendered animation duration in seconds.")
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


def save_particle_video(
    path: Path,
    arkit: ARKitTrajectory,
    pf_result: PFResult,
    title: str,
    fps: int = 12,
    duration_s: float = 18.0,
) -> Path:
    if pf_result.particle_times_unix is None or pf_result.particle_points is None:
        raise ValueError("PF result does not contain particle traces. Re-run with trace_particles=True.")

    _configure_matplotlib_cache()
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.animation import FFMpegWriter, FuncAnimation, PillowWriter

    path.parent.mkdir(parents=True, exist_ok=True)

    start = max(float(arkit.unix_t[0]), float(pf_result.times_unix[0]), float(pf_result.particle_times_unix[0]))
    end = min(float(arkit.unix_t[-1]), float(pf_result.times_unix[-1]), float(pf_result.particle_times_unix[-1]))
    if end <= start:
        raise ValueError("No overlapping time window for particle simulation video.")

    frame_count = max(2, int(fps * duration_s))
    frame_times = np.linspace(start, end, frame_count)

    arkit_xy = _interp_path(arkit.unix_t, arkit.points_map, frame_times)
    pf_xy = _interp_path(pf_result.times_unix, pf_result.points, frame_times)
    particle_traces = [
        _interp_path(pf_result.particle_times_unix, pf_result.particle_points[:, idx, :], frame_times)
        for idx in range(pf_result.particle_points.shape[1])
    ]
    particle_xy = np.stack(particle_traces, axis=1)

    point_sets = [
        _finite_points(arkit.points_map),
        _finite_points(pf_result.points),
        _finite_points(particle_xy.reshape(-1, 2)),
    ]
    combined = np.vstack([points for points in point_sets if points.size])
    mins = np.nanmin(combined, axis=0) - 0.5
    maxs = np.nanmax(combined, axis=0) + 0.5

    fig, ax = plt.subplots(figsize=(8.5, 8.5))
    ax.set_xlim(float(mins[0]), float(maxs[0]))
    ax.set_ylim(float(mins[1]), float(maxs[1]))
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, alpha=0.25)
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_title(title)

    particle_scatter = ax.scatter([], [], color="gray", s=18, alpha=0.35, label="PF particles")
    arkit_line, = ax.plot([], [], color="tab:blue", linewidth=2.4, label="ARKit")
    pf_line, = ax.plot([], [], color="tab:green", linewidth=2.2, label="PF RSSI + phase")
    arkit_dot = ax.scatter([], [], color="tab:blue", s=60)
    pf_dot = ax.scatter([], [], color="tab:green", s=52)
    time_text = ax.text(0.02, 0.98, "", transform=ax.transAxes, va="top")
    ax.legend(loc="lower left", fontsize="small")

    def update(i: int):
        particle_scatter.set_offsets(particle_xy[i])
        arkit_line.set_data(arkit_xy[: i + 1, 0], arkit_xy[: i + 1, 1])
        pf_line.set_data(pf_xy[: i + 1, 0], pf_xy[: i + 1, 1])
        arkit_dot.set_offsets([arkit_xy[i]])
        pf_dot.set_offsets([pf_xy[i]])
        time_text.set_text(f"t = {frame_times[i] - start:.1f}s")
        return particle_scatter, arkit_line, pf_line, arkit_dot, pf_dot, time_text

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


def main() -> None:
    args = build_parser().parse_args()
    tag_map = load_tag_map(args.tag_map)
    calibration = load_calibration(args.result_dir / "calibration.json")
    result = evaluate_run(
        args.eval_dir,
        tag_map,
        calibration,
        imu_characterization_path=args.imu_characterization,
        rfid_mode=args.rfid_mode,
        trace_particles=True,
    )
    run = result["run"]
    pf_result = result["pf_result"]
    saved_path = save_particle_video(
        args.out.expanduser().resolve(),
        run.arkit,
        pf_result,
        title=f"{run.name}: ARKit, PF particles, and PF RSSI + phase",
        fps=args.fps,
        duration_s=args.duration_s,
    )
    print(f"Saved particle simulation: {saved_path}")


if __name__ == "__main__":
    main()
