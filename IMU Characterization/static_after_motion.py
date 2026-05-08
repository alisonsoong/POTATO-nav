from __future__ import annotations

from pathlib import Path
from typing import Dict, Sequence

from imu_helpers import BIAS_SETTLING, TestSpec, analyze_static_after_motion_trials


def analyze_static_after_motion_csvs(
    csv_files: Sequence[Path],
    group: str = "static_after_motion",
) -> Dict:
    specs = [
        TestSpec(
            csv_file=csv_file,
            test_type=BIAS_SETTLING,
            trial_id=csv_file.stem,
            group=group,
        )
        for csv_file in csv_files
    ]
    return analyze_static_after_motion_trials(specs)
