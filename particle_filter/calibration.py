from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

from .antenna import apply_antenna_policy, candidate_policies, score_policy
from .filter import run_particle_filter
from .loaders import fit_rigid_transform, load_arkit_trajectory, load_rfid_reads, resolve_run_paths
from .metrics import path_length, trajectory_metrics
from .models import ARKitTrajectory, AntennaPolicy, CalibrationResult, MotionData, PFConfig, TagMap
from .pdr_adapter import imu_only_trajectory, load_motion_steps
from .rfid_pipeline import RFID_MODE_RAW


@dataclass(frozen=True)
class LoadedRun:
    name: str
    motion: MotionData
    reads: pd.DataFrame
    arkit: ARKitTrajectory


def load_run(
    folder: Path,
    tag_map: TagMap,
    base_step_length_m: float = 0.7,
    policy: AntennaPolicy | None = None,
    imu_characterization_path: Path | None = None,
    rfid_mode: str = RFID_MODE_RAW,
) -> LoadedRun:
    paths = resolve_run_paths(folder)
    motion = load_motion_steps(
        paths.imu_csv,
        imu_characterization_path=imu_characterization_path,
        base_step_length_m=base_step_length_m,
    )
    reads = load_rfid_reads(paths.rfid_csv, tag_map, mode=rfid_mode)
    arkit = load_arkit_trajectory(paths.arkit_csv, align_start_facing_y=False)
    if policy is not None:
        arkit, _ = align_arkit_with_rfid_peaks(arkit, reads, tag_map, policy)
    return LoadedRun(name=paths.folder.name, motion=motion, reads=reads, arkit=arkit)


def _interpolate_local_arkit(arkit: ARKitTrajectory, times: np.ndarray) -> np.ndarray:
    x = np.interp(times, arkit.unix_t, arkit.points_local[:, 0])
    y = np.interp(times, arkit.unix_t, arkit.points_local[:, 1])
    return np.column_stack([x, y])


def _peak_correspondences(
    reads: pd.DataFrame,
    arkit: ARKitTrajectory,
    tag_map: TagMap,
    policy: AntennaPolicy,
    start_end_weight: int = 5,
) -> tuple[np.ndarray, np.ndarray, Dict[str, float]]:
    filtered = apply_antenna_policy(reads, policy)
    positions = tag_map.positions_by_epc()
    peak_times = []
    target_points = []
    for epc, group in filtered.groupby("epc"):
        if epc not in positions:
            continue
        if group["rssi"].notna().any():
            peak_row = group.loc[group["rssi"].idxmax()]
        else:
            peak_row = group.iloc[len(group) // 2]
        peak_time = float(peak_row["timestamp_s"])
        if peak_time < arkit.unix_t[0] or peak_time > arkit.unix_t[-1]:
            continue
        peak_times.append(peak_time)
        target_points.append(positions[str(epc)])

    if len(peak_times) < 2:
        raise ValueError("At least two RFID tag peaks are required to align ARKit to the tag map.")

    source_points = _interpolate_local_arkit(arkit, np.asarray(peak_times, dtype=float))
    target_array = np.vstack(target_points)

    for _ in range(start_end_weight):
        source_points = np.vstack([arkit.points_local[0], source_points, arkit.points_local[-1]])
        target_array = np.vstack([[0.0, 0.0], target_array, [0.0, 0.0]])

    diagnostics = {
        "alignment_correspondences": float(len(peak_times)),
        "alignment_start_end_weight": float(start_end_weight),
    }
    return source_points, target_array, diagnostics


def align_arkit_with_rfid_peaks(
    raw_arkit: ARKitTrajectory,
    reads: pd.DataFrame,
    tag_map: TagMap,
    policy: AntennaPolicy,
) -> tuple[ARKitTrajectory, Dict[str, float]]:
    source_points, target_points, diagnostics = _peak_correspondences(reads, raw_arkit, tag_map, policy)
    rotation_rad, translation_xy, alignment_rmse_m = fit_rigid_transform(source_points, target_points)
    aligned = ARKitTrajectory(
        unix_t=raw_arkit.unix_t,
        points_local=raw_arkit.points_local,
        points_map=load_arkit_trajectory_from_arrays(raw_arkit, rotation_rad, translation_xy),
        rotation_rad=rotation_rad,
        tracking_state=raw_arkit.tracking_state,
        translation_xy=translation_xy,
    )
    diagnostics.update(
        {
            "alignment_rmse_m": alignment_rmse_m,
            "arkit_rotation_rad": rotation_rad,
            "arkit_translation_x_m": float(translation_xy[0]),
            "arkit_translation_y_m": float(translation_xy[1]),
        }
    )
    return aligned, diagnostics


def load_arkit_trajectory_from_arrays(raw_arkit: ARKitTrajectory, rotation_rad: float, translation_xy: np.ndarray) -> np.ndarray:
    c = float(np.cos(rotation_rad))
    s = float(np.sin(rotation_rad))
    points = raw_arkit.points_local
    return np.column_stack(
        [
            c * points[:, 0] - s * points[:, 1] + translation_xy[0],
            s * points[:, 0] + c * points[:, 1] + translation_xy[1],
        ]
    )


def _safe_metrics(times: np.ndarray, points: np.ndarray, arkit: ARKitTrajectory) -> Dict[str, float]:
    try:
        return trajectory_metrics(times, points, arkit)
    except ValueError:
        return {
            "paired_points": 0.0,
            "duration_s": 0.0,
            "mean_error_m": float("inf"),
            "median_error_m": float("inf"),
            "rmse_m": float("inf"),
            "p95_error_m": float("inf"),
            "max_error_m": float("inf"),
            "endpoint_error_m": float("inf"),
            "closed_loop_return_error_m": float("inf"),
            "arkit_path_length_m": path_length(arkit.points_map),
            "estimate_path_length_m": path_length(points),
            "path_length_ratio_estimate_over_arkit": float("nan"),
        }


def _initial_step_scale(motion: MotionData, arkit: ARKitTrajectory) -> float:
    if motion.step_count <= 0:
        return 1.0
    arkit_len = path_length(arkit.points_map)
    pdr_len = motion.step_count * motion.base_step_length_m
    if pdr_len <= 0:
        return 1.0
    return float(np.clip(arkit_len / pdr_len, 0.3, 2.5))


def _candidate_configs(base_config: PFConfig, motion: MotionData, arkit: ARKitTrajectory) -> List[PFConfig]:
    step_scale = _initial_step_scale(motion, arkit)
    step_scales = sorted({round(float(np.clip(step_scale * factor, 0.3, 2.5)), 5) for factor in (0.85, 1.0, 1.15)})
    anchor_radii = (1.25, 2.0, 3.0)
    rfid_weights = (0.01, 0.03, 0.06)
    heading_signs = (1.0, -1.0)
    heading_offsets = (-0.4, 0.0, 0.4)

    configs: List[PFConfig] = []
    for scale in step_scales:
        for radius in anchor_radii:
            for rfid_weight in rfid_weights:
                for heading_sign in heading_signs:
                    for heading_offset in heading_offsets:
                        configs.append(
                            PFConfig(
                                particle_count=base_config.particle_count,
                                seed=base_config.seed,
                                base_step_length_m=base_config.base_step_length_m,
                                step_scale_mean=scale,
                                step_scale_std=base_config.step_scale_std,
                                step_scale_process_std=base_config.step_scale_process_std,
                                heading_sign=heading_sign,
                                heading_offset_mean_rad=heading_offset,
                                heading_offset_std_rad=base_config.heading_offset_std_rad,
                                heading_noise_std_rad=base_config.heading_noise_std_rad,
                                position_init_std_m=base_config.position_init_std_m,
                                step_noise_std_m=base_config.step_noise_std_m,
                                anchor_radius_m=radius,
                                rfid_weight=rfid_weight,
                                resample_fraction=base_config.resample_fraction,
                                rfid_measurement_model=base_config.rfid_measurement_model,
                                rssi_weak_dbm=base_config.rssi_weak_dbm,
                                rssi_strong_dbm=base_config.rssi_strong_dbm,
                                rssi_min_weight=base_config.rssi_min_weight,
                                rssi_weight_power=base_config.rssi_weight_power,
                                phase_delta_scale=base_config.phase_delta_scale,
                                phase_delta_sigma=base_config.phase_delta_sigma,
                                phase_delta_max_abs=base_config.phase_delta_max_abs,
                                phase_expected_deadband_m=base_config.phase_expected_deadband_m,
                            )
                        )
    return configs


def _score_candidate(metrics: Dict[str, float], policy: AntennaPolicy) -> float:
    timing_penalty = float(policy.diagnostics.get("median_pass_timing_error_s", 0.0))
    if not np.isfinite(timing_penalty):
        timing_penalty = 60.0
    coverage_bonus = float(policy.diagnostics.get("known_epc_count", 0.0))
    return float(metrics["rmse_m"] + 0.15 * metrics["closed_loop_return_error_m"] + 0.005 * timing_penalty - 0.01 * coverage_bonus)


def calibrate(
    calibration_dir: Path,
    tag_map: TagMap,
    particle_count: int = 800,
    seed: int = 7,
    imu_characterization_path: Path | None = None,
    rfid_mode: str = RFID_MODE_RAW,
    rfid_measurement_model: str = "rssi_anchor",
) -> CalibrationResult:
    run = load_run(calibration_dir, tag_map, imu_characterization_path=imu_characterization_path, rfid_mode=rfid_mode)
    base_config = PFConfig(particle_count=particle_count, seed=seed, rfid_measurement_model=rfid_measurement_model)
    policies = candidate_policies(run.reads)
    configs = _candidate_configs(base_config, run.motion, run.arkit)

    best_result = None
    best_score = float("inf")
    candidate_count = 0

    for policy in policies:
        try:
            aligned_arkit, alignment_diagnostics = align_arkit_with_rfid_peaks(run.arkit, run.reads, tag_map, policy)
        except ValueError:
            continue
        policy_diagnostics = score_policy(run.reads, policy, aligned_arkit, tag_map)
        policy_diagnostics.update(alignment_diagnostics)
        policy = AntennaPolicy(
            mode=policy.mode,
            antenna=policy.antenna,
            epc_to_antenna=policy.epc_to_antenna,
            diagnostics=policy_diagnostics,
        )
        rfid_time_offset_s = float(policy_diagnostics.get("median_pass_time_offset_s", 0.0))
        for config in configs:
            config = replace(config, rfid_time_offset_s=rfid_time_offset_s)
            candidate_count += 1
            result = run_particle_filter(run.motion, run.reads, tag_map, policy, config)
            metrics = _safe_metrics(result.times_unix, result.points, aligned_arkit)
            score = _score_candidate(metrics, policy)
            if score < best_score:
                best_score = score
                best_result = (policy, config, metrics)

    if best_result is None:
        raise RuntimeError("Calibration did not produce any candidate result.")

    policy, config, metrics = best_result
    metrics = dict(metrics)
    metrics["score"] = float(best_score)
    return CalibrationResult(
        calibration_dir=str(Path(calibration_dir)),
        policy=policy,
        pf_config=config,
        arkit_rotation_rad=float(policy.diagnostics.get("arkit_rotation_rad", 0.0)),
        metrics=metrics,
        candidate_count=candidate_count,
    )


def save_calibration(calibration: CalibrationResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(calibration.to_json_dict(), indent=2, sort_keys=True), encoding="utf-8")


def load_calibration(path: Path) -> CalibrationResult:
    return CalibrationResult.from_json_dict(json.loads(path.read_text(encoding="utf-8")))


def evaluate_run(
    run_dir: Path,
    tag_map: TagMap,
    calibration: CalibrationResult,
    imu_characterization_path: Path | None = None,
    rfid_mode: str = RFID_MODE_RAW,
    trace_particles: bool = False,
) -> Dict[str, object]:
    run = load_run(
        run_dir,
        tag_map,
        base_step_length_m=calibration.pf_config.base_step_length_m,
        policy=calibration.policy,
        imu_characterization_path=imu_characterization_path,
        rfid_mode=rfid_mode,
    )
    baseline_times, baseline_points = imu_only_trajectory(
        run.motion,
        calibration.pf_config.step_scale_mean,
        heading_offset_rad=calibration.pf_config.heading_offset_mean_rad,
        heading_sign=calibration.pf_config.heading_sign,
    )
    baseline_metrics = _safe_metrics(baseline_times, baseline_points, run.arkit)

    pf_result = run_particle_filter(
        run.motion,
        run.reads,
        tag_map,
        calibration.policy,
        calibration.pf_config,
        trace_particles=trace_particles,
    )
    pf_metrics = _safe_metrics(pf_result.times_unix, pf_result.points, run.arkit)

    return {
        "run": run,
        "baseline_times": baseline_times,
        "baseline_points": baseline_points,
        "baseline_metrics": baseline_metrics,
        "pf_result": pf_result,
        "pf_metrics": pf_metrics,
    }


def flatten_metrics(run_label: str, method: str, metrics: Dict[str, float], calibration: CalibrationResult, accepted_rfid_count: int = 0) -> Dict[str, object]:
    row: Dict[str, object] = {
        "run": run_label,
        "method": method,
        "selected_antenna_policy": calibration.policy.label,
        "accepted_rfid_count": accepted_rfid_count,
    }
    row.update(metrics)
    return row
