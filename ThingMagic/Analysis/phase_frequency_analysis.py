#!/usr/bin/env python3
"""
Analyze phase behavior by frequency from a single results CSV.

Usage:
  python phase_frequency_analysis.py --file ../Results/TestPhaseRead_20260506_212500.csv
  python phase_frequency_analysis.py --file ../Results/TestMetadataRead_...csv --epc E200...
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Dict, List, Optional, Tuple


def to_int(v: str) -> Optional[int]:
    try:
        return int(float(v))
    except Exception:
        return None


def to_float(v: str) -> Optional[float]:
    try:
        return float(v)
    except Exception:
        return None


def load_rows(path: Path) -> List[Dict[str, str]]:
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    if not lines or not lines[0].startswith("timestamp_ms,epc,"):
        return []
    return list(csv.DictReader(lines))


def normalize_epc(epc: str) -> str:
    # If the first 4 hex chars are a PC word, stripping can make comparisons easier.
    if len(epc) > 4 and epc[:4].isalnum():
        return epc
    return epc


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True, help="Path to one Results CSV.")
    p.add_argument("--epc", default=None, help="Optional EPC filter.")
    p.add_argument("--top-freqs", type=int, default=10, help="How many frequencies to print.")
    args = p.parse_args()

    rows = load_rows(Path(args.file))
    if not rows:
        raise SystemExit("Input file does not look like metadata/phase CSV.")

    by_freq: Dict[int, List[Tuple[int, float, str]]] = defaultdict(list)
    total = 0
    for r in rows:
        epc = r.get("epc", "")
        if args.epc and epc != args.epc:
            continue
        ts = to_int(r.get("timestamp_ms", ""))
        f = to_int(r.get("frequency", ""))
        ph = to_float(r.get("phase", ""))
        if ts is None or f is None or ph is None:
            continue
        by_freq[f].append((ts, ph, epc))
        total += 1

    print(f"Total usable rows: {total}")
    print(f"Unique frequencies: {len(by_freq)}")
    print("")

    ranked = sorted(by_freq.items(), key=lambda kv: len(kv[1]), reverse=True)[: args.top_freqs]
    print("Top frequencies:")
    for freq, pts in ranked:
        phases = [p[1] for p in pts]
        span = max(phases) - min(phases)
        print(f"- {freq} kHz: n={len(pts)}, phase_mean={mean(phases):.2f}, phase_span={span:.2f}")


if __name__ == "__main__":
    main()

