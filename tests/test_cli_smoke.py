"""Smoke tests — CLI invocations that don't need an LLM."""

import subprocess
import sys


def test_help():
    result = subprocess.run(
        [sys.executable, "-m", "triplecheck.cli", "--help"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
    assert "triplecheck" in result.stdout.lower() or "--target" in result.stdout


def test_plan_only(tmp_path):
    """--plan-only should exit cleanly without calling any LLM."""
    # Create a minimal Python file so there's something to scan
    (tmp_path / "example.py").write_text("x = 1\n")
    # Need a config file
    config = tmp_path / "config.yml"
    config.write_text(
        "roles:\n"
        "  reviewer:\n"
        "    description: test\n"
        "    prompt_file: prompts/reviewer.txt\n"
        "  coder:\n"
        "    description: test\n"
        "    prompt_file: prompts/coder.txt\n"
        "  judge:\n"
        "    description: test\n"
        "    prompt_file: prompts/judge.txt\n"
        "models:\n"
        "  dummy:\n"
        "    provider: openai-compat\n"
        "    base_url: http://localhost:9999\n"
        "    model: dummy\n"
        "assignments:\n"
        "  reviewer: dummy\n"
        "  coder: dummy\n"
        "  judge: dummy\n"
        "pipeline:\n"
        "  max_rounds: 1\n"
    )
    result = subprocess.run(
        [
            sys.executable, "-m", "triplecheck.cli",
            "--target", str(tmp_path),
            "--config", str(config),
            "--scan", "--plan-only",
        ],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0
    assert "plan" in result.stdout.lower() or "unit" in result.stdout.lower()
