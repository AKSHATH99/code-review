"""Extract named JavaScript/TypeScript structures from a parsed file."""

from dataclasses import dataclass

from app.parsing.parser import ParsedFile

FUNCTION_NODE_TYPES = {
    "function_declaration",
    "generator_function_declaration",
    "function_expression",
    "function",
    "arrow_function",
}
NAMED_FUNCTION_NODE_TYPES = {
    "function_declaration": "function",
    "generator_function_declaration": "generator_function",
    "function_expression": "function",
    "function": "function",
}
CLASS_NODE_TYPES = {
    "class_declaration",
    "class",
    "abstract_class_declaration",
}
METHOD_NODE_TYPES = {"method_definition"}
TYPE_NODE_TYPES = {
    "interface_declaration": "interface",
    "type_alias_declaration": "type_alias",
    "enum_declaration": "enum",
}
NAME_HOST_NODE_TYPES = {
    "variable_declarator",
    "public_field_definition",
    "property_signature",
    "assignment_expression",
    "assignment_pattern",
    "pair",
}
COLLECTION_NODE_TYPES = {"array": "data_array", "object": "data_object"}
DECLARATION_WRAPPER_NODE_TYPES = {
    "export_statement",
    "lexical_declaration",
    "variable_declaration",
    "expression_statement",
}
JSX_PREFIX = "jsx_"
MAX_JSX_SCAN = 20000


@dataclass
class Structure:
    id: str
    name: str
    symbol_type: str
    language: str
    file_path: str
    start_line: int
    end_line: int
    start_index: int
    end_index: int
    source_code: str
    parent_id: str | None = None
    parent_symbol: str | None = None
    exported: bool = False
    json_path: str | None = None
    node: object = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "symbol_type": self.symbol_type,
            "language": self.language,
            "file_path": self.file_path,
            "parent_id": self.parent_id,
            "parent_symbol": self.parent_symbol,
            "exported": self.exported,
            "json_path": self.json_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "start_index": self.start_index,
            "end_index": self.end_index,
            "characters": len(self.source_code),
            "source_code": self.source_code,
        }


def extract_structures(parsed: ParsedFile) -> list[Structure]:
    structures: list[Structure] = []
    _walk(parsed, parsed.root, None, structures, exported=False)
    return structures


def _walk(parsed, node, parent, out, exported: bool) -> None:
    for child in node.children:
        _visit(parsed, child, parent, out, exported)


def _visit(parsed, node, parent, out, exported: bool) -> None:
    node_type = node.type

    if node_type in CLASS_NODE_TYPES:
        structure = _add(parsed, node, "class", parent, out, exported)
        _walk(parsed, node, structure, out, exported)
        return

    if node_type in METHOD_NODE_TYPES:
        structure = _add(parsed, node, "method", parent, out, exported)
        _walk(parsed, node, structure, out, exported)
        return

    if node_type in NAMED_FUNCTION_NODE_TYPES:
        name_node = _named_child(node, "name")
        if name_node is None:
            _walk(parsed, node, parent, out, exported)
            return

        structure = _add(
            parsed,
            node,
            NAMED_FUNCTION_NODE_TYPES[node_type],
            parent,
            out,
            exported,
            name_node=name_node,
        )
        _walk(parsed, node, structure, out, exported)
        return

    if node_type in FUNCTION_NODE_TYPES:
        # Unnamed callbacks belong to the chunk of their enclosing structure,
        # so they are not listed as standalone symbols.
        _walk(parsed, node, parent, out, exported)
        return

    if node_type in TYPE_NODE_TYPES:
        _add(parsed, node, TYPE_NODE_TYPES[node_type], parent, out, exported)
        return

    if node_type == "export_statement":
        _walk(parsed, node, parent, out, True)
        return

    if node_type in NAME_HOST_NODE_TYPES:
        value = _named_child(node, "value")
        declared = (
            _named_child(node, "left")
            or _named_child(node, "name")
            or _named_child(node, "key")
        )

        if value is not None and value.type in FUNCTION_NODE_TYPES:
            kind = "arrow_function" if value.type == "arrow_function" else "function"
            structure = _add(
                parsed,
                value,
                kind,
                parent,
                out,
                exported,
                name_node=declared,
                span_node=_statement_span(node),
            )
            _walk(parsed, value, structure, out, exported)
            return

        if value is not None and value.type in CLASS_NODE_TYPES:
            structure = _add(
                parsed,
                value,
                "class",
                parent,
                out,
                exported,
                name_node=declared,
                span_node=_statement_span(node),
            )
            _walk(parsed, value, structure, out, exported)
            return

        if value is not None and value.type in COLLECTION_NODE_TYPES:
            # Data files (project lists, configs, catalogs) are the payload a
            # question asks about, so the declaration stays glued to the value
            # and an oversized collection splits on its own element borders.
            structure = _add(
                parsed,
                value,
                COLLECTION_NODE_TYPES[value.type],
                parent,
                out,
                exported,
                name_node=declared,
                span_node=_statement_span(node),
            )
            _walk(parsed, value, structure, out, exported)
            return

    _walk(parsed, node, parent, out, exported)


def _statement_span(node):
    """Widen a structure to its whole statement when the statement is only it.

    `export const projects = [...]` otherwise loses `export const` to a
    leftover gap chunk, and the keywords are what make the data readable.
    """
    span = node

    while True:
        parent = span.parent

        if parent is None or parent.type not in DECLARATION_WRAPPER_NODE_TYPES:
            return span
        if len(list(parent.named_children)) != 1:
            return span

        span = parent


def _add(
    parsed,
    node,
    kind: str,
    parent,
    out,
    exported: bool,
    name_node=None,
    span_node=None,
) -> Structure:
    name = _text(parsed, name_node) or _text(parsed, _named_child(node, "name"))
    name = name or f"<anonymous {kind}>"

    if kind in {"function", "arrow_function", "method", "class"} and _is_pascal_case(
        name
    ):
        if _contains_jsx(node):
            kind = "react_component"

    span = span_node if span_node is not None else _statement_span(node)

    structure = Structure(
        id=f"s{len(out)}",
        name=name,
        symbol_type=kind,
        language=parsed.language,
        file_path=parsed.file_path,
        start_line=parsed.start_line(span),
        end_line=parsed.end_line(span),
        start_index=int(span.start_byte),
        end_index=int(span.end_byte),
        source_code=parsed.span_text(
            int(span.start_byte), int(span.end_byte)
        ),
        parent_id=parent.id if parent is not None else None,
        parent_symbol=parent.name if parent is not None else None,
        exported=exported,
        node=node,
    )
    out.append(structure)
    return structure


def _named_child(node, field_name: str):
    try:
        child = node.child_by_field_name(field_name)
    except Exception:
        return None
    return child if child is not None and child.is_named else None


def _text(parsed, node) -> str:
    if node is None:
        return ""
    return parsed.node_text(node).strip()


def _is_pascal_case(name: str) -> bool:
    return name[:1].isupper()


def _contains_jsx(node) -> bool:
    seen = 0
    stack = [node]

    while stack:
        current = stack.pop()
        seen += 1
        if seen > MAX_JSX_SCAN:
            return False
        if current.type.startswith(JSX_PREFIX):
            return True
        stack.extend(current.children)

    return False
