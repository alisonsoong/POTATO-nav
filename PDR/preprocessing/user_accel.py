from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd

try:
    from .csv_io import first_present, numeric_series, optional_numeric_series
except ImportError:  # pragma: no cover
    from csv_io import first_present, numeric_series, optional_numeric_series


def prepare_step_acceleration(
    df: pd.DataFrame,
    user_accel_bias_g: Dict[str, float],
    subtract_user_accel_bias: bool = False,
    prefer_user_accel: bool = True,
) -> Dict[str, object]:
    warnings = []
    has_user_accel = all(
        column in df.columns
        for column in ("user_accel_x", "user_accel_y", "user_accel_z")
    )

    if prefer_user_accel and has_user_accel:
        source = "user_accel"
        ax = numeric_series(df, "user_accel_x")
        ay = numeric_series(df, "user_accel_y")
        az = numeric_series(df, "user_accel_z")
        step_accel_note = "raw user_accel_* used for step detection"
        if subtract_user_accel_bias:
            ax = ax - user_accel_bias_g["x"]
            ay = ay - user_accel_bias_g["y"]
            az = az - user_accel_bias_g["z"]
            step_accel_note = "user_accel_* bias was subtracted before step magnitude"
    else:
        source = "fused_accel"
        step_accel_note = "fused accel used because user_accel_* was unavailable or disabled"
        warnings.append(
            "user_accel_x/y/z are missing or disabled; using fused accel for step detection. "
            "Do not interpret fused accel +/-1 g as accelerometer bias."
        )
        ax = numeric_series(df, "accel_x", "fused_accel_x")
        ay = numeric_series(df, "accel_y", "fused_accel_y")
        az = numeric_series(df, "accel_z", "fused_accel_z")

    df["step_accel_x"] = ax
    df["step_accel_y"] = ay
    df["step_accel_z"] = az
    df["step_accel_mag"] = np.sqrt(ax**2 + ay**2 + az**2)

    if has_user_accel:
        raw_x = optional_numeric_series(df, "user_accel_x")
        raw_y = optional_numeric_series(df, "user_accel_y")
        raw_z = optional_numeric_series(df, "user_accel_z")
        df["user_accel_x_bias_corrected"] = raw_x - user_accel_bias_g["x"]
        df["user_accel_y_bias_corrected"] = raw_y - user_accel_bias_g["y"]
        df["user_accel_z_bias_corrected"] = raw_z - user_accel_bias_g["z"]

    return {
        "step_accel_source": source,
        "step_accel_note": step_accel_note,
        "subtract_user_accel_bias": bool(subtract_user_accel_bias and source == "user_accel"),
        "user_accel_bias_subtracted_g": (
            {axis: float(value) for axis, value in user_accel_bias_g.items()}
            if source == "user_accel" and subtract_user_accel_bias
            else None
        ),
        "use_user_accel_for_step_detection": source == "user_accel",
        "use_fused_accel_for_step_detection": source == "fused_accel",
        "warnings": warnings,
    }
