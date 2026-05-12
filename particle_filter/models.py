from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RunPaths:
    folder: Path
    imu_csv: Path
    rfid_csv: Path
    arkit_csv: Path


@dataclass(frozen=True)
class TagMap:
    tags: pd.DataFrame

    @property
    def epcs(self) -> set[str]:
        return set(self.tags["epc"].astype(str))

    def position(self, epc: str) -> np.ndarray:
        row = self.tags.loc[self.tags["epc"] == epc]
        if row.empty:
            raise KeyError(f"Unknown EPC: {epc}")
        return row[["x_m", "y_m"]].iloc[0].to_numpy(dtype=float)

    def positions_by_epc(self) -> Dict[str, np.ndarray]:
        return {
            str(row.epc): np.array([float(row.x_m), float(row.y_m)], dtype=float)
            for row in self.tags.itertuples(index=False)
        }


@dataclass(frozen=True)
class ARKitTrajectory:
    unix_t: np.ndarray
    points_local: np.ndarray
    points_map: np.ndarray
    rotation_rad: float
    tracking_state: np.ndarray
    translation_xy: np.ndarray = field(default_factory=lambda: np.zeros(2, dtype=float))


@dataclass(frozen=True)
class MotionData:
    unix_t: np.ndarray
    rel_t: np.ndarray
    step_times_unix: np.ndarray
    step_times_rel: np.ndarray
    step_headings_rad: np.ndarray
    step_count: int
    base_step_length_m: float
    heading_source: str = "unknown"
    correction_summary: Dict[str, float | str] = field(default_factory=dict)


@dataclass(frozen=True)
class AntennaPolicy:
    mode: str
    antenna: Optional[int] = None
    epc_to_antenna: Dict[str, int] = field(default_factory=dict)
    diagnostics: Dict[str, float] = field(default_factory=dict)

    @property
    def label(self) -> str:
        if self.mode == "global":
            return f"antenna_{self.antenna}"
        if self.mode == "per_epc":
            return "per_epc_auto"
        return self.mode

    def to_json_dict(self) -> Dict[str, object]:
        return {
            "mode": self.mode,
            "antenna": self.antenna,
            "epc_to_antenna": dict(sorted(self.epc_to_antenna.items())),
            "diagnostics": self.diagnostics,
        }

    @classmethod
    def from_json_dict(cls, data: Dict[str, object]) -> "AntennaPolicy":
        return cls(
            mode=str(data["mode"]),
            antenna=int(data["antenna"]) if data.get("antenna") is not None else None,
            epc_to_antenna={str(k): int(v) for k, v in dict(data.get("epc_to_antenna", {})).items()},
            diagnostics={str(k): float(v) for k, v in dict(data.get("diagnostics", {})).items()},
        )


@dataclass(frozen=True)
class PFConfig:
    particle_count: int = 800
    seed: int = 7
    base_step_length_m: float = 0.7
    step_scale_mean: float = 1.0
    step_scale_std: float = 0.08
    step_scale_process_std: float = 0.002
    heading_sign: float = 1.0
    heading_offset_mean_rad: float = 0.0
    heading_offset_std_rad: float = 0.08
    heading_noise_std_rad: float = 0.035
    position_init_std_m: float = 0.05
    step_noise_std_m: float = 0.04
    anchor_radius_m: float = 2.0
    rfid_weight: float = 0.03
    rfid_time_offset_s: float = 0.0
    rfid_measurement_model: str = "rssi_anchor"
    rssi_weak_dbm: float = -75.0
    rssi_strong_dbm: float = -50.0
    rssi_min_weight: float = 0.05
    rssi_weight_power: float = 1.5
    phase_delta_scale: float = 0.02
    phase_delta_sigma: float = 0.45
    phase_delta_max_abs: float = 120.0
    phase_expected_deadband_m: float = 0.03
    resample_fraction: float = 0.5

    def to_json_dict(self) -> Dict[str, object]:
        return asdict(self)

    @classmethod
    def from_json_dict(cls, data: Dict[str, object]) -> "PFConfig":
        fields = cls.__dataclass_fields__
        return cls(**{name: data[name] for name in fields if name in data})


@dataclass(frozen=True)
class PFResult:
    times_unix: np.ndarray
    points: np.ndarray
    final_point: np.ndarray
    accepted_rfid_count: int
    ignored_rfid_count: int
    policy: AntennaPolicy
    particle_times_unix: Optional[np.ndarray] = None
    particle_points: Optional[np.ndarray] = None
    chosen_particle_points: Optional[np.ndarray] = None


@dataclass(frozen=True)
class CalibrationResult:
    calibration_dir: str
    policy: AntennaPolicy
    pf_config: PFConfig
    arkit_rotation_rad: float
    metrics: Dict[str, float]
    candidate_count: int

    def to_json_dict(self) -> Dict[str, object]:
        return {
            "calibration_dir": self.calibration_dir,
            "policy": self.policy.to_json_dict(),
            "pf_config": self.pf_config.to_json_dict(),
            "arkit_rotation_rad": self.arkit_rotation_rad,
            "metrics": self.metrics,
            "candidate_count": self.candidate_count,
        }

    @classmethod
    def from_json_dict(cls, data: Dict[str, object]) -> "CalibrationResult":
        return cls(
            calibration_dir=str(data["calibration_dir"]),
            policy=AntennaPolicy.from_json_dict(dict(data["policy"])),
            pf_config=PFConfig.from_json_dict(dict(data["pf_config"])),
            arkit_rotation_rad=float(data["arkit_rotation_rad"]),
            metrics={str(k): float(v) for k, v in dict(data["metrics"]).items()},
            candidate_count=int(data.get("candidate_count", 0)),
        )
