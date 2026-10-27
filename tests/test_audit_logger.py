import unittest
import tempfile
import shutil
import json
from pathlib import Path
from repocortex.core.config import RepoCortexConfig
from repocortex.security.audit_logger import AuditLogger


class TestAuditLogger(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = RepoCortexConfig(repo_root=str(self.tmp))
        self.logger = AuditLogger(self.cfg)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_log_and_verify(self):
        self.logger.log("INDEX", "repo_root", actor="assistant")
        self.logger.log("SEARCH", "query_term", actor="user")
        self.logger.log("PROPOSE_PATCH", "service.py", actor="assistant")

        is_valid, msg, count = self.logger.verify_integrity()
        self.assertTrue(is_valid)
        self.assertEqual(count, 3)

    def test_tamper_detection(self):
        self.logger.log("ACTION_1", "target_1")
        self.logger.log("ACTION_2", "target_2")

        # Corrupt one entry in the log file
        log_file = self.cfg.audit_log_path
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        data = json.loads(lines[0])
        data["payload"]["forged"] = True
        lines[0] = json.dumps(data) + "\n"

        with open(log_file, "w", encoding="utf-8") as f:
            f.writelines(lines)

        is_valid, msg, count = self.logger.verify_integrity()
        self.assertFalse(is_valid)
        self.assertIn("Tamper detected", msg)


if __name__ == "__main__":
    unittest.main()
