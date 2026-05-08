from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

try:
    from .csv_io import optional_numeric_series
except ImportError:  # pragma: no cover
    from csv_io import optional_numeric_series


def magnetometer_heading_policy(
    df: pd.DataFrame,
    allow_magnetometer_heading: bool = False,
) -> Dict[str, object]:
    accuracy = optional_numeric_series(df, "mag_accuracy", "magnetic_field_accuracy")
    if accuracy is None:
        return {
            "use_magnetometer_for_heading": False,
            "magnetometer_accuracy_mean": None,
            "magnetometer_reason": (
                "Magnetometer accuracy is missing; do not use magnetometer heading indoors."
            ),
        }

    finite = accuracy[np.isfinite(accuracy)]
    mean_accuracy = float(np.mean(finite)) if finite.size else None
    if allow_magnetometer_heading:
        reason = (
            "Magnetometer heading was explicitly allowed. Validate this against yaw tests before trusting it indoors."
        )
    else:
        reason = (
            "Magnetometer heading disabled for indoor PDR; use it only if accuracy is consistently high "
            "and known-yaw tests validate magnetic heading."
        )

    return {
        "use_magnetometer_for_heading": bool(allow_magnetometer_heading),
        "magnetometer_accuracy_mean": mean_accuracy,
        "magnetometer_reason": reason,
    }
