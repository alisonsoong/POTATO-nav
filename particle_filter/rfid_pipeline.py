from __future__ import annotations

import sys
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
RFID_READ_DIR = REPO_ROOT / "ThingMagic" / "Read"
if str(RFID_READ_DIR) not in sys.path:
    sys.path.insert(0, str(RFID_READ_DIR))

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(Path(tempfile.gettempdir()) / "fontconfig-cache"))

import rfid_processing  # noqa: E402


RFID_MODE_RAW = "raw"
RFID_MODE_SMOOTHED = "smoothed"
RFID_MODES = (RFID_MODE_RAW, RFID_MODE_SMOOTHED)


def _datetime_to_unix_seconds(values: pd.Series) -> np.ndarray:
    dt = pd.to_datetime(values, errors="coerce")
    out = dt.astype("int64").to_numpy(dtype=float) / 1e9
    out[dt.isna().to_numpy()] = np.nan
    return out


def smooth_rfid_file(
    csv_path: Path,
    phase_unit: str = "degrees",
    wrap_period: float = 180.0,
    disable_hampel: bool = False,
    hampel_window: str = "750ms",
    hampel_sigmas: float = 3.5,
    smooth_method: str = "gaussian",
    smooth_window: str = "1500ms",
    smooth_sigma: str | None = "500ms",
    min_smooth_points: int = 1,
) -> pd.DataFrame:
    df = rfid_processing.load_rfid_csv(
        csv_path=csv_path,
        tag_col="EPC",
        antenna_col="antenna",
        time_col="timestamp",
        phase_col="phase",
        timestamp_unit="auto",
        timestamp_format=None,
        dayfirst=False,
    )
    groups = []
    for _, group in df.groupby(["EPC", "antenna"], sort=False):
        groups.append(
            rfid_processing.process_group(
                group=group,
                time_col="timestamp",
                phase_col="phase",
                phase_unit=phase_unit,
                wrap_period=wrap_period,
                disable_hampel=disable_hampel,
                hampel_window=hampel_window,
                hampel_sigmas=hampel_sigmas,
                smooth_method=smooth_method,
                smooth_window=smooth_window,
                smooth_sigma=smooth_sigma,
                min_smooth_points=min_smooth_points,
            )
        )
    if not groups:
        return pd.DataFrame()
    return pd.concat(groups, ignore_index=True).sort_values("timestamp").reset_index(drop=True)


def standardize_rfid_dataframe(df: pd.DataFrame, smoothed: bool = False) -> pd.DataFrame:
    df = df.copy()
    df.columns = [column.strip() for column in df.columns]

    if "EPC" in df.columns:
        epc = df["EPC"].astype(str)
    elif "epc" in df.columns:
        epc = df["epc"].astype(str)
    else:
        raise KeyError("Missing RFID EPC column.")

    if "timestamp_s" in df.columns:
        timestamp_s = pd.to_numeric(df["timestamp_s"], errors="coerce").to_numpy(dtype=float)
    elif "timestamp_raw" in df.columns:
        timestamp_s = pd.to_numeric(df["timestamp_raw"], errors="coerce").to_numpy(dtype=float) / 1000.0
    elif "timestamp" in df.columns and np.issubdtype(df["timestamp"].dtype, np.datetime64):
        timestamp_s = _datetime_to_unix_seconds(df["timestamp"])
    elif "timestamp" in df.columns and not smoothed:
        timestamp_s = pd.to_numeric(df["timestamp"], errors="coerce").to_numpy(dtype=float) / 1000.0
    elif "timestamp" in df.columns:
        raw_timestamp = pd.to_numeric(df["timestamp"], errors="coerce")
        if raw_timestamp.notna().mean() >= 0.9 and raw_timestamp.dropna().median() > 1e8:
            timestamp_s = raw_timestamp.to_numpy(dtype=float) / (1000.0 if raw_timestamp.dropna().median() > 1e11 else 1.0)
        else:
            timestamp_s = _datetime_to_unix_seconds(df["timestamp"])
    else:
        raise KeyError("Missing RFID timestamp column.")

    if "phase_smooth" in df.columns and smoothed:
        phase = pd.to_numeric(df["phase_smooth"], errors="coerce")
    elif "phase" in df.columns:
        phase = pd.to_numeric(df["phase"], errors="coerce")
    else:
        phase = pd.Series(np.nan, index=df.index)

    out = pd.DataFrame(
        {
            "timestamp_s": timestamp_s,
            "epc": epc,
            "antenna": pd.to_numeric(df["antenna"], errors="coerce") if "antenna" in df.columns else np.nan,
            "frequency": pd.to_numeric(df["frequency"], errors="coerce") if "frequency" in df.columns else np.nan,
            "rssi": pd.to_numeric(df["rssi"], errors="coerce") if "rssi" in df.columns else np.nan,
            "phase": phase,
            "rfid_source": "smoothed" if smoothed else "raw",
        }
    )
    if "smooth_read_count" in df.columns:
        out["smooth_read_count"] = pd.to_numeric(df["smooth_read_count"], errors="coerce")
    return out


def load_rfid_events(csv_path: Path, mode: str = RFID_MODE_RAW) -> pd.DataFrame:
    if mode not in RFID_MODES:
        raise ValueError(f"Unknown RFID mode {mode!r}. Expected one of: {', '.join(RFID_MODES)}")
    if mode == RFID_MODE_SMOOTHED:
        return standardize_rfid_dataframe(smooth_rfid_file(csv_path), smoothed=True)
    return standardize_rfid_dataframe(pd.read_csv(csv_path), smoothed=False)
