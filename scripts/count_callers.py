#!/usr/bin/env python3
"""For each (name, file) in /tmp/a9_all_defs.tsv, count caller hits in backend/ + frontend/ + scripts/."""
import subprocess
from pathlib import Path

defs: list[tuple[str, str, str, int]] = []
with open("/tmp/a9_all_defs.tsv") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        kind, name, fileln = parts
        fname, lnum = fileln.rsplit(":", 1)
        defs.append((kind, name, fname, int(lnum)))

print(f"# Counting callers for {len(defs)} definitions...")

for kind, name, file, lineno in defs:
    # Count uses across the codebase (excluding the definition line itself)
    cmd = [
        "grep", "-rn",
        f"\\b{name}\\b",
        "backend/", "frontend/src/", "scripts/",
        "--include=*.py", "--include=*.js", "--include=*.jsx", "--include=*.ts", "--include=*.tsx",
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        print(f"TIMEOUT\t{kind}\t{name}\t{file}:{lineno}")
        continue
    lines = out.stdout.strip().split("\n") if out.stdout.strip() else []
    # Exclude the definition itself
    def_line_marker = f"{file}:{lineno}:"
    callers = [ln for ln in lines if not ln.startswith(def_line_marker) and ln]
    n_calls: int = len(callers)
    print(f"{n_calls}\t{kind}\t{name}\t{file}:{lineno}")
