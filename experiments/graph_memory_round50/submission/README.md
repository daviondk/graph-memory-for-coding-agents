# Maintaining Source-Linked Evidence Views for Agent Memory

This working ICDE demo-track package includes a four-page manuscript, editable LaTeX sources, seven interactive SQLite consoles and a narrated video of the six original consoles, including continuous source reweighting inside the trace console.

## Run the demo

With Python 3.10 or newer, run `python -B demo.py` in the extracted folder and open the local URL printed in the terminal. An optional `--port 0` chooses an available port. Ctrl+C stops the servers. The serving path uses the Python standard library and all required databases are included. The trace and edit examples use anonymized IDs, line hashes and offsets. The two-document view displays public 2WikiMultiHopQA questions, titles and text snippets. The evidence selector and its auditor read separate projections.

1. Open **Execution traces**. Select **In the packet** on q02 and compare the selected IDs. Unit 19 replaces unit 11. **Recompute and score** compares the maintained result with full recomputation and checks the 60 annotated characters. **Outside dependencies** shows when a source exclusion can reuse the old view.
2. Open **Code edits**. The **Relocated observations** example preserves a 315-byte packet. **Overlapping edit** keeps 74 of 507 bytes. In **Stale observation**, click **Verify line hashes and byte addresses**. All 14 IDs survive, yet three originally selected lines already had incorrect source coordinates.
3. Under **Edit context**, choose **Unchanged interior lines** and switch from **Match equal edges** to **Align all equal runs**. The packet grows from one to both original blocks. **Verify selected source lines** compares the stored observations with both file versions.
4. Under **Value transfer**, compare the current source flags with the flags that would survive an append-only update. Step one tool group back or forward and verify the output against the reference pair table.
5. Open **Source weight**. Step back to the preceding interval and compare the IDs. Move forward one Q32 unit, then choose **Recompute with exact Q32 DP** to check the changed packet.
6. Open **Two sources**. The q03 example changes each source by +0.0625. Both one-at-a-time packets stay at ID 352, while the joint optimum switches to 355. Click a region or adjust either weight. **Verify from original scores** recomputes the entire ordered packet from candidate and provenance records.
7. Open **Observed updates**. In q25, group 9, choose producer 5, producer 18, their pair, then all six recorded updates. Compare the binary policy with the capped count. **Verify from candidate scores** checks the result using an independent integer optimization. All 54 groups in this menu had observed changes in more than one source.
8. Under **Streaming packets**, choose Medium and advance one group at a time. At group 9 the reader resumes at row 48 and computes 31 rows instead of 79. Verify the full ordered packet, restart and compare checkpoint spacing or the work required if reads are deferred.
9. Open **Learned evidence packets**. Choose Long and the 100% cut. The fractional bound fixes two fragments, rules out 107 and leaves 61 candidates. **Audit against full DP** checks every ordered ID after 22,812 residual cell updates versus 189,290 in the full calculation.
10. Open **Choose a second source**. Inspect both candidate titles and adjust the registered bonus. Compare the archived generator responses for the selected inputs, then reveal support annotations. All 1,280 evaluated questions are available. The console replays recorded answers without running a model.
11. To verify the package in place, run `python -B verify_candidate.py`. It checks the extracted files and all seven running server APIs. `paper.pdf` is the paper, `walkthrough.mp4` is the video. To rebuild the paper, run `tectonic paper.tex` in this directory. The author block contains an anonymous placeholder pending the authors' details and final review. The source-weight control exposes exact Q32 switching points and checks them against the underlying candidates. The timed figures apply to local selection with fixed scores, costs and rank except for the stated common shift.

## Scope

Reported retrieval gains are on the ISETrace source-span benchmark. Handoff Debt comparisons concern packet preservation and line accuracy after observed edits. Neither metric measures the probability that a solver completes a coding task. The examples in the live console were selected for inspection. Aggregate estimates in the paper use the separate, larger evaluation cohorts.

On a separate panel of the public 2WikiMultiHopQA training split, choosing a second document with a fixed mention bonus reached 42.70 Answer F1 versus 41.62 with the unrestricted dense address. Both used the same reader and delivered token counts per question. The paper reports this as source selection in a two-read task. [2WikiMultiHopQA](https://aclanthology.org/2020.coling-main.580/)

[ICDE demonstration track](https://icde2027.github.io/cf-demonstrations.html) · [ISETrace study](https://arxiv.org/abs/2609.25913) · [Handoff Debt](https://aclanthology.org/2026.emnlp-main.738/)

## Manuscript measurements

Table I reports terminal ISETrace retrieval and CPU timing on the same ordered packets. The feature-to-packet measurement begins with the materialized numeric pool and a native rank. Of 960 evidence-available questions at the midpoint, 901 remained after excluding the pilot, and at the eighth tool group 649 of 697 remained. Feature ablations refit the model with the same learner family, training protocol and first-fit selector. The original walkthrough and six working consoles illustrate the earlier source updates and integer and floating-point contracts described in the text. The benchmark uses the no-adjacency hybrid, while the trace console shows the primary graph-ranked example.
