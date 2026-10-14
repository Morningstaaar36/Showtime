"""Static pre-check for scenario scripts, run again inside the sandbox before any script.

Same rules as `api/core/scripts.py` (a parity test keeps them in step). Stdlib only: this
file is copied into the simulation image.
"""

from __future__ import annotations

import ast

MAX_SCRIPT_CHARS = 8000
ALLOWED_IMPORTS = ("math", "statistics", "random")
FORBIDDEN_NAMES = frozenset(
    {
        "open",
        "exec",
        "eval",
        "compile",
        "__import__",
        "globals",
        "locals",
        "getattr",
        "setattr",
        "delattr",
        "vars",
        "dir",
        "input",
        "breakpoint",
        "help",
        "exit",
        "quit",
        "memoryview",
        "type",
        "object",
        "super",
    }
)
# attributes that reach interpreter internals without a dunder (frames, code, generators)
FORBIDDEN_ATTRS = frozenset({"format", "format_map", "mro"})
FORBIDDEN_ATTR_PREFIXES = ("_", "gi_", "cr_", "ag_", "f_", "tb_", "co_")
FORBIDDEN_NODES: dict[type[ast.AST], str] = {
    ast.Try: "try/except",
    ast.With: "with",
    ast.AsyncWith: "async with",
    ast.AsyncFunctionDef: "async def",
    ast.AsyncFor: "async for",
    ast.Await: "await",
}
if hasattr(ast, "TryStar"):
    FORBIDDEN_NODES[ast.TryStar] = "try/except*"


def check_script(code: str) -> list[str]:
    """Problems that stop a scenario script from being used; [] means it may run."""
    if len(code) > MAX_SCRIPT_CHARS:
        return [f"The script is longer than {MAX_SCRIPT_CHARS} characters."]
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        return [f"Python syntax error on line {exc.lineno}: {exc.msg}."]
    problems: list[str] = []

    def add(p: str) -> None:
        if p not in problems:
            problems.append(p)

    for node in ast.walk(tree):
        line = getattr(node, "lineno", "?")
        for kind, label in FORBIDDEN_NODES.items():
            if isinstance(node, kind):
                add(f"Line {line}: '{label}' is not allowed in scenario scripts.")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in ALLOWED_IMPORTS or "." in alias.name:
                    add(
                        f"Line {line}: import of '{alias.name}' is not allowed "
                        f"(only {', '.join(ALLOWED_IMPORTS)})."
                    )
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level or mod not in ALLOWED_IMPORTS:
                add(
                    f"Line {line}: import from '{mod or '.'}' is not allowed "
                    f"(only {', '.join(ALLOWED_IMPORTS)})."
                )
            if any(a.name == "*" for a in node.names):
                add(f"Line {line}: 'import *' is not allowed.")
            for a in node.names:
                if a.name.startswith("_"):
                    add(f"Line {line}: importing private name '{a.name}' is not allowed.")
        elif isinstance(node, ast.Name):
            if node.id.startswith("__"):
                add(f"Line {line}: name '{node.id}' is not allowed (no dunder names).")
            elif node.id in FORBIDDEN_NAMES:
                add(f"Line {line}: '{node.id}' is not allowed in scenario scripts.")
        elif isinstance(node, ast.Attribute):
            attr = node.attr
            if attr.startswith("__"):
                add(f"Line {line}: attribute '{attr}' is not allowed (no dunder attributes).")
            elif attr in FORBIDDEN_ATTRS or attr.startswith(FORBIDDEN_ATTR_PREFIXES):
                add(f"Line {line}: attribute '{attr}' is not allowed in scenario scripts.")
        elif isinstance(node, ast.FunctionDef | ast.ClassDef):
            if node.name.startswith("__"):
                add(f"Line {line}: name '{node.name}' is not allowed (no dunder names).")
        elif isinstance(node, ast.arg) and node.arg.startswith("__"):
            add(f"Line {line}: name '{node.arg}' is not allowed (no dunder names).")
        elif isinstance(node, ast.alias) and (node.asname or "").startswith("__"):
            add(f"Line {line}: name '{node.asname}' is not allowed (no dunder names).")

    on_step = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "on_step"]
    if not on_step:
        add("The script must define on_step(view, act).")
    else:
        args = on_step[-1].args
        if len(args.posonlyargs) + len(args.args) != 2 or args.vararg or args.kwonlyargs:
            add("on_step must take exactly two arguments: on_step(view, act).")
    return problems[:12]
