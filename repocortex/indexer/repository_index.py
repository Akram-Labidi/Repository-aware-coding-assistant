"""Repository Indexer with SQLite persistence, AST parsing, and hybrid search.

Coordinates symbol extraction, BM25 text indexing, and PageRank graph construction.
"""

from __future__ import annotations
import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from repocortex.core.config import RepoCortexConfig
from repocortex.core.types import FileNode, SearchResult, Symbol, SymbolKind
from repocortex.indexer.ast_parser import CodeParser
from repocortex.indexer.bm25 import BM25Index
from repocortex.indexer.symbol_graph import SymbolGraph


class RepositoryIndex:
    """Central repository indexing and code search coordinator."""

    IGNORE_DIRS = {
        ".git", ".svn", ".hg", ".venv", "venv", "env", "__pycache__",
        "node_modules", ".pytest_cache", ".repocortex", ".idea", ".vscode",
        "dist", "build", "target", ".mypy_cache"
    }

    IGNORE_EXTS = {
        ".pyc", ".pyo", ".pyd", ".exe", ".dll", ".so", ".dylib", ".bin",
        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".zip", ".tar",
        ".gz", ".7z", ".pdf", ".lock", ".db", ".sqlite", ".sqlite3"
    }

    def __init__(self, config: RepoCortexConfig):
        self.config = config
        self.files: Dict[str, FileNode] = {}
        self.symbols: Dict[str, Symbol] = {}  # qualified_key -> Symbol
        self.symbol_graph = SymbolGraph()
        self.bm25 = BM25Index()
        self.db_path = config.db_path
        self._init_db()
        self._load_from_db()

    def _load_from_db(self) -> None:
        if not self.db_path.exists():
            return
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT path, language, size_bytes, line_count, sha256, is_test_file, is_doc_file FROM files")
            for row in cursor.fetchall():
                fnode = FileNode(
                    path=row[0],
                    language=row[1],
                    size_bytes=row[2],
                    line_count=row[3],
                    sha256=row[4],
                    is_test_file=bool(row[5]),
                    is_doc_file=bool(row[6]),
                )
                self.files[row[0]] = fnode

            cursor.execute("SELECT key, name, qualified_name, kind, file_path, start_line, end_line, docstring, signature, code_snippet, callees, callers, pagerank FROM symbols")
            for row in cursor.fetchall():
                callees = json.loads(row[10]) if row[10] else []
                callers = json.loads(row[11]) if row[11] else []
                try:
                    kind = SymbolKind(row[3])
                except ValueError:
                    kind = SymbolKind.FUNCTION
                sym = Symbol(
                    name=row[1],
                    qualified_name=row[2],
                    kind=kind,
                    file_path=row[4],
                    start_line=row[5],
                    end_line=row[6],
                    docstring=row[7] or "",
                    signature=row[8] or "",
                    code_snippet=row[9] or "",
                    callees=callees,
                    callers=callers,
                )
                self.symbols[row[0]] = sym
                self.symbol_graph.add_symbol(sym)
                if row[12] is not None:
                    self.symbol_graph.pagerank_scores[row[0]] = float(row[12])

                if row[4] in self.files:
                    self.files[row[4]].symbols.append(sym)

            cursor.execute("SELECT json_data FROM bm25_data WHERE id = 1")
            bm25_row = cursor.fetchone()
            if bm25_row and bm25_row[0]:
                self.bm25 = BM25Index.from_dict(json.loads(bm25_row[0]))
        except Exception:
            pass
        finally:
            conn.close()

    def _init_db(self) -> None:
        self.config.ensure_storage_dir()
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    path TEXT PRIMARY KEY,
                    language TEXT,
                    size_bytes INTEGER,
                    line_count INTEGER,
                    sha256 TEXT,
                    is_test_file BOOLEAN,
                    is_doc_file BOOLEAN,
                    updated_at REAL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS symbols (
                    key TEXT PRIMARY KEY,
                    name TEXT,
                    qualified_name TEXT,
                    kind TEXT,
                    file_path TEXT,
                    start_line INTEGER,
                    end_line INTEGER,
                    docstring TEXT,
                    signature TEXT,
                    code_snippet TEXT,
                    callees TEXT,
                    callers TEXT,
                    pagerank REAL DEFAULT 0.0,
                    FOREIGN KEY(file_path) REFERENCES files(path)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bm25_data (
                    id INTEGER PRIMARY KEY,
                    json_data TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sym_name ON symbols(name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sym_file ON symbols(file_path)")
            conn.commit()
        finally:
            conn.close()

    def should_ignore(self, path: Path) -> bool:
        # Check parts for ignored directory names
        for part in path.parts:
            if part in self.IGNORE_DIRS:
                return True
        if path.suffix.lower() in self.IGNORE_EXTS:
            return True
        if path.name.startswith("."):
            return True
        return False

    def build_index(self, force: bool = False) -> Dict[str, Any]:
        """Indexes all supported source files and documentation in repo_root."""
        start_time = time.time()
        root = self.config.abs_repo_root

        # Track documents for BM25
        documents_for_bm25: Dict[str, str] = {}
        indexed_files = 0
        indexed_symbols = 0

        self.files.clear()
        self.symbols.clear()
        self.symbol_graph = SymbolGraph()

        for dirpath, dirnames, filenames in os.walk(root):
            # Prune ignored directories
            dirnames[:] = [d for d in dirnames if d not in self.IGNORE_DIRS and not d.startswith(".")]

            for fname in filenames:
                full_path = Path(dirpath) / fname
                if self.should_ignore(full_path):
                    continue

                try:
                    rel_path = str(full_path.relative_to(root)).replace("\\", "/")
                except ValueError:
                    rel_path = str(full_path).replace("\\", "/")

                # Read file content safely
                try:
                    content = full_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue

                sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
                size_bytes = len(content.encode("utf-8"))
                lines = content.splitlines()
                line_count = len(lines)
                is_test = "test" in rel_path.lower()
                is_doc = rel_path.lower().endswith((".md", ".rst", ".txt"))

                lang = CodeParser.get_language(rel_path) or ("markdown" if is_doc else "text")

                # Parse AST & symbols if code file
                file_symbols, imports = CodeParser.parse_file(rel_path, content)

                file_node = FileNode(
                    path=rel_path,
                    language=lang,
                    size_bytes=size_bytes,
                    line_count=line_count,
                    symbols=file_symbols,
                    imports=imports,
                    sha256=sha256,
                    is_test_file=is_test,
                    is_doc_file=is_doc,
                )
                self.files[rel_path] = file_node
                indexed_files += 1

                # BM25 document for entire file
                documents_for_bm25[f"file::{rel_path}"] = f"{rel_path}\n{content}"

                for sym in file_symbols:
                    sym_key = f"{rel_path}::{sym.qualified_name}"
                    self.symbols[sym_key] = sym
                    self.symbol_graph.add_symbol(sym)
                    indexed_symbols += 1

                    # BM25 document for each individual symbol chunk
                    sym_text = f"{sym.name} {sym.signature}\n{sym.docstring}\n{sym.code_snippet}"
                    documents_for_bm25[f"sym::{sym_key}"] = sym_text

        # Build symbol graph edges & PageRank
        self.symbol_graph.build_edges()

        # Build BM25 index
        self.bm25.index_documents(documents_for_bm25)

        # Persist to SQLite
        self._save_to_db()

        duration = time.time() - start_time
        return {
            "files_indexed": indexed_files,
            "symbols_indexed": indexed_symbols,
            "duration_sec": round(duration, 3),
        }

    def _save_to_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM files")
            cursor.execute("DELETE FROM symbols")
            cursor.execute("DELETE FROM bm25_data")

            # Insert files
            for f in self.files.values():
                cursor.execute(
                    "INSERT INTO files VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        f.path,
                        f.language,
                        f.size_bytes,
                        f.line_count,
                        f.sha256,
                        f.is_test_file,
                        f.is_doc_file,
                        time.time(),
                    ),
                )

            # Insert symbols
            for sym_key, sym in self.symbols.items():
                pr = self.symbol_graph.get_centrality(sym.file_path, sym.name)
                cursor.execute(
                    """
                    INSERT INTO symbols VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sym_key,
                        sym.name,
                        sym.qualified_name,
                        sym.kind.value if hasattr(sym.kind, "value") else str(sym.kind),
                        sym.file_path,
                        sym.start_line,
                        sym.end_line,
                        sym.docstring,
                        sym.signature,
                        sym.code_snippet,
                        json.dumps(sym.callees),
                        json.dumps(sym.callers),
                        pr,
                    ),
                )

            # Persist BM25
            cursor.execute(
                "INSERT INTO bm25_data VALUES (1, ?)",
                (json.dumps(self.bm25.to_dict()),),
            )
            conn.commit()
        finally:
            conn.close()

    def search_symbols(self, query: str, limit: int = 15) -> List[SearchResult]:
        """Searches specifically for function/class/method symbols by name or signature."""
        if not self.symbols and not self.files:
            self.build_index()
        query_clean = query.strip().lower()
        results: List[SearchResult] = []
        seen_keys: Set[str] = set()

        # 1. Exact & prefix match on symbol names
        for key, sym in self.symbols.items():
            sym_name_low = sym.name.lower()
            qual_name_low = sym.qualified_name.lower()

            score = 0.0
            if query_clean == sym_name_low or query_clean == qual_name_low:
                score = 10.0
            elif sym_name_low.startswith(query_clean):
                score = 8.0
            elif query_clean in sym_name_low or query_clean in qual_name_low:
                score = 6.0

            if score > 0:
                pr = self.symbol_graph.get_centrality(sym.file_path, sym.name)
                final_score = score + (pr * 3.0)
                results.append(
                    SearchResult(
                        symbol=sym,
                        file_path=sym.file_path,
                        score=final_score,
                        match_type="symbol",
                        snippet=sym.signature or sym.code_snippet[:200],
                        start_line=sym.start_line,
                        end_line=sym.end_line,
                    )
                )
                seen_keys.add(key)

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]

    def search_hybrid(self, query: str, limit: int = 15) -> List[SearchResult]:
        """Hybrid search combining symbol matching, BM25 Okapi lexical scoring, and PageRank."""
        # Symbol results first
        symbol_results = self.search_symbols(query, limit=limit)
        seen_targets: Set[str] = {f"{r.file_path}::{r.start_line}" for r in symbol_results}
        combined: List[SearchResult] = list(symbol_results)

        # BM25 results
        bm25_matches = self.bm25.search(query, top_k=limit * 2)

        for doc_id, score in bm25_matches:
            if doc_id.startswith("sym::"):
                sym_key = doc_id[len("sym::"):]
                if sym_key in self.symbols:
                    sym = self.symbols[sym_key]
                    target_id = f"{sym.file_path}::{sym.start_line}"
                    if target_id not in seen_targets:
                        seen_targets.add(target_id)
                        pr = self.symbol_graph.get_centrality(sym.file_path, sym.name)
                        final_score = score * 1.5 + (pr * 2.0)
                        combined.append(
                            SearchResult(
                                symbol=sym,
                                file_path=sym.file_path,
                                score=final_score,
                                match_type="bm25+symbol",
                                snippet=sym.signature or sym.code_snippet[:200],
                                start_line=sym.start_line,
                                end_line=sym.end_line,
                            )
                        )
            elif doc_id.startswith("file::"):
                file_path = doc_id[len("file::"):]
                target_id = f"{file_path}::1"
                if target_id not in seen_targets and file_path in self.files:
                    seen_targets.add(target_id)
                    fnode = self.files[file_path]
                    snippet = ""
                    try:
                        abs_p = self.config.abs_repo_root / file_path
                        if abs_p.exists():
                            snippet = "\n".join(abs_p.read_text(encoding="utf-8", errors="replace").splitlines()[:15])
                    except Exception:
                        pass
                    combined.append(
                        SearchResult(
                            symbol=None,
                            file_path=file_path,
                            score=score,
                            match_type="bm25_file",
                            snippet=snippet,
                            start_line=1,
                            end_line=min(fnode.line_count, 30),
                        )
                    )

        combined.sort(key=lambda x: x.score, reverse=True)
        return combined[:limit]

    def get_symbol_by_name(self, name: str) -> Optional[Symbol]:
        for sym in self.symbols.values():
            if sym.name == name or sym.qualified_name == name:
                return sym
        return None

    def get_file_content(self, rel_path: str) -> Optional[str]:
        target = (self.config.abs_repo_root / rel_path).resolve()
        # Enforce repo root boundary
        if not str(target).startswith(str(self.config.abs_repo_root)):
            return None
        if target.exists() and target.is_file():
            try:
                return target.read_text(encoding="utf-8", errors="replace")
            except Exception:
                return None
        return None
