"""Abstract LLM Provider interface."""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from repocortex.core.types import ContextWindow, FilePatch


class LLMProvider(ABC):
    """Abstract interface for LLM backends (Local, Gemini, OpenAI/Ollama, Anthropic)."""

    @abstractmethod
    def generate_response(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generates conversational or analytical text response."""
        pass

    @abstractmethod
    def diagnose_and_fix(
        self,
        context: ContextWindow,
        task_description: str,
        failing_test_output: Optional[str] = None,
    ) -> Dict[str, str]:
        """Analyzes bug context and returns dict of {file_path: fixed_file_content}."""
        pass
