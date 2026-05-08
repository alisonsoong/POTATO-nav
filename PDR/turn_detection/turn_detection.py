from typing import Iterable

import numpy as np

from turn_detection.heading import TurnSegment, detect_turns
from config import TurnDetectionConfig


def detect_turns_with_config(
    t: np.ndarray,
    heading: np.ndarray,
    config: TurnDetectionConfig,
) -> list[TurnSegment]:
    return detect_turns(
        t,
        heading,
        rate_threshold_rad_s=np.deg2rad(config.rate_threshold_deg_s),
        min_angle_rad=np.deg2rad(config.min_angle_deg),
        min_duration_s=config.min_duration_s,
        merge_gap_s=config.merge_gap_s,
    )


def summarize_turns(turns: Iterable[TurnSegment]) -> list[str]:
    turns = list(turns)
    summary = [f"Detected turns: {len(turns)}"]
    for idx, turn in enumerate(turns, start=1):
        summary.append(
            f"  Turn {idx}: {turn.direction}, "
            f"{turn.start_time:.2f}s -> {turn.end_time:.2f}s, "
            f"delta={turn.delta_yaw_deg:.1f} deg, "
            f"peak_rate={turn.peak_rate_deg_s:.1f} deg/s"
        )
    return summary


def step_turn_mask(t: np.ndarray, peaks: np.ndarray, turns: Iterable[TurnSegment]) -> np.ndarray:
    turns = list(turns)
    mask = np.zeros(len(peaks), dtype=bool)
    for idx, peak in enumerate(peaks):
        step_time = t[peak]
        mask[idx] = any(turn.start_time <= step_time <= turn.end_time for turn in turns)
    return mask
