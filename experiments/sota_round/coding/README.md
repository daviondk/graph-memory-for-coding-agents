# SWE-Explore coding-context experiment

On 23 real software issues from 12 repositories, a retriever combining code-identifier matches with path and raw-text rankings achieved **8.68% mean line F1**. The authors’ TF-IDF retriever reached **8.78%** on the same issues. The proposed method improved on the official whitespace BM25 control, and the uncertainty interval includes a tie against the stronger TF-IDF control.

| Method, five regions | Mean line F1 | Line precision | Line recall | Core-file coverage | Mean lines emitted |
| --- | ---: | ---: | ---: | ---: | ---: |
| Official BM25 | 2.83% | 5.95% | 2.91% | 11.96% | 370.13 |
| Official Potion-8M | 5.95% | 13.89% | 5.14% | 16.96% | 379.13 |
| Official TF-IDF | 8.78% | 19.73% | 6.93% | 28.48% | 319.74 |
| Candidate | 8.68% | 16.85% | 8.46% | 28.33% | 382.96 |

| Candidate minus control | F1 difference, percentage points | Paired 95% bootstrap interval, pp | Wins / ties / losses |
| --- | ---: | ---: | ---: |
| BM25 | +5.85 | [+1.01, +12.66] | 10 / 11 / 2 |
| Potion-8M | +2.73 | [−2.69, +9.89] | 6 / 9 / 8 |
| TF-IDF | −0.10 | [−3.28, +3.16] | 5 / 9 / 9 |

**Equal lines.** To equalize actual reader exposure, we truncated each method’s ranked regions on each issue to that pair’s shorter total line count. Candidate minus BM25 was +6.06 points [1.01, 13.51] with both emitting a mean 364.61 lines. Against TF-IDF the difference was +0.91 [−3.20, 6.19] with both emitting 317.83. Against Potion it was +3.09 [−2.58, 10.87] with both emitting 373.26. The original BM25 pairing and candidate were frozen before scoring. We added TF-IDF, Potion and these line-matched checks after seeing the BM25 comparison. Intervals resample entire repositories with replacement 10,000 times and recompute the issue-weighted difference. Twelve clusters limit precision, and these multiple comparisons carry no multiplicity adjustment.

**Scope.** We evaluated the five code regions a retriever would supply before editing a repository, using issue statements and pre-edit source snapshots. All methods used the same ordered source-chunk inventory on each issue. No test oracle, solver trajectory, target patch, or question-type labels were accessible to prediction. The task supplies no previous-session memory at inference. We measured neither patch success nor persistence across tasks. SWE-Explore’s trajectory-derived labels may omit other useful regions. Its paper reports 0.024 BM25, 0.054 TF-IDF, 0.026 Potion, 0.223 Codex and 0.602 CoSIL F1 on its own main comparison, where agentic spans may represent substantially more lines. Those scores give context for the strength of published methods. Only the rerun rows above share the 23-issue roster. [Official study, Table 6](https://arxiv.org/html/2606.07297v1#S4.T6)

**Sampling.** Out of 848 released SWE-Explore tasks, the 451 released records tagged Verified map cleanly to the original issue text and base commit. Take at most two per repository by the hash rule in `protocol.md`. This gives a repository-balanced pilot covering all 12 Verified repositories, with all 23 selected cases completed. One of the 23 cases, `pydata__xarray-4687`, also appears as an illustration in the MemDev-Bench paper consulted earlier. The candidate was written without inspecting its SWE-Explore labels. Excluding this record as a sensitivity check gives a +6.11-point difference vs BM25. [Pinned benchmark](https://github.com/Qiushao-E/SWE-Explore-Bench/tree/5602f031f2d9562d0a805f83402b536e831a5a11) · [Pinned labels](https://huggingface.co/datasets/SWE-Explore-Bench/SWE-Explore-Bench/tree/bdb0ae45d7c337d9e1dc3ebfe2a0af6bc7c1fbd9) · [Pinned issue text/base commits](https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified/tree/78f471bf655a3137b2e8a75af1501690ec009ec3)

**Method and budget.** The official BM25 explorer scores whitespace-separated words. The candidate combines its ranks with two votes from a second BM25 index over punctuation- and CamelCase-split code identifiers, and a vote for the separately ranked path when it shares a token with the query. Reciprocal rank fusion uses offset 60. The official chunker enumerates source files and emits 80-line windows with 20 lines of overlap, with a nominal cap of 3,000 chunks. Its end-of-file control flow can slightly overshoot that cap. Every method consumed identical per-task inventories, verified through content hashes. Five regions have a maximum of 400 raw lines. Near-EOF chunks can be shorter. The candidate and all three controls ran locally with zero LLM/API calls. Mean whole-index construction for the upstream BM25 run was 3.04 s/task, and additional fusion processing averaged 0.86 s/task including the receipt checksum. These wall times include CPU and disk work on this machine. Torch and an LLM are unnecessary for the three measured lexical/static controls. [BM25](https://github.com/Qiushao-E/SWE-Explore-Bench/blob/5602f031f2d9562d0a805f83402b536e831a5a11/explorers/bm25.py) · [TF-IDF](https://github.com/Qiushao-E/SWE-Explore-Bench/blob/5602f031f2d9562d0a805f83402b536e831a5a11/explorers/rag_tfidf.py) · [Potion](https://github.com/Qiushao-E/SWE-Explore-Bench/blob/5602f031f2d9562d0a805f83402b536e831a5a11/explorers/rag_potion.py) · [Scorer](https://github.com/Qiushao-E/SWE-Explore-Bench/blob/5602f031f2d9562d0a805f83402b536e831a5a11/eval.py)

## Reproduction

Run from this directory. The environment file records package versions actually used on Windows, Python 3.14.4. On another OS the official chunker’s filesystem traversal order can change the truncated index. Per-issue inventory hashes allow detection. In a fresh environment, use:

```powershell
python -m pip install numpy==2.4.4 rank-bm25==0.2.2 typer==0.24.1 pyarrow==24.0.0 scikit-learn==1.8.0 scipy==1.17.1 joblib==1.5.3 threadpoolctl==3.6.0 model2vec==0.10.0 safetensors==0.8.0 tokenizers==0.22.2 huggingface-hub==1.10.1
$env:SWE_EXPLORE_CACHE = 'D:\CodexData\x20-swe-explore-20261116'
python -X utf8 prepare.py --potion
python -X utf8 get_snapshots.py
python -X utf8 predict.py --force
python -X utf8 score.py
python -X utf8 controls.py tfidf
python -X utf8 controls.py potion
python -X utf8 controls.py score
```

Set the cache path to any writable local directory. Source archives totaled 163 MB compressed. Only eligible source extensions are materialized; four eligible symbolic links are represented by their exact target contents. File lengths needed for scoring out-of-extension gold targets can also be obtained directly from the corresponding fixed archive. `receipts/` retains commit IDs, archive SHA-256 and source counts. `predictions/` holds the primary ranked regions and per-issue index hashes, `tfidf_predictions.json` and `potion_predictions.json` hold the extra baselines, `score_rows.csv` and `controls_rows.jsonl` contain the official per-issue metrics, and `results.json` and `controls_results.json` retain the summaries. The large archives, snapshots, installed packages and weights belong in the working cache only.
