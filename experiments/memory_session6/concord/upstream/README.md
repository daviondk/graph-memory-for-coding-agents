<h1 align="center">When Agent Context Goes Stale:<br>Incoherence in Volatile Agent Context</h1>

<p align="center">
  <em>Keep tool observations coherent with the mutable sources they came from</em>
</p>

<p align="center">
  <a href="https://os-for-agent.github.io/"><img src="https://img.shields.io/badge/Workshop-AgenticOS%20%40%20SOSP%202026-0ea5e9?style=for-the-badge" alt="AgenticOS @ SOSP 2026"></a>
  <a href="#-quick-start"><img src="https://img.shields.io/badge/Quick_Start-uv-blue?style=for-the-badge" alt="Quick Start"></a>
  <a href="#-concordbench"><img src="https://img.shields.io/badge/ConcordBench-40_tasks-green?style=for-the-badge" alt="ConcordBench"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/runtime-block__context-7c3aed" alt="Runtime">
  <img src="https://img.shields.io/badge/recover-100%25_vs_oracle-10b981" alt="Recover">
  <img src="https://img.shields.io/badge/tokens-46.4%25_fewer-f59e0b" alt="Tokens">
</p>

<p align="center">
  <img src="asset/paper-overview.png" alt="System overview" width="820">
</p>

---

## 📰 News

- **2026-08** 🚀 Open-sourced Concord + ConcordBench for [AgenticOS @ SOSP 2026](https://os-for-agent.github.io/).

---

## 🤔 Why Concord

Agents increasingly ground reasoning in tool observations—file reads, workspace state, and other external resources. Those sources can later change (users, other agents, tools), while the model still holds only the **stale** text in its context window.

Most runtimes give little help when a previously observed fact becomes outdated. Agents then reuse stale observations and make incorrect claims about the current world.

**Concord** links each observation to its source, detects source changes, and applies configurable policies to update, annotate, or suppress stale context before reuse. The agent still sees ordinary trajectory text; coherence metadata stays on the system side.

<p align="center">
  <img src="asset/bench_example.png" alt="Stale observations in ConcordBench" width="820">
</p>

### System Design

```text
  ReAct trajectory                 Concord                      Mutable sources
+----------------------+    +----------------------+    +----------------------+
| LLM / tool call      |    | block_context        |    | workspace files      |
| tool return          |--->| SourceIndex          |<---| corpus docs          |
| (observation text)   |    | locators             |    |                      |
|                      |    |                      |    | write / B-side       |
| next step context <-------| render_safe()        |<---|                      |
+----------------------+    +----------------------+    +----------------------+
```

**High-level flow:**
1. Each tool return is registered as a block and bound in `SourceIndex` to its source file.
2. When a file changes, Concord finds affected blocks via the index.
3. Repairable blocks are relocated/recomputed; otherwise marked stale/invalid.
4. `render_safe()` feeds the next LLM step: update what it can, drop stale text, append a refresh notice if needed.

---

## ✨ Highlights

- **Provenance-indexed context** — observations stay tied to mutable sources
- **Configurable handling** — repair in place, annotate, or drop + refresh notice
- **Runtime-agnostic design** — package name in code: `block_context`
- **ConcordBench** — 40 HotpotQA agent tasks where observed files go stale mid-run
- **Strong results** — recovers **all** cases (matches oracle); non-oracle baselines recover **49.2%–87.5%**; **46.4%** fewer tokens than the strongest non-oracle baseline

### Results on ConcordBench (HotpotQA subset)

| Model | Method | Recover ↑ | Avg. Steps ↓ | Tokens ↓ |
|-------|--------|-----------|--------------|----------|
| **Claude Sonnet 5** | Oracle† | 40/40 (100%) | 3.03 | 285,417 |
| | Naive | 20/40 (50.0%) | 4.40 | 589,720 |
| | Alert | 26/40 (65.0%) | 4.33 | 609,750 |
| | Diff | 36/40 (90.0%) | 7.10 | 1,079,420 |
| | **Concord** | **40/40 (100%)** | **4.03** | **502,596** |
| **GLM 5.2** | Oracle† | 40/40 (100%) | 3.70 | 219,753 |
| | Naive | 15/40 (37.5%) | 4.68 | 408,511 |
| | Alert | 23/40 (57.5%) | 4.65 | 430,712 |
| | Diff | 31/40 (77.5%) | 6.73 | 663,430 |
| | **Concord** | **40/40 (100%)** | 4.75 | **389,953** |
| **DeepSeek V4 Pro** | Oracle† | 40/40 (100%) | 4.58 | 410,820 |
| | Naive | 24/40 (60.0%) | 5.60 | 562,851 |
| | Alert | 31/40 (77.5%) | 5.83 | 621,379 |
| | Diff | 38/40 (95.0%) | 8.20 | 903,032 |
| | **Concord** | **40/40 (100%)** | **5.38** | **524,862** |

† Oracle is the upper-bound setting (no A-side mutations). Bold marks the best non-oracle result per model (ties broken by recover, then tokens).

---

## 🚀 Quick Start

### 1. Clone & install

```bash
git clone https://github.com/FFFFFFFANG1/Concord.git
cd Concord

# runtime
UV_CACHE_DIR=.uv-cache uv sync

# ConcordBench harness
cd bench && UV_CACHE_DIR=../.uv-cache uv sync && cd ..
```

### 2. Configure API keys

```bash
cp .env.example .env
```

```text
LLM_API_KEY=
LLM_BASE_URL=
LLM_MODEL=

JUDGE_API_KEY=       # optional, for LLM judge
JUDGE_BASE_URL=
JUDGE_LLM=
```

### 3. Try the runtime

```bash
UV_CACHE_DIR=.uv-cache uv run python examples/v0_demo.py
```

```python
from block_context import BlockContextRuntime

runtime = BlockContextRuntime("workspace")
block = runtime.read_file("app.py", title="source", agent_id="agent-a")

doc = runtime.new_document()
doc.add_text("Context:\n")
doc.add_block(block)

runtime.write_file("app.py", "new content", agent_id="agent-b")
print(doc.render_safe().text)  # stale blocks dropped + refresh notice
```

### 4. Run ConcordBench (one task)

```bash
cd bench

# Concord policy + A/B race patches
UV_CACHE_DIR=../.uv-cache uv run python -m qa_agent.cli run-pioneer \
  --id hotpotqa-01 \
  --policy block_context \
  --race-candidates patch_candidate_augmented.json \
  --apply-a-side-mutations \
  --output /tmp/hotpotqa-01.json
```

---

## 🧪 ConcordBench

Each task is a small HotpotQA workspace. The agent uses `grep` / `read_file` / `glob` / `answer`. With race patches, A-side mutations are applied first; after the agent reads patched evidence, B-side restore returns files to the original text. Scoring always uses the original gold answer.

| Paper | CLI `--policy` |
|-------|----------------|
| Oracle | `raw` (no patches) |
| Naive | `raw` + patches |
| Alert | `system_alert` |
| Diff | `git` |
| **Concord** | `block_context` |

**Tasks:** `bench/pioneer_augmented.json` (40)  
**Patches:** `bench/patch_candidate_augmented.json`

### Full eval + judge

```bash
cd bench

UV_CACHE_DIR=../.uv-cache uv run python -m qa_agent.eval_pioneer \
  --policy block_context \
  --pioneer pioneer_augmented.json \
  --race-candidates patch_candidate_augmented.json \
  --apply-a-side-mutations \
  --opaque-doc-ids \
  --max-tool-calls-per-event 1 \
  --max-events 30 \
  --max-workers 8 \
  --save-traces \
  --output runs/my_block_context_eval.json

UV_CACHE_DIR=../.uv-cache uv run python -m qa_agent.llm_judge \
  --input runs/my_block_context_eval.json \
  --pioneer pioneer_augmented.json \
  --output runs/my_block_context_eval_judged.json
```

Paper result summaries for three models are in `bench/runs/` (`*_five_strategies_summary.json`).

---

## 📁 Layout

```text
src/block_context/   # Concord runtime
bench/               # ConcordBench harness + data + runs
examples/            # minimal demo
asset/               # paper figures
```

---

## 📚 Citation

If you use this repository, please cite our paper at [AgenticOS @ SOSP 2026](https://os-for-agent.github.io/):

```text
When Agent Context Goes Stale: Incoherence in Volatile Agent Context
AgenticOS Workshop @ SOSP 2026, Prague, Czechia
```

BibTeX will be added with the camera-ready version.
