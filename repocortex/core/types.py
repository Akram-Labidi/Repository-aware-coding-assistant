"""Core types and data models for RepoCortex."""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


class SymbolKind(str, Enum):
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    INTERFACE = "interface"
    STRUCT = "struct"
    VARIABLE = "variable"
    IMPORT = "import"
    CONSTANT = "constant"
    MODULE = "module"


@dataclass
class Symbol:
    name: str
    qualified_name: str
    kind: SymbolKind
    file_path: str
    start_line: int
    end_line: int
    docstring: str = ""
    signature: str = ""
    code_snippet: str = ""
    callers: List[str] = field(default_factory=list)
    callees: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "kind": self.kind.value if isinstance(self.kind, SymbolKind) else self.kind,
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "docstring": self.docstring,
            "signature": self.signature,
            "callers": self.callers,
            "callees": self.callees,
            "code_snippet": self.code_snippet,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Symbol:
        kind = data.get("kind", SymbolKind.FUNCTION)
        if isinstance(kind, str):
            try:
                kind = SymbolKind(kind)
            except ValueError:
                kind = SymbolKind.FUNCTION
        return cls(
            name=data["name"],
            qualified_name=data.get("qualified_name", data["name"]),
            kind=kind,
            file_path=data["file_path"],
            start_line=data["start_line"],
            end_line=data["end_line"],
            docstring=data.get("docstring", ""),
            signature=data.get("signature", ""),
            code_snippet=data.get("code_snippet", ""),
            callers=data.get("callers", []),
            callees=data.get("callees", []),
            metadata=data.get("metadata", {}),
        )


@dataclass
class FileNode:
    path: str
    language: str
    size_bytes: int
    line_count: int
    symbols: List[Symbol] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    sha256: str = ""
    is_test_file: bool = False
    is_doc_file: bool = False


@dataclass
class SearchResult:
    symbol: Optional[Symbol]
    file_path: str
    score: float
    match_type: str  # "symbol", "bm25", "pagerank", "fuzzy"
    snippet: str
    start_line: int
    end_line: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol.to_dict() if self.symbol else None,
            "file_path": self.file_path,
            "score": round(self.score, 4),
            "match_type": self.match_type,
            "snippet": self.snippet,
            "start_line": self.start_line,
            "end_line": self.end_line,
        }


@dataclass
class ContextWindow:
    query: str
    files: List[str]
    symbols: List[Symbol]
    snippets: List[Dict[str, Any]]
    repo_map: str
    token_estimate: int
    max_budget: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "files": self.files,
            "symbols": [s.to_dict() for s in self.symbols],
            "snippets": self.snippets,
            "repo_map": self.repo_map,
            "token_estimate": self.token_estimate,
            "max_budget": self.max_budget,
        }


class PermissionLevel(int, Enum):
    READ_ONLY = 0       # Can only read and analyze; no execution, no writes
    SAFE_EXEC = 1       # Can run whitelisted sandboxed tests; no file modifications
    WRITE_CONFIRM = 2   # Can propose patches, but modifications require explicit approval
    FULL_AUTO = 3       # Auto-applies approved changes in test harnesses


@dataclass
class CommandExecutionRequest:
    command: str
    cwd: str
    env: Dict[str, str] = field(default_factory=dict)
    timeout_sec: float = 15.0
    allowed_commands: Optional[List[str]] = None
    is_test_execution: bool = True


@dataclass
class CommandExecutionResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    duration_ms: float
    sandboxed: bool
    violated_boundary: bool
    error_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
            "duration_ms": self.duration_ms,
            "sandboxed": self.sandboxed,
            "violated_boundary": self.violated_boundary,
            "error_message": self.error_message,
        }


@dataclass
class FilePatch:
    file_path: str
    action: str  # "modify", "create", "delete"
    diff: str
    original_content: Optional[str] = None
    proposed_content: Optional[str] = None
    applied: bool = False
    verified: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "action": self.action,
            "diff": self.diff,
            "applied": self.applied,
            "verified": self.verified,
        }


@dataclass
class TestResult:
    test_name: str
    status: str  # "passed", "failed", "error", "skipped"
    duration_sec: float
    stdout: str = ""
    stderr: str = ""
    error_trace: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_name": self.test_name,
            "status": self.status,
            "duration_sec": self.duration_sec,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "error_trace": self.error_trace,
        }


@dataclass
class TestSuiteRun:
    total: int
    passed: int
    failed: int
    errors: int
    duration_sec: float
    results: List[TestResult]
    all_passed: bool
    raw_output: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "duration_sec": self.duration_sec,
            "results": [r.to_dict() for r in self.results],
            "all_passed": self.all_passed,
            "raw_output": self.raw_output,
        }


@dataclass
class AuditEntry:
    seq: int
    timestamp: str
    actor: str  # "user", "assistant", "system"
    action: str
    target: str
    payload: Dict[str, Any]
    status: str  # "success", "rejected", "blocked", "failed"
    prev_hash: str
    current_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seq": self.seq,
            "timestamp": self.timestamp,
            "actor": self.actor,
            "action": self.action,
            "target": self.target,
            "payload": self.payload,
            "status": self.status,
            "prev_hash": self.prev_hash,
            "current_hash": self.current_hash,
        }


@dataclass
class BenchmarkTask:
    id: str
    name: str
    description: str
    buggy_files: Dict[str, str]  # path -> buggy code
    test_file_path: str
    test_code: str
    expected_fix_files: Dict[str, str]  # path -> fixed code
    category: str


@dataclass
class BenchmarkEvaluationResult:
    task_id: str
    task_name: str
    category: str
    localized_correctly: bool
    patch_synthesized: bool
    tests_passed_after_patch: bool
    safety_passed: bool
    execution_time_sec: float
    audit_verified: bool
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "category": self.category,
            "localized_correctly": self.localized_correctly,
            "patch_synthesized": self.patch_synthesized,
            "tests_passed_after_patch": self.tests_passed_after_patch,
            "safety_passed": self.safety_passed,
            "execution_time_sec": round(self.execution_time_sec, 2),
            "audit_verified": self.audit_verified,
            "details": self.details,
        }
