"""Structure-aware chunking driven by Tree-sitter symbol boundaries.

Supported files are cut along their own syntax. Everything else — files
without a grammar, unparsable files and the gaps between symbols — is split by
character size with an overlap, never by a fixed line count.
"""

import os
from bisect import bisect_left, bisect_right
from dataclasses import dataclass

from app.parsing.json_structures import JSON_LANGUAGE, extract_json_structures
from app.parsing.parser import ParseFailedError, parse_source
from app.parsing.structures import extract_structures
from app.stats import estimate_text_tokens

DEFAULT_MAX_CHUNK_CHARACTERS = 6000
DEFAULT_TEXT_CHUNK_CHARACTERS = 4000
DEFAULT_TEXT_CHUNK_OVERLAP_CHARACTERS = 400
MAX_SPLIT_DEPTH = 3

SYMBOL_CHUNK = "symbol"
SYMBOL_PART_CHUNK = "symbol_part"
TEXT_CHUNK = "text"
STRUCTURAL_MODE = "structural"


def max_chunk_characters() -> int:
    """Largest size a single structural chunk may reach."""
    return _env_int("TREE_SITTER_MAX_CHUNK_CHARS", DEFAULT_MAX_CHUNK_CHARACTERS)


def text_chunk_characters() -> int:
    """Character budget for the size-based text chunks."""
    return _env_int("CHUNK_SIZE_CHARACTERS", DEFAULT_TEXT_CHUNK_CHARACTERS)


def text_chunk_overlap_characters() -> int:
    """Characters repeated between neighbouring text chunks."""
    overlap = _env_int(
        "CHUNK_OVERLAP_CHARACTERS", DEFAULT_TEXT_CHUNK_OVERLAP_CHARACTERS
    )
    return min(overlap, text_chunk_characters() // 2)


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, "").strip())
    except ValueError:
        return default
    return value if value > 0 else default


def chunk_source(file_path: str, text: str) -> tuple[list[dict], dict]:
    """Chunk one file by syntax, falling back to size-based text chunks.

    Returns chunks without a global chunk_index, plus per-file statistics.
    """
    stats = {
        "file_path": file_path,
        "supported": False,
        "parsed": False,
        "has_errors": False,
        "structures": 0,
        "errors": 0,
        "chunks": 0,
        "mode": TEXT_CHUNK,
        "language": None,
    }

    try:
        parsed = parse_source(file_path, text)
    except ParseFailedError as exc:
        stats["parse_error"] = str(exc)
        parsed = None

    if parsed is None:
        return _finish(stats, _whole_file_text_chunks(file_path, None, text))

    structures = _extract_structures(parsed)
    chunks = _structural_chunks(parsed, structures, text)

    stats.update(
        supported=True,
        parsed=True,
        has_errors=parsed.has_errors,
        structures=len(structures),
        errors=len(parsed.errors),
        mode=STRUCTURAL_MODE,
        language=parsed.language,
    )

    return _finish(stats, chunks)


def inspect_source(file_path: str, text: str) -> dict:
    """Parse one file once and return its tree, structures and final chunks."""
    result = {
        "mode": TEXT_CHUNK,
        "language": None,
        "supported": False,
        "parsed": False,
        "has_errors": False,
        "parse_error": None,
        "truncated_after_line": None,
        "node_count": 0,
        "errors": [],
        "tree": [],
        "tree_truncated": False,
        "structures": [],
        "chunks": [],
    }

    try:
        parsed = parse_source(file_path, text)
    except ParseFailedError as exc:
        result["parse_error"] = str(exc)
        parsed = None

    if parsed is None:
        result["chunks"] = _whole_file_text_chunks(file_path, None, text)
        return result

    structures = _extract_structures(parsed)
    tree, tree_truncated = parsed.serialize_tree()

    result.update(
        mode=STRUCTURAL_MODE,
        language=parsed.language,
        supported=True,
        parsed=True,
        has_errors=parsed.has_errors,
        truncated_after_line=parsed.truncated_after_line,
        node_count=parsed.node_count,
        errors=parsed.errors,
        tree=tree,
        tree_truncated=tree_truncated,
        structures=[structure.to_dict() for structure in structures],
        chunks=_structural_chunks(parsed, structures, text),
    )

    return result


def _extract_structures(parsed) -> list:
    if parsed.language == JSON_LANGUAGE:
        return extract_json_structures(parsed)
    return extract_structures(parsed)


def _whole_file_text_chunks(
    file_path: str, language: str | None, text: str
) -> list[dict]:
    source = _Source(file_path, language, text)
    return _text_chunks(source, 0, len(source.data))


def _finish(stats: dict, chunks: list[dict]) -> tuple[list[dict], dict]:
    counts: dict[str, int] = {}
    for chunk in chunks:
        counts[chunk["chunk_type"]] = counts.get(chunk["chunk_type"], 0) + 1

    stats["chunks"] = len(chunks)
    stats["chunk_type_counts"] = counts
    return chunks, stats


def _structural_chunks(parsed, structures, text: str) -> list[dict]:
    source = _Source(parsed.file_path, parsed.language, text)
    budget = max_chunk_characters()

    children_of: dict[str, list] = {}
    for structure in structures:
        if structure.parent_id is not None:
            children_of.setdefault(structure.parent_id, []).append(structure)

    chunks = []
    cursor = 0

    for structure in sorted(
        (item for item in structures if item.parent_id is None),
        key=lambda item: (item.start_index, item.start_line),
    ):
        if structure.start_index < cursor:
            continue

        if structure.start_index > cursor:
            chunks.extend(_text_chunks(source, cursor, structure.start_index))

        chunks.extend(
            _structure_chunks(source, structure, children_of, budget)
        )
        cursor = max(cursor, structure.end_index)

    if cursor < len(source.data):
        chunks.extend(_text_chunks(source, cursor, len(source.data)))

    return chunks


def _structure_chunks(
    source, structure, children_of, budget: int
) -> list[dict]:
    data = source.data

    if _fits(data, structure.start_index, structure.end_index, budget):
        return [
            source.chunk(
                structure.start_index,
                structure.end_index,
                structure,
                SYMBOL_CHUNK,
            )
        ]

    parts = _split_span(
        data,
        structure.start_index,
        structure.end_index,
        _member_nodes(structure.node),
        0,
        budget,
    )
    nested = children_of.get(structure.id, [])
    chunks = []

    for part_index, (part_start, part_end) in enumerate(parts, start=1):
        chunk = source.chunk(
            part_start,
            part_end,
            structure,
            SYMBOL_PART_CHUNK,
            part_number=part_index,
            part_count=len(parts),
        )
        chunk["contains"] = [
            item.name
            for item in nested
            if part_start <= item.start_index < part_end
        ]
        chunks.append(chunk)

    return chunks


@dataclass
class _Source:
    """Byte-addressable source text shared by every chunk of one file."""

    file_path: str
    language: str | None
    text: str

    def __post_init__(self) -> None:
        self.data = self.text.encode("utf-8")
        self.line_starts = _line_starts(self.data)

    def chunk(
        self,
        start_index: int,
        end_index: int,
        structure=None,
        chunk_type: str = TEXT_CHUNK,
        part_number: int | None = None,
        part_count: int | None = None,
    ) -> dict:
        content = self.data[start_index:end_index].decode("utf-8", "replace")
        start_line = bisect_right(self.line_starts, start_index)
        last = max(start_index, end_index - 1)
        end_line = bisect_right(self.line_starts, last)

        chunk = {
            "file_path": self.file_path,
            "chunk_id": f"{self.file_path}@{start_line}-{end_line}",
            "chunk_type": chunk_type,
            "language": self.language,
            "symbol": structure.name if structure is not None else None,
            "symbol_type": structure.symbol_type if structure is not None else None,
            "parent_symbol": (
                structure.parent_symbol if structure is not None else None
            ),
            "json_path": structure.json_path if structure is not None else None,
            "start_line": start_line,
            "end_line": end_line,
            "start_index": start_index,
            "end_index": end_index,
            "characters": len(content),
            "content": content,
            "estimated_tokens": estimate_text_tokens(content),
        }

        if structure is not None:
            chunk["structure_id"] = structure.id
            chunk["exported"] = structure.exported

        if part_number is not None:
            chunk["part_number"] = part_number
            chunk["part_count"] = part_count

        return chunk


def _text_chunks(
    source: _Source, start_index: int, end_index: int
) -> list[dict]:
    """Split a byte range by size, cutting on line ends and overlapping."""
    data = source.data
    budget = text_chunk_characters()
    overlap = text_chunk_overlap_characters()
    end = min(end_index, len(data))
    chunks = []
    start = start_index

    while start < end:
        limit = _char_boundary(data, min(end, start + budget), end)
        cut = _line_end_before(data, start, limit)
        if cut <= start:
            cut = min(start + 1, end)

        content = data[start:cut].decode("utf-8", "replace")
        if content.strip():
            chunks.append(source.chunk(start, cut))

        if cut >= end:
            break

        if overlap:
            restart = _next_line_start(source.line_starts, cut - overlap)
            start = cut if restart <= start else min(restart, cut)
        else:
            start = cut

    return chunks


def _split_span(
    data: bytes, span_start, span_end, children, depth: int, budget: int
):
    """Cut a symbol at inner syntax boundaries, keeping parts contiguous."""
    if _fits(data, span_start, span_end, budget):
        return [(span_start, span_end)]

    if not children or depth >= MAX_SPLIT_DEPTH:
        return _split_by_size(data, span_start, span_end, budget)

    groups = []
    part_start = span_start
    boundary = span_start
    members: list = []

    for child in children:
        child_end = int(child.end_byte)
        if child_end <= boundary:
            continue

        if members and not _fits(data, part_start, child_end, budget):
            groups.append((part_start, boundary, members))
            part_start = boundary
            members = []

        members.append(child)
        boundary = child_end

    groups.append((part_start, span_end, members))

    parts = []
    for group_start, group_end, group_members in groups:
        if _fits(data, group_start, group_end, budget):
            parts.append((group_start, group_end))
        elif len(group_members) == 1:
            parts.extend(
                _split_span(
                    data,
                    group_start,
                    group_end,
                    _member_nodes(group_members[0]),
                    depth + 1,
                    budget,
                )
            )
        else:
            parts.extend(_split_by_size(data, group_start, group_end, budget))

    return parts


def _split_by_size(data: bytes, start: int, end: int, budget: int):
    parts = []
    cursor = start

    while cursor < end:
        limit = _char_boundary(data, min(end, cursor + budget), end)
        cut = _line_end_before(data, cursor, limit)
        if cut <= cursor:
            cut = min(end, cursor + 1)
        parts.append((cursor, cut))
        cursor = cut

    return parts


def _fits(data: bytes, start: int, end: int, budget: int) -> bool:
    return end - start <= budget


def _member_nodes(node):
    """Return the nodes a span can be cut after, keeping keys with values."""
    if node is None:
        return []

    body = _field_node(node, "body") or node

    try:
        children = list(body.named_children)
    except AttributeError:
        children = [child for child in body.children if child.is_named]

    members = []
    for child in children:
        if child.end_byte <= child.start_byte:
            continue

        if child.type == "pair":
            value = _field_node(child, "value")
            if value is None or value.end_byte <= value.start_byte:
                continue
            members.append(value)
        else:
            members.append(child)

    return members


def _field_node(node, field_name: str):
    try:
        return node.child_by_field_name(field_name)
    except Exception:
        return None


def _line_starts(data: bytes) -> list[int]:
    starts = [0]
    index = data.find(b"\n")

    while index != -1:
        starts.append(index + 1)
        index = data.find(b"\n", index + 1)

    return starts


def _line_end_before(data: bytes, start: int, limit: int) -> int:
    """End the span at the last line break in the window, or at the window."""
    newline = data.rfind(b"\n", start + 1, limit)
    return newline + 1 if newline != -1 else limit


def _next_line_start(line_starts: list[int], index: int) -> int:
    position = bisect_left(line_starts, index)
    if position >= len(line_starts):
        return index
    return line_starts[position]


def _char_boundary(data: bytes, index: int, end: int) -> int:
    """Step back so a hard split never cuts a multi-byte character."""
    while 0 < index < end and (data[index] & 0xC0) == 0x80:
        index -= 1
    return index
