from typing import Tuple

import numpy as np


def unwrap_angle(theta: np.ndarray) -> np.ndarray:
    return np.unwrap(theta)


def run_pdr_with_step_lengths(
    t: np.ndarray,
    peaks: np.ndarray,
    yaw: np.ndarray,
    step_lengths: np.ndarray,
    start_x: float = 0.0,
    start_y: float = 0.0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    yaw_unwrapped = unwrap_angle(yaw)

    x, y = start_x, start_y
    xs = [x]
    ys = [y]
    step_times = [t[0]]

    if len(peaks) == 0:
        return np.array(xs), np.array(ys), np.array(step_times)

    theta0 = yaw_unwrapped[peaks[0]]

    for peak, step_length in zip(peaks, step_lengths):
        theta = yaw_unwrapped[peak] - theta0
        x += step_length * np.cos(theta)
        y += step_length * np.sin(theta)
        xs.append(x)
        ys.append(y)
        step_times.append(t[peak])

    return np.array(xs), np.array(ys), np.array(step_times)


def run_pdr_constant_step(
    t: np.ndarray,
    peaks: np.ndarray,
    yaw: np.ndarray,
    step_length: float = 0.7,
    start_x: float = 0.0,
    start_y: float = 0.0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    step_lengths = np.full(len(peaks), step_length)
    return run_pdr_with_step_lengths(
        t,
        peaks,
        yaw,
        step_lengths,
        start_x=start_x,
        start_y=start_y,
    )

def run_pdr_variable_step(
    t: np.ndarray,
    peaks: np.ndarray,
    yaw: np.ndarray,
    step_lengths: np.ndarray,
    start_x: float = 0.0,
    start_y: float = 0.0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    return run_pdr_with_step_lengths(
        t,
        peaks,
        yaw,
        step_lengths,
        start_x=start_x,
        start_y=start_y,
    )
