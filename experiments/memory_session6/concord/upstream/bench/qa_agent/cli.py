from __future__ import annotations

import argparse
import json
from pathlib import Path

from qa_agent.driver import load_hotpot_instance, load_pioneer_instance, result_to_dict, run_instance
from qa_agent.llm import LLMProvider
from qa_agent.loop import Policy
from qa_agent.race import RaceController, load_race_patches


def _bench_root() -> Path:
    return Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Block Context QA agent harness")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Run agent on a materialized HotpotQA instance")
    run_parser.add_argument("--instance", required=True, help="Instance directory")
    run_parser.add_argument("--benchmark", choices=["hotpotqa"], default="hotpotqa")
    run_parser.add_argument("--policy", choices=["raw", "block_context", "git", "system_alert", "reread"], default="raw")
    run_parser.add_argument("--max-events", type=int, default=30)
    run_parser.add_argument("--output", help="Optional JSON output path")
    run_parser.add_argument("--race-candidates", help="Path to patch_candidate_augmented.json for B-side restore")
    run_parser.add_argument("--race-id", help="Task id in patch candidates; defaults to task.json id")
    run_parser.add_argument("--race-delay-steps", type=int, default=0)
    run_parser.add_argument("--apply-a-side-mutations", action="store_true")

    pioneer_parser = sub.add_parser("run-pioneer", help="Run agent on a pioneer_augmented.json entry")
    pioneer_parser.add_argument("--id", required=True, help="Pioneer id, e.g. hotpotqa-01")
    pioneer_parser.add_argument("--policy", choices=["raw", "block_context", "git", "system_alert", "reread"], default="raw")
    pioneer_parser.add_argument("--max-events", type=int, default=30)
    pioneer_parser.add_argument("--output", help="Optional JSON output path")
    pioneer_parser.add_argument("--pioneer", help="Path to pioneer_augmented.json")
    pioneer_parser.add_argument("--race-candidates", help="Path to patch_candidate_augmented.json for B-side restore")
    pioneer_parser.add_argument("--race-delay-steps", type=int, default=0)
    pioneer_parser.add_argument("--apply-a-side-mutations", action="store_true")

    args = parser.parse_args(argv)
    bench_root = _bench_root()
    provider = LLMProvider.from_env()
    policy: Policy = args.policy

    if args.command == "run":
        instance_path = Path(args.instance).resolve()
        bundle = load_hotpot_instance(instance_path)
    else:
        bundle = load_pioneer_instance(
            args.id,
            bench_root=bench_root,
            pioneer_path=Path(args.pioneer).resolve() if args.pioneer else None,
        )

    race_controller = None
    if args.race_candidates:
        if args.command == "run-pioneer":
            race_id = args.id
        else:
            race_id = args.race_id or str((bundle.metadata or {}).get("id", ""))
            if not race_id:
                raise SystemExit("--race-id is required when task.json has no id")
        race_patches = load_race_patches(Path(args.race_candidates).resolve(), race_id)
        race_controller = RaceController(race_patches, delay_steps=args.race_delay_steps)
        if args.apply_a_side_mutations:
            race_controller.apply_a_side_mutations(bundle.runtime)

    result = run_instance(
        bundle,
        provider,
        policy=policy,
        max_events=args.max_events,
        race_controller=race_controller,
    )
    payload = result_to_dict(result, bundle)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
