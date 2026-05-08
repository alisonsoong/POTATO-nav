1. take all csvs of measurements and place in a folder
ex. PDR/walks/

2. preprocess raw IMU csvs before PDR

Use preprocessing when you want to create a corrected CSV but not run PDR yet. This keeps the original columns and adds corrected / PDR-ready columns such as:

- `timestamp_relative_s`
- `gyro_*_bias_corrected`
- `step_accel_mag`
- `step_accel_mag_filtered`
- `yaw_unwrapped`
- `heading_gyro_bias_corrected`
- `heading_selected`
- `tilt_from_flat_deg`

Run preprocessing only:

```bash
./.venv/bin/python PDR/preprocessing/main.py PDR/walks/L_1.csv
```

By default this writes:

```text
PDR/walks/L_1_corrected.csv
PDR/walks/L_1_corrected.correction_report.json
```

To choose explicit output paths:

```bash
./.venv/bin/python PDR/preprocessing/main.py \
  PDR/walks/L_1.csv \
  --output PDR/walks/L_1_corrected.csv \
  --report-json PDR/walks/L_1_corrected.correction_report.json
```

Useful preprocessing options:

```bash
# Use Core Motion yaw as heading_selected instead of gyro-integrated heading.
./.venv/bin/python PDR/preprocessing/main.py PDR/walks/L_1.csv --heading-source coremotion_yaw

# Force the static-flat characterization gyro bias instead of trying the first stationary seconds.
./.venv/bin/python PDR/preprocessing/main.py PDR/walks/L_1.csv --use-characterization-gyro-bias

# Change the initial stationary window used for per-run gyro bias estimation.
./.venv/bin/python PDR/preprocessing/main.py PDR/walks/L_1.csv --initial-stationary-s 5

# Opt in to subtracting the tiny static user-accel bias before step detection.
./.venv/bin/python PDR/preprocessing/main.py PDR/walks/L_1.csv --subtract-user-accel-bias
```

Current recommended default: do not subtract user-accel bias for step detection. Use raw `user_accel_*` magnitude plus bandpass filtering. Gyro bias is estimated from the first stationary seconds only if that segment looks stationary; otherwise preprocessing falls back to the static-flat characterization bias and records a warning in the report JSON.

3. run PDR on a corrected CSV

The PDR runner now expects corrected columns when they are available. First preprocess:

```bash
./.venv/bin/python PDR/preprocessing/main.py PDR/walks/L_1.csv
```

Then run PDR:

```bash
./.venv/bin/python PDR/pdr_run.py PDR/walks/L_1_corrected.csv
```

If no CSV path is passed, `PDR/pdr_run.py` uses the hardcoded `CONFIG.csv_file` in `PDR/pdr_run.py`.

The PDR plot overlays:

- before corrections: raw `user_accel_*` + Core Motion `yaw`
- after corrections: `step_accel_mag_filtered` + bias-corrected gyro heading

4. calibrate your weinberg with a csv of your straight walk with the ground truth distance covered
- ensure that the number of detected steps align with the ground truth number of steps taken in the walk
- this will produce a k-value for Weinberg variable step length detection.

```bash
./.venv/bin/python PDR/calibrate_weinberg.py --csv_file [CSV filepath] --ground_truth_distance_m [distance walked in m]
```

5. be sure to paste in the StepModelConfig with your k value

## ARKit evaluation

Export an ARKit bundle from the iOS app. The bundle should contain `metadata.json`, `arkit.csv`, and, for combined IMU + ARKit runs, `imu.csv`.
combined IMU + ARKit runs will appear and be available for export in the ARKit app. I also recommend putting input data in PDR/arkit so that it automatically gets gitignored

Validate that ARKit logging looks right:

```bash
python PDR/evaluate_arkit_pdr.py path/to/exported_bundle --arkit-only
```

If the beginning or end includes setup/stop motion, trim it out:

```bash
python PDR/evaluate_arkit_pdr.py path/to/exported_bundle --arkit-only --trim-start-s 5 --trim-end-s 5
```

Evaluate PDR drift against ARKit with start-only alignment:

```bash
python PDR/evaluate_arkit_pdr.py path/to/exported_bundle --alignment start
```

For diagnostic shape comparison, use best-fit rigid alignment:

```bash
python PDR/evaluate_arkit_pdr.py path/to/exported_bundle --alignment best-fit
```

Both alignment modes use rotation + translation only. Scale is intentionally not fitted, so step-length error remains visible.
