# One more code read

Start `python -B serve.py --port 0` and open the loopback URL printed in the terminal. The server, HTML and two SQLite files run offline using the Python standard library. No repository checkout, model, network service or raw file body is needed.

The trace contains the actual archived reads, strict final context and explicit suggested-unread paths of a GPT-5.4-mini coding-agent run from Agent Retrieval Bench. Version 0 reconstructs the strict context returned in the archive. Version 1 appends the single eligible path chosen by the active method and shows the recorded first chunk’s line interval and SHA-256 at the pinned repository revision. This is a counterfactual continuation with a source receipt. The original agent did not execute this extra step. The recorded-read panel shows the archived set of opened paths in alphabetical order. The trace projection does not encode their chronology.

The first 36 examples cover every trace with readable file names from the original public-repository projection (Click, clap and pytest). Each repository’s minimum SHA-256 of `r54-trace-demo-v1|` followed by its sample ID is listed first, then remaining examples in hash order. These 36 and their positions were chosen without using their per-case outcomes. After finding that they contained two losses and no wins for first suggestion versus three-list RRF, we added all 31 eligible Tokio traces, in the same hash order. The menu contains 67 illustrative traces from four repositories. It supports inspection of both directions. Population estimates use the 283-case research panel.

## Replay a case

1. Start on the first Click trace (`af8170`). Three-way RRF selects `tests/test_normalization.py`. Version 1 shows the verified chunk for lines 1–38.
2. Switch to **First valid suggestion**. The archive points to `src/click/termui.py`; the recorded chunk covers lines 1–786. In the **Corroborated suggestion** view the same path is supported by a static ranking. Both additions have a verifiable source even when neither covers a required file.
3. Select **Evaluate this version** to reveal coverage for this context. The serving SQLite database contains no benchmark gold labels. Only this explicit action reads the separate audit. Switching trace, version or method closes the audit.
4. For a paired contrast on the same methods, select Tokio trace `a395d9` and version 1. The suggestion `tokio/tests/rt_common.rs` covers a required file, while RRF picks `tokio/src/runtime/thread_pool/worker.rs`. On Tokio trace `d42e82`, the suggestion `tokio/src/runtime/tests/loom_multi_thread.rs` misses, while RRF picks the required `tokio/src/runtime/handle.rs`. Open the audit separately after each change.
5. On pytest trace `e6b3d0`, compare the RRF and suggestion policies, then compare the two four-list policies. The corpus receipt verifies the file identity; the independent required-file audit answers whether it was relevant.

## Decision rules

| Rule | Which path is selected |
|---|---|
| Three static lists | Top eligible path using RRF from lexical, repository-map and Qwen3-Embedding-4B lists |
| First valid suggestion | First actionable path in the agent’s explicit list, falling back to static RRF |
| Corroborated suggestion | First actionable suggestion that appears in at least one baseline list, otherwise static RRF |
| Static RRF + suggestions | The three static lists plus an additional vote from each path in the ordered agent list |
| Static RRF + 8B | The three static lists plus Qwen3-Embedding-8B |

Every eligibility decision excludes previously opened paths and inputs given in the task, and requires a file chunk at the pinned revision. RRF uses the raw one-based positions in each upstream list and denominator 60 + rank. SQL breaks ties by the original path ordering. The review table shows all eligible candidates and their original ranks.

`GET /api/cases` lists examples, methods and the neutral landing case. `GET /api/state?q=<id>&method=rrf|suggested|confirmed|memory_rrf|static_four&version=0|1` executes the actual SQL selector and versioned context lookup. `POST /api/evaluate` with the same URL parameters computes file coverage and identifies a newly required read. The state API never opens the labels database. Version 0 returns no receipt for an additional file. At version 1 the receipt identifies the real existing chunk; its text is not distributed in this console.

Run `python -B test_console.py` for the standalone HTTP check. `python -B test_console.py --browser` also tests a narrow browser and that no evaluation request occurs before the audit button. This optional check uses Playwright with Chromium. In the complete research repository `build.py` recreates both projections from the frozen input tables. The research checkout stores the original protocol at `experiments/graph_memory_round54/next_read/PROTOCOL_RU.md`. The adjacent `supplement.py` can recover the Tokio names from the pinned release. [Agent Retrieval Bench archived release](https://huggingface.co/datasets/eyuansu71/agent_retrieval_bench/tree/5901e1ee3aff048290db72edf9c63bc498b79ea3/releases)
