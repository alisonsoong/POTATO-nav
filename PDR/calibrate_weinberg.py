import argparse
from pathlib import Path
from dataclasses import dataclass

import numpy as np

from config import WEINBERG_STEP
from plot import plot_calibration_dashboard
from step_detection.step_detection import detect_steps, load_motion_csv
from step_detection.weinberg_steps import estimate_step_lengths_weinberg


@dataclass(frozen=True)
class WeinbergCalibrationResult:
    calibrated_k: float
    estimated_distance_m: float
    mean_step_length_m: float
    step_length_std_m: float
    step_lengths_m: np.ndarray


def calibrate_weinberg_k(
    amag_f: np.ndarray,
    peaks: np.ndarray,
    fs: float,
    target_distance: float,
) -> float:
    raw_lengths = estimate_step_lengths_weinberg(amag_f, peaks, fs, k=1.0)
    total_raw_distance = np.sum(raw_lengths)

    if total_raw_distance <= 0:
        raise ValueError("Could not calibrate Weinberg k because the raw estimated distance is zero.")

    return target_distance / total_raw_distance


def run_weinberg_calibration(
    amag_f: np.ndarray,
    peaks: np.ndarray,
    fs: float,
    ground_truth_distance_m: float,
) -> WeinbergCalibrationResult:
    calibrated_k = calibrate_weinberg_k(
        amag_f,
        peaks,
        fs,
        target_distance=ground_truth_distance_m,
    )
    step_lengths = estimate_step_lengths_weinberg(amag_f, peaks, fs, k=calibrated_k)
    return WeinbergCalibrationResult(
        calibrated_k=calibrated_k,
        estimated_distance_m=float(np.sum(step_lengths)),
        mean_step_length_m=float(np.mean(step_lengths)),
        step_length_std_m=float(np.std(step_lengths)),
        step_lengths_m=step_lengths,
    )


def suggested_step_model_config(k: float) -> str:
    return (
        "StepModelConfig(\n"
        f"    model={WEINBERG_STEP!r},\n"
        f"    weinberg_k={k:.6f},\n"
        ")"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate Weinberg step-length k from a straight walk CSV.")
    parser.add_argument("csv_file", help="Path to the straight-walk CSV file")
    parser.add_argument("ground_truth_distance_m", type=float, help="Known straight-line distance in meters")
    args = parser.parse_args()

    csv_path = Path(args.csv_file)
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    t, user_ax, user_ay, user_az = load_motion_csv(csv_path)
    peaks, amag_f, fs = detect_steps(
        t,
        user_ax,
        user_ay,
        user_az,
    )

    if len(peaks) == 0:
        raise ValueError("No steps were detected, so Weinberg calibration could not be performed.")

    calibration = run_weinberg_calibration(
        amag_f,
        peaks,
        fs,
        ground_truth_distance_m=args.ground_truth_distance_m,
    )

    print(f"CSV: {csv_path}")
    print(f"Ground-truth distance: {args.ground_truth_distance_m:.2f} m")
    print(f"Samples: {len(t)}")
    print(f"Estimated sample rate: {fs:.2f} Hz")
    print(f"Detected steps: {len(peaks)}")
    print(f"Calibrated Weinberg k: {calibration.calibrated_k:.6f}")
    print(f"Estimated distance with calibrated k: {calibration.estimated_distance_m:.2f} m")
    print(f"Mean step length: {calibration.mean_step_length_m:.3f} m")
    print(f"Step length std: {calibration.step_length_std_m:.3f} m")
    print("\nPaste this into CONFIG.step_model in pdr_run.py:")
    print(suggested_step_model_config(calibration.calibrated_k))

    plot_calibration_dashboard(
        t=t,
        amag_f=amag_f,
        peaks=peaks,
        step_lengths=calibration.step_lengths_m,
        title="Weinberg Calibration",
        calibrated_k=calibration.calibrated_k,
    )


if __name__ == "__main__":
    main()
