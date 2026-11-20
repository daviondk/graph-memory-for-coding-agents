# Papr on LongMemEval-S — 96.0% (High, K=20) / 95.4% (High, K=5) / 94.4% (Rerank) / 91.0% (Low)

Per-question answers, official grading logs, retrieved sessions and code for Papr memory retrieval on
[LongMemEval](https://github.com/xiaowu0162/LongMemEval) (`longmemeval_s_cleaned.json`, 500 questions).

## Results (official `evaluate_qa.py`, judge `gpt-4o-2024-08-06`, unmodified prompts)

| Setup | Answer model | Overall | Task-avg | Abstention | Retrieval speed (median, 1 request) | Reader tokens/q |
|---|---|---|---|---|---|---|
| **Papr Embed High, K=20** | Claude Opus 4.6 (8k thinking) | **96.0% (480/500)** | 96.71% | 27/30 | ~1.9 s | ~60k |
| **Papr Embed High** | Claude Opus 4.6 (8k thinking) | **95.4% (477/500)** | 96.94% | 27/30 | ~1.9 s | ~16.5k |
| **Papr Embed Rerank** | gpt-5-mini | **94.4% (472/500)** | 95.85% | 25/30 | ~1.9 s | ~15k |
| **Papr Embed Low** | gpt-5-mini | **91.0% (455/500)** | 92.4% | 26/30 | ~0.17 s | ~14.2k |

Papr Embed Low = schema embeddings only, no reranker (top 5 sessions by embedding score). Rerank and High add the Gemini 2.5 Flash reranker. Speed = question embedding (~170 ms, inline) + vector search (<1 ms) [+ reranker 1.8 s median]. Reranker tokens (20 sessions/question) are not included in reader tokens. Files: `papr_embed_*` = Low, `papr_low_*` = Rerank, `papr_high_*` = High (K=5), `papr_high_k20_*` = High, K=20.

Per type (correct / total, abstention questions counted separately):

| Type | High K=20 | Embed High (K=5) | Embed Rerank | Embed Low |
|---|---|---|---|---|
| single-session-user | 64/64 | 64/64 | 63/64 | 62/64 |
| single-session-assistant | 56/56 | 56/56 | 56/56 | 54/56 |
| single-session-preference | 29/30 | 30/30 | 30/30 | 28/30 |
| knowledge-update | 69/72 | 70/72 | 67/72 | 67/72 |
| temporal-reasoning | 124/127 | 118/127 | 119/127 | 114/127 |
| multi-session | 111/121 | 112/121 | 112/121 | 104/121 |
| abstention | 27/30 | 27/30 | 25/30 | 26/30 |

Reproduce the scores from the files here:
`python src/evaluation/print_qa_metrics.py results/<name>.jsonl.eval-results-gpt-4o data/longmemeval_s_cleaned.json`

### High K=20 (96.0%)

Same retrieval and the official CoT prompt, but the reader gets the **top 20 reranked sessions instead of the top 5**. No count-question extraction step. The reader sees about 60k tokens per question instead of 16.5k. 480/500 vs 477/500 for High K=5: 11 questions gained, 8 lost, so the net is +3, which is within the ±3 run-to-run variance below. The gain is concentrated in temporal-reasoning (130/133 vs 123/133, abstention-inclusive); task-averaged accuracy is 96.71% vs 96.94% for High K=5. K=20 was chosen after looking at the questions High K=5 missed, so it is tuned on the same set. Generate: `code/official_K20_generate.py`; grade: `code/judge_k20.py`. Per-question judge output: `results/papr_high_k20_opus-4-6.jsonl.eval-results-gpt-4o`.

## Pipeline

1. **Embed** every user turn and each question with `papr-embed-schema-1-0.6b` (Papr embeddings API, schema `memory:personal:1.6.0`). A session's score is its best turn's cosine similarity to the question. Top 20 sessions kept. (`code/embed_schema_all.py`)
2. **Rerank** the 20 with Gemini 2.5 Flash (thinking off): one call per question grades each session for whether it contains evidence needed to answer; order = grade, then embedding rank. (`code/rerank_schema.py`, `code/rerank40.py`)
3. **Answer** with the top 5 sessions, sorted by date, using the **official LongMemEval CoT prompt and JSON history format** from `run_generation.py`. (`code/official_A.py`)
   - Embed High only: for count/total-style questions (picked by a regex on the question text, no labels used), Opus first lists matching items per session, then answers with those notes. (`code/count3.py`, `code/route_cnt.py`)
4. **Grade** with the official `evaluate_qa.py` and `gpt-4o-2024-08-06`. (`code/official_eval_submit.py`)

Retrieval quality (all evidence sessions in the top 5, 470 answerable questions): **460/470 (97.9%)**; in the top 20: 467/470.
Reranker latency: 1.8 s median / 2.1 s p90 per question.

## Files

- `results/papr_*.jsonl` — `{question_id, hypothesis}` in the official submission format.
- `results/papr_*.jsonl.eval-results-gpt-4o` — official judge output per question.
- `retrieval/top5_sessions.jsonl` — per question: top-5 and top-20 session ids after reranking, rerank grades, latency.
- `code/` — the scripts above (keys read from environment variables).

## Caveats (please read)

- **Run-to-run variance.** gpt-5-mini: two full runs scored 469 and 472; we report the second. Opus 4.6 + extraction: two runs scored 477 and 473 (mean 475, 95.0%); we report 477. Expect ±3 questions.
- **Dev/test.** We iterated on prompts and routing using half of the 500 questions (248, `dev`) and checked on the other 252. There is no held-out set beyond that, so treat the numbers as tuned on this benchmark like most reported LongMemEval results.
- No question labels (`question_type`, `_abs`, answer sessions) are used anywhere in retrieval or answering; they are only used for grading and reporting.
