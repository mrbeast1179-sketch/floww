"""
backend/services/causal/dag.py

Causal DAG of the dealer-hedging system.

Nodes: spot, GEX, VPIN, QI, kyle_lambda, dealer_hedge_pressure, realized_vol, anomaly_score

Edges (causal arrows from theory):
  - spot → GEX (mechanical)
  - GEX → dealer_hedge_pressure (theoretical)
  - dealer_hedge_pressure → spot (feedback)
  - VPIN → spread → kyle_lambda
  - realized_vol ↔ dealer_hedge_pressure (mutual)

Reference: Pearl (2009) Causality, 2nd ed.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

log = logging.getLogger(__name__)

# Node definitions
NODES = [
    "spot",
    "gex",
    "vpin",
    "qi",
    "kyle_lambda",
    "dealer_hedge_pressure",
    "realized_vol",
    "anomaly_score",
]

# Directed edges (cause -> effect)
EDGES = [
    ("spot", "gex"),
    ("gex", "dealer_hedge_pressure"),
    ("dealer_hedge_pressure", "spot"),  # feedback
    ("vpin", "kyle_lambda"),
    ("qi", "kyle_lambda"),
    ("realized_vol", "dealer_hedge_pressure"),
    ("dealer_hedge_pressure", "realized_vol"),  # mutual
    ("anomaly_score", "vpin"),
    ("gex", "realized_vol"),
]

# Confounders (common causes)
CONFOUNDERS = [
    ("realized_vol", "vpin"),  # vol affects both VPIN and dealer pressure
]


class CausalDAG:
    """Directed Acyclic Graph for causal inference.

    Despite the name, we allow the feedback edge (dealer_hedge_pressure → spot)
    for modeling purposes but flag it during acyclicity checks.
    """

    def __init__(self, nodes: Optional[List[str]] = None, edges: Optional[List[Tuple[str, str]]] = None):
        self.nodes = nodes if nodes is not None else list(NODES)
        self.edges = edges if edges is not None else list(EDGES)
        self._adj: Dict[str, List[str]] = {n: [] for n in self.nodes}
        self._parents: Dict[str, List[str]] = {n: [] for n in self.nodes}
        for src, dst in self.edges:
            if src in self._adj and dst in self._adj:
                self._adj[src].append(dst)
                self._parents[dst].append(src)

    def get_parents(self, node: str) -> List[str]:
        """Return parent nodes (direct causes)."""
        return list(self._parents.get(node, []))

    def get_children(self, node: str) -> List[str]:
        """Return child nodes (direct effects)."""
        return list(self._adj.get(node, []))

    def get_ancestors(self, node: str) -> Set[str]:
        """Return all ancestors of a node."""
        visited = set()
        stack = [node]
        while stack:
            current = stack.pop()
            for parent in self._parents.get(current, []):
                if parent not in visited:
                    visited.add(parent)
                    stack.append(parent)
        return visited

    def get_descendants(self, node: str) -> Set[str]:
        """Return all descendants of a node."""
        visited = set()
        stack = [node]
        while stack:
            current = stack.pop()
            for child in self._adj.get(current, []):
                if child not in visited:
                    visited.add(child)
                    stack.append(child)
        return visited

    def is_d_separated(self, x: str, y: str, conditioning: Set[str]) -> bool:
        """Check if X is d-separated from Y given conditioning set.

        Uses the Bayes ball algorithm for d-separation.
        """
        # Simple implementation: check all paths between x and y
        # A path is blocked if it contains a collider not in conditioning
        # or a non-collider in conditioning
        paths = self._find_all_paths(x, y)
        for path in paths:
            if not self._is_path_blocked(path, conditioning):
                return False
        return True

    def _find_all_paths(self, start: str, end: str, max_depth: int = 10) -> List[List[str]]:
        """Find all simple paths between two nodes."""
        paths = []
        self._dfs_paths(start, end, [start], set([start]), paths, max_depth)
        return paths

    def _dfs_paths(self, current, end, path, visited, paths, max_depth):
        if len(path) > max_depth:
            return
        if current == end and len(path) > 1:
            paths.append(list(path))
            return
        # Follow edges in both directions (for d-separation)
        neighbors = list(self._adj.get(current, [])) + list(self._parents.get(current, []))
        for neighbor in neighbors:
            if neighbor not in visited:
                visited.add(neighbor)
                path.append(neighbor)
                self._dfs_paths(neighbor, end, path, visited, paths, max_depth)
                path.pop()
                visited.remove(neighbor)

    def _is_path_blocked(self, path: List[str], conditioning: Set[str]) -> bool:
        """Check if a path is blocked by the conditioning set."""
        for i in range(1, len(path) - 1):
            prev_node = path[i - 1]
            curr_node = path[i]
            next_node = path[i + 1]

            # Determine if curr_node is a collider on this path
            # Collider: prev -> curr <- next
            is_collider = (
                curr_node in self._adj.get(prev_node, []) and
                curr_node in self._adj.get(next_node, [])
            )

            if is_collider:
                # Path is blocked unless collider or its descendant is in conditioning
                if curr_node not in conditioning:
                    descendants = self.get_descendants(curr_node)
                    if not descendants.intersection(conditioning):
                        return True
            else:
                # Non-collider: path is blocked if in conditioning
                if curr_node in conditioning:
                    return True
        return False

    def check_acyclic(self) -> Tuple[bool, Optional[str]]:
        """Check if the DAG is acyclic (ignoring feedback/mutual edges)."""
        # Remove feedback edges for acyclicity check
        feedback_edges = {
            ("dealer_hedge_pressure", "spot"),
            ("dealer_hedge_pressure", "realized_vol"),
            ("realized_vol", "dealer_hedge_pressure"),
        }
        clean_edges = [e for e in self.edges if e not in feedback_edges]

        adj = {n: [] for n in self.nodes}
        for src, dst in clean_edges:
            if src in adj:
                adj[src].append(dst)

        # DFS-based cycle detection
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {n: WHITE for n in self.nodes}

        def dfs(node):
            color[node] = GRAY
            for neighbor in adj.get(node, []):
                if color[neighbor] == GRAY:
                    return True  # Back edge = cycle
                if color[neighbor] == WHITE and dfs(neighbor):
                    return True
            color[node] = BLACK
            return False

        for node in self.nodes:
            if color[node] == WHITE:
                if dfs(node):
                    return False, f"Cycle detected involving {node}"
        return True, None

    def get_backdoor_paths(self, treatment: str, outcome: str) -> List[List[str]]:
        """Find all backdoor paths from treatment to outcome.

        Backdoor paths are paths from treatment to outcome that start with
        an arrow into the treatment (confounding paths).
        """
        paths = []
        for parent in self._parents.get(treatment, []):
            # Find paths from parent to outcome that don't go through treatment
            self._dfs_paths_avoiding(parent, outcome, [parent], set([parent, treatment]), paths, 10)
        return paths

    def _dfs_paths_avoiding(self, current, end, path, visited, paths, max_depth):
        if len(path) > max_depth:
            return
        if current == end and len(path) > 1:
            paths.append(list(path))
            return
        neighbors = list(self._adj.get(current, [])) + list(self._parents.get(current, []))
        for neighbor in neighbors:
            if neighbor not in visited:
                visited.add(neighbor)
                path.append(neighbor)
                self._dfs_paths_avoiding(neighbor, end, path, visited, paths, max_depth)
                path.pop()
                visited.remove(neighbor)

    def get_adjustment_set(self, treatment: str, outcome: str) -> Set[str]:
        """Get the minimal adjustment set for causal identification.

        Uses the backdoor criterion: find a set Z that blocks all backdoor
        paths from treatment to outcome.
        """
        backdoor_paths = self.get_backdoor_paths(treatment, outcome)
        if not backdoor_paths:
            return set()

        # Simple greedy: use all confounders (parents of treatment that are
        # also ancestors of outcome)
        adjustment = set()
        for parent in self._parents.get(treatment, []):
            outcome_ancestors = self.get_ancestors(outcome)
            if parent in outcome_ancestors or parent == outcome:
                adjustment.add(parent)

        return adjustment

    def to_mermaid(self) -> str:
        """Generate Mermaid diagram syntax."""
        lines = ["graph TD"]
        for src, dst in self.edges:
            lines.append(f"    {src} --> {dst}")
        return "\n".join(lines)

    def get_state(self) -> Dict[str, Any]:
        return {
            "nodes": self.nodes,
            "edges": self.edges,
            "n_nodes": len(self.nodes),
            "n_edges": len(self.edges),
        }


# Global singleton
dag = CausalDAG()
