# Sharing Retained Git Events in a Graph Memory for Coding Agents

[Four-page working paper](paper.pdf) · [Watch the current walkthrough](../walkthrough/walkthrough.mp4) · [Editable IEEEtran source](paper.tex) · [English two-file demonstration](../seed_pair/demo.html) · [English one-file demonstration](../../graph_memory_round56/manuscript/replay.html)

The ICDE demonstrations draft lets a visitor trace which file retained an old commit, query a graph with two known files, and change the third file of a triple without changing any pair count. It includes the failed predictions as well as the successful ones. The manuscript uses an anonymous working author line and discloses the use of OpenAI Codex. The PDF is ready for internal review. [ICDE demonstrations call](https://icde2027.github.io/cf-demonstrations.html)

## Visit the demonstrations

The 1 min 57 s English recording shows the current NetworkX and SQL scenarios. Captions are available separately. [Video](../walkthrough/walkthrough.mp4) · [English captions](../walkthrough/captions.srt)

For the two-file scenario, open the downloaded HTML in a browser. Select Dask or xarray and hide or reveal held-out paths. Inspect the three predictions from the same history. Expand historical events to inspect their members. In the second tab, choose two files and cycle through the 16 histories while watching the common pair counts and the actual third file. To run live SQL from the repository, change to `../seed_pair`, run `python -B demo.py serve`, and open the address printed by the server with `?source=sqlite`. [Console implementation](../seed_pair/demo.py) · [Verified live and offline interactions](../seed_pair/browser-check.json)

For the one-file scenario, the two NetworkX cases in the earlier interactive replay expose a gain and a loss when reading through records owned by other files. The new paper supersedes the [preceding working paper](../../graph_memory_round56/manuscript/paper.pdf). The [full earlier downloadable package with video](https://github.com/daviondk/graph-memory-for-coding-agents/blob/71b6349f0676b4aed0ca256d7fa78bb3c6ac3d44/experiments/graph_memory_round55/submission/candidate.zip) documents the earlier scenes.

## Evidence used in the paper

- Fixed policy, independent one-file replication, size-only controls and work per query. [932 Git queries](../replication/REPORT_RU.md)
- Two observed paths, independent repositories, harmonic pair-overlap control and cyclic ambiguity construction. [621-query panel](../seed_pair/metrics.json) · [Formal construction and direct check](../seed_pair/ambiguity.py)
- Exact rank certificates with explicit cost for transferring and building the conditional summaries. [Certificate experiment](../joint_certificate/REPORT_RU.md)
- Identical reversible source receipts and exact one-anchor rankings with compressed full postings, hot/cold storage and grouped-source controls. [Same-disk volatile cache experiment](../composed/PROTOCOL_RU.md) · [Durable measurements](../block_index/REPORT_RU.md) · [Post-VACUUM sizes](../block_index/vacuum.json)
- Published retrieval benchmark, strict exclusion of already-known addresses and separate replay of actual coding-agent actions. [Multiple-source test retrieval](../arb_multi/REPORT_RU.md) · [108 SWE-agent traces](../agent_trace/REPORT_RU.md) · [Local solver pilot](../../graph_memory_round56/solver/REPORT_RU.md)

## Rebuild and verify

From this directory, compile `paper.tex` with Tectonic and an IEEEtran-enabled bundle. All figures needed for compilation are included. Use `SOURCE_DATE_EPOCH=1` for deterministic PDF metadata. A cached installation used the commands below.

```sh
SOURCE_DATE_EPOCH=1 tectonic --only-cached paper.tex
python -B verify.py
```

The offline check uses PyMuPDF and the Python standard library. It checks pagination, embedded fonts, references, figures, tables and selected numbers against the machine-readable experiment outputs. [Verification record](verification.json)

To regenerate the two-history drawing, run `python -B figure.py` (ReportLab). To recapture the real SQLite-derived Dask cards, run `python -B capture.py` (Playwright and Chrome). The source of the retention drawing is [the previous figure script](../../graph_memory_round56/manuscript/figure.py). The PDF was rendered and the four pages inspected, including the rankings, synthetic example, tables and balanced final columns.
