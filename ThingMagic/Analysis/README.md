# ThingMagic Results Analysis

Python helpers for analyzing CSV files written to `ThingMagic/Results`.

## Files
- `analyze_results.py` - scans the whole `Results` folder and prints per-file summaries.
- `phase_frequency_analysis.py` - analyzes one metadata/phase CSV by frequency buckets.

## Usage
Run from `ThingMagic/Analysis`.

### 1) Summarize all results
`python analyze_results.py`

Optional:
- `python analyze_results.py --results-dir ../Results`
- `python analyze_results.py --test TestPhaseRead`

### 2) Analyze phase vs frequency for one file
`python phase_frequency_analysis.py --file ../Results/TestPhaseRead_20260506_212242.csv`

Optional EPC filter:
`python phase_frequency_analysis.py --file ../Results/TestPhaseRead_20260506_212242.csv --epc E200001D0802003019700604`

## Notes
- These scripts use only Python standard library (no extra installs).
- `analyze_results.py` handles:
  - `TestBasicRead` key/value rows
  - metadata-style CSV rows
  - `AoAReader` CSV rows
