"""Static analysis pre-screening — run linters and feed results to LLM."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import click

from triplecheck.state import FileContent, Finding, Severity


def run_golangci_lint(target: Path) -> list[Finding]:
    """Run golangci-lint with JSON output."""
    if not shutil.which("golangci-lint"):
        return []
    try:
        result = subprocess.run(
            ["golangci-lint", "run", "--out-format=json", "./..."],
            cwd=target, capture_output=True, text=True, timeout=120,
        )
        data = json.loads(result.stdout) if result.stdout.strip() else {}
        issues = data.get("Issues") or []
        findings = []
        for issue in issues:
            pos = issue.get("Pos", {})
            findings.append(Finding(
                file=pos.get("Filename", ""),
                line=pos.get("Line", 0),
                severity=Severity.WARNING,
                category=issue.get("FromLinter", "lint"),
                message=issue.get("Text", ""),
                source="static_analysis",
            ))
        return findings
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return []


def run_go_vet(target: Path) -> list[Finding]:
    """Run go vet and parse stderr output."""
    if not shutil.which("go"):
        return []
    try:
        result = subprocess.run(
            ["go", "vet", "./..."],
            cwd=target, capture_output=True, text=True, timeout=60,
        )
        findings = []
        # go vet format: file.go:line:col: message
        pattern = re.compile(r"^(.+?):(\d+):\d+:\s+(.+)$")
        for line in result.stderr.splitlines():
            m = pattern.match(line)
            if m:
                findings.append(Finding(
                    file=m.group(1),
                    line=int(m.group(2)),
                    severity=Severity.WARNING,
                    category="go_vet",
                    message=m.group(3),
                    source="static_analysis",
                ))
        return findings
    except (subprocess.TimeoutExpired, OSError):
        return []


def run_ruff(target: Path) -> list[Finding]:
    """Run ruff with JSON output."""
    if not shutil.which("ruff"):
        return []
    try:
        result = subprocess.run(
            ["ruff", "check", "--output-format=json", "."],
            cwd=target, capture_output=True, text=True, timeout=60,
        )
        issues = json.loads(result.stdout) if result.stdout.strip() else []
        findings = []
        for issue in issues:
            loc = issue.get("location", {})
            findings.append(Finding(
                file=issue.get("filename", ""),
                line=loc.get("row", 0),
                severity=Severity.WARNING,
                category=f"ruff/{issue.get('code', '')}",
                message=issue.get("message", ""),
                source="static_analysis",
            ))
        return findings
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return []


def run_eslint(target: Path) -> list[Finding]:
    """Run eslint with JSON output."""
    eslint = shutil.which("eslint")
    if not eslint:
        return []
    try:
        result = subprocess.run(
            ["eslint", "--format=json", "."],
            cwd=target, capture_output=True, text=True, timeout=120,
        )
        data = json.loads(result.stdout) if result.stdout.strip() else []
        findings = []
        for file_result in data:
            filepath = file_result.get("filePath", "")
            # Make relative to target
            try:
                filepath = str(Path(filepath).relative_to(target))
            except ValueError:
                pass
            for msg in file_result.get("messages", []):
                sev = Severity.ERROR if msg.get("severity", 1) == 2 else Severity.WARNING
                findings.append(Finding(
                    file=filepath,
                    line=msg.get("line", 0),
                    severity=sev,
                    category=f"eslint/{msg.get('ruleId', '')}",
                    message=msg.get("message", ""),
                    source="static_analysis",
                ))
        return findings
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return []


def _detect_languages(files: list[FileContent]) -> set[str]:
    """Detect languages present in the file list."""
    langs = set()
    for f in files:
        if f.language:
            langs.add(f.language)
    return langs


def run_static_analysis(target: Path, files: list[FileContent]) -> list[Finding]:
    """Run appropriate static analysis tools based on detected languages."""
    langs = _detect_languages(files)
    all_findings: list[Finding] = []

    if "go" in langs:
        click.echo("    Running golangci-lint...")
        all_findings.extend(run_golangci_lint(target))
        click.echo("    Running go vet...")
        all_findings.extend(run_go_vet(target))

    if "python" in langs:
        click.echo("    Running ruff...")
        all_findings.extend(run_ruff(target))

    if "javascript" in langs or "typescript" in langs:
        click.echo("    Running eslint...")
        all_findings.extend(run_eslint(target))

    # Normalize file paths to be relative to target
    for f in all_findings:
        p = Path(f.file)
        if p.is_absolute():
            try:
                f.file = str(p.relative_to(target))
            except ValueError:
                pass

    click.echo(f"    Static analysis: {len(all_findings)} findings")
    return all_findings


def format_static_findings_for_prompt(findings: list[Finding]) -> str:
    """Format static analysis findings as context for the LLM reviewer prompt."""
    if not findings:
        return ""

    lines = [
        "",
        "## Static Analysis Results (pre-screening)",
        "The following issues were found by static analysis tools. "
        "These are already captured — focus your review on deeper issues "
        "that static tools cannot catch (logic errors, design flaws, "
        "security issues requiring data-flow analysis, etc.).",
        "",
    ]
    for f in findings:
        lines.append(f"- {f.file}:{f.line} [{f.category}] {f.message}")

    return "\n".join(lines)
