from __future__ import annotations

import json
import re
import string
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from qa_agent.driver import load_pioneer_instance, result_to_dict, run_instance
from qa_agent.llm import LLMProvider
from qa_agent.parallel import run_parallel
from qa_agent.race import RaceController, load_race_patches


def normalize_answer(text: str) -> str:
    text = text.lower()

    def remove_articles(value: str) -> str:
        return re.sub(r"\b(a|an|the)\b", " ", value)

    def remove_punc(value: str) -> str:
        exclude = set(string.punctuation)
        return "".join(ch for ch in value if ch not in exclude)

    return " ".join(remove_articles(remove_punc(text)).split())


def exact_match(prediction: str, gold: str) -> bool:
    return normalize_answer(prediction) == normalize_answer(gold)


def token_f1(prediction: str, gold: str) -> float:
    pred_tokens = normalize_answer(prediction).split()
    gold_tokens = normalize_answer(gold).split()
    if not pred_tokens and not gold_tokens:
        return 1.0
    if not pred_tokens or not gold_tokens:
        return 0.0
    common = Counter(pred_tokens) & Counter(gold_tokens)
    num_same = sum(common.values())
    if num_same == 0:
        return 0.0
    precision = num_same / len(pred_tokens)
    recall = num_same / len(gold_tokens)
    return 2 * precision * recall / (precision + recall)


@dataclass(slots=True)
class TaskMetrics:
    id: str
    benchmark: str
    gold_answer: str
    final_answer: str
    stop_reason: str
    event_count: int
    resend_answer_count: int
    exact_match: bool
    token_f1: float
    elapsed_s: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    llm_call_count: int = 0


def bench_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _search_stats(events: list) -> dict:
    search_tools = {"grep", "glob"}
    search_calls = []
    for event in events:
        for tc in event.get("tool_calls", []):
            if tc.get("tool_name") in search_tools:
                search_calls.append({"event_id": event.get("event_id"), "tool": tc.get("tool_name")})
    events_with_search = sorted({c["event_id"] for c in search_calls})
    return {
        "search_call_count": len(search_calls),
        "grep_call_count": sum(1 for c in search_calls if c["tool"] == "grep"),
        "search_event_count": len(events_with_search),
    }


def _run_single_pioneer_task(
    pioneer_id: str,
    *,
    root: Path,
    pioneer_file: Path,
    provider: LLMProvider,
    policy: str,
    max_events: int,
    cache_dir: Path | None,
    opaque_doc_ids: bool,
    max_grep_per_event: int | None,
    max_tool_calls_per_event: int | None,
    save_traces: bool,
    race_candidate_path: Path | None,
    race_delay_steps: int,
    apply_a_side_mutations: bool,
) -> dict:
    started = time.time()
    bundle = load_pioneer_instance(
        pioneer_id,
        bench_root=root,
        pioneer_path=pioneer_file,
        cache_dir=cache_dir,
        opaque_doc_ids=opaque_doc_ids,
        max_grep_per_event=max_grep_per_event,
        max_tool_calls_per_event=max_tool_calls_per_event,
    )
    race_controller = None
    if race_candidate_path is not None:
        race_patches = load_race_patches(race_candidate_path, pioneer_id)
        race_controller = RaceController(race_patches, delay_steps=race_delay_steps)
        if apply_a_side_mutations:
            race_controller.apply_a_side_mutations(bundle.runtime)
    run_result = run_instance(
        bundle,
        provider,
        policy=policy,  # type: ignore[arg-type]
        max_events=max_events,
        race_controller=race_controller,
    )
    elapsed = time.time() - started
    final_answer = run_result.final_answer or ""
    trace_payload = result_to_dict(run_result, bundle) if save_traces else None
    events_payload = [
        {
            "event_id": event.event_id,
            "tool_calls": [{"tool_name": tc.tool_name} for tc in event.tool_calls],
        }
        for event in run_result.events
    ]
    search_stats = _search_stats(events_payload)
    metrics = TaskMetrics(
        id=pioneer_id,
        benchmark=bundle.benchmark,
        gold_answer=bundle.gold_answer,
        final_answer=final_answer,
        stop_reason=run_result.stop_reason,
        event_count=run_result.event_count,
        resend_answer_count=run_result.resend_answer_count,
        exact_match=exact_match(final_answer, bundle.gold_answer),
        token_f1=token_f1(final_answer, bundle.gold_answer),
        elapsed_s=round(elapsed, 2),
        prompt_tokens=run_result.token_usage.prompt_tokens,
        completion_tokens=run_result.token_usage.completion_tokens,
        total_tokens=run_result.token_usage.total_tokens,
        llm_call_count=run_result.llm_call_count,
    )
    row = asdict(metrics)
    row.update(search_stats)
    if save_traces and trace_payload is not None:
        row["trace"] = trace_payload
    return row


def run_pioneer_batch(
    *,
    policy: str = "raw",
    max_events: int = 30,
    pioneer_ids: list[str] | None = None,
    pioneer_path: Path | None = None,
    output_path: Path | None = None,
    cache_dir: Path | None = None,
    opaque_doc_ids: bool = False,
    max_grep_per_event: int | None = None,
    max_tool_calls_per_event: int | None = None,
    save_traces: bool = False,
    race_candidate_path: Path | None = None,
    race_delay_steps: int = 0,
    apply_a_side_mutations: bool = False,
    max_workers: int = 8,
) -> dict:
    root = bench_root()
    load_dotenv(root.parent / ".env")
    provider = LLMProvider.from_env()
    pioneer_file = pioneer_path or (root / "pioneer_augmented.json")
    pioneer = json.loads(pioneer_file.read_text(encoding="utf-8"))
    all_ids = [item["id"] for item in pioneer.get("hotpotqa", [])]
    ids = pioneer_ids or all_ids

    def worker(pioneer_id: str) -> dict:
        return _run_single_pioneer_task(
            pioneer_id,
            root=root,
            pioneer_file=pioneer_file,
            provider=provider,
            policy=policy,
            max_events=max_events,
            cache_dir=cache_dir,
            opaque_doc_ids=opaque_doc_ids,
            max_grep_per_event=max_grep_per_event,
            max_tool_calls_per_event=max_tool_calls_per_event,
            save_traces=save_traces,
            race_candidate_path=race_candidate_path,
            race_delay_steps=race_delay_steps,
            apply_a_side_mutations=apply_a_side_mutations,
        )

    def on_complete(completed: int, total: int, pioneer_id: str, row: dict) -> None:
        print(f"[{completed}/{total}] finished {pioneer_id}", flush=True)
        print(
            f"  events={row['event_count']} grep={row.get('grep_call_count', '?')} "
            f"search_events={row.get('search_event_count', '?')} "
            f"resend_answer={row.get('resend_answer_count', 0)} "
            f"em={row['exact_match']} f1={row['token_f1']:.3f} "
            f"tokens={row.get('total_tokens', 0)} "
            f"stop={row['stop_reason']} elapsed={row['elapsed_s']}s",
            flush=True,
        )

    if max_workers > 1 and len(ids) > 1:
        print(f"Running {len(ids)} tasks with max_workers={max_workers}", flush=True)
    results = run_parallel(ids, worker, max_workers=max_workers, on_complete=on_complete)

    def summarize(items: list[TaskMetrics]) -> dict:
        if not items:
            return {"count": 0}
        return {
            "count": len(items),
            "exact_match_acc": sum(item.exact_match for item in items) / len(items),
            "avg_token_f1": sum(item.token_f1 for item in items) / len(items),
            "avg_events": sum(item.event_count for item in items) / len(items),
            "total_resend_answer_count": sum(item.resend_answer_count for item in items),
            "avg_resend_answer_count": sum(item.resend_answer_count for item in items) / len(items),
            "avg_elapsed_s": sum(item.elapsed_s for item in items) / len(items),
            "total_prompt_tokens": sum(item.prompt_tokens for item in items),
            "total_completion_tokens": sum(item.completion_tokens for item in items),
            "total_tokens": sum(item.total_tokens for item in items),
            "avg_tokens_per_task": sum(item.total_tokens for item in items) / len(items),
            "total_llm_calls": sum(item.llm_call_count for item in items),
            "avg_llm_calls_per_task": sum(item.llm_call_count for item in items) / len(items),
        }

    metric_rows = [
        TaskMetrics(
            id=row["id"],
            benchmark=row["benchmark"],
            gold_answer=row["gold_answer"],
            final_answer=row["final_answer"],
            stop_reason=row["stop_reason"],
            event_count=row["event_count"],
            resend_answer_count=row["resend_answer_count"],
            exact_match=row["exact_match"],
            token_f1=row["token_f1"],
            elapsed_s=row["elapsed_s"],
            prompt_tokens=row.get("prompt_tokens", 0),
            completion_tokens=row.get("completion_tokens", 0),
            total_tokens=row.get("total_tokens", 0),
            llm_call_count=row.get("llm_call_count", 0),
        )
        for row in results
    ]
    hotpot = [item for item in metric_rows if item.benchmark == "hotpotqa"]
    payload = {
        "policy": policy,
        "max_events": max_events,
        "model": provider.model,
        "opaque_doc_ids": opaque_doc_ids,
        "max_grep_per_event": max_grep_per_event,
        "max_tool_calls_per_event": max_tool_calls_per_event,
        "race_candidate_path": str(race_candidate_path) if race_candidate_path else None,
        "race_delay_steps": race_delay_steps,
        "apply_a_side_mutations": apply_a_side_mutations,
        "max_workers": max_workers,
        "summary": {
            "all": summarize(metric_rows),
            "hotpotqa": summarize(hotpot),
        },
        "tasks": results,
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run all pioneer tasks and report accuracy/events")
    parser.add_argument("--policy", choices=["raw", "block_context", "git", "system_alert"], default="raw")
    parser.add_argument("--max-events", type=int, default=30)
    parser.add_argument("--output", default="bench/runs/pioneer_eval.json")
    parser.add_argument("--pioneer", help="Path to pioneer_augmented.json")
    parser.add_argument("--ids", nargs="*", help="Optional subset of pioneer ids")
    parser.add_argument("--cache-dir", help="Override pioneer materialization cache directory")
    parser.add_argument("--opaque-doc-ids", action="store_true", help="Materialize Hotpot docs as doc_01.json, doc_02.json, ...")
    parser.add_argument("--max-grep-per-event", type=int, help="Limit grep calls per agent event (e.g. 1)")
    parser.add_argument("--max-tool-calls-per-event", type=int, help="Limit total tool calls per agent event (e.g. 1)")
    parser.add_argument("--save-traces", action="store_true", help="Include full event traces in output JSON")
    parser.add_argument("--race-candidates", help="Path to patch_candidate_augmented.json for B-side restore")
    parser.add_argument("--race-delay-steps", type=int, default=0, help="Interruptible steps to wait after read before B patch")
    parser.add_argument("--apply-a-side-mutations", action="store_true", help="Apply original->mutated before each run")
    parser.add_argument(
        "--max-workers",
        type=int,
        default=8,
        help="Parallel task workers (default: 8; use 1 for sequential)",
    )
    args = parser.parse_args(argv)

    pioneer_path = Path(args.pioneer).resolve() if args.pioneer else None
    output = Path(args.output)
    if not output.is_absolute():
        output = bench_root().parent / output if str(args.output).startswith("bench/") else bench_root() / output
    cache_dir = Path(args.cache_dir).resolve() if args.cache_dir else None

    payload = run_pioneer_batch(
        policy=args.policy,
        max_events=args.max_events,
        pioneer_ids=args.ids,
        pioneer_path=pioneer_path,
        output_path=output,
        cache_dir=cache_dir,
        opaque_doc_ids=args.opaque_doc_ids,
        max_grep_per_event=args.max_grep_per_event,
        max_tool_calls_per_event=args.max_tool_calls_per_event,
        save_traces=args.save_traces,
        race_candidate_path=Path(args.race_candidates).resolve() if args.race_candidates else None,
        race_delay_steps=args.race_delay_steps,
        apply_a_side_mutations=args.apply_a_side_mutations,
        max_workers=args.max_workers,
    )
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
