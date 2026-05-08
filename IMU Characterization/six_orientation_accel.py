from __future__ import annotations

from pathlib import Path
from typing import Dict, Mapping, Sequence

from imu_helpers import STATIC_6_ORIENTATION, TestSpec, analyze_six_orientation_static


def analyze_six_orientation_csvs(
    pose_csvs: Mapping[str, Sequence[Path]],
    group: str = "six_orientation",
) -> Dict:
    specs = []
    for pose, csv_files in pose_csvs.items():
        for index, csv_file in enumerate(csv_files, start=1):
            specs.append(
                TestSpec(
                    csv_file=csv_file,
                    test_type=STATIC_6_ORIENTATION,
                    trial_id=f"{pose}_{index}",
                    group=group,
                    orientation=pose,
                )
            )
    return analyze_six_orientation_static(specs)
