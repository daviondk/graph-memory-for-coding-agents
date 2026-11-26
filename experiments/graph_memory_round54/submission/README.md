# Maintaining Source-Linked Evidence Views for Agent Memory

The artifact includes a four-page IEEE demonstration proposal, editable sources, twelve local SQLite consoles, a self-contained Git replay and a narrated walkthrough. All consoles run on Python's standard library with the included projections.

## Run locally

Extract the archive to a writable directory. From that directory run `python -B demo.py --port 0` with Python 3.10 or newer. Open the printed loopback URL. Ctrl+C stops the launcher and all child servers. For an independent check in the extracted directory, run `python -B verify_candidate.py`. It checks file digests, starts the consoles, follows the landing links and exercises the read and audit APIs.

## Inspect the differing Git transition

Choose **Replay a Git import change** on the landing page (or open `tox-replay.html` directly). Step across tox commit `62bd8cf9`. The import score for the eighth-ranked file falls from 30 to 29. The cached outsider bound certifies the file's new rank. At capacity eight the exact-prefix baseline fetches one row. Increasing the cap to twelve makes the two policies tie on this transition. This selected case was the single differing commit in 714 transitions.

## Reproduce the main scenarios

1. **Spend one more code read.** Select the pytest session starting with `e6b3d0`. The version control switches between the archived strict context and a replay with one extra file. Try **Three static lists**, then **First valid suggestion**. Select **Evaluate this version** separately for each. Then compare **Static RRF + suggestions** with **Static RRF + 8B**. The memory-augmented vote opens `testing/acceptance_test.py` and shows the archived first-chunk digest and lines 1–1653. A completed read and a relevant read have separate receipts. The original agent's recorded actions are listed separately. [Session controls](apps/session/README.md)
2. **Replay an evidence withdrawal.** At commit horizon 17 inspect read version 16. The interval query and the journal return producer 14 with score 2. At version 17 the edge from producer 14 to consumer 19 drops from one to zero, bringing producer 14 to score 1. Producer 3 wins the tie. Rewind to 16 and inspect the two query plans.
3. **Code edits.** The relocated-observations example preserves a 315-byte packet. An overlapping edit keeps 74 of 507 bytes. In the stale-observation example all 14 IDs survive, and a snapshot check reveals three incorrect original line addresses. Under **Edit context**, switch to local alignment to recover both blocks in the interior-lines example.
4. **Execution traces.** Excluding a selected source in q02 replaces unit 11 with unit 19 and still covers the 60 annotated characters. Inspect the packet's prefix boundary and the independent recomputation. The other controls expose streaming checkpoints, changes in one or two source weights, and order-sensitive top-document reads.

## Measurements

The research panel comprises 283 archived coding-agent sessions across 25 repositories. A proposal added an uncovered required file on 20 sessions, three static rankings fused on 16, and Qwen3-Embedding-4B alone on 26. The interactive menu contains a readable subset, and its individual examples illustrate how a decision was made. Its results should be interpreted using the full panel. The projected file receipts document an offline continuation of an archived session.

The system measurements use a distinct dataset. The top-eight study replayed 1,072 atomic updates over 40 tool traces. A packed history and four alternative representations agreed at every one of the 1,112 states. The cutoff certificate used the full index after 39 updates. Its warm elapsed time was similar to the simpler unchanged-result control. At a capacity of twelve pairs, lazy maintenance and the variable-length prefix algorithm of Yi and colleagues both eliminated all remaining warm index probes. The published method retained fewer pairs on average (9.94 versus 10.08). At capacity eight the partial-suffix implementation used 36 index probes to retrieve 38 rows. The published-prefix adaptation used 39 to retrieve 41. In 714 Git transitions in six Python projects these plans saved one warm read in total. The reserve tests measured logical work. Run `python -B replay_topk.py` to reconstruct every ISETrace historical rank at k=2, 4 and 8 and reproduce the six source-index counts offline. Handoff Debt supplies observed code edits. Agent Retrieval Bench supplies separate file-retrieval tasks. The ClassEval pilot uses released unit tests for individual masked methods.

Aggregate experiments are bundled under `evidence/` for top-k history, the cutoff certificate and bounded reserve, code retrieval and executable generation. Each includes its study-specific result and comparison definitions. The paired-generation and retrieval protocols differ from their benchmarks' leaderboard tasks. Source details and attributions appear in [Data sources](DATA_SOURCES.md).

## Paper and video

`paper.pdf` is the English four-page proposal. To rebuild it in the extracted directory, run `tectonic paper.tex` with IEEEtran and the declared fonts available. The screenshot sources in Figure 1 are the actual local consoles. With Playwright and Chromium installed, running `python -B capture.py` writes the two fresh screenshots under `captures/`. The author block is an anonymous placeholder awaiting the authors’ details and final review.

`walkthrough.mp4` is the original 4 min 52.92 s narrated video. It demonstrates the earlier packet, edit and monotone history views. The code-session, withdrawal and global-directory scenarios can be exercised from the live landing page. The video is unchanged from the previous release. [ICDE demonstrations call](https://icde2027.github.io/cf-demonstrations.html)
