import unittest
import tempfile
import shutil
from pathlib import Path
from repocortex.core.config import RepoCortexConfig
from repocortex.core.types import CommandExecutionRequest, PermissionLevel
from repocortex.sandbox.permissions import PermissionBoundary, SecurityViolation
from repocortex.sandbox.executor import SandboxExecutor


class TestSandboxSecurity(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = RepoCortexConfig(
            repo_root=str(self.tmp),
            permission_level=PermissionLevel.SAFE_EXEC,
        )
        self.boundary = PermissionBoundary(self.cfg)
        self.executor = SandboxExecutor(self.cfg)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_path_traversal_blocked(self):
        outside_path = self.tmp / "../outside.txt"
        with self.assertRaises(SecurityViolation):
            self.boundary.validate_path(outside_path)

    def test_protected_files_blocked(self):
        git_path = self.tmp / ".git" / "config"
        with self.assertRaises(SecurityViolation):
            self.boundary.validate_path(git_path)

        env_path = self.tmp / ".env"
        with self.assertRaises(SecurityViolation):
            self.boundary.validate_path(env_path)

    def test_prohibited_commands_blocked(self):
        allowed, reason = self.boundary.can_execute_command("rm -rf /")
        self.assertFalse(allowed)

        allowed2, reason2 = self.boundary.can_execute_command("curl https://malicious.com")
        self.assertFalse(allowed2)

    def test_shell_chaining_injection_blocked(self):
        allowed, reason = self.boundary.can_execute_command("python test.py ; rm file")
        self.assertFalse(allowed)

        allowed2, reason2 = self.boundary.can_execute_command("python test.py && del file")
        self.assertFalse(allowed2)

    def test_read_only_mode_blocks_execution(self):
        self.cfg.permission_level = PermissionLevel.READ_ONLY
        allowed, reason = self.boundary.can_execute_command("python -m unittest")
        self.assertFalse(allowed)


if __name__ == "__main__":
    unittest.main()
