from __future__ import annotations

import json
from typing import Any

from block_context import BlockContextRuntime, ContextDocument
from block_context.types import ContextBlock


def initialize_trajectory_document(
    runtime: BlockContextRuntime,
    document: ContextDocument,
    *,
    system_prompt: str,
    question: str,
    agent_id: str,
) -> None:
    document.add_block(
        runtime.create_immutable_block(
            _ensure_trailing_newline(system_prompt),
            title="system prompt",
            owner_agent_id=agent_id,
        )
    )
    document.add_block(
        runtime.create_immutable_block(
            f"Question:\n{question.strip()}\n",
            title="user question",
            owner_agent_id=agent_id,
        )
    )


def append_reasoning(
    runtime: BlockContextRuntime,
    document: ContextDocument,
    reasoning: str,
    *,
    event_id: str,
    agent_id: str,
) -> ContextBlock | None:
    if not reasoning.strip():
        return None
    block = runtime.create_immutable_block(
        _ensure_trailing_newline(reasoning),
        title="agent reasoning",
        owner_agent_id=agent_id,
        event_id=event_id,
    )
    document.add_block(block)
    return block


def append_tool_call(
    runtime: BlockContextRuntime,
    document: ContextDocument,
    tool_name: str,
    tool_args: dict[str, Any],
    *,
    event_id: str,
    agent_id: str,
) -> ContextBlock:
    block = runtime.create_immutable_block(
        f"Tool call: {tool_name}({json.dumps(tool_args, ensure_ascii=False, sort_keys=True)})\n",
        title=f"tool call: {tool_name}",
        owner_agent_id=agent_id,
        event_id=event_id,
    )
    document.add_block(block)
    return block


def append_mutable_blocks(
    document: ContextDocument,
    blocks: tuple[ContextBlock, ...],
) -> None:
    for block in blocks:
        document.add_block(block)


def append_tool_result_record(
    runtime: BlockContextRuntime,
    document: ContextDocument,
    tool_name: str,
    text: str,
    *,
    event_id: str,
    agent_id: str,
) -> ContextBlock:
    block = runtime.create_immutable_block(
        f"Tool result: {tool_name}\n{text.rstrip()}\n",
        title=f"tool result: {tool_name}",
        owner_agent_id=agent_id,
        event_id=event_id,
    )
    document.add_block(block)
    return block


def append_answer(
    runtime: BlockContextRuntime,
    document: ContextDocument,
    text: str,
    *,
    event_id: str,
    agent_id: str,
) -> ContextBlock:
    block = runtime.create_immutable_block(
        f"Answer:\n{text.strip()}\n",
        title="answer",
        owner_agent_id=agent_id,
        event_id=event_id,
    )
    document.add_block(block)
    return block


def record_tool_execution_in_document(
    runtime: BlockContextRuntime,
    document: ContextDocument,
    *,
    tool_name: str,
    tool_args: dict[str, Any],
    result_text: str,
    mutable_blocks: tuple[ContextBlock, ...],
    terminal: bool,
    event_id: str,
    agent_id: str,
) -> None:
    append_tool_call(runtime, document, tool_name, tool_args, event_id=event_id, agent_id=agent_id)
    if mutable_blocks:
        append_mutable_blocks(document, mutable_blocks)
    elif terminal and tool_name == "answer":
        append_answer(runtime, document, result_text, event_id=event_id, agent_id=agent_id)
    else:
        append_tool_result_record(
            runtime,
            document,
            tool_name,
            result_text,
            event_id=event_id,
            agent_id=agent_id,
        )


def _ensure_trailing_newline(text: str) -> str:
    return text if text.endswith("\n") else f"{text}\n"
