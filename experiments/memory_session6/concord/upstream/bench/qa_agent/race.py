from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable

from block_context import BlockContextRuntime
from block_context.types import BlockState

from qa_agent.adapters.base import DatasetAdapter


@dataclass(frozen=True, slots=True)
class RacePatch:
    evidence_id: str
    source_path: str
    original_text: str
    mutated_text: str
    race_trigger: str
    role: str | None = None

    @property
    def trigger_source(self) -> str:
        prefix = "after_read:"
        if not self.race_trigger.startswith(prefix):
            raise ValueError(f"unsupported race trigger: {self.race_trigger}")
        return self.race_trigger[len(prefix) :]

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> RacePatch:
        return cls(
            evidence_id=str(payload["evidence_id"]),
            source_path=str(payload["source_path"]),
            original_text=str(payload["original_text"]),
            mutated_text=str(payload["mutated_text"]),
            race_trigger=str(payload["race_trigger"]),
            role=str(payload["role"]) if payload.get("role") is not None else None,
        )


@dataclass(frozen=True, slots=True)
class PatchApplicationRecord:
    evidence_id: str
    source_path: str
    status: str
    affected_block_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RaceEventRecord:
    step_index: int
    boundary: str
    reason: str
    trigger: str
    delay_steps: int
    applications: tuple[PatchApplicationRecord, ...]


@dataclass(slots=True)
class _PatchState:
    patch: RacePatch
    restored: bool = False


class RaceController:
    """Per-patch independent race controller.

    Each patch has its own mutated→restored lifecycle, independent of other
    patches in the same task. Triggers:

    1. read_file hitting a patch's source → restore that patch only.
    2. grep returning hits, then the next action is NOT read_file on one of
       those hits → restore patches whose source was in the grep hits.
    3. answer() called while patches remain unrestored → discard the answer,
       restore all remaining patches, and let the agent re-respond from the
       previous tool-return state.
    """

    def __init__(self, patches: Iterable[RacePatch], *, delay_steps: int = 0) -> None:
        if delay_steps < 0:
            raise ValueError("delay_steps must be >= 0")
        self.delay_steps = delay_steps
        self.events: list[RaceEventRecord] = []
        self._states: list[_PatchState] = [_PatchState(p) for p in patches]
        self._step_index = 0
        self._pending_grep_sources: set[str] = set()
        self._generation = 0
        self._pending_alerts: list[str] = []
        self.resend_answer_count = 0
        self.max_answer_retries = 3

    @property
    def patches(self) -> tuple[RacePatch, ...]:
        return tuple(s.patch for s in self._states)

    @property
    def applied(self) -> bool:
        return all(s.restored for s in self._states)

    def has_unrestored_patches(self) -> bool:
        return any(not s.restored for s in self._states)

    @property
    def generation(self) -> int:
        return self._generation

    def unrestored_patches(self) -> list[_PatchState]:
        return [s for s in self._states if not s.restored]

    def restored_patches(self) -> list[_PatchState]:
        return [s for s in self._states if s.restored]

    def apply_a_side_mutations(self, runtime: BlockContextRuntime) -> tuple[PatchApplicationRecord, ...]:
        applications: list[PatchApplicationRecord] = []
        for s in self._states:
            applications.append(
                _apply_replacement(
                    runtime,
                    source_path=s.patch.source_path,
                    old=s.patch.original_text,
                    new=s.patch.mutated_text,
                    evidence_id=s.patch.evidence_id,
                    already_text=s.patch.mutated_text,
                    already_status="already_mutated",
                    applied_status="mutated",
                )
            )
        if applications:
            self._generation += 1
        return tuple(applications)

    def current_diff_text(self) -> str:
        restored = self.restored_patches()
        if not restored:
            return "No workspace changes."

        paths = sorted({s.patch.source_path for s in restored})
        lines = ["Modified files:"]
        lines.extend(f"- {path}" for path in paths)
        for s in restored:
            patch = s.patch
            lines.extend(
                [
                    "",
                    f"diff -- {patch.source_path}",
                    f"- {patch.mutated_text}",
                    f"+ {patch.original_text}",
                ]
            )
        return "\n".join(lines)

    @property
    def has_pending_alerts(self) -> bool:
        return bool(self._pending_alerts)

    def consume_alerts(self) -> str:
        if not self._pending_alerts:
            return ""
        alerts = "\n".join(self._pending_alerts)
        self._pending_alerts.clear()
        return alerts

    def inspect_response_for_answer(self, response: Any, runtime: BlockContextRuntime) -> bool:
        """Check if response contains answer while patches are unrestored.

        If so, restore all remaining patches and return True (discard & retry).
        Returns False if no interception needed.
        """
        if not self.has_unrestored_patches():
            return False
        if not getattr(response, "should_execute_tools", False):
            return False
        has_answer = any(tc.name == "answer" for tc in response.tool_calls)
        if not has_answer:
            return False
        if self.resend_answer_count >= self.max_answer_retries:
            return False
        self.resend_answer_count += 1
        self._restore_all_remaining(
            runtime, boundary="before_answer", reason="premature_answer_intercept"
        )
        return True

    def before_tool_call(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        *,
        adapter: DatasetAdapter,
        runtime: BlockContextRuntime,
    ) -> None:
        if not self._pending_grep_sources:
            return
        if tool_name == "read_file":
            read_source = _resolve_read_source(tool_args, adapter)
            read_forms = _source_forms(read_source)
            hits_read = {s for s in self._pending_grep_sources if _source_forms(s) & read_forms}
            hits_not_read = self._pending_grep_sources - hits_read
            if hits_not_read:
                self._trigger_sources(
                    hits_not_read, runtime, boundary="before_tool_call", reason="grep_hit_not_read"
                )
            self._pending_grep_sources.clear()
        else:
            self._trigger_sources(
                self._pending_grep_sources, runtime, boundary="before_tool_call", reason="grep_not_followed_by_read"
            )
            self._pending_grep_sources.clear()

    def after_tool_return(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_result_text: str,
        *,
        adapter: DatasetAdapter,
        runtime: BlockContextRuntime,
    ) -> None:
        self._step_index += 1
        if tool_name == "grep":
            hits = _parse_grep_paths(tool_result_text)
            self._pending_grep_sources = hits
        elif tool_name == "read_file":
            read_source = _resolve_read_source(tool_args, adapter)
            matching = self._patches_matching_read(read_source)
            if matching:
                self._restore_patches(
                    matching, runtime, boundary="after_tool_return", reason="read_file_trigger"
                )

    def _restore_patches(
        self,
        states: list[_PatchState],
        runtime: BlockContextRuntime,
        *,
        boundary: str,
        reason: str,
    ) -> None:
        applications: list[PatchApplicationRecord] = []
        for s in states:
            if s.restored:
                continue
            app = _apply_replacement(
                runtime,
                source_path=s.patch.source_path,
                old=s.patch.mutated_text,
                new=s.patch.original_text,
                evidence_id=s.patch.evidence_id,
                already_text=s.patch.original_text,
                already_status="already_original",
                applied_status="restored",
            )
            s.restored = True
            applications.append(app)
        if applications:
            self._generation += 1
            self._pending_alerts.extend(
                f"[alert] {path} is modified"
                for path in sorted({app.source_path for app in applications})
            )
            self.events.append(
                RaceEventRecord(
                    step_index=self._step_index,
                    boundary=boundary,
                    reason=reason,
                    trigger="per_patch",
                    delay_steps=self.delay_steps,
                    applications=tuple(applications),
                )
            )

    def _trigger_sources(
        self,
        sources: set[str],
        runtime: BlockContextRuntime,
        *,
        boundary: str,
        reason: str,
    ) -> None:
        to_restore: list[_PatchState] = []
        for s in self._states:
            if s.restored:
                continue
            patch_forms = _source_forms(s.patch.source_path) | _source_forms(s.patch.trigger_source)
            if any(_source_forms(src) & patch_forms for src in sources):
                to_restore.append(s)
        self._restore_patches(to_restore, runtime, boundary=boundary, reason=reason)

    def _restore_all_remaining(
        self,
        runtime: BlockContextRuntime,
        *,
        boundary: str,
        reason: str,
    ) -> None:
        remaining = self.unrestored_patches()
        self._restore_patches(remaining, runtime, boundary=boundary, reason=reason)

    def _patches_matching_read(self, read_source: str) -> list[_PatchState]:
        return [
            s
            for s in self._states
            if not s.restored
            and (
                _source_matches(read_source, s.patch.source_path)
                or _source_matches(read_source, s.patch.trigger_source)
            )
        ]


def load_race_patches(candidate_path: Path, task_id: str) -> tuple[RacePatch, ...]:
    payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    for task in payload.get("tasks", []):
        if task.get("id") == task_id:
            return tuple(RacePatch.from_mapping(patch) for patch in task.get("patches", []))
    raise KeyError(f"patch candidate task not found: {task_id}")


_GREP_PATH_RE = re.compile(r"^path:\s*(\S+)", re.MULTILINE)


def _parse_grep_paths(tool_result_text: str) -> set[str]:
    return {m.group(1) for m in _GREP_PATH_RE.finditer(tool_result_text)}


def _apply_replacement(
    runtime: BlockContextRuntime,
    *,
    source_path: str,
    old: str,
    new: str,
    evidence_id: str,
    already_text: str,
    already_status: str,
    applied_status: str,
) -> PatchApplicationRecord:
    if _is_hotpot_corpus_json(source_path):
        return _apply_hotpot_sentence_replacement(
            runtime,
            source_path=source_path,
            old=old,
            new=new,
            evidence_id=evidence_id,
            already_text=already_text,
            already_status=already_status,
            applied_status=applied_status,
        )

    path = runtime.workspace_root / source_path
    content = path.read_text(encoding="utf-8")
    if old in content:
        affected = runtime.apply_text_replacement(source_path, old, new)
        _repair_observation_blocks(
            runtime,
            affected,
            source_path=source_path,
            old=old,
            new=new,
        )
        return PatchApplicationRecord(
            evidence_id=evidence_id,
            source_path=source_path,
            status=applied_status,
            affected_block_ids=tuple(block.id for block in affected if block.id is not None),
        )
    if already_text in content:
        return PatchApplicationRecord(
            evidence_id=evidence_id,
            source_path=source_path,
            status=already_status,
        )
    raise ValueError(f"neither expected patch text was found in {source_path}")


def _repair_observation_blocks(
    runtime: BlockContextRuntime,
    affected: list[Any],
    *,
    source_path: str,
    old: str,
    new: str,
) -> None:
    """Patch agent-visible observation blocks after source coherence runs."""
    if not affected:
        return
    if not _is_local_observation_repair(old, new):
        return
    new_version = runtime.source_version(source_path)
    for block in affected:
        if block.metadata.get("observation_text") != "agent-visible":
            continue
        if old not in block.content:
            continue
        block.content = block.content.replace(old, new)
        block.source_set = tuple(
            replace(ref, version=new_version) if ref.object_id == source_path else ref
            for ref in block.source_set
        )
        block.state = BlockState.VALID
        block.stale_reason = None
        block.metadata["last_coherence_action"] = "observation-text-replacement-on-patch"


def _is_local_observation_repair(old: str, new: str) -> bool:
    """Only auto-repair observations for small local edits.

    Broad sentence rewrites are intentionally left stale so the block-context
    policy has to surface a refresh notice instead of silently rewriting prose.
    """
    if not old or not new:
        return False
    if old == new:
        return True
    old_tokens = re.findall(r"\w+", old.lower())
    new_tokens = re.findall(r"\w+", new.lower())
    if old_tokens and len(old_tokens) == len(new_tokens):
        changed = sum(1 for left, right in zip(old_tokens, new_tokens, strict=True) if left != right)
        if changed <= max(2, len(old_tokens) // 5):
            return True
    ratio = SequenceMatcher(None, old, new).ratio()
    return ratio >= 0.78


def _is_hotpot_corpus_json(source_path: str) -> bool:
    normalized = source_path.replace("\\", "/")
    return normalized.startswith("corpus/") and normalized.endswith(".json")


def _sentence_fingerprint(text: str, *, length: int = 48) -> str:
    normalized = " ".join(text.split())
    return normalized[:length]


def _apply_hotpot_sentence_replacement(
    runtime: BlockContextRuntime,
    *,
    source_path: str,
    old: str,
    new: str,
    evidence_id: str,
    already_text: str,
    already_status: str,
    applied_status: str,
) -> PatchApplicationRecord:
    path = runtime.workspace_root / source_path
    payload = json.loads(path.read_text(encoding="utf-8"))
    sentences = payload.get("sentences")
    if not isinstance(sentences, list):
        raise ValueError(f"Hotpot corpus file missing sentences array: {source_path}")

    fingerprint = _sentence_fingerprint(old if applied_status == "mutated" else new)

    if old in sentences:
        sentences[sentences.index(old)] = new
        status = applied_status
    elif already_text in sentences:
        return PatchApplicationRecord(
            evidence_id=evidence_id,
            source_path=source_path,
            status=already_status,
        )
    else:
        replaced = False
        for idx, sentence in enumerate(sentences):
            if isinstance(sentence, str) and old in sentence:
                sentences[idx] = sentence.replace(old, new, 1)
                replaced = True
                break
        if not replaced:
            for idx, sentence in enumerate(sentences):
                if isinstance(sentence, str) and already_text in sentence:
                    return PatchApplicationRecord(
                        evidence_id=evidence_id,
                        source_path=source_path,
                        status=already_status,
                    )
            for idx, sentence in enumerate(sentences):
                if isinstance(sentence, str) and sentence.startswith(fingerprint):
                    if applied_status == "mutated":
                        return PatchApplicationRecord(
                            evidence_id=evidence_id,
                            source_path=source_path,
                            status="superseded",
                        )
                    sentences[idx] = new
                    replaced = True
                    status = applied_status
                    break
            if not replaced:
                raise ValueError(f"neither expected patch text was found in {source_path}")
        else:
            status = applied_status

    payload["sentences"] = sentences
    payload["lines"] = [f"{idx + 1}. {sentence}" for idx, sentence in enumerate(sentences)]
    affected = runtime.write_file(
        source_path,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )
    _repair_observation_blocks(
        runtime,
        affected,
        source_path=source_path,
        old=old,
        new=new,
    )
    return PatchApplicationRecord(
        evidence_id=evidence_id,
        source_path=source_path,
        status=status,
        affected_block_ids=tuple(block.id for block in affected if block.id is not None),
    )


def _resolve_read_source(tool_args: dict[str, Any], adapter: DatasetAdapter) -> str:
    raw_path = str(tool_args.get("path", ""))
    try:
        return adapter.resolve_source_path(raw_path)
    except Exception:
        return raw_path


def _source_matches(left: str, right: str) -> bool:
    return bool(_source_forms(left) & _source_forms(right))


def _source_forms(value: str) -> set[str]:
    normalized = value.strip().replace("\\", "/").lstrip("./").lower()
    path = Path(normalized)
    forms = {normalized}
    if path.name:
        forms.add(path.name)
        forms.add(path.stem)
    if "/mutated/" in normalized:
        forms.add(normalized.replace("/mutated/", "/original/"))
    if "/original/" in normalized:
        forms.add(normalized.replace("/original/", "/mutated/"))
    return {form for form in forms if form}
