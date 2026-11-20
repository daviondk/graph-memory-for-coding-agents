from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from block_context.runtime import BlockContextRuntime
from block_context.types import ContextBlock, SourceLocator, SourceRef


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="block-context")
    subparsers = parser.add_subparsers(dest="command", required=True)

    read_parser = subparsers.add_parser("read-file")
    read_parser.add_argument("workspace")
    read_parser.add_argument("path")
    read_parser.add_argument("--start-line", type=int)
    read_parser.add_argument("--end-line", type=int)

    observe_parser = subparsers.add_parser("observe")
    observe_parser.add_argument("workspace")
    observe_parser.add_argument("path")
    observe_parser.add_argument("kind", choices=["file-stats", "python-symbols"])

    write_parser = subparsers.add_parser("write-file")
    write_parser.add_argument("workspace")
    write_parser.add_argument("path")
    write_parser.add_argument("--content", required=True)
    write_parser.add_argument("--create", action="store_true")

    demo_parser = subparsers.add_parser("render-demo")
    demo_parser.add_argument("workspace")

    args = parser.parse_args(argv)
    runtime = BlockContextRuntime(args.workspace)

    if args.command == "read-file":
        span = None
        if args.start_line is not None or args.end_line is not None:
            if args.start_line is None or args.end_line is None:
                parser.error("--start-line and --end-line must be used together")
            span = (args.start_line, args.end_line)
        print(json.dumps(_block_payload(runtime.read_file(args.path, span=span)), indent=2, sort_keys=True))
        return 0

    if args.command == "observe":
        print(json.dumps(_block_payload(runtime.observe_file(args.path, args.kind)), indent=2, sort_keys=True))
        return 0

    if args.command == "write-file":
        affected = runtime.write_file(args.path, args.content, create=args.create)
        print(json.dumps({"affected_blocks": [_block_payload(block) for block in affected]}, indent=2, sort_keys=True))
        return 0

    if args.command == "render-demo":
        print(_render_demo(runtime, Path(args.workspace)))
        return 0

    parser.error(f"unsupported command: {args.command}")
    return 2


def _render_demo(runtime: BlockContextRuntime, workspace: Path) -> str:
    source = workspace / "demo.py"
    if not source.exists():
        runtime.write_file("demo.py", "def answer():\n    return 41\n", create=True)

    doc = runtime.new_document()
    doc.add_text("Relevant context:\n")
    block = runtime.read_file("demo.py", span=(2, 2), title="demo return line")
    doc.add_block(block)
    doc.add_text("\nNotes:\n")
    doc.add_text("The previous source read may guide the next step.\n")
    doc.add_text("\nCurrent request:\nExplain the current answer.\n")

    runtime.write_file("demo.py", "def answer():\n")
    rendered = doc.render_safe()
    return rendered.text


def _block_payload(block: ContextBlock) -> dict[str, object]:
    return {
        "id": block.id,
        "content": block.content,
        "transform_type": block.transform_type.value,
        "owner_agent_id": block.owner_agent_id,
        "event_id": block.event_id,
        "state": block.state.value,
        "stale_reason": block.stale_reason,
        "metadata": block.metadata,
        "source_set": [_source_payload(source) for source in block.source_set],
    }


def _source_payload(source: SourceRef) -> dict[str, object]:
    return {
        "object_id": source.object_id,
        "version": source.version,
        "span": None
        if source.span is None
        else {"start_line": source.span.start_line, "end_line": source.span.end_line},
        "transform_type": source.transform_type.value,
        "locator": None if source.locator is None else _locator_payload(source.locator),
    }


def _locator_payload(locator: SourceLocator) -> dict[str, object]:
    return {
        "content_hash": locator.content_hash,
        "context_hash": locator.context_hash,
        "context_window": locator.context_window,
        "pre_context": list(locator.pre_context),
        "post_context": list(locator.post_context),
        "unique_anchor_lines": list(locator.unique_anchor_lines),
    }


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
