from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from block_context.types import Span, TransformType

ToolRole = Literal["register", "update"]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    roles: frozenset[ToolRole]
    output_block: TransformType | None = None
    source_from_args: Callable[[Mapping[str, Any]], str] | None = None
    content_from_result: Callable[[Any], str] | None = None
    content_from_args: Callable[[Mapping[str, Any]], str] | None = None
    span_from_args: Callable[[Mapping[str, Any]], Span | tuple[int, int] | None] | None = None
    observation_kind: str | None = None

    def __post_init__(self) -> None:
        if not self.roles:
            raise ValueError("tool spec must define at least one role")
        if self.output_block is not None and self.output_block not in {
            TransformType.VERBATIM,
            TransformType.STRUCTURED,
        }:
            raise ValueError("tool output_block must be verbatim or structured")
        if "register" in self.roles and self.output_block is None:
            raise ValueError("register tools must define output_block")
        if "register" in self.roles and self.source_from_args is None:
            raise ValueError("register tools must define source_from_args")
        if "update" in self.roles and self.source_from_args is None:
            raise ValueError("update tools must define source_from_args")
        if "update" in self.roles and self.content_from_args is None and self.content_from_result is None:
            raise ValueError("update tools must define content_from_args or content_from_result")
        if self.output_block == TransformType.STRUCTURED and self.observation_kind is None:
            raise ValueError("structured register tools must define observation_kind")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register_tool(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def require(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"unknown tool: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))
