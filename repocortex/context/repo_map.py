"""Repository Map generator.

Constructs a compact structural skeleton of the repository's files, classes,
and functions, prioritized by PageRank architectural centrality.
"""

from __future__ import annotations
from typing import Dict, List, Optional, Set
from repocortex.core.types import FileNode, Symbol, SymbolKind
from repocortex.indexer.repository_index import RepositoryIndex


class RepoMapGenerator:
    """Generates concise, token-efficient repository outlines."""

    def __init__(self, index: RepositoryIndex):
        self.index = index

    def generate_map(self, max_tokens: int = 1500, focus_files: Optional[List[str]] = None) -> str:
        """Builds a condensed tree map of files, classes, and top function signatures."""
        lines: List[str] = []
        lines.append("# REPOSITORY STRUCTURE & SYMBOL MAP")
        lines.append("")

        focus_set = set(focus_files or [])
        files_by_priority = sorted(
            self.index.files.values(),
            key=lambda f: (
                0 if f.path in focus_set else 1,
                0 if not f.is_test_file else 2,
                f.path,
            ),
        )

        approx_token_count = 20

        for fnode in files_by_priority:
            if approx_token_count >= max_tokens:
                lines.append("... [remaining repository files truncated for brevity]")
                break

            prefix = "📄 "
            if fnode.is_test_file:
                prefix = "🧪 "
            elif fnode.is_doc_file:
                prefix = "📖 "

            file_header = f"{prefix}{fnode.path} ({fnode.line_count} lines, {fnode.language})"
            lines.append(file_header)
            approx_token_count += len(file_header.split()) + 3

            # Sort symbols by line number or importance
            sorted_symbols = sorted(fnode.symbols, key=lambda s: s.start_line)

            for sym in sorted_symbols:
                if approx_token_count >= max_tokens:
                    break

                indent = "    " if sym.kind == SymbolKind.METHOD else "  "
                icon = {
                    SymbolKind.CLASS: "class",
                    SymbolKind.FUNCTION: "def",
                    SymbolKind.METHOD: "def",
                    SymbolKind.INTERFACE: "interface",
                    SymbolKind.STRUCT: "struct",
                    SymbolKind.CONSTANT: "const",
                }.get(sym.kind, "sym")

                sig_display = sym.signature if sym.signature else f"{icon} {sym.name}"
                pr = self.index.symbol_graph.get_centrality(sym.file_path, sym.name)
                pr_tag = f" [★ rank {pr:.2f}]" if pr > 0.4 else ""

                entry = f"{indent}• {sig_display} (lines {sym.start_line}-{sym.end_line}){pr_tag}"
                lines.append(entry)
                approx_token_count += len(entry.split()) + 3

            lines.append("")

        return "\n".join(lines)
