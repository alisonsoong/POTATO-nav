from dataclasses import dataclass
from pathlib import Path
from typing import List

import numpy as np

from step_detection.step_detection import load_aligned_series


CORE_MOTION_YAW = "core_motion_yaw"
GYRO_INTEGRATED_YAW = "gyro_integrated_yaw"
HEADING_MODES = (CORE_MOTION_YAW, GYRO_INTEGRATED_YAW)

STEP_ACCEL_X_COLUMNS = (
    "step_accel_x",
    "user_accel_x",
    "user_accel_x_bias_corrected",
    "fused_accel_x",
    "accel_x",
)
STEP_ACCEL_Y_COLUMNS = (
    "step_accel_y",
    "user_accel_y",
    "user_accel_y_bias_corrected",
    "fused_accel_y",
    "accel_y",
)
STEP_ACCEL_Z_COLUMNS = (
    "step_accel_z",
    "user_accel_z",
    "user_accel_z_bias_corrected",
    "fused_accel_z",
    "accel_z",
)


@dataclass
class TurnSegment:
    start_index: int
    end_index: int
    start_time: float
    end_time: float
    duration: float
    delta_yaw: float
    peak_rate: float

    @property
    def direction(self) -> str:
        return "left" if self.delta_yaw > 0 else "right"

    @property
    def delta_yaw_deg(self) -> float:
        return np.degrees(self.delta_yaw)

    @property
    def peak_rate_deg_s(self) -> float:
        return np.degrees(self.peak_rate)


def unwrap_angle(theta: np.ndarray) -> np.ndarray:
    return np.unwrap(theta)


def integrate_gyro_yaw(t: np.ndarray, gyro_z: np.ndarray) -> np.ndarray:
    yaw = np.zeros_like(gyro_z)
    for i in range(1, len(gyro_z)):
        dt = t[i] - t[i - 1]
        yaw[i] = yaw[i - 1] + 0.5 * (gyro_z[i] + gyro_z[i - 1]) * dt
    return yaw


def load_heading_series(csv_path: Path, mode: str) -> tuple[np.ndarray, np.ndarray]:
    if mode == CORE_MOTION_YAW:
        t, yaw = load_aligned_series(
            csv_path,
            ("yaw_unwrapped", "yaw"),
        )
        return t, unwrap_angle(yaw)

    if mode == GYRO_INTEGRATED_YAW:
        try:
            t, heading = load_aligned_series(csv_path, ("heading_gyro_bias_corrected",))
            return t, heading
        except KeyError:
            t, gyro_z = load_aligned_series(csv_path, ("gyro_z_bias_corrected", "gyro_z"))
            return t, integrate_gyro_yaw(t, gyro_z)

    raise ValueError(f"Unknown heading mode: {mode}")


def load_step_heading_data(
    csv_path: Path,
    mode: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if mode == CORE_MOTION_YAW:
        t, user_ax, user_ay, user_az, yaw = load_aligned_series(
            csv_path,
            STEP_ACCEL_X_COLUMNS,
            STEP_ACCEL_Y_COLUMNS,
            STEP_ACCEL_Z_COLUMNS,
            ("yaw_unwrapped", "yaw"),
        )
        return t, user_ax, user_ay, user_az, unwrap_angle(yaw)

    if mode == GYRO_INTEGRATED_YAW:
        try:
            t, user_ax, user_ay, user_az, heading = load_aligned_series(
                csv_path,
                STEP_ACCEL_X_COLUMNS,
                STEP_ACCEL_Y_COLUMNS,
                STEP_ACCEL_Z_COLUMNS,
                ("heading_gyro_bias_corrected",),
            )
            return t, user_ax, user_ay, user_az, heading
        except KeyError:
            t, user_ax, user_ay, user_az, gyro_z = load_aligned_series(
                csv_path,
                STEP_ACCEL_X_COLUMNS,
                STEP_ACCEL_Y_COLUMNS,
                STEP_ACCEL_Z_COLUMNS,
                ("gyro_z_bias_corrected", "gyro_z"),
            )
            return t, user_ax, user_ay, user_az, integrate_gyro_yaw(t, gyro_z)

    raise ValueError(f"Unknown heading mode: {mode}")


def heading_rate(t: np.ndarray, heading: np.ndarray) -> np.ndarray:
    if len(t) < 2:
        raise ValueError("At least two heading samples are required to compute heading rate.")
    return np.gradient(heading, t)


def detect_turns(
    t: np.ndarray,
    heading: np.ndarray,
    rate_threshold_rad_s: float = np.deg2rad(20.0),
    min_angle_rad: float = np.deg2rad(30.0),
    min_duration_s: float = 0.2,
    merge_gap_s: float = 0.15,
) -> List[TurnSegment]:
    rate = heading_rate(t, heading)
    active = np.abs(rate) >= rate_threshold_rad_s

    turns: List[TurnSegment] = []
    start_index = None

    for index, is_active in enumerate(active):
        if is_active and start_index is None:
            start_index = index
        elif not is_active and start_index is not None:
            turns.append(_build_turn_segment(t, heading, rate, start_index, index - 1))
            start_index = None

    if start_index is not None:
        turns.append(_build_turn_segment(t, heading, rate, start_index, len(t) - 1))

    merged = _merge_turn_segments(t, heading, rate, turns, merge_gap_s)
    filtered = []
    for turn in merged:
        if turn.duration < min_duration_s:
            continue
        if abs(turn.delta_yaw) < min_angle_rad:
            continue
        filtered.append(turn)
    return filtered


def _build_turn_segment(
    t: np.ndarray,
    heading: np.ndarray,
    rate: np.ndarray,
    start_index: int,
    end_index: int,
) -> TurnSegment:
    peak_rate = np.max(np.abs(rate[start_index : end_index + 1]))
    start_time = t[start_index]
    end_time = t[end_index]
    return TurnSegment(
        start_index=start_index,
        end_index=end_index,
        start_time=start_time,
        end_time=end_time,
        duration=end_time - start_time,
        delta_yaw=heading[end_index] - heading[start_index],
        peak_rate=peak_rate,
    )


def _merge_turn_segments(
    t: np.ndarray,
    heading: np.ndarray,
    rate: np.ndarray,
    turns: List[TurnSegment],
    merge_gap_s: float,
) -> List[TurnSegment]:
    if not turns:
        return []

    merged = [turns[0]]
    for turn in turns[1:]:
        last = merged[-1]
        gap = turn.start_time - last.end_time
        same_direction = np.sign(turn.delta_yaw) == np.sign(last.delta_yaw)
        if gap <= merge_gap_s and same_direction:
            merged[-1] = _build_turn_segment(t, heading, rate, last.start_index, turn.end_index)
        else:
            merged.append(turn)
    return merged
