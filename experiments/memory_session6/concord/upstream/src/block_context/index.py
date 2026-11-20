from __future__ import annotations

from dataclasses import dataclass, field

from block_context.types import ContextBlock, TransformType


@dataclass(slots=True)
class SourceIndexEntry:
    source_version: str
    anchored_blocks: set[str] = field(default_factory=set)
    whole_file_blocks: set[str] = field(default_factory=set)
    predicate_blocks: set[str] = field(default_factory=set)

    def block_ids(self) -> set[str]:
        return (
            set(self.anchored_blocks)
            | set(self.whole_file_blocks)
            | set(self.predicate_blocks)
        )


class SourceIndex:
    def __init__(self) -> None:
        self.by_source: dict[str, SourceIndexEntry] = {}

    def register(self, block: ContextBlock) -> None:
        for source in block.source_set:
            entry = self.by_source.setdefault(source.object_id, SourceIndexEntry(source.version))
            entry.source_version = source.version
            if block.transform_type == TransformType.VERBATIM:
                entry.anchored_blocks.add(block.id)
            elif block.transform_type == TransformType.STRUCTURED:
                if block.metadata.get("observer_semantics") == "predicate":
                    entry.predicate_blocks.add(block.id)
                else:
                    entry.whole_file_blocks.add(block.id)

    def unregister(self, block: ContextBlock) -> None:
        for source in block.source_set:
            entry = self.by_source.get(source.object_id)
            if entry is None:
                continue
            entry.anchored_blocks.discard(block.id)
            entry.whole_file_blocks.discard(block.id)
            entry.predicate_blocks.discard(block.id)

    def affected_blocks(self, object_id: str) -> set[str]:
        entry = self.by_source.get(object_id)
        if entry is None:
            return set()
        return entry.block_ids()

    def rebuild(self, blocks: dict[str, ContextBlock]) -> None:
        self.by_source = {}
        for block in blocks.values():
            self.register(block)
