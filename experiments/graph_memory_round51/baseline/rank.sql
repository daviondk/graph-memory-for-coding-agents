-- Each row is one visible title. Question/snippet ranks are zero-based in the original
-- lexical catalog, dense_rank is zero-based among remaining titles, mention is 0 or 1.
-- :w0..:w4 = trained coefficients divided by their training feature standard deviations.
-- The subtracted mean term is common to every candidate and cancels in an ORDER BY.
WITH addressed AS (
    SELECT qid, candidate, dense_rank,
           :w0 * cosine + :w1 / (1.0 + question_rank)
               + :w2 / (1.0 + snippet_rank) + :w3 / (1.0 + dense_rank)
               + :w4 * mention AS score
    FROM candidates
),
ordered AS (
    SELECT qid, candidate,
           ROW_NUMBER() OVER (PARTITION BY qid ORDER BY score DESC, dense_rank ASC) AS position
    FROM addressed
)
SELECT qid, candidate FROM ordered WHERE position = 1 ORDER BY qid;
