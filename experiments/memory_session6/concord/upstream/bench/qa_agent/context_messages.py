from __future__ import annotations

from typing import Any

from block_context import BlockContextRuntime, ContextDocument
from block_context.types import BlockState, ContextBlock


def render_safe_evidence(runtime: BlockContextRuntime, block_ids: tuple[str, ...]) -> str:
    """Render agent-visible text for one tool return from its backing mutable blocks."""
    parts: list[str] = []
    for block_id in block_ids:
        block = runtime.get_block(block_id)
        if block.is_mutable_block() and block.state != BlockState.VALID:
            continue
        parts.append(block.content)
    return "".join(parts)


def block_context_messages(
    messages: list[dict[str, Any]],
    *,
    runtime: BlockContextRuntime,
    document: ContextDocument,
    tool_evidence: dict[str, tuple[str, ...]],
    include_refresh_notice: bool = True,
) -> list[dict[str, Any]]:
    """Build incremental chat messages with block-backed, freshness-safe tool returns.

    Trajectory layout matches Block Context v0: system prompt, question, then per event
    reasoning (assistant) + tool call (assistant tool_calls) + observation (tool message).
    Mutable observations are resolved from the block registry at send time so in-place
    coherence updates and omissions are visible without flattening the full document.
    """
    refreshed: list[dict[str, Any]] = []
    for message in messages:
        if message.get("role") != "tool":
            refreshed.append(dict(message))
            continue
        tool_call_id = message.get("tool_call_id")
        block_ids = tool_evidence.get(str(tool_call_id), ())
        if block_ids:
            content = render_safe_evidence(runtime, block_ids)
        else:
            content = str(message.get("content", ""))
        refreshed.append({**message, "content": content})

    if include_refresh_notice:
        notice = document.refresh_notice_block()
        if notice is not None:
            refreshed.append({"role": "system", "content": notice.content})
    return refreshed
