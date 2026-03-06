"""Generate JSON and markdown reports from a review session."""

from __future__ import annotations

import json
from pathlib import Path

from code_review.state import ReviewSession, Severity


def save_json_report(session: ReviewSession, output_dir: Path) -> Path:
    """Save full session state as JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{session.session_id}.json"
    with open(path, "w") as f:
        json.dump(session.to_dict(), f, indent=2)
    return path


def generate_markdown_report(session: ReviewSession) -> str:
    """Generate a markdown report from a review session."""
    lines = [
        f"# Code Review Report — `{session.session_id}`",
        "",
        f"**Target:** `{session.target}`",
        f"**Started:** {session.started_at}",
        f"**Status:** {session.status}",
        f"**Rounds:** {len(session.rounds)}",
        "",
    ]

    # Summary stats
    total_findings = sum(len(r.findings) for r in session.rounds)
    total_fixes = sum(1 for r in session.rounds for f in r.fixes if f.applied)
    lines.append(f"**Total findings:** {total_findings}")
    lines.append(f"**Fixes applied:** {total_fixes}")
    lines.append("")

    # Per-round details
    for rnd in session.rounds:
        lines.append(f"## Round {rnd.round_number}")
        lines.append("")

        if rnd.findings:
            errors = sum(1 for f in rnd.findings if f.severity == Severity.ERROR)
            warnings = sum(1 for f in rnd.findings if f.severity == Severity.WARNING)
            suggestions = sum(1 for f in rnd.findings if f.severity == Severity.SUGGESTION)
            lines.append(f"**Findings:** {len(rnd.findings)} ({errors} errors, {warnings} warnings, {suggestions} suggestions)")
            lines.append("")

            high_conf = [f for f in rnd.findings if f.confidence == "high"]
            low_conf = [f for f in rnd.findings if f.confidence == "low"]
            has_confidence_split = bool(low_conf)

            if high_conf:
                if has_confidence_split:
                    lines.append("| File | Line | Severity | Category | Confidence | Message |")
                    lines.append("|------|------|----------|----------|------------|---------|")
                    for f in high_conf:
                        lines.append(
                            f"| `{f.file}` | {f.line} | {f.severity.value} | {f.category} | {f.confidence} | {f.message} |"
                        )
                else:
                    lines.append("| File | Line | Severity | Category | Message |")
                    lines.append("|------|------|----------|----------|---------|")
                    for f in high_conf:
                        lines.append(
                            f"| `{f.file}` | {f.line} | {f.severity.value} | {f.category} | {f.message} |"
                        )
                lines.append("")

            if low_conf:
                lines.append("### Low Confidence (Human Review)")
                lines.append("")
                lines.append("| File | Line | Severity | Category | Message |")
                lines.append("|------|------|----------|----------|---------|")
                for f in low_conf:
                    lines.append(
                        f"| `{f.file}` | {f.line} | {f.severity.value} | {f.category} | {f.message} |"
                    )
                lines.append("")

        if rnd.fixes:
            applied = sum(1 for f in rnd.fixes if f.applied)
            lines.append(f"**Fixes:** {applied}/{len(rnd.fixes)} applied")
            for f in rnd.fixes:
                status = "applied" if f.applied else "rejected"
                lines.append(f"- `{f.file}`: {status} — {str(f.explanation or '')[:100]}")
            lines.append("")

        if rnd.ci_passed is not None:
            ci_icon = "PASS" if rnd.ci_passed else "FAIL"
            lines.append(f"**CI:** {ci_icon}")
            lines.append("")

    # Verdict
    if session.verdict:
        v = session.verdict
        lines.append("## Verdict")
        lines.append("")
        lines.append(f"**Status:** {v.status.value}")
        lines.append(f"**Score:** {v.score}/10")
        lines.append(f"**Summary:** {v.summary}")
        lines.append("")

        if v.category_scores:
            lines.append("### Category Scores")
            lines.append("")
            lines.append("| Category | Score |")
            lines.append("|----------|-------|")
            for cat, score in v.category_scores.items():
                lines.append(f"| {cat} | {score}/10 |")
            lines.append("")

        if v.recommendations:
            lines.append("### Recommendations")
            lines.append("")
            for rec in v.recommendations:
                lines.append(f"- {rec}")
            lines.append("")

    return "\n".join(lines)


def save_markdown_report(session: ReviewSession, output_dir: Path) -> Path:
    """Save markdown report."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{session.session_id}.md"
    path.write_text(generate_markdown_report(session))
    return path
