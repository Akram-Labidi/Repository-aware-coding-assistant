"""Central Orchestrator for RepoCortex.

Coordinates repository indexing, smart context selection, sandboxed execution,
diff generation, permission boundary enforcement, and tamper-evident audit logging.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from repocortex.core.config import RepoCortexConfig
from repocortex.core.types import (
    AuditEntry,
    ContextWindow,
    FilePatch,
    PermissionLevel,
    SearchResult,
    TestSuiteRun,
)
from repocortex.context.context_selector import ContextSelector
from repocortex.indexer.repository_index import RepositoryIndex
from repocortex.llm.local_agent import LocalDeterministicAgent
from repocortex.llm.gemini_provider import GeminiProvider
from repocortex.llm.openai_provider import OpenAICompatibleProvider
from repocortex.llm.provider import LLMProvider
from repocortex.sandbox.executor import IsolatedWorkspace, SandboxExecutor
from repocortex.sandbox.patch_manager import PatchManager
from repocortex.sandbox.permissions import PermissionBoundary, SecurityViolation
from repocortex.security.audit_logger import AuditLogger
from repocortex.testing.test_runner import TestRunner


class RepoCortexAssistant:
    """End-to-end repository-aware coding assistant."""

    def __init__(self, config: Optional[RepoCortexConfig] = None):
        self.config = config or RepoCortexConfig.load()
        self.boundary = PermissionBoundary(self.config)
        self.executor = SandboxExecutor(self.config)
        self.patch_manager = PatchManager(self.config)
        self.audit_logger = AuditLogger(self.config)
        self.test_runner = TestRunner(self.config, self.executor)
        self.index = RepositoryIndex(self.config)
        self.context_selector = ContextSelector(self.index, self.config)
        self.llm = self._init_llm_provider()

    def _init_llm_provider(self) -> LLMProvider:
        prov = self.config.llm_provider.lower()
        if prov == "gemini" and self.config.api_key:
            return GeminiProvider(api_key=self.config.api_key, model=self.config.llm_model)
        elif prov == "openai" and self.config.api_key:
            return OpenAICompatibleProvider(api_key=self.config.api_key, model=self.config.llm_model)
        else:
            return LocalDeterministicAgent()

    def index_repo(self, force: bool = False) -> Dict[str, Any]:
        """Indexes repository AST, symbols, call graph, and BM25 search."""
        stats = self.index.build_index(force=force)
        self.audit_logger.log(
            action="INDEX_REPOSITORY",
            target=str(self.config.abs_repo_root),
            actor="assistant",
            payload=stats,
            status="success",
        )
        return stats

    def search_code(self, query: str, limit: int = 10) -> List[SearchResult]:
        """Performs hybrid symbol and lexical code search."""
        results = self.index.search_hybrid(query, limit=limit)
        self.audit_logger.log(
            action="SEARCH_CODE",
            target=query,
            actor="user",
            payload={"results_count": len(results)},
            status="success",
        )
        return results

    def investigate_bug(
        self, bug_report: str, target_files: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Read-only analysis of a reported bug."""
        # Assemble context
        ctx = self.context_selector.select_context(bug_report, target_files=target_files)

        analysis = (
            f"### Bug Investigation Report\n\n"
            f"**Query**: {bug_report}\n\n"
            f"**Candidate Files**: {', '.join(ctx.files) if ctx.files else 'None'}\n\n"
            f"**Key Architectural Symbols**:\n"
        )
        for sym in ctx.symbols[:5]:
            analysis += f"- `{sym.qualified_name}` ({sym.file_path}:{sym.start_line}) [{sym.kind.value}]\n"

        self.audit_logger.log(
            action="INVESTIGATE_BUG",
            target=bug_report[:80],
            actor="assistant",
            payload={"files": ctx.files, "symbols": [s.name for s in ctx.symbols]},
            status="success",
        )

        return {
            "analysis": analysis,
            "context": ctx.to_dict(),
            "candidate_files": ctx.files,
        }

    def propose_fix(
        self,
        bug_report: str,
        target_files: Optional[List[str]] = None,
        verify_in_sandbox: bool = True,
    ) -> Dict[str, Any]:
        """Synthesizes a fix, generates unified diffs, and safely runs tests in sandbox."""
        # 1. Assemble context
        ctx = self.context_selector.select_context(bug_report, target_files=target_files)

        # 2. Run baseline test suite to capture failure trace if available
        baseline_run: Optional[TestSuiteRun] = None
        if verify_in_sandbox and self.config.permission_level != PermissionLevel.READ_ONLY:
            try:
                baseline_run = self.test_runner.run_tests()
            except Exception:
                pass

        failing_output = baseline_run.raw_output if (baseline_run and not baseline_run.all_passed) else None

        # 3. Request fix from reasoning provider
        fixed_files = self.llm.diagnose_and_fix(
            ctx, bug_report, failing_test_output=failing_output
        )

        if not fixed_files:
            return {
                "success": False,
                "message": "Could not synthesize a confident fix for the reported issue.",
                "patches": [],
                "tests_verified": False,
            }

        # 4. Generate FilePatch objects
        patches: List[FilePatch] = []
        for rel_path, proposed_content in fixed_files.items():
            orig_content = self.index.get_file_content(rel_path) or ""
            patch = self.patch_manager.create_patch(rel_path, orig_content, proposed_content)
            patches.append(patch)

        # 5. Safe verification in temporary isolated workspace
        sandbox_tests_passed = False
        sandbox_test_run: Optional[TestSuiteRun] = None

        if verify_in_sandbox and self.config.permission_level != PermissionLevel.READ_ONLY:
            with IsolatedWorkspace(self.config.abs_repo_root) as sandbox_dir:
                # Apply patches inside isolated sandbox
                for p in patches:
                    self.patch_manager.apply_patch(p, base_dir=sandbox_dir)

                # Run tests inside isolated sandbox
                sandbox_test_run = self.test_runner.run_tests(cwd=sandbox_dir)
                sandbox_tests_passed = sandbox_test_run.all_passed
                for p in patches:
                    p.verified = sandbox_tests_passed

        # Log patch proposal to audit trail
        self.audit_logger.log(
            action="PROPOSE_PATCH",
            target=bug_report[:80],
            actor="assistant",
            payload={
                "patched_files": [p.file_path for p in patches],
                "sandbox_verified": sandbox_tests_passed,
                "diffs": [p.diff for p in patches],
            },
            status="success" if sandbox_tests_passed else "pending_review",
        )

        return {
            "success": True,
            "patches": [p.to_dict() for p in patches],
            "raw_patches": patches,
            "tests_verified": sandbox_tests_passed,
            "sandbox_test_run": sandbox_test_run.to_dict() if sandbox_test_run else None,
            "baseline_test_run": baseline_run.to_dict() if baseline_run else None,
        }

    def apply_patch(self, patch: FilePatch, user_confirmed: bool = False) -> Tuple[bool, str]:
        """Applies patch with strict permission gate check."""
        if self.config.permission_level == PermissionLevel.READ_ONLY:
            msg = "Permission Denied: Operating in READ_ONLY mode. Patch application blocked."
            self.audit_logger.log("APPLY_PATCH", patch.file_path, actor="assistant", payload={"reason": msg}, status="blocked")
            return False, msg

        if self.config.permission_level == PermissionLevel.WRITE_CONFIRM and not user_confirmed:
            msg = f"User Confirmation Required: Patch to '{patch.file_path}' requires explicit authorization."
            self.audit_logger.log("APPLY_PATCH", patch.file_path, actor="assistant", payload={"reason": msg}, status="pending_approval")
            return False, msg

        # Apply patch to live repository
        success, msg, backup_path = self.patch_manager.apply_patch(patch)
        self.audit_logger.log(
            action="APPLY_PATCH",
            target=patch.file_path,
            actor="user" if user_confirmed else "assistant",
            payload={"success": success, "backup_path": backup_path, "diff": patch.diff},
            status="success" if success else "failed",
        )

        # Refresh file in index
        if success:
            self.index.build_index()

        return success, msg
