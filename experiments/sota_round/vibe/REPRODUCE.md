# Reproducing the VibeMemBench executable pilot

The study uses the public VibeMemBench release, its pinned mini-SWE-agent, the two original SWE-rebench images, the release's original test patches and the unmodified public evaluator. The cohort and operating limits are in `cohort.json`, `amendment_8b.json` and `prospective_27b.json`. The official paper describes a reference-solver-selected population of targets. These two Python repositories were deliberately chosen by ID as inexpensive targets. Report comparisons as paired results on these targets.

## Prerequisites

Use the immutable links and file digests in `provenance.json`. Place VibeMemBench at `$env:VIBE_RELEASE`, its dataset at `benchmark/test.parquet`, and the pinned agent source at `mini-swe-agent/` in that tree. Generate each memory system's results into the original `outputs/memory/<method>/python/<target>/memory.txt` using the memory-stage artifact. The release uses the ordinary injected distractor from its own source. The datasets, images and model checkpoints are independently available from the authors.

The runner here uses Windows Python 3.12, a WSL2 distribution named `CodexX20MSR` with Docker Engine and Python 3, and a Docker client on Windows pointing to the same Linux daemon over loopback. The Docker image layers live in the WSL ext4 volume. Pull the original image tags from `cohort.json` and verify the immutable digests in the registry JSON files. Install the pinned mini-agent, the harness dependencies, and the small local bridge as an editable Python package in the same Windows environment. Versions actually used are in `windows_packages.txt`. Point the local solver to the frozen model and port in the respective protocol. The 8B service details are in the sibling `vibe_solver` artifact. The larger model's service has a separate release.

## Running

For the two 27B cohorts, the continuation used `resume_evaluation.ps1 -Phase main` and then `resume_evaluation.ps1 -Phase in_loop`. Each command accepts `-GradeOnly` for independent reevaluation and checking. The second run uses the separate loopback intervention shim on port 18841, whose health response and exact model inputs are audited. WSL runs only the pre-pinned images in the project-specific CodexX20MSR distro, with local Docker listening on its Unix socket and on Windows loopback port 23767. See qwen38_27b/interruption_accounting.json for separately charged lost-attempt tokens and in_loop/paired_timing_audit.json for differences between observations in same-seed natural trials.

```powershell
# Set VIBE_RELEASE, local Python environment and scratch/cache location on D first.
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:PYTHONUTF8 = '1'
$env:DOCKER_HOST = 'tcp://127.0.0.1:23767'
$env:VIBE_SOLVER_PROTOCOL = (Resolve-Path .\amendment_8b.json).Path
python .\pilot_driver.py
$bridge = (Resolve-Path .\wsl_eval.py).Path
python "$env:VIBE_RELEASE/scripts/run_eval.py" --runs-dir "$env:VIBE_RELEASE/outputs/pilot_agent" --dataset "$env:VIBE_RELEASE/benchmark/test.parquet" --image-pool-size 0 --image-workers 1 --seed-workers 1 --eval-script "$bridge"
python .\summarize.py
```

For 27B, select `prospective_27b.json` and replace `pilot_agent` with `pilot_qwen38_27b` in the grader invocation. The upstream evaluator returns a nonzero exit code when predictions fail its tests. It also writes a row and an evaluation report per completed assignment, which the summarizer reconciles. `python checker_controls.py` runs the authored solution and an inert marker-file-only patch for each target in a separate grader directory. `python provenance.py` rechecks both immutable image digests and checkouts.

The published SWE-bench agent template and runtime both hardcode `/testbed`. In each original image the true Git checkout was located at the image's repository-specific working directory. Both lacked `/testbed`. The bridge starts the original image without network, verifies its HEAD against the dataset, replaces the newly created empty `/testbed` with a symlink into the verified working tree, then runs the exact published agent command. It does this in disposable containers; no derived image is built. The evaluator uses its own original working directory and pristine image. The WSL forwarding shim only translates host paths so that the evaluator can bind its temporary patch directory from the Linux daemon's filesystem. The checks independently accepted both authored solutions and rejected both inert controls.

The solver receives a parquet projection containing six allowed columns, recorded in `provenance.json`. Mini-SWE-agent passes only `problem_statement` into its user task prompt. The target gold patch, test patch and expected test lists are available to the scorer. Each retrieval arm includes one earlier historical record. The images expose no named Git refs; the verified detached HEAD ancestry is recorded in the provenance manifest.

The 8B execution archive includes all eight original trajectories, the four interrupted trajectories, submitted patches in the native trajectory format, exact grader reports, actual unit-test logs when present, and separate calibration reports. It omits full input parquets and the grader's inputs containing reference patches. Empty submissions are counted as unresolved; the official scorer reports a missing patch before running tests for these assignments. `attempts.jsonl` records each outcome and the test execution indicator. The ZIP's digest is in `results.json`. For 8B, the original host restarted before seed 0 finished; four incomplete attempts were archived and retried on the same paired seed. The other 24 planned tasks are explicitly recorded as administratively unrun. The resumed schedule ran one solver worker at a time.
