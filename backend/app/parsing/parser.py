"""Turn source text into a Tree-sitter syntax tree."""

from bisect import bisect_right
from dataclasses import dataclass, field

from app.parsing.grammars import language_for_path, parser_for


MAX_PARSE_BYTES = 512 * 1024
MAX_TREE_NODES = 20000
MAX_TREE_DEPTH = 32
MAX_ERROR_ENTRIES = 50
PREVIEW_LENGTH = 90


class ParseFailedError(Exception):
    pass


@dataclass
class ParsedFile:
    file_path: str
    language: str
    source_bytes: bytes
    root: object
    errors: list[dict] = field(default_factory=list)
    node_count: int = 0
    truncated_after_line: int | None = None
    line_starts: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        starts = [0]
        offset = self.source_bytes.find(b"\n")

        while offset != -1:
            offset += 1
            starts.append(offset)
            offset = self.source_bytes.find(b"\n", offset)

        self.line_starts = starts

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    def node_text(self, node) -> str:
        return self.span_text(int(node.start_byte), int(node.end_byte))

    def span_text(self, start_index: int, end_index: int) -> str:
        return self.source_bytes[start_index:end_index].decode("utf-8", "replace")

    def start_line(self, node) -> int:
        return bisect_right(self.line_starts, int(node.start_byte))

    def end_line(self, node) -> int:
        start_byte = int(node.start_byte)
        last_byte = max(start_byte, int(node.end_byte) - 1)
        return bisect_right(self.line_starts, last_byte)

    def serialize_tree(self) -> tuple[list[dict], bool]:
        """Return the child lists of the root node plus a truncation flag."""
        remaining = MAX_TREE_NODES
        truncated = False

        def visit(node, depth: int) -> dict:
            nonlocal remaining, truncated

            children = []
            if depth < MAX_TREE_DEPTH:
                for child in node.children:
                    if remaining <= 0:
                        truncated = True
                        break
                    remaining -= 1
                    children.append(visit(child, depth + 1))

            preview = self.node_text(node).split("\n", 1)[0].strip()
            if len(preview) > PREVIEW_LENGTH:
                preview = f"{preview[:PREVIEW_LENGTH]}…"

            return {
                "type": node.type,
                "start_line": self.start_line(node),
                "end_line": self.end_line(node),
                "named": bool(node.is_named),
                "has_error": bool(node.has_error),
                "child_count": len(children),
                "preview": preview,
                "children": children,
            }

        branches = []
        for child in self.root.children:
            if remaining <= 0:
                truncated = True
                break
            remaining -= 1
            branches.append(visit(child, 1))

        return branches, truncated


def parse_source(file_path: str, source: str) -> ParsedFile | None:
    """Parse a supported file. Returns None when Tree-sitter cannot help."""
    language = language_for_path(file_path)
    if language is None:
        return None

    source_bytes = source.encode("utf-8")
    truncated = len(source_bytes) > MAX_PARSE_BYTES

    if truncated:
        cut = source_bytes.rfind(b"\n", 0, MAX_PARSE_BYTES)
        if cut == -1:
            return None
        parse_bytes = source_bytes[:cut]
        truncated_after_line = parse_bytes.count(b"\n") + 1
    else:
        parse_bytes = source_bytes
        truncated_after_line = None

    try:
        parser = parser_for(language)
        if parser is None:
            return None
        tree = parser.parse(parse_bytes)
    except Exception as exc:
        raise ParseFailedError(str(exc)) from exc

    parsed = ParsedFile(
        file_path=file_path,
        language=language,
        source_bytes=parse_bytes,
        root=tree.root_node,
        truncated_after_line=truncated_after_line,
    )
    parsed.errors = _collect_errors(parsed)
    parsed.node_count = _count_nodes(parsed)
    return parsed


def _collect_errors(parsed: ParsedFile) -> list[dict]:
    """Record ERROR and MISSING nodes so a broken file still reports context."""
    errors = []
    stack = [parsed.root]

    while stack and len(errors) < MAX_ERROR_ENTRIES:
        node = stack.pop()

        if node.type == "ERROR" or node.is_missing:
            snippet = parsed.node_text(node).split("\n", 1)[0].strip()
            errors.append(
                {
                    "node_type": node.type,
                    "start_line": parsed.start_line(node),
                    "end_line": parsed.end_line(node),
                    "preview": snippet[:PREVIEW_LENGTH],
                }
            )
            continue

        stack.extend(node.children)

    return errors


def _count_nodes(parsed: ParsedFile) -> int:
    count = 0
    stack = [parsed.root]

    while stack:
        node = stack.pop()
        count += 1
        if count >= MAX_TREE_NODES:
            break
        stack.extend(node.children)

    return count
