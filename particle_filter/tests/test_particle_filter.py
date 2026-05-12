import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PDR_DIR = ROOT / "PDR"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(PDR_DIR) not in sys.path:
    sys.path.insert(0, str(PDR_DIR))

from step_detection.step_detection import load_aligned_series  # noqa: E402

from particle_filter.antenna import candidate_policies  # noqa: E402
from particle_filter.filter import run_particle_filter  # noqa: E402
from particle_filter.loaders import load_rfid_reads, load_tag_map  # noqa: E402
from particle_filter.models import ARKitTrajectory, AntennaPolicy, MotionData, PFConfig  # noqa: E402


class ParticleFilterTests(unittest.TestCase):
    def test_load_tag_map_converts_cm_to_meters(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tags.csv"
            path.write_text("epc,tag_id,x_cm,y_cm\nE1,T1,120,-35\n", encoding="utf-8")

            tag_map = load_tag_map(path)

        row = tag_map.tags.iloc[0]
        self.assertEqual(row["epc"], "E1")
        self.assertAlmostEqual(row["x_m"], 1.2)
        self.assertAlmostEqual(row["y_m"], -0.35)

    def test_load_rfid_reads_flags_unknown_epcs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tag_path = Path(tmp) / "tags.csv"
            rfid_path = Path(tmp) / "reads.csv"
            tag_path.write_text("epc,tag_id,x_cm,y_cm\nE1,T1,0,0\n", encoding="utf-8")
            rfid_path.write_text(
                "EPC,antenna,timestamp,frequency,rssi,phase\n"
                "E1,1,1000,921750,-50,10\n"
                "UNKNOWN,1,1100,921750,-40,20\n",
                encoding="utf-8",
            )

            reads = load_rfid_reads(rfid_path, load_tag_map(tag_path))

        self.assertEqual(len(reads), 2)
        self.assertEqual(int(reads["known_tag"].sum()), 1)
        self.assertAlmostEqual(reads.iloc[0]["timestamp_s"], 1.0)

    def test_pdr_loader_accepts_passivenav_elapsed_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "imu.csv"
            csv_path.write_text(
                "elapsed_since_run_start_s,user_accel_x\n"
                "5.0,0.1\n"
                "6.0,0.2\n"
                "7.0,0.3\n",
                encoding="utf-8",
            )

            t, accel = load_aligned_series(csv_path, ("user_accel_x",))

        np.testing.assert_allclose(t, np.array([0.0, 1.0, 2.0]))
        np.testing.assert_allclose(accel, np.array([0.1, 0.2, 0.3]))

    def test_candidate_policies_include_per_epc_auto(self):
        tag_map = load_tag_map_from_text("epc,tag_id,x_cm,y_cm\nE1,T1,0,100\n")
        reads = pd.DataFrame(
            {
                "timestamp_s": [1.0, 1.1, 4.0],
                "epc": ["E1", "E1", "E1"],
                "antenna": [1, 1, 2],
                "rssi": [-55, -50, -45],
                "known_tag": [True, True, True],
            }
        )
        arkit = ARKitTrajectory(
            unix_t=np.array([0.0, 1.0, 2.0]),
            points_local=np.array([[0.0, 0.0], [0.0, 1.0], [0.0, 2.0]]),
            points_map=np.array([[0.0, 0.0], [0.0, 1.0], [0.0, 2.0]]),
            rotation_rad=0.0,
            tracking_state=np.array(["normal", "normal", "normal"]),
        )

        policies = candidate_policies(reads, arkit, tag_map)

        self.assertTrue(any(policy.mode == "per_epc" for policy in policies))
        per_epc = next(policy for policy in policies if policy.mode == "per_epc")
        self.assertEqual(per_epc.epc_to_antenna["E1"], 1)

    def test_particle_filter_runs_on_tiny_motion(self):
        tag_map = load_tag_map_from_text("epc,tag_id,x_cm,y_cm\nE1,T1,0,140\n")
        motion = MotionData(
            unix_t=np.array([0.0, 1.0, 2.0]),
            rel_t=np.array([0.0, 1.0, 2.0]),
            step_times_unix=np.array([1.0, 2.0]),
            step_times_rel=np.array([1.0, 2.0]),
            step_headings_rad=np.array([0.0, 0.0]),
            step_count=2,
            base_step_length_m=0.7,
        )
        reads = pd.DataFrame(
            {
                "timestamp_s": [1.5],
                "epc": ["E1"],
                "antenna": [1],
                "known_tag": [True],
                "rssi": [-50],
                "phase": [10],
            }
        )
        config = PFConfig(particle_count=100, seed=3, step_scale_mean=1.0, step_scale_std=0.01)
        policy = AntennaPolicy(mode="global", antenna=1)

        result = run_particle_filter(motion, reads, tag_map, policy, config)

        self.assertEqual(result.points.shape, (3, 2))
        self.assertEqual(result.accepted_rfid_count, 1)
        self.assertTrue(np.isfinite(result.final_point).all())


def load_tag_map_from_text(text: str):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "tags.csv"
        path.write_text(text, encoding="utf-8")
        return load_tag_map(path)


if __name__ == "__main__":
    unittest.main()
