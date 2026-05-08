import argparse
from dataclasses import dataclass
from pathlib import Path
import numpy as np

from config import (
    CONSTANT_STEP,
    RUN_PDR,
    PDRConfig,
    RunnerConfig,
    StartPointConfig,
    StepDetectionConfig,
    StepModelConfig,
    TurnDetectionConfig,
    WEINBERG_STEP,
)

from helpers import run_pdr_with_step_lengths
from plot import plot_pdr_dashboard
from step_detection.step_detection import detect_steps, detect_steps_from_csv, load_aligned_series
from step_detection.weinberg_steps import build_weinberg_step_lengths
from turn_detection.heading import CORE_MOTION_YAW, GYRO_INTEGRATED_YAW, load_heading_series, unwrap_angle
from turn_detection.turn_detection import detect_turns_with_config, step_turn_mask, summarize_turns


BASE_DIR = Path(__file__).resolve().parent

CONFIG = PDRConfig(
    csv_file=BASE_DIR / "walks" / "L_1_corrected.csv",
    runner=RunnerConfig(
        mode=RUN_PDR,
        show_plots=True,
    ),
    start_point=StartPointConfig(x_m=0.0, y_m=0.0),
    step_detection=StepDetectionConfig(
        low_hz=0.5,
        high_hz=3.0,
        min_step_gap_s=0.35,
        prominence=0.03,
    ),
    turn_detection=TurnDetectionConfig(
        heading_mode=GYRO_INTEGRATED_YAW,
        rate_threshold_deg_s=20.0,
        min_angle_deg=30.0,
        min_duration_s=0.2,
        merge_gap_s=0.15,
    ),
    step_model=StepModelConfig(
        model=CONSTANT_STEP,
        constant_step_length_m=0.7,
        weinberg_k=0.45,
    ),
    plot_title="L Walk PDR",
)


@dataclass
class PDRRunResult:
    label: str
    accel_source: str
    heading_source: str
    t: np.ndarray
    peaks: np.ndarray
    amag_f: np.ndarray
    fs: float
    heading: np.ndarray
    turns: list
    turn_steps: np.ndarray
    step_lengths: np.ndarray
    step_model_label: str
    xs: np.ndarray
    ys: np.ndarray
    step_times: np.ndarray


def resolve_csv_path(config: PDRConfig) -> Path:
    parser = argparse.ArgumentParser(description="Run the central PDR pipeline on an IMU CSV.")
    parser.add_argument(
        "csv_file",
        nargs="?",
        default=None,
        help="Optional path to the input CSV file. If omitted, the hardcoded CONFIG csv_file is used.",
    )
    args = parser.parse_args()
    return Path(args.csv_file) if args.csv_file is not None else config.csv_file


def build_step_lengths(peaks, amag_f, fs, config: PDRConfig):
    model = config.step_model

    if model.model == CONSTANT_STEP:
        step_lengths = np.full(len(peaks), model.constant_step_length_m, dtype=float)
        return step_lengths, f"constant {model.constant_step_length_m:.2f} m"

    if model.model == WEINBERG_STEP:
        step_lengths, _, label = build_weinberg_step_lengths(amag_f, peaks, fs, model)
        return step_lengths, label

    raise ValueError(f"Unknown step model: {model.model}")


def align_to_time(t: np.ndarray, source_t: np.ndarray, values: np.ndarray) -> np.ndarray:
    if source_t.shape == t.shape and np.allclose(source_t, t):
        return values
    return np.interp(t, source_t, values)


def build_pdr_result(
    label: str,
    accel_source: str,
    heading_source: str,
    t: np.ndarray,
    peaks: np.ndarray,
    amag_f: np.ndarray,
    fs: float,
    heading: np.ndarray,
    config: PDRConfig,
) -> PDRRunResult:
    turns = detect_turns_with_config(t, heading, config.turn_detection)
    step_lengths, step_model_label = build_step_lengths(peaks, amag_f, fs, config)
    xs, ys, step_times = run_pdr_with_step_lengths(
        t,
        peaks,
        heading,
        step_lengths,
        start_x=config.start_point.x_m,
        start_y=config.start_point.y_m,
    )
    turn_steps = step_turn_mask(t, peaks, turns)

    return PDRRunResult(
        label=label,
        accel_source=accel_source,
        heading_source=heading_source,
        t=t,
        peaks=peaks,
        amag_f=amag_f,
        fs=fs,
        heading=heading,
        turns=turns,
        turn_steps=turn_steps,
        step_lengths=step_lengths,
        step_model_label=step_model_label,
        xs=xs,
        ys=ys,
        step_times=step_times,
    )


def compute_corrected_pdr(csv_path: Path, config: PDRConfig) -> PDRRunResult:
    peaks, amag_f, fs, t, _, _, _ = detect_steps_from_csv(
        csv_path,
        low=config.step_detection.low_hz,
        high=config.step_detection.high_hz,
        min_step_gap_s=config.step_detection.min_step_gap_s,
        prominence=config.step_detection.prominence,
    )
    heading_t, heading = load_heading_series(csv_path, config.turn_detection.heading_mode)
    heading = align_to_time(t, heading_t, heading)

    return build_pdr_result(
        label="After corrections",
        accel_source="step_accel_mag_filtered from corrected CSV",
        heading_source=config.turn_detection.heading_mode,
        t=t,
        peaks=peaks,
        amag_f=amag_f,
        fs=fs,
        heading=heading,
        config=config,
    )


def compute_before_corrections_pdr(csv_path: Path, config: PDRConfig) -> PDRRunResult:
    t, user_ax, user_ay, user_az, yaw = load_aligned_series(
        csv_path,
        ("user_accel_x",),
        ("user_accel_y",),
        ("user_accel_z",),
        ("yaw",),
    )
    peaks, amag_f, fs = detect_steps(
        t,
        user_ax,
        user_ay,
        user_az,
        low=config.step_detection.low_hz,
        high=config.step_detection.high_hz,
        min_step_gap_s=config.step_detection.min_step_gap_s,
        prominence=config.step_detection.prominence,
    )

    return build_pdr_result(
        label="Before corrections",
        accel_source="raw user_accel_*",
        heading_source=CORE_MOTION_YAW,
        t=t,
        peaks=peaks,
        amag_f=amag_f,
        fs=fs,
        heading=unwrap_angle(yaw),
        config=config,
    )


def print_result_summary(result: PDRRunResult) -> None:
    print(f"{result.label}:")
    print(f"  Acceleration source: {result.accel_source}")
    print(f"  Heading source: {result.heading_source}")
    print(f"  Detected steps: {len(result.peaks)}")
    print(f"  Steps during turns: {int(result.turn_steps.sum())}")
    print(f"  Estimated path length: {float(result.step_lengths.sum()):.2f} m")
    print(f"  Final position: ({result.xs[-1]:.2f}, {result.ys[-1]:.2f}) m")


def run_pdr_mode(csv_path: Path, config: PDRConfig) -> None:
    corrected = compute_corrected_pdr(csv_path, config)
    before_corrections = None
    try:
        before_corrections = compute_before_corrections_pdr(csv_path, config)
    except (KeyError, ValueError) as error:
        print(f"Before-correction PDR unavailable: {error}")

    print(f"CSV: {csv_path}")
    print(f"Step model: {corrected.step_model_label}")
    print(f"Samples: {len(corrected.t)}")
    print(f"Estimated sample rate: {corrected.fs:.2f} Hz")
    if before_corrections is not None:
        print_result_summary(before_corrections)
    print_result_summary(corrected)
    for line in summarize_turns(corrected.turns):
        print(line)

    if config.runner.show_plots:
        plot_pdr_dashboard(
            t=corrected.t,
            amag_f=corrected.amag_f,
            peaks=corrected.peaks,
            heading=corrected.heading,
            turns=corrected.turns,
            turn_steps=corrected.turn_steps,
            xs=corrected.xs,
            ys=corrected.ys,
            title=config.plot_title,
            comparison_xs=before_corrections.xs if before_corrections is not None else None,
            comparison_ys=before_corrections.ys if before_corrections is not None else None,
            comparison_label="Before corrections",
            trajectory_label="After corrections",
        )


def main() -> None:
    config = CONFIG
    csv_path = resolve_csv_path(config)
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    if config.runner.mode != RUN_PDR:
        raise ValueError("pdr_run.py only supports RUN_PDR. Use calibrate_weinberg.py for Weinberg calibration.")

    run_pdr_mode(csv_path, config)


if __name__ == "__main__":
    main()
