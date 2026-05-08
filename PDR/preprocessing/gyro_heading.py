from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd

try:
    from .constants import HEADING_AUTO, HEADING_CORE_MOTION_YAW, HEADING_GYRO
except ImportError:  # pragma: no cover
    from constants import HEADING_AUTO, HEADING_CORE_MOTION_YAW, HEADING_GYRO


def integrate_gyro_heading(
    t: np.ndarray,
    gyro_z_corr: np.ndarray,
    scale_factor: Optional[float] = None,
) -> np.ndarray:
    scale = 1.0 if scale_factor is None else float(scale_factor)
    heading = np.zeros_like(t, dtype=float)
    for index in range(1, t.size):
        dt = t[index] - t[index - 1]
        heading[index] = heading[index - 1] + scale * gyro_z_corr[index] * dt
    return heading


def add_heading_columns(
    df: pd.DataFrame,
    t: np.ndarray,
    heading_source: str = HEADING_GYRO,
    apply_gyro_scale_correction: bool = False,
    gyro_z_scale_factor: Optional[float] = None,
) -> Dict[str, object]:
    if "gyro_z_bias_corrected" not in df.columns:
        raise KeyError("gyro_z_bias_corrected must exist before heading integration.")

    gyro_z_corr = pd.to_numeric(df["gyro_z_bias_corrected"], errors="coerce").to_numpy(dtype=float)
    gyro_z_corr = np.where(np.isfinite(gyro_z_corr), gyro_z_corr, 0.0)
    scale = gyro_z_scale_factor if apply_gyro_scale_correction else None
    heading_gyro = integrate_gyro_heading(t, gyro_z_corr, scale_factor=scale)
    df["heading_gyro_bias_corrected"] = heading_gyro

    warnings = []
    selected_source = heading_source
    if heading_source == HEADING_AUTO:
        selected_source = HEADING_GYRO

    if selected_source == HEADING_CORE_MOTION_YAW:
        if "yaw_unwrapped" not in df.columns:
            warnings.append("Core Motion yaw requested but yaw_unwrapped is unavailable; using gyro heading.")
            selected_source = HEADING_GYRO
        else:
            df["heading_selected"] = pd.to_numeric(df["yaw_unwrapped"], errors="coerce")
    elif selected_source == HEADING_GYRO:
        df["heading_selected"] = heading_gyro
    else:
        raise ValueError(f"Unknown heading source: {heading_source}")

    return {
        "preferred_heading_source": selected_source,
        "heading_source_reason": (
            "Bias-corrected gyro integration selected for controlled short PDR turns."
            if selected_source == HEADING_GYRO
            else "Core Motion yaw explicitly selected."
        ),
        "apply_gyro_scale_correction": bool(apply_gyro_scale_correction),
        "gyro_z_scale_factor": float(gyro_z_scale_factor) if apply_gyro_scale_correction and gyro_z_scale_factor is not None else None,
        "warnings": warnings,
    }
