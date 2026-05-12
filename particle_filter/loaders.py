from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .models import ARKitTrajectory, RunPaths, TagMap
from .rfid_pipeline import RFID_MODE_RAW, load_rfid_events


def resolve_run_paths(folder: Path) -> RunPaths:
    folder = folder.expanduser().resolve()
    if not folder.is_dir():
        raise FileNotFoundError(f"Run folder not found: {folder}")

    imu_candidates = sorted(folder.glob("*imu.csv"))
    arkit_candidates = sorted(folder.glob("*arkit.csv"))
    rfid_candidates = sorted(folder.glob("reads*.csv"))

    if not imu_candidates:
        raise FileNotFoundError(f"No *imu.csv found in {folder}")
    if not arkit_candidates:
        raise FileNotFoundError(f"No *arkit.csv found in {folder}")
    if not rfid_candidates:
        raise FileNotFoundError(f"No reads*.csv found in {folder}")

    return RunPaths(
        folder=folder,
        imu_csv=imu_candidates[0],
        rfid_csv=rfid_candidates[0],
        arkit_csv=arkit_candidates[0],
    )


def load_tag_map(path: Path) -> TagMap:
    path = path.expanduser().resolve()
    df = pd.read_csv(path)
    df.columns = [column.strip() for column in df.columns]

    required = {"epc", "x_cm", "y_cm"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise KeyError(f"Missing required tag-map columns in {path}: {', '.join(missing)}")

    if "tag_id" not in df.columns:
        df["tag_id"] = df["epc"].astype(str)

    out = pd.DataFrame(
        {
            "epc": df["epc"].astype(str),
            "tag_id": df["tag_id"].astype(str),
            "x_m": pd.to_numeric(df["x_cm"], errors="coerce") / 100.0,
            "y_m": pd.to_numeric(df["y_cm"], errors="coerce") / 100.0,
        }
    )
    out = out.dropna(subset=["x_m", "y_m"]).drop_duplicates(subset=["epc"], keep="first")
    if out.empty:
        raise ValueError(f"No usable tag coordinates in {path}")
    return TagMap(tags=out.reset_index(drop=True))


def load_rfid_reads(path: Path, tag_map: TagMap, mode: str = RFID_MODE_RAW) -> pd.DataFrame:
    path = path.expanduser().resolve()
    out = load_rfid_events(path, mode=mode)
    out = out.dropna(subset=["timestamp_s", "antenna"])
    out["antenna"] = out["antenna"].astype(int)
    out["known_tag"] = out["epc"].isin(tag_map.epcs)
    out = out.sort_values("timestamp_s").reset_index(drop=True)
    return out


def _initial_motion_heading(points: np.ndarray, min_displacement_m: float) -> float:
    if points.shape[0] < 2:
        return 0.0
    origin = points[0]
    for point in points[1:]:
        delta = point - origin
        if float(np.linalg.norm(delta)) >= min_displacement_m:
            return float(np.arctan2(delta[1], delta[0]))
    delta = points[-1] - origin
    if float(np.linalg.norm(delta)) <= 1e-9:
        return 0.0
    return float(np.arctan2(delta[1], delta[0]))


def align_points_start_facing_y(
    points: np.ndarray,
    min_displacement_m: float = 0.25,
    rotation_rad: Optional[float] = None,
) -> tuple[np.ndarray, float]:
    translated = points - points[0]
    if rotation_rad is None:
        current_heading = _initial_motion_heading(points, min_displacement_m=min_displacement_m)
        rotation_rad = float(np.pi / 2.0 - current_heading)
    c = float(np.cos(rotation_rad))
    s = float(np.sin(rotation_rad))
    rotated = np.column_stack(
        [
            c * translated[:, 0] - s * translated[:, 1],
            s * translated[:, 0] + c * translated[:, 1],
        ]
    )
    return rotated, rotation_rad


def rotate_translate_points(points: np.ndarray, rotation_rad: float, translation_xy: np.ndarray) -> np.ndarray:
    c = float(np.cos(rotation_rad))
    s = float(np.sin(rotation_rad))
    rotated = np.column_stack(
        [
            c * points[:, 0] - s * points[:, 1],
            s * points[:, 0] + c * points[:, 1],
        ]
    )
    return rotated + translation_xy


def fit_rigid_transform(source_points: np.ndarray, target_points: np.ndarray) -> tuple[float, np.ndarray, float]:
    if source_points.shape != target_points.shape or source_points.ndim != 2 or source_points.shape[1] != 2:
        raise ValueError("source_points and target_points must both have shape (N, 2).")
    if source_points.shape[0] < 2:
        raise ValueError("At least two point correspondences are required.")

    source_center = np.mean(source_points, axis=0)
    target_center = np.mean(target_points, axis=0)
    source_zero = source_points - source_center
    target_zero = target_points - target_center
    h = source_zero.T @ target_zero
    u, _, vt = np.linalg.svd(h)
    r = vt.T @ u.T
    if np.linalg.det(r) < 0:
        vt[-1, :] *= -1
        r = vt.T @ u.T

    rotation_rad = float(np.arctan2(r[1, 0], r[0, 0]))
    translation_xy = target_center - source_center @ r.T
    fitted = source_points @ r.T + translation_xy
    rmse = float(np.sqrt(np.mean(np.sum((fitted - target_points) ** 2, axis=1))))
    return rotation_rad, translation_xy.astype(float), rmse


def load_arkit_trajectory(
    path: Path,
    include_non_normal: bool = False,
    rotation_rad: Optional[float] = None,
    translation_xy: Optional[np.ndarray] = None,
    align_start_facing_y: bool = True,
) -> ARKitTrajectory:
    path = path.expanduser().resolve()
    df = pd.read_csv(path)
    df.columns = [column.strip() for column in df.columns]

    required = {"unix_timestamp_s", "x_m", "z_m"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise KeyError(f"Missing required ARKit columns in {path}: {', '.join(missing)}")

    unix_t = pd.to_numeric(df["unix_timestamp_s"], errors="coerce").to_numpy(dtype=float)
    x = pd.to_numeric(df["x_m"], errors="coerce").to_numpy(dtype=float)
    z = pd.to_numeric(df["z_m"], errors="coerce").to_numpy(dtype=float)
    state = (
        df["tracking_state"].fillna("unknown").astype(str).to_numpy()
        if "tracking_state" in df.columns
        else np.full(len(df), "unknown")
    )

    valid = np.isfinite(unix_t) & np.isfinite(x) & np.isfinite(z)
    if not include_non_normal and np.any(state == "normal"):
        valid &= state == "normal"

    unix_t = unix_t[valid]
    points = np.column_stack([x[valid], -z[valid]])
    state = state[valid]

    order = np.argsort(unix_t)
    unix_t = unix_t[order]
    points = points[order]
    state = state[order]

    if unix_t.size < 2:
        raise ValueError(f"At least two valid ARKit frames are required in {path}")

    if translation_xy is not None:
        used_rotation = 0.0 if rotation_rad is None else float(rotation_rad)
        used_translation = np.asarray(translation_xy, dtype=float)
        points_map = rotate_translate_points(points, used_rotation, used_translation)
    elif align_start_facing_y:
        points_map, used_rotation = align_points_start_facing_y(points, rotation_rad=rotation_rad)
        used_translation = np.zeros(2, dtype=float)
    else:
        used_rotation = 0.0 if rotation_rad is None else float(rotation_rad)
        used_translation = np.zeros(2, dtype=float)
        points_map = rotate_translate_points(points, used_rotation, used_translation)

    return ARKitTrajectory(
        unix_t=unix_t,
        points_local=points,
        points_map=points_map,
        rotation_rad=used_rotation,
        tracking_state=state,
        translation_xy=used_translation,
    )
