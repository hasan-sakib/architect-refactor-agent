from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import tree_sitter_language_pack as tslp

from app.core.config import get_settings

settings = get_settings()


@dataclass
class CodeChunk:
    id: str
    file_path: str
    language: str
    kind: str
    name: Optional[str]
    context_path: str
    start_line: int
    end_line: int
    content: str
    part_index: int = 0
    part_total: int = 1


@dataclass
class _RawSpan:
    kind: str
    name: Optional[str]
    context_path: str
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int


def detect_language(file_path: str) -> Optional[str]:
    return tslp.detect_language_from_path(file_path)


def _flatten_structure(items, source_bytes: bytes, prefix: list[str]) -> list[_RawSpan]:
    spans: list[_RawSpan] = []
    for item in items:
        if item.span is None:
            continue
        name = item.name
        context_path = ".".join(prefix + [name]) if name else ".".join(prefix)
        kind = str(item.kind).lower()

        if item.children:
            first_child_start = min(
                (c.span.start_byte for c in item.children if c.span is not None),
                default=item.span.end_byte,
            )
            head_end = max(item.span.start_byte, min(first_child_start, item.span.end_byte))
            if head_end > item.span.start_byte:
                spans.append(
                    _RawSpan(
                        kind=kind,
                        name=name,
                        context_path=context_path,
                        start_byte=item.span.start_byte,
                        end_byte=head_end,
                        start_line=item.span.start_line,
                        end_line=source_bytes.count(b"\n", 0, head_end),
                    )
                )
            spans.extend(_flatten_structure(item.children, source_bytes, prefix + ([name] if name else [])))
        else:
            spans.append(
                _RawSpan(
                    kind=kind,
                    name=name,
                    context_path=context_path,
                    start_byte=item.span.start_byte,
                    end_byte=item.span.end_byte,
                    start_line=item.span.start_line,
                    end_line=item.span.end_line,
                )
            )
    return spans


def _residual_spans(top_level_items, source_bytes: bytes) -> list[_RawSpan]:
    covered = sorted(
        (item.span.start_byte, item.span.end_byte)
        for item in top_level_items
        if item.span is not None
    )
    gaps: list[tuple[int, int]] = []
    cursor = 0
    for start, end in covered:
        if start > cursor:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < len(source_bytes):
        gaps.append((cursor, len(source_bytes)))

    spans = []
    for start, end in gaps:
        if not source_bytes[start:end].strip():
            continue
        spans.append(
            _RawSpan(
                kind="module",
                name=None,
                context_path="",
                start_byte=start,
                end_byte=end,
                start_line=source_bytes.count(b"\n", 0, start),
                end_line=source_bytes.count(b"\n", 0, end),
            )
        )
    return spans


def _split_oversized(span: _RawSpan, source_bytes: bytes, max_bytes: int) -> list[_RawSpan]:
    total = span.end_byte - span.start_byte
    if total <= max_bytes:
        return [span]

    parts: list[_RawSpan] = []
    cursor = span.start_byte
    while cursor < span.end_byte:
        chunk_end = min(cursor + max_bytes, span.end_byte)
        parts.append(
            _RawSpan(
                kind=span.kind,
                name=span.name,
                context_path=span.context_path,
                start_byte=cursor,
                end_byte=chunk_end,
                start_line=source_bytes.count(b"\n", 0, cursor),
                end_line=source_bytes.count(b"\n", 0, chunk_end),
            )
        )
        cursor = chunk_end
    return parts


def _make_chunk_id(file_path: str, start_byte: int, end_byte: int, part_index: int) -> str:
    digest = hashlib.sha1(f"{file_path}:{start_byte}:{end_byte}:{part_index}".encode()).hexdigest()[:16]
    return f"{file_path}::{digest}"


def chunk_source(source: str, file_path: str, language: Optional[str] = None) -> list[CodeChunk]:
    if language is None:
        language = detect_language(file_path)

    source_bytes = source.encode("utf-8")

    raw_spans: list[_RawSpan]
    resolved_language = language or "text"

    if language is None:
        raw_spans = [
            _RawSpan(
                kind="file",
                name=None,
                context_path="",
                start_byte=0,
                end_byte=len(source_bytes),
                start_line=0,
                end_line=source_bytes.count(b"\n"),
            )
        ]
    else:
        try:
            config = tslp.ProcessConfig(language=language, structure=True)
            result = tslp.process(source, config)
        except Exception:
            raw_spans = [
                _RawSpan(
                    kind="file",
                    name=None,
                    context_path="",
                    start_byte=0,
                    end_byte=len(source_bytes),
                    start_line=0,
                    end_line=source_bytes.count(b"\n"),
                )
            ]
        else:
            raw_spans = _flatten_structure(result.structure, source_bytes, [])
            raw_spans.extend(_residual_spans(result.structure, source_bytes))

    raw_spans.sort(key=lambda s: s.start_byte)

    chunks: list[CodeChunk] = []
    for span in raw_spans:
        parts = _split_oversized(span, source_bytes, settings.RAG_CHUNK_MAX_BYTES)
        for part_index, part in enumerate(parts):
            content = source_bytes[part.start_byte:part.end_byte].decode("utf-8", errors="replace")
            if not content.strip():
                continue
            chunks.append(
                CodeChunk(
                    id=_make_chunk_id(file_path, part.start_byte, part.end_byte, part_index),
                    file_path=file_path,
                    language=resolved_language,
                    kind=part.kind,
                    name=part.name,
                    context_path=part.context_path,
                    start_line=part.start_line,
                    end_line=part.end_line,
                    content=content,
                    part_index=part_index,
                    part_total=len(parts),
                )
            )
    return chunks


def chunk_file(path: str, root_dir: Optional[str] = None) -> list[CodeChunk]:
    file_path = Path(path)
    source = file_path.read_text(encoding="utf-8", errors="replace")
    relative_path = str(file_path.relative_to(root_dir)) if root_dir else str(file_path)
    return chunk_source(source, relative_path)
