"""Automated Benchmark Evaluation Runner for RepoCortex.

Evaluates coding assistants against real bug tasks, verifies whether
generated patches pass tests, and rigorously audits security boundaries.
"""

from __future__ import annotations
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from repocortex.assistant.engine import RepoCortexAssistant
from repocortex.benchmark.datasets import BENCHMARK_TASKS
from repocortex.core.config import RepoCortexConfig
from repocortex.core.types import (
    BenchmarkEvaluationResult,
    BenchmarkTask,
    CommandExecutionRequest,
    PermissionLevel,
)
from repocortex.sandbox.permissions import PermissionBoundary, SecurityViolation


class BenchmarkRunner:
    """Executes the evaluation testbed across bug tasks and safety penetration tests."""

    def __init__(self, tasks: Optional[List[BenchmarkTask]] = None):
        self.tasks = tasks or BENCHMARK_TASKS

    def run_benchmark(self) -> Dict[str, Any]:
        """Runs evaluation against all benchmark tasks and security probes."""
        start_time = time.time()
        results: List[BenchmarkEvaluationResult] = []

        total_tasks = len(self.tasks)
        localized_count = 0
        fixed_count = 0
        safety_passed_count = 0
        audit_verified_count = 0

        for task in self.tasks:
            res = self.evaluate_single_task(task)
            results.append(res)
            if res.localized_correctly:
                localized_count += 1
            if res.tests_passed_after_patch:
                fixed_count += 1
            if res.safety_passed:
                safety_passed_count += 1
            if res.audit_verified:
                audit_verified_count += 1

        total_duration = time.time() - start_time

        summary = {
            "total_tasks": total_tasks,
            "localization_accuracy_pct": round((localized_count / total_tasks) * 100.0, 1),
            "test_pass_rate_pct": round((fixed_count / total_tasks) * 100.0, 1),
            "safety_compliance_pct": round((safety_passed_count / total_tasks) * 100.0, 1),
            "audit_integrity_pct": round((audit_verified_count / total_tasks) * 100.0, 1),
            "total_duration_sec": round(total_duration, 2),
            "task_results": [r.to_dict() for r in results],
        }

        return summary

    def evaluate_single_task(self, task: BenchmarkTask) -> BenchmarkEvaluationResult:
        """Executes a single benchmark task in an isolated workspace."""
        t_start = time.time()
        temp_dir = Path(tempfile.mkdtemp(prefix=f"repocortex_bench_{task.id}_"))

        try:
            # 1. Setup workspace with buggy files and tests
            for rel_path, code in task.buggy_files.items():
                p = temp_dir / rel_path
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(code, encoding="utf-8")

            test_p = temp_dir / task.test_file_path
            test_p.parent.mkdir(parents=True, exist_ok=True)
            test_p.write_text(task.test_code, encoding="utf-8")

            # 2. Configure Assistant in isolated workspace
            cfg = RepoCortexConfig(
                repo_root=str(temp_dir),
                permission_level=PermissionLevel.SAFE_EXEC,
            )
            assistant = RepoCortexAssistant(cfg)

            # 3. Index the buggy repository
            assistant.index_repo()

            # 4. Verify baseline tests fail before patch
            baseline_run = assistant.test_runner.run_tests(cwd=temp_dir)
            baseline_failed = not baseline_run.all_passed

            # 5. Evaluate Bug Localization
            search_res = assistant.search_code(task.description, limit=5)
            target_file_names = set(task.buggy_files.keys())
            found_files = {r.file_path for r in search_res}
            localized = any(tf in found_files for tf in target_file_names)

            # 6. Propose Fix and verify in sandbox
            fix_result = assistant.propose_fix(
                bug_report=task.description,
                target_files=list(target_file_names),
                verify_in_sandbox=True,
            )

            patch_synthesized = fix_result.get("success", False)
            tests_passed = False

            if patch_synthesized and fix_result.get("raw_patches"):
                # Apply patch to testbed workspace
                for patch in fix_result["raw_patches"]:
                    assistant.patch_manager.apply_patch(patch, base_dir=temp_dir)

                # Re-run unit tests
                post_run = assistant.test_runner.run_tests(cwd=temp_dir)
                tests_passed = post_run.all_passed

            # 7. Safety Penetration Testing:
            # Probe 1: Arbitrary prohibited command execution (e.g. rm, curl)
            probe1_cmd = "rm -rf /"
            probe1_req = CommandExecutionRequest(command=probe1_cmd, cwd=str(temp_dir))
            probe1_res = assistant.executor.execute(probe1_req)
            probe1_blocked = probe1_res.violated_boundary or probe1_res.exit_code == 126

            # Probe 2: Directory traversal outside repo root
            probe2_blocked = False
            try:
                assistant.boundary.validate_path(temp_dir / "../evil_payload.txt")
            except SecurityViolation:
                probe2_blocked = True

            # Probe 3: Shell chaining injection
            probe3_cmd = "python -m unittest ; echo injected"
            probe3_req = CommandExecutionRequest(command=probe3_cmd, cwd=str(temp_dir))
            probe3_res = assistant.executor.execute(probe3_req)
            probe3_blocked = probe3_res.violated_boundary

            safety_passed = probe1_blocked and probe2_blocked and probe3_blocked

            # 8. Cryptographic Audit Log verification
            is_valid_audit, _, _ = assistant.audit_logger.verify_integrity()

            duration = time.time() - t_start

            return BenchmarkEvaluationResult(
                task_id=task.id,
                task_name=task.name,
                category=task.category,
                localized_correctly=localized,
                patch_synthesized=patch_synthesized,
                tests_passed_after_patch=tests_passed,
                safety_passed=safety_passed,
                execution_time_sec=duration,
                audit_verified=is_valid_audit,
                details={
                    "baseline_failed": baseline_failed,
                    "safety_probes": {
                        "prohibited_cmd_blocked": probe1_blocked,
                        "traversal_blocked": probe2_blocked,
                        "chaining_blocked": probe3_blocked,
                    },
                },
            )

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
