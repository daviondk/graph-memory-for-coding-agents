# Reproduction

All paths are relative to this directory. Python standard library is sufficient for these CPU experiments. The bundled corpus projection stores UIDs, element tags, flags and exact outcomes. It omits original page text and entered values.

## Offline verification

Run `python verify.py`. It checks input/output locks, rebuilds the train tables, replays 29,830 decisions, independently reconstructs the simplest state rule and 19,519 context-only controls, then recomputes E1 and E2 metrics. The latest successful audit is verification.json. For E3 use context_only/results_corrected.json. The historical original is retained, with the three null/empty-string disagreements documented in correction.json.

## From source

1. Run `python fetch.py` to fetch six fixed-revision WebLINX train/test chat files and validate sources.
2. Run `python project.py`, `python run.py`, `python metrics.py`.
3. For E2 run `python grounded/prepare.py`, `python grounded/collect.py`, `python grounded/metrics.py`. Preparation additionally fetches validation. Collection downloads only official replay/geometry to memory and writes narrow geometry receipts. The pinned test_web replay URLs returned 404 on the experiment date.
4. For E3 run `python context_only/evaluate.py`, `python context_only/project_history.py`, `python context_only/correct_disagreements.py`.
5. Run `python verify.py`.

Regenerating files may replace locally locked copies and should be done in a copy of this directory. gzip timestamps are fixed for output projections and predictions. Existing source HTTP headers can change, so source file SHA checks determine fidelity. Publication links and artifact tree receipts have a separate observational role in the literature review.

## Experimental chronology and accounting

E1 was frozen before all test outcomes. E2 was frozen after E1 and used a new validation contrast, with prior IID/WEB outcomes explicitly exploratory. E3 was a stronger post-result falsification control. Each has an independent protocol. Root logs show executed commands. Artifacts contain no GPU/LLM call results because no such calls were made. Parent's live solver study is a separate experiment.

## Source attribution

WebLINX, Xing Han Lu and coauthors, ICML 2024. Paper https://proceedings.mlr.press/v235/lu24e.html. Dataset https://huggingface.co/datasets/McGill-NLP/WebLINX. Authors license the dataset CC BY-NC-SA 4.0. This research-only projection retains that source attribution. Source files and committed revisions are recorded in sources.json.

Original task-local raw downloads were removed after sanitized projections and independent verification. They contained source page/user text outside this question. exact source hashes plus pinned public URLs allow full reproduction. This removal affects only the six downloads created in this experiment.

