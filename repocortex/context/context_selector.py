"""Smart Context Selector across code, call graph, tests, and documentation.

Assembles token-budget-aware context windows prioritizing relevant symbols,
architectural neighbors, associated unit tests, and repository documentation.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from repocortex.core.config import RepoCortexConfig
from repocortex.core.types import ContextWindow, FileNode, SearchResult, Symbol
from repocortex.context.repo_map import RepoMapGenerator
from repocortex.indexer.repository_index import RepositoryIndex


class ContextSelector:
    """Assembles rich context for coding tasks while strictly respecting token budgets."""

    def __init__(self, index: RepositoryIndex, config: RepoCortexConfig):
        self.index = index
        self.config = config
        self.repo_map_gen = RepoMapGenerator(index)

    def estimate_tokens(self, text: str) -> int:
        """Rough token count estimation (approx 3.8 characters per token for code/text)."""
        if not text:
            return 0
        return max(1, len(text) // 4)

    def select_context(
        self,
        query: str,
        target_files: Optional[List[str]] = None,
        max_tokens: Optional[int] = None,
    ) -> ContextWindow:
        """Assembles a prioritized context window for an investigation or bug fix."""
        budget = max_tokens or self.config.max_context_tokens
        used_tokens = 0

        selected_files: Set[str] = set(target_files or [])
        selected_symbols: List[Symbol] = []
        snippets: List[Dict[str, Any]] = []

        # 1. Hybrid search for target symbols and files
        search_results = self.index.search_hybrid(query, limit=10)

        # Collect primary matching symbols
        for res in search_results:
            if res.symbol:
                selected_symbols.append(res.symbol)
                selected_files.add(res.file_path)
            elif res.file_path:
                selected_files.add(res.file_path)

        # 2. Expand call graph neighbors (callers & callees)
        expanded_symbols: List[Symbol] = []
        for sym in selected_symbols[:5]:
            callers = self.index.symbol_graph.get_callers(sym.file_path, sym.name)
            callees = self.index.symbol_graph.get_callees(sym.file_path, sym.name)
            expanded_symbols.extend(callers[:2])
            expanded_symbols.extend(callees[:2])

        # Deduplicate symbols
        seen_sym_keys: Set[str] = set()
        all_candidate_symbols: List[Symbol] = []
        for s in selected_symbols + expanded_symbols:
            key = f"{s.file_path}::{s.qualified_name}"
            if key not in seen_sym_keys:
                seen_sym_keys.add(key)
                all_candidate_symbols.append(s)

        # 3. Discover associated test files
        associated_tests: List[str] = self._find_associated_tests(selected_files)

        # 4. Discover associated docs
        associated_docs: List[str] = self._find_associated_docs(query)

        # 5. Build compact Repo Map (reserve 15% budget for map)
        map_budget = min(1200, int(budget * 0.15))
        repo_map_str = self.repo_map_gen.generate_map(
            max_tokens=map_budget, focus_files=list(selected_files)
        )
        used_tokens += self.estimate_tokens(repo_map_str)

        # 6. Allocate remaining budget to Tier 1: Target symbols & file snippets
        remaining_budget = budget - used_tokens

        # Add full or windowed file content for target files
        for fpath in list(selected_files)[:4]:
            content = self.index.get_file_content(fpath)
            if not content:
                continue

            content_tokens = self.estimate_tokens(content)
            if content_tokens <= remaining_budget // 2:
                # Add complete file
                snippets.append({
                    "file_path": fpath,
                    "kind": "full_file",
                    "start_line": 1,
                    "end_line": len(content.splitlines()),
                    "content": content,
                })
                used_tokens += content_tokens
                remaining_budget -= content_tokens
            else:
                # Windowed snippet around relevant symbols
                window_snippet = self._extract_relevant_window(content, fpath, all_candidate_symbols)
                snip_tokens = self.estimate_tokens(window_snippet["content"])
                if snip_tokens <= remaining_budget:
                    snippets.append(window_snippet)
                    used_tokens += snip_tokens
                    remaining_budget -= snip_tokens

        # 7. Include relevant test snippets if budget permits
        for test_file in associated_tests[:2]:
            test_content = self.index.get_file_content(test_file)
            if not test_content:
                continue
            t_tokens = self.estimate_tokens(test_content)
            if t_tokens <= remaining_budget:
                snippets.append({
                    "file_path": test_file,
                    "kind": "test_suite",
                    "start_line": 1,
                    "end_line": len(test_content.splitlines()),
                    "content": test_content,
                })
                used_tokens += t_tokens
                remaining_budget -= t_tokens

        # 8. Include relevant doc snippet if budget permits
        for doc_file in associated_docs[:1]:
            doc_content = self.index.get_file_content(doc_file)
            if not doc_content:
                continue
            d_tokens = self.estimate_tokens(doc_content)
            doc_slice = "\n".join(doc_content.splitlines()[:60])
            slice_tokens = self.estimate_tokens(doc_slice)
            if slice_tokens <= remaining_budget:
                snippets.append({
                    "file_path": doc_file,
                    "kind": "documentation",
                    "start_line": 1,
                    "end_line": 60,
                    "content": doc_slice,
                })
                used_tokens += slice_tokens
                remaining_budget -= slice_tokens

        return ContextWindow(
            query=query,
            files=list(selected_files),
            symbols=all_candidate_symbols[:10],
            snippets=snippets,
            repo_map=repo_map_str,
            token_estimate=used_tokens,
            max_budget=budget,
        )

    def _find_associated_tests(self, target_files: Set[str]) -> List[str]:
        test_files: List[str] = []
        for tf in target_files:
            stem = Path(tf).stem
            # Match tests/test_<stem>.py, test_<stem>.py, <stem>_test.py
            for fpath, fnode in self.index.files.items():
                if fnode.is_test_file:
                    f_name = Path(fpath).name.lower()
                    if stem.lower() in f_name:
                        test_files.append(fpath)
        return test_files

    def _find_associated_docs(self, query: str) -> List[str]:
        docs: List[str] = []
        for fpath, fnode in self.index.files.items():
            if fnode.is_doc_file:
                docs.append(fpath)
        return docs

    def _extract_relevant_window(
        self, content: str, file_path: str, symbols: List[Symbol]
    ) -> Dict[str, Any]:
        lines = content.splitlines()
        file_syms = [s for s in symbols if s.file_path == file_path]
        if not file_syms:
            # Default to first 80 lines
            sub = lines[:80]
            return {
                "file_path": file_path,
                "kind": "partial_file",
                "start_line": 1,
                "end_line": len(sub),
                "content": "\n".join(sub),
            }

        start_line = max(1, min(s.start_line for s in file_syms) - 5)
        end_line = min(len(lines), max(s.end_line for s in file_syms) + 15)
        sub = lines[start_line - 1 : end_line]

        return {
            "file_path": file_path,
            "kind": "symbol_window",
            "start_line": start_line,
            "end_line": end_line,
            "content": "\n".join(sub),
        }
