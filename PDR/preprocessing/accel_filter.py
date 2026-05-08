from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd
from scipy.signal import butter, filtfilt


def bandpass(
    x: np.ndarray,
    fs: float,
    low_hz: float = 0.5,
    high_hz: float = 3.0,
    order: int = 2,
) -> np.ndarray:
    if fs <= 0:
        raise ValueError("Sample rate must be positive.")
    nyquist = fs / 2.0
    if high_hz >= nyquist:
        high_hz = nyquist * 0.95
    if low_hz <= 0 or low_hz >= high_hz:
        raise ValueError("Invalid band-pass cutoff frequencies.")

    b, a = butter(order, [low_hz, high_hz], btype="bandpass", fs=fs)
    padlen = 3 * max(len(a), len(b))
    if x.size <= padlen:
        # Too few samples for filtfilt padding; centered signal is safer than failing.
        return x - np.nanmean(x)
    return filtfilt(b, a, x)


def filter_step_acceleration(
    df: pd.DataFrame,
    fs: float,
    low_hz: float = 0.5,
    high_hz: float = 3.0,
    order: int = 2,
) -> Dict[str, float | str]:
    if "step_accel_mag" not in df.columns:
        raise KeyError("step_accel_mag must exist before filtering.")

    accel_mag = pd.to_numeric(df["step_accel_mag"], errors="coerce").to_numpy(dtype=float)
    if np.any(~np.isfinite(accel_mag)):
        finite_mean = np.nanmean(accel_mag)
        accel_mag = np.where(np.isfinite(accel_mag), accel_mag, finite_mean)

    filtered = bandpass(accel_mag, fs, low_hz=low_hz, high_hz=high_hz, order=order)
    df["step_accel_mag_filtered"] = filtered

    return {
        "filter": "butterworth_bandpass_filtfilt",
        "low_hz": float(low_hz),
        "high_hz": float(high_hz),
        "order": int(order),
    }
