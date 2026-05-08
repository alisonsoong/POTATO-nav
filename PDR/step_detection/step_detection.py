from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd
from scipy.signal import butter, filtfilt, find_peaks


def first_present(df: pd.DataFrame, *candidates: str) -> str:
    for name in candidates:
        if name in df.columns:
            return name
    raise KeyError(f"Missing required column. Tried: {', '.join(candidates)}")


def optional_series(df: pd.DataFrame, *candidates: str) -> Optional[np.ndarray]:
    for name in candidates:
        if name in df.columns:
            return pd.to_numeric(df[name], errors="coerce").to_numpy()
    return None


def load_motion_dataframe(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, comment="#")
    df.columns = [column.strip() for column in df.columns]
    return df


def required_series(df: pd.DataFrame, *candidates: str) -> np.ndarray:
    series = optional_series(df, *candidates)
    if series is None:
        raise KeyError(f"Could not find any of these columns in the CSV: {', '.join(candidates)}")
    return series


def load_aligned_series(csv_path: Path, *column_groups: Tuple[str, ...]) -> Tuple[np.ndarray, ...]:
    df = load_motion_dataframe(csv_path)

    time_column = first_present(df, "timestamp_relative_s", "timestamp_s", "timestamp")
    t = pd.to_numeric(df[time_column], errors="coerce").to_numpy()
    series_list = [required_series(df, *group) for group in column_groups]

    valid = np.isfinite(t)
    for series in series_list:
        valid &= np.isfinite(series)

    t = t[valid]
    aligned = [series[valid] for series in series_list]

    if t.size < 3:
        raise ValueError("Not enough valid samples after CSV alignment.")

    t = t - t[0]
    return (t, *aligned)


def load_motion_csv(csv_path: Path) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    return load_aligned_series(
        csv_path,
        (
            "step_accel_x",
            "user_accel_x",
            "user_accel_x_bias_corrected",
            "fused_accel_x",
            "accel_x",
        ),
        (
            "step_accel_y",
            "user_accel_y",
            "user_accel_y_bias_corrected",
            "fused_accel_y",
            "accel_y",
        ),
        (
            "step_accel_z",
            "user_accel_z",
            "user_accel_z_bias_corrected",
            "fused_accel_z",
            "accel_z",
        ),
    )


def bandpass(x: np.ndarray, fs: float, low: float = 0.5, high: float = 3.0, order: int = 2) -> np.ndarray:
    b, a = butter(order, [low, high], btype="bandpass", fs=fs)
    return filtfilt(b, a, x)


def detect_steps(
    t: np.ndarray,
    user_ax: np.ndarray,
    user_ay: np.ndarray,
    user_az: np.ndarray,
    low: float = 0.5,
    high: float = 3.0,
    min_step_gap_s: float = 0.35,
    prominence: float = 0.03,
) -> Tuple[np.ndarray, np.ndarray, float]:
    dt = np.median(np.diff(t))
    if not np.isfinite(dt) or dt <= 0:
        raise ValueError("Could not infer a valid sample interval from timestamps.")

    fs = 1.0 / dt
    amag = np.sqrt(user_ax**2 + user_ay**2 + user_az**2)
    amag_f = bandpass(amag, fs, low=low, high=high)

    peaks, _ = find_peaks(
        amag_f,
        distance=max(1, int(min_step_gap_s * fs)),
        prominence=prominence,
    )

    return peaks, amag_f, fs


def detect_steps_from_csv(
    csv_path: Path,
    low: float = 0.5,
    high: float = 3.0,
    min_step_gap_s: float = 0.35,
    prominence: float = 0.03,
) -> Tuple[np.ndarray, np.ndarray, float, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    df = load_motion_dataframe(csv_path)
    time_column = first_present(df, "timestamp_relative_s", "timestamp_s", "timestamp")
    t = pd.to_numeric(df[time_column], errors="coerce").to_numpy(dtype=float)

    prefiltered = optional_series(df, "step_accel_mag_filtered")
    if prefiltered is not None:
        valid = np.isfinite(t) & np.isfinite(prefiltered)
        t = t[valid]
        t = t - t[0]
        amag_f = prefiltered[valid]
        dt = np.median(np.diff(t))
        if not np.isfinite(dt) or dt <= 0:
            raise ValueError("Could not infer a valid sample interval from timestamps.")
        fs = 1.0 / dt
        peaks, _ = find_peaks(
            amag_f,
            distance=max(1, int(min_step_gap_s * fs)),
            prominence=prominence,
        )
        empty = np.full_like(t, np.nan, dtype=float)
        return peaks, amag_f, fs, t, empty, empty, empty

    t, user_ax, user_ay, user_az = load_motion_csv(csv_path)
    peaks, amag_f, fs = detect_steps(
        t,
        user_ax,
        user_ay,
        user_az,
        low=low,
        high=high,
        min_step_gap_s=min_step_gap_s,
        prominence=prominence,
    )
    return peaks, amag_f, fs, t, user_ax, user_ay, user_az
