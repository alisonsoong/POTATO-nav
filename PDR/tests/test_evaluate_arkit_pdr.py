import tempfile
import unittest
from pathlib import Path

import numpy as np

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluate_arkit_pdr import (  # noqa: E402
    ALIGNMENT_BEST_FIT,
    ALIGNMENT_START,
    TrimConfig,
    align_pdr_to_arkit,
    interpolate_points,
    load_arkit_csv,
    path_length,
    resolve_bundle_paths,
    trim_arkit_trajectory,
)


class EvaluateARKitPDRTests(unittest.TestCase):
    def test_load_arkit_csv_filters_to_normal_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "arkit.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "timestamp_s,x_m,y_m,z_m,tracking_state,tracking_reason",
                        "0.0,0,0,0,limited,initializing",
                        "1.0,1,0,0,normal,",
                        "2.0,2,0,0,normal,",
                    ]
                ),
                encoding="utf-8",
            )

            traj = load_arkit_csv(csv_path)

        self.assertEqual(traj.t.tolist(), [1.0, 2.0])
        np.testing.assert_allclose(traj.points, np.array([[1.0, -0.0], [2.0, -0.0]]))
        self.assertEqual(traj.tracking_state.tolist(), ["normal", "normal"])

    def test_load_arkit_csv_can_include_non_normal_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "arkit.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "timestamp_s,x_m,y_m,z_m,tracking_state,tracking_reason",
                        "0.0,0,0,0,limited,initializing",
                        "1.0,1,0,0,normal,",
                    ]
                ),
                encoding="utf-8",
            )

            traj = load_arkit_csv(csv_path, include_non_normal=True)

        self.assertEqual(traj.t.tolist(), [0.0, 1.0])
        self.assertEqual(traj.tracking_state.tolist(), ["limited", "normal"])

    def test_resolve_bundle_paths_finds_standard_bundle_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "metadata.json").write_text("{}", encoding="utf-8")
            (folder / "arkit.csv").write_text("timestamp_s,x_m,z_m\n0,0,0\n1,1,0", encoding="utf-8")
            (folder / "imu.csv").write_text("timestamp_s,gyro_x,gyro_y,gyro_z,accel_z\n", encoding="utf-8")

            paths = resolve_bundle_paths(folder)

        self.assertEqual(paths.arkit_csv.name, "arkit.csv")
        self.assertEqual(paths.imu_csv.name, "imu.csv")
        self.assertEqual(paths.metadata_csv_or_json.name, "metadata.json")

    def test_interpolate_points(self):
        source_t = np.array([0.0, 1.0, 2.0])
        source_points = np.array([[0.0, 0.0], [2.0, 2.0], [4.0, 0.0]])
        target_t = np.array([0.5, 1.5])

        interpolated = interpolate_points(source_t, source_points, target_t)

        np.testing.assert_allclose(interpolated, np.array([[1.0, 1.0], [3.0, 1.0]]))

    def test_trim_arkit_trajectory(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "arkit.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "timestamp_s,x_m,y_m,z_m,tracking_state,tracking_reason",
                        "0.0,0,0,0,normal,",
                        "1.0,1,0,0,normal,",
                        "2.0,2,0,0,normal,",
                        "3.0,3,0,0,normal,",
                        "4.0,4,0,0,normal,",
                    ]
                ),
                encoding="utf-8",
            )
            traj = load_arkit_csv(csv_path)

        trimmed = trim_arkit_trajectory(traj, TrimConfig(start_s=1.0, end_s=1.0))

        self.assertEqual(trimmed.t.tolist(), [1.0, 2.0, 3.0])
        np.testing.assert_allclose(trimmed.points[:, 0], np.array([1.0, 2.0, 3.0]))

    def test_start_alignment_matches_start_position_and_heading(self):
        pdr = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]])
        arkit = np.array([[10.0, 5.0], [10.0, 6.0], [10.0, 7.0]])

        aligned = align_pdr_to_arkit(pdr, arkit, ALIGNMENT_START)

        np.testing.assert_allclose(aligned, arkit, atol=1e-9)

    def test_best_fit_alignment_does_not_scale(self):
        pdr = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]])
        arkit_scaled = np.array([[5.0, 5.0], [7.0, 5.0], [7.0, 7.0]])

        aligned = align_pdr_to_arkit(pdr, arkit_scaled, ALIGNMENT_BEST_FIT)

        self.assertAlmostEqual(path_length(aligned), path_length(pdr))
        self.assertNotAlmostEqual(path_length(aligned), path_length(arkit_scaled))


if __name__ == "__main__":
    unittest.main()
