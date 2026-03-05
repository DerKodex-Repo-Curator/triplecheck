"""Orchestrator + CLI entry point for the code review loop."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import click

from code_review.ci_runner import run_ci
from code_review.file_grouper import batch_files, discover_files, load_files, smart_batch_files
from code_review.knowledge import KnowledgeAccumulator
from code_review.multi_pass import multi_pass_review
from code_review.report import save_json_report, save_markdown_report
from code_review.review_layers import run_layered_review
from code_review.roles import load_config, load_prompt, resolve_provider
from code_review.static_analysis import (
    format_static_findings_for_prompt,
    run_static_analysis,
)
from code_review.state import (
    FileContent,
    Finding,
    ReviewRound,
    ReviewSession,
    Severity,
)


def _severity_gate(threshold: str) -> set[str]:
    """Return severities at or above the threshold."""
    levels = ["suggestion", "warning", "error"]
    idx = levels.index(threshold) if threshold in levels else 1
    return set(levels[idx:])


def _run_auto_style(target: Path) -> None:
    """Run auto-formatters if available."""
    if shutil.which("ruff"):
        subprocess.run(
            ["ruff", "check", "--fix", "--quiet", "."],
            cwd=target, capture_output=True, timeout=60,
        )
        subprocess.run(
            ["ruff", "format", "--quiet", "."],
            cwd=target, capture_output=True, timeout=60,
        )
    elif shutil.which("black"):
        subprocess.run(
            ["black", "--quiet", "."],
            cwd=target, capture_output=True, timeout=60,
        )


def _detect_oscillation(rounds: list[ReviewRound]) -> bool:
    """Check if findings are oscillating (reappearing after being fixed)."""
    if len(rounds) < 3:
        return False
    # Compare finding messages from round N and N-2
    current = {f.message for f in rounds[-1].findings}
    two_ago = {f.message for f in rounds[-3].findings}
    overlap = current & two_ago
    return len(overlap) > 0


def run_pipeline(
    target: Path,
    cfg: dict,
    config_dir: Path,
    overrides: dict[str, str],
    max_rounds: int | None = None,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    ci_cmd: str | None = None,
    skip_ci: bool = False,
    output_dir: Path | None = None,
) -> ReviewSession:
    """Run the full review pipeline."""
    pipeline_cfg = cfg.get("pipeline", {})
    max_rounds = max_rounds or pipeline_cfg.get("max_rounds", 4)
    batch_max = pipeline_cfg.get("batch_max_lines", 6000)
    threshold = pipeline_cfg.get("severity_threshold", "warning")
    auto_style = pipeline_cfg.get("auto_style_fix", True)
    review_passes = pipeline_cfg.get("review_passes", 1)
    review_min_votes = pipeline_cfg.get("review_min_votes", 2)
    only_high_confidence = pipeline_cfg.get("only_high_confidence", True)
    static_analysis_enabled = pipeline_cfg.get("static_analysis", False)
    review_layers = pipeline_cfg.get("review_layers", [])
    knowledge_enabled = pipeline_cfg.get("knowledge_accumulation", False)
    smart_grouping = pipeline_cfg.get("smart_grouping", False)
    gate_severities = _severity_gate(threshold)

    # Resolve providers
    reviewer = resolve_provider("reviewer", cfg, overrides)
    coder = resolve_provider("coder", cfg, overrides)
    judge_provider = resolve_provider("judge", cfg, overrides)

    # Load prompts
    reviewer_prompt = load_prompt("reviewer", cfg, config_dir)
    coder_prompt = load_prompt("coder", cfg, config_dir)
    judge_prompt = load_prompt("judge", cfg, config_dir)

    # Initialize session
    session = ReviewSession(
        target=str(target),
        config_snapshot=cfg,
    )

    # Track changed files for subsequent rounds
    changed_files: set[str] | None = None  # None = review all files

    # Knowledge accumulator (P4)
    knowledge = KnowledgeAccumulator() if knowledge_enabled else None

    for round_num in range(1, max_rounds + 1):
        click.echo(f"\n{'='*60}")
        click.echo(f"  Round {round_num}/{max_rounds}")
        click.echo(f"{'='*60}")

        rnd = ReviewRound(round_number=round_num)

        # Discover and load files
        all_paths = discover_files(target, include=include, exclude=exclude)
        all_files = load_files(all_paths, target)

        if changed_files is not None:
            # Only review files changed in last round
            all_files = [f for f in all_files if str(f.path) in changed_files]
            if not all_files:
                click.echo("  No changed files to review — converged!")
                break

        click.echo(f"  Files to review: {len(all_files)}")

        # --- KNOWLEDGE INJECTION (P4) ---
        effective_reviewer_prompt = reviewer_prompt
        if knowledge and knowledge.patterns:
            knowledge_context = knowledge.get_prompt_context()
            effective_reviewer_prompt = reviewer_prompt + knowledge_context

        # --- STATIC ANALYSIS PHASE (P1) ---
        static_findings: list[Finding] = []
        if static_analysis_enabled:
            click.echo("  [Static Analysis] Running...")
            static_findings = run_static_analysis(target, all_files)
            if static_findings:
                static_context = format_static_findings_for_prompt(static_findings)
                effective_reviewer_prompt += static_context

        # --- REVIEW PHASE ---
        previous_feedback = None
        if session.rounds:
            previous_feedback = [
                f.to_dict() for f in session.rounds[-1].findings
            ]

        if review_layers:
            # Layered review (P2) — mutually exclusive with flat/multi-pass
            click.echo(f"  [Layered Review] Running layers: {', '.join(review_layers)}")
            all_findings = run_layered_review(
                reviewer=reviewer,
                files=all_files,
                layers=review_layers,
                batch_max_lines=batch_max,
                previous_feedback=previous_feedback,
            )
        elif review_passes > 1:
            click.echo("  [Reviewer] Multi-pass analyzing...")
            all_findings = multi_pass_review(
                reviewer=reviewer,
                files=all_files,
                base_prompt=effective_reviewer_prompt,
                num_passes=review_passes,
                batch_max_lines=batch_max,
                min_votes=review_min_votes,
                previous_feedback=previous_feedback,
            )
        else:
            click.echo("  [Reviewer] Analyzing...")
            if smart_grouping:
                batches = smart_batch_files(all_files, target, max_lines=batch_max)
            else:
                batches = batch_files(all_files, max_lines=batch_max)
            all_findings: list[Finding] = []
            for i, batch in enumerate(batches):
                click.echo(f"    Batch {i+1}/{len(batches)} ({len(batch)} files)...")
                findings = reviewer.review(batch, effective_reviewer_prompt, previous_feedback)
                all_findings.extend(findings)

        # Merge static analysis findings into all_findings
        if static_findings:
            all_findings.extend(static_findings)

        # Filter by severity threshold + confidence (exclude static_analysis from coder)
        gated = [
            f for f in all_findings
            if f.severity.value in gate_severities and f.source != "static_analysis"
        ]
        if only_high_confidence and review_passes > 1 and not review_layers:
            gated = [f for f in gated if f.confidence == "high"]
        rnd.findings = all_findings
        click.echo(f"  [Reviewer] {len(all_findings)} findings ({len(gated)} at/above threshold)")

        # --- KNOWLEDGE ACCUMULATION (P4) ---
        if knowledge:
            knowledge.ingest_round(all_findings)

        # --- CONVERGENCE CHECK: zero gated findings ---
        if not gated:
            click.echo("  No actionable findings — converged!")
            session.rounds.append(rnd)
            break

        # --- CODER PHASE ---
        click.echo("  [Coder] Fixing...")
        changed_files = set()

        # Group findings by file
        findings_by_file: dict[str, list[Finding]] = {}
        for f in gated:
            findings_by_file.setdefault(f.file, []).append(f)

        # Map filenames to FileContent objects
        file_map = {str(fc.path): fc for fc in all_files}

        for fname, file_findings in findings_by_file.items():
            fc = file_map.get(fname)
            if fc is None:
                click.echo(f"    Skipping {fname} — not in file list")
                continue

            click.echo(f"    Fixing {fname} ({len(file_findings)} findings)...")
            fix = coder.fix(fc, file_findings, coder_prompt)
            rnd.fixes.append(fix)

            if fix.applied and fix.fixed:
                # Write fix to disk
                out_path = target / fname
                out_path.write_text(fix.fixed)
                changed_files.add(fname)
                click.echo(f"      Applied ({fix.explanation[:60]})")
            else:
                click.echo(f"      Rejected ({fix.explanation[:60]})")

        # --- CONVERGENCE CHECK: coder rejected everything ---
        if not changed_files:
            click.echo("  Coder rejected all findings — stopping")
            session.rounds.append(rnd)
            break

        # --- AUTO STYLE ---
        if auto_style:
            click.echo("  [Style] Running auto-formatters...")
            _run_auto_style(target)

        # --- CI GATE ---
        if not skip_ci:
            click.echo("  [CI] Running checks...")
            ci_passed, ci_output = run_ci(target, ci_cmd)
            rnd.ci_passed = ci_passed
            rnd.ci_output = ci_output
            if ci_passed:
                click.echo("  [CI] PASSED")
            else:
                click.echo(f"  [CI] FAILED — stopping (rollback not implemented)")
                session.rounds.append(rnd)
                break

        session.rounds.append(rnd)

        # --- CONVERGENCE CHECK: oscillation ---
        if _detect_oscillation(session.rounds):
            click.echo("  Oscillation detected — stopping")
            break

    # --- JUDGE PHASE ---
    click.echo(f"\n{'='*60}")
    click.echo("  [Judge] Evaluating session...")
    click.echo(f"{'='*60}")

    history = json.dumps(session.to_dict(), indent=2)
    verdict = judge_provider.judge(history, judge_prompt)
    session.verdict = verdict
    session.status = "completed"

    click.echo(f"  Verdict: {verdict.status.value} (score: {verdict.score}/10)")
    click.echo(f"  Summary: {verdict.summary}")

    # --- SAVE REPORTS ---
    out = output_dir or Path("reports")
    json_path = save_json_report(session, out)
    md_path = save_markdown_report(session, out)
    click.echo(f"\n  Reports saved:")
    click.echo(f"    {json_path}")
    click.echo(f"    {md_path}")

    return session


@click.command()
@click.option("--target", required=True, type=click.Path(exists=True), help="Project directory to review")
@click.option("--config", "config_path", default=None, type=click.Path(), help="Config file path")
@click.option("--reviewer", "reviewer_override", default=None, help="Override reviewer model")
@click.option("--coder", "coder_override", default=None, help="Override coder model")
@click.option("--judge", "judge_override", default=None, help="Override judge model")
@click.option("--max-rounds", default=None, type=int, help="Max review rounds")
@click.option("--include", multiple=True, help="File glob include patterns")
@click.option("--exclude", multiple=True, help="File glob exclude patterns")
@click.option("--ci-cmd", default=None, help="Custom CI command")
@click.option("--skip-ci", is_flag=True, help="Skip CI gate")
@click.option("--output", "output_dir", default=None, type=click.Path(), help="Output directory for reports")
def main(
    target: str,
    config_path: str | None,
    reviewer_override: str | None,
    coder_override: str | None,
    judge_override: str | None,
    max_rounds: int | None,
    include: tuple[str, ...],
    exclude: tuple[str, ...],
    ci_cmd: str | None,
    skip_ci: bool,
    output_dir: str | None,
) -> None:
    """Multi-agent, model-agnostic code review pipeline."""
    target_path = Path(target).resolve()

    # Find config
    if config_path:
        cfg_path = Path(config_path)
    else:
        # Look for config.yml in current dir, then package dir
        cfg_path = Path("config.yml")
        if not cfg_path.exists():
            cfg_path = Path(__file__).parent.parent / "config.yml"

    cfg = load_config(cfg_path)
    config_dir = cfg_path.parent

    # Build overrides
    overrides: dict[str, str] = {}
    if reviewer_override:
        overrides["reviewer"] = reviewer_override
    if coder_override:
        overrides["coder"] = coder_override
    if judge_override:
        overrides["judge"] = judge_override

    click.echo(f"Code Review Loop")
    click.echo(f"  Target: {target_path}")
    click.echo(f"  Config: {cfg_path}")
    click.echo(f"  Reviewer: {overrides.get('reviewer', cfg['assignments']['reviewer'])}")
    click.echo(f"  Coder: {overrides.get('coder', cfg['assignments']['coder'])}")
    click.echo(f"  Judge: {overrides.get('judge', cfg['assignments']['judge'])}")

    session = run_pipeline(
        target=target_path,
        cfg=cfg,
        config_dir=config_dir,
        overrides=overrides,
        max_rounds=max_rounds,
        include=list(include) if include else None,
        exclude=list(exclude) if exclude else None,
        ci_cmd=ci_cmd,
        skip_ci=skip_ci,
        output_dir=Path(output_dir) if output_dir else None,
    )

    # Exit code based on verdict
    if session.verdict and session.verdict.status.value == "fail":
        sys.exit(1)


if __name__ == "__main__":
    main()
