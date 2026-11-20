from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from block_context.types import ContextBlock


@dataclass(slots=True)
class ToolResult:
    text: str
    block: ContextBlock | None = None
    blocks: tuple[ContextBlock, ...] = ()
    terminal: bool = False

    def all_blocks(self) -> tuple[ContextBlock, ...]:
        if self.blocks:
            return self.blocks
        if self.block is not None:
            return (self.block,)
        return ()


class Tool(Protocol):
    name: str
    description: str
    parameters: dict[str, Any]

    def execute(self, **kwargs: Any) -> ToolResult: ...


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self._tools.values()
        ]

    def execute(self, name: str, arguments: dict[str, Any] | str) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"unknown tool: {name}")
        if isinstance(arguments, str):
            args = json.loads(arguments) if arguments.strip() else {}
        else:
            args = dict(arguments)
        return tool.execute(**args)
