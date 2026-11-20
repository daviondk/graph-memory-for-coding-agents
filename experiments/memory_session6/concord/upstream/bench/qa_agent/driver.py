from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from block_context import BlockContextRuntime

from qa_agent.adapters.hotpot import HotpotAdapter
from qa_agent.llm import LLMProvider
from qa_agent.loop import AgentRunResult, Policy, run_agent
from qa_agent.race import RaceController
from qa_agent.tools.hotpot import build_hotpot_registry

Benchmark = Literal["hotpotqa"]


@dataclass(slots=True)
class InstanceBundle:
    benchmark: Benchmark
    question: str
    gold_answer: str
    adapter: HotpotAdapter
    runtime: BlockContextRuntime
    registry: Any
    instance_root: Path | None = None
    metadata: dict[str, Any] | None = None


def load_hotpot_instance(instance_root: Path) -> InstanceBundle:
    task = json.loads((instance_root / "task.json").read_text(encoding="utf-8"))
    adapter = HotpotAdapter(instance_root)
    runtime = BlockContextRuntime(adapter.workspace_root())
    registry = build_hotpot_registry(adapter, runtime)
    return InstanceBundle(
        benchmark="hotpotqa",
        question=task["question"],
        gold_answer=task["answer"],
        adapter=adapter,
        runtime=runtime,
        registry=registry,
        instance_root=instance_root,
        metadata=task,
    )


def _hotpot_data_root(bench_root: Path, payload: dict) -> Path:
    rel = payload.get("hotpot_data_root")
    if rel:
        return (bench_root / rel).resolve()
    return bench_root / "data" / "hotpotqa" / "fullwiki" / "validation"


def load_pioneer_instance(
    pioneer_id: str,
    *,
    bench_root: Path,
    pioneer_path: Path | None = None,
    cache_dir: Path | None = None,
    opaque_doc_ids: bool = False,
    max_grep_per_event: int | None = None,
    max_tool_calls_per_event: int | None = None,
) -> InstanceBundle:
    pioneer_file = pioneer_path or (bench_root / "pioneer_augmented.json")
    payload = json.loads(pioneer_file.read_text(encoding="utf-8"))
    cache = cache_dir or (bench_root / ".pioneer_cache")
    hotpot_data_root = _hotpot_data_root(bench_root, payload)

    for record in payload.get("hotpotqa", []):
        if record["id"] == pioneer_id:
            adapter = HotpotAdapter.from_pioneer_record(
                record,
                hotpot_data_root,
                cache,
                opaque_doc_ids=opaque_doc_ids,
                max_grep_per_event=max_grep_per_event,
                max_tool_calls_per_event=max_tool_calls_per_event,
            )
            runtime = BlockContextRuntime(adapter.workspace_root())
            registry = build_hotpot_registry(adapter, runtime)
            return InstanceBundle(
                benchmark="hotpotqa",
                question=record["question"],
                gold_answer=record["answer"],
                adapter=adapter,
                runtime=runtime,
                registry=registry,
                instance_root=cache / "hotpotqa" / pioneer_id,
                metadata=record,
            )

    raise KeyError(f"pioneer id not found: {pioneer_id}")


def run_instance(
    bundle: InstanceBundle,
    provider: LLMProvider,
    *,
    policy: Policy = "raw",
    max_events: int = 30,
    race_controller: RaceController | None = None,
) -> AgentRunResult:
    return run_agent(
        provider,
        bundle.registry,
        bundle.adapter,
        bundle.question,
        runtime=bundle.runtime,
        policy=policy,
        max_events=max_events,
        race_controller=race_controller,
    )


def result_to_dict(result: AgentRunResult, bundle: InstanceBundle) -> dict[str, Any]:
    safe_text = None
    if result.document is not None:
        safe_text = result.document.render_safe().text
    return {
        "benchmark": bundle.benchmark,
        "question": bundle.question,
        "gold_answer": bundle.gold_answer,
        "final_answer": result.final_answer,
        "stop_reason": result.stop_reason,
        "policy": result.policy,
        "events": [
            {
                "event_id": event.event_id,
                "reasoning": event.reasoning,
                "tool_calls": [asdict(tool_call) for tool_call in event.tool_calls],
            }
            for event in result.events
        ],
        "race_events": [asdict(event) for event in result.race_events],
        "resend_answer_count": result.resend_answer_count,
        "event_count": result.event_count,
        "tool_call_count": result.tool_call_count,
        "llm_call_count": result.llm_call_count,
        "token_usage": {
            "prompt_tokens": result.token_usage.prompt_tokens,
            "completion_tokens": result.token_usage.completion_tokens,
            "total_tokens": result.token_usage.total_tokens,
        },
        "safe_rendered_context": safe_text,
    }
