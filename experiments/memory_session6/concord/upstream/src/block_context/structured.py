from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StructuredObservation:
    kind: str
    content: str
    semantics: str = "whole_file"


def compute_observation(kind: str, object_id: str, content: str) -> StructuredObservation:
    if kind == "file-stats":
        return StructuredObservation(kind=kind, content=_file_stats(object_id, content))
    if kind == "python-symbols":
        return StructuredObservation(kind=kind, content=_python_symbols(object_id, content))
    if kind == "glob-listing":
        raise ValueError("glob-listing observations must be refreshed by re-running glob")
    raise ValueError(f"unsupported structured observation kind: {kind}")


def _file_stats(object_id: str, content: str) -> str:
    payload = {
        "kind": "file-stats",
        "object_id": object_id,
        "sha256": hashlib.sha256(content.encode()).hexdigest(),
        "line_count": len(content.splitlines()),
        "char_count": len(content),
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _python_symbols(object_id: str, content: str) -> str:
    try:
        tree = ast.parse(content, filename=object_id)
    except SyntaxError as exc:
        payload = {
            "kind": "python-symbols",
            "object_id": object_id,
            "parse_error": {
                "lineno": exc.lineno,
                "offset": exc.offset,
                "msg": exc.msg,
            },
            "symbols": [],
        }
        return json.dumps(payload, indent=2, sort_keys=True)

    symbols: list[dict[str, object]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            symbols.append({"type": "class", "name": node.name, "line": node.lineno})
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(
                {
                    "type": "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function",
                    "name": node.name,
                    "line": node.lineno,
                }
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                symbols.append({"type": "import", "name": alias.name, "line": node.lineno})
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                name = f"{module}.{alias.name}" if module else alias.name
                symbols.append({"type": "import_from", "name": name, "line": node.lineno})

    payload = {
        "kind": "python-symbols",
        "object_id": object_id,
        "symbols": sorted(symbols, key=lambda item: (int(item["line"]), str(item["type"]), str(item["name"]))),
    }
    return json.dumps(payload, indent=2, sort_keys=True)
