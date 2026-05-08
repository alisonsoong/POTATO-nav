from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from turn_detection.heading import CORE_MOTION_YAW


RUN_PDR = "pdr"
CONSTANT_STEP = "constant"
WEINBERG_STEP = "weinberg"
STEP_MODELS = (CONSTANT_STEP, WEINBERG_STEP)


@dataclass(frozen=True)
class StepDetectionConfig:
    low_hz: float = 0.5
    high_hz: float = 3.0
    min_step_gap_s: float = 0.35
    prominence: float = 0.03


@dataclass(frozen=True)
class TurnDetectionConfig:
    heading_mode: str = CORE_MOTION_YAW
    rate_threshold_deg_s: float = 20.0
    min_angle_deg: float = 30.0
    min_duration_s: float = 0.2
    merge_gap_s: float = 0.15


@dataclass(frozen=True)
class StepModelConfig:
    model: str = CONSTANT_STEP
    constant_step_length_m: float = 0.7
    weinberg_k: float = 0.45


@dataclass(frozen=True)
class StartPointConfig:
    x_m: float = 0.0
    y_m: float = 0.0


@dataclass(frozen=True)
class RunnerConfig:
    mode: str = RUN_PDR
    show_plots: bool = True


@dataclass(frozen=True)
class PDRConfig:
    csv_file: Path
    runner: RunnerConfig = field(default_factory=RunnerConfig)
    start_point: StartPointConfig = field(default_factory=StartPointConfig)
    step_detection: StepDetectionConfig = field(default_factory=StepDetectionConfig)
    turn_detection: TurnDetectionConfig = field(default_factory=TurnDetectionConfig)
    step_model: StepModelConfig = field(default_factory=StepModelConfig)
    plot_title: str = "PDR Run"
