# Full VibeMemBench memory stage

All 111 tasks in 90 repositories ran through the authors' identical `run_one`, scope, add/search, target-gold fingerprint checks, 64 decimal MB file limit, top-1 and memory.txt serialization. Six released files match upstream byte-for-byte. Methods only receive previous histories in the same repository, by trailing PR number, and the query comprises the target problem statement. The source release has 3,634 trajectories. The causal union across all targets is 2,471 unique files and 1,530,325,375 bytes, verified by Git blob hash or LFS SHA-256. One Qiskit history of 81.32 MB exceeded the default cap. The other 2,470 unique histories were used 3,858 times across target-specific indexes, with 449,043 history messages per arm. The frozen receipt construction/search used zero LLM calls and no target answer fields. The authors' immutable pipeline handles the hidden fields internally only for the leakage check.

| Method | With result | Stored records across indexes | Stored UTF-8 text bytes | Mean served words with header | Mean stage seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Own BM25 over raw historical steps | 111/111 | 234,594 | 303,925,254 | 205.41 | 0.73 |
| Author Echo (Jaccard) with common output cap | 111/111 | 234,594 | 362,053,505 | 175.44 | 0.60 |
| Own BM25 over observed-action receipts | 111/111 | 3,858 | 1,963,766 | 56.94 | 0.64 |

Each arm had the same maximum body budget of 240 whitespace-delimited words and 6,000 characters plus the authors' fixed source header. Actual lengths differ. Echo retains its unchanged index, score and top-1 choice; only the final body is capped. Both BM25 arms use the same positive-IDF formula and identifier tokenizer. The raw arm stores one historical step including available command, reasoning and output. The candidate stores at most one receipt per historical issue. Contents include observed tool invocation/results and paths from the old submission. UTF-8 totals measure logical record text, excluding postings, Python object overhead, file system storage, upstream history generation, the solver and evaluator. Elapsed time measures each complete official local write/search stage including loading/checks, at up to six concurrent processes. The two BM25 representations selected the same historical PR on only 18 of 111 queries.

Each of the 111 selected candidate receipts was checked against the original history step/tool output. In 27 cases the primary command had exit code 0 and an explicit positive test-output pattern. In 84 cases the primary command had exit code 0 and contained a viewing utility. Among those, 75 mentioned a saved prior patch or diff file. Some compound commands have additional operations. These are observations of the prior repository task. They supply no target-relevance or repair labels. The published executable endpoint is resolved using tests after the agent's patch. The only worked implementation shipped at the pin is Echo. The paper reports Mem0, SimpleMem, MemoryOS, A-MEM on DeepSeek-V4-Pro, GLM-5 and Kimi-K2.7-Code. GLM-5.2 and Qwen3.8-Max also appear in the distinct verified-experience transfer experiment. Those memory/hosted solver results were not reproduced in this stage. [Official code](https://github.com/AlibabaResearch/DAMO-ConvAI/blob/7152cf96809b45343ccc1caf7115a7d3fa43f956/VibeMemBench/scripts/run_memory.py) · [Per-target contract](https://github.com/AlibabaResearch/DAMO-ConvAI/blob/7152cf96809b45343ccc1caf7115a7d3fa43f956/VibeMemBench/scripts/CONTRACT.md) · [Dataset](https://huggingface.co/datasets/Tongyi-ConvAI/VibeMemBench/tree/11164976b4f920cdb0d0cd570ca572e49acea1e8) · [Original paper](https://arxiv.org/abs/2609.23570)

## Path navigability at the exact target commit

An exploratory diagnostic, specified after memory retrieval and before any target-path checks, applied one common extractor to each complete served body. It recognized up to three distinct candidate paths per item, excluded saved patch/diff files and environment artifacts, and requested the path from the exact target base commit. Across all 111 targets the action receipts contained at least one recognized candidate on 110 and a confirmed existing file on 102. Raw BM25 had 81 and 59, Echo 76 and 57. Across all per-item paths the confirmed fractions were 151/173, 75/146 and 68/122, respectively. The 380 distinct URLs gave 249 HTTP 206 and 131 HTTP 404. Commit-level availability checks succeeded on all 34 distinct snapshots checked when every candidate in a response was missing. Comparing action receipts against raw BM25 on the same targets yielded 47 candidate-only hits, 4 raw-only hits, 55 joint hits and 5 joint misses. Explicitly listing paths from prior submitted patches makes the new representation easier for this extractor to read. Any existing file counts; this diagnostic supplies no relevance or repair label. Median served lengths were 57, 245 and 177 words respectively.

## Reproduce

Run from this directory. Set `VIBE_BENCH_HOME` to a fresh writable location to avoid resuming existing records. Timings are from Windows, Python 3.12.13, pandas 2.2.3, PyArrow 17.0.0, NumPy 1.26.4. The repository stores reproducible scripts and compact output files. Source histories and installed packages stay on the external volume.

```powershell
python -m pip install pandas==2.2.3 pyarrow==17.0.0 numpy==1.26.4
$env:VIBE_BENCH_HOME='D:/CodexData/VibeMemBench'
python -X utf8 prepare_code.py
python -X utf8 fetch_history.py --workers 24
python -X utf8 run_stage.py --focus --workers 4
python -X utf8 run_stage.py --workers 6
python -X utf8 summarize.py
python -X utf8 path_probe.py
```

`protocol.md` documents the design and `methods.py` gives the frozen ranking/construction. `results.json`, `stage_rows.jsonl`, and `stage_outputs.zip` cover 333 paired method/target runs and their 666 official output files. The audit checks actual fed counts for every target/arm against the original source manifest. The separate `path-protocol.md`, `path_results.json`, `path_rows.jsonl` and diagnostic script check textual path navigability at the untouched target base commit.

For the separately selected solver cohort, brazilian-utils PR 125's candidate provided 54 words from PR 124 recording two historical pytest invocations (19 and 1 passed); raw BM25 returned 122 words from the same PR. For s-knibbs PR 64 the candidate supplied 45 words from a code inspection of past PR 10's patch, versus 224 words from PR 11 for raw BM25. Counts include the harness's source header.
