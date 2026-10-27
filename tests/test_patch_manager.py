import unittest
import tempfile
import shutil
from pathlib import Path
from repocortex.core.config import RepoCortexConfig
from repocortex.core.types import PermissionLevel
from repocortex.sandbox.patch_manager import PatchManager


class TestPatchManager(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = RepoCortexConfig(
            repo_root=str(self.tmp),
            permission_level=PermissionLevel.SAFE_EXEC,
        )
        self.pm = PatchManager(self.cfg)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_diff_creation(self):
        orig = "def add(a, b):\n    return a - b\n"
        proposed = "def add(a, b):\n    return a + b\n"
        patch = self.pm.create_patch("calc.py", orig, proposed)

        self.assertEqual(patch.action, "modify")
        self.assertIn("-    return a - b", patch.diff)
        self.assertIn("+    return a + b", patch.diff)

    def test_atomic_apply_and_rollback(self):
        target = self.tmp / "calc.py"
        orig = "def add(a, b):\n    return a - b\n"
        target.write_text(orig, encoding="utf-8")

        proposed = "def add(a, b):\n    return a + b\n"
        patch = self.pm.create_patch("calc.py", orig, proposed)

        # Apply
        success, msg, backup = self.pm.apply_patch(patch)
        self.assertTrue(success)
        self.assertEqual(target.read_text(encoding="utf-8"), proposed)
        self.assertIsNotNone(backup)

        # Rollback
        restored = self.pm.rollback("calc.py", backup)
        self.assertTrue(restored)
        self.assertEqual(target.read_text(encoding="utf-8"), orig)


if __name__ == "__main__":
    unittest.main()
