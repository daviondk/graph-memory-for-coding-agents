from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from block_context.errors import BlockNotFoundError
from block_context.types import BlockState, ContextBlock, TransformType

if TYPE_CHECKING:
    from block_context.runtime import BlockContextRuntime


@dataclass(frozen=True, slots=True)
class BlockSpan:
    block_id: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class RenderedContext:
    text: str
    block_spans: tuple[BlockSpan, ...]


class ContextDocument:
    def __init__(self, runtime: BlockContextRuntime) -> None:
        self._runtime = runtime
        self._block_ids: list[str] = []

    @property
    def block_ids(self) -> tuple[str, ...]:
        return tuple(self._block_ids)

    def add_block(self, block: ContextBlock | str) -> ContextDocument:
        block_id = block if isinstance(block, str) else block.id
        self._runtime.get_block(block_id)
        self._block_ids.append(block_id)
        return self

    def add_text(self, content: str, *, title: str | None = None) -> ContextBlock:
        block = self._runtime.create_immutable_block(content, title=title)
        self.add_block(block)
        return block

    def render(self) -> RenderedContext:
        return _render_blocks([self._runtime.get_block(block_id) for block_id in self._block_ids])

    def render_safe(self) -> RenderedContext:
        blocks = [self._runtime.get_block(block_id) for block_id in self._block_ids]
        safe_blocks = self._safe_blocks(blocks)
        return _render_blocks(safe_blocks)

    def refresh_notice_block(self) -> ContextBlock | None:
        blocks = [self._runtime.get_block(block_id) for block_id in self._block_ids]
        omitted = [block for block in blocks if block.is_mutable_block() and block.state != BlockState.VALID]
        if not omitted:
            return None
        return self._runtime.create_refresh_notice_block(omitted)

    def _safe_blocks(self, blocks: list[ContextBlock]) -> list[ContextBlock]:
        omitted = [block for block in blocks if block.is_mutable_block() and block.state != BlockState.VALID]
        if not omitted:
            return blocks

        notice = self._runtime.create_refresh_notice_block(omitted)
        safe = [block for block in blocks if not (block.is_mutable_block() and block.state != BlockState.VALID)]
        safe.append(notice)
        return safe


def _render_blocks(blocks: list[ContextBlock]) -> RenderedContext:
    # Agent-visible text is plain block.content only; block type/title metadata stay sidecar.
    text_parts: list[str] = []
    spans: list[BlockSpan] = []
    cursor = 0
    for block in blocks:
        if block.id is None:
            raise BlockNotFoundError("cannot render block without id")
        start = cursor
        text_parts.append(block.content)
        cursor += len(block.content)
        spans.append(BlockSpan(block.id, start, cursor))
    return RenderedContext("".join(text_parts), tuple(spans))
