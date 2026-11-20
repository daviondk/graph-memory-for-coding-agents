# Frozen protocol for LongMemEval-S session retrieval

Written before generating ranks or evaluating any target labels. Embedding compilation may run concurrently. All fixed choices below apply to every question. There is no development split, fitting, prompt tuning, or threshold selection.

## Data and inputs

Use the official cleaned small benchmark, all 500 histories with the original distractors. The sole ranker inputs are the question text and lists of user utterance strings in their original order, grouped by session. The ranker returns integer positions. Session identifiers, annotations, types, dates, and assistant turns are withheld during ranking. Metadata and gold labels are opened by a separate evaluator after rank output is written. The cleaned release postdates the ICLR experiments.

## Methods

- **Reference BM25.** Execute the authors' session BM25 implementation from their pinned code, with rank-bm25 0.2.2. Preserve case, literal-space splitting, document order and NumPy tie sorting.
- **Normalized BM25.** Casefold, extract alphabetic/numeric Unicode word sequences, and apply the English Snowball stemmer. Use Okapi defaults on one concatenation of user turns per session. Keep stopwords.
- **Contriever session.** The released facebook/contriever checkpoint, the authors' 512-token truncation, mean over unmasked last-layer states, unnormalized dot product. Cache by content for speed. All neural arms share embeddings.
- **Flat fusion.** Sum reciprocal ranks from normalized session BM25 and session Contriever, with constant 10. Equal weights. It is the matched direct baseline.
- **Bounded witness policy.** Use the first 12 sessions from flat fusion. Compute normalized BM25 over user utterances in this history. For each candidate, choose the top utterance. Choose a different second utterance after halving the contribution of query stems already present in the first. Encode the two selected utterances with the same Contriever and take their maximum query dot product. Rerank the 12 candidates by 1/(10 + coarse rank) + 0.8/(10 + within-candidate-list dense witness rank), with one-based ranks. Preserve the remaining coarse ordering. With one turn use it once. If no user turn exists, assign negative infinity to its witness. Ordinal tie-breaks are deterministic.
- **Position control.** Same coarse candidates, two-utterance bound and reranking, with the first and last user turn as the witnesses.
- **Exhaustive turn control.** Rank all sessions by the maximum Contriever dot product over every user turn in that session. This is a session ranking obtained by deduplicating the authors' dense round ranking, evaluated on the same session labels. Also run a capacity-matched coarse fusion that reranks the same 12 candidates with the maximum over all of their turns. This isolates the bounded-vs-exhaustive witness choice.

## Endpoints

Primary endpoint is the official session recall_all@5, a binary hit if the top five distinct sessions cover every labeled user-side evidence session. The planned main contrast is bounded witness minus flat fusion. Also report direct BM25, normalized BM25, session Contriever, position and exhaustive-turn controls. Report recall_any@5 and the official NDCG@5 as descriptive endpoints. Report recall_all@1, @3 and @10. The authors' raw retrieval runner excludes abstention questions and non-abstaining questions with no positive user-turn annotation. Report both exclusion counts and disposition for every question. For inference, compute paired two-sided exact McNemar tests and 95% paired percentile question bootstrap intervals, 20,000 replicates seed 20261116. Only the primary contrast is confirmatory. Repeated distractor material can correlate errors. Report a sensitivity interval clustering questions by shared positive evidence content where applicable.

## Costs and interpretation

Report logical selected utterances and candidate counts per question alongside the exhaustive requirement. A global text-content cache is populated for every control, so this run measures retrieval accuracy and candidate work counts, not a deployment latency improvement. Record checkpoint/runtime details, batch preprocessing time, and logical embedding reads. The question benchmark measures retrieval, without a reader, judge, answer generation, financial API cost, or interactive persistence. Relative effects are specific to this public benchmark.
