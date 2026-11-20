# Reproduce and audit the logged results

Use CPython 3.12.13 on Windows for exact exception strings and path semantics. The observations use the standard library. The external selector was run in its own virtual environment with the dependencies below. All source copies, tool data and worktrees were written on drive D. Each package has its full wheel download URL and SHA256 in sources.json or external_validation/sources.json. Network access is required to materialize missing wheels. The scripts require no credentials.

## Audit existing artifacts

From this directory with the same checkout of artifacts:

```powershell
python verify.py
python environment/check.py
```

When the downloaded releases exist, run `python verify.py --with-wheels`. To check the archived evidence inventory against its own digest list run `python manifest.py --check`. Code in verify.py rebuilds each count from selector receipts, per-check decisions, and canonical observed values. The environment check also recalculates a project-level documented-key baseline. The archive is complete for offline verification without installing pytest-testmon. Offline observed labels differ from exact prospective timing replay; OS scheduling and CPU state change timings.

## Run from fresh outputs

Use a separate copy of this directory retaining .py and .md files and the directory hierarchy. Exclude generated runs, plugin receipts, seals, source inventories, CSV, derived JSON and logs so resumable scripts do not skip completed observations. The files in this evidence bundle can be consulted as a reference. The default shared wheel and snapshot cache is D:/CodexResearch/x20-validity-releases. Override via MEMORY_VALIDITY_CACHE as needed (the separately pinned expected plugin Python is at testmon-env/Scripts/python.exe under this directory). Normal runs read wheel sources directly from each snapshot. Source acquisition chooses the first lexically sorted published pure wheel for each package/version and checks its PyPI digest; original filenames and hashes can be compared against the two inventories.

```powershell
$env:MEMORY_VALIDITY_CACHE = 'D:/CodexResearch/x20-validity-releases'
python sources.py
python roster.py
python run_observations.py
python predict.py
uv venv --python 3.12.13 "$env:MEMORY_VALIDITY_CACHE/testmon-env"
uv pip install --python "$env:MEMORY_VALIDITY_CACHE/testmon-env/Scripts/python.exe" pytest-testmon==2.3.0 pytest==8.4.2 coverage==7.10.7 packaging==26.3 pluggy==1.7.0 iniconfig==2.3.1 colorama==0.4.6 Pygments==2.21.0
python testmon_pair.py
python testmon_normal.py
python score.py
python economics.py
python posthoc_baseline.py
python external_validation/sources.py
python external_validation/roster.py
python external_validation/run_observations.py
python external_validation/predict.py
python external_validation/score_external.py
python external_validation/economics.py
python age_eval.py
python environment/external_state.py
python environment/check.py
python verify.py --with-wheels
```

The selector script copies the old source to an isolated directory, primes .testmondata, updates changed .py files, and runs the exact same IDs again. Unchanged-source checks are interleaved at the first pair in each project in normal pytest mode. Fresh pair roots are under testmon-trials in the external cache. The testmon wrappers preserve return codes, wall time, node IDs, canonical value hashes, and output. The only initial unrecoverable attempt was a plugin load command with the wrong pytest entry point. Its log is saved as plugin-initialization-failure.log. Replays must use the working module name in the two scripts, testmon.pytest_testmon. No observations were scored from the failed attempt.

Protocol and decision locks are cryptographic consistency records inside the archive, not third-party timestamp registration. Runtime fields (ns, wall time, SHA hashes over raw timing and absolute paths in logs) are expected to vary on repeat. Version lists, inputs, canonical value hashes, decisions and totals are the quantities to compare.
