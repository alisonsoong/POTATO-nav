from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from .models import ARKitTrajectory, AntennaPolicy, TagMap


def apply_antenna_policy(reads: pd.DataFrame, policy: AntennaPolicy) -> pd.DataFrame:
    known = reads[reads["known_tag"]].copy()
    if policy.mode == "global":
        return known[known["antenna"] == int(policy.antenna)].copy()
    if policy.mode == "per_epc":
        if not policy.epc_to_antenna:
            return known.iloc[0:0].copy()
        keep = known.apply(lambda row: int(row["antenna"]) == policy.epc_to_antenna.get(str(row["epc"]), -1), axis=1)
        return known[keep].copy()
    raise ValueError(f"Unknown antenna policy: {policy.mode}")


def _closest_approach_by_epc(arkit: ARKitTrajectory, tag_map: TagMap) -> Dict[str, tuple[float, float]]:
    closest: Dict[str, tuple[float, float]] = {}
    for epc, pos in tag_map.positions_by_epc().items():
        distances = np.linalg.norm(arkit.points_map - pos, axis=1)
        index = int(np.argmin(distances))
        closest[epc] = (float(arkit.unix_t[index]), float(distances[index]))
    return closest


def _median_gap_s(group: pd.DataFrame) -> float:
    times = np.sort(group["timestamp_s"].to_numpy(dtype=float))
    if times.size < 2:
        return float("inf")
    return float(np.median(np.diff(times)))


def _pass_time(group: pd.DataFrame) -> float:
    if "rssi" in group.columns and group["rssi"].notna().any():
        return float(group.loc[group["rssi"].idxmax(), "timestamp_s"])
    return float(group["timestamp_s"].median())


def score_policy(reads: pd.DataFrame, policy: AntennaPolicy, arkit: ARKitTrajectory, tag_map: TagMap) -> Dict[str, float]:
    filtered = apply_antenna_policy(reads, policy)
    closest = _closest_approach_by_epc(arkit, tag_map)
    timing_errors: List[float] = []
    timing_offsets: List[float] = []
    closest_distances: List[float] = []
    median_gaps: List[float] = []

    for epc, group in filtered.groupby("epc"):
        pass_time = _pass_time(group)
        closest_time, closest_distance = closest.get(str(epc), (np.nan, np.nan))
        if np.isfinite(closest_time):
            timing_errors.append(abs(pass_time - closest_time))
            timing_offsets.append(float(closest_time - pass_time))
            closest_distances.append(float(closest_distance))
        median_gaps.append(_median_gap_s(group))

    read_count = int(len(filtered))
    epc_count = int(filtered["epc"].nunique()) if read_count else 0
    return {
        "read_count": float(read_count),
        "known_epc_count": float(epc_count),
        "median_gap_s": float(np.median(median_gaps)) if median_gaps else float("inf"),
        "median_pass_timing_error_s": float(np.median(timing_errors)) if timing_errors else float("inf"),
        "median_pass_time_offset_s": float(np.median(timing_offsets)) if timing_offsets else 0.0,
        "median_closest_distance_m": float(np.median(closest_distances)) if closest_distances else float("inf"),
    }


def _rank_antenna_for_epc(group: pd.DataFrame, closest_time: float) -> int:
    best_antenna = None
    best_score = float("inf")
    for antenna, ant_group in group.groupby("antenna"):
        timing_error = abs(_pass_time(ant_group) - closest_time) if np.isfinite(closest_time) else 0.0
        gap = _median_gap_s(ant_group)
        count_bonus = min(float(len(ant_group)), 500.0) / 500.0
        score = timing_error + 0.25 * min(gap, 10.0) - 0.5 * count_bonus
        if score < best_score:
            best_score = score
            best_antenna = int(antenna)
    if best_antenna is None:
        raise ValueError("Cannot rank antennas for an empty EPC group.")
    return best_antenna


def candidate_policies(reads: pd.DataFrame, arkit: ARKitTrajectory | None = None, tag_map: TagMap | None = None) -> List[AntennaPolicy]:
    known = reads[reads["known_tag"]].copy()
    policies: List[AntennaPolicy] = []
    for antenna in sorted(known["antenna"].dropna().astype(int).unique()):
        policy = AntennaPolicy(mode="global", antenna=int(antenna))
        diagnostics = score_policy(known, policy, arkit, tag_map) if arkit is not None and tag_map is not None else {
            "read_count": float(len(known[known["antenna"] == int(antenna)])),
            "known_epc_count": float(known[known["antenna"] == int(antenna)]["epc"].nunique()),
            "median_gap_s": float(np.median([_median_gap_s(group) for _, group in known[known["antenna"] == int(antenna)].groupby("epc")]))
            if not known[known["antenna"] == int(antenna)].empty
            else float("inf"),
        }
        policies.append(AntennaPolicy(mode="global", antenna=int(antenna), diagnostics=diagnostics))

    epc_to_antenna: Dict[str, int] = {}
    for epc, group in known.groupby("epc"):
        if arkit is not None and tag_map is not None:
            closest = _closest_approach_by_epc(arkit, tag_map)
            closest_time = closest.get(str(epc), (np.nan, np.nan))[0]
            epc_to_antenna[str(epc)] = _rank_antenna_for_epc(group, closest_time)
        else:
            best = group.sort_values(["rssi"], ascending=False).iloc[0] if group["rssi"].notna().any() else group.groupby("antenna").size().sort_values(ascending=False).index[0]
            epc_to_antenna[str(epc)] = int(best["antenna"]) if hasattr(best, "__getitem__") else int(best)

    if epc_to_antenna:
        policy = AntennaPolicy(mode="per_epc", epc_to_antenna=epc_to_antenna)
        diagnostics = score_policy(known, policy, arkit, tag_map) if arkit is not None and tag_map is not None else {
            "read_count": float(len(apply_antenna_policy(known, policy))),
            "known_epc_count": float(apply_antenna_policy(known, policy)["epc"].nunique()),
        }
        policies.append(AntennaPolicy(mode="per_epc", epc_to_antenna=epc_to_antenna, diagnostics=diagnostics))

    if not policies:
        raise ValueError("No known-tag RFID reads are available for antenna policy calibration.")
    return policies
