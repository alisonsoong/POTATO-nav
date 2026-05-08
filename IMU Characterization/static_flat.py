from __future__ import annotations

from pathlib import Path
from typing import Dict, Sequence

from imu_helpers import analyze_long_static_rest, load_imu_csv, merge_imu_runs


def analyze_static_flat_csvs(
    csv_files: Sequence[Path],
    label: str = "static_flat",
) -> Dict:
    runs = [load_imu_csv(path) for path in csv_files]
    return analyze_long_static_rest(merge_imu_runs(runs), label=label)


def static_flat_gyro_bias(result: Dict) -> Dict[str, float]:
    return result["static_flat"]["gyro_bias_rad_per_s"]
