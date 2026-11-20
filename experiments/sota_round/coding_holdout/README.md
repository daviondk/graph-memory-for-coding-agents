# Prospective SWE-Explore holdout

Thirty new issues, three per repository, from ten repositories shared with the first pilot. The 23 prior issue IDs and a published illustrative scikit-learn issue were excluded before sampling. The roster comes from the 451 released records with the Verified tag. Both controls and the new rule use issue statements and source at the same original base commit. Each snapshot's single shared official chunk inventory and all ordered outputs have receipts. The new method gates on code-shaped names and fuses the author word TF-IDF ranks, earlier identifier+path BM25 ranks, and character TF-IDF ranks. We fixed the rule, including the 3/1/2 RRF weights, before scoring this roster.

| System | Mean line F1 at matched lines | Mean line F1 at five regions | Mean raw lines at five regions |
| --- | ---: | ---: | ---: |
| Author TF-IDF | 7.41% | 7.49% | 336.13 |
| First-pilot identifier/path ranker | 8.69% | 9.16% | 384.73 |
| New three-ranking fusion | 7.52% | 7.75% | 371.00 |

The primary budget truncated each ordered response to the smallest raw line count on that issue across all three systems. Each emitted a mean 333.97 lines. The new method exceeded TF-IDF by 0.11 percentage points, with a paired 95% repository bootstrap interval from −3.90 to +3.77 and 9 wins, 16 ties, 5 losses. Dropping each repository in turn gave differences from −0.88 to +1.35 points. Against the older ranker the difference was −1.16 points, interval −4.19 to +1.47 and 5/18/7 wins/ties/losses. None of these intervals establishes a gain. The gate fired on every issue. Compared with TF-IDF, line precision rose from 13.86% to 18.19% and line recall fell from 7.71% to 5.70%. F1 is the mean of official issue-level scores. The primary endpoint, two controls, secondary untrimmed budget, and cluster uncertainty were fixed in advance.

Timing on the shared Windows workstation used four prediction workers. Per snapshot, author indexing/ranking took 3.36 seconds on average, the previous ranker added 1.63 seconds, and the character index and final fusion added 1.28 seconds. The 6.28-second total includes a second word-scoring call for the exact author-order assertion, excludes source download and evaluator time, and represents concurrent per-task wall times. Archives totaled 239,045,107 bytes. These CPU methods made zero LLM calls. Filesystem traversal order affects the author's capped corpus on different OSes. Ordered-inventory hashes detect that difference. This test measures issue-to-code localization on repositories seen during development. Effects on bug fixes or inter-task memory require a solver experiment.

## Reproduce

Start with the pinned packages/inputs and upstream files described in the sibling `coding/README.md`. Configure `SWE_EXPLORE_CACHE` to a writable drive. Prepare the original pilot issue inputs via `python -X utf8 ../coding/prepare.py` if reconstructing from the archives. From this directory run the following commands.

```powershell
python -X utf8 prepare_holdout.py --fetch
python -X utf8 predict_holdout.py --workers 4
python -X utf8 score_holdout.py
```

The distributed outputs are already present. The prediction command resumes existing issue files. For an independent rerun that checks all ordered regions and the corpus hashes against the frozen author/previous/new outputs, use `python -X utf8 replay_holdout.py --workers 4`. The original prediction seal includes measured timing fields and therefore identifies that particular run. Replay verifies the deterministic outputs independently of timings. `--check-pilot` on the prediction script checks two older issues when their pilot snapshots exist.

The design and selection seals are in `design_lock.json`. The 90 ranked lists and their ordered-corpus hashes live in `predictions/`; `predictions_lock.json` links them to frozen code and protocol. `receipts/` records base commits, exact archives and source counts. `results.json` contains absolute metrics, paired differences, repository bootstrap limits and sensitivity; `rows.jsonl` holds the 180 official issue-level outcomes. The work uses the [pinned official evaluator](https://github.com/Qiushao-E/SWE-Explore-Bench/blob/5602f031f2d9562d0a805f83402b536e831a5a11/eval.py), [pinned labels](https://huggingface.co/datasets/SWE-Explore-Bench/SWE-Explore-Bench/tree/bdb0ae45d7c337d9e1dc3ebfe2a0af6bc7c1fbd9) and [pinned original inputs](https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified/tree/78f471bf655a3137b2e8a75af1501690ec009ec3).
