from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd

try:
    from .csv_io import optional_numeric_series
except ImportError:  # pragma: no cover
    from csv_io import optional_numeric_series


def unwrap_and_check_yaw(df: pd.DataFrame, t: np.ndarray) -> Dict[str, object]:
    yaw = optional_numeric_series(df, "yaw")
    if yaw is None:
        return {
            "yaw_available": False,
            "yaw_wrap_detected": None,
            "yaw_delta_deg": None,
            "yaw_drift_deg_per_min": None,
            "warnings": ["Core Motion yaw column is missing."],
        }

    finite = np.isfinite(yaw)
    unwrapped = np.full_like(yaw, np.nan, dtype=float)
    unwrapped[finite] = np.unwrap(yaw[finite])
    df["yaw_unwrapped"] = unwrapped

    raw_diff = np.diff(yaw[finite])
    wrap_detected = bool(np.any(np.abs(raw_diff) > np.pi)) if raw_diff.size else False
    yaw_delta = None
    yaw_drift = None
    if finite.sum() >= 2:
        valid_t = t[finite]
        duration_min = (valid_t[-1] - valid_t[0]) / 60.0
        yaw_delta = float(np.degrees(unwrapped[finite][-1] - unwrapped[finite][0]))
        yaw_drift = yaw_delta / duration_min if duration_min > 0 else None

    warnings = []
    if wrap_detected:
        warnings.append("Core Motion yaw wrap detected; yaw_unwrapped was added.")
    if finite.sum() < yaw.size:
        warnings.append("Yaw contains non-finite samples.")

    return {
        "yaw_available": True,
        "yaw_wrap_detected": wrap_detected,
        "yaw_delta_deg": yaw_delta,
        "yaw_drift_deg_per_min": yaw_drift,
        "warnings": warnings,
    }
