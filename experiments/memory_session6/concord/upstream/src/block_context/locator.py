from __future__ import annotations

import hashlib
from dataclasses import dataclass

from block_context.types import SourceLocator, Span


@dataclass(frozen=True, slots=True)
class Relocation:
    content: str
    span: Span


@dataclass(frozen=True, slots=True)
class RelocationFailure:
    reason: str


def build_locator(
    full_content: str,
    span: Span,
    *,
    context_window: int,
) -> SourceLocator:
    lines = full_content.splitlines(keepends=True)
    if span.start_line > len(lines):
        raise ValueError(f"span {span.label()} does not exist")

    block_lines = lines[span.start_line - 1 : span.end_line]
    block_content = "".join(block_lines)
    pre_start = max(0, span.start_line - 1 - context_window)
    pre_context = tuple(lines[pre_start : span.start_line - 1])
    post_end = min(len(lines), span.end_line + context_window)
    post_context = tuple(lines[span.end_line : post_end])
    unique_anchor_lines = _unique_anchor_lines(block_lines + list(pre_context) + list(post_context), lines)
    context_blob = "".join(pre_context) + "\0" + "".join(post_context)

    return SourceLocator(
        content=block_content,
        content_hash=_hash(block_content),
        pre_context=pre_context,
        post_context=post_context,
        context_hash=_hash(context_blob),
        unique_anchor_lines=tuple(unique_anchor_lines),
        context_window=context_window,
    )


def relocate(locator: SourceLocator, new_content: str) -> Relocation | RelocationFailure:
    lines = new_content.splitlines(keepends=True)

    exact_matches = _find_sequence(lines, locator.content.splitlines(keepends=True))
    if len(exact_matches) == 1:
        start, end = exact_matches[0]
        return Relocation(locator.content, Span(start + 1, end))
    if len(exact_matches) > 1:
        return RelocationFailure("ambiguous exact anchor")

    bounded_matches = _context_bounded_matches(lines, locator.pre_context, locator.post_context)
    if len(bounded_matches) == 1:
        start, end = bounded_matches[0]
        if start == end:
            return RelocationFailure("anchored locator resolved to empty content")
        return Relocation("".join(lines[start:end]), Span(start + 1, end))
    if len(bounded_matches) > 1:
        return RelocationFailure("ambiguous context-bounded anchor")

    anchor_matches = _anchor_assisted_matches(lines, locator.content.splitlines(keepends=True), locator.unique_anchor_lines)
    if len(anchor_matches) == 1:
        start, end = anchor_matches[0]
        return Relocation("".join(lines[start:end]), Span(start + 1, end))
    if len(anchor_matches) > 1:
        return RelocationFailure("ambiguous unique anchor")

    return RelocationFailure("source content changed and anchored locator was not found")


def _find_sequence(lines: list[str], needle: list[str]) -> list[tuple[int, int]]:
    if not needle:
        return []
    matches: list[tuple[int, int]] = []
    needle_len = len(needle)
    for start in range(0, len(lines) - needle_len + 1):
        end = start + needle_len
        if lines[start:end] == needle:
            matches.append((start, end))
    return matches


def _context_bounded_matches(
    lines: list[str],
    pre_context: tuple[str, ...],
    post_context: tuple[str, ...],
) -> list[tuple[int, int]]:
    if not pre_context and not post_context:
        return []

    matches: list[tuple[int, int]] = []
    pre_matches = _find_sequence(lines, list(pre_context)) if pre_context else [(0, 0)]
    post_matches = _find_sequence(lines, list(post_context)) if post_context else [(len(lines), len(lines))]

    for _, pre_end in pre_matches:
        for post_start, _ in post_matches:
            if pre_end <= post_start:
                matches.append((pre_end, post_start))
    return matches


def _anchor_assisted_matches(
    lines: list[str],
    old_block_lines: list[str],
    unique_anchor_lines: tuple[str, ...],
) -> list[tuple[int, int]]:
    matches: list[tuple[int, int]] = []
    for anchor in unique_anchor_lines:
        if anchor not in old_block_lines:
            continue
        anchor_offset = old_block_lines.index(anchor)
        positions = [idx for idx, line in enumerate(lines) if line == anchor]
        if len(positions) == 1:
            start = positions[0] - anchor_offset
            end = start + len(old_block_lines)
            if start >= 0 and end <= len(lines):
                matches.append((start, end))
    return sorted(set(matches))


def _unique_anchor_lines(candidate_lines: list[str], source_lines: list[str]) -> list[str]:
    anchors: list[str] = []
    seen: set[str] = set()
    for line in candidate_lines:
        if not line.strip():
            continue
        if line in seen:
            continue
        seen.add(line)
        if source_lines.count(line) == 1:
            anchors.append(line)
    return anchors[:5]


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()
