# Reproduction

The small offline replay requires Python and NumPy (recorded run: CPython 3.14.4, NumPy 2.4.4). From this directory run:

```
python switch.py
```

This refits all five outer folds per corpus, repeats inner tuning, evaluates both zero-shot transfers and reruns all group bootstrap draws from the 708 frozen pairs in potential_outcomes.jsonl. Existing results, actions and fitted models are checked against regeneration. Each pair includes the selected evidence or passage identifiers and both official metric values. decisions.jsonl joins to these rows by dataset and item ID. The per-row fold on transfer refers to the target corpus' diagnostic local folds. models.json stores all coefficients; features in prepare.py are ordered by NAMES.

Full regrading requires the pinned data and scorer. Run `python fetch.py` with Python requests installed (recorded version in input_versions.json). It verifies that qrels from NIST and the organizers' repository are identical and fetches the pinned NIST trec_eval v9.0.8 source. Build the target `trec_eval` via `make trec_eval` in the extracted sources/trec_eval-d95ca64e14a47d763ae349fb65e6d8cde4141dbd directory. Linux runs it natively. Windows uses WSL and environment variable TREC_WSL (machine default CodexX20MSR). Source URLs, SHA256 hashes and original license references are retained in source_receipt.json. Organizers' ranked outputs are replayed as released. No expensive model training or encoding is needed.

`python prepare.py` also expects the preserved memory_session5/serbench experiment under the work directory, or a SERBENCH_DIR environment variable pointing at it. Input hashes are listed in input_versions.json. It runs the original SERBench score_predictions with strict per-state candidate validation and both cutoffs. For CAsT it ranks by decreasing run score (document ID descending breaks ties as in NIST), computes full precision nDCG, and checks every score and both means against the official compiled trec_eval output, rounded to the 4 decimals it prints. The exact invocation is in prepare.py. Nothing in a dataset is interpreted as code.

After `python switch.py`, run `python audit.py` with sources/topics.json present. The independent check recalculates headline means from row-level actions, ensures each group belongs to one outer fold, and reproduces the descriptive first-turn control. See preregistration.md for the prospectively fixed endpoints and summary_ru.md for limitations, the exact zero-shot interpretation, and the post-outcome diagnostic. Input hashes were recorded for fetch.py, and the preregistration hash was communicated before the first new outcome calculations.

`python standalone_check.py` verifies the compact offline replay package, including the first-turn diagnostic from the included topics, in a fresh temporary directory. It creates only temporary copies of the small derived inputs.
The post-hoc read-count-matched benchmark is specified in COUNT_CONTROL.md. Run python count_control.py to reproduce all 50,000 conditional random masks for each evaluation. The offline checker also verifies its output.
