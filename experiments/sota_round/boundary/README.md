# Boundary experiments, 16 Nov 2026
Protocol, scripts, model hashes and immutable predictions are bundled. Original data https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/98d7416c24c778c2fee6e6f3006e7a073259d48f/longmemeval_s_cleaned.json . Papr relative to archive: comparators/papr_ranks.jsonl (source commit 3543e066f4a5f065f4e3d473f5a37a644d6a8881). Compare SHA-256 against dretr/results.json. Python 3.12, torch 2.6.0+cu124, transformers 4.46.3 for MiniLM. The cleaned dataset and model weights are external.
From archive root, replacing DATA, MODEL_DIR, BLIND_JSONL with local paths:
    python boundary/download.py MODEL_DIR
    python boundary/prepare.py DATA comparators/papr_ranks.jsonl BLIND_JSONL
    python boundary/rank.py BLIND_JSONL MODEL_DIR boundary/run
    python boundary/decide.py boundary/run boundary/unused
    python boundary/evaluate.py DATA comparators/papr_ranks.jsonl boundary/run comparators
    python boundary/slate.py BLIND_JSONL boundary/run boundary/followup
    python boundary/evaluate.py DATA comparators/papr_ranks.jsonl boundary/followup comparators
The last command replays 500 frozen follow-up rankings without making hosted calls. 64 per-call decisions, slot maps, usage, unique prompt hashes, per-question scores, error/gate diagnostics are included. The extra hosted reader used gpt-6.1-sol/low; its version can change. See run_model.py and slate_decide.py for exact interface if running in a suitable environment. Full existing local CLI event logs are in the study workspace; ZIP exposes research decisions & resource receipts. Full upstream candidate-generation and Gemini costs unknown. Exact initial evaluator retained in evaluate-initial.py: its check that abstentions have empty gold was wrong on this input. The original official suffix-only skip was reinstated in evaluate.py; rankings and population rule are unchanged. Models never received hidden labels; see strict allowlist in prepare.py. The primary gate did not activate, and its theoretical verifier effect therefore was not observed. The budget-64 follow-up was frozen after inspecting only gate activation and logit distributions. Retrospective error ledger was computed after both rankings were final.

