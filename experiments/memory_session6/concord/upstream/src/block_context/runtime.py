from __future__ import annotations

import hashlib
import itertools
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any

from block_context.document import ContextDocument
from block_context.errors import SourceChangedError, WorkspacePathError
from block_context.index import SourceIndex
from block_context.locator import RelocationFailure, build_locator, relocate
from block_context.structured import compute_observation
from block_context.tools import ToolRegistry, ToolSpec
from block_context.types import AgentEvent, BlockState, ContextBlock, SourceRef, Span, TransformType


class BlockContextRuntime:
    def __init__(
        self,
        workspace_root: str | os.PathLike[str],
        *,
        locator_context_lines: int = 3,
        default_agent_id: str = "system",
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        if locator_context_lines < 0:
            raise ValueError("locator_context_lines must be >= 0")
        self.workspace_root = Path(workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.locator_context_lines = locator_context_lines
        self.default_agent_id = default_agent_id
        self.tool_registry = tool_registry or ToolRegistry()
        self._blocks: dict[str, ContextBlock] = {}
        self.source_index = SourceIndex()
        self._id_counter = itertools.count(1)
        self._register_builtin_tools()

    def new_document(self) -> ContextDocument:
        return ContextDocument(self)

    def register_tool(self, spec: ToolSpec) -> None:
        self.tool_registry.register_tool(spec)

    def record_event(self, event: AgentEvent) -> list[ContextBlock]:
        blocks: list[ContextBlock] = []
        if event.reasoning_text:
            blocks.append(
                self.create_immutable_block(
                    event.reasoning_text,
                    title="agent reasoning",
                    owner_agent_id=event.agent_id,
                    event_id=event.event_id,
                )
            )

        blocks.append(
            self.create_immutable_block(
                event.tool_call_text or self._default_tool_call_text(event),
                title=f"tool call: {event.tool_name}",
                owner_agent_id=event.agent_id,
                event_id=event.event_id,
            )
        )

        spec = self.tool_registry.get(event.tool_name)
        if spec is None:
            if event.tool_result_text is not None or event.tool_result is not None:
                blocks.append(
                    self.create_immutable_block(
                        event.tool_result_text or self._default_tool_result_text(event.tool_result),
                        title=f"tool result: {event.tool_name}",
                        owner_agent_id=event.agent_id,
                        event_id=event.event_id,
                    )
                )
            return blocks

        if "update" in spec.roles:
            self._apply_update_tool(spec, event)

        if "register" in spec.roles:
            block = self._apply_register_tool(spec, event)
            if block is not None:
                blocks.append(block)
        elif event.tool_result_text is not None or event.tool_result is not None:
            blocks.append(
                self.create_immutable_block(
                    event.tool_result_text or self._default_tool_result_text(event.tool_result),
                    title=f"tool result: {event.tool_name}",
                    owner_agent_id=event.agent_id,
                    event_id=event.event_id,
                )
            )

        return blocks

    def create_immutable_block(
        self,
        content: str,
        *,
        title: str | None = None,
        owner_agent_id: str | None = None,
        event_id: str | None = None,
    ) -> ContextBlock:
        metadata = {"title": title} if title else {}
        return self._add_block(
            content=content,
            transform_type=TransformType.IMMUTABLE,
            source_set=(),
            metadata=metadata,
            owner_agent_id=owner_agent_id or self.default_agent_id,
            event_id=event_id,
        )

    def read_file(
        self,
        path: str,
        span: Span | tuple[int, int] | None = None,
        *,
        title: str | None = None,
        agent_id: str | None = None,
        event_id: str | None = None,
    ) -> ContextBlock:
        return self._create_verbatim_block(
            path,
            span=span,
            title=title,
            owner_agent_id=agent_id or self.default_agent_id,
            event_id=event_id,
        )

    def create_verbatim_from_content(
        self,
        path: str,
        content: str,
        span: Span | tuple[int, int],
        *,
        title: str | None = None,
        agent_id: str | None = None,
        event_id: str | None = None,
    ) -> ContextBlock:
        object_id = self._object_id(path)
        source_content = self._resolve(path).read_text()
        block_span = self._coerce_span(span)
        if block_span is None:
            raise ValueError("span is required when creating verbatim content blocks")
        locator = build_locator(source_content, block_span, context_window=self.locator_context_lines)
        source = SourceRef(
            object_id=object_id,
            version=self._version_for_content(source_content),
            span=block_span,
            transform_type=TransformType.VERBATIM,
            locator=locator,
        )
        metadata = {"title": title} if title else {}
        return self._add_block(
            content=content,
            transform_type=TransformType.VERBATIM,
            source_set=(source,),
            metadata=metadata,
            owner_agent_id=agent_id or self.default_agent_id,
            event_id=event_id,
        )

    def create_verbatim_observation_block(
        self,
        path: str,
        content: str,
        *,
        title: str | None = None,
        agent_id: str | None = None,
        event_id: str | None = None,
    ) -> ContextBlock:
        """Register agent-visible tool output as mutable evidence for a source.

        Some tools render source-backed observations in a format that is not a
        literal file span, such as Hotpot's numbered lines. These blocks can be
        repaired by benchmark patch logic without changing the text the model
        would otherwise have seen.
        """
        object_id = self._object_id(path)
        source = SourceRef(
            object_id=object_id,
            version=self._version_for_path(object_id),
            span=None,
            transform_type=TransformType.VERBATIM,
            locator=None,
        )
        metadata: dict[str, object] = {"observation_text": "agent-visible"}
        if title:
            metadata["title"] = title
        return self._add_block(
            content=content,
            transform_type=TransformType.VERBATIM,
            source_set=(source,),
            metadata=metadata,
            owner_agent_id=agent_id or self.default_agent_id,
            event_id=event_id,
        )

    def observe_file(
        self,
        path: str,
        kind: str,
        *,
        title: str | None = None,
        agent_id: str | None = None,
        event_id: str | None = None,
    ) -> ContextBlock:
        return self._create_structured_block(
            path,
            kind,
            title=title,
            owner_agent_id=agent_id or self.default_agent_id,
            event_id=event_id,
        )

    def create_glob_listing_block(
        self,
        pattern: str,
        matches: list[str],
        *,
        title: str | None = None,
        agent_id: str | None = None,
        event_id: str | None = None,
    ) -> ContextBlock:
        if not matches:
            raise ValueError("glob listing requires at least one match")
        sorted_matches = sorted(matches)
        source_set = tuple(
            SourceRef(
                object_id=object_id,
                version=self._version_for_path(object_id),
                span=None,
                transform_type=TransformType.STRUCTURED,
            )
            for object_id in sorted(set(sorted_matches))
        )
        metadata: dict[str, object] = {
            "observation_kind": "glob-listing",
            "pattern": pattern,
            "matches": sorted_matches,
            "observer_semantics": "predicate",
        }
        if title:
            metadata["title"] = title
        return self._add_block(
            content="\n".join(sorted_matches),
            transform_type=TransformType.STRUCTURED,
            source_set=source_set,
            metadata=metadata,
            owner_agent_id=agent_id or self.default_agent_id,
            event_id=event_id,
        )

    def create_refresh_notice_block(self, omitted_blocks: list[ContextBlock]) -> ContextBlock:
        lines = ["\nSome mutable context was omitted because it may be stale.\n", "\n"]
        for block in omitted_blocks:
            lines.append(f"- {self._notice_line(block)}\n")
        owner = omitted_blocks[0].owner_agent_id if omitted_blocks else self.default_agent_id
        return self._add_block(
            content="".join(lines),
            transform_type=TransformType.REFRESH_NOTICE,
            source_set=(),
            metadata={"title": "Refresh notice"},
            owner_agent_id=owner,
            event_id=None,
            register=False,
        )

    def write_file(
        self,
        path: str,
        content: str,
        *,
        expected_version: str | None = None,
        create: bool = False,
        agent_id: str | None = None,
        event_id: str | None = None,
    ) -> list[ContextBlock]:
        return self._write_source(path, content, expected_version=expected_version, create=create)

    def apply_text_replacement(
        self,
        path: str,
        old: str,
        new: str,
        *,
        count: int = 1,
        expected_version: str | None = None,
        agent_id: str | None = None,
        event_id: str | None = None,
    ) -> list[ContextBlock]:
        source_path = self._resolve(path)
        content = source_path.read_text()
        if old not in content:
            raise ValueError(f"old text not found in {self._object_id(path)}")
        return self._write_source(
            path,
            content.replace(old, new, count),
            expected_version=expected_version,
            create=False,
        )

    def validate_before_use(self, block_id: str) -> ContextBlock:
        block = self.get_block(block_id)
        if not block.is_mutable_block() or not block.is_valid():
            return block

        changed_sources: list[str] = []
        for ref in block.source_set:
            current_version = self._version_for_path(ref.object_id)
            if current_version != ref.version:
                changed_sources.append(ref.object_id)

        for object_id in changed_sources:
            new_content = self._resolve(object_id).read_text()
            self._cohere_source(object_id, new_content, self._version_for_content(new_content))
        return self.get_block(block_id)

    def get_block(self, block_id: str) -> ContextBlock:
        try:
            return self._blocks[block_id]
        except KeyError as exc:
            raise KeyError(f"unknown block id: {block_id}") from exc

    def list_blocks(self) -> list[ContextBlock]:
        return list(self._blocks.values())

    def source_version(self, path: str) -> str:
        return self._version_for_path(self._object_id(path))

    def _create_verbatim_block(
        self,
        path: str,
        *,
        span: Span | tuple[int, int] | None,
        title: str | None,
        owner_agent_id: str,
        event_id: str | None,
    ) -> ContextBlock:
        object_id = self._object_id(path)
        content = self._resolve(path).read_text()
        block_span = self._coerce_span(span) or self._whole_file_span(content)
        block_content = self._select_span(content, block_span)
        locator = build_locator(content, block_span, context_window=self.locator_context_lines)
        source = SourceRef(
            object_id=object_id,
            version=self._version_for_content(content),
            span=block_span,
            transform_type=TransformType.VERBATIM,
            locator=locator,
        )
        return self._add_block(
            content=block_content,
            transform_type=TransformType.VERBATIM,
            source_set=(source,),
            metadata={"title": title} if title else {},
            owner_agent_id=owner_agent_id,
            event_id=event_id,
        )

    def _create_structured_block(
        self,
        path: str,
        kind: str,
        *,
        title: str | None,
        owner_agent_id: str,
        event_id: str | None,
    ) -> ContextBlock:
        object_id = self._object_id(path)
        content = self._resolve(path).read_text()
        observation = compute_observation(kind, object_id, content)
        source = SourceRef(
            object_id=object_id,
            version=self._version_for_content(content),
            span=None,
            transform_type=TransformType.STRUCTURED,
            locator=None,
        )
        metadata = {
            "observation_kind": kind,
            "observer_semantics": observation.semantics,
        }
        if title:
            metadata["title"] = title
        return self._add_block(
            content=observation.content,
            transform_type=TransformType.STRUCTURED,
            source_set=(source,),
            metadata=metadata,
            owner_agent_id=owner_agent_id,
            event_id=event_id,
        )

    def _write_source(
        self,
        path: str,
        content: str,
        *,
        expected_version: str | None = None,
        create: bool = False,
    ) -> list[ContextBlock]:
        source_path = self._resolve(path)
        if not source_path.exists() and not create:
            raise FileNotFoundError(source_path)

        previous_content = source_path.read_text() if source_path.exists() else ""
        previous_version = self._version_for_content(previous_content)
        if expected_version is not None and expected_version != previous_version:
            raise SourceChangedError(
                f"{self._object_id(path)} expected {expected_version}, found {previous_version}"
            )

        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(content)
        new_version = self._version_for_content(content)
        if new_version == previous_version:
            return []
        return self._cohere_source(self._object_id(path), content, new_version)

    def _cohere_source(self, object_id: str, new_content: str, new_version: str) -> list[ContextBlock]:
        affected_ids = sorted(self.source_index.affected_blocks(object_id))
        affected: list[ContextBlock] = []
        for block_id in affected_ids:
            block = self.get_block(block_id)
            if not any(ref.object_id == object_id for ref in block.source_set):
                continue
            if block.transform_type == TransformType.VERBATIM:
                self._refresh_verbatim_block(block, object_id, new_content, new_version)
            elif block.transform_type == TransformType.STRUCTURED:
                self._refresh_structured_block(block, object_id, new_content, new_version)
            affected.append(block)

        self.source_index.rebuild(self._blocks)
        if object_id in self.source_index.by_source:
            self.source_index.by_source[object_id].source_version = new_version
        return affected

    def _refresh_verbatim_block(
        self,
        block: ContextBlock,
        object_id: str,
        new_content: str,
        new_version: str,
    ) -> None:
        if len(block.source_set) != 1:
            self._mark_stale(block, f"cannot automatically relocate multi-source mutable block for {object_id}")
            return

        ref = block.source_set[0]
        if ref.locator is None:
            self._mark_stale(block, f"verbatim mutable block for {object_id} has no source locator")
            return

        relocated = relocate(ref.locator, new_content)
        if isinstance(relocated, RelocationFailure):
            self._mark_invalid(block, relocated.reason)
            return
        if not relocated.content:
            self._mark_invalid(block, "anchored locator resolved to empty content")
            return

        locator = build_locator(
            new_content,
            relocated.span,
            context_window=ref.locator.context_window,
        )
        new_ref = replace(ref, version=new_version, span=relocated.span, locator=locator)
        block.content = relocated.content
        block.source_set = (new_ref,)
        block.state = BlockState.VALID
        block.stale_reason = None
        block.metadata["last_coherence_action"] = "anchored-update-on-write"

    def _refresh_structured_block(
        self,
        block: ContextBlock,
        object_id: str,
        new_content: str,
        new_version: str,
    ) -> None:
        kind = block.metadata.get("observation_kind")
        if kind == "glob-listing":
            block.source_set = tuple(
                replace(ref, version=new_version) if ref.object_id == object_id else ref
                for ref in block.source_set
            )
            block.state = BlockState.VALID
            block.stale_reason = None
            block.metadata["last_coherence_action"] = "glob-listing-unchanged-on-content-write"
            return
        if len(block.source_set) != 1:
            self._mark_stale(block, f"cannot automatically recompute multi-source mutable block for {object_id}")
            return
        if not isinstance(kind, str):
            self._mark_stale(block, "structured mutable block is missing observation_kind metadata")
            return

        observation = compute_observation(kind, object_id, new_content)
        ref = replace(block.source_set[0], version=new_version)
        block.content = observation.content
        block.source_set = (ref,)
        block.state = BlockState.VALID
        block.stale_reason = None
        block.metadata["last_coherence_action"] = "whole-file-recompute-on-write"

    @staticmethod
    def _mark_stale(block: ContextBlock, reason: str) -> None:
        block.state = BlockState.STALE
        block.stale_reason = reason
        block.metadata["last_coherence_action"] = "stale-on-write"

    @staticmethod
    def _mark_invalid(block: ContextBlock, reason: str) -> None:
        block.state = BlockState.INVALID
        block.stale_reason = reason
        block.metadata["last_coherence_action"] = "invalid-on-write"

    def _add_block(
        self,
        *,
        content: str,
        transform_type: TransformType,
        source_set: tuple[SourceRef, ...],
        owner_agent_id: str,
        event_id: str | None,
        metadata: dict[str, object] | None = None,
        register: bool = True,
    ) -> ContextBlock:
        self._require_non_empty(content)
        block = ContextBlock(
            id=f"block-{next(self._id_counter):06d}",
            content=content,
            transform_type=transform_type,
            owner_agent_id=owner_agent_id,
            event_id=event_id,
            source_set=source_set,
            metadata=dict(metadata or {}),
        )
        self._blocks[block.id] = block
        if register:
            self.source_index.register(block)
        return block

    def _apply_update_tool(self, spec: ToolSpec, event: AgentEvent) -> None:
        if spec.source_from_args is None:
            raise ValueError(f"update tool {spec.name} must define source_from_args")
        source = spec.source_from_args(event.tool_args)
        if spec.content_from_args is not None:
            content = spec.content_from_args(event.tool_args)
        elif spec.content_from_result is not None:
            content = spec.content_from_result(event.tool_result)
        else:
            raise ValueError(f"update tool {spec.name} must define content extractor")
        self._write_source(source, content, create=True)

    def _apply_register_tool(self, spec: ToolSpec, event: AgentEvent) -> ContextBlock | None:
        if spec.source_from_args is None:
            raise ValueError(f"register tool {spec.name} must define source_from_args")
        source = spec.source_from_args(event.tool_args)
        title = f"tool result: {event.tool_name}"
        if spec.output_block == TransformType.VERBATIM:
            span = spec.span_from_args(event.tool_args) if spec.span_from_args else None
            return self._create_verbatim_block(
                source,
                span=span,
                title=title,
                owner_agent_id=event.agent_id,
                event_id=event.event_id,
            )
        if spec.output_block == TransformType.STRUCTURED:
            if spec.observation_kind is None:
                raise ValueError(f"structured register tool {spec.name} must define observation_kind")
            return self._create_structured_block(
                source,
                spec.observation_kind,
                title=title,
                owner_agent_id=event.agent_id,
                event_id=event.event_id,
            )
        return None

    def _notice_line(self, block: ContextBlock) -> str:
        reason = block.stale_reason or block.state.value
        ref = block.source_set[0] if block.source_set else None
        owner = f"agent {block.owner_agent_id}"
        if ref is None:
            title = block.metadata.get("title") or block.id
            return f"{owner} {title}: {reason}; refresh this context if needed."

        span = f" {ref.span.label()}" if ref.span else ""
        return f"{owner} {ref.object_id}{span}: {reason}; re-run or re-read this source if needed."

    def _register_builtin_tools(self) -> None:
        if self.tool_registry.get("read_file") is None:
            self.tool_registry.register_tool(
                ToolSpec(
                    name="read_file",
                    roles=frozenset({"register"}),
                    output_block=TransformType.VERBATIM,
                    source_from_args=lambda args: str(args["path"]),
                    span_from_args=lambda args: args.get("span"),
                )
            )
        if self.tool_registry.get("write_file") is None:
            self.tool_registry.register_tool(
                ToolSpec(
                    name="write_file",
                    roles=frozenset({"update"}),
                    source_from_args=lambda args: str(args["path"]),
                    content_from_args=lambda args: str(args["content"]),
                )
            )

    @staticmethod
    def _default_tool_call_text(event: AgentEvent) -> str:
        return f"Tool call: {event.tool_name}({json.dumps(event.tool_args, sort_keys=True)})\n"

    @staticmethod
    def _default_tool_result_text(result: Any) -> str:
        if result is None:
            return "Tool result: <none>\n"
        return f"Tool result: {result}\n"

    def _object_id(self, path: str) -> str:
        return self._resolve(path).relative_to(self.workspace_root).as_posix()

    def _resolve(self, path: str) -> Path:
        resolved = (self.workspace_root / path).resolve()
        try:
            resolved.relative_to(self.workspace_root)
        except ValueError as exc:
            raise WorkspacePathError(f"path escapes workspace root: {path}") from exc
        return resolved

    def _version_for_path(self, object_id: str) -> str:
        return self._version_for_content(self._resolve(object_id).read_text())

    @staticmethod
    def _version_for_content(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()

    @staticmethod
    def _coerce_span(span: Span | tuple[int, int] | None) -> Span | None:
        if span is None or isinstance(span, Span):
            return span
        return Span(span[0], span[1])

    @staticmethod
    def _whole_file_span(content: str) -> Span:
        line_count = max(1, len(content.splitlines()))
        return Span(1, line_count)

    @staticmethod
    def _select_span(content: str, span: Span) -> str:
        lines = content.splitlines(keepends=True)
        if span.start_line > len(lines):
            raise ValueError(f"span {span.label()} does not exist")
        if span.end_line > len(lines):
            raise ValueError(f"span {span.label()} does not exist")
        return "".join(lines[span.start_line - 1 : span.end_line])

    @staticmethod
    def _require_non_empty(content: str) -> None:
        if content == "":
            raise ValueError("blocks cannot be empty")
