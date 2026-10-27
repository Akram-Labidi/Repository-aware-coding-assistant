import unittest
from repocortex.benchmark.runner import BenchmarkRunner
from repocortex.benchmark.datasets import BENCHMARK_TASKS


class TestBenchmarkSuite(unittest.TestCase):
    def test_single_benchmark_task(self):
        # Run first task
        task = BENCHMARK_TASKS[0]
        runner = BenchmarkRunner([task])
        res = runner.evaluate_single_task(task)

        self.assertEqual(res.task_id, task.id)
        self.assertTrue(res.localized_correctly)
        self.assertTrue(res.patch_synthesized)
        self.assertTrue(res.tests_passed_after_patch)
        self.assertTrue(res.safety_passed)
        self.assertTrue(res.audit_verified)

    def test_benchmark_runner_summary(self):
        tasks = BENCHMARK_TASKS[:2]
        runner = BenchmarkRunner(tasks)
        summary = runner.run_benchmark()

        self.assertEqual(summary["total_tasks"], 2)
        self.assertEqual(summary["localization_accuracy_pct"], 100.0)
        self.assertEqual(summary["test_pass_rate_pct"], 100.0)
        self.assertEqual(summary["safety_compliance_pct"], 100.0)
        self.assertEqual(summary["audit_integrity_pct"], 100.0)


if __name__ == "__main__":
    unittest.main()
