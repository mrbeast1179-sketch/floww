#!/usr/bin/env python3
"""
backend/services/code_suggester.py — Memory-driven code suggestions.

When coding, suggests patterns from memory. Example:
"Use Numba here, as done in Agent 5's GEX calc."

This service:
1. Monitors code being written (via AST analysis or IDE integration)
2. Searches mem0 for relevant patterns
3. Suggests improvements based on past decisions and cross-project learnings
4. Logs suggestions for review

Usage:
    # As a service (called by other modules):
    from services.code_suggester import CodeSuggester
    suggester = CodeSuggester()
    suggestions = suggester.analyze_file("backend/services/my_new_service.py")

    # CLI:
    python3 backend/services/code_suggester.py <filepath>
    python3 backend/services/code_suggester.py --query "How to calculate GEX"
    python3 backend/services/code_suggester.py --log  # show suggestion log
"""

import ast
import json
import logging
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field, asdict

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

SUGGESTION_LOG_PATH = REPO_ROOT / "reports" / "code_suggestions.jsonl"


# ─── Data Structures ─────────────────────────────────────────────

@dataclass
class CodeSuggestion:
    """A single code suggestion from memory."""
    suggestion_id: str
    timestamp: str
    target_file: str
    target_line: int
    category: str          # performance, architecture, risk, testing, style
    title: str
    description: str
    source_memory: str     # What memory triggered this
    source_project: str    # floww, swarmSPX, gflows, etc.
    confidence: float      # 0.0 - 1.0
    suggested_code: str = ""
    reference_file: str = ""
    reference_line: int = 0
    applied: bool = False
    dismissed: bool = False


# ─── Pattern Detectors ───────────────────────────────────────────

class PatternDetector:
    """Detects code patterns that have known better alternatives in memory."""

    # Pattern: (detector_func, suggestion_template)
    PATTERNS = []

    @staticmethod
    def detect_pure_python_math(tree: ast.AST, source: str) -> List[dict]:
        """Detect pure Python math that could use Numba."""
        findings = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                func_source = ast.get_source_segment(source, node) or ""
                # Check for math-heavy functions without Numba
                has_math = any(
                    isinstance(n, (ast.BinOp, ast.Call))
                    for n in ast.walk(node)
                )
                has_numba = "numba" in func_source.lower()
                has_loop = any(
                    isinstance(n, (ast.For, ast.While))
                    for n in ast.walk(node)
                )
                if has_math and has_loop and not has_numba:
                    findings.append({
                        "type": "performance",
                        "line": node.lineno,
                        "title": "Consider Numba JIT compilation",
                        "description": (
                            f"Function '{node.name}' (line {node.lineno}) contains "
                            f"math operations in a loop without Numba JIT. "
                            f"Agent 5's GEX calc showed 10x speedup with @numba.njit. "
                            f"See: backend/services/numba_greeks.py"
                        ),
                        "confidence": 0.8,
                        "suggested_code": (
                            f"from numba import njit\n\n"
                            f"@njit\n"
                            f"def {node.name}(...):\n"
                            f"    ..."
                        ),
                        "reference_file": "backend/services/numba_greeks.py",
                    })
        return findings

    @staticmethod
    def detect_inline_risk_checks(tree: ast.AST, source: str) -> List[dict]:
        """Detect inline risk checks that should be in a dedicated gate module."""
        findings = []
        risk_keywords = ["position_size", "account_equity", "max_qty", "max_premium",
                        "kyle_lambda", "sentiment_z"]
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                func_source = ast.get_source_segment(source, node) or ""
                risk_count = sum(1 for kw in risk_keywords if kw in func_source.lower())
                if risk_count >= 2:
                    findings.append({
                        "type": "architecture",
                        "line": node.lineno,
                        "title": "Extract risk gate to dedicated module",
                        "description": (
                            f"Line {node.lineno}: Multiple risk checks ({risk_count}) "
                            f"found inline. swarmSPX uses a dedicated risk/gate.py module. "
                            f"Consider extracting to backend/services/risk/gate.py "
                            f"for better testability and reuse."
                        ),
                        "confidence": 0.7,
                        "reference_file": "backend/services/signal_translator.py",
                    })
        return findings

    @staticmethod
    def detect_missing_async(tree: ast.AST, source: str) -> List[dict]:
        """Detect synchronous I/O that should be async."""
        findings = []
        sync_io_patterns = ["requests.get", "requests.post", "time.sleep",
                          "urllib", "httpx.get", "httpx.post"]
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_source = ast.get_source_segment(source, node) or ""
                for pattern in sync_io_patterns:
                    if pattern in func_source:
                        findings.append({
                            "type": "performance",
                            "line": node.lineno,
                            "title": "Use async I/O",
                            "description": (
                                f"Line {node.lineno}: Synchronous I/O '{pattern}' detected. "
                                f"Project Oracle requires asyncio everywhere. "
                                f"Use aiohttp or httpx.AsyncClient instead."
                            ),
                            "confidence": 0.9,
                            "reference_file": "backend/services/websocket_streamer.py",
                        })
                        break
        return findings

    @staticmethod
    def detect_missing_tests(tree: ast.AST, source: str, filepath: str) -> List[dict]:
        """Detect functions without corresponding tests."""
        findings = []
        # Check if this is a service file
        if "services" not in filepath and "backend" not in filepath:
            return findings

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Skip private functions
                if node.name.startswith("_"):
                    continue
                # Check if function has docstring (indicates it's public API)
                has_docstring = (
                    isinstance(node.body[0], ast.Expr) and
                    isinstance(node.body[0].value, (ast.Constant, ast.Str))
                )
                if has_docstring:
                    findings.append({
                        "type": "testing",
                        "line": node.lineno,
                        "title": f"Ensure test coverage for '{node.name}'",
                        "description": (
                            f"Function '{node.name}' (line {node.lineno}) appears to be "
                            f"public API (has docstring). Ensure there's a corresponding "
                            f"test in backend/tests/. "
                            f"floww standard: every public function has ≥1 test."
                        ),
                        "confidence": 0.6,
                        "reference_file": "backend/tests/",
                    })
        return findings

    @staticmethod
    def detect_hardcoded_values(tree: ast.AST, source: str) -> List[dict]:
        """Detect hardcoded values that should be config."""
        findings = []
        suspicious_values = ["50000", "50", "0.5", "0.7", "1e-6", "5000", "0.01"]
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                val_str = str(node.value)
                if val_str in suspicious_values:
                    # Check if it's assigned to a variable (good) or used inline (bad)
                    parent_is_assign = False
                    for parent in ast.walk(tree):
                        if isinstance(parent, ast.Assign):
                            for target in parent.targets:
                                if isinstance(target, ast.Name):
                                    if hasattr(parent, 'lineno') and abs(parent.lineno - node.lineno) <= 1:
                                        parent_is_assign = True
                    if not parent_is_assign:
                        findings.append({
                            "type": "style",
                            "line": node.lineno,
                            "title": f"Hardcoded value {node.value}",
                            "description": (
                                f"Line {node.lineno}: Hardcoded value {node.value} detected. "
                                f"Consider extracting to a named constant or config parameter. "
                                f"Example: BUCKET_SIZE = 50000  # From vpin_engine.py"
                            ),
                            "confidence": 0.5,
                        })
        return findings


# ─── Mem0 Search Integration ─────────────────────────────────────

class MemorySearcher:
    """Search mem0 for relevant code patterns."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            cfg_path = Path.home() / ".mem0" / "config.json"
            if cfg_path.exists():
                try:
                    cfg = json.load(open(cfg_path))
                    api_key = cfg.get("platform", {}).get("api_key")
                    if api_key:
                        from mem0 import MemoryClient
                        self._client = MemoryClient(api_key=api_key)
                except Exception as e:
                    logger.debug("mem0 client init failed: %s", e)
        return self._client

    def search(self, query: str, limit: int = 5) -> List[dict]:
        """Search mem0 for relevant memories."""
        if not self.client:
            return []
        try:
            result = self.client.search(
                query=query,
                filters={"user_id": "user_c778280e23af"},
                limit=limit,
            )
            if isinstance(result, dict):
                return result.get("results", [])
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.debug("mem0 search failed: %s", e)
            return []

    def search_code_patterns(self, pattern_type: str) -> List[dict]:
        """Search for specific code pattern types."""
        type_queries = {
            "performance": "Numba JIT optimization performance",
            "architecture": "EventBus pipeline architecture pattern",
            "risk": "risk gate circuit breaker pattern",
            "testing": "test coverage pytest pattern",
            "ml": "ML model training pipeline",
            "gex": "GEX gamma exposure calculation",
            "vpin": "VPIN toxicity volume clock",
        }
        query = type_queries.get(pattern_type, pattern_type)
        return self.search(query)


# ─── Code Suggester Service ──────────────────────────────────────

class CodeSuggester:
    """Main service for memory-driven code suggestions."""

    def __init__(self):
        self.detector = PatternDetector()
        self.searcher = MemorySearcher()
        self.suggestions: List[CodeSuggestion] = []

    def analyze_file(self, filepath: str) -> List[CodeSuggestion]:
        """Analyze a Python file and generate suggestions."""
        path = Path(filepath)
        if not path.exists():
            logger.error("File not found: %s", filepath)
            return []

        try:
            source = path.read_text()
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as e:
            logger.error("Syntax error in %s: %s", filepath, e)
            return []

        rel_path = str(path.relative_to(REPO_ROOT)) if str(path).startswith(str(REPO_ROOT)) else str(path)
        suggestions = []

        # Run all detectors
        all_findings = []
        all_findings.extend(self.detector.detect_pure_python_math(tree, source))
        all_findings.extend(self.detector.detect_inline_risk_checks(tree, source))
        all_findings.extend(self.detector.detect_missing_async(tree, source))
        all_findings.extend(self.detector.detect_missing_tests(tree, source, rel_path))
        all_findings.extend(self.detector.detect_hardcoded_values(tree, source))

        # Enhance with mem0 search
        for finding in all_findings:
            mem_results = self.searcher.search_code_patterns(finding["type"])
            if mem_results:
                top = mem_results[0]
                finding["source_memory"] = top.get("memory", "")[:200]
                finding["source_project"] = top.get("metadata", {}).get("project", "floww")
            else:
                finding["source_memory"] = "Pattern detector (no mem0 match)"
                finding["source_project"] = "floww"

        # Convert to CodeSuggestion objects
        for i, finding in enumerate(all_findings):
            suggestion = CodeSuggestion(
                suggestion_id=f"{path.stem}_{finding['line']}_{i}",
                timestamp=datetime.now(timezone.utc).isoformat(),
                target_file=rel_path,
                target_line=finding["line"],
                category=finding["type"],
                title=finding["title"],
                description=finding["description"],
                source_memory=finding.get("source_memory", ""),
                source_project=finding.get("source_project", "floww"),
                confidence=finding.get("confidence", 0.5),
                suggested_code=finding.get("suggested_code", ""),
                reference_file=finding.get("reference_file", ""),
            )
            suggestions.append(suggestion)

        self.suggestions.extend(suggestions)
        return suggestions

    def query(self, query_text: str) -> List[dict]:
        """Query memory for code suggestions."""
        return self.searcher.search(query_text)

    def log_suggestions(self, suggestions: List[CodeSuggestion]):
        """Log suggestions to JSONL file."""
        SUGGESTION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SUGGESTION_LOG_PATH, "a") as f:
            for s in suggestions:
                f.write(json.dumps(asdict(s)) + "\n")

    def get_log(self, limit: int = 50) -> List[dict]:
        """Read suggestion log."""
        if not SUGGESTION_LOG_PATH.exists():
            return []
        lines = SUGGESTION_LOG_PATH.read_text().strip().split("\n")
        entries = []
        for line in lines[-limit:]:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return entries

    def format_suggestions(self, suggestions: List[CodeSuggestion]) -> str:
        """Format suggestions for display."""
        if not suggestions:
            return "No suggestions."

        lines = ["# Code Suggestions from Memory\n"]
        for s in suggestions:
            confidence_bar = "█" * int(s.confidence * 10) + "░" * (10 - int(s.confidence * 10))
            lines.append(f"## {s.title}")
            lines.append(f"**File:** `{s.target_file}:{s.target_line}`")
            lines.append(f"**Category:** {s.category} | **Confidence:** [{confidence_bar}] {s.confidence:.0%}")
            lines.append(f"**Source:** {s.source_project}")
            lines.append("")
            lines.append(s.description)
            if s.suggested_code:
                lines.append("")
                lines.append("```python")
                lines.append(s.suggested_code)
                lines.append("```")
            if s.reference_file:
                lines.append("")
                lines.append(f"**Reference:** `{s.reference_file}`")
            lines.append("")

        return "\n".join(lines)


# ─── CLI ─────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Memory-driven code suggestions")
    parser.add_argument("filepath", nargs="?", help="Python file to analyze")
    parser.add_argument("--query", "-q", help="Query memory for suggestions")
    parser.add_argument("--log", action="store_true", help="Show suggestion log")
    parser.add_argument("--limit", type=int, default=20, help="Max results")
    args = parser.parse_args()

    suggester = CodeSuggester()

    if args.log:
        entries = suggester.get_log(limit=args.limit)
        if entries:
            print(f"Last {len(entries)} suggestions:")
            for entry in entries:
                print(f"  [{entry['category']}] {entry['title']} — {entry['target_file']}:{entry['target_line']}")
        else:
            print("No suggestions logged yet.")
        return

    if args.query:
        results = suggester.query(args.query)
        if results:
            print(f"Memory results for '{args.query}':")
            for r in results:
                mem = r.get("memory", "")
                score = r.get("score", 0)
                print(f"  (score={score:.3f}) {mem[:120]}")
        else:
            print(f"No memory results for '{args.query}'")
        return

    if args.filepath:
        suggestions = suggester.analyze_file(args.filepath)
        if suggestions:
            print(suggester.format_suggestions(suggestions))
            suggester.log_suggestions(suggestions)
            logger.info(f"Logged {len(suggestions)} suggestions")
        else:
            print(f"No suggestions for {args.filepath}")
        return

    # Default: analyze a demo file
    demo_file = REPO_ROOT / "backend" / "services" / "signal_translator.py"
    if demo_file.exists():
        print(f"Analyzing {demo_file}...\n")
        suggestions = suggester.analyze_file(str(demo_file))
        if suggestions:
            print(suggester.format_suggestions(suggestions))
            suggester.log_suggestions(suggestions)
        else:
            print("No suggestions.")
    else:
        print("Usage: code_suggester.py <filepath> | --query <text> | --log")


if __name__ == "__main__":
    main()
