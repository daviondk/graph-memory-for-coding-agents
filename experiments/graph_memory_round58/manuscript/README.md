# Checkpointing Shared Git Events for a Coding Agent's Graph Memory

[Four-page English working draft](paper.pdf) · [Editable IEEEtran source](paper.tex) · [Interactive checkpoint console](../demo/index.html) · [Narrated walkthrough, 1 min 51 s](../walkthrough/walkthrough.mp4) · [Captions](../walkthrough/captions.srt)

A visitor chooses a checkpoint per repository, compares the source events and changes the read policy. The same durable SQLite index supports a cold reopen, a partial checkpoint or a complete snapshot. The prototype shows what was transferred and timed for each decision. The paper includes the reversal observed when subsequent queries were sparse on twelve additional repositories. The English IEEE conference PDF has four pages including references. The working author line is anonymous and the acknowledgments disclose OpenAI Codex's contribution. [Official ICDE Demonstrations Call](https://icde2027.github.io/cf-demonstrations.html)

## Visit the scenarios

- Open the [offline console](../demo/index.html). Select long histories and a 1 KiB budget. Switch from estimated demand to largest bodies, compare both with the unpadded full snapshot, then inspect the detailed charges and full-run time. The cost-increase button jumps to the measured short-history reversal.
- The editor-cache tab replays actual requests from SWE-agent. Compare fixed-width and compact address encoding while keeping the observed request sequence fixed. [Cache measurements](../task_cache/REPORT_RU.md)
- The [two-file SQL demonstration](../../graph_memory_round57/seed_pair/demo.html) compares several readings of the same Dask or xarray events. Its constructed histories preserve all observed pair counts while changing the third file. For a live read of SQLite, run `python -B demo.py serve` in the R57 seed_pair directory and use the printed address with `?source=sqlite`. The [NetworkX replay](../../graph_memory_round56/manuscript/replay.html) follows individual commit evidence across owners. [Preceding full draft](../../graph_memory_round57/manuscript/paper.pdf)

## Evidence and measurements

- Checkpoint policy, same-budget largest-body control, complete unpadded snapshot, total runtime and failure recovery. [Nine-project instrumented trial](../restart/REPORT_RU.md)
- Prior policy tested unchanged on sparse and dense queries from twelve further repositories. [External transfer](../restart_transfer/REPORT_RU.md)
- Direct experiment on 21 new functions with a shared first draft, four memory conditions and 87 fresh GPU generations. [Executable solver results](../solver/REPORT_RU.md)
- Independent single-anchor replication and multi-anchor ambiguity. [932 single-anchor tasks](../../graph_memory_round57/replication/REPORT_RU.md) · [621 two-anchor tasks](../../graph_memory_round57/seed_pair/metrics.json) · [Exact construction](../../graph_memory_round57/seed_pair/ambiguity.py)

## Rebuild

Compile from this directory. The two diagrams reproduced from the previous draft and the screen capture from the current console are supplied beside the source. The following PowerShell commands use Tectonic with a cached IEEEtran bundle and PyMuPDF.

```powershell
$env:SOURCE_DATE_EPOCH='1'
tectonic --only-cached paper.tex
python -B verify.py
```

The checks verify pagination, embedded fonts, figure and table captions, references and reported costs against the frozen experiment files. To regenerate the screenshot from the exact default controls, run `python -B capture.py` with Playwright and Chrome. The PDF was rendered with Poppler for visual review. [Verification record](verification.json) · [Screenshot source](capture.py) · [Synthetic-diagram source](../../graph_memory_round57/manuscript/figure.py)
