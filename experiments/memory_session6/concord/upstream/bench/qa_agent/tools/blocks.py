from __future__ import annotations

from collections.abc import Callable
from typing import Literal, Protocol

from block_context import BlockContextRuntime
from block_context.types import ContextBlock, Span

from qa_agent.adapters.base import GrepHit


class SpanTextReader(Protocol):
    def __call__(self, path: str, start_line: int, end_line: int) -> str: ...


def _first_non_empty_line(content: str) -> str:
    for line in content.splitlines():
        if line.strip():
            return line
    raise ValueError("grep hit content cannot be empty")


def _locate_rendered_content_span(source_content: str, content: str) -> Span:
    if content in source_content:
        start_char = source_content.index(content)
        end_char = start_char + len(content)
        start_line = source_content.count("\n", 0, start_char) + 1
        end_line = source_content.count("\n", 0, max(start_char, end_char - 1)) + 1
        return Span(start_line, end_line)

    needle = _first_non_empty_line(content)
    file_lines = source_content.splitlines(keepends=True)
    matches = [idx for idx, line in enumerate(file_lines, start=1) if needle in line]
    if not matches:
        stripped = needle.split(". ", 1)[-1] if ". " in needle else needle
        matches = [idx for idx, line in enumerate(file_lines, start=1) if stripped in line]
    if not matches:
        raise ValueError("grep hit content not found in source file")
    if len(matches) > 1:
        raise ValueError("grep hit content matched multiple source lines")
    return Span(matches[0], matches[0])


def grep_hit_blocks(
    runtime: BlockContextRuntime,
    hits: list[GrepHit],
    *,
    agent_id: str = "qa-agent",
    line_basis: Literal["file", "rendered"] = "file",
    text_reader: SpanTextReader | None = None,
) -> tuple[ContextBlock, ...]:
    blocks: list[ContextBlock] = []
    seen: set[tuple[str, int, int]] = set()
    for hit in hits:
        key = (hit.path, hit.context_start, hit.context_end)
        if key in seen:
            continue
        seen.add(key)

        if line_basis == "file":
            if text_reader is None:
                def _read(path: str, start_line: int, end_line: int) -> str:
                    source = (runtime.workspace_root / path).read_text(encoding="utf-8")
                    lines = source.splitlines()
                    return "\n".join(lines[start_line - 1 : end_line])

                reader = _read
            else:
                reader = text_reader
            content = reader(hit.path, hit.context_start, hit.context_end)
            span = Span(hit.context_start, hit.context_end)
        else:
            if text_reader is None:
                raise ValueError("rendered grep blocks require text_reader")
            content = text_reader(hit.path, hit.context_start, hit.context_end)
            source_content = (runtime.workspace_root / hit.path).read_text(encoding="utf-8")
            span = _locate_rendered_content_span(source_content, content)

        blocks.append(
            runtime.create_verbatim_from_content(
                hit.path,
                content,
                span,
                title=f"grep: {hit.path}:{hit.line}",
                agent_id=agent_id,
            )
        )
    return tuple(blocks)


def glob_listing_block(
    runtime: BlockContextRuntime,
    pattern: str,
    matches: list[str],
    *,
    agent_id: str = "qa-agent",
) -> ContextBlock | None:
    if not matches:
        return None
    return runtime.create_glob_listing_block(
        pattern,
        matches,
        title=f"glob: {pattern}",
        agent_id=agent_id,
    )
