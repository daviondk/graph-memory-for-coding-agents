---
pretty_name: "Memory Representation ContextBench Artifacts"
license: "other"
language:
- en
tags:
- software-engineering
- llm-agents
- coding-agents
- trajectories
- swe-bench
- contextbench
- agent-memory
- tabular
- text
configs:
- config_name: prompts
  data_files:
  - split: train
    path: data/prompts/train.parquet
- config_name: targets
  data_files:
  - split: train
    path: data/targets/train.parquet
- config_name: runs
  data_files:
  - split: train
    path: data/runs/train.parquet
- config_name: patch_manifest
  data_files:
  - split: train
    path: data/patch_manifest/train.parquet
- config_name: timeline_events
  data_files:
  - split: train
    path: data/timeline_events/train.parquet
- config_name: evidence_inventory
  data_files:
  - split: train
    path: data/evidence_inventory/train.parquet
- config_name: evidence_target_overlap
  data_files:
  - split: train
    path: data/evidence_target_overlap/train.parquet
- config_name: mechanism_attribution
  data_files:
  - split: train
    path: data/mechanism_attribution/train.parquet
- config_name: disagreement_cases
  data_files:
  - split: train
    path: data/disagreement_cases/train.parquet
- config_name: time_to_gold_file
  data_files:
  - split: train
    path: data/time_to_gold_file/train.parquet
- config_name: test_command_reuse
  data_files:
  - split: train
    path: data/test_command_reuse/train.parquet
- config_name: failure_signature_reuse
  data_files:
  - split: train
    path: data/failure_signature_reuse/train.parquet
---
# Memory Representation ContextBench Artifacts

## Dataset Summary

This repository contains processed artifacts for the paper "Memory as a Map: Prior-Trajectory Representations for Software Engineering Agents." The artifact supports reproduction and inspection of a controlled prior-context representation experiment over SWEContextBench prior-target pairs.

The experiment renders each target under four prompt conditions: no prior context, stripped Claude Code transcript replay, normalized ADP action trace, and deterministic evidence digest. The target issue and task instructions are held fixed across conditions; the intended intervention is only the PRIOR_CONTEXT section.

## Contents

- `prompts`: 384 rows. Columns: target_id, prior_id, repo, condition, artifact_condition, prompt_text, prompt_path, prompt_sha256, prior_context_text, prior_context_path, prior_context_sha256, target_issue_sha256, prompt_chars, prior_context_chars, valid_target, excluded, exclusion_reason.
- `targets`: 96 rows. Columns: target_id, repo, prior_id, valid_target, excluded, exclusion_reason, target_issue_sha256, target_gold_files_json, prior_gold_files_json, gold_overlap_bucket, prior_localization_bucket.
- `runs`: 380 rows. Columns: target_id, repo, condition, artifact_condition, run_id, resolved, non_empty_patch, empty_patch, eval_no_patch, eval_patch_failed, other_eval_error, eval_status, patch_path, patch_sha256, openhands_run_path, evaluator_log_path, anomaly, anomaly_note.
- `patch_manifest`: 380 rows. Columns: target_id, condition, artifact_condition, patch_path, patch_sha256, patch_bytes, patch_touches_target_gold_file, edited_target_gold_file, modified_files_json.
- `timeline_events`: 0 rows. Columns: target_id, condition, artifact_condition, tool_step, event_type, tool_name, file_path, command, is_target_gold_file, is_prior_evidence, clipped, raw_event_json.
- `evidence_inventory`: 0 rows. Columns: target_id, condition, artifact_condition, evidence_type, evidence_value, evidence_sha256, source_step, source_file, notes.
- `evidence_target_overlap`: 380 rows. Columns: target_id, condition, artifact_condition, mentions_target_gold_file, mentions_target_gold_dir, contains_relevant_test_command, contains_prior_inspected_gold_file, agent_reads_target_gold_file, agent_edits_target_gold_file, agent_runs_tests, resolved.
- `mechanism_attribution`: 380 rows. Columns: target_id, condition, artifact_condition, label, evidence, confidence_or_source, notes.
- `disagreement_cases`: 24 rows. Columns: target_id, pattern, none_resolved, trace_resolved, action_resolved, digest_resolved, why_included, prior_target_relation, mechanism_hypothesis, notes.
- `time_to_gold_file`: 380 rows. Columns: target_id, condition, artifact_condition, first_target_gold_file_read_step, never_read_target_gold_file, search_command_count, resolved.
- `test_command_reuse`: 380 rows. Columns: target_id, condition, artifact_condition, prior_test_command, reused_test_command, reuse_match_type, resolved.
- `failure_signature_reuse`: 380 rows. Columns: target_id, condition, artifact_condition, prior_failure_signature, observed_failure_signature, reuse_match_type, resolved.

CSV summary tables are under `tables/`. Per-file checksums are under `manifests/SHA256SUMS`; table schemas are under `schemas/`.

The artifact contains 384 rendered prompt rows for 96 original targets and 380 evaluated run rows for the final 95 valid targets. The excluded target is `django__django-28147`: sandbox image did not contain the expected manifest base commit.

## Relation to Raw Trajectories

This processed artifact is the primary reproducibility artifact. Raw or reformatted trajectories, if released, are provided separately in `memory-representation-contextbench-traces`.

## Source Data

Sources include SWEContextBench target/prior pairs, Claude Code prior trajectories, OpenHands/Qwen target runs, generated evaluator summaries, and derived analysis tables. The license is composite; users should inspect upstream dataset licenses and terms before reuse.

## Processing Pipeline

The pipeline converts Claude Code JSONL to canonical ADP, strips ADP fields for controlled prompt rendering, renders raw/trace prior context, renders normalized action traces, renders deterministic evidence digests, evaluates target runs with OpenHands/Qwen, and derives transcript or evaluator based behavioral tables where source data is available.

## Limitations

Mechanism labels are post hoc. The representation-choice oracle is retrospective. This artifact corresponds to one OpenHands/Qwen setup. Full OpenHands JSONL event traces were not present in the source tree, so event-level behavioral tables contain nulls or empty rows where the source field is unavailable.

## Missing Optional Files

- `figures/fig_paired_effects.png`
- `figures/fig_localization_map.png`
- `figures/fig_solve_complementarity_oracle.png`
- `figures/fig_patch_action_funnel.png`
- `figures/appendix_fig_evidence_action_heatmap.png`
- `figures/fig_disagreement_timeline_raster.png`

## Citation

```bibtex
@inproceedings{memory_as_a_map_2026,
  title = {Memory as a Map: Prior-Trajectory Representations for Software Engineering Agents},
  author = {Anonymous},
  booktitle = {Workshop paper},
  year = {2026}
}
```
