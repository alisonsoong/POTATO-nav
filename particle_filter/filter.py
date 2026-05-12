from __future__ import annotations

import numpy as np
import pandas as pd

from .antenna import apply_antenna_policy
from .models import AntennaPolicy, MotionData, PFConfig, PFResult, TagMap

RFID_MODEL_RSSI = "rssi_anchor"
RFID_MODEL_PHASE = "phase_delta"
RFID_MODEL_COMBINED = "rssi_phase"
RFID_MODELS = (RFID_MODEL_RSSI, RFID_MODEL_PHASE, RFID_MODEL_COMBINED)


def _normalize_weights(weights: np.ndarray) -> np.ndarray:
    total = float(np.sum(weights))
    if not np.isfinite(total) or total <= 0:
        return np.full_like(weights, 1.0 / len(weights), dtype=float)
    return weights / total


def _effective_particle_count(weights: np.ndarray) -> float:
    return float(1.0 / np.sum(weights**2))


def _systematic_resample(rng: np.random.Generator, weights: np.ndarray) -> np.ndarray:
    n = len(weights)
    positions = (rng.random() + np.arange(n)) / n
    cumulative_sum = np.cumsum(weights)
    indexes = np.zeros(n, dtype=int)
    i = 0
    j = 0
    while i < n:
        if positions[i] < cumulative_sum[j]:
            indexes[i] = j
            i += 1
        else:
            j += 1
    return indexes


def _estimate(x: np.ndarray, y: np.ndarray, weights: np.ndarray) -> np.ndarray:
    return np.array([float(np.average(x, weights=weights)), float(np.average(y, weights=weights))], dtype=float)


def _read_float(record: object, name: str, default: float = np.nan) -> float:
    value = getattr(record, name, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _rssi_strength(rssi_dbm: float, config: PFConfig) -> float:
    if not np.isfinite(rssi_dbm):
        return 1.0
    span = max(config.rssi_strong_dbm - config.rssi_weak_dbm, 1e-9)
    normalized = np.clip((rssi_dbm - config.rssi_weak_dbm) / span, 0.0, 1.0)
    shaped = float(normalized ** max(config.rssi_weight_power, 1e-9))
    return float(config.rssi_min_weight + (1.0 - config.rssi_min_weight) * shaped)


def _apply_rfid_update(
    x: np.ndarray,
    y: np.ndarray,
    weights: np.ndarray,
    tag_position: np.ndarray,
    config: PFConfig,
    strength: float = 1.0,
) -> np.ndarray:
    effective_weight = config.rfid_weight * float(np.clip(strength, 0.0, 1.0))
    if config.anchor_radius_m <= 0 or effective_weight <= 0:
        return weights
    dx = x - tag_position[0]
    dy = y - tag_position[1]
    distances = np.sqrt(dx * dx + dy * dy)
    log_likelihood = -0.5 * (distances / config.anchor_radius_m) ** 2
    log_likelihood *= effective_weight
    likelihood = np.exp(log_likelihood - np.max(log_likelihood))
    return _normalize_weights(weights * likelihood)


def _phase_direction(value: float, deadband: float = 1e-9) -> float:
    if value > deadband:
        return 1.0
    if value < -deadband:
        return -1.0
    return 0.0


def _apply_phase_delta_update(
    x: np.ndarray,
    y: np.ndarray,
    weights: np.ndarray,
    tag_position: np.ndarray,
    observed_phase_delta: float,
    previous_distance: np.ndarray,
    config: PFConfig,
    strength: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    effective_weight = config.rfid_weight * float(np.clip(strength, 0.0, 1.0))
    if effective_weight <= 0:
        current_distance = np.sqrt((x - tag_position[0]) ** 2 + (y - tag_position[1]) ** 2)
        return weights, current_distance
    if not np.isfinite(observed_phase_delta) or abs(observed_phase_delta) > config.phase_delta_max_abs:
        current_distance = np.sqrt((x - tag_position[0]) ** 2 + (y - tag_position[1]) ** 2)
        return weights, current_distance

    current_distance = np.sqrt((x - tag_position[0]) ** 2 + (y - tag_position[1]) ** 2)
    predicted_range_delta = previous_distance - current_distance
    expected_phase_delta = predicted_range_delta / max(config.phase_delta_scale, 1e-9)

    observed_sign = _phase_direction(observed_phase_delta)
    predicted_sign = np.where(
        predicted_range_delta > config.phase_expected_deadband_m,
        1.0,
        np.where(predicted_range_delta < -config.phase_expected_deadband_m, -1.0, 0.0),
    )
    sign_penalty = np.where((observed_sign != 0.0) & (predicted_sign != 0.0) & (observed_sign != predicted_sign), 2.0, 0.0)
    residual = (observed_phase_delta - expected_phase_delta) / max(config.phase_delta_sigma, 1e-9)
    log_likelihood = -0.5 * residual**2 - sign_penalty
    log_likelihood *= effective_weight
    likelihood = np.exp(log_likelihood - np.max(log_likelihood))
    return _normalize_weights(weights * likelihood), current_distance


def run_particle_filter(
    motion: MotionData,
    reads: pd.DataFrame,
    tag_map: TagMap,
    policy: AntennaPolicy,
    config: PFConfig,
    trace_particles: bool = False,
    trace_particle_count: int = 40,
) -> PFResult:
    if config.rfid_measurement_model not in RFID_MODELS:
        raise ValueError(f"Unknown RFID measurement model: {config.rfid_measurement_model}")

    rng = np.random.default_rng(config.seed)
    n = int(config.particle_count)
    if n <= 0:
        raise ValueError("particle_count must be positive.")

    x = rng.normal(0.0, config.position_init_std_m, size=n)
    y = rng.normal(0.0, config.position_init_std_m, size=n)
    heading_offset = rng.normal(config.heading_offset_mean_rad, config.heading_offset_std_rad, size=n)
    step_scale = rng.normal(config.step_scale_mean, config.step_scale_std, size=n)
    step_scale = np.clip(step_scale, 0.2, 3.0)
    weights = np.full(n, 1.0 / n, dtype=float)

    filtered_reads = apply_antenna_policy(reads, policy).copy()
    if not filtered_reads.empty:
        filtered_reads["timestamp_s"] = filtered_reads["timestamp_s"] + float(config.rfid_time_offset_s)
    filtered_reads = filtered_reads.sort_values("timestamp_s")
    ignored_rfid_count = int(len(reads) - len(filtered_reads))
    tag_positions = tag_map.positions_by_epc()
    read_records = list(filtered_reads.itertuples(index=False))
    read_index = 0
    accepted_rfid_count = 0
    last_processed_read_time = None
    last_phase_by_key: dict[tuple[str, int], float] = {}
    last_distance_by_key: dict[tuple[str, int], np.ndarray] = {}

    start_time = float(motion.unix_t[0]) if motion.unix_t.size else 0.0
    times = [start_time]
    points = [_estimate(x, y, weights)]
    particle_times = [start_time] if trace_particles else None
    particle_snapshots = [np.column_stack([x, y])] if trace_particles else None

    def process_reads_until(cutoff_s: float) -> None:
        nonlocal read_index, weights, x, y, heading_offset, step_scale, accepted_rfid_count, last_processed_read_time
        while read_index < len(read_records) and float(read_records[read_index].timestamp_s) <= cutoff_s:
            record = read_records[read_index]
            last_processed_read_time = float(record.timestamp_s)
            epc = str(record.epc)
            tag_position = tag_positions.get(epc)
            if tag_position is not None:
                rssi_strength = _rssi_strength(_read_float(record, "rssi"), config)
                updated_this_read = False

                if config.rfid_measurement_model in (RFID_MODEL_RSSI, RFID_MODEL_COMBINED):
                    weights = _apply_rfid_update(x, y, weights, tag_position, config, strength=rssi_strength)
                    updated_this_read = True

                if config.rfid_measurement_model in (RFID_MODEL_PHASE, RFID_MODEL_COMBINED):
                    key = (epc, int(record.antenna))
                    current_phase = _read_float(record, "phase")
                    current_distance = np.sqrt((x - tag_position[0]) ** 2 + (y - tag_position[1]) ** 2)
                    if key in last_phase_by_key and key in last_distance_by_key and np.isfinite(current_phase):
                        observed_delta = current_phase - last_phase_by_key[key]
                        weights, current_distance = _apply_phase_delta_update(
                            x,
                            y,
                            weights,
                            tag_position,
                            observed_delta,
                            last_distance_by_key[key],
                            config,
                            strength=rssi_strength,
                        )
                        updated_this_read = True
                    if np.isfinite(current_phase):
                        last_phase_by_key[key] = current_phase
                        last_distance_by_key[key] = current_distance

                if updated_this_read:
                    accepted_rfid_count += 1

                if _effective_particle_count(weights) < config.resample_fraction * n:
                    indexes = _systematic_resample(rng, weights)
                    x = x[indexes]
                    y = y[indexes]
                    heading_offset = heading_offset[indexes]
                    step_scale = step_scale[indexes]
                    weights = np.full(n, 1.0 / n, dtype=float)
                    for key, distances in list(last_distance_by_key.items()):
                        last_distance_by_key[key] = distances[indexes]
            read_index += 1

    for step_time, step_heading in zip(motion.step_times_unix, motion.step_headings_rad):
        process_reads_until(float(step_time))

        noisy_heading = config.heading_sign * step_heading + heading_offset + rng.normal(0.0, config.heading_noise_std_rad, size=n)
        noisy_step = motion.base_step_length_m * step_scale + rng.normal(0.0, config.step_noise_std_m, size=n)
        x += noisy_step * np.sin(noisy_heading)
        y += noisy_step * np.cos(noisy_heading)
        if config.step_scale_process_std > 0:
            step_scale += rng.normal(0.0, config.step_scale_process_std, size=n)
            step_scale = np.clip(step_scale, 0.2, 3.0)

        times.append(float(step_time))
        points.append(_estimate(x, y, weights))
        if trace_particles:
            particle_times.append(float(step_time))
            particle_snapshots.append(np.column_stack([x, y]))

    while read_index < len(read_records):
        process_reads_until(float("inf"))

    final_point = _estimate(x, y, weights)
    final_time = last_processed_read_time if last_processed_read_time is not None else times[-1]
    if final_time > times[-1]:
        times.append(float(final_time))
        points.append(final_point)
        if trace_particles:
            particle_times.append(float(final_time))
            particle_snapshots.append(np.column_stack([x, y]))
    elif points:
        points[-1] = final_point
        if trace_particles:
            particle_snapshots[-1] = np.column_stack([x, y])

    particle_times_array = np.asarray(particle_times, dtype=float) if trace_particles and particle_times is not None else None
    particle_points_array = None
    chosen_particle_points = None
    if trace_particles and particle_snapshots is not None:
        full_particle_points = np.stack(particle_snapshots, axis=0)
        trace_count = min(int(trace_particle_count), n)
        if trace_count > 0:
            trace_indices = np.linspace(0, n - 1, trace_count, dtype=int)
            particle_points_array = full_particle_points[:, trace_indices, :]
        distances_to_final = np.linalg.norm(full_particle_points[-1] - final_point, axis=1)
        chosen_index = int(np.argmin(distances_to_final))
        chosen_particle_points = full_particle_points[:, chosen_index, :]

    return PFResult(
        times_unix=np.asarray(times, dtype=float),
        points=np.asarray(points, dtype=float),
        final_point=final_point,
        accepted_rfid_count=accepted_rfid_count,
        ignored_rfid_count=ignored_rfid_count,
        policy=policy,
        particle_times_unix=particle_times_array,
        particle_points=particle_points_array,
        chosen_particle_points=chosen_particle_points,
    )
 
