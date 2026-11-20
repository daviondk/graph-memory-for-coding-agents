# In-session reuse of observed shell reads

On all 2,470 source histories, the bounded selective cache reproduced 270 complete process observations, made no stale or unscorable returns, and abstained on 54,078 of 54,348 eligible reads. Whole-cache flushing reproduced 250 with no observed errors. The paired difference was +0.368 correct responses per 1,000 eligible reads, repository-resampled 95% interval +0.205 to +0.576 (10,000 draws of all 90 repositories). All 20 discordances favored selective retention, across 19 histories and 15 repositories. After removing patch.txt results descriptively, counts were 243 and 229. The unguarded unlimited-count cache made 1,306 correct and 1,354 stale returns (50.9% of its 2,660 serves were stale). Fixed TTL1 made 85 correct and zero stale returns; TTL3 made 274 correct and 508 stale. All policy outputs were compared with the same recorded responses, at fixed future requests. [Pinned VibeMemBench histories](https://huggingface.co/datasets/Tongyi-ConvAI/VibeMemBench/tree/11164976b4f920cdb0d0cd570ca572e49acea1e8)

The 149,344 source commands include 55,066 syntactically eligible one-file reads; 718 were in mixed batches so only 54,348 could call the cache. On 2,769 of those the same exact command had occurred in an earlier eligible batch, and 51,372 responses had intact visible wrappers and fit the common 16 KiB per-value budget. Of the 54,348 observations, 2,976 were marked truncated in the benchmark display. All reported hit outcomes were measurable from recorded merged process stdout/stderr plus exit status, preserving UTF-8 exactly. One tool may itself truncate a process before logging. The selective cache held a mean 3,244.8 bytes at an assistant decision boundary (106,640 max), global flushing 3,159.2 bytes (same peak). The field is textual payload size, excluding Python object/hash-table overhead. No wall-clock execution saving or agent-token saving was measured. Natural external writers, symlink targets, shell aliases and downstream behavior after a stale hit are outside instrumented evidence.

Concord previously implemented source-linked invalidation/update/annotation and evaluated it on constructed volatile-context tasks. This experiment tests the limited coverage and observed stale/cost tradeoff of inferring mutations only from natural commands. [Concord paper](https://arxiv.org/abs/2610.05281)

## Reproduction

Use Python 3.14.4 and NumPy as recorded in summary.json. No LLM, processes from traces, GPU or target solutions are needed. Unpack ledgers.zip in this folder (and within_task/ledgers.zip in that sibling folder). To recreate the corpus on a new drive run ../within_task/prepare.py --base PATH; an existing immutable source directory can be passed directly. Keep the supplied freeze.json. Run:

    python canary.py
    python run.py --base D:/vibe-work-cache
    python summary.py
    python audit.py --base D:/vibe-work-cache

The single-worker replay took 20.40 s on the study host. summary.py checks each hit's source SHA and exit status, prior turn, identical key and admissibility, independently of the in-memory simulator. queries.jsonl.gz has 54,348 decisions and seven arms ordered as runtime.json; null is a miss, other records give previous batch, slot and outcome. batches.jsonl.gz preserves all 133,834 batch branches, declared classifications, known writes and cache sizes. histories.jsonl.gz preserves 2,470 source hashes and all counts. repositories.csv and source_audit.json give paired contributions and all 20 discordances. The independent transfer is in replication/.
