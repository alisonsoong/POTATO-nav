from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Optional

import numpy as np
import pandas as pd


def read_comment_metadata(csv_path: Path) -> Dict[str, str]:
    metadata: Dict[str, str] = {}
    with csv_path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.startswith("#"):
                break
            key, _, value = line[1:].strip().partition(",")
            if key:
                metadata[key.strip()] = value.strip()
    return metadata


def load_imu_dataframe(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, comment="#")
    df.columns = [column.strip() for column in df.columns]
    if df.empty:
        raise ValueError(f"CSV has no samples: {csv_path}")
    return df


def first_present(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    for column in candidates:
        if column in df.columns:
            return column
    return None


def required_column(df: pd.DataFrame, *candidates: str) -> str:
    column = first_present(df, candidates)
    if column is None:
        raise KeyError(f"Missing required column. Tried: {', '.join(candidates)}")
    return column


def numeric_series(df: pd.DataFrame, *candidates: str) -> np.ndarray:
    column = required_column(df, *candidates)
    return pd.to_numeric(df[column], errors="coerce").to_numpy(dtype=float)


def optional_numeric_series(df: pd.DataFrame, *candidates: str) -> Optional[np.ndarray]:
    column = first_present(df, candidates)
    if column is None:
        return None
    return pd.to_numeric(df[column], errors="coerce").to_numpy(dtype=float)


def relative_time(df: pd.DataFrame) -> np.ndarray:
    t = numeric_series(df, "timestamp_s", "timestamp")
    valid = np.isfinite(t)
    if valid.sum() < 2:
        raise ValueError("At least two finite timestamps are required.")
    t0 = t[valid][0]
    return t - t0


def infer_sample_rate_hz(t: np.ndarray) -> float:
    dt = np.diff(t)
    valid = dt[np.isfinite(dt) & (dt > 0)]
    if valid.size == 0:
        raise ValueError("Could not infer a positive sample interval.")
    return float(1.0 / np.median(valid))


def sampling_report(t: np.ndarray) -> Dict[str, float | bool]:
    dt = np.diff(t)
    valid = dt[np.isfinite(dt) & (dt > 0)]
    if valid.size == 0:
        return {
            "sample_rate_hz": float("nan"),
            "median_dt_s": float("nan"),
            "dt_std_s": float("nan"),
            "irregular_sampling": True,
        }
    median_dt = float(np.median(valid))
    dt_std = float(np.std(valid, ddof=1)) if valid.size > 1 else 0.0
    return {
        "sample_rate_hz": float(1.0 / median_dt),
        "median_dt_s": median_dt,
        "dt_std_s": dt_std,
        "irregular_sampling": bool(dt_std > 0.1 * median_dt),
    }


def write_dataframe(df: pd.DataFrame, output_csv: Path) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)
