from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TransformType(StrEnum):
    IMMUTABLE = "immutable"
    VERBATIM = "verbatim"
    STRUCTURED = "structured"
    REFRESH_NOTICE = "refresh_notice"


class BlockState(StrEnum):
    VALID = "valid"
    STALE = "stale"
    UPDATING = "updating"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class Span:
    start_line: int
    end_line: int

    def __post_init__(self) -> None:
        if self.start_line < 1:
            raise ValueError("start_line must be >= 1")
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")

    def label(self) -> str:
        if self.start_line == self.end_line:
            return f"line {self.start_line}"
        return f"lines {self.start_line}-{self.end_line}"


@dataclass(frozen=True, slots=True)
class SourceLocator:
    content: str
    content_hash: str
    pre_context: tuple[str, ...]
    post_context: tuple[str, ...]
    context_hash: str
    unique_anchor_lines: tuple[str, ...]
    context_window: int


@dataclass(frozen=True, slots=True)
class SourceRef:
    object_id: str
    version: str
    span: Span | None
    transform_type: TransformType
    locator: SourceLocator | None = None


@dataclass(slots=True)
class ContextBlock:
    id: str
    content: str
    transform_type: TransformType
    owner_agent_id: str
    event_id: str | None = None
    source_set: tuple[SourceRef, ...] = ()
    state: BlockState = BlockState.VALID
    metadata: dict[str, Any] = field(default_factory=dict)
    stale_reason: str | None = None

    def is_mutable_block(self) -> bool:
        return self.transform_type in {
            TransformType.VERBATIM,
            TransformType.STRUCTURED,
        }

    def is_valid(self) -> bool:
        return self.state == BlockState.VALID


@dataclass(frozen=True, slots=True)
class AgentEvent:
    event_id: str
    agent_id: str
    tool_name: str
    tool_args: dict[str, Any]
    tool_result: Any = None
    reasoning_text: str | None = None
    tool_call_text: str | None = None
    tool_result_text: str | None = None
