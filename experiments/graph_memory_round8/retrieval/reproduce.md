# Reproducing the four panels

Use a fresh writable copy containing the scripts and frozen protocols. The ranking stages refuse an already sealed run for the dense SWE/Loc panels. The public inputs are downloaded into `SWERANK_TEMP`, default `D:/CodexResearch/x20-r8-swerank-runtime`. Primary rankings and outcomes are written beside the scripts. In the retained study directory all four prediction sets, judgments, SHA-256 manifests, per-query outcomes, and full aggregate JSON files are available without an encoder download. Run `python verify.py` to validate them. Set `PYTHONUTF8=1` on Windows if your default encoding is not UTF-8.

The observed environment was Windows, CPython 3.12, PyTorch 2.6.0+cpu, Transformers 4.52.4, four intra-op threads and one inter-op thread per encoder process. The entire CPU inference for the 18-task dense panel took 488.5 seconds in the measured run, with other local work active; this is a workload observation, not a model latency benchmark. Library versions are saved in [environment.txt](environment.txt). No CUDA, model generation, API credits, remote model inference or training was used.

```powershell
python acquire.py model
python encoder.py
python prepare.py
python rank.py
python score.py

python pool_rank.py
python pool_score.py
python loc_rank.py
python loc_score.py
python degree_rank.py
python degree_score.py
python verify.py
```

`encoder.py` downloads two Python modules pinned at Snowflake revision 92d97331f1f4b6a366c1f161354b9f3390cc219f. It then reads local safetensors, validates that the entire state dict matches the architecture, selects CPU attention and sanity-checks output shape. Runtime downloads neither custom code nor weights by name after this setup. Inputs come from the official authors' archive, identified by Google Drive file ID in [acquire.py](acquire.py). Its ZIP directory offset and size, each extracted member's CRC and each corpus's retained SHA guard the version. File-level hashes for official model weights are in [model_manifest.json](model_manifest.json) and the official backend hashes are in [backend_manifest.json](backend_manifest.json). The official raw QREL hashes plus actual IDs are logged in the three SWE and one Loc judgments files.

The experimental chain is generation, hash seal, then assessment. All CLI stages must complete before the immediately dependent one. Four protocols specify the sampling and expected scoring. The independent degree follow-up intentionally uses the discovery-panel observations documented in the report. Sampling excludes the other SWE panels and the materials do not present this as a double-blind research study. Initial same-subset encoder ranking is not equivalent to full retrieval over SWE-bench Lite. Full-corpus Loc-Bench uses a six-project convenience panel.

The optional R7 overlap report searches for the existing local sibling directory `graph_memory_round7/localization`. On a fresh machine without the R7 artifacts, the additional overlap field is null. Published benchmark Acc@k uses an all-target criterion and may rely on an extra filtered annotation set. Our all10 and recall use the retained original function-level BEIR qrels, with every labeled target in the denominator.
