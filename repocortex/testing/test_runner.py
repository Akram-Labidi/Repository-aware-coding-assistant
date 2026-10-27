"""Automated Test Discovery and Execution Engine.

Executes test suites within sandbox boundaries, parses stdout/stderr,
and structures test results into pass/fail/error diagnostics.
"""

from __future__ import annotations
import os
import re
import sys
import time
from pathlib import Path
from typing import List, Optional

from repocortex.core.config import RepoCortexConfig
from repocortex.core.types import (
    CommandExecutionRequest,
    CommandExecutionResult,
    TestResult,
    TestSuiteRun,
)
from repocortex.sandbox.executor import SandboxExecutor


class TestRunner:
    """Executes test suites and parses granular test outcomes."""

    def __init__(self, config: RepoCortexConfig, executor: Optional[SandboxExecutor] = None):
        self.config = config
        self.executor = executor or SandboxExecutor(config)

    def run_tests(
        self,
        test_target: Optional[str] = None,
        cwd: Optional[Path] = None,
        timeout_sec: float = 25.0,
    ) -> TestSuiteRun:
        """Runs test target or discovers all tests in repository."""
        work_dir = (cwd or self.config.abs_repo_root).resolve()
        python_bin = sys.executable

        # Ensure tests directory has __init__.py if tests exists
        tests_dir = work_dir / "tests"
        if tests_dir.exists() and tests_dir.is_dir():
            init_file = tests_dir / "__init__.py"
            if not init_file.exists():
                try:
                    init_file.write_text("", encoding="utf-8")
                except Exception:
                    pass

        # Find test files in work_dir
        if test_target:
            cmd = f"{python_bin} -m unittest {test_target}"
        else:
            test_files = list(work_dir.glob("test_*.py")) + list(work_dir.glob("tests/test_*.py"))
            if test_files:
                # Relative paths formatted with forward slashes for python invocation
                rel_paths = []
                for tf in test_files:
                    try:
                        rel_paths.append(str(tf.relative_to(work_dir)).replace("\\", "/"))
                    except ValueError:
                        rel_paths.append(str(tf).replace("\\", "/"))
                cmd = f"{python_bin} -m unittest {' '.join(rel_paths)}"
            else:
                cmd = f"{python_bin} -m unittest discover -s . -p test_*.py"

        req = CommandExecutionRequest(
            command=cmd,
            cwd=str(work_dir),
            timeout_sec=timeout_sec,
            is_test_execution=True,
        )

        exec_res = self.executor.execute(req)
        return self._parse_unittest_output(exec_res)

    def _parse_unittest_output(self, res: CommandExecutionResult) -> TestSuiteRun:
        """Parses output from standard python -m unittest."""
        raw_output = (res.stdout + "\n" + res.stderr).strip()

        total = 0
        passed = 0
        failed = 0
        errors = 0
        results: List[TestResult] = []

        # Check for: Ran X tests in Ys
        summary_match = re.search(r"Ran (\d+) tests? in ([\d\.]+)s", raw_output)
        duration_sec = float(summary_match.group(2)) if summary_match else (res.duration_ms / 1000.0)
        if summary_match:
            total = int(summary_match.group(1))

        # Check if FAILED (failures=X, errors=Y)
        failed_match = re.search(r"FAILED \((?:failures=(\d+))?(?:, )?(?:errors=(\d+))?\)", raw_output)
        if failed_match:
            f_str = failed_match.group(1)
            e_str = failed_match.group(2)
            failed = int(f_str) if f_str else 0
            errors = int(e_str) if e_str else 0
            passed = max(0, total - failed - errors)
            all_passed = False
        elif "OK" in raw_output and res.exit_code == 0 and total > 0:
            passed = total
            all_passed = True
        else:
            # Execution error or timeout
            if res.timed_out:
                errors = max(1, total)
                all_passed = False
            elif res.exit_code != 0:
                errors = max(1, total)
                all_passed = False
            else:
                passed = total
                all_passed = (total > 0)

        # Parse individual test traces if failures exist
        if not all_passed:
            results.append(
                TestResult(
                    test_name="TestSuiteFailure",
                    status="failed" if failed > 0 else "error",
                    duration_sec=duration_sec,
                    stdout=res.stdout,
                    stderr=res.stderr,
                    error_trace=raw_output,
                )
            )
        else:
            results.append(
                TestResult(
                    test_name="TestSuiteRun",
                    status="passed",
                    duration_sec=duration_sec,
                    stdout=res.stdout,
                    stderr=res.stderr,
                )
            )

        return TestSuiteRun(
            total=total,
            passed=passed,
            failed=failed,
            errors=errors,
            duration_sec=duration_sec,
            results=results,
            all_passed=all_passed,
            raw_output=raw_output,
        )
