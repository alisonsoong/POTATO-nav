# PassiveNav CSV export reference

This document describes the files and columns produced when you export a run from the **PassiveNav** tab (JSON plus one or two CSV files). It also explains how those columns relate to the **IMU characterization** flows in the other tab.

## Files you get

| File | Contents |
|------|-----------|
| `*_imu.csv` | One row per device-motion sample (~50 Hz by default). Fused IMU, raw accel/gyro, ARKit snapshot columns, and **Unix** timestamps for alignment with external logs (e.g. RFID reader). |
| `*.json` | Full run metadata (`startedAt`, `endedAt`, `name`, …) plus the same samples and the full `arkitFrames` array. |
| `*_arkit.csv` | Present only if ARKit produced at least one frame. Full-rate camera poses (same layout as the ARKit evaluation bundle’s `arkit.csv`). |

## Time columns (important for RFID merge)

All **primary** alignment times use **Unix time**: seconds since `1970-01-01 00:00:00 UTC`, as `TimeInterval` / `Double` (fractional seconds allowed). This matches a typical “seconds since epoch” field from another device if that device also uses UTC epoch time.

| Column | File | Meaning |
|--------|------|--------|
| `unix_timestamp_s` | `*_imu.csv` | Wall-clock time when this IMU row was recorded (`Date().timeIntervalSince1970` at sample time). **Use this to join with RFID CSV timestamps.** |
| `cm_motion_timestamp_s` | `*_imu.csv` | Apple **Core Motion** `CMDeviceMotion.timestamp` (sensor / monotonic clock). **Not** Unix time; useful only for spacing samples within the motion subsystem. |
| `elapsed_since_run_start_s` | `*_imu.csv` | Seconds since the run’s `startedAt` from the JSON (`Date` difference). Handy for quick in-run plots; for cross-device sync prefer `unix_timestamp_s`. |
| `unix_timestamp_s` | `*_arkit.csv` | Wall-clock time when the ARKit frame was delivered to the app. |
| `timestamp_s` | `*_arkit.csv` | Seconds since recording start on a **process-uptime** style basis (legacy internal normalization). Use `unix_timestamp_s` for RFID alignment. |
| `startedAt` / `endedAt` | `*.json` | ISO-encoded `Date` values for the run boundaries. |

**Clock note:** Phone and RFID reader must agree on absolute time (NTP, GPS time, or post-hoc offset estimation) if you need sub-100 ms alignment across devices. Unix timestamps only make the **representation** compatible.

---

## `*_imu.csv` columns (in column order)

### Time

1. **`unix_timestamp_s`** — Unix epoch seconds for this sample (RFID join key).
2. **`cm_motion_timestamp_s`** — Core Motion device-motion timestamp (not epoch).
3. **`elapsed_since_run_start_s`** — Seconds after run start (`Date`-based).

### Fused “device motion” (same family as characterization tab)

These come from **`CMMotionManager` `CMDeviceMotion`** (attitude + gravity + user acceleration fused by Apple). This is the same **class of API** used when you record runs in the **Data / characterization** tab (`MotionRecorder` → `IMUSample`), though that tab’s CSV uses slightly different column names (`accel_x` there = linear specific force = user + gravity, same physics as `fused_accel_*` here).

| Column | Description |
|--------|-------------|
| `user_accel_x`, `user_accel_y`, `user_accel_z` | Linear acceleration with gravity removed (device frame). **Units: g** (multiples of nominal Earth gravity; 1 g ≈ 9.80665 m/s²). |
| `gravity_x`, `gravity_y`, `gravity_z` | Estimated gravity vector (device frame). **Units: g** (magnitude ≈ 1 when the phone is still). |
| `fused_accel_x`, `fused_accel_y`, `fused_accel_z` | `user_accel + gravity` in this app (= specific force / “accelerometer” sense). **Units: g.** Same as **`accel_x/y/z`** in the characterization export. |
| `gyro_x`, `gyro_y`, `gyro_z` | Angular rate from **device motion** (device frame). **Units: rad/s.** |
| `roll`, `pitch`, `yaw` | Orientation from fused **attitude**. **Units: rad.** Reference frame: `.xArbitraryCorrectedZVertical` for PassiveNav. |
| `mag_x`, `mag_y`, `mag_z` | Calibrated magnetic field (device frame). **Units: microtesla (µT)** per Core Motion. |
| `mag_accuracy` | Raw `CMMagneticFieldCalibrationAccuracy.rawValue` stored as `Double` (**unitless** enum code, not µT). |

### Raw / “less processed” IMU (not used for characterization CSV)

These are **separate** streams: **`CMAccelerometerData`** and **`CMGyroData`**. They are **not** attitude-corrected and do **not** appear in the default characterization-tab CSV (that tab logs fused `CMDeviceMotion` only). Treat them as closer to “basic” phone IMU channels for comparison or custom fusion.

| Column | Description |
|--------|-------------|
| `raw_accel_x`, `raw_accel_y`, `raw_accel_z` | Raw accelerometer (includes gravity). **Units: g** (same convention as `CMAccelerometerData.acceleration`). |
| `raw_gyro_x`, `raw_gyro_y`, `raw_gyro_z` | Raw gyro. **Units: rad/s.** |

### ARKit snapshot (copied onto every IMU row)

ARKit updates at a lower rate than 50 Hz. On each IMU row we copy the **latest** pose; values **repeat** until the next ARKit frame.

| Column | Description |
|--------|-------------|
| `arkit_x_m`, `arkit_y_m`, `arkit_z_m` | Camera position in ARKit world space. **Units: meters (m).** |
| `arkit_yaw_rad` | Yaw from camera forward in the horizontal plane (**radians**, app convention). |
| `arkit_timestamp_s` | ARKit pose time **seconds** since record start (session-relative; same basis as `timestamp_s` in `*_arkit.csv`). |
| `arkit_unix_timestamp_s` | **Unix epoch seconds** for that ARKit frame (when the frame was received). |
| `arkit_tracking_state`, `arkit_tracking_reason` | e.g. `normal`, `limited`, `not_available`, plus reason text when limited. |

For **highest-rate ground truth**, use **`*_arkit.csv`** (or `arkitFrames` in JSON), not only the IMU-row copies.

---

## `*_arkit.csv` columns

Header order:

`unix_timestamp_s`, `timestamp_s`, `raw_frame_timestamp_s`, `callback_uptime_s`, `tracking_state`, `tracking_reason`, `x_m`, `y_m`, `z_m`, `yaw_rad`, then `m00`…`m33` (row-major 4×4 **camera** transform in world coordinates).

**`*_arkit.csv` units:** `unix_timestamp_s` = Unix **seconds**; `timestamp_s` = **seconds** since record start; `raw_frame_timestamp_s` = ARKit frame time **seconds**; `callback_uptime_s` = `systemUptime` **seconds**; `x_m`, `y_m`, `z_m` = **meters**; `yaw_rad` = **radians**; `m00`–`m33` = **dimensionless** transform (rotation + translation; translation components in **meters** in the last column).

- **`unix_timestamp_s`**: wall-clock epoch time for the frame (join with RFID).
- **`timestamp_s`**: seconds since record start (uptime-based normalization inside the app).
- **`raw_frame_timestamp_s`**: `ARFrame.timestamp` from ARKit.
- **`callback_uptime_s`**: `ProcessInfo.processInfo.systemUptime` when the delegate ran.

---

## Path preview (UI)

The PassiveNav tab shows a **top-down path** (horizontal **X** vs **−Z**) built from the same poses as the ARKit tab’s path view. There is **no** live camera preview tile; the camera still runs in the background for world tracking when ARKit is supported.

---

## Quick “which columns for my analysis?”

| Goal | Columns / file |
|------|------------------|
| Align phone to RFID by time | `unix_timestamp_s` on `*_imu.csv` and on `*_arkit.csv` |
| Same physics as characterization `accel_*` / gyro / attitude | `fused_accel_*`, `gyro_*`, `roll`, `pitch`, `yaw`, … |
| Minimal fusion / “rawer” phone IMU | `raw_accel_*`, `raw_gyro_*` |
| Best ARKit trajectory | `*_arkit.csv` or JSON `arkitFrames` |
