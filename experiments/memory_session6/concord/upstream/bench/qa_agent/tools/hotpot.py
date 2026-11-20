from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from block_context import BlockContextRuntime

from qa_agent.adapters.hotpot import HotpotAdapter
from qa_agent.tools.base import ToolRegistry, ToolResult
from qa_agent.tools.blocks import glob_listing_block


@dataclass(slots=True)
class GrepTool:
    adapter: HotpotAdapter
    runtime: BlockContextRuntime
    agent_id: str = "qa-agent"

    name: ClassVar[str] = "grep"
    description: ClassVar[str] = (
        "Search localized document contents by regex. Returns up to 100 matches. "
        "Each match includes source_path, line number, and a small context window."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": (
                    "Regex pattern to search for in document text (Python re syntax). "
                    "When fixed_strings is true, this is treated as plain text."
                ),
            },
            "path": {
                "type": "string",
                "description": (
                    "Optional workspace-relative source_path to search within, "
                    "for example corpus/original/larry_drake.json. Omit to search all documents."
                ),
            },
            "glob": {
                "type": "string",
                "description": (
                    "Optional filename/path filter applied before content search, "
                    "for example '*.json' or 'corpus/original/*.json'."
                ),
            },
            "case_insensitive": {
                "type": "boolean",
                "description": "If true, match letters regardless of case. Default false.",
            },
            "fixed_strings": {
                "type": "boolean",
                "description": "If true, treat pattern as literal text instead of regex. Default false.",
            },
        },
        "required": ["pattern"],
    }

    def execute(self, **kwargs: Any) -> ToolResult:
        if not self.adapter.consume_grep_slot():
            limit = self.adapter.max_grep_per_event
            return ToolResult(
                text=(
                    f"Error: grep limit reached for this event (max {limit}). "
                    "Use read_file on paths from earlier results, or continue in the next turn."
                )
            )
        hits = self.adapter.grep(
            str(kwargs["pattern"]),
            path=str(kwargs["path"]) if kwargs.get("path") else None,
            glob=str(kwargs["glob"]) if kwargs.get("glob") else None,
            case_insensitive=bool(kwargs.get("case_insensitive", False)),
            fixed_strings=bool(kwargs.get("fixed_strings", False)),
        )
        if not hits:
            return ToolResult(text="No matches.")
        lines = []
        blocks = []
        for hit in hits:
            content = f"path: {hit.path}\nline: {hit.line}\n{hit.context}"
            lines.append(content)
            blocks.append(
                self.runtime.create_verbatim_observation_block(
                    hit.path,
                    content,
                    title=f"grep: {hit.path}:{hit.line}",
                    agent_id=self.agent_id,
                )
            )
        return ToolResult(text="\n\n".join(lines), blocks=tuple(blocks))


@dataclass(slots=True)
class GlobTool:
    adapter: HotpotAdapter
    runtime: BlockContextRuntime
    agent_id: str = "qa-agent"

    name: ClassVar[str] = "glob"
    description: ClassVar[str] = (
        "Find workspace-relative document paths by glob pattern. "
        "Returns up to 100 matching source_path values."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": (
                    "Glob pattern matched against source_path. "
                    "Examples: '*.json', 'corpus/original/*.json', '*drake*'."
                ),
            },
        },
        "required": ["pattern"],
    }

    def execute(self, **kwargs: Any) -> ToolResult:
        matches = self.adapter.glob(str(kwargs["pattern"]))
        if not matches:
            return ToolResult(text="No matches.")
        block = glob_listing_block(self.runtime, str(kwargs["pattern"]), matches, agent_id=self.agent_id)
        return ToolResult(text="\n".join(matches), block=block)


@dataclass(slots=True)
class ReadFileTool:
    adapter: HotpotAdapter
    runtime: BlockContextRuntime
    agent_id: str = "qa-agent"

    name: ClassVar[str] = "read_file"
    description: ClassVar[str] = (
        "Read one localized document by workspace-relative source_path. "
        "Returns numbered lines. Optionally restrict to a line range."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Workspace-relative source_path from the workspace listing, "
                    "for example corpus/original/larry_drake.json."
                ),
            },
            "start_line": {
                "type": "integer",
                "description": "1-indexed first line to read, inclusive. Must be used together with end_line.",
            },
            "end_line": {
                "type": "integer",
                "description": "1-indexed last line to read, inclusive. Must be used together with start_line.",
            },
        },
        "required": ["path"],
    }

    def execute(self, **kwargs: Any) -> ToolResult:
        source_id = str(kwargs["path"])
        span = None
        start_line = kwargs.get("start_line")
        end_line = kwargs.get("end_line")
        if start_line is not None or end_line is not None:
            if start_line is None or end_line is None:
                raise ValueError("start_line and end_line must both be provided together")
            span = (int(start_line), int(end_line))
        rel_path = self.adapter.resolve_source_path(source_id)
        text = self.adapter.read_text(source_id, span=span)
        block = self.runtime.create_verbatim_observation_block(
            rel_path,
            text,
            title=f"read_file: {rel_path}",
            agent_id=self.agent_id,
        )
        return ToolResult(text=text, block=block)


@dataclass(slots=True)
class AnswerTool:
    name: ClassVar[str] = "answer"
    description: ClassVar[str] = (
        "Submit the final answer. Call exactly once after you have read supporting evidence."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Final answer text supported by tool results. Prefer a short span when possible.",
            },
        },
        "required": ["text"],
    }

    def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult(text=str(kwargs["text"]), terminal=True)


def build_hotpot_registry(adapter: HotpotAdapter, runtime: BlockContextRuntime) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(GrepTool(adapter, runtime))
    registry.register(GlobTool(adapter, runtime))
    registry.register(ReadFileTool(adapter, runtime))
    registry.register(AnswerTool())
    return registry
