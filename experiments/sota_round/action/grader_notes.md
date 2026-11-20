# Artifact execution and assessment

The controller used the exact public task trees, author-written reference functions and author-written checkers from commit c1b15726f1153b02dda0490ca1936bb86a809514. No model calls occur in the grader. Each case receives a new fixture using the authors' harness.sandbox.restore, including a local Git initialization, add and commit. It records the initial file-tree SHA-256 for checking identical starts across the three arms of each task. [Benchmark source](https://github.com/GiulioDER/agent-memory-bench/tree/c1b15726f1153b02dda0490ca1936bb86a809514) · [Authors' reference validation](https://github.com/GiulioDER/agent-memory-bench/blob/c1b15726f1153b02dda0490ca1936bb86a809514/tests/test_references.py)

Execution used Alpine 3.22.8 in WSL2, Linux 6.18.58.1, Python 3.12.16, bubblewrap 0.12.0, Git 2.49.1 and Bash 5.2.37. Builder execution has fresh user, mount, network, IPC, PID, UTS and cgroup namespaces, no Linux capabilities, and nested user namespaces disabled. It mounts the Linux runtime read-only, a fresh writable artifact directory, the returned builder read-only, private /tmp, /dev and /proc. The sandbox probe observed only the loopback interface, the expected root directories and a cleared environment populated with HOME, LANG, PATH, PWD and TZ. No benchmark source, oracle, prior output, external host drive or Windows interop endpoint is exposed to the builder. Limits are 75 seconds wall clock, 60 seconds CPU, 1 GiB virtual memory and 16 MiB per file. The controller executes Python source literally. The reader's declared single outer fence removal applies before JSON parsing. A string echoing the example placeholder is a Python syntax error.

After the builder exits, a second offline sandbox starts. The original task checker receives the resulting artifact and its own oracle as read-only mounts through harness.checker_worker. The trusted checker side has access to the held-out files it needs. Outbound networking and host drives are absent. Checkers may execute generated helper code against staged hidden fixtures, as in the public benchmark. The protocol separates the builder and checker, and does not claim adversarial secrecy from deliberately hostile code during checker execution. Every completed checker supplies its actual verdict even when the builder exits nonzero. A malformed response is graded on the untouched fixture. Infrastructure errors, missing responses, rejection reasons, builder states and grader states are distinguishable in the ledger.

All 34 informed references passed, all 34 naive references failed, and all 34 untouched fixtures failed. An additional sandbox-surface probe passed. This validates all task runners, including the shell, Git, CRLF and oracle-driven behaviors, against positive and negative controls. The exact canary stdout and stderr are in canaries.jsonl and the evidence archive. Each generated builder is preserved in the reader log. The grader keeps the final fixture trees as tar.gz archives, excluding Git internals and preserving symlinks without following them. Each archived output includes process stdout, stderr and verdict.

## Regrading

Use Linux with bash, git, Python 3.12 and bubblewrap installed. The executable below is intended to run under Linux, including the controlling Python process. Place the public checkout at the exact commit above and choose an empty evidence directory. These commands use an existing frozen assigned.jsonl and completed logs directory. Do not run generated artifacts directly on the host.

```sh
python3 grade.py --repo /path/to/agent-memory-bench --evidence /path/to/empty-evidence --mode canaries
python3 grade.py --repo /path/to/agent-memory-bench --evidence /path/to/empty-evidence --mode model
python3 analyze_action.py --repo /path/to/agent-memory-bench
python3 bundle_grades.py --evidence /path/to/empty-evidence
```

graded.jsonl contains per-cell process status and truncated tails for convenient inspection. grading-evidence.zip includes complete process streams and artifact archives, with SHA-256 digests. action_per_cell.csv combines all 102 assignments with status, token counts and timings. action_per_task.csv aligns the three arms per fixture; action_results.json records exact paired tests, gains/losses, descriptive splits, batch-level generation time and the sensitivity excluding ts-bool-env.

For the separately frozen plain-Python sensitivity, use the same scripts with an explicit --study path pointing to the action_text directory and a distinct --evidence directory. Pass the first experiment's evidence directory as --canary-evidence to bundle_grades.py to retain the shared, unchanged reference checks.
