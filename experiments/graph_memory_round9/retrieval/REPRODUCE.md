# Reproducing the selective-read experiment

Use the adjacent round-8 retrieval directory and its verified local Salesforce model environment. The default Windows cache is on D:, and source.py accepts R8_RETRIEVAL_DIR and SWERANK_TEMP for equivalent paths. Required libraries are the CPU PyTorch 2.6.0, Transformers 4.52.4, NumPy, Requests, Einops and PyArrow 22.0.0. The complete source model SHA, weights hash and custom backend hashes are checked in the prior manifest; the main blind seal pins the exact imported files. Large model tensors never form part of the experiment output directory. If rehydrating from scratch, install the dependencies, run round 8 acquire.py model and encoder.py, and place the pinned authors' refactored_eval_localization.py file in SWERANK_TEMP. Its required SHA-256 is 11a886e0d12895dca9c3eef03ddd1c4282adab94e771089814ab7516c936c03d. [Pinned source](https://github.com/SalesforceAIResearch/SweRank/blob/d3df5088485eda13c7eebfcd6250052fd276f1a3/src/refactored_eval_localization.py)

Re-run from a fresh copy of the scripts and protocols. Embeddings may be reused by SHA-256 of the exact complete input string. Each selected issue retains a complete original candidate set. The following order places both prediction seals before relevance judgments.

```powershell
python sample.py
python embed.py
python predict.py
python stop_predict.py
python dense_check.py
python score.py
python stop_score.py
python verify.py
python describe.py
```

parallel_tail.py only schedules the last two corpora sooner on a second group of CPU threads and is optional. dense_check.py independently reruns single-document inference on nine hash-selected query–function pairs. The main estimator emits seven complete rank permutations per issue, including a rank- and degree-matched null. stop_predict.py uses each observed prefix separately and records the stopping trace. score.py invokes canonical unmodified functions from the pinned, hash-verified original evaluator additionally to our own all-target computation. All development, inference and grading ran locally. The experiment accesses public files to acquire the corpus and checkpoint.

The current sample.json retains the full screening flow, including all 68 in-range official test cases, activities omitted by predefined bounds and original content hashes. The local layout also includes format_smoke, superseded unjudged diagnostics kept to explain the released format issue. The public split has 560 tasks; the selected series covers 18 complete small or mid-size corpora. Source reads, retained graph-memory observations and database cost of the evaluation-only degree-matching pass are accounted for separately.