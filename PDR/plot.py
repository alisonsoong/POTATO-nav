from typing import Iterable, Optional

import matplotlib.pyplot as plt
import numpy as np

from turn_detection.heading import TurnSegment, heading_rate


def plot_calibration_dashboard(
    t: np.ndarray,
    amag_f: np.ndarray,
    peaks: np.ndarray,
    step_lengths: np.ndarray,
    title: str,
    calibrated_k: float,
) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=False)

    axes[0].plot(t, amag_f, label="Filtered acceleration magnitude")
    axes[0].plot(t[peaks], amag_f[peaks], "o", label="Detected steps")
    axes[0].set_xlabel("time [s]")
    axes[0].set_ylabel("filtered accel mag")
    axes[0].set_title(title)
    axes[0].grid(True, alpha=0.3)
    axes[0].legend()

    axes[1].plot(t[peaks], step_lengths, marker="o")
    axes[1].set_xlabel("time [s]")
    axes[1].set_ylabel("step length [m]")
    axes[1].set_title(f"Calibrated Weinberg step lengths (k={calibrated_k:.6f})")
    axes[1].grid(True, alpha=0.3)

    fig.tight_layout()
    plt.show()


def plot_pdr_dashboard(
    t: np.ndarray,
    amag_f: np.ndarray,
    peaks: np.ndarray,
    heading: np.ndarray,
    turns: Iterable[TurnSegment],
    turn_steps: np.ndarray,
    xs: np.ndarray,
    ys: np.ndarray,
    title: str,
    comparison_xs: Optional[np.ndarray] = None,
    comparison_ys: Optional[np.ndarray] = None,
    comparison_label: str = "Before corrections",
    trajectory_label: str = "After corrections",
) -> None:
    turns = list(turns)
    heading_deg = np.degrees(heading)
    rate_deg_s = np.degrees(heading_rate(t, heading))

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    axes[0, 0].plot(t, amag_f, label="Filtered acceleration magnitude")
    axes[0, 0].plot(t[peaks], amag_f[peaks], "o", label="Detected steps")
    if np.any(turn_steps):
        axes[0, 0].plot(t[peaks][turn_steps], amag_f[peaks][turn_steps], "o", label="Steps during turns")
    axes[0, 0].set_xlabel("time [s]")
    axes[0, 0].set_ylabel("filtered accel mag")
    axes[0, 0].set_title("Step detection")
    axes[0, 0].grid(True, alpha=0.3)
    axes[0, 0].legend()

    axes[0, 1].plot(t, heading_deg)
    axes[0, 1].set_xlabel("time [s]")
    axes[0, 1].set_ylabel("heading [deg]")
    axes[0, 1].set_title("Heading")
    axes[0, 1].grid(True, alpha=0.3)

    axes[1, 0].plot(t, rate_deg_s)
    axes[1, 0].set_xlabel("time [s]")
    axes[1, 0].set_ylabel("yaw rate [deg/s]")
    axes[1, 0].set_title("Turn detection")
    axes[1, 0].grid(True, alpha=0.3)

    for turn in turns:
        axes[0, 1].axvspan(turn.start_time, turn.end_time, alpha=0.2, color="tab:orange")
        axes[1, 0].axvspan(turn.start_time, turn.end_time, alpha=0.2, color="tab:orange")

    if comparison_xs is not None and comparison_ys is not None:
        axes[1, 1].plot(
            comparison_xs,
            comparison_ys,
            marker="o",
            linestyle="--",
            color="tab:gray",
            label=comparison_label,
        )
        axes[1, 1].scatter(
            comparison_xs[-1],
            comparison_ys[-1],
            color="tab:gray",
            marker="x",
            label="before end",
        )

    axes[1, 1].plot(xs, ys, marker="o", color="tab:blue", label=trajectory_label)
    if len(turn_steps) > 0:
        turn_xs = xs[1:][turn_steps]
        turn_ys = ys[1:][turn_steps]
        if len(turn_xs) > 0:
            axes[1, 1].scatter(turn_xs, turn_ys, color="tab:orange", label="Turn steps")
    axes[1, 1].scatter(xs[0], ys[0], color="tab:green", label="start")
    axes[1, 1].scatter(xs[-1], ys[-1], color="tab:blue", marker="x", label="after end")
    axes[1, 1].axis("equal")
    axes[1, 1].set_xlabel("x [m]")
    axes[1, 1].set_ylabel("y [m]")
    axes[1, 1].set_title(title)
    axes[1, 1].grid(True, alpha=0.3)
    axes[1, 1].legend()

    fig.tight_layout()
    plt.show()
