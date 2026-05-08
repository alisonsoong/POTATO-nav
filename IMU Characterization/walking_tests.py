from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Sequence

from imu_helpers import (
    analyze_known_path_with_turns,
    analyze_out_and_back_hallway,
    analyze_straight_line_walk,
    load_imu_csv,
)


@dataclass(frozen=True)
class StraightWalkCsv:
    csv_file: Path
    expected_distance_m: Optional[float] = None
    trial_id: str = ""


@dataclass(frozen=True)
class KnownPathCsv:
    csv_file: Path
    expected_path_length_m: Optional[float] = None
    expected_end_x_m: Optional[float] = None
    expected_end_y_m: Optional[float] = None
    expected_turn_count: Optional[int] = None
    closed_loop: bool = False
    trial_id: str = ""


def analyze_straight_walk_csvs(trials: Sequence[StraightWalkCsv]) -> Dict:
    results = []
    for trial in trials:
        result = analyze_straight_line_walk(
            load_imu_csv(trial.csv_file),
            expected_distance_m=trial.expected_distance_m,
            label=trial.trial_id or trial.csv_file.stem,
        )
        results.append(result)
    return {"test_type": "straight_line_walk", "trials": results}


def analyze_known_path_csvs(trials: Sequence[KnownPathCsv]) -> Dict:
    results = []
    for trial in trials:
        expected_end_xy = None
        if trial.expected_end_x_m is not None and trial.expected_end_y_m is not None:
            expected_end_xy = (trial.expected_end_x_m, trial.expected_end_y_m)
        result = analyze_known_path_with_turns(
            load_imu_csv(trial.csv_file),
            expected_path_length_m=trial.expected_path_length_m,
            expected_end_xy=expected_end_xy,
            expected_turn_count=trial.expected_turn_count,
            closed_loop=trial.closed_loop,
            label=trial.trial_id or trial.csv_file.stem,
        )
        results.append(result)
    return {"test_type": "known_path_turns", "trials": results}


def analyze_out_and_back_csvs(trials: Sequence[StraightWalkCsv]) -> Dict:
    results = []
    for trial in trials:
        result = analyze_out_and_back_hallway(
            load_imu_csv(trial.csv_file),
            expected_one_way_distance_m=trial.expected_distance_m,
            label=trial.trial_id or trial.csv_file.stem,
        )
        results.append(result)
    return {"test_type": "out_and_back", "trials": results}
