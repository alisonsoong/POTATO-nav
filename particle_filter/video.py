from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import numpy as np

from .metrics import interpolate_points
from .models import ARKitTrajectory, PFResult, TagMap


def _interp_path(times: np.ndarray, points: np.ndarray, frame_times: np.ndarray) -> np.ndarray:
    if times.size < 2 or points.shape[0] < 2:
        return np.repeat(points[:1], len(frame_times), axis=0)
    mask = (frame_times >= times[0]) & (frame_times <= times[-1])
    out = np.full((len(frame_times), 2), np.nan, dtype=float)
    out[mask] = interpolate_points(times, points, frame_times[mask])
    return out


def save_simulation_video(
    path: Path,
    arkit: ARKitTrajectory,
    baseline_times: np.ndarray,
    baseline_points: np.ndarray,
    pf_result: PFResult,
    tag_map: TagMap,
    title: str,
    fps: int = 12,
    duration_s: float = 18.0,
) -> Path:
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "matplotlib"))
    os.environ.setdefault("XDG_CACHE_HOME", str(Path(tempfile.gettempdir()) / "fontconfig-cache"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation, FFMpegWriter, PillowWriter

    path.parent.mkdir(parents=True, exist_ok=True)

    start = max(float(arkit.unix_t[0]), float(baseline_times[0]), float(pf_result.times_unix[0]))
    end = min(float(arkit.unix_t[-1]), float(baseline_times[-1]), float(pf_result.times_unix[-1]))
    if end <= start:
        raise ValueError("No overlapping time window for simulation video.")
    frame_count = max(2, int(fps * duration_s))
    frame_times = np.linspace(start, end, frame_count)

    arkit_xy = _interp_path(arkit.unix_t, arkit.points_map, frame_times)
    pdr_xy = _interp_path(baseline_times, baseline_points, frame_times)
    pf_xy = _interp_path(pf_result.times_unix, pf_result.points, frame_times)

    particle_xy = None
    chosen_xy = None
    if pf_result.particle_times_unix is not None and pf_result.particle_points is not None:
        traces = []
        for idx in range(pf_result.particle_points.shape[1]):
            traces.append(_interp_path(pf_result.particle_times_unix, pf_result.particle_points[:, idx, :], frame_times))
        particle_xy = np.stack(traces, axis=1) if traces else None
    if pf_result.particle_times_unix is not None and pf_result.chosen_particle_points is not None:
        chosen_xy = _interp_path(pf_result.particle_times_unix, pf_result.chosen_particle_points, frame_times)

    tags = tag_map.tags
    all_points = [arkit.points_map, baseline_points, pf_result.points, tags[["x_m", "y_m"]].to_numpy(dtype=float)]
    if particle_xy is not None:
        all_points.append(particle_xy.reshape(-1, 2))
    combined = np.vstack([pts[np.isfinite(pts).all(axis=1)] for pts in all_points if pts.size])
    mins = np.nanmin(combined, axis=0) - 0.5
    maxs = np.nanmax(combined, axis=0) + 0.5

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.set_xlim(float(mins[0]), float(maxs[0]))
    ax.set_ylim(float(mins[1]), float(maxs[1]))
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, alpha=0.25)
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_title(title)

    ax.scatter(tags["x_m"], tags["y_m"], color="tab:red", marker="x", s=45, label="RFID tags")
    for row in tags.itertuples(index=False):
        ax.text(float(row.x_m), float(row.y_m), str(row.tag_id), fontsize=8, ha="left", va="bottom")

    arkit_line, = ax.plot([], [], color="tab:blue", linewidth=2, label="ARKit truth")
    pdr_line, = ax.plot([], [], color="tab:orange", linewidth=1.8, label="PDR only")
    pf_line, = ax.plot([], [], color="tab:green", linewidth=1.8, label="PF estimate")
    particle_scatter = ax.scatter([], [], color="gray", s=12, alpha=0.30, label="sample particles")
    chosen_line, = ax.plot([], [], color="black", linewidth=1.5, alpha=0.8, label="chosen particle")
    arkit_dot = ax.scatter([], [], color="tab:blue", s=55)
    pdr_dot = ax.scatter([], [], color="tab:orange", s=45)
    pf_dot = ax.scatter([], [], color="tab:green", s=45)
    time_text = ax.text(0.02, 0.98, "", transform=ax.transAxes, va="top")
    ax.legend(loc="lower left", fontsize="small")

    def update(i: int):
        arkit_line.set_data(arkit_xy[: i + 1, 0], arkit_xy[: i + 1, 1])
        pdr_line.set_data(pdr_xy[: i + 1, 0], pdr_xy[: i + 1, 1])
        pf_line.set_data(pf_xy[: i + 1, 0], pf_xy[: i + 1, 1])
        arkit_dot.set_offsets([arkit_xy[i]])
        pdr_dot.set_offsets([pdr_xy[i]])
        pf_dot.set_offsets([pf_xy[i]])
        if particle_xy is not None:
            particle_scatter.set_offsets(particle_xy[i])
        if chosen_xy is not None:
            chosen_line.set_data(chosen_xy[: i + 1, 0], chosen_xy[: i + 1, 1])
        time_text.set_text(f"t = {frame_times[i] - start:.1f}s")
        return (
            arkit_line,
            pdr_line,
            pf_line,
            particle_scatter,
            chosen_line,
            arkit_dot,
            pdr_dot,
            pf_dot,
            time_text,
        )

    animation = FuncAnimation(fig, update, frames=frame_count, interval=1000 / fps, blit=False)

    output_path = path
    if path.suffix.lower() == ".mp4" and shutil.which("ffmpeg"):
        animation.save(path, writer=FFMpegWriter(fps=fps, bitrate=1800))
    else:
        if path.suffix.lower() != ".gif":
            output_path = path.with_suffix(".gif")
        animation.save(output_path, writer=PillowWriter(fps=fps))
    plt.close(fig)
    return output_path
