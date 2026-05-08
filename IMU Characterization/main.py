from __future__ import annotations

from pathlib import Path

from typing import Dict, List

from imu_helpers import format_result_summary, results_to_json
from known_yaw_rotation import YawRotationCsv, analyze_known_yaw_rotation_csvs
from six_orientation_accel import analyze_six_orientation_csvs
from static_after_motion import analyze_static_after_motion_csvs
from static_flat import analyze_static_flat_csvs, static_flat_gyro_bias
from walking_tests import (
    analyze_known_path_csvs,
    analyze_out_and_back_csvs,
    analyze_straight_walk_csvs,
)


BASE_DIR = Path(__file__).resolve().parent
TESTS_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "results"


# Edit these lists directly for your experiment.
STATIC_FLAT_CSVS = [
    TESTS_DIR / "static_rest.csv",
]

SIX_ORIENTATION_CSVS = {
    "x_up": [TESTS_DIR / "+x.csv"],
    "x_down": [TESTS_DIR / "-x.csv"],
    "y_up": [TESTS_DIR / "+y.csv"],
    "y_down": [TESTS_DIR / "-y.csv"],
    "z_up": [TESTS_DIR / "+z.csv"],
    "z_down": [],
}

KNOWN_YAW_ROTATION_CSVS = [
    YawRotationCsv(TESTS_DIR / "90_left_1.csv", true_rotation_deg=90.0),
    YawRotationCsv(TESTS_DIR / "90_left_2.csv", true_rotation_deg=90.0),
    YawRotationCsv(TESTS_DIR / "90_left_3.csv", true_rotation_deg=90.0),
    YawRotationCsv(TESTS_DIR / "90_right_1.csv", true_rotation_deg=-90.0),
    YawRotationCsv(TESTS_DIR / "90_right_2.csv", true_rotation_deg=-90.0),
    YawRotationCsv(TESTS_DIR / "90_right_3.csv", true_rotation_deg=-90.0),
    YawRotationCsv(TESTS_DIR / "180_1.csv", true_rotation_deg=-180.0),
    YawRotationCsv(TESTS_DIR / "180_2.csv", true_rotation_deg=-180.0),
    YawRotationCsv(TESTS_DIR / "180_3.csv", true_rotation_deg=-180.0),
    YawRotationCsv(TESTS_DIR / "360_1.csv", true_rotation_deg=360.0),
    YawRotationCsv(TESTS_DIR / "360_2.csv", true_rotation_deg=360.0),
    YawRotationCsv(TESTS_DIR / "360_3.csv", true_rotation_deg=360.0),
]

STATIC_AFTER_MOTION_CSVS = []

STRAIGHT_WALK_CSVS = []

KNOWN_PATH_CSVS = []

OUT_AND_BACK_CSVS = []


def existing(paths):
    return [path for path in paths if path.is_file()]


def existing_yaw_trials(trials):
    return [trial for trial in trials if trial.csv_file.is_file()]



def recommended_corrections(document: Dict) -> Dict:
    static_flat = document.get("static_flat")
    known_yaw = document.get("known_yaw_rotation")
    gyro_bias = (
        static_flat.get("gyro_bias_rad_per_s")
        if static_flat is not None
        else {"x": None, "y": None, "z": None}
    )
    user_accel_available = static_flat is not None and static_flat.get("user_accel_bias_g", {}).get("x") is not None
    preferred_heading = "unknown"
    reason = "Known yaw rotation results are unavailable."
    scale_factor = None
    if known_yaw is not None:
        summary = known_yaw.get("summary", {})
        preferred_heading = summary.get("recommendation_preferred_heading_source") or "unknown"
        reason = summary.get("heading_source_reason") or reason
        scale_factor = summary.get("estimated_gyro_z_scale_factor")

    apply_scale = (
        scale_factor is not None
        and abs(float(scale_factor) - 1.0) > 0.02
        and known_yaw is not None
    )
    return {
        "subtract_gyro_bias": static_flat is not None,
        "gyro_bias_to_subtract_rad_per_s": gyro_bias,
        "use_user_accel_for_step_detection": user_accel_available,
        "use_fused_accel_for_step_detection": not user_accel_available,
        "use_gravity_for_tilt_sanity": static_flat is not None and static_flat.get("phone_flatness", {}).get("gravity_mean_g", {}).get("x") is not None,
        "preferred_heading_source": preferred_heading,
        "heading_source_reason": reason,
        "apply_gyro_scale_correction": apply_scale,
        "gyro_z_scale_factor": scale_factor,
        "use_magnetometer_for_heading": False,
        "magnetometer_reason": "Indoor magnetometer heading is not recommended unless magnetometer accuracy is consistently high and yaw tests validate it.",
        "pdr_noise_note": (
            "Sensor-level noise estimates are not the same as PDR process noise. "
            "PDR process noise must also account for step length error, phone-pose error, "
            "heading misalignment, and walking dynamics."
        ),
    }


def build_output_document(results: List[Dict]) -> Dict:
    document: Dict = {
        "static_flat": None,
        "allan_noise_model": None,
        "six_orientation_accel": None,
        "known_yaw_rotation": None,
        "static_after_motion": None,
        "other_tests": [],
        "recommended_corrections": None,
        "notes_and_warnings": [],
    }
    for result in results:
        document["notes_and_warnings"].extend(result.get("notes_and_warnings", []))
        if "static_flat" in result:
            document["static_flat"] = result["static_flat"]
            document["allan_noise_model"] = result.get("allan_noise_model")
        elif "six_orientation_accel" in result:
            document["six_orientation_accel"] = result["six_orientation_accel"]
        elif "known_yaw_rotation" in result:
            document["known_yaw_rotation"] = result["known_yaw_rotation"]
        elif "static_after_motion" in result:
            document["static_after_motion"] = result["static_after_motion"]
        else:
            document["other_tests"].append(result)
    document["recommended_corrections"] = recommended_corrections(document)
    document["notes_and_warnings"] = sorted(set(document["notes_and_warnings"]))
    return document


def write_outputs(results: List[Dict], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "imu_characterization_results.json"
    report_path = output_dir / "imu_characterization_report.txt"
    document = build_output_document(results)
    json_path.write_text(results_to_json(document), encoding="utf-8")
    report_path.write_text(
        "\n\n".join(format_result_summary(result) for result in results),
        encoding="utf-8",
    )
    return json_path, report_path

def main() -> None:
    results = []
    gyro_bias = None

    static_files = existing(STATIC_FLAT_CSVS)
    if static_files:
        static_result = analyze_static_flat_csvs(static_files)
        results.append(static_result)
        gyro_bias = static_flat_gyro_bias(static_result)

    six_orientation = {
        pose: existing(csv_files)
        for pose, csv_files in SIX_ORIENTATION_CSVS.items()
    }
    six_orientation = {
        pose: csv_files
        for pose, csv_files in six_orientation.items()
        if csv_files
    }
    if six_orientation:
        results.append(analyze_six_orientation_csvs(six_orientation))

    yaw_trials = existing_yaw_trials(KNOWN_YAW_ROTATION_CSVS)
    if yaw_trials:
        results.append(analyze_known_yaw_rotation_csvs(yaw_trials, gyro_bias))

    static_after_motion = existing(STATIC_AFTER_MOTION_CSVS)
    if static_after_motion:
        results.append(analyze_static_after_motion_csvs(static_after_motion))

    if STRAIGHT_WALK_CSVS:
        trials = [trial for trial in STRAIGHT_WALK_CSVS if trial.csv_file.is_file()]
        if trials:
            results.append(analyze_straight_walk_csvs(trials))

    if KNOWN_PATH_CSVS:
        trials = [trial for trial in KNOWN_PATH_CSVS if trial.csv_file.is_file()]
        if trials:
            results.append(analyze_known_path_csvs(trials))

    if OUT_AND_BACK_CSVS:
        trials = [trial for trial in OUT_AND_BACK_CSVS if trial.csv_file.is_file()]
        if trials:
            results.append(analyze_out_and_back_csvs(trials))

    if not results:
        raise ValueError("No configured CSV files were found. Edit main.py.")

    json_path, report_path = write_outputs(results, OUTPUT_DIR)
    print("\n\n".join(format_result_summary(result) for result in results))
    print(f"\nWrote JSON: {json_path}")
    print(f"Wrote report: {report_path}")


if __name__ == "__main__":
    main()
