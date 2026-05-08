# IMU Characterization

This folder analyzes IMU CSV recordings and writes characterization results for PDR preprocessing. It is intentionally simple: edit the CSV lists in `main.py`, then run the script.

Outputs are written to:

```text
IMU Characterization/results/imu_characterization_results.json
IMU Characterization/results/imu_characterization_report.txt
```

## Folder Layout

```text
IMU Characterization/
  input/                         raw characterization CSVs
  results/                       generated JSON and text reports
  main.py                        hardcoded runner
  static_flat.py                 long static-flat analysis
  six_orientation_accel.py       six-orientation accel characterization
  known_yaw_rotation.py          known-angle yaw rotation tests
  static_after_motion.py         static-after-motion bias settling tests
  walking_tests.py               straight, known-path, and out-and-back walking checks
  plot_csv.py                    helper for plotting/cutting gravity CSV ranges
```

## Input CSV Format

Required columns:

```text
timestamp_s or timestamp
gyro_x, gyro_y, gyro_z
accel_x, accel_y, accel_z
```

Optional but recommended columns:

```text
user_accel_x, user_accel_y, user_accel_z
gravity_x, gravity_y, gravity_z
roll, pitch, yaw
mag_accuracy
```

Notes:

- `accel_*` is treated as fused acceleration, usually `userAcceleration + gravity`.
- `user_accel_*` is treated as gravity-removed acceleration.
- Accelerometer static bias from six-orientation tests uses fused acceleration / gravity, not `user_accel_*`.
- Static-flat user-accel bias uses `user_accel_*`, not fused `accel_*`.

## Configure Tests

Open `main.py` and edit the hardcoded lists near the top:

```python
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
```

Multiple repetitions are supported by adding more CSVs to the same list:

```python
SIX_ORIENTATION_CSVS = {
    "x_up": [
        TESTS_DIR / "+x_1.csv",
        TESTS_DIR / "+x_2.csv",
        TESTS_DIR / "+x_3.csv",
    ],
}
```

Known yaw rotations are also configured as a list. Use signed angles. The current convention in `main.py` is left turns positive and right turns negative:

```python
KNOWN_YAW_ROTATION_CSVS = [
    YawRotationCsv(TESTS_DIR / "90_left_1.csv", true_rotation_deg=90.0),
    YawRotationCsv(TESTS_DIR / "90_right_1.csv", true_rotation_deg=-90.0),
]
```

For 180-degree and 360-degree tests, keep the sign consistent with the actual turn direction. A mislabeled sign can create fake 360-degree errors.

## Run Characterization

From the repo root:

```bash
./.venv/bin/python "IMU Characterization/main.py"
```

The runner ignores missing CSVs in the configured lists. If nothing configured exists, it raises an error.

## What The Results Include

`static_flat`:

- duration and sample count
- phone flatness from gravity
- gyro bias and noise
- user-accel bias and noise
- fused accel mean and noise
- attitude drift
- gyro-integrated yaw drift
- Allan/noise model estimates when the recording is long enough

`six_orientation_accel`:

- per-pose fused accel mean
- per-pose user accel mean
- gravity mean
- dominant axis checks
- cross-axis error
- estimated accel bias and scale from positive/negative axis pairs
- warnings for missing poses or suspicious labels

`known_yaw_rotation`:

- Core Motion yaw delta/error
- raw gyro-integrated yaw delta/error
- bias-corrected gyro yaw delta/error
- dominant gyro axis
- flatness during rotation
- summary MAE/bias
- preferred heading source recommendation

`static_after_motion`:

- gyro bias before and after motion
- bias shift
- user-accel bias shift
- after-motion yaw drift

Walking tests:

- rough step/path diagnostics for straight walks, known paths, closed loops, and out-and-back runs
- these are diagnostics, not full PDR validation

`recommended_corrections`:

- gyro bias to subtract
- whether to prefer user acceleration for step detection
- preferred heading source
- whether gyro scale correction is recommended
- magnetometer policy
- reminder that sensor noise is not the same as PDR process noise

## Plot Or Cut A CSV

`plot_csv.py` plots gravity columns and can write a cut CSV using 1-based data-row indices.

```bash
./.venv/bin/python "IMU Characterization/plot_csv.py" static_rest.csv
```

Save a row range to a new CSV:

```bash
./.venv/bin/python "IMU Characterization/plot_csv.py" static_rest.csv \
  --start-row 100 \
  --end-row 5000 \
  --output "IMU Characterization/input/static_rest_cut.csv" \
  --no-show
```

Save a plot image:

```bash
./.venv/bin/python "IMU Characterization/plot_csv.py" +x.csv \
  --plot-output "IMU Characterization/results/+x_gravity.png" \
  --no-show
```

## Practical Recording Notes

- For static-flat, keep the phone flat and motionless. Longer recordings improve Allan/noise estimates.
- For six orientation, each pose should be stationary. Record one CSV per pose or multiple repetitions per pose.
- For known yaw rotations, start still, rotate by the known angle, then end still.
- For PDR-bound walking runs, include a few still seconds at the beginning if you want per-run gyro bias estimation later.
- Do not interpret fused `accel_z` near +/-1 g as accelerometer bias; that is mostly gravity.
