"""Extract JSON objects and arrays as chunkable structures.

JSON has no symbols, so a structure here is a container value plus the path
that locates it in the document. A container stored under a key takes the
whole pair, so its chunks always carry `"key": ` alongside the value.
"""

from app.parsing.parser import ParsedFile
from app.parsing.structures import Structure

JSON_LANGUAGE = "json"
CONTAINER_NODE_TYPES = {"object", "array"}
ROOT_NAME = "(root)"
MISSING_KEY_NAME = "?"


def extract_json_structures(parsed: ParsedFile) -> list[Structure]:
    structures: list[Structure] = []

    for child in parsed.root.children:
        if child.type not in CONTAINER_NODE_TYPES:
            continue
        structure = _add(parsed, child, None, ROOT_NAME, "", child, structures)
        _visit_members(parsed, child, structure, structures)

    return structures


def _visit_members(parsed, node, parent, out) -> None:
    if node.type == "object":
        _visit_pairs(parsed, node, parent, out)
    else:
        _visit_elements(parsed, node, parent, out)


def _visit_pairs(parsed, node, parent, out) -> None:
    for pair in node.children:
        if pair.type != "pair":
            continue

        value = _field(pair, "value")
        if value is None or value.type not in CONTAINER_NODE_TYPES:
            continue

        name = _key_name(parsed, _field(pair, "key"))
        structure = _add(
            parsed,
            value,
            parent,
            name,
            _child_path(parent.json_path, name),
            pair,
            out,
        )
        _visit_members(parsed, value, structure, out)


def _visit_elements(parsed, node, parent, out) -> None:
    index = 0

    for element in node.children:
        if not element.is_named:
            continue

        if element.type in CONTAINER_NODE_TYPES:
            name = f"[{index}]"
            structure = _add(
                parsed,
                element,
                parent,
                name,
                f"{parent.json_path}{name}",
                element,
                out,
            )
            _visit_members(parsed, element, structure, out)

        index += 1


def _add(
    parsed, value_node, parent, name, json_path, span_node, out
) -> Structure:
    start_index = int(span_node.start_byte)
    end_index = int(value_node.end_byte)

    structure = Structure(
        id=f"j{len(out)}",
        name=name,
        symbol_type=value_node.type,
        language=parsed.language,
        file_path=parsed.file_path,
        start_line=parsed.start_line(span_node),
        end_line=parsed.end_line(value_node),
        start_index=start_index,
        end_index=end_index,
        source_code=parsed.span_text(start_index, end_index),
        parent_id=parent.id if parent is not None else None,
        parent_symbol=parent.name if parent is not None else None,
        json_path=json_path,
        node=value_node,
    )
    out.append(structure)
    return structure


def _child_path(parent_path: str, key: str) -> str:
    return f"{parent_path}.{key}" if parent_path else key


def _key_name(parsed, key_node) -> str:
    if key_node is None:
        return MISSING_KEY_NAME
    return parsed.node_text(key_node).strip().strip('"') or MISSING_KEY_NAME


def _field(node, field_name: str):
    try:
        return node.child_by_field_name(field_name)
    except Exception:
        return None
