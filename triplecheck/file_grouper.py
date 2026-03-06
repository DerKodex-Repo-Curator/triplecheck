"""Discover files, respect .gitignore, batch by directory."""

from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path

import click

from triplecheck.state import FileContent


def discover_files(
    target: Path,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> list[Path]:
    """Discover files in target directory, respecting .gitignore.

    Uses `git ls-files` if inside a git repo, otherwise walks the directory.
    """
    target = target.resolve()
    files: list[Path] = []

    # Try git ls-files first (respects .gitignore)
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=target,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if line:
                    files.append(target / line)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # Not a git repo or git not available — walk directory
        for p in target.rglob("*"):
            if p.is_file() and not any(
                part.startswith(".") for part in p.relative_to(target).parts
            ):
                files.append(p)

    # Apply include filters
    if include:
        filtered = []
        for f in files:
            rel = str(f.relative_to(target))
            if any(fnmatch.fnmatch(rel, pat) for pat in include):
                filtered.append(f)
        files = filtered

    # Apply exclude filters
    if exclude:
        filtered = []
        for f in files:
            rel = str(f.relative_to(target))
            if not any(fnmatch.fnmatch(rel, pat) for pat in exclude):
                filtered.append(f)
        files = filtered

    # Filter to text files only (skip binary)
    text_extensions = {
        ".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java",
        ".rb", ".c", ".cpp", ".h", ".hpp", ".sh", ".bash", ".zsh",
        ".yml", ".yaml", ".json", ".toml", ".cfg", ".ini",
        ".md", ".txt", ".rst", ".html", ".css", ".scss",
        ".sql", ".graphql", ".proto", ".swift", ".kt",
    }
    files = [f for f in files if f.suffix in text_extensions]

    return sorted(files)


def load_files(paths: list[Path], target: Path, max_size: int = 10 * 1024 * 1024) -> list[FileContent]:
    """Load file contents, skipping files that can't be read.

    Args:
        paths: List of file paths to load
        target: Target directory for relative paths
        max_size: Maximum file size in bytes (default 10MB)
    """
    result = []
    for p in paths:
        try:
            if p.stat().st_size > max_size:
                continue
            content = p.read_text(errors="replace")
            result.append(FileContent(
                path=p.relative_to(target),
                content=content,
            ))
        except (OSError, UnicodeDecodeError):
            continue
    return result


def batch_files(
    files: list[FileContent],
    max_lines: int = 6000,
    max_files: int = 5,
) -> list[list[FileContent]]:
    """Split files into batches that fit within line and file count limits."""
    batches: list[list[FileContent]] = []
    current_batch: list[FileContent] = []
    current_lines = 0

    for f in files:
        lines = f.content.count("\n") + 1
        if (current_lines + lines > max_lines or len(current_batch) >= max_files) and current_batch:
            batches.append(current_batch)
            current_batch = []
            current_lines = 0
        current_batch.append(f)
        current_lines += lines

    if current_batch:
        batches.append(current_batch)

    return batches


def smart_batch_files(
    files: list[FileContent],
    target: Path,
    max_lines: int = 6000,
    max_files: int = 5,
) -> list[list[FileContent]]:
    """Batch files using dependency graph when available, fallback to line count.

    Tries to use tree-sitter based smart batching. If tree-sitter
    dependencies are not installed, falls back to simple line-count batching.
    """
    try:
        from triplecheck.code_graph import smart_batch
        result = smart_batch(files, target, max_lines, max_files)
        click.echo(f"    Smart grouping: {len(result)} batches (dependency-aware)")
        return result
    except ImportError:
        click.echo("    Smart grouping unavailable (install with: pip install -e '.[graph]')")
        return batch_files(files, max_lines, max_files)
    except Exception as e:
        click.echo(f"    Smart grouping failed ({e}), falling back to line-count batching")
        return batch_files(files, max_lines, max_files)
