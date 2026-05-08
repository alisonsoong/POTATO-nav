from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np


GRAVITY_MPS2 = 9.80665
DEFAULT_STEP_LENGTH_M = 0.7


LONG_STATIC_REST = "long_static_rest"
STATIC_6_ORIENTATION = "static_6_orientation"
KNOWN_ANGLE_ROTATION = "known_angle_rotation"
BIAS_SETTLING = "bias_settling"
STRAIGHT_LINE_WALK = "straight_line_walk"
KNOWN_PATH_TURNS = "known_path_turns"
OUT_AND_BACK = "out_and_back"
CARRYING_MODE_SENSITIVITY = "carrying_mode_sensitivity"

TEST_TYPES = (
    LONG_STATIC_REST,
    STATIC_6_ORIENTATION,
    KNOWN_ANGLE_ROTATION,
    BIAS_SETTLING,
    STRAIGHT_LINE_WALK,
    KNOWN_PATH_TURNS,
    OUT_AND_BACK,
    CARRYING_MODE_SENSITIVITY,
)


@dataclass(frozen=True)
class IMURun:
    source_files: List[str]
    metadata: Dict[str, str]
    sample_interval_s: float
    t: np.ndarray
    gyro_x: np.ndarray
    gyro_y: np.ndarray
    gyro_z: np.ndarray
    accel_x: np.ndarray
    accel_y: np.ndarray
    accel_z: np.ndarray
    user_accel_x: Optional[np.ndarray] = None
    user_accel_y: Optional[np.ndarray] = None
    user_accel_z: Optional[np.ndarray] = None
    gravity_x: Optional[np.ndarray] = None
    gravity_y: Optional[np.ndarray] = None
    gravity_z: Optional[np.ndarray] = None
    roll: Optional[np.ndarray] = None
    pitch: Optional[np.ndarray] = None
    yaw: Optional[np.ndarray] = None
    mag_accuracy: Optional[np.ndarray] = None


@dataclass(frozen=True)
class AllanPoint:
    tau_s: float
    deviation: float


@dataclass(frozen=True)
class IMUAxisStats:
    mean: float
    standard_deviation: float


@dataclass(frozen=True)
class StaticCharacterization:
    gyro_x: IMUAxisStats
    gyro_y: IMUAxisStats
    gyro_z: IMUAxisStats
    fused_accel_x: IMUAxisStats
    fused_accel_y: IMUAxisStats
    fused_accel_z: IMUAxisStats
    user_accel_x: IMUAxisStats
    user_accel_y: IMUAxisStats
    user_accel_z: IMUAxisStats
    user_accel_available: bool
    orientation_drift_deg_per_sec: float
    orientation_drift_deg_per_min: float
    allan_deviation_gyro_z: List[AllanPoint]
    allan_deviation_fused_accel_z: List[AllanPoint]
    allan_deviation_user_accel_z: List[AllanPoint]


@dataclass(frozen=True)
class ParticleSimulationParameters:
    sample_rate_hz: float
    gyro_bias_rad_per_sec: float
    accel_bias_g: float
    gyro_noise_density_rad_per_sec_per_sqrt_hz: float
    accel_noise_density_g_per_sqrt_hz: float
    arw_deg_per_sqrt_hour: float
    vrw_mps_per_sqrt_hour: float
    gyro_bias_instability_deg_per_hour: float
    accel_bias_instability_g: float


@dataclass(frozen=True)
class TestSpec:
    csv_file: Path
    test_type: str
    trial_id: str = ""
    group: str = ""
    orientation: str = ""
    rotation_axis: str = "z"
    expected_angle_deg: Optional[float] = None
    expected_distance_m: Optional[float] = None
    expected_path_length_m: Optional[float] = None
    expected_end_x_m: Optional[float] = None
    expected_end_y_m: Optional[float] = None
    expected_turn_count: Optional[int] = None
    carrying_mode: str = ""
    closed_loop: Optional[bool] = None
    notes: str = ""


@dataclass(frozen=True)
class PDRPathEstimate:
    step_count: int
    sample_rate_hz: float
    path_length_m: float
    displacement_m: float
    straightness_ratio: float
    endpoint_x_m: float
    endpoint_y_m: float
    heading_change_deg: float
    turn_count: int
    closure_error_m: Optional[float]
    step_length_m: float
    xs: np.ndarray
    ys: np.ndarray


def parse_csv_metadata(csv_path: Path) -> Dict[str, str]:
    metadata: Dict[str, str] = {}
    with csv_path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.startswith("#"):
                break
            key, _, value = line[1:].strip().partition(",")
            if key:
                metadata[key.strip()] = value.strip()
    return metadata


def load_imu_csv(csv_path: Path) -> IMURun:
    rows = _read_csv_rows(csv_path)

    t = _required_numeric(rows, "timestamp_s", "timestamp")
    gyro_x = _required_numeric(rows, "gyro_x")
    gyro_y = _required_numeric(rows, "gyro_y")
    gyro_z = _required_numeric(rows, "gyro_z")
    accel_x = _required_numeric(rows, "accel_x", "fused_accel_x")
    accel_y = _required_numeric(rows, "accel_y", "fused_accel_y")
    accel_z = _required_numeric(rows, "accel_z", "fused_accel_z")
    optional = {
        "user_accel_x": _optional_numeric(rows, "user_accel_x"),
        "user_accel_y": _optional_numeric(rows, "user_accel_y"),
        "user_accel_z": _optional_numeric(rows, "user_accel_z"),
        "gravity_x": _optional_numeric(rows, "gravity_x"),
        "gravity_y": _optional_numeric(rows, "gravity_y"),
        "gravity_z": _optional_numeric(rows, "gravity_z"),
        "roll": _optional_numeric(rows, "roll"),
        "pitch": _optional_numeric(rows, "pitch"),
        "yaw": _optional_numeric(rows, "yaw"),
        "mag_accuracy": _optional_numeric(rows, "mag_accuracy", "magnetic_field_accuracy"),
    }

    valid = np.isfinite(t)
    for series in (gyro_x, gyro_y, gyro_z, accel_x, accel_y, accel_z):
        valid &= np.isfinite(series)

    if int(valid.sum()) < 3:
        raise ValueError(f"Not enough valid IMU samples in {csv_path}.")

    t = t[valid]
    gyro_x = gyro_x[valid]
    gyro_y = gyro_y[valid]
    gyro_z = gyro_z[valid]
    accel_x = accel_x[valid]
    accel_y = accel_y[valid]
    accel_z = accel_z[valid]
    optional = {
        key: series[valid] if series is not None else None
        for key, series in optional.items()
    }

    order = np.argsort(t)
    t = t[order] - t[order][0]
    gyro_x = gyro_x[order]
    gyro_y = gyro_y[order]
    gyro_z = gyro_z[order]
    accel_x = accel_x[order]
    accel_y = accel_y[order]
    accel_z = accel_z[order]
    optional = {
        key: series[order] if series is not None else None
        for key, series in optional.items()
    }

    metadata = parse_csv_metadata(csv_path)
    sample_interval = _metadata_sample_interval(metadata)
    if sample_interval is None:
        sample_interval = infer_sample_interval(t)

    return IMURun(
        source_files=[str(csv_path)],
        metadata=metadata,
        sample_interval_s=sample_interval,
        t=t,
        gyro_x=gyro_x,
        gyro_y=gyro_y,
        gyro_z=gyro_z,
        accel_x=accel_x,
        accel_y=accel_y,
        accel_z=accel_z,
        user_accel_x=optional["user_accel_x"],
        user_accel_y=optional["user_accel_y"],
        user_accel_z=optional["user_accel_z"],
        gravity_x=optional["gravity_x"],
        gravity_y=optional["gravity_y"],
        gravity_z=optional["gravity_z"],
        roll=optional["roll"],
        pitch=optional["pitch"],
        yaw=optional["yaw"],
        mag_accuracy=optional["mag_accuracy"],
    )


def merge_imu_runs(runs: Sequence[IMURun]) -> IMURun:
    if not runs:
        raise ValueError("At least one IMU run is required.")
    if len(runs) == 1:
        return runs[0]

    sample_interval = float(np.mean([run.sample_interval_s for run in runs]))
    t_parts = []
    offset = 0.0
    for run in runs:
        local_t = run.t - run.t[0]
        merged_t = local_t + offset
        t_parts.append(merged_t)
        offset = float(merged_t[-1] + sample_interval)

    metadata = {
        "merged_run_count": str(len(runs)),
        "test_types": ", ".join(
            sorted({run.metadata.get("test_type", "unknown") for run in runs})
        ),
    }

    return IMURun(
        source_files=[source for run in runs for source in run.source_files],
        metadata=metadata,
        sample_interval_s=sample_interval,
        t=np.concatenate(t_parts),
        gyro_x=np.concatenate([run.gyro_x for run in runs]),
        gyro_y=np.concatenate([run.gyro_y for run in runs]),
        gyro_z=np.concatenate([run.gyro_z for run in runs]),
        accel_x=np.concatenate([run.accel_x for run in runs]),
        accel_y=np.concatenate([run.accel_y for run in runs]),
        accel_z=np.concatenate([run.accel_z for run in runs]),
        user_accel_x=_concat_optional([run.user_accel_x for run in runs]),
        user_accel_y=_concat_optional([run.user_accel_y for run in runs]),
        user_accel_z=_concat_optional([run.user_accel_z for run in runs]),
        gravity_x=_concat_optional([run.gravity_x for run in runs]),
        gravity_y=_concat_optional([run.gravity_y for run in runs]),
        gravity_z=_concat_optional([run.gravity_z for run in runs]),
        roll=_concat_optional([run.roll for run in runs]),
        pitch=_concat_optional([run.pitch for run in runs]),
        yaw=_concat_optional([run.yaw for run in runs]),
        mag_accuracy=_concat_optional([run.mag_accuracy for run in runs]),
    )


def analyze_long_static_rest(
    run: IMURun,
    label: str = "",
) -> Dict[str, Any]:
    characterization = static_characterization(run)
    warnings = static_flat_warnings(run, characterization)
    static_flat = build_static_flat_section(run, characterization)
    allan_model = build_allan_noise_model(run, characterization, warnings)
    return {
        "test_type": "static_flat",
        "label": label,
        "source_files": run.source_files,
        "static_flat": static_flat,
        "allan_noise_model": allan_model,
        "notes_and_warnings": warnings,
    }


def build_static_flat_section(
    run: IMURun,
    characterization: StaticCharacterization,
) -> Dict[str, Any]:
    duration_s = run_duration_s(run)
    gyro_bias = stats_vector(characterization.gyro_x, characterization.gyro_y, characterization.gyro_z, "mean")
    gyro_noise = stats_vector(characterization.gyro_x, characterization.gyro_y, characterization.gyro_z, "standard_deviation")
    user_accel_bias = stats_vector(characterization.user_accel_x, characterization.user_accel_y, characterization.user_accel_z, "mean")
    user_accel_noise = stats_vector(characterization.user_accel_x, characterization.user_accel_y, characterization.user_accel_z, "standard_deviation")
    fused_accel_mean = stats_vector(characterization.fused_accel_x, characterization.fused_accel_y, characterization.fused_accel_z, "mean")
    fused_accel_noise = stats_vector(characterization.fused_accel_x, characterization.fused_accel_y, characterization.fused_accel_z, "standard_deviation")

    return {
        "duration_s": duration_s,
        "samples": int(run.t.size),
        "phone_flatness": phone_flatness_section(run),
        "gyro_bias_rad_per_s": gyro_bias,
        "gyro_noise_std_rad_per_s": gyro_noise,
        "gyro_noise_rms_rad_per_s": rms_from_vector(gyro_noise),
        "user_accel_bias_g": user_accel_bias,
        "user_accel_noise_std_g": user_accel_noise,
        "user_accel_noise_rms_g": rms_from_vector(user_accel_noise),
        "fused_accel_mean_g": fused_accel_mean,
        "fused_accel_noise_std_g": fused_accel_noise,
        "attitude_drift": attitude_drift_section(run),
        "gyro_integrated_yaw_drift": gyro_integrated_yaw_drift_section(
            run,
            characterization.gyro_z.mean,
        ),
    }


def build_allan_noise_model(
    run: IMURun,
    characterization: StaticCharacterization,
    warnings: List[str],
) -> Dict[str, Any]:
    sample_rate_hz = 1.0 / run.sample_interval_s
    gyro_noise = np.array([
        characterization.gyro_x.standard_deviation,
        characterization.gyro_y.standard_deviation,
        characterization.gyro_z.standard_deviation,
    ])
    if characterization.user_accel_available:
        accel_noise = np.array([
            characterization.user_accel_x.standard_deviation,
            characterization.user_accel_y.standard_deviation,
            characterization.user_accel_z.standard_deviation,
        ])
        accel_source = "user_accel"
    else:
        accel_noise = np.array([
            characterization.fused_accel_x.standard_deviation,
            characterization.fused_accel_y.standard_deviation,
            characterization.fused_accel_z.standard_deviation,
        ])
        accel_source = "fused_accel"
        warnings.append(
            "user_accel columns are missing; accelerometer noise density uses fused accel "
            "and may include gravity/orientation effects."
        )

    gyro_noise_density = gyro_noise / np.sqrt(sample_rate_hz)
    accel_noise_density = accel_noise / np.sqrt(sample_rate_hz)
    arw = gyro_noise_density * 180.0 / np.pi * np.sqrt(3600.0)
    vrw = accel_noise_density * GRAVITY_MPS2 * np.sqrt(3600.0)

    gyro_allan = {
        "x": allan_deviation(run.gyro_x, run.sample_interval_s),
        "y": allan_deviation(run.gyro_y, run.sample_interval_s),
        "z": allan_deviation(run.gyro_z, run.sample_interval_s),
    }
    accel_arrays = user_accel_arrays(run) if characterization.user_accel_available else fused_accel_arrays(run)
    accel_allan = {
        "x": allan_deviation(accel_arrays[0], run.sample_interval_s),
        "y": allan_deviation(accel_arrays[1], run.sample_interval_s),
        "z": allan_deviation(accel_arrays[2], run.sample_interval_s),
    }

    return {
        "source_test_type": "static_flat",
        "duration_s": run_duration_s(run),
        "sample_rate_hz": sample_rate_hz,
        "accel_noise_source": accel_source,
        "gyro_noise_density_rad_per_s_per_sqrt_hz": vector_dict(gyro_noise_density),
        "accel_noise_density_g_per_sqrt_hz": vector_dict(accel_noise_density),
        "arw_deg_per_sqrt_hour": vector_dict(arw),
        "vrw_mps_per_sqrt_hour": vector_dict(vrw),
        "gyro_bias_instability_deg_per_hour": vector_dict(np.array([
            gyro_bias_instability_deg_per_hour(gyro_allan["x"]),
            gyro_bias_instability_deg_per_hour(gyro_allan["y"]),
            gyro_bias_instability_deg_per_hour(gyro_allan["z"]),
        ])),
        "accel_bias_instability_g": vector_dict(np.array([
            estimate_bias_instability(accel_allan["x"]),
            estimate_bias_instability(accel_allan["y"]),
            estimate_bias_instability(accel_allan["z"]),
        ])),
        "allan_deviation": {
            "gyro_x": allan_points_to_dicts(gyro_allan["x"]),
            "gyro_y": allan_points_to_dicts(gyro_allan["y"]),
            "gyro_z": allan_points_to_dicts(gyro_allan["z"]),
            "user_accel_x": allan_points_to_dicts(accel_allan["x"]) if accel_source == "user_accel" else None,
            "user_accel_y": allan_points_to_dicts(accel_allan["y"]) if accel_source == "user_accel" else None,
            "user_accel_z": allan_points_to_dicts(accel_allan["z"]) if accel_source == "user_accel" else None,
            "fused_accel_x": allan_points_to_dicts(accel_allan["x"]) if accel_source == "fused_accel" else None,
            "fused_accel_y": allan_points_to_dicts(accel_allan["y"]) if accel_source == "fused_accel" else None,
            "fused_accel_z": allan_points_to_dicts(accel_allan["z"]) if accel_source == "fused_accel" else None,
        },
    }


def analyze_six_orientation_static(
    specs: Sequence[TestSpec],
) -> Dict[str, Any]:
    if not specs:
        raise ValueError("Six-orientation analysis requires at least one test spec.")

    orientation_trials: Dict[str, List[Dict[str, Any]]] = {}
    means_by_orientation: Dict[str, List[np.ndarray]] = {}
    gyro_by_orientation: Dict[str, List[np.ndarray]] = {}

    for spec in specs:
        run = load_imu_csv(spec.csv_file)
        orientation = canonical_orientation(
            spec.orientation or run.metadata.get("orientation", "") or spec.csv_file.stem
        )
        fused_accel_mean = np.array(
            [
                float(np.mean(run.accel_x)),
                float(np.mean(run.accel_y)),
                float(np.mean(run.accel_z)),
            ]
        )
        fused_norm = np.sqrt(run.accel_x**2 + run.accel_y**2 + run.accel_z**2)
        user_accel_mean = user_accel_mean_vector(run)
        gravity_mean = gravity_mean_vector(run)
        gyro_mean = np.array(
            [
                float(np.mean(run.gyro_x)),
                float(np.mean(run.gyro_y)),
                float(np.mean(run.gyro_z)),
            ]
        )
        means_by_orientation.setdefault(orientation, []).append(fused_accel_mean)
        gyro_by_orientation.setdefault(orientation, []).append(gyro_mean)
        expected_axis, expected_sign = orientation_expected_axis_sign(orientation)
        dominant = dominant_axis_name(fused_accel_mean)
        axis_index = axis_index_for_name(expected_axis) if expected_axis is not None else None
        axis_error = (
            float(fused_accel_mean[axis_index] - expected_sign)
            if axis_index is not None and expected_sign is not None
            else None
        )
        cross_axis = cross_axis_magnitude(fused_accel_mean, axis_index)
        orientation_trials.setdefault(orientation, []).append({
            "source_file": str(spec.csv_file),
            "samples": int(run.t.size),
            "duration_s": float(run.t[-1] - run.t[0]),
            "fused_accel_mean_g": vector_dict(fused_accel_mean),
            "user_accel_mean_g": vector_dict(user_accel_mean),
            "gravity_mean_g": nullable_vector_dict(gravity_mean),
            "fused_accel_norm_mean_g": float(np.mean(fused_norm)),
            "fused_accel_norm_std_g": sample_std(fused_norm),
            "dominant_axis": dominant,
            "expected_axis": expected_axis,
            "expected_sign": expected_sign,
            "axis_error_g": axis_error,
            "cross_axis_magnitude_g": cross_axis,
            "gyro_mean_rad_per_sec": vector_dict(gyro_mean),
        })

    orientations: Dict[str, Dict[str, Any]] = {}
    for orientation, trials in orientation_trials.items():
        fused_means = np.vstack(means_by_orientation[orientation])
        user_means = np.vstack([
            np.array([
                trial["user_accel_mean_g"]["x"],
                trial["user_accel_mean_g"]["y"],
                trial["user_accel_mean_g"]["z"],
            ])
            for trial in trials
        ])
        gyro_means = np.vstack(gyro_by_orientation[orientation])
        fused_mean = np.mean(fused_means, axis=0)
        expected_axis, expected_sign = orientation_expected_axis_sign(orientation)
        axis_index = axis_index_for_name(expected_axis) if expected_axis is not None else None
        fused_norm_means = np.array([trial["fused_accel_norm_mean_g"] for trial in trials])
        cross_axis_values = [
            trial["cross_axis_magnitude_g"]
            for trial in trials
            if trial["cross_axis_magnitude_g"] is not None
        ]
        orientations[orientation] = {
            "samples": int(sum(trial["samples"] for trial in trials)),
            "duration_s": float(sum(trial["duration_s"] for trial in trials)),
            "trial_count": len(trials),
            "trials": trials,
            "fused_accel_mean_g": vector_dict(fused_mean),
            "user_accel_mean_g": vector_dict(finite_column_mean(user_means)),
            "gravity_mean_g": nullable_vector_dict(finite_column_mean_from_trial_dicts(trials, "gravity_mean_g")),
            "fused_accel_norm_mean_g": float(np.mean(fused_norm_means)),
            "fused_accel_norm_std_g": sample_std(fused_norm_means),
            "dominant_axis": dominant_axis_name(fused_mean),
            "expected_axis": expected_axis,
            "expected_sign": expected_sign,
            "axis_error_g": (
                float(fused_mean[axis_index] - expected_sign)
                if axis_index is not None and expected_sign is not None
                else None
            ),
            "cross_axis_magnitude_g": (
                float(np.max(cross_axis_values)) if cross_axis_values else None
            ),
            "gyro_mean_rad_per_sec": vector_dict(np.mean(gyro_means, axis=0)),
        }

    orientation_means = {
        orientation: np.mean(np.vstack(means), axis=0)
        for orientation, means in means_by_orientation.items()
    }

    pairs = (("x_up", "x_down", "x"), ("y_up", "y_down", "y"), ("z_up", "z_down", "z"))
    accel_bias: Dict[str, float] = {}
    accel_scale: Dict[str, float] = {}
    pair_errors: Dict[str, Any] = {}

    for positive, negative, axis in pairs:
        if positive not in orientation_means or negative not in orientation_means:
            continue
        axis_index = {"x": 0, "y": 1, "z": 2}[axis]
        pos = orientation_means[positive]
        neg = orientation_means[negative]
        bias_vector = (pos + neg) / 2.0
        signed_span = (pos[axis_index] - neg[axis_index]) / 2.0
        accel_bias[axis] = float(bias_vector[axis_index])
        accel_scale[axis] = float(abs(signed_span))
        pair_errors[axis] = {
            "positive_orientation": positive,
            "negative_orientation": negative,
            "axis_bias_g": accel_bias[axis],
            "axis_scale_g": accel_scale[axis],
            "axis_scale_error_g": float(abs(signed_span) - 1.0),
            "axis_pair_consistency_error_g": float(abs(abs(signed_span) - 1.0)),
            "pair_cross_axis_bias_g": vector_dict(bias_vector),
        }

    all_gyro_means = np.vstack([
        gyro_mean
        for gyro_means in gyro_by_orientation.values()
        for gyro_mean in gyro_means
    ])
    max_cross_axis = [
        pose["cross_axis_magnitude_g"]
        for pose in orientations.values()
        if pose["cross_axis_magnitude_g"] is not None
    ]
    orientation_warnings = [
        f"Missing six-orientation pose: {orientation}"
        for orientation in ("x_up", "x_down", "y_up", "y_down", "z_up", "z_down")
        if orientation not in orientations
    ]
    for orientation, pose in orientations.items():
        if pose["expected_axis"] is not None and pose["dominant_axis"] != pose["expected_axis"]:
            orientation_warnings.append(
                f"{orientation} dominant axis is {pose['dominant_axis']}, expected {pose['expected_axis']}."
            )
        if pose["axis_error_g"] is not None and abs(pose["axis_error_g"]) > 0.5:
            orientation_warnings.append(
                f"{orientation} observed sign/axis differs from default convention; "
                "check orientation labels or adjust the orientation convention."
            )

    return {
        "test_type": "six_orientation_accel",
        "group": specs[0].group,
        "six_orientation_accel": {
            "poses": orientations,
            "estimated_accel_bias_g": fill_axis_dict(accel_bias),
            "estimated_accel_scale_g_per_g": fill_axis_dict(accel_scale),
            "axis_pair_consistency_error_g": {
                axis: pair_errors[axis]["axis_pair_consistency_error_g"]
                for axis in ("x", "y", "z")
                if axis in pair_errors
            },
            "axis_pair_consistency_error_definition": "abs(abs((plus_axis_mean - minus_axis_mean) / 2) - 1)",
            "max_cross_axis_error_g": float(np.max(max_cross_axis)) if max_cross_axis else None,
            "orientation_label_warnings": orientation_warnings,
        },
        "gyro_bias_by_orientation_mean_rad_per_sec": vector_dict(np.mean(all_gyro_means, axis=0)),
        "gyro_bias_by_orientation_std_rad_per_sec": vector_dict(np.std(all_gyro_means, axis=0, ddof=0)),
        "notes_and_warnings": orientation_warnings,
    }


def analyze_known_angle_rotation(
    run: IMURun,
    expected_angle_deg: Optional[float] = None,
    axis: str = "z",
    label: str = "",
) -> Dict[str, Any]:
    gyro = gyro_axis(run, axis)
    integrated_angle_rad = integrate_rate(run.t, gyro)
    integrated_angle_deg = float(np.degrees(integrated_angle_rad[-1]))
    yaw_delta_deg = None
    if axis in {"z", "yaw"} and run.yaw is not None:
        yaw_delta_deg = float(np.degrees(np.unwrap(run.yaw)[-1] - np.unwrap(run.yaw)[0]))

    result = {
        "test_type": KNOWN_ANGLE_ROTATION,
        "label": label,
        "source_files": run.source_files,
        "axis": axis,
        "samples": int(run.t.size),
        "duration_s": float(run.t[-1] - run.t[0]),
        "integrated_gyro_angle_deg": integrated_angle_deg,
        "absolute_integrated_gyro_angle_deg": abs(integrated_angle_deg),
        "attitude_yaw_delta_deg": yaw_delta_deg,
        "peak_rate_deg_per_s": float(np.degrees(np.max(np.abs(gyro)))),
        "mean_rate_deg_per_s": float(np.degrees(np.mean(gyro))),
    }
    if expected_angle_deg is not None:
        signed_error = integrated_angle_deg - expected_angle_deg
        abs_error = abs(abs(integrated_angle_deg) - abs(expected_angle_deg))
        result.update(
            {
                "expected_angle_deg": expected_angle_deg,
                "signed_angle_error_deg": signed_error,
                "absolute_angle_error_deg": abs_error,
                "percent_error": safe_ratio(abs_error, abs(expected_angle_deg)) * 100.0,
            }
        )
    return result


def analyze_known_yaw_rotation_trials(
    specs: Sequence[TestSpec],
    gyro_bias_rad_per_s: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    warnings: List[str] = []
    trials = []
    for spec in specs:
        run = load_imu_csv(spec.csv_file)
        true_rotation = true_rotation_signed_deg(spec, run, warnings)
        gyro_integrals = {
            "x": float(np.degrees(integrate_rate(run.t, run.gyro_x)[-1])),
            "y": float(np.degrees(integrate_rate(run.t, run.gyro_y)[-1])),
            "z": float(np.degrees(integrate_rate(run.t, run.gyro_z)[-1])),
        }
        dominant_axis = max(gyro_integrals, key=lambda axis_name: abs(gyro_integrals[axis_name]))
        gyro_bias = gyro_bias_rad_per_s or {"x": 0.0, "y": 0.0, "z": 0.0}
        if gyro_bias_rad_per_s is None:
            warnings.append(
                f"{spec.csv_file}: no static_flat gyro bias available; bias-corrected yaw uses zero bias."
            )

        gyro_z_corr = run.gyro_z - float(gyro_bias.get("z", 0.0) or 0.0)
        gyro_corrected_delta = float(np.degrees(integrate_rate(run.t, gyro_z_corr)[-1]))
        yaw_delta = attitude_delta_deg(run.yaw) if run.yaw is not None else None
        yaw_wrap = yaw_wrap_detected(run.yaw)
        if yaw_wrap:
            warnings.append(f"{spec.csv_file}: Core Motion yaw wrap detected; unwrap was applied.")
        tilt = tilt_series_deg(run)
        mean_tilt = float(np.mean(tilt)) if tilt is not None else None
        if mean_tilt is not None and mean_tilt > 5.0:
            warnings.append(
                f"{spec.csv_file}: phone tilt during yaw rotation averaged {mean_tilt:.2f} deg."
            )

        trial = {
            "file": str(spec.csv_file),
            "true_rotation_deg": true_rotation,
            "rotation_direction": rotation_direction_label(true_rotation, run),
            "duration_s": run_duration_s(run),
            "coremotion_yaw_delta_deg": yaw_delta,
            "gyro_integrated_delta_deg": gyro_integrals["z"],
            "gyro_bias_corrected_delta_deg": gyro_corrected_delta,
            "coremotion_yaw_error_deg": subtract_nullable(yaw_delta, true_rotation),
            "gyro_integrated_error_deg": subtract_nullable(gyro_integrals["z"], true_rotation),
            "gyro_bias_corrected_error_deg": subtract_nullable(gyro_corrected_delta, true_rotation),
            "dominant_gyro_axis": dominant_axis,
            "gyro_axis_integrals_deg": gyro_integrals,
            "gravity_z_abs_mean_g": gravity_z_abs_mean(run),
            "phone_flatness_tilt_deg_mean": mean_tilt,
            "yaw_wrap_detected": yaw_wrap,
        }
        if true_rotation is None:
            warnings.append(f"{spec.csv_file}: missing true_rotation_deg metadata.")
        trials.append(trial)

    coremotion_errors = finite_values([trial["coremotion_yaw_error_deg"] for trial in trials])
    gyro_errors = finite_values([trial["gyro_integrated_error_deg"] for trial in trials])
    corrected_errors = finite_values([trial["gyro_bias_corrected_error_deg"] for trial in trials])
    scale_trials = []
    for trial in trials:
        true_rotation = trial["true_rotation_deg"]
        corrected = trial["gyro_bias_corrected_delta_deg"]
        if true_rotation is not None and corrected is not None and abs(corrected) > 1e-9:
            scale_trials.append(true_rotation / corrected)
    preferred, reason = choose_heading_source(coremotion_errors, corrected_errors)

    return {
        "test_type": "known_yaw_rotation",
        "known_yaw_rotation": {
            "trials": trials,
            "summary": {
                "trial_count": len(trials),
                "coremotion_yaw_mae_deg": mean_abs(coremotion_errors),
                "coremotion_yaw_bias_deg": mean_or_none(coremotion_errors),
                "gyro_integrated_mae_deg": mean_abs(gyro_errors),
                "gyro_integrated_bias_deg": mean_or_none(gyro_errors),
                "gyro_bias_corrected_mae_deg": mean_abs(corrected_errors),
                "gyro_bias_corrected_bias_deg": mean_or_none(corrected_errors),
                "estimated_gyro_z_scale_factor": (
                    float(np.median(scale_trials)) if scale_trials else None
                ),
                "dominant_yaw_axis": most_common([
                    trial["dominant_gyro_axis"] for trial in trials
                ]),
                "sign_convention": "left_positive_right_negative",
                "recommendation_preferred_heading_source": preferred,
                "heading_source_reason": reason,
                "by_true_rotation_deg": known_yaw_group_summary(trials),
            },
        },
        "notes_and_warnings": warnings,
    }


def analyze_bias_settling(
    run: IMURun,
    static_window_s: float = 5.0,
    rolling_window_s: float = 1.0,
    tolerance_rad_per_s: float = 0.01,
    hold_s: float = 2.0,
    label: str = "",
) -> Dict[str, Any]:
    gyro_norm = np.sqrt(run.gyro_x**2 + run.gyro_y**2 + run.gyro_z**2)
    accel_norm = np.sqrt(run.accel_x**2 + run.accel_y**2 + run.accel_z**2)
    motion_score = gyro_norm + np.abs(accel_norm - 1.0)
    peak_index = int(np.argmax(motion_score))

    final_window = run.t >= max(run.t[-1] - static_window_s, run.t[0])
    if int(final_window.sum()) < 3:
        final_window = np.arange(run.t.size) >= max(run.t.size - 3, 0)

    final_bias = np.array(
        [
            float(np.mean(run.gyro_x[final_window])),
            float(np.mean(run.gyro_y[final_window])),
            float(np.mean(run.gyro_z[final_window])),
        ]
    )
    initial_window = run.t <= min(run.t[0] + static_window_s, run.t[-1])
    initial_bias = np.array(
        [
            float(np.mean(run.gyro_x[initial_window])),
            float(np.mean(run.gyro_y[initial_window])),
            float(np.mean(run.gyro_z[initial_window])),
        ]
    )

    rolling = rolling_mean(
        np.column_stack([run.gyro_x, run.gyro_y, run.gyro_z]),
        max(1, int(round(rolling_window_s / run.sample_interval_s))),
    )
    error = np.linalg.norm(rolling - final_bias, axis=1)
    start_after_motion = peak_index
    hold_samples = max(1, int(round(hold_s / run.sample_interval_s)))
    settled_index = first_hold_index(error, tolerance_rad_per_s, hold_samples, start_after_motion)
    settling_time = None
    if settled_index is not None:
        settling_time = float(run.t[settled_index] - run.t[peak_index])

    return {
        "test_type": BIAS_SETTLING,
        "label": label,
        "source_files": run.source_files,
        "samples": int(run.t.size),
        "duration_s": float(run.t[-1] - run.t[0]),
        "motion_peak_time_s": float(run.t[peak_index]),
        "initial_gyro_bias_rad_per_sec": vector_dict(initial_bias),
        "final_gyro_bias_rad_per_sec": vector_dict(final_bias),
        "bias_shift_rad_per_sec": vector_dict(final_bias - initial_bias),
        "rolling_window_s": rolling_window_s,
        "settling_tolerance_rad_per_sec": tolerance_rad_per_s,
        "settling_hold_s": hold_s,
        "settling_time_after_motion_s": settling_time,
        "max_post_motion_bias_error_rad_per_sec": float(np.max(error[start_after_motion:])),
    }


def analyze_static_after_motion_trials(
    specs: Sequence[TestSpec],
) -> Dict[str, Any]:
    warnings: List[str] = []
    trials = []
    for spec in specs:
        run = load_imu_csv(spec.csv_file)
        before_mask, after_mask, segment_note = static_after_motion_masks(run)
        if segment_note:
            warnings.append(f"{spec.csv_file}: {segment_note}")
        before_bias = gyro_mean_for_mask(run, before_mask)
        after_bias = gyro_mean_for_mask(run, after_mask)
        before_noise = gyro_std_for_mask(run, before_mask, before_bias)
        after_noise = gyro_std_for_mask(run, after_mask, after_bias)
        before_user = user_accel_mean_for_mask(run, before_mask)
        after_user = user_accel_mean_for_mask(run, after_mask)
        after_duration_min = duration_minutes_for_mask(run, after_mask)

        coremotion_drift = yaw_drift_for_mask(run, after_mask)
        gyro_after = integrate_rate(run.t[after_mask], run.gyro_z[after_mask] - before_bias[2])
        gyro_after_drift = (
            float(np.degrees(gyro_after[-1]) / after_duration_min)
            if gyro_after.size > 1 and after_duration_min > 0
            else None
        )

        trials.append(
            {
                "file": str(spec.csv_file),
                "before_static_duration_s": duration_for_mask(run, before_mask),
                "after_static_duration_s": duration_for_mask(run, after_mask),
                "gyro_bias_before_rad_per_s": vector_dict(before_bias),
                "gyro_bias_after_rad_per_s": vector_dict(after_bias),
                "gyro_bias_shift_rad_per_s": vector_dict(after_bias - before_bias),
                "gyro_noise_before_std_rad_per_s": vector_dict(before_noise),
                "gyro_noise_after_std_rad_per_s": vector_dict(after_noise),
                "user_accel_bias_before_g": nullable_vector_dict(before_user),
                "user_accel_bias_after_g": nullable_vector_dict(after_user),
                "user_accel_bias_shift_g": nullable_vector_dict(after_user - before_user),
                "coremotion_yaw_drift_after_deg_per_min": coremotion_drift,
                "gyro_integrated_yaw_drift_after_deg_per_min": gyro_after_drift,
                "gyro_integrated_yaw_correction_used": "before_static_gyro_z_bias",
            }
        )

    shifts = np.array([
        [
            trial["gyro_bias_shift_rad_per_s"]["x"],
            trial["gyro_bias_shift_rad_per_s"]["y"],
            trial["gyro_bias_shift_rad_per_s"]["z"],
        ]
        for trial in trials
    ]) if trials else np.empty((0, 3))
    yaw_drifts = finite_values([
        trial["gyro_integrated_yaw_drift_after_deg_per_min"] for trial in trials
    ])
    max_shift = np.max(np.abs(shifts), axis=0) if shifts.size else np.array([np.nan, np.nan, np.nan])
    recommendation = bool(np.any(max_shift > 0.01)) if shifts.size else None

    return {
        "test_type": "static_after_motion",
        "static_after_motion": {
            "trials": trials,
            "summary": {
                "trial_count": len(trials),
                "mean_gyro_bias_shift_rad_per_s": nullable_vector_dict(
                    np.mean(shifts, axis=0) if shifts.size else np.array([np.nan, np.nan, np.nan])
                ),
                "max_abs_gyro_bias_shift_rad_per_s": nullable_vector_dict(max_shift),
                "mean_after_motion_yaw_drift_deg_per_min": mean_or_none(yaw_drifts),
                "max_after_motion_yaw_drift_deg_per_min": (
                    float(np.max(np.abs(yaw_drifts))) if yaw_drifts else None
                ),
                "recommendation_recalibrate_bias_before_each_run": recommendation,
            },
        },
        "notes_and_warnings": warnings,
    }


def analyze_straight_line_walk(
    run: IMURun,
    expected_distance_m: Optional[float] = None,
    label: str = "",
    step_length_m: Optional[float] = None,
) -> Dict[str, Any]:
    estimate = estimate_pdr_path(
        run,
        expected_distance_m=expected_distance_m,
        expected_end_xy=(expected_distance_m, 0.0) if expected_distance_m is not None else None,
        step_length_m=step_length_m,
    )
    return {
        "test_type": STRAIGHT_LINE_WALK,
        "label": label,
        "source_files": run.source_files,
        "samples": int(run.t.size),
        "duration_s": float(run.t[-1] - run.t[0]),
        "step_count": estimate.step_count,
        "step_length_m": estimate.step_length_m,
        "estimated_path_length_m": estimate.path_length_m,
        "estimated_displacement_m": estimate.displacement_m,
        "straightness_ratio": estimate.straightness_ratio,
        "endpoint_x_m": estimate.endpoint_x_m,
        "endpoint_y_m": estimate.endpoint_y_m,
        "heading_change_deg": estimate.heading_change_deg,
        "lateral_drift_m": estimate.endpoint_y_m,
        "distance_error_m": (
            estimate.displacement_m - expected_distance_m
            if expected_distance_m is not None
            else None
        ),
        "distance_percent_error": (
            safe_ratio(estimate.displacement_m - expected_distance_m, expected_distance_m) * 100.0
            if expected_distance_m is not None
            else None
        ),
    }


def analyze_known_path_with_turns(
    run: IMURun,
    expected_path_length_m: Optional[float] = None,
    expected_end_xy: Optional[tuple[float, float]] = None,
    expected_turn_count: Optional[int] = None,
    closed_loop: bool = False,
    label: str = "",
) -> Dict[str, Any]:
    estimate = estimate_pdr_path(
        run,
        expected_distance_m=expected_path_length_m,
        expected_end_xy=expected_end_xy if expected_end_xy is not None else ((0.0, 0.0) if closed_loop else None),
    )
    result = {
        "test_type": KNOWN_PATH_TURNS,
        "label": label,
        "source_files": run.source_files,
        "samples": int(run.t.size),
        "duration_s": float(run.t[-1] - run.t[0]),
        "step_count": estimate.step_count,
        "estimated_path_length_m": estimate.path_length_m,
        "estimated_displacement_m": estimate.displacement_m,
        "straightness_ratio": estimate.straightness_ratio,
        "endpoint_x_m": estimate.endpoint_x_m,
        "endpoint_y_m": estimate.endpoint_y_m,
        "heading_change_deg": estimate.heading_change_deg,
        "detected_turn_count": estimate.turn_count,
        "closure_error_m": estimate.closure_error_m,
        "expected_path_length_m": expected_path_length_m,
        "path_length_error_m": (
            estimate.path_length_m - expected_path_length_m
            if expected_path_length_m is not None
            else None
        ),
    }
    if expected_turn_count is not None:
        result["expected_turn_count"] = expected_turn_count
        result["turn_count_error"] = estimate.turn_count - expected_turn_count
    return result


def analyze_out_and_back_hallway(
    run: IMURun,
    expected_one_way_distance_m: Optional[float] = None,
    label: str = "",
) -> Dict[str, Any]:
    expected_path_length = (
        expected_one_way_distance_m * 2.0
        if expected_one_way_distance_m is not None
        else None
    )
    result = analyze_known_path_with_turns(
        run,
        expected_path_length_m=expected_path_length,
        expected_end_xy=(0.0, 0.0),
        expected_turn_count=1,
        closed_loop=True,
        label=label,
    )
    result["test_type"] = OUT_AND_BACK
    result["expected_one_way_distance_m"] = expected_one_way_distance_m
    return result


def analyze_phone_carrying_mode_sensitivity(
    specs: Sequence[TestSpec],
) -> Dict[str, Any]:
    if not specs:
        raise ValueError("Carrying-mode analysis requires at least one test spec.")

    trial_results = []
    for spec in specs:
        run = load_imu_csv(spec.csv_file)
        mode = spec.carrying_mode or run.metadata.get("carrying_mode", "") or "unknown"
        walk = analyze_straight_line_walk(
            run,
            expected_distance_m=spec.expected_distance_m,
            label=spec.trial_id or spec.csv_file.stem,
        )
        walk["carrying_mode"] = mode
        trial_results.append(walk)

    by_mode: Dict[str, List[Dict[str, Any]]] = {}
    for result in trial_results:
        by_mode.setdefault(str(result["carrying_mode"]), []).append(result)

    mode_summary = {}
    for mode, results in by_mode.items():
        mode_summary[mode] = {
            "trial_count": len(results),
            "mean_step_count": mean_metric(results, "step_count"),
            "mean_estimated_path_length_m": mean_metric(results, "estimated_path_length_m"),
            "mean_estimated_displacement_m": mean_metric(results, "estimated_displacement_m"),
            "mean_lateral_drift_m": mean_metric(results, "lateral_drift_m"),
            "mean_heading_change_deg": mean_metric(results, "heading_change_deg"),
            "mean_distance_error_m": mean_metric(results, "distance_error_m"),
        }

    return {
        "test_type": CARRYING_MODE_SENSITIVITY,
        "group": specs[0].group,
        "mode_count": len(mode_summary),
        "modes": mode_summary,
        "trials": trial_results,
    }


def static_characterization(run: IMURun) -> StaticCharacterization:
    gyro_x = axis_stats(run.gyro_x)
    gyro_y = axis_stats(run.gyro_y)
    gyro_z = axis_stats(run.gyro_z)
    fused_accel_x = axis_stats(run.accel_x)
    fused_accel_y = axis_stats(run.accel_y)
    fused_accel_z = axis_stats(run.accel_z)
    user_accel_available = has_user_accel(run)
    user_accel_x = axis_stats(run.user_accel_x) if run.user_accel_x is not None else empty_axis_stats()
    user_accel_y = axis_stats(run.user_accel_y) if run.user_accel_y is not None else empty_axis_stats()
    user_accel_z = axis_stats(run.user_accel_z) if run.user_accel_z is not None else empty_axis_stats()
    drift = orientation_drift(run.t, run.gyro_z)

    return StaticCharacterization(
        gyro_x=gyro_x,
        gyro_y=gyro_y,
        gyro_z=gyro_z,
        fused_accel_x=fused_accel_x,
        fused_accel_y=fused_accel_y,
        fused_accel_z=fused_accel_z,
        user_accel_x=user_accel_x,
        user_accel_y=user_accel_y,
        user_accel_z=user_accel_z,
        user_accel_available=user_accel_available,
        orientation_drift_deg_per_sec=drift,
        orientation_drift_deg_per_min=drift * 60.0,
        allan_deviation_gyro_z=allan_deviation(run.gyro_z, run.sample_interval_s),
        allan_deviation_fused_accel_z=allan_deviation(run.accel_z, run.sample_interval_s),
        allan_deviation_user_accel_z=(
            allan_deviation(run.user_accel_z, run.sample_interval_s)
            if run.user_accel_z is not None
            else []
        ),
    )


def particle_parameters(
    characterization: StaticCharacterization,
    sample_interval_s: float,
) -> ParticleSimulationParameters:
    if sample_interval_s <= 0:
        raise ValueError("Sample interval must be positive.")

    sample_rate_hz = 1.0 / sample_interval_s
    gyro_noise_density = characterization.gyro_z.standard_deviation / np.sqrt(sample_rate_hz)
    accel_noise_density = characterization.user_accel_z.standard_deviation / np.sqrt(sample_rate_hz)
    arw = gyro_noise_density * 180.0 / np.pi * np.sqrt(3600.0)
    vrw = accel_noise_density * GRAVITY_MPS2 * np.sqrt(3600.0)
    gyro_bias_instability = (
        estimate_bias_instability(characterization.allan_deviation_gyro_z)
        * 180.0
        / np.pi
        * 3600.0
    )
    accel_bias_instability = (
        estimate_bias_instability(characterization.allan_deviation_user_accel_z)
        if characterization.user_accel_available
        else float("nan")
    )

    return ParticleSimulationParameters(
        sample_rate_hz=sample_rate_hz,
        gyro_bias_rad_per_sec=characterization.gyro_z.mean,
        accel_bias_g=characterization.user_accel_z.mean,
        gyro_noise_density_rad_per_sec_per_sqrt_hz=gyro_noise_density,
        accel_noise_density_g_per_sqrt_hz=accel_noise_density,
        arw_deg_per_sqrt_hour=arw,
        vrw_mps_per_sqrt_hour=vrw,
        gyro_bias_instability_deg_per_hour=gyro_bias_instability,
        accel_bias_instability_g=accel_bias_instability,
    )


def estimate_pdr_path(
    run: IMURun,
    expected_distance_m: Optional[float] = None,
    expected_end_xy: Optional[tuple[float, float]] = None,
    step_length_m: Optional[float] = None,
) -> PDRPathEstimate:
    t, user_mag = walking_signal(run)
    step_indices = detect_steps_simple(t, user_mag)
    heading = heading_series(run)

    if step_length_m is None:
        if expected_distance_m is not None and step_indices.size > 0:
            step_length_m = expected_distance_m / float(step_indices.size)
        else:
            step_length_m = DEFAULT_STEP_LENGTH_M

    xs = [0.0]
    ys = [0.0]
    if step_indices.size:
        heading0 = heading[step_indices[0]]
        for step_index in step_indices:
            theta = heading[step_index] - heading0
            xs.append(xs[-1] + step_length_m * float(np.cos(theta)))
            ys.append(ys[-1] + step_length_m * float(np.sin(theta)))

    xs_arr = np.asarray(xs)
    ys_arr = np.asarray(ys)
    path_length_m = float(step_length_m * step_indices.size)
    displacement_m = float(np.hypot(xs_arr[-1] - xs_arr[0], ys_arr[-1] - ys_arr[0]))
    straightness_ratio = safe_ratio(displacement_m, path_length_m)
    heading_change = float(np.degrees(heading[-1] - heading[0]))
    turns = detect_turns_from_heading(t, heading)
    closure_error = None
    if expected_end_xy is not None:
        closure_error = float(np.hypot(xs_arr[-1] - expected_end_xy[0], ys_arr[-1] - expected_end_xy[1]))

    return PDRPathEstimate(
        step_count=int(step_indices.size),
        sample_rate_hz=1.0 / run.sample_interval_s,
        path_length_m=path_length_m,
        displacement_m=displacement_m,
        straightness_ratio=straightness_ratio,
        endpoint_x_m=float(xs_arr[-1]),
        endpoint_y_m=float(ys_arr[-1]),
        heading_change_deg=heading_change,
        turn_count=len(turns),
        closure_error_m=closure_error,
        step_length_m=float(step_length_m),
        xs=xs_arr,
        ys=ys_arr,
    )


def axis_stats(values: Optional[np.ndarray]) -> IMUAxisStats:
    if values is None:
        return empty_axis_stats()
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return empty_axis_stats()
    mean = float(np.mean(finite))
    ddof = 1 if finite.size > 1 else 0
    return IMUAxisStats(mean=mean, standard_deviation=float(np.std(finite, ddof=ddof)))


def empty_axis_stats() -> IMUAxisStats:
    return IMUAxisStats(mean=float("nan"), standard_deviation=float("nan"))


def orientation_drift(t: np.ndarray, gyro_z: np.ndarray) -> float:
    if t.size < 2:
        return 0.0
    yaw_rad = integrate_rate(t, gyro_z)[-1]
    total_time = t[-1] - t[0]
    if total_time <= 0:
        return 0.0
    return float(abs(yaw_rad) * 180.0 / np.pi / total_time)


def allan_deviation(signal: Optional[np.ndarray], dt: float) -> List[AllanPoint]:
    if signal is None:
        return []
    signal = signal[np.isfinite(signal)]
    n = signal.size
    if n <= 32:
        return []

    points: List[AllanPoint] = []
    cluster = 1
    while cluster * 2 < n / 2:
        m = n // cluster
        if m < 3:
            break

        averages = []
        for index in range(m):
            start = index * cluster
            end = min(start + cluster, n)
            if end > start:
                averages.append(float(np.mean(signal[start:end])))

        if len(averages) > 2:
            differences = np.diff(np.asarray(averages, dtype=float))
            variance = 0.5 * float(np.sum(differences**2)) / float(len(averages) - 1)
            points.append(
                AllanPoint(
                    tau_s=float(cluster * dt),
                    deviation=float(np.sqrt(max(variance, 0.0))),
                )
            )
        cluster *= 2
    return points


def estimate_bias_instability(allan: Sequence[AllanPoint]) -> float:
    if not allan:
        return 0.0
    return min(point.deviation for point in allan) / 0.664


def infer_sample_interval(t: np.ndarray) -> float:
    dt = np.diff(t)
    valid = dt[np.isfinite(dt) & (dt > 0)]
    if valid.size == 0:
        raise ValueError("Could not infer a valid sample interval from timestamps.")
    return float(np.median(valid))


def integrate_rate(t: np.ndarray, rate: np.ndarray) -> np.ndarray:
    integrated = np.zeros_like(rate, dtype=float)
    for index in range(1, rate.size):
        dt = t[index] - t[index - 1]
        integrated[index] = integrated[index - 1] + rate[index] * dt
    return integrated


def walking_signal(run: IMURun) -> tuple[np.ndarray, np.ndarray]:
    if run.user_accel_x is not None and run.user_accel_y is not None and run.user_accel_z is not None:
        magnitude = np.sqrt(run.user_accel_x**2 + run.user_accel_y**2 + run.user_accel_z**2)
    else:
        magnitude = np.sqrt(run.accel_x**2 + run.accel_y**2 + run.accel_z**2)
        magnitude = magnitude - np.mean(magnitude)
    return run.t, magnitude


def has_user_accel(run: IMURun) -> bool:
    return bool(
        run.user_accel_x is not None
        and run.user_accel_y is not None
        and run.user_accel_z is not None
        and np.any(np.isfinite(run.user_accel_x))
        and np.any(np.isfinite(run.user_accel_y))
        and np.any(np.isfinite(run.user_accel_z))
    )


def user_accel_mean_vector(run: IMURun) -> np.ndarray:
    if not has_user_accel(run):
        return np.array([np.nan, np.nan, np.nan])
    return np.array(
        [
            axis_stats(run.user_accel_x).mean,
            axis_stats(run.user_accel_y).mean,
            axis_stats(run.user_accel_z).mean,
        ]
    )


def finite_column_mean(values: np.ndarray) -> np.ndarray:
    means = []
    for index in range(values.shape[1]):
        column = values[:, index]
        finite = column[np.isfinite(column)]
        means.append(float(np.mean(finite)) if finite.size else float("nan"))
    return np.asarray(means)


def finite_column_mean_from_trial_dicts(trials: Sequence[Dict[str, Any]], key: str) -> np.ndarray:
    values = []
    for trial in trials:
        vector = trial.get(key)
        if isinstance(vector, dict):
            values.append([vector.get("x", np.nan), vector.get("y", np.nan), vector.get("z", np.nan)])
    if not values:
        return np.array([np.nan, np.nan, np.nan])
    return finite_column_mean(np.asarray(values, dtype=float))


def run_duration_s(run: IMURun) -> float:
    return float(run.t[-1] - run.t[0]) if run.t.size else 0.0


def duration_minutes(duration_s: float) -> Optional[float]:
    return duration_s / 60.0 if duration_s > 0 else None


def sample_std(values: np.ndarray) -> Optional[float]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return None
    ddof = 1 if finite.size > 1 else 0
    return float(np.std(finite, ddof=ddof))


def stats_vector(x: IMUAxisStats, y: IMUAxisStats, z: IMUAxisStats, attr: str) -> Dict[str, Optional[float]]:
    return {
        "x": finite_or_none(getattr(x, attr)),
        "y": finite_or_none(getattr(y, attr)),
        "z": finite_or_none(getattr(z, attr)),
    }


def finite_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if np.isfinite(numeric) else None


def rms_from_vector(values: Dict[str, Optional[float]]) -> Optional[float]:
    finite = [float(value) for value in values.values() if value is not None and np.isfinite(value)]
    if not finite:
        return None
    return float(np.sqrt(np.mean(np.asarray(finite) ** 2)))


def gravity_arrays(run: IMURun) -> Optional[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    if run.gravity_x is None or run.gravity_y is None or run.gravity_z is None:
        return None
    return run.gravity_x, run.gravity_y, run.gravity_z


def gravity_mean_vector(run: IMURun) -> np.ndarray:
    gravity = gravity_arrays(run)
    if gravity is None:
        return np.array([np.nan, np.nan, np.nan])
    return np.array([axis_stats(axis).mean for axis in gravity])


def phone_flatness_section(run: IMURun) -> Dict[str, Any]:
    gravity = gravity_arrays(run)
    if gravity is None:
        return {
            "gravity_mean_g": nullable_vector_dict(np.array([np.nan, np.nan, np.nan])),
            "gravity_norm_mean_g": None,
            "gravity_norm_std_g": None,
            "estimated_tilt_from_flat_deg": None,
        }
    gx, gy, gz = gravity
    gravity_mean = gravity_mean_vector(run)
    gravity_norm = np.sqrt(gx**2 + gy**2 + gz**2)
    return {
        "gravity_mean_g": vector_dict(gravity_mean),
        "gravity_norm_mean_g": float(np.mean(gravity_norm)),
        "gravity_norm_std_g": sample_std(gravity_norm),
        "estimated_tilt_from_flat_deg": tilt_from_gravity_mean_deg(gravity_mean),
    }


def tilt_from_gravity_mean_deg(gravity_mean: np.ndarray) -> Optional[float]:
    if not np.all(np.isfinite(gravity_mean)):
        return None
    horizontal = float(np.hypot(gravity_mean[0], gravity_mean[1]))
    vertical = abs(float(gravity_mean[2]))
    return float(np.degrees(np.arctan2(horizontal, vertical)))


def attitude_drift_section(run: IMURun) -> Dict[str, Optional[float]]:
    roll_delta = attitude_delta_deg(run.roll)
    pitch_delta = attitude_delta_deg(run.pitch)
    yaw_delta = attitude_delta_deg(run.yaw)
    minutes = duration_minutes(run_duration_s(run))
    return {
        "roll_final_minus_initial_deg": roll_delta,
        "pitch_final_minus_initial_deg": pitch_delta,
        "yaw_final_minus_initial_deg": yaw_delta,
        "yaw_drift_deg_per_min": (
            yaw_delta / minutes if yaw_delta is not None and minutes is not None else None
        ),
    }


def attitude_delta_deg(values: Optional[np.ndarray]) -> Optional[float]:
    if values is None:
        return None
    finite = values[np.isfinite(values)]
    if finite.size < 2:
        return None
    unwrapped = np.unwrap(finite)
    return float(np.degrees(unwrapped[-1] - unwrapped[0]))


def gyro_integrated_yaw_drift_section(run: IMURun, gyro_bias_z: float) -> Dict[str, Optional[float]]:
    minutes = duration_minutes(run_duration_s(run))
    raw = integrate_rate(run.t, run.gyro_z)
    corrected = integrate_rate(run.t, run.gyro_z - gyro_bias_z)
    raw_deg = float(np.degrees(raw[-1])) if raw.size else None
    corrected_deg = float(np.degrees(corrected[-1])) if corrected.size else None
    return {
        "raw_final_yaw_change_deg": raw_deg,
        "raw_yaw_drift_deg_per_min": raw_deg / minutes if raw_deg is not None and minutes else None,
        "bias_corrected_final_yaw_change_deg": corrected_deg,
        "bias_corrected_yaw_drift_deg_per_min": (
            corrected_deg / minutes if corrected_deg is not None and minutes else None
        ),
    }


def static_flat_warnings(
    run: IMURun,
    characterization: StaticCharacterization,
) -> List[str]:
    warnings = ["Fused accel near +/-1 g is interpreted as gravity, not accelerometer bias."]
    if not characterization.user_accel_available:
        warnings.append("user_accel columns are missing; user acceleration bias/noise cannot be computed.")
    if gravity_arrays(run) is None:
        warnings.append("gravity_x/y/z columns are missing; phone flatness cannot be computed from gravity.")
    if run.roll is None or run.pitch is None or run.yaw is None:
        warnings.append("roll/pitch/yaw columns are missing; attitude drift cannot be computed.")
    if run_duration_s(run) < 600.0:
        warnings.append("Static_flat recording is shorter than 10 minutes; Allan estimates may be weak.")
    if is_irregular_sampling(run.t, run.sample_interval_s):
        warnings.append("Irregular sampling rate detected.")
    if run.mag_accuracy is None:
        warnings.append("Magnetometer accuracy is missing.")
    return warnings


def is_irregular_sampling(t: np.ndarray, sample_interval_s: float) -> bool:
    dt = np.diff(t)
    if dt.size < 2 or sample_interval_s <= 0:
        return False
    return bool(np.std(dt) > 0.1 * sample_interval_s)


def user_accel_arrays(run: IMURun) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return run.user_accel_x, run.user_accel_y, run.user_accel_z  # type: ignore[return-value]


def fused_accel_arrays(run: IMURun) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return run.accel_x, run.accel_y, run.accel_z


def allan_points_to_dicts(points: Sequence[AllanPoint]) -> List[Dict[str, float]]:
    return [asdict(point) for point in points]


def gyro_bias_instability_deg_per_hour(points: Sequence[AllanPoint]) -> float:
    return estimate_bias_instability(points) * 180.0 / np.pi * 3600.0


def nullable_vector_dict(values: np.ndarray) -> Dict[str, Optional[float]]:
    return {
        "x": finite_or_none(values[0]),
        "y": finite_or_none(values[1]),
        "z": finite_or_none(values[2]),
    }


def fill_axis_dict(values: Dict[str, float]) -> Dict[str, Optional[float]]:
    return {axis: finite_or_none(values.get(axis)) for axis in ("x", "y", "z")}


def dominant_axis_name(values: np.ndarray) -> Optional[str]:
    if not np.any(np.isfinite(values)):
        return None
    return ("x", "y", "z")[int(np.nanargmax(np.abs(values)))]


def axis_index_for_name(axis_name: Optional[str]) -> Optional[int]:
    if axis_name not in {"x", "y", "z"}:
        return None
    return {"x": 0, "y": 1, "z": 2}[axis_name]


def orientation_expected_axis_sign(orientation: str) -> tuple[Optional[str], Optional[int]]:
    mapping = {
        "x_up": ("x", 1),
        "x_down": ("x", -1),
        "y_up": ("y", 1),
        "y_down": ("y", -1),
        "z_up": ("z", 1),
        "z_down": ("z", -1),
    }
    return mapping.get(canonical_orientation(orientation), (None, None))


def cross_axis_magnitude(values: np.ndarray, axis_index: Optional[int]) -> Optional[float]:
    if axis_index is None or not np.all(np.isfinite(values)):
        return None
    mask = np.ones(3, dtype=bool)
    mask[axis_index] = False
    return float(np.linalg.norm(values[mask]))


def subtract_nullable(value: Optional[float], baseline: Optional[float]) -> Optional[float]:
    if value is None or baseline is None:
        return None
    return float(value - baseline)


def true_rotation_signed_deg(
    spec: TestSpec,
    run: IMURun,
    warnings: List[str],
) -> Optional[float]:
    value = spec.expected_angle_deg
    if value is None:
        for key in ("true_rotation_deg", "expected_angle_deg"):
            if key in run.metadata:
                try:
                    value = float(run.metadata[key])
                    break
                except ValueError:
                    warnings.append(f"{spec.csv_file}: invalid {key} metadata.")
    if value is None:
        return None
    direction = (run.metadata.get("rotation_direction") or "").lower()
    if direction in {"right", "cw", "clockwise"} and value > 0:
        return -value
    if direction in {"left", "ccw", "counterclockwise"} and value < 0:
        return abs(value)
    return value


def rotation_direction_label(true_rotation_deg: Optional[float], run: IMURun) -> Optional[str]:
    metadata_direction = run.metadata.get("rotation_direction")
    if metadata_direction:
        return metadata_direction
    if true_rotation_deg is None:
        return None
    return "left" if true_rotation_deg > 0 else "right" if true_rotation_deg < 0 else "none"


def yaw_wrap_detected(yaw: Optional[np.ndarray]) -> bool:
    if yaw is None:
        return False
    finite = yaw[np.isfinite(yaw)]
    if finite.size < 2:
        return False
    return bool(np.any(np.abs(np.diff(finite)) > np.pi))


def tilt_series_deg(run: IMURun) -> Optional[np.ndarray]:
    gravity = gravity_arrays(run)
    if gravity is None:
        return None
    gx, gy, gz = gravity
    return np.degrees(np.arctan2(np.sqrt(gx**2 + gy**2), np.abs(gz)))


def gravity_z_abs_mean(run: IMURun) -> Optional[float]:
    if run.gravity_z is None:
        return None
    finite = run.gravity_z[np.isfinite(run.gravity_z)]
    return float(np.mean(np.abs(finite))) if finite.size else None


def finite_values(values: Iterable[Optional[float]]) -> List[float]:
    finite = []
    for value in values:
        numeric = finite_or_none(value)
        if numeric is not None:
            finite.append(numeric)
    return finite


def mean_abs(values: Sequence[float]) -> Optional[float]:
    return float(np.mean(np.abs(values))) if values else None


def mean_or_none(values: Sequence[float]) -> Optional[float]:
    return float(np.mean(values)) if values else None


def most_common(values: Sequence[str]) -> Optional[str]:
    counts: Dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return max(counts, key=counts.get) if counts else None


def choose_heading_source(
    coremotion_errors: Sequence[float],
    corrected_gyro_errors: Sequence[float],
) -> tuple[str, str]:
    coremotion_mae = mean_abs(coremotion_errors)
    gyro_mae = mean_abs(corrected_gyro_errors)
    if coremotion_mae is None and gyro_mae is None:
        return "unknown", "Known yaw rotation errors are unavailable."
    if coremotion_mae is not None and (gyro_mae is None or coremotion_mae <= gyro_mae):
        return "coremotion_yaw", "Core Motion yaw had lower or equal known-rotation MAE."
    return "bias_corrected_gyro_integration", "Bias-corrected gyro integration had lower known-rotation MAE."


def known_yaw_group_summary(trials: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Optional[float]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for trial in trials:
        true_rotation = trial.get("true_rotation_deg")
        key = "missing" if true_rotation is None else f"{float(true_rotation):.6g}"
        grouped.setdefault(key, []).append(trial)

    summary: Dict[str, Dict[str, Optional[float]]] = {}
    for key, group in grouped.items():
        coremotion_errors = finite_values([trial.get("coremotion_yaw_error_deg") for trial in group])
        gyro_errors = finite_values([trial.get("gyro_integrated_error_deg") for trial in group])
        corrected_errors = finite_values([trial.get("gyro_bias_corrected_error_deg") for trial in group])
        corrected_deltas = finite_values([trial.get("gyro_bias_corrected_delta_deg") for trial in group])
        coremotion_deltas = finite_values([trial.get("coremotion_yaw_delta_deg") for trial in group])
        gyro_deltas = finite_values([trial.get("gyro_integrated_delta_deg") for trial in group])
        summary[key] = {
            "trial_count": len(group),
            "mean_coremotion_yaw_delta_deg": mean_or_none(coremotion_deltas),
            "mean_gyro_integrated_delta_deg": mean_or_none(gyro_deltas),
            "mean_gyro_bias_corrected_delta_deg": mean_or_none(corrected_deltas),
            "coremotion_yaw_mae_deg": mean_abs(coremotion_errors),
            "coremotion_yaw_bias_deg": mean_or_none(coremotion_errors),
            "gyro_integrated_mae_deg": mean_abs(gyro_errors),
            "gyro_integrated_bias_deg": mean_or_none(gyro_errors),
            "gyro_bias_corrected_mae_deg": mean_abs(corrected_errors),
            "gyro_bias_corrected_bias_deg": mean_or_none(corrected_errors),
        }
    return summary


def static_after_motion_masks(run: IMURun) -> tuple[np.ndarray, np.ndarray, str]:
    metadata = run.metadata
    before_start = metadata_float(metadata, "before_static_start_s")
    before_end = metadata_float(metadata, "before_static_end_s")
    after_start = metadata_float(metadata, "after_static_start_s")
    after_end = metadata_float(metadata, "after_static_end_s")
    if None not in (before_start, before_end, after_start, after_end):
        return (
            (run.t >= before_start) & (run.t <= before_end),
            (run.t >= after_start) & (run.t <= after_end),
            "",
        )

    n = run.t.size
    window = max(3, int(round(5.0 / run.sample_interval_s)))
    window = min(window, max(3, n // 5))
    before = np.zeros(n, dtype=bool)
    after = np.zeros(n, dtype=bool)
    before[:window] = True
    after[-window:] = True
    return before, after, "Missing explicit segment metadata; used first/last static windows."


def metadata_float(metadata: Dict[str, str], key: str) -> Optional[float]:
    try:
        return float(metadata[key])
    except (KeyError, TypeError, ValueError):
        return None


def gyro_mean_for_mask(run: IMURun, mask: np.ndarray) -> np.ndarray:
    return np.array([
        axis_stats(run.gyro_x[mask]).mean,
        axis_stats(run.gyro_y[mask]).mean,
        axis_stats(run.gyro_z[mask]).mean,
    ])


def gyro_std_for_mask(run: IMURun, mask: np.ndarray, bias: np.ndarray) -> np.ndarray:
    return np.array([
        sample_std(run.gyro_x[mask] - bias[0]) or np.nan,
        sample_std(run.gyro_y[mask] - bias[1]) or np.nan,
        sample_std(run.gyro_z[mask] - bias[2]) or np.nan,
    ])


def user_accel_mean_for_mask(run: IMURun, mask: np.ndarray) -> np.ndarray:
    if not has_user_accel(run):
        return np.array([np.nan, np.nan, np.nan])
    return np.array([
        axis_stats(run.user_accel_x[mask]).mean,  # type: ignore[index]
        axis_stats(run.user_accel_y[mask]).mean,  # type: ignore[index]
        axis_stats(run.user_accel_z[mask]).mean,  # type: ignore[index]
    ])


def duration_for_mask(run: IMURun, mask: np.ndarray) -> Optional[float]:
    times = run.t[mask]
    if times.size < 2:
        return None
    return float(times[-1] - times[0])


def duration_minutes_for_mask(run: IMURun, mask: np.ndarray) -> float:
    duration = duration_for_mask(run, mask)
    return duration / 60.0 if duration and duration > 0 else 0.0


def yaw_drift_for_mask(run: IMURun, mask: np.ndarray) -> Optional[float]:
    if run.yaw is None:
        return None
    minutes = duration_minutes_for_mask(run, mask)
    if minutes <= 0:
        return None
    return attitude_delta_deg(run.yaw[mask]) / minutes  # type: ignore[operator]


def heading_series(run: IMURun) -> np.ndarray:
    if run.yaw is not None:
        return np.unwrap(run.yaw)
    return integrate_rate(run.t, run.gyro_z)


def detect_steps_simple(
    t: np.ndarray,
    signal: np.ndarray,
    min_step_gap_s: float = 0.35,
    prominence: float = 0.03,
) -> np.ndarray:
    if t.size < 3:
        return np.array([], dtype=int)
    centered = signal - moving_average(signal, max(3, int(round(0.75 / np.median(np.diff(t))))))
    threshold = float(np.mean(centered) + 0.25 * np.std(centered) + prominence)
    min_gap = max(1, int(round(min_step_gap_s / np.median(np.diff(t)))))
    peaks = []
    last_peak = -min_gap
    for index in range(1, centered.size - 1):
        if index - last_peak < min_gap:
            continue
        if centered[index] <= threshold:
            continue
        if centered[index] >= centered[index - 1] and centered[index] > centered[index + 1]:
            peaks.append(index)
            last_peak = index
    return np.asarray(peaks, dtype=int)


def detect_turns_from_heading(
    t: np.ndarray,
    heading: np.ndarray,
    rate_threshold_deg_s: float = 20.0,
    min_angle_deg: float = 30.0,
    min_duration_s: float = 0.2,
) -> List[Dict[str, float]]:
    if t.size < 2:
        return []
    rate = np.gradient(heading, t)
    active = np.abs(np.degrees(rate)) >= rate_threshold_deg_s
    turns = []
    start = None
    for index, is_active in enumerate(active):
        if is_active and start is None:
            start = index
        elif not is_active and start is not None:
            maybe_add_turn(turns, t, heading, rate, start, index - 1, min_angle_deg, min_duration_s)
            start = None
    if start is not None:
        maybe_add_turn(turns, t, heading, rate, start, t.size - 1, min_angle_deg, min_duration_s)
    return turns


def maybe_add_turn(
    turns: List[Dict[str, float]],
    t: np.ndarray,
    heading: np.ndarray,
    rate: np.ndarray,
    start: int,
    end: int,
    min_angle_deg: float,
    min_duration_s: float,
) -> None:
    duration = float(t[end] - t[start])
    delta_deg = float(np.degrees(heading[end] - heading[start]))
    if duration < min_duration_s or abs(delta_deg) < min_angle_deg:
        return
    turns.append(
        {
            "start_time_s": float(t[start]),
            "end_time_s": float(t[end]),
            "duration_s": duration,
            "delta_deg": delta_deg,
            "peak_rate_deg_s": float(np.degrees(np.max(np.abs(rate[start : end + 1])))),
        }
    )


def rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return values.astype(float)
    if values.ndim == 1:
        kernel = np.ones(window) / window
        return np.convolve(values, kernel, mode="same")
    columns = [rolling_mean(values[:, index], window) for index in range(values.shape[1])]
    return np.column_stack(columns)


def moving_average(values: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return values.astype(float)
    window = min(window, values.size)
    kernel = np.ones(window) / window
    return np.convolve(values, kernel, mode="same")


def first_hold_index(
    values: np.ndarray,
    threshold: float,
    hold_samples: int,
    start_index: int,
) -> Optional[int]:
    for index in range(start_index, max(start_index, values.size - hold_samples + 1)):
        if np.all(values[index : index + hold_samples] <= threshold):
            return index
    return None


def gyro_axis(run: IMURun, axis: str) -> np.ndarray:
    axis = axis.lower().strip()
    if axis in {"x", "roll"}:
        return run.gyro_x
    if axis in {"y", "pitch"}:
        return run.gyro_y
    if axis in {"z", "yaw", ""}:
        return run.gyro_z
    raise ValueError(f"Unknown gyro axis: {axis}")


def canonical_test_type(value: str) -> str:
    normalized = normalize_label(value)
    aliases = {
        "static": LONG_STATIC_REST,
        "static_rest": LONG_STATIC_REST,
        "long_static": LONG_STATIC_REST,
        "long_static_rest": LONG_STATIC_REST,
        "static_flat": LONG_STATIC_REST,
        "six_orientation": STATIC_6_ORIENTATION,
        "six_orientations": STATIC_6_ORIENTATION,
        "static_6_orientation": STATIC_6_ORIENTATION,
        "static_6_orientations": STATIC_6_ORIENTATION,
        "known_angle": KNOWN_ANGLE_ROTATION,
        "known_angle_rotation": KNOWN_ANGLE_ROTATION,
        "known_yaw_rotation": KNOWN_ANGLE_ROTATION,
        "known_motion": KNOWN_ANGLE_ROTATION,
        "rotation": KNOWN_ANGLE_ROTATION,
        "integration": LONG_STATIC_REST,
        "integration_drift": LONG_STATIC_REST,
        "bias_settling": BIAS_SETTLING,
        "static_after_motion": BIAS_SETTLING,
        "static_after_motion_bias_settling": BIAS_SETTLING,
        "straight": STRAIGHT_LINE_WALK,
        "straight_line": STRAIGHT_LINE_WALK,
        "straight_line_walk": STRAIGHT_LINE_WALK,
        "known_path": KNOWN_PATH_TURNS,
        "known_path_turns": KNOWN_PATH_TURNS,
        "l_shape": KNOWN_PATH_TURNS,
        "l_walk": KNOWN_PATH_TURNS,
        "rectangle": KNOWN_PATH_TURNS,
        "closed_loop": KNOWN_PATH_TURNS,
        "out_and_back": OUT_AND_BACK,
        "out_back": OUT_AND_BACK,
        "out_and_back_hallway": OUT_AND_BACK,
        "carrying_mode": CARRYING_MODE_SENSITIVITY,
        "phone_carrying_mode": CARRYING_MODE_SENSITIVITY,
        "carrying_mode_sensitivity": CARRYING_MODE_SENSITIVITY,
    }
    return aliases.get(normalized, normalized)


def canonical_orientation(value: str) -> str:
    normalized = normalize_label(value)
    aliases = {
        "+x": "x_up",
        "xup": "x_up",
        "x_up": "x_up",
        "positive_x": "x_up",
        "-x": "x_down",
        "xdown": "x_down",
        "x_down": "x_down",
        "negative_x": "x_down",
        "+y": "y_up",
        "yup": "y_up",
        "y_up": "y_up",
        "positive_y": "y_up",
        "-y": "y_down",
        "ydown": "y_down",
        "y_down": "y_down",
        "negative_y": "y_down",
        "+z": "z_up",
        "zup": "z_up",
        "z_up": "z_up",
        "face_up": "z_up",
        "screen_up": "z_up",
        "positive_z": "z_up",
        "-z": "z_down",
        "zdown": "z_down",
        "z_down": "z_down",
        "face_down": "z_down",
        "screen_down": "z_down",
        "negative_z": "z_down",
    }
    return aliases.get(normalized, normalized)


def normalize_label(value: str) -> str:
    return (
        value.strip()
        .lower()
        .replace("-", "_")
        .replace("/", "_")
        .replace(" ", "_")
        .replace("__", "_")
    )


def vector_dict(values: np.ndarray) -> Dict[str, float]:
    return {"x": float(values[0]), "y": float(values[1]), "z": float(values[2])}


def safe_ratio(numerator: Optional[float], denominator: Optional[float]) -> float:
    if numerator is None or denominator is None or denominator == 0:
        return float("nan")
    return float(numerator / denominator)


def mean_metric(results: Sequence[Dict[str, Any]], key: str) -> Optional[float]:
    values = [result.get(key) for result in results]
    finite = [float(value) for value in values if value is not None and np.isfinite(value)]
    if not finite:
        return None
    return float(np.mean(finite))


def results_to_json(results: Any) -> str:
    return json.dumps(make_json_safe(results), indent=2, sort_keys=True)


def make_json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): make_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [make_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [make_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return make_json_safe(value.tolist())
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.generic):
        return make_json_safe(value.item())
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    return value


def format_result_summary(result: Dict[str, Any]) -> str:
    label = result.get("label") or result.get("group") or result.get("test_type")
    lines = [f"{result.get('test_type', 'unknown')}: {label}"]
    if "static_flat" in result:
        static_flat = result["static_flat"]
        lines.append(f"  duration_s: {static_flat['duration_s']:.6f}")
        lines.append(f"  samples: {static_flat['samples']}")
        user = static_flat["user_accel_bias_g"]
        fused = static_flat["fused_accel_mean_g"]
        lines.append(
            "  user_accel_bias_g: "
            f"x={format_optional(user['x'])}, y={format_optional(user['y'])}, z={format_optional(user['z'])}"
        )
        lines.append(
            "  fused_accel_mean_g: "
            f"x={format_optional(fused['x'])}, y={format_optional(fused['y'])}, z={format_optional(fused['z'])}"
        )
        return "\n".join(lines)
    if "known_yaw_rotation" in result:
        summary = result["known_yaw_rotation"]["summary"]
        lines.append(f"  trial_count: {summary['trial_count']}")
        lines.append(f"  coremotion_yaw_mae_deg: {format_optional(summary['coremotion_yaw_mae_deg'])}")
        lines.append(f"  gyro_bias_corrected_mae_deg: {format_optional(summary['gyro_bias_corrected_mae_deg'])}")
        lines.append(f"  preferred_heading: {summary['recommendation_preferred_heading_source']}")
        return "\n".join(lines)
    if "static_after_motion" in result:
        summary = result["static_after_motion"]["summary"]
        lines.append(f"  trial_count: {summary['trial_count']}")
        lines.append(
            "  mean_after_motion_yaw_drift_deg_per_min: "
            f"{format_optional(summary['mean_after_motion_yaw_drift_deg_per_min'])}"
        )
        return "\n".join(lines)
    if "six_orientation_accel" in result:
        section = result["six_orientation_accel"]
        lines.append(f"  pose_count: {len(section['poses'])}")
        missing = section.get("orientation_label_warnings", [])
        lines.append(f"  warnings: {len(missing)}")
        return "\n".join(lines)
    for key in (
        "duration_s",
        "sample_rate_hz",
        "step_count",
        "estimated_path_length_m",
        "estimated_displacement_m",
        "closure_error_m",
        "integrated_gyro_angle_deg",
        "absolute_angle_error_deg",
        "settling_time_after_motion_s",
    ):
        value = result.get(key)
        if value is not None:
            lines.append(f"  {key}: {value:.6f}" if isinstance(value, float) else f"  {key}: {value}")
    if "orientation_count" in result:
        lines.append(f"  orientation_count: {result['orientation_count']}")
        lines.append(f"  missing_orientations: {', '.join(result.get('missing_orientations', [])) or 'none'}")
    if "mode_count" in result:
        lines.append(f"  mode_count: {result['mode_count']}")
    if "user_accel_mean_g" in result:
        user = result["user_accel_mean_g"]
        fused = result["fused_accel_mean_g"]
        lines.append(
            "  user_accel_mean_g: "
            f"x={user['x']:.6f}, y={user['y']:.6f}, z={user['z']:.6f}"
        )
        lines.append(
            "  fused_accel_mean_g: "
            f"x={fused['x']:.6f}, y={fused['y']:.6f}, z={fused['z']:.6f}"
        )
    return "\n".join(lines)


def format_optional(value: Optional[float]) -> str:
    return "null" if value is None else f"{value:.6f}"


def _metadata_sample_interval(metadata: Dict[str, str]) -> Optional[float]:
    value = metadata.get("sample_interval")
    if value is None:
        return None
    try:
        sample_interval = float(value)
    except ValueError:
        return None
    return sample_interval if sample_interval > 0 else None


def _concat_optional(series_list: Sequence[Optional[np.ndarray]]) -> Optional[np.ndarray]:
    if any(series is None for series in series_list):
        return None
    return np.concatenate([series for series in series_list if series is not None])


def _read_csv_rows(csv_path: Path) -> List[Dict[str, str]]:
    with csv_path.open("r", encoding="utf-8", newline="") as file:
        data_lines = (line for line in file if not line.startswith("#"))
        reader = csv.DictReader(data_lines)
        if reader.fieldnames is None:
            raise ValueError(f"CSV file has no header row: {csv_path}")
        reader.fieldnames = [field.strip() for field in reader.fieldnames]
        return [
            {key.strip(): value for key, value in row.items() if key is not None}
            for row in reader
        ]


def _required_numeric(rows: Sequence[Dict[str, str]], *candidates: str) -> np.ndarray:
    series = _optional_numeric(rows, *candidates)
    if series is None:
        raise KeyError(
            f"Could not find any of these columns in the CSV: {', '.join(candidates)}"
        )
    return series


def _optional_numeric(rows: Sequence[Dict[str, str]], *candidates: str) -> Optional[np.ndarray]:
    if not rows:
        raise ValueError("CSV file has no data rows.")
    columns = set().union(*(row.keys() for row in rows))
    for column in candidates:
        if column in columns:
            return np.asarray([_to_float(row.get(column, "")) for row in rows], dtype=float)
    return None


def _to_float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run static IMU characterization on one or more CSV files."
    )
    parser.add_argument("csv_files", nargs="+", help="One or more static-rest IMU CSV files")
    parser.add_argument("--json", dest="json_file", help="Optional path to write JSON results")
    args = parser.parse_args()

    runs = [load_imu_csv(Path(csv_file)) for csv_file in args.csv_files]
    result = analyze_long_static_rest(merge_imu_runs(runs), label="merged_static")
    print(format_result_summary(result))

    if args.json_file:
        Path(args.json_file).write_text(results_to_json([result]), encoding="utf-8")
        print(f"Wrote JSON: {args.json_file}")


if __name__ == "__main__":
    main()
