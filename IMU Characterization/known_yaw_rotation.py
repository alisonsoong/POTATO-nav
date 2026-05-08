from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Sequence

from imu_helpers import (
    KNOWN_ANGLE_ROTATION,
    TestSpec,
    analyze_known_yaw_rotation_trials,
)


@dataclass(frozen=True)
class YawRotationCsv:
    csv_file: Path
    true_rotation_deg: float
    trial_id: str = ""
    rotation_axis: str = "z"


def analyze_known_yaw_rotation_csvs(
    trials: Sequence[YawRotationCsv],
    gyro_bias_rad_per_s: Optional[Dict[str, float]] = None,
) -> Dict:
    specs = [
        TestSpec(
            csv_file=trial.csv_file,
            test_type=KNOWN_ANGLE_ROTATION,
            trial_id=trial.trial_id or trial.csv_file.stem,
            rotation_axis=trial.rotation_axis,
            expected_angle_deg=trial.true_rotation_deg,
        )
        for trial in trials
    ]
    return analyze_known_yaw_rotation_trials(specs, gyro_bias_rad_per_s)
