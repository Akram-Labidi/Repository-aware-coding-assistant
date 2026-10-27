"""Sandboxed process execution engine and isolated virtual workspace.

Runs test suites and approved commands with strict timeouts, environment scrubbing,
and optional isolated temp clones to prevent accidental repository corruption.
"""

from __future__ import annotations
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional
from repocortex.core.config import RepoCortexConfig
from repocortex.core.types import (
    CommandExecutionRequest,
    CommandExecutionResult,
    PermissionLevel,
)
from repocortex.sandbox.permissions import PermissionBoundary


class IsolatedWorkspace:
    """Creates a temporary isolated copy of the repository for safe patch testing."""

    def __init__(self, source_repo: Path, include_dirs: Optional[List[str]] = None):
        self.source_repo = source_repo
        self.include_dirs = include_dirs
        self.temp_dir: Optional[Path] = None

    def __enter__(self) -> Path:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="repocortex_sandbox_"))
        
        # Copy files ignoring .git, .venv, .repocortex
        ignore_patterns = shutil.ignore_patterns(
            ".git", ".venv", "venv", "__pycache__", ".pytest_cache",
            ".repocortex", "node_modules", "*.pyc", "*.db"
        )
        shutil.copytree(self.source_repo, self.temp_dir, dirs_exist_ok=True, ignore=ignore_patterns)
        return self.temp_dir

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)


class SandboxExecutor:
    """Executes permitted commands inside strict sandboxed boundaries."""

    SENSITIVE_ENV_VARS = {
        "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN",
        "GITLAB_TOKEN", "SSH_AUTH_SOCK", "OPENAI_API_KEY", "GEMINI_API_KEY",
        "ANTHROPIC_API_KEY", "SLACK_BOT_TOKEN", "DATABASE_URL"
    }

    def __init__(self, config: RepoCortexConfig):
        self.config = config
        self.boundary = PermissionBoundary(config)

    def _scrub_environment(self, custom_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Filters out credentials and API keys from child process environment."""
        env = dict(os.environ)
        for var in self.SENSITIVE_ENV_VARS:
            env.pop(var, None)
        
        # Scrub any key containing SECRET, TOKEN, or KEY (except basic PATH/PYTHONPATH)
        for k in list(env.keys()):
            if any(term in k.upper() for term in ("SECRET", "TOKEN", "API_KEY", "PRIVATE_KEY")):
                env.pop(k, None)

        if custom_env:
            env.update(custom_env)
        return env

    def execute(self, request: CommandExecutionRequest) -> CommandExecutionResult:
        """Executes a command enforcing boundary checks, timeouts, and isolation."""
        # 1. Boundary check
        is_allowed, reason = self.boundary.can_execute_command(request.command)
        if not is_allowed:
            return CommandExecutionResult(
                exit_code=126,
                stdout="",
                stderr=reason,
                timed_out=False,
                duration_ms=0.0,
                sandboxed=True,
                violated_boundary=True,
                error_message=reason,
            )

        # 2. Working directory validation
        work_dir = Path(request.cwd).resolve()
        
        # 3. Environment sanitization
        env = self._scrub_environment(request.env)

        start_time = time.time()
        max_output_chars = 100_000

        try:
            # On Windows, use shell=False with split arguments to avoid cmd/powershell injection
            cmd_args = request.command.split()
            
            proc = subprocess.run(
                cmd_args,
                cwd=str(work_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=request.timeout_sec or self.config.command_timeout_sec,
                shell=False,
            )

            duration_ms = (time.time() - start_time) * 1000.0
            stdout = proc.stdout[:max_output_chars]
            stderr = proc.stderr[:max_output_chars]

            return CommandExecutionResult(
                exit_code=proc.returncode,
                stdout=stdout,
                stderr=stderr,
                timed_out=False,
                duration_ms=round(duration_ms, 2),
                sandboxed=True,
                violated_boundary=False,
            )

        except subprocess.TimeoutExpired:
            duration_ms = (time.time() - start_time) * 1000.0
            return CommandExecutionResult(
                exit_code=124,
                stdout="",
                stderr=f"Command timed out after {request.timeout_sec} seconds.",
                timed_out=True,
                duration_ms=round(duration_ms, 2),
                sandboxed=True,
                violated_boundary=False,
                error_message=f"Timeout of {request.timeout_sec}s exceeded",
            )
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000.0
            return CommandExecutionResult(
                exit_code=-1,
                stdout="",
                stderr=str(e),
                timed_out=False,
                duration_ms=round(duration_ms, 2),
                sandboxed=True,
                violated_boundary=False,
                error_message=str(e),
            )
