"""Auto-detect project type and run CI checks."""

from __future__ import annotations

import subprocess
from pathlib import Path


def detect_ci_command(target: Path) -> str | None:
    """Auto-detect CI command based on project files."""
    if (target / "Makefile").exists():
        return "make check"
    if (target / "pyproject.toml").exists() or (target / "setup.py").exists():
        # Python project
        if (target / "tox.ini").exists():
            return "tox"
        return "python -m pytest --tb=short -q"
    if (target / "package.json").exists():
        return "npm test"
    if (target / "Cargo.toml").exists():
        return "cargo test"
    if (target / "go.mod").exists():
        return "go test ./..."
    return None


def run_ci(target: Path, command: str | None = None) -> tuple[bool, str]:
    """Run CI checks on the target project.

    Returns (passed, output).
    """
    if command is None:
        command = detect_ci_command(target)
    if command is None:
        return True, "No CI command detected — skipping"

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=target,
            capture_output=True,
            text=True,
            timeout=300,
        )
        output = result.stdout + result.stderr
        passed = result.returncode == 0
        return passed, output[-2000:]  # Truncate long output
    except subprocess.TimeoutExpired:
        return False, "CI timed out after 300s"
    except Exception as e:
        return False, f"CI failed to run: {e}"
