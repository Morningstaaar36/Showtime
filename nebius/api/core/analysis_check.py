"""Pre-check for analysis scripts (AI- or user-written) before they go to a sandbox.

A quality filter, not the security boundary: the sandbox (no network, non-root, read-only
inputs, caps, wall timeout) is. It rejects what an analysis never needs, in plain words:
imports outside the allow-list, dunder names, dynamic code and attribute tricks, file I/O
helpers, and anything over 8 KB.
"""

from __future__ import annotations

import ast

MAX_BYTES = 8 * 1024
ALLOWED_IMPORTS = frozenset({"math", "statistics", "json", "numpy", "pandas", "showtime_data"})
FORBIDDEN_NAMES = frozenset(
    {
        "open",
        "exec",
        "eval",
        "compile",
        "__import__",
        "getattr",
        "setattr",
        "delattr",
        "globals",
        "locals",
        "vars",
        "input",
        "breakpoint",
        "memoryview",
        "help",
        "exit",
        "quit",
    }
)
# numpy/pandas helpers that read or write files (the data comes from showtime_data only)
FORBIDDEN_ATTRS = frozenset(
    {
        "load",
        "loadtxt",
        "save",
        "savez",
        "savez_compressed",
        "savetxt",
        "fromfile",
        "tofile",
        "memmap",
        "genfromtxt",
        "fromregex",
        "to_pickle",
        "to_csv",
        "to_parquet",
        "to_hdf",
        "to_sql",
        "to_excel",
        "to_feather",
        "to_stata",
        "to_orc",
        "to_clipboard",
        "system",
        "popen",
    }
)
MAX_PROBLEMS = 8


def _dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__") and len(name) > 4


def check_analysis(code: str) -> list[str]:
    """Problems with an analysis script, in plain words (empty list = it may run)."""
    size = len(code.encode())
    if size > MAX_BYTES:
        return [f"The script is {size} bytes; the limit is {MAX_BYTES} (8 KB)."]
    if not code.strip():
        return ["The script is empty."]
    try:
        tree = ast.parse(code, filename="script.py")
    except SyntaxError as exc:
        return [f"Syntax error on line {exc.lineno}: {exc.msg}."]
    problems: list[str] = []

    def add(msg: str) -> None:
        if msg not in problems:
            problems.append(msg)

    allowed = ", ".join(sorted(ALLOWED_IMPORTS))
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top not in ALLOWED_IMPORTS:
                    add(f"Line {line}: importing {alias.name!r} is not allowed (only {allowed}).")
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if node.level or top not in ALLOWED_IMPORTS:
                add(f"Line {line}: importing from {node.module!r} is not allowed (only {allowed}).")
            for alias in node.names:
                if alias.name == "*":
                    add(f"Line {line}: 'import *' is not allowed; import names one by one.")
                elif _dunder(alias.name):
                    add(f"Line {line}: names with double underscores are not allowed.")
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_NAMES:
                add(f"Line {line}: {node.id}() is not allowed in an analysis script.")
            elif _dunder(node.id):
                add(f"Line {line}: names with double underscores ({node.id}) are not allowed.")
        elif isinstance(node, ast.Attribute):
            if _dunder(node.attr) or node.attr.startswith("__"):
                add(f"Line {line}: attributes with double underscores are not allowed.")
            elif node.attr in FORBIDDEN_ATTRS or node.attr.startswith("read_"):
                add(
                    f"Line {line}: .{node.attr}() reads or writes files; "
                    "use the showtime_data helpers for the run's data."
                )
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            if _dunder(node.name):
                add(f"Line {line}: names with double underscores are not allowed.")
        elif isinstance(node, ast.arg):
            if _dunder(node.arg):
                add(f"Line {line}: names with double underscores are not allowed.")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "__" in node.value and any(_dunder(w) for w in node.value.replace(".", " ").split()):
                add(f"Line {line}: text with double-underscore names is not allowed.")
        elif isinstance(node, ast.Global | ast.Nonlocal):
            add(f"Line {line}: global and nonlocal are not allowed.")
        if len(problems) >= MAX_PROBLEMS:
            break
    return problems
