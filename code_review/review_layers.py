"""Layered review — architecture, interface, logic, security passes."""

from __future__ import annotations

import re
from pathlib import Path

import click

from code_review.file_grouper import batch_files
from code_review.state import FileContent, Finding

LAYER_NAMES = ("architecture", "interface", "logic", "security")

# Patterns for extracting imports (Python and Go)
_PYTHON_IMPORT_RE = re.compile(
    r"^\s*(import\s+\S+|from\s+\S+\s+import\s+.+)$", re.MULTILINE
)
_GO_IMPORT_RE = re.compile(
    r'^\s*(?:import\s+(?:"[^"]+"|[\w.]+)|"[^"]+")\s*$', re.MULTILINE
)
_GO_IMPORT_BLOCK_RE = re.compile(
    r"import\s*\((.*?)\)", re.DOTALL
)

# Patterns for extracting signatures
_PYTHON_SIG_RE = re.compile(
    r"^(\s*(?:class\s+\w+.*?:|(?:async\s+)?def\s+\w+\s*\(.*?\)(?:\s*->.*?)?:))", re.MULTILINE
)
_GO_SIG_RE = re.compile(
    r"^(func\s+(?:\([^)]*\)\s*)?\w+\s*\([^)]*\)(?:\s*(?:\([^)]*\)|[\w.*]+))?)",
    re.MULTILINE,
)
_GO_TYPE_RE = re.compile(
    r"^(type\s+\w+\s+(?:struct|interface)\s*\{)", re.MULTILINE
)


def _extract_imports_only(files: list[FileContent]) -> list[FileContent]:
    """Extract only import lines from files."""
    result = []
    for f in files:
        lines = []
        if f.language == "python":
            for m in _PYTHON_IMPORT_RE.finditer(f.content):
                lines.append(m.group(0))
        elif f.language == "go":
            for m in _GO_IMPORT_RE.finditer(f.content):
                lines.append(m.group(0))
            for m in _GO_IMPORT_BLOCK_RE.finditer(f.content):
                lines.append("import (")
                lines.append(m.group(1).strip())
                lines.append(")")
        else:
            # Generic: lines containing 'import' or 'require'
            for line in f.content.splitlines():
                stripped = line.strip()
                if stripped.startswith(("import ", "from ", "require(", "require ")):
                    lines.append(line)

        if lines:
            result.append(FileContent(
                path=f.path,
                content="\n".join(lines),
                language=f.language,
            ))
    return result


def _extract_signatures(files: list[FileContent]) -> list[FileContent]:
    """Extract only function/class/type definition signatures."""
    result = []
    for f in files:
        sigs = []
        if f.language == "python":
            for m in _PYTHON_SIG_RE.finditer(f.content):
                sigs.append(m.group(0))
        elif f.language == "go":
            for m in _GO_SIG_RE.finditer(f.content):
                sigs.append(m.group(0))
            for m in _GO_TYPE_RE.finditer(f.content):
                sigs.append(m.group(0))
        else:
            # Generic heuristic: lines with 'function', 'def', 'class', 'type', 'interface'
            for line in f.content.splitlines():
                stripped = line.strip()
                if re.match(
                    r"^(export\s+)?(function|class|type|interface|def|async\s+function)\s+",
                    stripped,
                ):
                    sigs.append(line)

        if sigs:
            result.append(FileContent(
                path=f.path,
                content="\n".join(sigs),
                language=f.language,
            ))
    return result


def prepare_layer_context(
    layer: str, files: list[FileContent]
) -> list[FileContent]:
    """Prepare code context appropriate for the given review layer."""
    if layer == "architecture":
        return _extract_imports_only(files)
    elif layer == "interface":
        return _extract_signatures(files)
    else:
        # logic and security get full file content
        return files


def _load_layer_prompt(layer: str) -> str:
    """Load the prompt for a specific review layer."""
    prompt_path = Path(__file__).parent / "prompts" / f"layer_{layer}.txt"
    if prompt_path.exists():
        return prompt_path.read_text()
    raise FileNotFoundError(f"Layer prompt not found: {prompt_path}")


def run_layered_review(
    reviewer,
    files: list[FileContent],
    layers: list[str],
    batch_max_lines: int = 6000,
    previous_feedback: list[dict] | None = None,
) -> list[Finding]:
    """Run layered review — each layer sees appropriate context.

    Upper layer findings are injected into lower layer prompts
    so reviewers can focus on new issues.
    """
    all_findings: list[Finding] = []

    for layer in layers:
        if layer not in LAYER_NAMES:
            click.echo(f"    Unknown layer '{layer}' — skipping")
            continue

        click.echo(f"  [Layer: {layer}] Reviewing...")

        # Load layer-specific prompt
        layer_prompt = _load_layer_prompt(layer)

        # Inject upper layer findings as context
        if all_findings:
            prior_lines = [
                "",
                "## Findings from previous layers (already captured):",
            ]
            for f in all_findings:
                prior_lines.append(
                    f"- [{f.source}] {f.file}:{f.line} {f.message}"
                )
            prior_lines.append("")
            prior_lines.append(
                "Do NOT re-report these. Focus on new issues within your scope."
            )
            layer_prompt += "\n".join(prior_lines)

        # Prepare context for this layer
        layer_files = prepare_layer_context(layer, files)
        if not layer_files:
            click.echo(f"    No relevant content for {layer} layer")
            continue

        batches = batch_files(layer_files, max_lines=batch_max_lines)
        layer_findings: list[Finding] = []

        for i, batch in enumerate(batches):
            click.echo(f"    Batch {i + 1}/{len(batches)} ({len(batch)} files)...")
            findings = reviewer.review(batch, layer_prompt, previous_feedback)
            # Tag findings with layer source
            for finding in findings:
                finding.source = f"layer_{layer}"
            layer_findings.extend(findings)

        click.echo(f"    → {len(layer_findings)} findings")
        all_findings.extend(layer_findings)

    return all_findings
