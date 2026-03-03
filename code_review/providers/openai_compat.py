"""OpenAI-compatible API provider (works with Qwen, DeepSeek, OpenRouter, vLLM, etc.)."""

from __future__ import annotations

import json
import os
import re

import httpx

from code_review.providers.base import BaseProvider
from code_review.state import FileContent, Finding, FixResult, Verdict


class OpenAICompatProvider(BaseProvider):
    """Provider for any OpenAI-compatible chat completions API."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.base_url = config.get("base_url", "http://localhost:8000").rstrip("/")
        self.model = config.get("model", "default")
        self.max_tokens = config.get("max_tokens", 8192)
        self.temperature = config.get("temperature", 0.1)
        api_key_env = config.get("api_key_env", "")
        self.api_key = os.environ.get(api_key_env, "no-key") if api_key_env else "no-key"

    def _chat(self, system: str, user: str) -> str:
        url = f"{self.base_url}/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        resp = httpx.post(url, json=payload, headers=headers, timeout=300)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _extract_json(self, text: str) -> str:
        """Extract JSON from markdown code blocks or raw text."""
        # Try ```json ... ``` block first
        m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
        if m:
            return m.group(1).strip()
        # Try raw JSON (array or object)
        m = re.search(r"(\[.*\]|\{.*\})", text, re.DOTALL)
        if m:
            return m.group(1).strip()
        return text.strip()

    def review(
        self,
        files: list[FileContent],
        system_prompt: str,
        previous_feedback: list[dict] | None = None,
    ) -> list[Finding]:
        user_parts = []
        for f in files:
            user_parts.append(f"## {f.path}\n```{f.language}\n{f.content}\n```")
        user_msg = "Review the following files:\n\n" + "\n\n".join(user_parts)
        if previous_feedback:
            user_msg += "\n\nPrevious review feedback:\n" + json.dumps(previous_feedback, indent=2)

        raw = self._chat(system_prompt, user_msg)
        try:
            data = json.loads(self._extract_json(raw))
        except json.JSONDecodeError:
            return []

        if isinstance(data, list):
            return [Finding.from_dict(d) for d in data]
        return []

    def fix(
        self,
        file: FileContent,
        findings: list[Finding],
        system_prompt: str,
    ) -> FixResult:
        findings_json = json.dumps([f.to_dict() for f in findings], indent=2)
        user_msg = (
            f"## {file.path}\n```{file.language}\n{file.content}\n```\n\n"
            f"Findings to address:\n{findings_json}"
        )

        raw = self._chat(system_prompt, user_msg)
        try:
            data = json.loads(self._extract_json(raw))
        except json.JSONDecodeError:
            return FixResult(
                file=str(file.path), applied=False,
                original=file.content, fixed=file.content,
                explanation="Failed to parse coder response",
            )

        applied = data.get("applied", False)
        fixed = data.get("fixed_content", "") if applied else file.content
        return FixResult(
            file=str(file.path),
            applied=applied,
            original=file.content,
            fixed=fixed,
            explanation=data.get("explanation", ""),
            findings_addressed=data.get("findings_addressed", []),
        )

    def judge(self, session_history: str, system_prompt: str) -> Verdict:
        raw = self._chat(system_prompt, session_history)
        try:
            data = json.loads(self._extract_json(raw))
        except json.JSONDecodeError:
            return Verdict.from_dict({
                "status": "partial",
                "score": 0,
                "summary": f"Failed to parse judge response: {raw[:200]}",
            })
        return Verdict.from_dict(data)
