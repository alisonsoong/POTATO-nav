#!/usr/bin/env bash
set -euo pipefail

CAL_DIR="Tests/Directional/Test1"
EVAL_DIR="Tests/Directional/Test2"
TAG_MAP="particle_filter/epc_to_tag_coordinates.csv"
OUT_ROOT="particle_filter/results/directional_rssi_sweep2"
PARTICLES=250
MODEL="rssi_phase"

WEAK_VALUES=(-80 -75 -70)
STRONG_VALUES=(-55 -50 -45)

mkdir -p "$OUT_ROOT"

for weak in "${WEAK_VALUES[@]}"; do
  for strong in "${STRONG_VALUES[@]}"; do
    if (( strong <= weak )); then
      continue
    fi

    weak_label="m${weak#-}"
    strong_label="m${strong#-}"
    out_dir="$OUT_ROOT/weak_${weak_label}_strong_${strong_label}"

    .venv/bin/python -m particle_filter.run \
      --calibration-dir "$CAL_DIR" \
      --eval-dir "$EVAL_DIR" \
      --tag-map "$TAG_MAP" \
      --out-dir "$out_dir" \
      --particles "$PARTICLES" \
      --rfid-measurement-model "$MODEL" \
      --rssi-weak-dbm "$weak" \
      --rssi-strong-dbm "$strong"
  done
done
