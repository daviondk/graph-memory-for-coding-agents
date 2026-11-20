from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from qa_agent.llm import LLMProvider
from qa_agent.parallel import run_parallel

JUDGE_SYSTEM_PROMPT = """You are an impartial answer grader for QA benchmark evaluation.

Your job is to decide whether a model prediction correctly answers the question, using the gold answer as the reference standard.

Grading rules:
- Judge semantic correctness, not exact string match.
- The prediction may be longer or phrased differently than the gold answer.
- Mark correct when the prediction contains the same core answer as the gold answer and does not contradict it.
- For short gold answers (names, places, dates, short phrases), the gold span must appear in the prediction in an equivalent form.
- For long gold answers (explanations, code references, multi-part technical answers), the prediction must preserve the key factual claims in the gold answer. Minor wording or formatting differences are fine.
- Mark incorrect if the prediction is empty, refuses to answer, contradicts the gold answer, answers a different question, or misses a required key fact.
- Do not use outside knowledge beyond what is needed to compare the prediction against the gold answer.
- When uncertain, mark incorrect.

Respond with JSON only, no markdown fences:
{"correct": true or false, "reason": "one or two sentences"}
"""


def build_judge_user_prompt(
    *,
    question: str,
    gold_answer: str,
    prediction: str,
    benchmark: str | None = None,
) -> str:
    benchmark_line = f"Benchmark: {benchmark}\n" if benchmark else ""
    return (
        f"{benchmark_line}"
        f"Question:\n{question.strip()}\n\n"
        f"Gold answer:\n{gold_answer.strip()}\n\n"
        f"Model prediction:\n{prediction.strip() or '(empty)'}\n"
    )


@dataclass(slots=True)
class JudgeVerdict:
    correct: bool
    reason: str
    raw_response: str = ""


@dataclass(slots=True)
class JudgeTaskResult:
    id: str
    benchmark: str
    question: str
    gold_answer: str
    final_answer: str
    llm_judge_correct: bool
    llm_judge_reason: str
    exact_match: bool | None = None
    token_f1: float | None = None


def parse_judge_response(text: str) -> JudgeVerdict:
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("empty judge response")

    candidates = [cleaned]
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        candidates.insert(0, fence.group(1).strip())

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if not isinstance(payload, dict):
            continue
        if "correct" not in payload:
            continue
        reason = str(payload.get("reason", "")).strip()
        return JudgeVerdict(correct=bool(payload["correct"]), reason=reason, raw_response=text)
    raise ValueError(f"could not parse judge JSON: {last_error}")


def judge_answer(
    provider: LLMProvider,
    *,
    question: str,
    gold_answer: str,
    prediction: str,
    benchmark: str | None = None,
) -> JudgeVerdict:
    response = provider.chat(
        [
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_judge_user_prompt(
                    question=question,
                    gold_answer=gold_answer,
                    prediction=prediction,
                    benchmark=benchmark,
                ),
            },
        ]
    )
    return parse_judge_response(response.content or "")


def _judge_single_task(
    task: dict[str, Any],
    *,
    provider: LLMProvider,
    question_by_id: dict[str, str] | None,
) -> JudgeTaskResult:
    task_id = str(task["id"])
    question = (question_by_id or {}).get(task_id, task.get("question", ""))
    verdict = judge_answer(
        provider,
        question=question,
        gold_answer=str(task.get("gold_answer", "")),
        prediction=str(task.get("final_answer", "")),
        benchmark=str(task.get("benchmark", "")) or None,
    )
    return JudgeTaskResult(
        id=task_id,
        benchmark=str(task.get("benchmark", "")),
        question=question,
        gold_answer=str(task.get("gold_answer", "")),
        final_answer=str(task.get("final_answer", "")),
        llm_judge_correct=verdict.correct,
        llm_judge_reason=verdict.reason,
        exact_match=task.get("exact_match"),
        token_f1=task.get("token_f1"),
    )


def judge_eval_payload(
    provider: LLMProvider,
    payload: dict[str, Any],
    *,
    question_by_id: dict[str, str] | None = None,
    max_workers: int = 8,
) -> dict[str, Any]:
    tasks = payload.get("tasks", [])

    def worker(task: dict[str, Any]) -> JudgeTaskResult:
        return _judge_single_task(task, provider=provider, question_by_id=question_by_id)

    def on_complete(completed: int, total: int, task: dict[str, Any], result: JudgeTaskResult) -> None:
        print(f"[{completed}/{total}] judged {result.id}...", flush=True)
        print(f"  judge={result.llm_judge_correct} reason={result.llm_judge_reason}", flush=True)

    if max_workers > 1 and len(tasks) > 1:
        print(f"Judging {len(tasks)} tasks with max_workers={max_workers}", flush=True)
    judged = run_parallel(tasks, worker, max_workers=max_workers, on_complete=on_complete)

    def summarize(items: list[JudgeTaskResult]) -> dict[str, Any]:
        if not items:
            return {"count": 0}
        return {
            "count": len(items),
            "llm_judge_acc": sum(item.llm_judge_correct for item in items) / len(items),
            "exact_match_acc": sum(bool(item.exact_match) for item in items) / len(items)
            if any(item.exact_match is not None for item in items)
            else None,
            "avg_token_f1": sum(item.token_f1 or 0.0 for item in items) / len(items)
            if any(item.token_f1 is not None for item in items)
            else None,
        }

    hotpot = [item for item in judged if item.benchmark == "hotpotqa"]
    return {
        "judge_model": provider.model,
        "max_workers": max_workers,
        "summary": {
            "all": summarize(judged),
            "hotpotqa": summarize(hotpot),
        },
        "tasks": [asdict(item) for item in judged],
    }


def load_questions_from_pioneer(pioneer_path: Path) -> dict[str, str]:
    payload = json.loads(pioneer_path.read_text(encoding="utf-8"))
    questions: dict[str, str] = {}
    for record in payload.get("hotpotqa", []):
        questions[str(record["id"])] = str(record["question"])
    return questions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LLM-judge correctness for eval result JSON")
    parser.add_argument("--input", required=True, help="Eval JSON from eval_pioneer.py")
    parser.add_argument("--output", help="Optional output JSON path")
    parser.add_argument("--pioneer", help="Optional pioneer/task JSON to recover question text")
    parser.add_argument("--judge-model", help="Override JUDGE_LLM / LLM_MODEL for judging")
    parser.add_argument(
        "--max-workers",
        type=int,
        default=8,
        help="Parallel judge workers (default: 8; use 1 for sequential)",
    )
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parent.parent
    load_dotenv(root.parent / ".env")

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = root / input_path if not str(args.input).startswith("bench/") else root.parent / args.input

    provider = LLMProvider.from_judge_env()
    if args.judge_model:
        provider = LLMProvider(
            api_key=provider.api_key,
            base_url=provider.base_url,
            model=args.judge_model,
            temperature=0.0,
            http_proxy=os.environ.get("JUDGE_HTTP_PROXY"),
        )

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    question_by_id = None
    if args.pioneer:
        pioneer_path = Path(args.pioneer)
        if not pioneer_path.is_absolute():
            pioneer_path = root / pioneer_path
        question_by_id = load_questions_from_pioneer(pioneer_path)

    judged = judge_eval_payload(
        provider,
        payload,
        question_by_id=question_by_id,
        max_workers=args.max_workers,
    )
    print(json.dumps(judged["summary"], ensure_ascii=False, indent=2))

    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = root / output_path if not str(args.output).startswith("bench/") else root.parent / args.output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(judged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
