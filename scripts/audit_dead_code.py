#!/usr/bin/env python3
"""One-off AST scan of backend/ — lists every top-level def/class with its file:line."""
import ast
from pathlib import Path

ROOT = Path("backend")
EXCLUDES = {".venv", "__pycache__", "tests"}

results = []
for p in ROOT.rglob("*.py"):
    if any(part in EXCLUDES for part in p.parts):
        continue
    try:
        tree = ast.parse(p.read_text())
    except SyntaxError:
        print(f"SYNTAX_ERROR\t{p}")
        continue
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # Skip dunder methods
            if node.name.startswith("__") and node.name.endswith("__"):
                continue
            if node.name.startswith("_") and not isinstance(node, ast.ClassDef):
                kind = "private_fn"
            elif isinstance(node, ast.ClassDef):
                kind = "class"
            else:
                kind = "public_fn"
            results.append({
                "kind": kind,
                "name": node.name,
                "file": str(p.relative_to(".")),
                "line": node.lineno,
            })

print(f"# Total: {len(results)}")
for r in sorted(results, key=lambda r: (r["file"], r["line"])):
    print(f"{r['kind']}\t{r['name']}\t{r['file']}:{r['line']}")
