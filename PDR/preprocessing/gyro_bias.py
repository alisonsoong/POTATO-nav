from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd

try:
    from .csv_io import numeric_series, optional_numeric_series
except ImportError:  # pragma: no cover - direct script execution support
    from csv_io import numeric_series, optional_numeric_series


def subtract_gyro_bias(
    df: pd.DataFrame,
    gyro_bias_rad_per_s: Dict[str, float],
    t: Optional[np.ndarray] = None,
    initial_stationary_s: float = 0.0,
    min_stationary_samples: int = 10,
) -> Dict[str, Dict[str, float]]:
    gyro_x = numeric_series(df, "gyro_x")
    gyro_y = numeric_series(df, "gyro_y")
    gyro_z = numeric_series(df, "gyro_z")
    gyro_by_axis = {"x": gyro_x, "y": gyro_y, "z": gyro_z}

    bias_to_subtract = {axis: float(value) for axis, value in gyro_bias_rad_per_s.items()}
    bias_source = "static_flat_characterization"
    warnings = []
    initial_segment_report = None

    if t is not None and initial_stationary_s > 0:
        initial_segment_report = estimate_initial_stationary_bias(
            df,
            t,
            gyro_by_axis,
            initial_stationary_s=initial_stationary_s,
            min_stationary_samples=min_stationary_samples,
        )
        if initial_segment_report["usable"]:
            bias_to_subtract = initial_segment_report["gyro_bias_rad_per_s"]
            bias_source = "initial_stationary_segment"
        else:
            warnings.extend(initial_segment_report["warnings"])

    df["gyro_x_bias_corrected"] = gyro_x - bias_to_subtract["x"]
    df["gyro_y_bias_corrected"] = gyro_y - bias_to_subtract["y"]
    df["gyro_z_bias_corrected"] = gyro_z - bias_to_subtract["z"]

    return {
        "gyro_bias_source": bias_source,
        "gyro_bias_subtracted_rad_per_s": {
            "x": bias_to_subtract["x"],
            "y": bias_to_subtract["y"],
            "z": bias_to_subtract["z"],
        },
        "static_flat_characterization_bias_rad_per_s": {
            "x": float(gyro_bias_rad_per_s["x"]),
            "y": float(gyro_bias_rad_per_s["y"]),
            "z": float(gyro_bias_rad_per_s["z"]),
        },
        "correction_formula": "gyro_axis_bias_corrected = gyro_axis - gyro_bias_axis",
        "initial_stationary_segment": initial_segment_report,
        "gyro_corrected_mean_rad_per_s": {
            "x": finite_mean(df["gyro_x_bias_corrected"].to_numpy(dtype=float)),
            "y": finite_mean(df["gyro_y_bias_corrected"].to_numpy(dtype=float)),
            "z": finite_mean(df["gyro_z_bias_corrected"].to_numpy(dtype=float)),
        },
        "warnings": warnings,
    }


def finite_mean(values: np.ndarray) -> float:
    finite = values[np.isfinite(values)]
    return float(np.mean(finite)) if finite.size else float("nan")


def estimate_initial_stationary_bias(
    df: pd.DataFrame,
    t: np.ndarray,
    gyro_by_axis: Dict[str, np.ndarray],
    initial_stationary_s: float,
    min_stationary_samples: int,
    user_accel_rms_warn_g: float = 0.05,
    gyro_std_warn_rad_per_s: float = 0.03,
) -> Dict[str, object]:
    mask = np.isfinite(t) & (t >= 0.0) & (t <= initial_stationary_s)
    sample_count = int(mask.sum())
    warnings = []
    if sample_count < min_stationary_samples:
        return {
            "usable": False,
            "duration_s": float(initial_stationary_s),
            "samples": sample_count,
            "gyro_bias_rad_per_s": None,
            "gyro_std_rms_rad_per_s": None,
            "user_accel_mag_rms_g": None,
            "warnings": [
                f"Initial stationary segment has only {sample_count} samples; using static-flat characterization gyro bias."
            ],
        }

    gyro_bias = {}
    gyro_std_values = []
    for axis, values in gyro_by_axis.items():
        segment = values[mask]
        finite = segment[np.isfinite(segment)]
        if finite.size < min_stationary_samples:
            warnings.append(
                f"Initial stationary segment has too few finite gyro_{axis} samples; using static-flat characterization gyro bias."
            )
            return {
                "usable": False,
                "duration_s": float(initial_stationary_s),
                "samples": sample_count,
                "gyro_bias_rad_per_s": None,
                "gyro_std_rms_rad_per_s": None,
                "user_accel_mag_rms_g": None,
                "warnings": warnings,
            }
        gyro_bias[axis] = float(np.mean(finite))
        gyro_std_values.append(float(np.std(finite, ddof=1)) if finite.size > 1 else 0.0)

    gyro_std_rms = float(np.sqrt(np.mean(np.square(gyro_std_values))))
    user_accel_mag_rms = initial_user_accel_mag_rms(df, mask)
    if gyro_std_rms > gyro_std_warn_rad_per_s:
        warnings.append(
            "Initial segment gyro variation is high; it may not be stationary. "
            "Using static-flat characterization gyro bias instead."
        )
    if user_accel_mag_rms is not None and user_accel_mag_rms > user_accel_rms_warn_g:
        warnings.append(
            "Initial segment user-accel magnitude is high; it may not be stationary. "
            "Using static-flat characterization gyro bias instead."
        )

    return {
        "usable": len(warnings) == 0,
        "duration_s": float(initial_stationary_s),
        "samples": sample_count,
        "gyro_bias_rad_per_s": gyro_bias,
        "gyro_std_rms_rad_per_s": gyro_std_rms,
        "user_accel_mag_rms_g": user_accel_mag_rms,
        "warnings": warnings,
    }


def initial_user_accel_mag_rms(df: pd.DataFrame, mask: np.ndarray) -> Optional[float]:
    ax = optional_numeric_series(df, "user_accel_x")
    ay = optional_numeric_series(df, "user_accel_y")
    az = optional_numeric_series(df, "user_accel_z")
    if ax is None or ay is None or az is None:
        return None
    mag = np.sqrt(ax[mask] ** 2 + ay[mask] ** 2 + az[mask] ** 2)
    finite = mag[np.isfinite(mag)]
    if finite.size == 0:
        return None
    return float(np.sqrt(np.mean(finite**2)))
