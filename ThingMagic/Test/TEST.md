# ThingMagic Java Test Scripts

## Assumptions
- Windows 10
- Java installed (`javac` and `java` in PATH)
- Reader works in Universal Reader Assistant (URA)
- COM port is `COM4`
- Region is `NA`
- Protocol is `Gen2`

## Compile from `ThingMagic/Test`
Use this classpath:

`"../Compiled;../mercuryapi/java/mercuryapi.jar;../mercuryapi/java/ltkjava-1.0.0.6.jar"`

Create output folders (one-time):

`mkdir ../Compiled ../Results`

Compile all test files into `ThingMagic/Compiled`:

`javac -d ../Compiled -cp ".;../mercuryapi/java/mercuryapi.jar;../mercuryapi/java/ltkjava-1.0.0.6.jar" TestBasicRead.java TestMetadataRead.java TestPhaseRead.java TestFrequencyRead.java TestTwoAntennaRead.java TestLiveRead.java`

## Output Files (No PowerShell Variables Needed)
All `ThingMagic/Test` Java tests now save to `ThingMagic/Results` by default using:

`../Results/<TestName>_yyyyMMdd_HHmmss.csv`

Examples:
- `TestBasicRead_20260506_204955.csv`
- `TestPhaseRead_20260506_205104.csv`

You can override the output filename with `--out your_file.csv`.

## EPC Filter Addlist
All tests now only process EPCs listed in `ThingMagic/addlist.csv` (default path: `../addlist.csv` when run from `ThingMagic/Test`).

Current `addlist.csv` contains:
- `E200001D0802003019700604`

Optional override:
- `--addlist ../addlist.csv`

Discovery mode (ignore addlist) for `TestBasicRead`:
- `--no-addlist`

## Show Every Read (`--raw`)
Use `--raw` to request unfiltered per-read streaming by setting:
- `/reader/tagReadData/enableReadFilter=false`

Supported in all test scripts and `AoAReader`.

## Recommended Test Sequence (Antenna Bring-Up -> AoA)

### Step 1 - Basic connectivity on antenna 1
Run:

`java -cp "../Compiled;../mercuryapi/java/mercuryapi.jar;../mercuryapi/java/ltkjava-1.0.0.6.jar" TestBasicRead --uri tmr:///COM4 --ant 1 --duration 5000 --raw`

If you want to discover tags without filtering:

`java -cp "../Compiled;../mercuryapi/java/mercuryapi.jar;../mercuryapi/java/ltkjava-1.0.0.6.jar" TestBasicRead --uri tmr:///COM4 --ant 1 --duration 5000 --no-addlist --raw`

Expected:
- Reader connects and EPC lines appear.
- `antenna=1` entries are shown.
- Results auto-save to `TestBasicRead_*.csv`.

### Step 2 - Metadata check on antenna 1
Run:

`java -cp "../Compiled;../mercuryapi/java/mercuryapi.jar;../mercuryapi/java/ltkjava-1.0.0.6.jar" TestMetadataRead --uri tmr:///COM4 --ant 1 --duration 5000 --raw`

If you want to ignore addlist filtering:

`java -cp "../Compiled;../mercuryapi/java/mercuryapi.jar;../mercuryapi/java/ltkjava-1.0.0.6.jar" TestMetadataRead --uri tmr:///COM4 --ant 1 --duration 5000 --no-addlist --raw`

Expected:
- CSV header and rows print.
- `frequency` and `phase` fields are present (`-1` if unsupported).
- Results auto-save to `TestMetadataRead_*.csv`.

### Step 3 - Phase stability on antenna 1
Run:

`java -cp "../Compiled;../mercuryapi/java/mercuryapi.jar;../mercuryapi/java/ltkjava-1.0.0.6.jar" TestPhaseRead --uri tmr:///COM4 --ant 1 --duration 10000 --raw`

Expected:
- Phase trends visible over time.
- Some jumps are normal (wrap/hopping/multipath).
- Results auto-save to `TestPhaseRead_*.csv`.

### Step 4 - Frequency behavior
Run:

`java -cp "../Compiled;../mercuryapi/java/mercuryapi.jar;../mercuryapi/java/ltkjava-1.0.0.6.jar" TestFrequencyRead --uri tmr:///COM4 --ant 1 --duration 5000 --raw`

Expected:
- Frequency-related parameter info is printed.
- Read rows still print if fixed-frequency configuration is unsupported.
- Results auto-save to `TestFrequencyRead_*.csv`.

### Step 5 - Continuous stream on antenna 1
Run forever (stop with `Ctrl+C`):

`java -cp "../Compiled;../mercuryapi/java/mercuryapi.jar;../mercuryapi/java/ltkjava-1.0.0.6.jar" TestLiveRead --uri tmr:///COM4 --ant 1 --duration 0 --raw`

Expected:
- Continuous rows print until stopped.
- Results auto-save to `TestLiveRead_*.csv`.

### Step 6 - Two-antenna validation (ports 1 and 2)
Run:

`java -cp "../Compiled;../mercuryapi/java/mercuryapi.jar;../mercuryapi/java/ltkjava-1.0.0.6.jar" TestTwoAntennaRead --uri tmr:///COM4 --duration 5000 --raw`

Expected:
- `antenna` column contains both `1` and `2`.
- Results auto-save to `TestTwoAntennaRead_*.csv`.

### Step 7 - Transition to AoA (`ThingMagic/Reader/AoAReader.java`)
From `ThingMagic/Reader`:

`javac -d ../Compiled -cp ".;../mercuryapi/java/mercuryapi.jar;../mercuryapi/java/ltkjava-1.0.0.6.jar" ../Reader/AoAReader.java`

`java -cp "../Compiled;../mercuryapi/java/mercuryapi.jar;../mercuryapi/java/ltkjava-1.0.0.6.jar" AoAReader --uri tmr:///COM4 --ant1 1 --ant2 2 --duration 0 --spacing-m 0.16 --phase-offset-rad 0.0 --pair-window-ms 200 --raw`

For AoA formula/calibration/limitations, see `../Reader/DEPLOY.md`.

## Optional: explicit output filename examples
- `java -cp "../Compiled;../mercuryapi/java/mercuryapi.jar;../mercuryapi/java/ltkjava-1.0.0.6.jar" TestPhaseRead --uri tmr:///COM4 --ant 1 --duration 10000 --out ../Results/phase_step3.csv`
- `java -cp "../Compiled;../mercuryapi/java/mercuryapi.jar;../mercuryapi/java/ltkjava-1.0.0.6.jar" TestTwoAntennaRead --uri tmr:///COM4 --duration 5000 --out ../Results/ant12_step6.csv`
