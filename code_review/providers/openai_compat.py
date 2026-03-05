"""OpenAI-compatible API provider (works with Qwen, DeepSeek, OpenRouter, vLLM, etc.)."""

from __future__ import annotations

import json
import os
import re
import time

import click
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

    def _chat(self, system: str, user: str, retries: int = 3, prefill: str = "") -> str:
        url = f"{self.base_url}/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        if prefill:
            messages.append({"role": "assistant", "content": prefill})
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        for attempt in range(1, retries + 1):
            try:
                resp = httpx.post(url, json=payload, headers=headers, timeout=900)
                resp.raise_for_status()
                data = resp.json()
                try:
                    return data["choices"][0]["message"]["content"]
                except (KeyError, IndexError, TypeError) as e:
                    click.echo(f"      [ERROR] Unexpected API response structure: {e}")
                    click.echo(f"      [DEBUG] Response keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                    raise RuntimeError(f"Malformed API response: {e}") from e
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                body = e.response.text[:300]
                # Don't retry on 504 (gateway timeout) — payload is likely too large
                retryable = status >= 500 and status != 504
                if attempt < retries and retryable:
                    wait = 10 * attempt
                    click.echo(f"      [RETRY] HTTP {status} — waiting {wait}s then retry {attempt}/{retries}")
                    click.echo(f"      [DEBUG] Response: {body}")
                    time.sleep(wait)
                else:
                    if status == 504:
                        click.echo(f"      [ERROR] HTTP 504 timeout — batch may be too large. Try lowering batch_max_lines in config.yml")
                    else:
                        click.echo(f"      [ERROR] HTTP {status}: {body}")
                    raise
            except (httpx.ReadTimeout, httpx.RemoteProtocolError, httpx.ConnectError) as e:
                if attempt < retries:
                    wait = 10 * attempt
                    click.echo(f"      [RETRY] {type(e).__name__} — waiting {wait}s then retry {attempt}/{retries}")
                    time.sleep(wait)
                else:
                    raise

    def _extract_json(self, text: str) -> str:
        """Extract JSON from markdown code blocks or raw text."""
        # Try ```json ... ``` block first
        m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
        if m:
            return m.group(1).strip()
        # Try raw JSON — find first [ or { and match to its balanced closing bracket
        for i, ch in enumerate(text):
            if ch in ('[', '{'):
                close = ']' if ch == '[' else '}'
                depth = 0
                in_string = False
                escape = False
                for j in range(i, len(text)):
                    c = text[j]
                    if escape:
                        escape = False
                        continue
                    if c == '\\' and in_string:
                        escape = True
                        continue
                    if c == '"' and not escape:
                        in_string = not in_string
                        continue
                    if in_string:
                        continue
                    if c == ch:
                        depth += 1
                    elif c == close:
                        depth -= 1
                        if depth == 0:
                            return text[i:j+1].strip()
                break
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

        raw = self._chat(system_prompt, user_msg, prefill="[")
        raw = "[" + raw  # prepend the prefill since API doesn't echo it
        extracted = self._extract_json(raw)
        try:
            data = json.loads(extracted)
        except json.JSONDecodeError:
            click.echo(f"      [DEBUG] Failed to parse JSON from response ({len(raw)} chars)")
            click.echo(f"      [DEBUG] Raw start: {raw[:300]}")
            return []

        if isinstance(data, list):
            findings = []
            for d in data:
                try:
                    findings.append(Finding.from_dict(d))
                except (KeyError, ValueError, TypeError, AttributeError) as e:
                    click.echo(f"      [DEBUG] Skipped malformed finding: {e} — {d}")
            return findings
        click.echo(f"      [DEBUG] Response was not a list: {type(data)}")
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

        raw = self._chat(system_prompt, user_msg, prefill="{")
        raw = "{" + raw
        try:
            data = json.loads(self._extract_json(raw))
        except json.JSONDecodeError:
            return FixResult(
                file=str(file.path), applied=False,
                original=file.content, fixed=file.content,
                explanation="Failed to parse coder response",
            )

        # LLM sometimes returns a list instead of an object — take the first item
        if isinstance(data, list):
            data = data[0] if data else {}
        if not isinstance(data, dict):
            return FixResult(
                file=str(file.path), applied=False,
                original=file.content, fixed=file.content,
                explanation=f"Unexpected response type: {type(data).__name__}",
            )

        fixed_content = data.get("fixed_content", "")
        applied = data.get("applied", False) and bool(fixed_content)
        fixed = fixed_content if applied else file.content
        return FixResult(
            file=str(file.path),
            applied=applied,
            original=file.content,
            fixed=fixed,
            explanation=data.get("explanation", ""),
            findings_addressed=data.get("findings_addressed", []),
        )

    def judge(self, session_history: str, system_prompt: str) -> Verdict:
        raw = self._chat(system_prompt, session_history, prefill="{")
        raw = "{" + raw
        try:
            data = json.loads(self._extract_json(raw))
        except json.JSONDecodeError:
            return Verdict.from_dict({
                "status": "partial",
                "score": 0,
                "summary": f"Failed to parse judge response: {raw[:200]}",
            })
        # LLM sometimes returns a list instead of an object
        if isinstance(data, list):
            data = data[0] if data else {}
        if not isinstance(data, dict):
            return Verdict.from_dict({
                "status": "partial",
                "score": 0,
                "summary": f"Unexpected judge response type: {type(data).__name__}",
            })
        return Verdict.from_dict(data)
