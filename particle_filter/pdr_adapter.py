from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .models import MotionData


REPO_ROOT = Path(__file__).resolve().parents[1]
PDR_DIR = REPO_ROOT / "PDR"
if str(PDR_DIR) not in sys.path:
    sys.path.insert(0, str(PDR_DIR))

from step_detection.step_detection import detect_steps, first_time_column, load_motion_dataframe  # noqa: E402


ACCEL_X_COLUMNS = (
    "step_accel_x",
    "user_accel_x",
    "user_accel_x_bias_corrected",
    "fused_accel_x",
    "accel_x",
)
ACCEL_Y_COLUMNS = (
    "step_accel_y",
    "user_accel_y",
    "user_accel_y_bias_corrected",
    "fused_accel_y",
    "accel_y",
)
ACCEL_Z_COLUMNS = (
    "step_accel_z",
    "user_accel_z",
    "user_accel_z_bias_corrected",
    "fused_accel_z",
    "accel_z",
)


def _first_numeric(df: pd.DataFrame, candidates: tuple[str, ...]) -> np.ndarray:
    for name in candidates:
        if name in df.columns:
            return pd.to_numeric(df[name], errors="coerce").to_numpy(dtype=float)
    raise KeyError(f"Missing required column. Tried: {', '.join(candidates)}")


def _relative_time(df: pd.DataFrame) -> np.ndarray:
    if "elapsed_since_run_start_s" in df.columns:
        t = pd.to_numeric(df["elapsed_since_run_start_s"], errors="coerce").to_numpy(dtype=float)
    else:
        time_col = first_time_column(df)
        t = pd.to_numeric(df[time_col], errors="coerce").to_numpy(dtype=float)
        t = t - t[np.isfinite(t)][0]
    return t


def _unix_time(df: pd.DataFrame, rel_t: np.ndarray) -> np.ndarray:
    if "unix_timestamp_s" in df.columns:
        return pd.to_numeric(df["unix_timestamp_s"], errors="coerce").to_numpy(dtype=float)
    return rel_t.copy()


def load_imu_characterization(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    path = path.expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"IMU characterization JSON not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _integrate_gyro_heading(rel_t: np.ndarray, gyro_z: np.ndarray) -> np.ndarray:
    heading = np.zeros_like(gyro_z, dtype=float)
    for i in range(1, len(gyro_z)):
        dt = rel_t[i] - rel_t[i - 1]
        if not np.isfinite(dt) or dt <= 0:
            dt = 0.0
        heading[i] = heading[i - 1] + 0.5 * (gyro_z[i] + gyro_z[i - 1]) * dt
    return heading


def _load_heading(df: pd.DataFrame, rel_t: np.ndarray, imu_characterization: dict[str, Any]) -> tuple[np.ndarray, str, dict[str, float | str]]:
    recommended = imu_characterization.get("recommended_corrections", {})
    preferred = recommended.get("preferred_heading_source")
    correction_summary: dict[str, float | str] = {}

    if preferred == "bias_corrected_gyro_integration":
        gyro_z = _first_numeric(df, ("gyro_z", "raw_gyro_z", "gyro_z_bias_corrected"))
        bias = float(recommended.get("gyro_bias_to_subtract_rad_per_s", {}).get("z", 0.0))
        scale = float(recommended.get("gyro_z_scale_factor", 1.0))
        if bool(recommended.get("subtract_gyro_bias", False)):
            gyro_z = gyro_z - bias
            correction_summary["gyro_z_bias_subtracted_rad_per_s"] = bias
        if bool(recommended.get("apply_gyro_scale_correction", False)) and scale != 0.0:
            gyro_z = gyro_z / scale
            correction_summary["gyro_z_scale_factor_applied"] = scale
        correction_summary["heading_source_reason"] = str(recommended.get("heading_source_reason", ""))
        return _integrate_gyro_heading(rel_t, gyro_z), "bias_corrected_gyro_integration", correction_summary

    if "heading_gyro_bias_corrected" in df.columns:
        return (
            pd.to_numeric(df["heading_gyro_bias_corrected"], errors="coerce").to_numpy(dtype=float),
            "heading_gyro_bias_corrected",
            correction_summary,
        )
    if "yaw_unwrapped" in df.columns:
        return (
            pd.to_numeric(df["yaw_unwrapped"], errors="coerce").to_numpy(dtype=float),
            "yaw_unwrapped",
            correction_summary,
        )
    if "yaw" in df.columns:
        return (
            np.unwrap(pd.to_numeric(df["yaw"], errors="coerce").to_numpy(dtype=float)),
            "coremotion_yaw",
            correction_summary,
        )

    gyro_z = _first_numeric(df, ("gyro_z_bias_corrected", "gyro_z", "raw_gyro_z"))
    return _integrate_gyro_heading(rel_t, gyro_z), "gyro_integration", correction_summary


def load_motion_steps(
    imu_csv: Path,
    imu_characterization_path: Path | None = None,
    base_step_length_m: float = 0.7,
    low_hz: float = 0.5,
    high_hz: float = 3.0,
    min_step_gap_s: float = 0.35,
    prominence: float = 0.03,
) -> MotionData:
    imu_characterization = load_imu_characterization(imu_characterization_path)
    df = load_motion_dataframe(imu_csv)
    rel_t = _relative_time(df)
    unix_t = _unix_time(df, rel_t)
    ax = _first_numeric(df, ACCEL_X_COLUMNS)
    ay = _first_numeric(df, ACCEL_Y_COLUMNS)
    az = _first_numeric(df, ACCEL_Z_COLUMNS)
    heading, heading_source, correction_summary = _load_heading(df, rel_t, imu_characterization)

    valid = np.isfinite(rel_t) & np.isfinite(unix_t) & np.isfinite(ax) & np.isfinite(ay) & np.isfinite(az) & np.isfinite(heading)
    rel_t = rel_t[valid]
    unix_t = unix_t[valid]
    ax = ax[valid]
    ay = ay[valid]
    az = az[valid]
    heading = heading[valid]

    order = np.argsort(rel_t)
    rel_t = rel_t[order]
    unix_t = unix_t[order]
    ax = ax[order]
    ay = ay[order]
    az = az[order]
    heading = heading[order]

    rel_t = rel_t - rel_t[0]
    peaks, _, _ = detect_steps(
        rel_t,
        ax,
        ay,
        az,
        low=low_hz,
        high=high_hz,
        min_step_gap_s=min_step_gap_s,
        prominence=prominence,
    )
    if len(peaks) == 0:
        return MotionData(
            unix_t=unix_t,
            rel_t=rel_t,
            step_times_unix=np.array([], dtype=float),
            step_times_rel=np.array([], dtype=float),
            step_headings_rad=np.array([], dtype=float),
            step_count=0,
            base_step_length_m=base_step_length_m,
            heading_source=heading_source,
            correction_summary=correction_summary,
        )

    step_times_rel = rel_t[peaks]
    step_times_unix = np.interp(step_times_rel, rel_t, unix_t)
    step_headings = np.unwrap(heading)[peaks]
    step_headings = step_headings - step_headings[0]

    return MotionData(
        unix_t=unix_t,
        rel_t=rel_t,
        step_times_unix=step_times_unix,
        step_times_rel=step_times_rel,
        step_headings_rad=step_headings,
        step_count=len(peaks),
        base_step_length_m=base_step_length_m,
        heading_source=heading_source,
        correction_summary=correction_summary,
    )


def imu_only_trajectory(
    motion: MotionData,
    step_scale: float,
    heading_offset_rad: float = 0.0,
    heading_sign: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    x = 0.0
    y = 0.0
    points = [[x, y]]
    times = [motion.unix_t[0] if motion.unix_t.size else 0.0]
    for t, heading in zip(motion.step_times_unix, motion.step_headings_rad):
        theta = heading_sign * heading + heading_offset_rad
        step_length = motion.base_step_length_m * step_scale
        x += step_length * np.sin(theta)
        y += step_length * np.cos(theta)
        points.append([x, y])
        times.append(float(t))
    return np.asarray(times, dtype=float), np.asarray(points, dtype=float)
