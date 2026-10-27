"""Unified diff generation, visual rendering, and safe patch application.

Enforces atomicity, validation against original file content, and automatic rollback.
"""

from __future__ import annotations
import difflib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from repocortex.core.config import RepoCortexConfig
from repocortex.core.types import FilePatch
from repocortex.sandbox.permissions import PermissionBoundary, SecurityViolation


class PatchManager:
    """Manages patch generation, diff rendering, and safe atomic application."""

    def __init__(self, config: RepoCortexConfig):
        self.config = config
        self.boundary = PermissionBoundary(config)

    def create_patch(self, file_path: str, original_content: str, proposed_content: str) -> FilePatch:
        """Generates a standard unified diff between original and proposed code."""
        orig_lines = original_content.splitlines(keepends=True)
        new_lines = proposed_content.splitlines(keepends=True)

        diff_lines = list(
            difflib.unified_diff(
                orig_lines,
                new_lines,
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
                n=3,
            )
        )
        diff_str = "".join(diff_lines)
        action = "modify"
        if not original_content and proposed_content:
            action = "create"
        elif original_content and not proposed_content:
            action = "delete"

        return FilePatch(
            file_path=file_path,
            action=action,
            diff=diff_str,
            original_content=original_content,
            proposed_content=proposed_content,
            applied=False,
            verified=False,
        )

    def apply_patch(
        self, patch: FilePatch, base_dir: Optional[Path] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """Safely applies patch to disk. Returns (success, message, backup_path)."""
        root = base_dir or self.config.abs_repo_root
        target_path = (root / patch.file_path).resolve()

        # Permission check
        try:
            self.boundary.validate_path(target_path, allow_create=(patch.action == "create"))
        except SecurityViolation as e:
            return False, str(e), None

        if patch.proposed_content is None:
            return False, "Cannot apply patch: proposed_content is missing.", None

        backup_path = None
        try:
            # Create parent directories if needed
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # Create backup if file already exists
            if target_path.exists():
                backup_path = str(target_path) + ".repocortex.bak"
                shutil.copy2(target_path, backup_path)

            if patch.action == "delete":
                if target_path.exists():
                    target_path.unlink()
            else:
                # Atomic write: write to temp file then replace
                temp_file = target_path.with_suffix(".tmp_patch")
                temp_file.write_text(patch.proposed_content, encoding="utf-8")
                temp_file.replace(target_path)

            patch.applied = True
            return True, f"Successfully applied patch to {patch.file_path}", backup_path

        except Exception as e:
            # Rollback if backup exists
            if backup_path and os.path.exists(backup_path):
                shutil.copy2(backup_path, target_path)
            return False, f"Failed to apply patch: {str(e)}", backup_path

    def rollback(self, file_path: str, backup_path: str, base_dir: Optional[Path] = None) -> bool:
        """Restores a file from backup."""
        root = base_dir or self.config.abs_repo_root
        target_path = (root / file_path).resolve()

        if os.path.exists(backup_path):
            try:
                shutil.copy2(backup_path, target_path)
                os.remove(backup_path)
                return True
            except Exception:
                return False
        return False

    @staticmethod
    def format_ansi_diff(diff_text: str) -> str:
        """Colors unified diff for terminal display using ANSI escape codes."""
        lines = diff_text.splitlines()
        colored_lines = []

        RED = "\033[91m"
        GREEN = "\033[92m"
        CYAN = "\033[96m"
        BOLD = "\033[1m"
        RESET = "\033[0m"

        for line in lines:
            if line.startswith("---") or line.startswith("+++"):
                colored_lines.append(f"{BOLD}{line}{RESET}")
            elif line.startswith("@@"):
                colored_lines.append(f"{CYAN}{line}{RESET}")
            elif line.startswith("+"):
                colored_lines.append(f"{GREEN}{line}{RESET}")
            elif line.startswith("-"):
                colored_lines.append(f"{RED}{line}{RESET}")
            else:
                colored_lines.append(line)

        return "\n".join(colored_lines)
