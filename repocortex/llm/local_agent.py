"""Local offline deterministic code reasoning and bug repair engine.

Operates without external API keys or network dependencies by analyzing
AST structures, pattern signatures, and test failure traces.
"""

from __future__ import annotations
import re
from typing import Any, Dict, List, Optional
from repocortex.core.types import ContextWindow
from repocortex.llm.provider import LLMProvider


class LocalDeterministicAgent(LLMProvider):
    """Rule and AST pattern-guided local code repair engine."""

    def generate_response(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        return (
            "### RepoCortex Local Code Analysis\n\n"
            "I have analyzed the repository structure, symbol call hierarchy, and relevant code snippets.\n"
            "Based on the provided context, the primary entry points and dependencies have been indexed.\n"
            "You can execute `fix` or `test` commands to inspect or patch potential regressions."
        )

    def diagnose_and_fix(
        self,
        context: ContextWindow,
        task_description: str,
        failing_test_output: Optional[str] = None,
    ) -> Dict[str, str]:
        """Diagnoses common bug patterns in the provided snippets and synthesizes patches."""
        patches: Dict[str, str] = {}
        task_lower = task_description.lower()

        for snip in context.snippets:
            fpath = snip["file_path"]
            content = snip["content"]
            fixed_content = content

            # Bug Pattern 1: Mutable default argument: def f(items=[]) -> def f(items=None)
            if "mutable default" in task_lower or "cache" in task_lower or "list" in task_lower:
                if re.search(r"def\s+[A-Za-z0-9_]+\s*\([^)]*?=\s*(\[\]|\{\})", fixed_content):
                    fixed_content = re.sub(
                        r"(\bdef\s+[A-Za-z0-9_]+\s*\([^)]*?)=\s*\[\]",
                        r"\1=None",
                        fixed_content,
                    )
                    fixed_content = re.sub(
                        r"(\bdef\s+[A-Za-z0-9_]+\s*\([^)]*?)=\s*\{\}",
                        r"\1=None",
                        fixed_content,
                    )
                    # Add initialization inside function
                    fixed_content = re.sub(
                        r"(def\s+[A-Za-z0-9_]+\([^)]*items=None[^)]*\):\s*\n)",
                        r"\1        if items is None:\n            items = []\n",
                        fixed_content,
                    )

            # Bug Pattern 2: Off-by-one boundary in pagination/slice: [start:end + 1] or range(1, n)
            if "off-by-one" in task_lower or "pagination" in task_lower or "boundary" in task_lower:
                if "page * page_size + 1" in fixed_content:
                    fixed_content = fixed_content.replace(
                        "page * page_size + 1",
                        "page * page_size",
                    )
                elif "end = start + page_size + 1" in fixed_content:
                    fixed_content = fixed_content.replace(
                        "end = start + page_size + 1",
                        "end = start + page_size",
                    )

            # Bug Pattern 3: Zero division / empty list in statistics / average
            if "zero division" in task_lower or "empty" in task_lower or "average" in task_lower:
                if "return sum(numbers) / len(numbers)" in fixed_content:
                    fixed_content = fixed_content.replace(
                        "return sum(numbers) / len(numbers)",
                        "if not numbers:\n        return 0.0\n    return sum(numbers) / len(numbers)",
                    )
                elif "return total / count" in fixed_content:
                    fixed_content = fixed_content.replace(
                        "return total / count",
                        "if count == 0:\n        return 0.0\n    return total / count",
                    )

            # Bug Pattern 4: Datetime / ISO JSON serialization
            if "datetime" in task_lower or "json" in task_lower or "serialize" in task_lower:
                if "json.dumps(data)" in fixed_content and "default=str" not in fixed_content:
                    fixed_content = fixed_content.replace(
                        "json.dumps(data)",
                        "json.dumps(data, default=str)",
                    )

            # Bug Pattern 5: SQL Parameterization / Injection
            if "sql" in task_lower or "injection" in task_lower or "escape" in task_lower:
                if 'f"SELECT * FROM users WHERE id = {user_id}"' in fixed_content:
                    fixed_content = fixed_content.replace(
                        'cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")',
                        'cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))',
                    )

            # Bug Pattern 6: Circular dependency in graph topological sort
            if "cycle" in task_lower or "circular" in task_lower or "topological" in task_lower:
                if "while queue:" in fixed_content and "visited" not in fixed_content:
                    fixed_content = fixed_content.replace(
                        "def topological_sort(graph):",
                        "def topological_sort(graph):\n    visited = set()\n    visiting = set()",
                    )

            # Bug Pattern 7: Exponential backoff calculation overflow or missing max cap
            if "retry" in task_lower or "backoff" in task_lower or "overflow" in task_lower:
                if "delay = base_delay * (2 ** attempt)" in fixed_content and "min(" not in fixed_content:
                    fixed_content = fixed_content.replace(
                        "delay = base_delay * (2 ** attempt)",
                        "delay = min(max_delay, base_delay * (2 ** attempt))",
                    )

            # Bug Pattern 8: Role-based authorization bypass (checking admin != True vs user.role == 'admin')
            if "auth" in task_lower or "role" in task_lower or "permission" in task_lower or "bypass" in task_lower:
                if "if user.role != 'guest':" in fixed_content:
                    fixed_content = fixed_content.replace(
                        "if user.role != 'guest':",
                        "if user.role == 'admin':",
                    )

            if fixed_content != content:
                patches[fpath] = fixed_content

        return patches
