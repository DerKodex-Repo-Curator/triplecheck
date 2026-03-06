"""Claude CLI provider — shells out to `claude -p`."""

from __future__ import annotations

import json
import re
import subprocess

from triplecheck.providers.base import BaseProvider
from triplecheck.state import FileContent, Finding, FixResult, Verdict


class ClaudeCLIProvider(BaseProvider):
    """Provider that uses the Claude Code CLI (`claude -p`)."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.model = config.get("model", "sonnet")  # opus, sonnet, haiku

    def _run_claude(self, prompt: str) -> str:
        cmd = [
            "claude", "-p",
            "--model", self.model,
            "--output-format", "text",
        ]
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            raise RuntimeError(f"claude CLI failed: {result.stderr[:500]}")
        return result.stdout

    def _extract_json(self, text: str) -> str:
        m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
        if m:
            return m.group(1).strip()
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
        file_parts = []
        for f in files:
            file_parts.append(f"## {f.path}\n```{f.language}\n{f.content}\n```")
        prompt = f"{system_prompt}\n\n"
        prompt += "Review the following files:\n\n" + "\n\n".join(file_parts)
        if previous_feedback:
            prompt += "\n\nPrevious review feedback:\n" + json.dumps(previous_feedback, indent=2)

        raw = self._run_claude(prompt)
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
        prompt = (
            f"{system_prompt}\n\n"
            f"## {file.path}\n```{file.language}\n{file.content}\n```\n\n"
            f"Findings to address:\n{findings_json}"
        )

        raw = self._run_claude(prompt)
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
        prompt = f"{system_prompt}\n\n{session_history}"
        raw = self._run_claude(prompt)
        try:
            data = json.loads(self._extract_json(raw))
        except json.JSONDecodeError:
            return Verdict.from_dict({
                "status": "partial",
                "score": 0,
                "summary": f"Failed to parse judge response: {raw[:200]}",
            })
        return Verdict.from_dict(data)
