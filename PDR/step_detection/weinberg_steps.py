import numpy as np

from config import StepModelConfig

def estimate_step_lengths_weinberg(
    amag_f: np.ndarray,
    peaks: np.ndarray,
    fs: float,
    k: float = 0.45,
) -> np.ndarray:
    lengths = []
    half_window = max(1, int(0.25 * fs))

    for peak in peaks:
        lo = max(0, peak - half_window)
        hi = min(len(amag_f), peak + half_window)

        amax = np.max(amag_f[lo:hi])
        amin = np.min(amag_f[lo:hi])
        amp = max(amax - amin, 1e-6)
        length = k * (amp ** 0.25)
        lengths.append(length)

    return np.array(lengths)


## Weinberg step length estimation
def build_weinberg_step_lengths(
    amag_f: np.ndarray,
    peaks: np.ndarray,
    fs: float,
    step_model: StepModelConfig,
) -> tuple[np.ndarray, float, str]:
    k = step_model.weinberg_k
    step_lengths = estimate_step_lengths_weinberg(amag_f, peaks, fs, k=k)
    return step_lengths, k, f"Weinberg k={k:.4f}"
