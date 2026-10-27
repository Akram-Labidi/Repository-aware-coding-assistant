"""Google Gemini API Provider implementation using standard library HTTP."""

from __future__ import annotations
import json
import os
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

from repocortex.core.types import ContextWindow
from repocortex.llm.provider import LLMProvider


class GeminiProvider(LLMProvider):
    """Integrates with Google Gemini API (Gemini 1.5 Flash/Pro, Gemini 2.0)."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-1.5-pro"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model = model
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"

    def _call_gemini(self, contents: List[Dict[str, Any]], system_instruction: Optional[str] = None) -> str:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not configured.")

        url = f"{self.base_url}/{self.model}:generateContent?key={self.api_key}"
        body: Dict[str, Any] = {"contents": contents}

        if system_instruction:
            body["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        data_bytes = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                candidates = res_data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "")
                return ""
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Gemini API Error {e.code}: {error_body}")
        except Exception as e:
            raise RuntimeError(f"Failed to communicate with Gemini API: {str(e)}")

    def generate_response(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        contents = [{"parts": [{"text": prompt}]}]
        return self._call_gemini(contents, system_instruction=system_prompt)

    def diagnose_and_fix(
        self,
        context: ContextWindow,
        task_description: str,
        failing_test_output: Optional[str] = None,
    ) -> Dict[str, str]:
        """Prompts Gemini to diagnose the bug and output patched file contents."""
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

        response_text = self._call_gemini(
            [{"parts": [{"text": user_prompt}]}],
            system_instruction=system_instruction,
        )

        # Parse JSON from response
        try:
            # Strip markdown json blocks if present
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
