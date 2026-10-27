import unittest
import tempfile
import shutil
from pathlib import Path
from repocortex.core.config import RepoCortexConfig
from repocortex.indexer.repository_index import RepositoryIndex
from repocortex.context.context_selector import ContextSelector


class TestContextSelector(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = RepoCortexConfig(repo_root=str(self.tmp))
        
        # Create sample files
        (self.tmp / "service.py").write_text("""
def process_order(order_id):
    '''Processes a customer order.'''
    return True
""", encoding="utf-8")

        tests_dir = self.tmp / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_service.py").write_text("""
import unittest
from service import process_order

class TestService(unittest.TestCase):
    def test_process(self):
        self.assertTrue(process_order(123))
""", encoding="utf-8")

        self.index = RepositoryIndex(self.cfg)
        self.index.build_index()
        self.selector = ContextSelector(self.index, self.cfg)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_select_context_finds_file_and_tests(self):
        ctx = self.selector.select_context("process_order", max_tokens=4000)
        self.assertIn("service.py", ctx.files)
        # Should include relevant snippets
        snip_files = [s["file_path"] for s in ctx.snippets]
        self.assertIn("service.py", snip_files)
        self.assertIn("tests/test_service.py", snip_files)


if __name__ == "__main__":
    unittest.main()
