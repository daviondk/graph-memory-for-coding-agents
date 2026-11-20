from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from block_context import BlockContextRuntime, ContextDocument

from qa_agent.adapters.base import DatasetAdapter
from qa_agent.llm import LLMProvider, LLMResponse, TokenUsage
from qa_agent.prompts import build_system_prompt
from qa_agent.race import RaceController, RaceEventRecord
from qa_agent.tools.base import ToolRegistry, ToolResult
from qa_agent.context_messages import block_context_messages
from qa_agent.trajectory import (
    append_reasoning,
    initialize_trajectory_document,
    record_tool_execution_in_document,
)

Policy = Literal["raw", "block_context", "git", "system_alert", "reread"]


@dataclass(slots=True)
class DiffTool:
    race_controller: RaceController | None
    on_diff: Any

    name: ClassVar[str] = "diff"
    description: ClassVar[str] = (
        "Inspect differences between previously observed patched evidence and the current workspace. "
        "Call this once after gathering evidence and before answer."
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    def execute(self, **kwargs: Any) -> ToolResult:
        generation = self.race_controller.generation if self.race_controller is not None else 0
        self.on_diff(generation)
        if self.race_controller is None:
            return ToolResult(text="No workspace changes.")
        return ToolResult(text=self.race_controller.current_diff_text())


@dataclass(slots=True)
class ToolCallRecord:
    tool_name: str
    tool_args: dict[str, Any]
    tool_result: str
    block_id: str | None = None
    block_ids: tuple[str, ...] = ()
    terminal: bool = False


@dataclass(slots=True)
class AgentEventRecord:
    """One agent event = one reasoning + action loop (single LLM turn)."""

    event_id: str
    reasoning: str
    tool_calls: list[ToolCallRecord]


@dataclass(slots=True)
class AgentRunResult:
    final_answer: str
    messages: list[dict[str, Any]]
    events: list[AgentEventRecord]
    race_events: list[RaceEventRecord]
    stop_reason: str
    policy: Policy
    document: ContextDocument | None = None
    resend_answer_count: int = 0
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    llm_call_count: int = 0

    @property
    def event_count(self) -> int:
        return len(self.events)

    @property
    def tool_call_count(self) -> int:
        return sum(len(event.tool_calls) for event in self.events)


def _assistant_message(response: LLMResponse) -> dict[str, Any]:
    message: dict[str, Any] = {
        "role": "assistant",
        "content": response.content or "",
    }
    if response.tool_calls:
        message["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                },
            }
            for tc in response.tool_calls
        ]
    return message


def _tool_message(tool_call_id: str, name: str, content: str) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": name,
        "content": content,
    }


def _response_has_answer(response: LLMResponse) -> bool:
    return response.should_execute_tools and any(
        tc.name == "answer" for tc in response.tool_calls
    )


def _usage_from_response(response: LLMResponse) -> TokenUsage:
    return response.usage or TokenUsage()


def _append_to_last_tool_message(messages: list[dict[str, Any]], text: str) -> bool:
    if not text:
        return False
    for message in reversed(messages):
        if message.get("role") != "tool":
            continue
        existing = str(message.get("content", ""))
        separator = "\n\n" if existing else ""
        message["content"] = f"{existing}{separator}{text}"
        return True
    return False


def _messages_for_model(
    messages: list[dict[str, Any]],
    *,
    policy: Policy,
    document: ContextDocument | None,
    runtime: BlockContextRuntime | None = None,
    tool_evidence: dict[str, tuple[str, ...]] | None = None,
) -> list[dict[str, Any]]:
    if policy != "block_context" or document is None or runtime is None:
        return list(messages)
    return block_context_messages(
        messages,
        runtime=runtime,
        document=document,
        tool_evidence=tool_evidence or {},
    )


def run_agent(
    provider: LLMProvider,
    registry: ToolRegistry,
    adapter: DatasetAdapter,
    question: str,
    *,
    runtime: BlockContextRuntime,
    policy: Policy = "raw",
    max_events: int = 30,
    agent_id: str = "qa-agent",
    race_controller: RaceController | None = None,
) -> AgentRunResult:
    if policy == "reread":
        raise NotImplementedError("reread policy is not implemented yet")

    system_prompt = build_system_prompt(
        workspace_context=adapter.workspace_summary(),
        policy=policy,
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]
    document = runtime.new_document()
    initialize_trajectory_document(
        runtime,
        document,
        system_prompt=system_prompt,
        question=question,
        agent_id=agent_id,
    )
    events: list[AgentEventRecord] = []
    tool_evidence: dict[str, tuple[str, ...]] = {}
    diff_seen_generation: int | None = None
    final_answer = ""
    stop_reason = "max_events"
    token_usage = TokenUsage()
    llm_call_count = 0

    def _set_diff_seen_generation(generation: int) -> None:
        nonlocal diff_seen_generation
        diff_seen_generation = generation

    def _git_diff_is_fresh() -> bool:
        current_generation = race_controller.generation if race_controller is not None else 0
        return diff_seen_generation == current_generation

    def _append_system_alert_if_needed(text: str, *, terminal: bool) -> str:
        if policy != "system_alert" or race_controller is None or terminal:
            return text
        alert = race_controller.consume_alerts()
        if not alert:
            return text
        separator = "\n\n" if text else ""
        return f"{text}{separator}{alert}"

    if policy == "git":
        registry.register(DiffTool(race_controller, on_diff=_set_diff_seen_generation))

    for event_idx in range(1, max_events + 1):
        event_id = f"evt-{event_idx}"
        if hasattr(adapter, "reset_grep_event_budget"):
            adapter.reset_grep_event_budget()

        while True:
            model_messages = _messages_for_model(
                messages,
                policy=policy,
                document=document,
                runtime=runtime,
                tool_evidence=tool_evidence,
            )
            response = provider.chat(model_messages, tools=registry.definitions())
            llm_call_count += 1
            token_usage += _usage_from_response(response)
            if (
                policy == "system_alert"
                and race_controller is not None
                and _response_has_answer(response)
                and race_controller.has_pending_alerts
            ):
                _append_to_last_tool_message(messages, race_controller.consume_alerts())
                continue
            if race_controller is not None and race_controller.inspect_response_for_answer(response, runtime):
                if policy == "system_alert":
                    _append_to_last_tool_message(messages, race_controller.consume_alerts())
                continue
            break

        reasoning = response.content or ""
        if not response.should_execute_tools:
            append_reasoning(
                runtime,
                document,
                reasoning,
                event_id=event_id,
                agent_id=agent_id,
            )
            if reasoning.strip():
                messages.append({"role": "assistant", "content": reasoning})
            stop_reason = "no_tool_calls"
            break

        messages.append(_assistant_message(response))
        append_reasoning(
            runtime,
            document,
            reasoning,
            event_id=event_id,
            agent_id=agent_id,
        )
        loop_tool_calls: list[ToolCallRecord] = []
        tool_call_limit = getattr(adapter, "max_tool_calls_per_event", None)
        for tool_idx, tool_call in enumerate(response.tool_calls):
            if tool_call_limit is not None and tool_idx >= tool_call_limit:
                result = ToolResult(
                    text=(
                        f"Error: only {tool_call_limit} tool call(s) allowed per event. "
                        "Continue in the next turn."
                    )
                )
                result.text = _append_system_alert_if_needed(result.text, terminal=False)
                result_blocks = result.all_blocks()
                block_ids = tuple(
                    block.id for block in result_blocks if block.id is not None
                )
                if block_ids:
                    tool_evidence[tool_call.id] = block_ids
                loop_tool_calls.append(
                    ToolCallRecord(
                        tool_name=tool_call.name,
                        tool_args=dict(tool_call.arguments),
                        tool_result=result.text,
                        block_ids=block_ids,
                        terminal=False,
                    )
                )
                record_tool_execution_in_document(
                    runtime,
                    document,
                    tool_name=tool_call.name,
                    tool_args=dict(tool_call.arguments),
                    result_text=result.text,
                    mutable_blocks=result_blocks,
                    terminal=False,
                    event_id=event_id,
                    agent_id=agent_id,
                )
                messages.append(_tool_message(tool_call.id, tool_call.name, result.text))
                continue
            if race_controller is not None:
                race_controller.before_tool_call(
                    tool_call.name,
                    dict(tool_call.arguments),
                    adapter=adapter,
                    runtime=runtime,
                )
            if policy == "git" and tool_call.name == "answer" and not _git_diff_is_fresh():
                result = ToolResult(
                    text=(
                        "Error: call diff before answer to inspect current workspace changes."
                    )
                )
            else:
                try:
                    result = registry.execute(tool_call.name, tool_call.arguments)
                except Exception as exc:
                    result = ToolResult(text=f"Tool error: {exc}")
            result.text = _append_system_alert_if_needed(result.text, terminal=result.terminal)

            result_blocks = result.all_blocks()
            block_ids = tuple(block.id for block in result_blocks if block.id is not None)
            block_id = block_ids[0] if len(block_ids) == 1 else None
            if block_ids:
                tool_evidence[tool_call.id] = block_ids
            record_tool_execution_in_document(
                runtime,
                document,
                tool_name=tool_call.name,
                tool_args=dict(tool_call.arguments),
                result_text=result.text,
                mutable_blocks=result_blocks,
                terminal=result.terminal,
                event_id=event_id,
                agent_id=agent_id,
            )

            loop_tool_calls.append(
                ToolCallRecord(
                    tool_name=tool_call.name,
                    tool_args=dict(tool_call.arguments),
                    tool_result=result.text,
                    block_id=block_id,
                    block_ids=block_ids,
                    terminal=result.terminal,
                )
            )
            messages.append(
                _tool_message(tool_call.id, tool_call.name, result.text)
            )
            if race_controller is not None:
                race_controller.after_tool_return(
                    tool_call.name,
                    dict(tool_call.arguments),
                    result.text,
                    adapter=adapter,
                    runtime=runtime,
                )

            if result.terminal:
                final_answer = result.text
                stop_reason = "answer"
                events.append(
                    AgentEventRecord(
                        event_id=event_id,
                        reasoning=reasoning,
                        tool_calls=loop_tool_calls,
                    )
                )
                return AgentRunResult(
                    final_answer=final_answer,
                    messages=messages,
                    events=events,
                    race_events=list(race_controller.events) if race_controller is not None else [],
                    stop_reason=stop_reason,
                    policy=policy,
                    document=document,
                    resend_answer_count=(
                        race_controller.resend_answer_count if race_controller is not None else 0
                    ),
                    token_usage=token_usage,
                    llm_call_count=llm_call_count,
                )

        events.append(
            AgentEventRecord(
                event_id=event_id,
                reasoning=reasoning,
                tool_calls=loop_tool_calls,
            )
        )

    return AgentRunResult(
        final_answer=final_answer,
        messages=messages,
        events=events,
        race_events=list(race_controller.events) if race_controller is not None else [],
        stop_reason=stop_reason,
        policy=policy,
        document=document,
        resend_answer_count=race_controller.resend_answer_count if race_controller is not None else 0,
        token_usage=token_usage,
        llm_call_count=llm_call_count,
    )
