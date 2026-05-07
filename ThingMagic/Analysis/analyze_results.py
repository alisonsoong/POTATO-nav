#!/usr/bin/env python3
"""
Analyze ThingMagic Results CSV outputs.

Usage:
  python analyze_results.py
  python analyze_results.py --results-dir ../Results
  python analyze_results.py --test TestMetadataRead
"""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Dict, Iterable, List, Optional


@dataclass
class Row:
    timestamp_ms: Optional[int]
    epc: Optional[str]
    antenna: Optional[int]
    rssi: Optional[float]
    frequency: Optional[int]
    phase: Optional[float]
    read_count: Optional[int]
    theta_deg: Optional[float] = None
    valid: Optional[bool] = None


def to_int(v: Optional[str]) -> Optional[int]:
    if v is None:
        return None
    v = v.strip()
    if v == "":
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


def to_float(v: Optional[str]) -> Optional[float]:
    if v is None:
        return None
    v = v.strip()
    if v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return None


def to_bool(v: Optional[str]) -> Optional[bool]:
    if v is None:
        return None
    s = v.strip().lower()
    if s == "true":
        return True
    if s == "false":
        return False
    return None


def test_type_from_name(path: Path) -> str:
    return path.name.split("_")[0]


def parse_key_value_line(line: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for part in line.split(","):
        part = part.strip()
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def parse_file(path: Path) -> List[Row]:
    rows: List[Row] = []
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    if not lines:
        return rows

    # AoAReader CSV
    if lines[0].startswith("timestamp_ms,epc,freq_hz,phase1_rad,phase2_rad"):
        reader = csv.DictReader(lines)
        for r in reader:
            rows.append(
                Row(
                    timestamp_ms=to_int(r.get("timestamp_ms")),
                    epc=r.get("epc"),
                    antenna=None,
                    rssi=None,
                    frequency=to_int(r.get("freq_hz")),
                    phase=None,
                    read_count=None,
                    theta_deg=to_float(r.get("theta_deg")),
                    valid=to_bool(r.get("valid")),
                )
            )
        return rows

    # Metadata/phase/frequency/live/two-antenna CSV
    if lines[0].startswith("timestamp_ms,epc,"):
        reader = csv.DictReader(lines)
        for r in reader:
            # Skip non-data lines accidentally written by some tests.
            if r.get("timestamp_ms") is None or to_int(r.get("timestamp_ms")) is None:
                continue
            rows.append(
                Row(
                    timestamp_ms=to_int(r.get("timestamp_ms")),
                    epc=r.get("epc"),
                    antenna=to_int(r.get("antenna")),
                    rssi=to_float(r.get("rssi")),
                    frequency=to_int(r.get("frequency")),
                    phase=to_float(r.get("phase")),
                    read_count=to_int(r.get("read_count")),
                )
            )
        return rows

    # Basic read key=value format
    for ln in lines:
        if "EPC=" not in ln:
            continue
        kv = parse_key_value_line(ln)
        rows.append(
            Row(
                timestamp_ms=to_int(kv.get("timestamp_ms")),
                epc=kv.get("EPC"),
                antenna=to_int(kv.get("antenna")),
                rssi=to_float(kv.get("rssi")),
                frequency=None,
                phase=None,
                read_count=to_int(kv.get("read_count")),
            )
        )
    return rows


def summarize_rows(rows: List[Row]) -> Dict[str, object]:
    epcs = [r.epc for r in rows if r.epc]
    rssis = [r.rssi for r in rows if r.rssi is not None]
    freqs = [r.frequency for r in rows if r.frequency is not None]
    phases = [r.phase for r in rows if r.phase is not None]
    valids = [r.valid for r in rows if r.valid is not None]
    thetas = [r.theta_deg for r in rows if r.theta_deg is not None]
    ants = [r.antenna for r in rows if r.antenna is not None]
    return {
        "rows": len(rows),
        "unique_epcs": len(set(epcs)),
        "rssi_avg": round(mean(rssis), 2) if rssis else None,
        "freq_unique": len(set(freqs)),
        "phase_span": round(max(phases) - min(phases), 2) if phases else None,
        "antennas": sorted(set(ants)),
        "valid_pct": round((sum(1 for v in valids if v) / len(valids)) * 100.0, 2) if valids else None,
        "theta_avg_deg": round(mean(thetas), 2) if thetas else None,
    }


def print_summary(results: Dict[str, Dict[str, object]]) -> None:
    if not results:
        print("No result files found.")
        return
    print("Per-file summary:\n")
    for name, s in sorted(results.items()):
        print(
            f"- {name}: rows={s['rows']}, unique_epcs={s['unique_epcs']}, "
            f"antennas={s['antennas']}, freq_unique={s['freq_unique']}, "
            f"rssi_avg={s['rssi_avg']}, phase_span={s['phase_span']}, "
            f"valid_pct={s['valid_pct']}, theta_avg_deg={s['theta_avg_deg']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", default="../Results", help="Path to Results folder.")
    parser.add_argument("--test", default=None, help="Optional test type filter, e.g. TestPhaseRead.")
    args = parser.parse_args()

    root = Path(args.results_dir)
    if not root.exists():
        raise SystemExit(f"Results directory not found: {root}")

    out: Dict[str, Dict[str, object]] = {}
    files = sorted(root.glob("*.csv"))
    for f in files:
        t = test_type_from_name(f)
        if args.test and t != args.test:
            continue
        rows = parse_file(f)
        out[f.name] = summarize_rows(rows)

    print_summary(out)


if __name__ == "__main__":
    main()

