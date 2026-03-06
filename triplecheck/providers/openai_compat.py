"""OpenAI-compatible API provider (works with Qwen, DeepSeek, OpenRouter, vLLM, etc.)."""

from __future__ import annotations

import json
import os
import re
import time

import click
import httpx

from triplecheck.providers.base import BaseProvider
from triplecheck.state import FileContent, Finding, FixResult, Severity, Verdict


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
        self.no_think = config.get("no_think", False)

    def _chat(self, system: str, user: str, retries: int = 3) -> str:
        url = f"{self.base_url}/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        # Qwen3 /no_think: disable thinking mode to save tokens for actual output
        if self.no_think:
            user = user + " /no_think"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
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
        # Strip <think>...</think> blocks (Qwen3 outputs these even without reasoning-parser)
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        # Also handle unclosed <think> (truncated by max_tokens)
        text = re.sub(r"<think>.*", "", text, flags=re.DOTALL).strip()
        # Try ```json ... ``` block first
        m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
        if m:
            return m.group(1).strip()
        # Try raw JSON — find each [ or { and try balanced matching.
        # Try all positions (not just the first) since thinking text may
        # contain unbalanced brackets before the actual JSON payload.
        best = None
        for i, ch in enumerate(text):
            if ch in ('[', '{'):
                close = ']' if ch == '[' else '}'
                depth = 0
                in_string = False
                escape = False
                found_end = None
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
                            found_end = j
                            break
                if found_end is not None:
                    candidate = text[i:found_end+1]
                    # Prefer the largest valid JSON (likely the real payload)
                    if best is None or len(candidate) > len(best):
                        best = candidate
        if best is not None:
            return best.strip()
        # Truncated JSON recovery: if text starts with [ or {, try closing it
        stripped = text.strip()
        if stripped and stripped[0] in ('[', '{'):
            # Likely truncated by max_tokens — try to close it
            close = ']' if stripped[0] == '[' else '}'
            # Find the last complete item (last }, or last ])
            last_complete = stripped.rfind('}')
            if last_complete > 0:
                attempt = stripped[:last_complete+1] + close
                try:
                    json.loads(attempt)
                    return attempt
                except json.JSONDecodeError:
                    pass
        return text.strip()

    def _parse_natural_language_findings(self, text: str, files: list[FileContent]) -> list[Finding]:
        """Fallback: extract findings from natural language reviewer output."""
        findings = []
        # Build a set of known file paths for matching
        file_paths = {str(f.path) for f in files}
        file_basenames = {str(f.path).rsplit("/", 1)[-1]: str(f.path) for f in files}

        # Pattern: **File:** X / **Line:** Y / **Issue:** Z  (or similar markdown patterns)
        # Also matches: `file.py`, line 42: description
        # Also matches: - file.py:42 — description
        # Also matches numbered lists: 1. **file.py line 42** — description
        current_file = list(file_paths)[0] if len(file_paths) == 1 else ""
        current_severity = "warning"

        # Try to find file references with line numbers and descriptions
        # Pattern 1: **filename.py**, line NN or filename.py:NN
        line_patterns = [
            # "**file.py**, line 42:" or "**file.py** (line 42):"
            re.compile(r'\*\*([^\*]+?)\*\*[,\s]*(?:\(?line\s*(\d+)\)?)', re.IGNORECASE),
            # "file.py:42" or "`file.py:42`"
            re.compile(r'`?([a-zA-Z_][\w/]*\.py)`?[:\s]*(?:line\s*)?(\d+)'),
            # "Line NN" with context (when file is clear from section header)
            re.compile(r'(?:^|\n)\s*(?:\d+\.\s*)?(?:\*\*)?[Ll]ine\s+(\d+)(?:\*\*)?[\s:—-]+(.+)', re.MULTILINE),
        ]

        # Split by sections that look like findings
        # Split on numbered items, bullet points, or markdown headers
        sections = re.split(r'\n(?=\d+\.\s|\*\s|\-\s|#{1,3}\s)', text)

        for section in sections:
            if len(section.strip()) < 20:
                continue

            file_match = None
            line_num = 0
            message = ""

            # Try to extract file and line from this section
            for pattern in line_patterns[:2]:
                m = pattern.search(section)
                if m:
                    fname = m.group(1).strip().strip('`').strip('*')
                    line_num = int(m.group(2)) if m.group(2) else 0
                    # Resolve filename to full path
                    if fname in file_paths:
                        file_match = fname
                    elif fname in file_basenames:
                        file_match = file_basenames[fname]
                    else:
                        # Fuzzy: check if any known path ends with this name
                        for fp in file_paths:
                            if fp.endswith(fname) or fp.endswith("/" + fname):
                                file_match = fp
                                break
                    break

            if not file_match:
                # Try Line NN pattern (file from context)
                m = line_patterns[2].search(section)
                if m and current_file:
                    line_num = int(m.group(1))
                    file_match = current_file
                    message = m.group(2).strip()

            # Update current_file from ## headers
            header_m = re.search(r'##\s+(.+\.py)', section)
            if header_m:
                hf = header_m.group(1).strip()
                for fp in file_paths:
                    if fp.endswith(hf) or fp.endswith("/" + hf):
                        current_file = fp
                        break

            if not file_match:
                file_match = current_file

            if not file_match:
                continue

            # Extract message: take the main descriptive text
            if not message:
                # Remove file/line references and get the core message
                clean = re.sub(r'\*\*([^\*]+)\*\*', r'\1', section)  # strip bold
                clean = re.sub(r'`([^`]+)`', r'\1', clean)  # strip code
                lines = [l.strip() for l in clean.split('\n') if l.strip() and len(l.strip()) > 10]
                # Skip lines that are just file references
                desc_lines = [l for l in lines if not re.match(r'^[\d.]+\s*$', l)]
                message = desc_lines[0] if desc_lines else section[:200]
                # Clean up leading list markers
                message = re.sub(r'^[\d]+\.\s*', '', message)
                message = re.sub(r'^[-*]\s*', '', message)

            if len(message) < 10:
                continue

            # Detect severity from keywords
            sev = "warning"
            lower = (section + message).lower()
            if any(w in lower for w in ["crash", "security", "injection", "critical", "vulnerability", "race condition"]):
                sev = "error"
            elif any(w in lower for w in ["suggestion", "consider", "minor", "style", "could"]):
                sev = "suggestion"

            findings.append(Finding(
                file=file_match,
                line=line_num,
                severity=Severity(sev),
                category="general",
                message=message[:500],
                suggestion="",
                source="reviewer",
            ))

        return findings

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

        user_msg += "\n\nRespond with ONLY a JSON array of findings. Start with [ and end with ]. No other text."
        raw = self._chat(system_prompt, user_msg)
        extracted = self._extract_json(raw)
        try:
            data = json.loads(extracted)
        except json.JSONDecodeError:
            # Fallback: parse natural language findings instead of retrying
            nl_findings = self._parse_natural_language_findings(raw, files)
            if nl_findings:
                click.echo(f"      [NL-PARSE] Extracted {len(nl_findings)} findings from natural language ({len(raw)} chars)")
                return nl_findings
            click.echo(f"      [WARN] Could not extract findings from response ({len(raw)} chars)")
            click.echo(f"      [DEBUG] Raw start: {raw[:300]}")
            click.echo(f"      [DEBUG] Raw end: {raw[-300:]}")
            click.echo(f"      [DEBUG] Extracted start: {extracted[:300]}")
            return []

        if isinstance(data, list):
            findings = []
            for d in data:
                try:
                    if not isinstance(d, dict):
                        continue
                    # Skip placeholder/example entries from the prompt
                    if isinstance(d, dict) and d.get("file", "").startswith("path/to/"):
                        continue
                    findings.append(Finding.from_dict(d))
                except (KeyError, ValueError, TypeError, AttributeError) as e:
                    click.echo(f"      [DEBUG] Skipped malformed finding: {e} — {d}")
            return findings
        click.echo(f"      [DEBUG] Response was not a list: {type(data)}")
        return []

    def _extract_code_from_natural_language(self, text: str, file: FileContent) -> FixResult | None:
        """Fallback: extract fixed code from natural language coder response."""
        # Strip think tags
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        text = re.sub(r"<think>.*", "", text, flags=re.DOTALL).strip()

        # Look for a code block with the full fixed file content
        # Pattern: ```python\n...\n``` or ```\n...\n```
        code_blocks = re.findall(r"```(?:\w*)\s*\n(.*?)\n```", text, re.DOTALL)
        if not code_blocks:
            return None

        # Pick the largest code block (most likely the full fixed file)
        largest = max(code_blocks, key=len)

        # Sanity check: the code block should be reasonably similar in size to original
        orig_len = len(file.content)
        if len(largest) < orig_len * 0.3:
            # Too small — probably just a snippet, not the full file
            return None

        # Extract explanation from surrounding text
        explanation = ""
        for line in text.split("\n"):
            line = line.strip()
            if line and not line.startswith("```") and len(line) > 20:
                explanation = line[:300]
                break

        return FixResult(
            file=str(file.path),
            applied=True,
            original=file.content,
            fixed=largest,
            explanation=f"[NL-extracted] {explanation}",
        )

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

        user_msg += "\n\nRespond with ONLY a JSON object. Start with { and end with }. No other text."
        raw = self._chat(system_prompt, user_msg)
        try:
            data = json.loads(self._extract_json(raw))
        except json.JSONDecodeError:
            # Fallback: try to extract code block from natural language
            nl_result = self._extract_code_from_natural_language(raw, file)
            if nl_result:
                click.echo(f"      [NL-PARSE] Extracted fixed code from natural language response")
                return nl_result
            click.echo(f"      [WARN] Could not parse coder response ({len(raw)} chars)")
            click.echo(f"      [DEBUG] Coder raw start: {raw[:300]}")
            click.echo(f"      [DEBUG] Coder raw end: {raw[-300:]}")
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

        # Support both formats: "changes" (search/replace pairs) and legacy "fixed_content"
        changes = data.get("changes", [])
        fixed_content = data.get("fixed_content", "")
        applied = data.get("applied", False)

        if changes and applied:
            # Apply search/replace pairs to original content
            fixed = file.content
            applied_count = 0
            for change in changes:
                if not isinstance(change, dict):
                    continue
                search = change.get("search", "")
                replace = change.get("replace", "")
                if search and search in fixed:
                    fixed = fixed.replace(search, replace, 1)
                    applied_count += 1
                else:
                    click.echo(f"      [DEBUG] Search string not found in file (skipped)")
            applied = applied_count > 0
        elif fixed_content and applied:
            # Legacy format: full file content
            fixed = fixed_content
        else:
            fixed = file.content
            applied = False

        return FixResult(
            file=str(file.path),
            applied=applied,
            original=file.content,
            fixed=fixed,
            explanation=data.get("explanation", ""),
            findings_addressed=data.get("findings_addressed", []),
        )

    def judge(self, session_history: str, system_prompt: str) -> Verdict:
        raw = self._chat(system_prompt, session_history + "\n\nRespond with ONLY a JSON object. No other text.")
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
