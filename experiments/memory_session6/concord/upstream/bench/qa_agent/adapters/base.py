from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SearchHit:
    title: str
    source_path: str
    snippet: str


@dataclass(frozen=True, slots=True)
class GrepHit:
    path: str
    line: int
    context: str
    context_start: int
    context_end: int


class DatasetAdapter(Protocol):
    benchmark: str

    def workspace_root(self) -> Path: ...

    def resolve_source_path(self, source_id: str) -> str: ...

    def read_text(self, source_id: str, span: tuple[int, int] | None = None) -> str: ...

    def workspace_summary(self) -> str: ...
