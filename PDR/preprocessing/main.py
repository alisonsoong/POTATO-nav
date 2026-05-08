from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

import numpy as np

try:
    from .accel_filter import filter_step_acceleration
    from .constants import (
        DEFAULT_ACCEL_HIGH_HZ,
        DEFAULT_ACCEL_LOW_HZ,
        DEFAULT_FILTER_ORDER,
        DEFAULT_GYRO_Z_SCALE_FACTOR,
        GYRO_BIAS_RAD_PER_S,
        HEADING_GYRO,
        HEADING_SOURCES,
        USER_ACCEL_BIAS_G,
    )
    from .csv_io import (
        infer_sample_rate_hz,
        load_imu_dataframe,
        read_comment_metadata,
        relative_time,
        sampling_report,
        write_dataframe,
    )
    from .gravity_sanity import add_gravity_tilt_check
    from .gyro_bias import subtract_gyro_bias
    from .gyro_heading import add_heading_columns
    from .magnetometer import magnetometer_heading_policy
    from .user_accel import prepare_step_acceleration
    from .yaw_sanity import unwrap_and_check_yaw
except ImportError:  # pragma: no cover - direct script execution support
    from accel_filter import filter_step_acceleration
    from constants import (
        DEFAULT_ACCEL_HIGH_HZ,
        DEFAULT_ACCEL_LOW_HZ,
        DEFAULT_FILTER_ORDER,
        DEFAULT_GYRO_Z_SCALE_FACTOR,
        GYRO_BIAS_RAD_PER_S,
        HEADING_GYRO,
        HEADING_SOURCES,
        USER_ACCEL_BIAS_G,
    )
    from csv_io import (
        infer_sample_rate_hz,
        load_imu_dataframe,
        read_comment_metadata,
        relative_time,
        sampling_report,
        write_dataframe,
    )
    from gravity_sanity import add_gravity_tilt_check
    from gyro_bias import subtract_gyro_bias
    from gyro_heading import add_heading_columns
    from magnetometer import magnetometer_heading_policy
    from user_accel import prepare_step_acceleration
    from yaw_sanity import unwrap_and_check_yaw


def preprocess_imu_csv(
    csv_path: Path,
    output_csv: Path,
    report_json: Path,
    heading_source: str = HEADING_GYRO,
    subtract_user_accel_bias: bool = False,
    initial_stationary_s: float = 3.0,
    apply_gyro_scale_correction: bool = False,
    gyro_z_scale_factor: float = DEFAULT_GYRO_Z_SCALE_FACTOR,
    accel_low_hz: float = DEFAULT_ACCEL_LOW_HZ,
    accel_high_hz: float = DEFAULT_ACCEL_HIGH_HZ,
    filter_order: int = DEFAULT_FILTER_ORDER,
    allow_magnetometer_heading: bool = False,
) -> Dict[str, Any]:
    metadata = read_comment_metadata(csv_path)
    df = load_imu_dataframe(csv_path)
    t = relative_time(df)
    fs = infer_sample_rate_hz(t)
    df["timestamp_relative_s"] = t

    report: Dict[str, Any] = {
        "input_csv": str(csv_path),
        "output_csv": str(output_csv),
        "metadata": metadata,
        "sampling": sampling_report(t),
        "corrections": {},
        "warnings": [],
    }

    gyro_report = subtract_gyro_bias(
        df,
        GYRO_BIAS_RAD_PER_S,
        t=t,
        initial_stationary_s=initial_stationary_s,
    )
    report["corrections"]["gyro_bias"] = gyro_report
    report["warnings"].extend(gyro_report.get("warnings", []))

    accel_report = prepare_step_acceleration(
        df,
        USER_ACCEL_BIAS_G,
        subtract_user_accel_bias=subtract_user_accel_bias,
        prefer_user_accel=True,
    )
    report["corrections"]["step_acceleration_source"] = accel_report
    report["warnings"].extend(accel_report.get("warnings", []))

    filter_report = filter_step_acceleration(
        df,
        fs,
        low_hz=accel_low_hz,
        high_hz=accel_high_hz,
        order=filter_order,
    )
    report["corrections"]["acceleration_filter"] = filter_report

    yaw_report = unwrap_and_check_yaw(df, t)
    report["corrections"]["yaw_sanity"] = yaw_report
    report["warnings"].extend(yaw_report.get("warnings", []))

    heading_report = add_heading_columns(
        df,
        t,
        heading_source=heading_source,
        apply_gyro_scale_correction=apply_gyro_scale_correction,
        gyro_z_scale_factor=gyro_z_scale_factor,
    )
    report["corrections"]["heading"] = heading_report
    report["warnings"].extend(heading_report.get("warnings", []))

    gravity_report = add_gravity_tilt_check(df)
    report["corrections"]["gravity_tilt_sanity"] = gravity_report
    report["warnings"].extend(gravity_report.get("warnings", []))

    magnetometer_report = magnetometer_heading_policy(
        df,
        allow_magnetometer_heading=allow_magnetometer_heading,
    )
    report["corrections"]["magnetometer_policy"] = magnetometer_report

    report["pdr_columns"] = {
        "time_s": "timestamp_relative_s",
        "step_accel_mag": "step_accel_mag",
        "step_accel_mag_filtered": "step_accel_mag_filtered",
        "heading": "heading_selected",
        "heading_gyro_bias_corrected": "heading_gyro_bias_corrected",
        "gyro_z_bias_corrected": "gyro_z_bias_corrected",
        "tilt_deg": "tilt_from_flat_deg" if "tilt_from_flat_deg" in df.columns else None,
    }

    write_dataframe(df, output_csv)
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(json_safe(report), indent=2, sort_keys=True), encoding="utf-8")
    return report


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    return value


def default_output_path(csv_path: Path) -> Path:
    return csv_path.with_name(f"{csv_path.stem}_corrected.csv")


def default_report_path(output_csv: Path) -> Path:
    return output_csv.with_suffix(".correction_report.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply pre-PDR corrections to an IMU CSV.")
    parser.add_argument("csv_file", type=Path, help="Input IMU CSV")
    parser.add_argument("--output", type=Path, default=None, help="Output corrected CSV")
    parser.add_argument("--report-json", type=Path, default=None, help="Output correction report JSON")
    parser.add_argument(
        "--heading-source",
        choices=HEADING_SOURCES,
        default=HEADING_GYRO,
        help="Heading column to write into heading_selected.",
    )
    parser.add_argument(
        "--no-user-accel-bias",
        action="store_true",
        help="Use user_accel columns without subtracting the static user-accel bias. This is now the default.",
    )
    parser.add_argument(
        "--subtract-user-accel-bias",
        action="store_true",
        help="Opt in to subtracting the tiny static user-accel bias before step magnitude.",
    )
    parser.add_argument(
        "--initial-stationary-s",
        type=float,
        default=3.0,
        help="Use the first N seconds as a stationary segment to estimate this run's gyro bias.",
    )
    parser.add_argument(
        "--use-characterization-gyro-bias",
        action="store_true",
        help="Disable initial-segment gyro bias estimation and use the static-flat characterization bias.",
    )
    parser.add_argument(
        "--apply-gyro-scale-correction",
        action="store_true",
        help="Apply the optional gyro z scale factor during heading integration.",
    )
    parser.add_argument(
        "--gyro-z-scale-factor",
        type=float,
        default=DEFAULT_GYRO_Z_SCALE_FACTOR,
        help="Gyro z scale factor to use only when --apply-gyro-scale-correction is set.",
    )
    parser.add_argument("--accel-low-hz", type=float, default=DEFAULT_ACCEL_LOW_HZ)
    parser.add_argument("--accel-high-hz", type=float, default=DEFAULT_ACCEL_HIGH_HZ)
    parser.add_argument("--filter-order", type=int, default=DEFAULT_FILTER_ORDER)
    parser.add_argument(
        "--allow-magnetometer-heading",
        action="store_true",
        help="Record that magnetometer heading is allowed. Default is disabled for indoor PDR.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    csv_path = args.csv_file.expanduser()
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    output_csv = args.output or default_output_path(csv_path)
    report_json = args.report_json or default_report_path(output_csv)
    report = preprocess_imu_csv(
        csv_path=csv_path,
        output_csv=output_csv,
        report_json=report_json,
        heading_source=args.heading_source,
        subtract_user_accel_bias=args.subtract_user_accel_bias and not args.no_user_accel_bias,
        initial_stationary_s=0.0 if args.use_characterization_gyro_bias else args.initial_stationary_s,
        apply_gyro_scale_correction=args.apply_gyro_scale_correction,
        gyro_z_scale_factor=args.gyro_z_scale_factor,
        accel_low_hz=args.accel_low_hz,
        accel_high_hz=args.accel_high_hz,
        filter_order=args.filter_order,
        allow_magnetometer_heading=args.allow_magnetometer_heading,
    )

    print(f"Input CSV: {csv_path}")
    print(f"Output CSV: {output_csv}")
    print(f"Report JSON: {report_json}")
    print(f"Sample rate: {report['sampling']['sample_rate_hz']:.3f} Hz")
    print(f"Step accel source: {report['corrections']['step_acceleration_source']['step_accel_source']}")
    print(f"Heading source: {report['corrections']['heading']['preferred_heading_source']}")
    if report["warnings"]:
        print("Warnings:")
        for warning in report["warnings"]:
            print(f"  - {warning}")


if __name__ == "__main__":
    main()
