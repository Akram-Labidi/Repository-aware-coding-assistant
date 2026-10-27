"""Symbol graph, call hierarchy, and PageRank centrality ranking.

Maps architectural relationships between functions, classes, and files,
enabling global repository awareness and accurate context ranking.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Set, Tuple
from repocortex.core.types import Symbol, SymbolKind


class SymbolGraph:
    """Directed graph representing symbol calls, definitions, and dependencies."""

    def __init__(self):
        # symbol_key: "file_path::qualified_name"
        self.nodes: Dict[str, Symbol] = {}
        # Outgoing edges: caller_key -> set of callee_keys
        self.adj_out: Dict[str, Set[str]] = {}
        # Incoming edges: callee_key -> set of caller_keys
        self.adj_in: Dict[str, Set[str]] = {}
        # Quick lookup: unqualified name -> list of symbol_keys
        self.name_to_keys: Dict[str, List[str]] = {}
        # PageRank scores: symbol_key -> score (0.0 - 1.0)
        self.pagerank_scores: Dict[str, float] = {}

    def _make_key(self, file_path: str, name: str) -> str:
        return f"{file_path}::{name}"

    def add_symbol(self, symbol: Symbol) -> str:
        key = self._make_key(symbol.file_path, symbol.qualified_name)
        self.nodes[key] = symbol
        if key not in self.adj_out:
            self.adj_out[key] = set()
        if key not in self.adj_in:
            self.adj_in[key] = set()

        if symbol.name not in self.name_to_keys:
            self.name_to_keys[symbol.name] = []
        if key not in self.name_to_keys[symbol.name]:
            self.name_to_keys[symbol.name].append(key)

        return key

    def build_edges(self) -> None:
        """Resolves callees for all symbols and builds edges."""
        for key, symbol in self.nodes.items():
            for callee_name in symbol.callees:
                # Find matching symbols with that name
                target_keys = self.name_to_keys.get(callee_name, [])
                for target_key in target_keys:
                    if target_key != key:
                        self.adj_out[key].add(target_key)
                        self.adj_in[target_key].add(key)
                        
                        # Update Symbol data objects as well
                        if key not in self.nodes[target_key].callers:
                            self.nodes[target_key].callers.append(key)

        self.compute_pagerank()

    def compute_pagerank(self, damping: float = 0.85, max_iter: int = 40, tol: float = 1e-5) -> Dict[str, float]:
        """Calculates PageRank centrality using power iteration."""
        num_nodes = len(self.nodes)
        if num_nodes == 0:
            self.pagerank_scores = {}
            return {}

        init_score = 1.0 / num_nodes
        scores = {k: init_score for k in self.nodes}

        for _ in range(max_iter):
            new_scores = {}
            dangling_sum = sum(scores[k] for k in self.nodes if not self.adj_out[k])
            dangling_contrib = (damping * dangling_sum) / num_nodes
            base_score = (1.0 - damping) / num_nodes + dangling_contrib

            diff = 0.0
            for node in self.nodes:
                inbound_sum = 0.0
                for inbound in self.adj_in[node]:
                    out_degree = len(self.adj_out[inbound])
                    if out_degree > 0:
                        inbound_sum += scores[inbound] / out_degree

                new_scores[node] = base_score + damping * inbound_sum
                diff += abs(new_scores[node] - scores[node])

            scores = new_scores
            if diff < tol:
                break

        # Normalize so max is 1.0
        max_val = max(scores.values()) if scores else 1.0
        if max_val > 0:
            self.pagerank_scores = {k: v / max_val for k, v in scores.items()}
        else:
            self.pagerank_scores = scores

        return self.pagerank_scores

    def get_centrality(self, file_path: str, symbol_name: str) -> float:
        key = self._make_key(file_path, symbol_name)
        return self.pagerank_scores.get(key, 0.0)

    def get_callers(self, file_path: str, symbol_name: str) -> List[Symbol]:
        key = self._make_key(file_path, symbol_name)
        caller_keys = self.adj_in.get(key, set())
        return [self.nodes[k] for k in caller_keys if k in self.nodes]

    def get_callees(self, file_path: str, symbol_name: str) -> List[Symbol]:
        key = self._make_key(file_path, symbol_name)
        callee_keys = self.adj_out.get(key, set())
        return [self.nodes[k] for k in callee_keys if k in self.nodes]

    def get_related_subgraph(
        self, target_keys: List[str], max_depth: int = 2
    ) -> Tuple[List[Dict], List[Dict]]:
        """Extracts nodes and edges for UI visualization around target symbols."""
        visited_nodes: Set[str] = set()
        frontier: Set[str] = set(target_keys)

        for _ in range(max_depth):
            next_frontier = set()
            for key in frontier:
                if key in self.nodes and key not in visited_nodes:
                    visited_nodes.add(key)
                    next_frontier.update(self.adj_out.get(key, set()))
                    next_frontier.update(self.adj_in.get(key, set()))
            frontier = next_frontier

        # Format for visualization
        nodes_out = []
        for k in visited_nodes:
            if k in self.nodes:
                sym = self.nodes[k]
                nodes_out.append({
                    "id": k,
                    "label": sym.name,
                    "file": sym.file_path,
                    "kind": sym.kind.value if hasattr(sym.kind, "value") else str(sym.kind),
                    "centrality": round(self.pagerank_scores.get(k, 0.0), 3),
                })

        edges_out = []
        for src in visited_nodes:
            for dst in self.adj_out.get(src, set()):
                if dst in visited_nodes:
                    edges_out.append({
                        "source": src,
                        "target": dst,
                        "type": "calls",
                    })

        return nodes_out, edges_out
