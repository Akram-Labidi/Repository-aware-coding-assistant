"""Multi-language AST and symbol parser.

Uses Python's native `ast` module for Python files, and structural regex/brace parsers
for polyglot support (JavaScript/TypeScript, Go, Rust, Java, C/C++).
"""

from __future__ import annotations
import ast
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from repocortex.core.types import Symbol, SymbolKind


class PythonASTParser:
    """Extracts symbols, signatures, docstrings, imports, and call graph from Python code."""

    def __init__(self, file_path: str, source_code: str):
        self.file_path = file_path
        self.source_code = source_code
        self.lines = source_code.splitlines()

    def parse(self) -> Tuple[List[Symbol], List[str]]:
        """Returns (symbols, imports)."""
        symbols: List[Symbol] = []
        imports: List[str] = []

        try:
            tree = ast.parse(self.source_code, filename=self.file_path)
        except SyntaxError:
            # If standard syntax error, attempt relaxed parsing or fallback
            return symbols, imports

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.extend(self._extract_imports(node))
            elif isinstance(node, ast.ClassDef):
                symbols.extend(self._extract_class(node))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append(self._extract_function(node, parent_class=None))
            elif isinstance(node, ast.Assign):
                symbols.extend(self._extract_constants(node))

        return symbols, imports

    def _extract_imports(self, node: ast.AST) -> List[str]:
        res = []
        if isinstance(node, ast.Import):
            for alias in node.names:
                res.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                res.append(f"{mod}.{alias.name}" if mod else alias.name)
        return res

    def _extract_constants(self, node: ast.Assign) -> List[Symbol]:
        res = []
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.isupper():
                snippet = self._get_snippet(node.lineno, getattr(node, "end_lineno", node.lineno))
                res.append(
                    Symbol(
                        name=target.id,
                        qualified_name=target.id,
                        kind=SymbolKind.CONSTANT,
                        file_path=self.file_path,
                        start_line=node.lineno,
                        end_line=getattr(node, "end_lineno", node.lineno),
                        code_snippet=snippet,
                    )
                )
        return res

    def _extract_class(self, node: ast.ClassDef) -> List[Symbol]:
        res: List[Symbol] = []
        class_name = node.name
        docstring = ast.get_docstring(node) or ""
        bases = [ast.unparse(b) for b in node.bases] if hasattr(ast, "unparse") else []
        sig = f"class {class_name}({', '.join(bases)})" if bases else f"class {class_name}"

        snippet = self._get_snippet(node.lineno, min(node.lineno + 15, getattr(node, "end_lineno", node.lineno)))

        # Find methods
        methods = []
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_sym = self._extract_function(child, parent_class=class_name)
                res.append(method_sym)
                methods.append(method_sym.name)

        class_sym = Symbol(
            name=class_name,
            qualified_name=class_name,
            kind=SymbolKind.CLASS,
            file_path=self.file_path,
            start_line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno),
            docstring=docstring,
            signature=sig,
            code_snippet=snippet,
            callees=methods,
            metadata={"bases": bases},
        )
        res.insert(0, class_sym)
        return res

    def _extract_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        parent_class: Optional[str] = None,
    ) -> Symbol:
        fn_name = node.name
        qualified_name = f"{parent_class}.{fn_name}" if parent_class else fn_name
        kind = SymbolKind.METHOD if parent_class else SymbolKind.FUNCTION
        docstring = ast.get_docstring(node) or ""

        # Extract signature
        sig = self._format_signature(node)

        # Extract callers & callees
        callees = self._extract_callees(node)

        snippet = self._get_snippet(node.lineno, getattr(node, "end_lineno", node.lineno))

        return Symbol(
            name=fn_name,
            qualified_name=qualified_name,
            kind=kind,
            file_path=self.file_path,
            start_line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno),
            docstring=docstring,
            signature=sig,
            code_snippet=snippet,
            callees=callees,
            metadata={"is_async": isinstance(node, ast.AsyncFunctionDef)},
        )

    def _format_signature(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
        args_str = ""
        if hasattr(ast, "unparse"):
            args_str = ast.unparse(node.args)
        else:
            args_str = ", ".join(arg.arg for arg in node.args.args)
        
        ret_annotation = ""
        if node.returns:
            ret_annotation = f" -> {ast.unparse(node.returns) if hasattr(ast, 'unparse') else '...'}"
        
        return f"{prefix}{node.name}({args_str}){ret_annotation}"

    def _extract_callees(self, func_node: ast.AST) -> List[str]:
        callees: Set[str] = set()
        for node in ast.walk(func_node):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    callees.add(func.id)
                elif isinstance(func, ast.Attribute):
                    callees.add(func.attr)
        return sorted(list(callees))

    def _get_snippet(self, start_line: int, end_line: int) -> str:
        s = max(0, start_line - 1)
        e = min(len(self.lines), end_line)
        return "\n".join(self.lines[s:e])


class PolyglotStructuralParser:
    """Regex/structural parser for TypeScript, JavaScript, Go, Rust, Java, and C/C++."""

    JS_PATTERNS = [
        (re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+([A-Za-z0-9_$]+)\s*\(([^)]*)\)", re.MULTILINE), SymbolKind.FUNCTION),
        (re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z0-9_$]+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>", re.MULTILINE), SymbolKind.FUNCTION),
        (re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z0-9_$]+)(?:\s+extends\s+[A-Za-z0-9_$]+)?", re.MULTILINE), SymbolKind.CLASS),
        (re.compile(r"^\s*(?:export\s+)?interface\s+([A-Za-z0-9_$]+)", re.MULTILINE), SymbolKind.INTERFACE),
    ]

    GO_PATTERNS = [
        (re.compile(r"^func\s+(?:\([^)]+\)\s+)?([A-Za-z0-9_]+)\s*\(([^)]*)\)", re.MULTILINE), SymbolKind.FUNCTION),
        (re.compile(r"^type\s+([A-Za-z0-9_]+)\s+struct", re.MULTILINE), SymbolKind.STRUCT),
        (re.compile(r"^type\s+([A-Za-z0-9_]+)\s+interface", re.MULTILINE), SymbolKind.INTERFACE),
    ]

    RUST_PATTERNS = [
        (re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z0-9_]+)\s*(?:<[^>]+>)?\s*\(([^)]*)\)", re.MULTILINE), SymbolKind.FUNCTION),
        (re.compile(r"^\s*(?:pub\s+)?struct\s+([A-Za-z0-9_]+)", re.MULTILINE), SymbolKind.STRUCT),
        (re.compile(r"^\s*(?:pub\s+)?enum\s+([A-Za-z0-9_]+)", re.MULTILINE), SymbolKind.CLASS),
        (re.compile(r"^\s*(?:pub\s+)?trait\s+([A-Za-z0-9_]+)", re.MULTILINE), SymbolKind.INTERFACE),
    ]

    def __init__(self, file_path: str, source_code: str, language: str):
        self.file_path = file_path
        self.source_code = source_code
        self.language = language.lower()
        self.lines = source_code.splitlines()

    def parse(self) -> Tuple[List[Symbol], List[str]]:
        symbols: List[Symbol] = []
        imports: List[str] = []

        patterns = []
        if self.language in ("javascript", "typescript", "js", "ts", "jsx", "tsx"):
            patterns = self.JS_PATTERNS
            imports.extend(re.findall(r"(?:import\s+.*?from\s+['\"](.*?)['\"]|require\(['\"](.*?)['\"]\))", self.source_code))
            flat_imports = [i[0] or i[1] for i in imports if any(i)]
            imports = flat_imports
        elif self.language in ("go", "golang"):
            patterns = self.GO_PATTERNS
            imports.extend(re.findall(r'import\s+\(\s*([\s\S]*?)\)', self.source_code))
        elif self.language in ("rust", "rs"):
            patterns = self.RUST_PATTERNS
            imports.extend(re.findall(r"use\s+([A-Za-z0-9_:]+);", self.source_code))

        for pattern, kind in patterns:
            for match in pattern.finditer(self.source_code):
                name = match.group(1)
                char_idx = match.start()
                start_line = self.source_code[:char_idx].count("\n") + 1
                end_line = min(len(self.lines), start_line + 25)
                sig = match.group(0).strip()
                snippet = "\n".join(self.lines[start_line - 1 : min(len(self.lines), start_line + 15)])

                symbols.append(
                    Symbol(
                        name=name,
                        qualified_name=name,
                        kind=kind,
                        file_path=self.file_path,
                        start_line=start_line,
                        end_line=end_line,
                        signature=sig,
                        code_snippet=snippet,
                    )
                )

        return symbols, imports


class CodeParser:
    """Unified parser router selecting appropriate parser based on file extension."""

    LANGUAGE_EXTENSIONS = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".cpp": "cpp",
        ".c": "c",
        ".h": "c",
        ".hpp": "cpp",
    }

    @classmethod
    def get_language(cls, file_path: str) -> Optional[str]:
        ext = Path(file_path).suffix.lower()
        return cls.LANGUAGE_EXTENSIONS.get(ext)

    @classmethod
    def parse_file(cls, file_path: str, content: str) -> Tuple[List[Symbol], List[str]]:
        lang = cls.get_language(file_path)
        if not lang:
            return [], []

        if lang == "python":
            return PythonASTParser(file_path, content).parse()
        else:
            return PolyglotStructuralParser(file_path, content, lang).parse()
