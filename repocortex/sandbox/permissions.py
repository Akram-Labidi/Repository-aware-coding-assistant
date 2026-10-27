"""Permission boundary verification and security policy enforcement.

Enforces read-only analysis, path confinement, command whitelists,
and strictly blocks unauthorized execution or file modifications.
"""

from __future__ import annotations
import os
import re
from pathlib import Path
from typing import List, Optional, Set, Tuple
from repocortex.core.config import RepoCortexConfig
from repocortex.core.types import PermissionLevel


class SecurityViolation(Exception):
    """Raised when an operation attempts to breach security boundaries."""
    pass


class PermissionBoundary:
    """Enforces strict capability controls on filesystem and process execution."""

    DANGEROUS_SHELL_CHARS = {";", "&", "|", "`", "$", "(", ")", ">", "<", "!"}

    def __init__(self, config: RepoCortexConfig):
        self.config = config
        self.repo_root = config.abs_repo_root

    def validate_path(self, target_path: str | Path, allow_create: bool = False) -> Path:
        """Ensures path resides strictly inside repo_root and is not protected."""
        p = Path(target_path)
        if not p.is_absolute():
            p = (self.repo_root / p).resolve()
        else:
            p = p.resolve()

        # 1. Path traversal check: must start with repo_root
        try:
            p.relative_to(self.repo_root)
        except ValueError:
            raise SecurityViolation(
                f"Path traversal blocked: '{target_path}' is outside repository root '{self.repo_root}'"
            )

        # 2. Protected paths check (.git, .env, secrets)
        rel_parts = p.relative_to(self.repo_root).parts
        for part in rel_parts:
            for protected in self.config.protected_paths:
                if protected.startswith("*."):
                    ext = protected[1:]
                    if part.endswith(ext):
                        raise SecurityViolation(f"Access to protected pattern '{protected}' is forbidden: {p}")
                elif part == protected:
                    raise SecurityViolation(f"Access to protected directory/file '{protected}' is forbidden: {p}")

        return p

    def can_read_file(self, target_path: str | Path) -> Tuple[bool, str]:
        try:
            self.validate_path(target_path)
            return True, "Allowed"
        except SecurityViolation as e:
            return False, str(e)

    def can_modify_file(self, target_path: str | Path) -> Tuple[bool, str]:
        if self.config.permission_level == PermissionLevel.READ_ONLY:
            return False, "Modifications blocked: Assistant is operating in READ_ONLY mode."

        try:
            self.validate_path(target_path)
            return True, "Allowed"
        except SecurityViolation as e:
            return False, str(e)

    def can_execute_command(self, command: str) -> Tuple[bool, str]:
        """Validates command against execution whitelist, blacklist, and shell injections."""
        if self.config.permission_level == PermissionLevel.READ_ONLY:
            return False, "Command execution blocked: Assistant is in READ_ONLY mode."

        if not command or not command.strip():
            return False, "Empty command."

        cmd_clean = command.strip()

        # 1. Reject dangerous shell chaining characters
        for char in self.DANGEROUS_SHELL_CHARS:
            if char in cmd_clean:
                return False, f"Execution blocked: Chaining character '{char}' is forbidden in sandboxed execution."

        # 2. Extract base command executable
        parts = cmd_clean.split()
        base_cmd = Path(parts[0]).name.lower()
        if base_cmd.endswith(".exe"):
            base_cmd = base_cmd[:-4]

        # 3. Check prohibited commands list
        for prohibited in self.config.prohibited_commands:
            if base_cmd == prohibited or prohibited in cmd_clean.lower():
                return False, f"Execution blocked: Prohibited binary/utility '{prohibited}' detected."

        # 4. Check allowed commands list
        allowed = False
        for allowed_prefix in self.config.allowed_commands:
            if cmd_clean.startswith(allowed_prefix) or base_cmd == allowed_prefix:
                allowed = True
                break

        if not allowed:
            return False, (
                f"Execution blocked: Command '{parts[0]}' is not in allowed sandbox whitelist: "
                f"{self.config.allowed_commands}"
            )

        return True, "Allowed"
