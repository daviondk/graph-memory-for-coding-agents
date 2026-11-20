# SWE-Explore prospective issue holdout

Lock before looking at labels or running the systems on this split. The first 23-issue pilot found the author word TF-IDF slightly ahead of identifier/path BM25 fusion at five regions. Use exactly one new treatment combining the complementary word, character and identifier views. No parameter selection on this holdout.

## Selection

Use SWE-Explore release bdb0ae45d7c337d9e1dc3ebfe2a0af6bc7c1fbd9, Verified-tagged rows. Match SWE-bench Verified metadata 78f471bf655a3137b2e8a75af1501690ec009ec3. Remove all first-pilot issue IDs and the paper's publicly illustrated scikit-learn__scikit-learn-10844. Sort each repository by sha256("swe-localization-v1|"+instance_id), take the next three or all remaining where fewer. Issue-disjoint; repositories overlap the pilot. Only issue text and exact base-commit source enter prediction. Scoring uses public evidence labels only after all three ordered lists are saved and hashed.

## Systems and fixed ranking

All use the official explorer's same ordered chunk inventory (up to roughly 3,000, windows of 80 lines, overlap 20). Controls are the author word TF-IDF and the first pilot's whitespace BM25 + identifier-aware BM25 + overlap-gated path BM25 at RRF weights 1/2/1 and constant 60. Each returns five source regions. The new system copies author TF-IDF if the issue has no code-shaped name. Detect ASCII dotted names, names with an underscore, and names with an uppercase letter beyond the first character. Retain the first 24 unique lowercased names. Collect the first 128 distinct lowercased code-shaped names or class/function declaration names from each chunk, plus its path twice. Character view uses char_wb 3–4 grams in 2^17 hash buckets, unsigned counts, sublinear TF-IDF and cosine. Fuse author word ranking (weight 3), previous fused ranking (1), and positive character ranking (2) by weighted reciprocal rank with constant 60. Word votes require positive similarity. Deterministic ties use upstream word order for the word list and input inventory order for the other ranks. This specific weighting is an unvalidated design choice.

## Endpoints

Primary endpoint is new minus author TF-IDF on official mean line F1 at the same raw emitted-line count for each issue across all three systems. Trim the ranked final interval(s) from their ends to the common minimum, counting overlap as emitted. Also report untrimmed five-region F1 and the original fusion at both budgets. Output five valid regions per method before trimming. Report wins/ties/losses, paired 10,000-draw percentile bootstrap sampling repository clusters (seed 20261116), and leave-one-repository-out differences. Use original ExploreEvaluator at commit 5602f031f2d9562d0a805f83402b536e831a5a11 and source-derived file lengths for open-ended labels. Absolute cost is CPU indexing/ranking per snapshot, no LLM, API or network inference. Timings are local descriptive observations.
