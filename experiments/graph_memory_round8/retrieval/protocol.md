# Frozen protocol — graph retrieval from a prior symbol lookup

## Question

Does expanding a recorded symbol lookup across a call edge improve function localization over a frozen, published dense encoder, and over the same dense/lexical/anchor retriever without graph expansion? This is a controlled, static simulation of one tool observation and its subsequent read, with a fresh short-lived memory per issue. It does not measure long-horizon persistence or patch correctness.

## Data and sampling

Use Salesforce SweRank's original SWE-bench Lite archive and BEIR queries/functions/relevance judgments. Sample six issues apiece from the project's three math/documentation/plotting repositories (SymPy, Sphinx, Matplotlib). Sample order is ascending SHA256 of `R8-lookup-v1|` + original instance ID within repo. Skip queries containing whole-word markers CVE, exploit, vulnerability, vulnerabilities, arbitrary code execution, security, injection, denial of service. Do not filter on presence of named code symbols or qrels. All officially represented function IDs can enter a first-stage implementation of BM25 (k1=1.2, b=0.75, Robertson/Sparck Jones positive IDF, identifiers split at underscore and case changes; duplicates of full terms and components avoided per token). A generator returns top 40 by score, breaking ties by official candidate ID. Only these 40 are available to every final ranker. Empty qrels receive explicit separate accounting and are excluded only if present (the target evaluation would otherwise be undefined).

## Conditions

1. BM25 first-stage order. 
2. Salesforce SweRankEmbed-Small, frozen model revision 745d2a06103a66d3cfa600aa52fc0d3523010daa. Use official query prefix, CLS pooling, L2 norm, cosine score, FP32 CPU and 1,024-token cap matching the authors' script. 
3. Equal reciprocal-rank fusion (RRF, offset 10) of dense and BM25 ranks.
4. Same RRF plus one additional reciprocal-rank term for exact anchors: match explicit Python-call spellings and code-style identifiers in the issue to the final symbol name (case-sensitive, ignore names <3 characters), and remember up to eight matching candidate addresses. Select by lexical order of retrieval rank, with frequency of exact identifier in query prioritized. A direct anchor gets 1/(10+its observation rank), other candidates zero. 
5. Same direct-anchor condition plus undirected static call evidence inside the 40-function graph. An outgoing edge from function U to V exists when U's body contains a call-shaped token V(...), V has a unique basename in the pool, and U differs from V. Exclude the function definition line from edges. Each non-anchor candidate neighboring at least one anchor receives 0.5 times the best adjacent anchor's reciprocal-rank term. No extra data or test labels supplied.
6. Negative control uses a fixed SHA256 permutation of candidate ID labels to rewire the same undirected graph while keeping anchor identity and score mass rule. Use original issue ID + candidate ID as permutation seed. Cost/setup conditions identical.

The method in condition 5 is the primary treatment. Comparisons to dense, RRF and specifically condition 4 distinguish numerical gain from evidence for a graph mechanism. Gold-free predictions and their SHA256 are saved before loading qrels. Release the issue IDs, candidate IDs, individual signals/ranks, graph edges, direct anchors and per-issue metrics.

## Metrics and tests

Primary outcome is issue-level MRR@10 (0 for no relevant function in top 10). Secondary outcomes are Hit@1/5/10, macro Recall@10, nDCG@10 and candidate coverage Hit@40 over all sampled issues. Summarize differences as paired means with fixed-seed percentile bootstrap (10,000 draws, resampling tasks within each of the three repositories), plus counts of wins/ties/losses and a two-sided exact sign test (zeros discarded) for MRR@10. With six tasks per repository, intervals describe sampled repos only. No tune/test search, no ranking claims from secondary endpoints. An inferential interpretation would require a fresh larger multi-repository holdout. The paper's full-corpus headline and LLM patch-success results are distinct experiments. This is a controlled reranking diagnostic.

## Provenance

- [SweRank paper](https://arxiv.org/abs/2505.07849)
- [Pinned official evaluation](https://github.com/SalesforceAIResearch/SweRank/tree/d3df5088485eda13c7eebfcd6250052fd276f1a3)
- [Pinned published model](https://huggingface.co/Salesforce/SweRankEmbed-Small/tree/745d2a06103a66d3cfa600aa52fc0d3523010daa)
- [Pinned encoder implementation referenced by the published config](https://huggingface.co/Snowflake/snowflake-arctic-embed-m-long/tree/92d97331f1f4b6a366c1f161354b9f3390cc219f)
