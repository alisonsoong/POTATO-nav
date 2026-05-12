from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .calibration import calibrate, evaluate_run, flatten_metrics, save_calibration
from .filter import RFID_MODEL_RSSI, RFID_MODELS
from .loaders import load_tag_map
from .plotting import save_trajectory_plot
from .rfid_pipeline import RFID_MODE_SMOOTHED, RFID_MODES
from .video import save_simulation_video


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run offline RFID + IMU particle-filter calibration/evaluation.")
    parser.add_argument("--calibration-dir", type=Path, required=True, help="Test1 folder used for ARKit calibration.")
    parser.add_argument("--eval-dir", type=Path, action="append", default=[], help="Evaluation run folder. May be repeated.")
    parser.add_argument("--tag-map", type=Path, required=True, help="CSV with epc,tag_id,x_cm,y_cm.")
    parser.add_argument("--out-dir", type=Path, required=True, help="Directory for calibration JSON, metrics CSV, and plots.")
    parser.add_argument("--particles", type=int, default=800, help="Number of particles for calibration and evaluation.")
    parser.add_argument("--seed", type=int, default=7, help="Random seed for deterministic PF runs.")
    parser.add_argument(
        "--imu-characterization",
        type=Path,
        default=Path("IMU Characterization/results/imu_characterization_results.json"),
        help="IMU characterization JSON used for gyro/PDR corrections.",
    )
    parser.add_argument(
        "--rfid-mode",
        choices=RFID_MODES,
        default=RFID_MODE_SMOOTHED,
        help="Use raw RFID reads or zero-lag smoothed reads from ThingMagic/Read/rfid_processing.py.",
    )
    parser.add_argument(
        "--rfid-measurement-model",
        choices=RFID_MODELS,
        default=RFID_MODEL_RSSI,
        help="RFID PF update model: RSSI/proximity anchors, phase-change range hints, or both.",
    )
    parser.add_argument("--no-plots", action="store_true", help="Skip trajectory plot generation.")
    parser.add_argument("--video", action="store_true", help="Save an ARKit/PDR/PF/particle simulation video for each eval run.")
    parser.add_argument("--video-fps", type=int, default=12, help="Simulation video frames per second.")
    parser.add_argument("--video-duration-s", type=float, default=18.0, help="Rendered video duration in seconds.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    tag_map = load_tag_map(args.tag_map)
    calibration = calibrate(
        args.calibration_dir,
        tag_map,
        particle_count=args.particles,
        seed=args.seed,
        imu_characterization_path=args.imu_characterization,
        rfid_mode=args.rfid_mode,
        rfid_measurement_model=args.rfid_measurement_model,
    )
    calibration_path = out_dir / "calibration.json"
    save_calibration(calibration, calibration_path)

    rows = []
    print(f"Calibration folder: {args.calibration_dir}")
    print(f"Selected antenna policy: {calibration.policy.label}")
    print(f"Calibration candidates: {calibration.candidate_count}")
    print(f"Calibration RMSE: {calibration.metrics['rmse_m']:.3f} m")
    print(f"Saved calibration: {calibration_path}")

    for eval_dir in args.eval_dir:
        result = evaluate_run(
            eval_dir,
            tag_map,
            calibration,
            imu_characterization_path=args.imu_characterization,
            rfid_mode=args.rfid_mode,
            trace_particles=args.video,
        )
        run = result["run"]
        pf_result = result["pf_result"]
        rows.append(flatten_metrics(run.name, "imu_only", result["baseline_metrics"], calibration))
        rows.append(
            flatten_metrics(
                run.name,
                "rfid_imu_pf",
                result["pf_metrics"],
                calibration,
                accepted_rfid_count=pf_result.accepted_rfid_count,
            )
        )

        if not args.no_plots:
            plot_path = out_dir / f"{run.name.replace(' ', '_')}_trajectory.png"
            save_trajectory_plot(
                plot_path,
                run.arkit,
                result["baseline_points"],
                pf_result.points,
                tag_map,
                title=f"{run.name}: ARKit vs IMU vs RFID+IMU PF",
            )
            print(f"Saved plot: {plot_path}")

        if args.video:
            video_path = out_dir / f"{run.name.replace(' ', '_')}_simulation.mp4"
            saved_video = save_simulation_video(
                video_path,
                run.arkit,
                result["baseline_times"],
                result["baseline_points"],
                pf_result,
                tag_map,
                title=f"{run.name}: ARKit vs PDR vs PF particles",
                fps=args.video_fps,
                duration_s=args.video_duration_s,
            )
            print(f"Saved video: {saved_video}")

        print(
            f"{run.name}: IMU RMSE={result['baseline_metrics']['rmse_m']:.3f} m, "
            f"PF RMSE={result['pf_metrics']['rmse_m']:.3f} m, "
            f"PF closed-loop={result['pf_metrics']['closed_loop_return_error_m']:.3f} m, "
            f"RFID updates={pf_result.accepted_rfid_count}"
        )

    if rows:
        metrics_path = out_dir / "metrics.csv"
        pd.DataFrame(rows).to_csv(metrics_path, index=False)
        print(f"Saved metrics: {metrics_path}")
    else:
        print("No --eval-dir provided; calibration only.")


if __name__ == "__main__":
    main()
