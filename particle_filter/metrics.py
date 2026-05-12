from __future__ import annotations

from typing import Dict

import numpy as np

from .models import ARKitTrajectory


def path_length(points: np.ndarray) -> float:
    if points.shape[0] < 2:
        return 0.0
    return float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())


def interpolate_points(source_t: np.ndarray, source_points: np.ndarray, target_t: np.ndarray) -> np.ndarray:
    if source_t.size < 2:
        raise ValueError("At least two source samples are required.")
    x = np.interp(target_t, source_t, source_points[:, 0])
    y = np.interp(target_t, source_t, source_points[:, 1])
    return np.column_stack([x, y])


def trajectory_metrics(
    times_unix: np.ndarray,
    points: np.ndarray,
    arkit: ARKitTrajectory,
) -> Dict[str, float]:
    if times_unix.size != points.shape[0]:
        raise ValueError("Trajectory times and points must have matching lengths.")
    mask = (times_unix >= arkit.unix_t[0]) & (times_unix <= arkit.unix_t[-1])
    if int(mask.sum()) < 2:
        raise ValueError("Not enough trajectory points overlap ARKit.")

    paired_times = times_unix[mask]
    paired_points = points[mask]
    arkit_points = interpolate_points(arkit.unix_t, arkit.points_map, paired_times)
    errors = np.linalg.norm(paired_points - arkit_points, axis=1)
    arkit_distance = path_length(arkit_points)
    estimate_distance = path_length(paired_points)

    return {
        "paired_points": float(errors.size),
        "duration_s": float(paired_times[-1] - paired_times[0]),
        "mean_error_m": float(np.mean(errors)),
        "median_error_m": float(np.median(errors)),
        "rmse_m": float(np.sqrt(np.mean(errors**2))),
        "p95_error_m": float(np.percentile(errors, 95)),
        "max_error_m": float(np.max(errors)),
        "endpoint_error_m": float(errors[-1]),
        "closed_loop_return_error_m": float(np.linalg.norm(points[-1])),
        "arkit_path_length_m": arkit_distance,
        "estimate_path_length_m": estimate_distance,
        "path_length_ratio_estimate_over_arkit": float(estimate_distance / arkit_distance) if arkit_distance > 0 else np.nan,
    }
