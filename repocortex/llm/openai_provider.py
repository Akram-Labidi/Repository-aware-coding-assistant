"""OpenAI / Ollama / Local LLM provider using standard library HTTP."""

from __future__ import annotations
import json
import os
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

from repocortex.core.types import ContextWindow
from repocortex.llm.provider import LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    """Integrates with OpenAI API or local Ollama/vLLM/LM-Studio server."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "gpt-4o",
    ):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")).rstrip("/")
        self.model = model

    def _call_api(self, messages: List[Dict[str, str]]) -> str:
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
                return ""
        except Exception as e:
            raise RuntimeError(f"OpenAI/Ollama API Error: {str(e)}")

    def generate_response(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return self._call_api(messages)

    def diagnose_and_fix(
        self,
        context: ContextWindow,
        task_description: str,
        failing_test_output: Optional[str] = None,
    ) -> Dict[str, str]:
        system_instruction = (
            "You are RepoCortex, an expert repository-aware software engineer. "
            "Analyze the codebase context, symbol graph, and failing test output. "
            "Propose the minimal, correct bug fix. "
            "You MUST output the complete updated content of any modified files in JSON format: "
            '{"files": [{"path": "relative/path/to/file.py", "content": "FULL FIXED FILE CONTENT"}]}'
        )

        user_prompt = f"TASK DESCRIPTION:\n{task_description}\n\n"
        if failing_test_output:
            user_prompt += f"FAILING TEST TRACE:\n{failing_test_output}\n\n"

        user_prompt += "CODEBASE CONTEXT:\n"
        for snip in context.snippets:
            user_prompt += f"\n--- FILE: {snip['file_path']} ---\n{snip['content']}\n"

        user_prompt += "\nPlease return strictly valid JSON containing the fixed files."

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_prompt},
        ]
        response_text = self._call_api(messages)

        try:
            clean_text = response_text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            if clean_text.startswith("```"):
                clean_text = clean_text[3:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]

            parsed = json.loads(clean_text.strip())
            files_dict: Dict[str, str] = {}
            for item in parsed.get("files", []):
                files_dict[item["path"]] = item["content"]
            return files_dict
        except Exception:
            return {}
