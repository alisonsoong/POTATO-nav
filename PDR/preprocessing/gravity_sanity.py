from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

try:
    from .csv_io import optional_numeric_series
except ImportError:  # pragma: no cover
    from csv_io import optional_numeric_series


def add_gravity_tilt_check(
    df: pd.DataFrame,
    flat_tilt_warn_deg: float = 15.0,
) -> Dict[str, object]:
    gx = optional_numeric_series(df, "gravity_x")
    gy = optional_numeric_series(df, "gravity_y")
    gz = optional_numeric_series(df, "gravity_z")
    if gx is None or gy is None or gz is None:
        return {
            "gravity_available": False,
            "tilt_mean_deg": None,
            "tilt_std_deg": None,
            "tilt_max_deg": None,
            "warnings": ["gravity_x/y/z are missing; phone flatness was not checked."],
        }

    tilt_deg = np.degrees(np.arctan2(np.sqrt(gx**2 + gy**2), np.abs(gz)))
    df["tilt_from_flat_deg"] = tilt_deg

    finite = tilt_deg[np.isfinite(tilt_deg)]
    warnings = []
    if finite.size and float(np.mean(finite)) > flat_tilt_warn_deg:
        warnings.append(
            f"Mean tilt from flat exceeds {flat_tilt_warn_deg:.1f} deg; gyro_z may not be pure yaw."
        )

    return {
        "gravity_available": True,
        "tilt_mean_deg": float(np.mean(finite)) if finite.size else None,
        "tilt_std_deg": float(np.std(finite, ddof=1)) if finite.size > 1 else 0.0,
        "tilt_max_deg": float(np.max(finite)) if finite.size else None,
        "warnings": warnings,
    }
