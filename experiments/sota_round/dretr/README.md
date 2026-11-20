# Testing bounded access to conversational evidence

On LongMemEval-S, revisiting two selected user utterances in each of 12 candidate sessions retrieved every labeled user-side evidence session for 391 of 419 eligible questions. The same session-level ranker without revisiting turns succeeded on 385. The proposed lexical rule for selecting utterances did not beat taking the first and last utterance, which succeeded on 393. Both outcomes apply to retrieval of evidence for the question.

## Results

| Session ranking | All evidence sessions in top 5, n/419 | Any evidence session in top 5 | Official NDCG@5 |
|---|---:|---:|---:|
| Authors' BM25 session implementation | 311 (74.22%) | 88.78% | .7715 |
| Casefolded, stemmed BM25 | 358 (85.44%) | 95.70% | .8844 |
| Contriever, authors' whole-session FP32 routine | 378 (90.21%) | 97.85% | .9141 |
| Stella V5 1.5B, whole session (additional control) | 373 (89.02%) | 95.47% | .8903 |
| Whole-session lexical/dense fusion | 385 (91.89%) | 97.61% | .9295 |
| Fusion + two query-selected utterances | 391 (93.32%) | 97.85% | .9366 |
| Fusion + first and last utterance | 393 (93.79%) | 97.61% | .9244 |
| Contriever, maximum over all turns | 383 (91.41%) | 98.09% | .9172 |
| Fusion + all turns in the 12 candidates | 393 (93.79%) | 98.09% | .9355 |

The frozen primary comparison gained seven successes and lost one relative to whole-session fusion, a paired difference of +1.43 percentage points. With only eight discordant questions, the exact two-sided McNemar p-value was .0703. The prespecified paired percentile bootstrap interval was [+0.24, +2.86] points. An additional conservative exact interval was [−0.61, +4.00] points. The latter combines individual 97.5% exact binomial intervals for the discordance probability and the conditional probability of winning by taking the extrema of their product after converting the latter to a signed effect. Both the 405 clusters sharing exact evidence material and the per-question bootstrap gave similar percentile results. Questions can still share semantically related material or distractors.

Compared descriptively with whole-session Contriever, the bounded policy gained 16 and lost 3 (+3.10 points, exact p=.0044). It gained one and lost three against the first/last control. The small difference between the two bounded strategies does not establish an advantage for lexical witness selection. Of 121 multi-session questions, fusion alone covered all evidence on 105, query-selected probes on 110, first/last on 112.

The added Stella V5 1.5B control covered all evidence on 373/419, and on 419/470 under declared session gold. A paired comparison against the bounded policy on the primary cohort yielded 26 wins and eight losses for the bounded policy (descriptive exact p=.00294). Encoding all 18,863 distinct questions and sessions with Stella took 373.6 seconds for 4,438,050 non-padding tokens, using 6.18 GB peak PyTorch allocation. Other jobs shared the GPU during this run.

For all 500 questions we also executed the authors' verbatim Contriever branch in FP32 with its original per-question batching. Compared with the length-batched TF32-enabled cache used by fusion, it returned the same top-five set on 499 questions and identical ordered top fives on 496. Both versions scored 378 all-evidence hits and 410 any-evidence hits on the official cohort. The cached version's NDCG@5 was .9145 versus .9141 from the author routine.

The retrieval program produced complete rankings for all 500 records. The authors' session benchmark uses only user turns. Its aggregation excludes 30 abstentions and 51 further questions without a positive user turn, giving 419. It derives gold session IDs through its own session-indexing routine. It scored five single-session-assistant questions with positive user-turn evidence. The authors' DCG discounts rank 2 by log2(2), giving ranks 1 and 2 equal gain. The checked-in evaluator preserves this definition. All ranking methods take only the question string and session-grouped user-side content.

The separate 470-question table uses the data release's declared evidence IDs for every non-abstention, including evidence on the assistant side. After ranks were frozen, the bounded method retrieved any declared evidence on 461/470 and all declared evidence on 434/470. For flat fusion these counts were 457 and 426. The two definitions have different gold sets and denominators. No reader, answer generator, or judge was run.

On the same 470-question all-evidence endpoint, Papr's published reranked top five cover 460. Its pipeline includes schema extraction and a language-model reranker. Its output files support independent scoring without running those services. Candidate generation followed by budgeted slate selection also has a direct precedent in AgentMemRec. This experiment tests a specific two-turn policy and its controls. [Papr's pinned ranks and report](https://github.com/Papr-ai/papr-longmemeval/tree/3543e066f4a5f065f4e3d473f5a37a644d6a8881) · [Agent Memory as Recommendation](https://arxiv.org/abs/2610.34673)

## Compute and material

The bounded policy read 9,993 additional turn vectors for the 419 scored questions. Exhaustively reranking the same candidates read 28,891 turn vectors, and global maximum-turn retrieval read 102,236. That is 65.4% fewer turn probes than exhausting the shortlist and 90.2% fewer than probing all user turns. Every candidate-scoring variant sharing the coarse stage also uses one dense query vector and scores one session vector per session. The bounded policy additionally computes BM25 over all user turns. These counts measure dense turn-vector work. The global cache for this experiment materialized all vectors for the exhaustive controls.

An RTX 3090 encoded 18,863 distinct queries/whole sessions in 49.0 seconds (4,609,811 non-padding tokens), then 92,740 additional distinct turn texts in 60.5 seconds (4,676,113 non-padding tokens), using batch size 32 and a reported peak of 1.09 GB allocated by PyTorch. Cached ranking of 500 questions across eight methods took 7.71 seconds on an AMD Ryzen 7 8700F. These exclude downloads and model startup. Data, model weights, and embedding matrices were kept on the external cache volume. All computation was local after download. No paid inference APIs were used. We did not measure production end-to-end latency, persistence across conversations, or answer correctness.

## Reproduction

Run with Python 3.12; the study used Python 3.12.13, Windows, PyTorch 2.6.0+cu124, and a CUDA GPU. Run the commands below from this folder. Set the path to a writable cache with room for data and models. Requirements include NumPy 1.26.4 so the original evaluator can call its original asfarray implementation. The two author source files and MIT license in the upstream directory are included verbatim.

```powershell
python -m pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cu124
python -m pip install -r requirements.txt
$cache = 'D:\longmemeval-replication'
$env:HF_HOME = Join-Path $cache 'hf'
$env:OPENBLAS_NUM_THREADS = '1'
python fetch.py $cache
python encode.py $cache
python rank.py $cache
python evaluate.py $cache
python declared_gold.py $cache
python audit_dense.py $cache
python audit_dense.py $cache --all
python verify.py $cache
```

For the additional Stella control, run the commands below. The pinned release's custom model files execute locally with Transformers, using BF16 encoder weights and FP32 mean pooling, 1,024-dimensional projection and normalization. The official retrieval code uses raw queries and a 512-token limit. Cached batches are sorted by text length.

```powershell
python fetch.py $cache --stella
python stella.py $cache
```

To re-score saved rankings without recomputing embeddings, fetch the pinned data, install the requirements, and run evaluate.py, declared_gold.py and verify.py. The first program writes results.json, dispositions.csv, and per_question.csv. The second writes declared_gold_results.json and declared_gold_per_question.csv. ranks.jsonl contains eight complete integer-index orders per question. stella_ranks.jsonl, stella_results.json, and stella_per_question.csv hold the added control. contriever_parity.json checks a label-blind sample against the original dense routine, while contriever_parity_all.json covers the entire release. The contriever_original files contain the full original-method ranks and their separate official and declared-gold evaluations. PROTOCOL.md records the primary experiment before ranks were generated. The cache and Python bytecode are outside the reproduction package.

## Provenance

The benchmark and vendored evaluator are MIT-licensed. The cleaned data release removes interfering history sessions present in the original publication. Direct comparisons in this study recompute the paper's methods on the same cleaned file. The published figures retain the authors' original data, scale, and settings. [ICLR paper](https://proceedings.iclr.cc/paper_files/paper/2025/file/d813d324dbf0598bbdc9c8e79740ed01-Paper-Conference.pdf) · [Pinned data release](https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/tree/98d7416c24c778c2fee6e6f3006e7a073259d48f) · [Pinned retrieval source](https://github.com/xiaowu0162/LongMemEval/tree/9e0b455f4ef0e2ab8f2e582289761153549043fc/src/retrieval)

Contriever weights and tokenizer were fetched from the official checkpoint. The authors' repository gives CC BY-NC 4.0 terms. The Stella model card lists MIT. Model weights and benchmark conversations are fetched separately. fetch.py verifies the large files against their published SHA-256 values. [Contriever checkpoint](https://huggingface.co/facebook/contriever/tree/2bd46a25019aeea091fd42d1f0fd4801675cf699) · [Contriever license](https://github.com/facebookresearch/contriever/blob/main/LICENSE) · [Stella checkpoint](https://huggingface.co/NovaSearch/stella_en_1.5B_v5/tree/7817065102fd9e1b031fe874e910c01f40b2f001)
