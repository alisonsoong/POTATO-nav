from __future__ import annotations

import os
import tempfile
from pathlib import Path

import numpy as np

from .models import ARKitTrajectory, TagMap


def save_trajectory_plot(
    path: Path,
    arkit: ARKitTrajectory,
    baseline_points: np.ndarray,
    pf_points: np.ndarray,
    tag_map: TagMap,
    title: str,
) -> None:
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "matplotlib"))
    os.environ.setdefault("XDG_CACHE_HOME", str(Path(tempfile.gettempdir()) / "fontconfig-cache"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.plot(arkit.points_map[:, 0], arkit.points_map[:, 1], color="tab:blue", label="ARKit")
    ax.plot(baseline_points[:, 0], baseline_points[:, 1], color="tab:orange", marker="o", markersize=2, label="IMU-only")
    ax.plot(pf_points[:, 0], pf_points[:, 1], color="tab:green", marker="o", markersize=2, label="RFID+IMU PF")
    ax.scatter([0.0], [0.0], color="black", s=40, label="start/end")

    tags = tag_map.tags
    ax.scatter(tags["x_m"], tags["y_m"], color="tab:red", marker="x", s=50, label="tags")
    for row in tags.itertuples(index=False):
        ax.text(float(row.x_m), float(row.y_m), str(row.tag_id), fontsize=8, ha="left", va="bottom")

    ax.set_title(title)
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.axis("equal")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
