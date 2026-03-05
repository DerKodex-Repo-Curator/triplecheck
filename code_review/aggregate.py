"""Aggregate results from multiple review unit sessions into one report."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from code_review.planner import ScanPlan
from code_review.state import AggregatedReport, ReviewSession, Severity


def aggregate_sessions(
    sessions: list[ReviewSession],
    plan: ScanPlan,
    completed_unit_names: list[str] | None = None,
) -> AggregatedReport:
    """Merge all unit review sessions into a single aggregated report."""
    report = AggregatedReport(plan=plan.to_dict())

    report.unit_sessions = sessions

    # Build name→line_count lookup from plan for weighted scoring
    unit_line_counts: dict[str, int] = {u.name: u.line_count for u in plan.units}

    # Map sessions to unit names — use completed_unit_names if provided (resume-safe),
    # otherwise fall back to positional mapping
    if completed_unit_names and len(completed_unit_names) == len(sessions):
        session_unit_names = completed_unit_names
    else:
        session_unit_names = [
            plan.units[i].name if i < len(plan.units) else ""
            for i in range(len(sessions))
        ]

    total_findings = 0
    total_fixes = 0
    category_counts: dict[str, int] = {}
    weighted_score_sum = 0.0
    weight_sum = 0

    for i, session in enumerate(sessions):
        for rnd in session.rounds:
            total_findings += len(rnd.findings)
            total_fixes += sum(1 for f in rnd.fixes if f.applied)
            for finding in rnd.findings:
                category_counts[finding.category] = (
                    category_counts.get(finding.category, 0) + 1
                )

        # Weighted average score by unit line count (matched by name)
        if session.verdict:
            unit_name = session_unit_names[i] if i < len(session_unit_names) else ""
            unit_lines = unit_line_counts.get(unit_name, 1)
            weighted_score_sum += session.verdict.score * unit_lines
            weight_sum += unit_lines

    report.total_findings = total_findings
    report.total_fixes = total_fixes
    report.category_breakdown = category_counts
    report.aggregate_score = (
        round(weighted_score_sum / weight_sum, 1) if weight_sum > 0 else 0.0
    )
    report.unit_names = list(session_unit_names)
    report.status = "completed"

    return report


def generate_aggregated_markdown(report: AggregatedReport) -> str:
    """Generate a combined markdown report from the aggregated data."""
    lines = [
        f"# Scan Report — `{report.scan_id}`",
        "",
        f"**Status:** {report.status}",
        f"**Aggregate Score:** {report.aggregate_score}/10",
        f"**Total Findings:** {report.total_findings}",
        f"**Total Fixes Applied:** {report.total_fixes}",
        "",
    ]

    # Plan overview
    plan = report.plan
    if plan.get("units"):
        lines.append("## Scan Plan")
        lines.append("")
        lines.append(f"**Target:** `{plan.get('target', '')}`")
        lines.append(f"**Total Files:** {plan.get('total_files', 0)}")
        lines.append(f"**Total Lines:** {plan.get('total_lines', 0):,}")
        lines.append("")
        lines.append("| # | Unit | Tier | Files | Lines |")
        lines.append("|---|------|------|-------|-------|")
        for i, u in enumerate(plan["units"]):
            lines.append(
                f"| {i} | `{u['name']}` | {u['tier']} | {u['file_count']} | {u['line_count']:,} |"
            )
        lines.append("")

    # Per-unit summary
    lines.append("## Unit Results")
    lines.append("")
    lines.append("| Unit | Score | Findings | Fixes | Status |")
    lines.append("|------|-------|----------|-------|--------|")

    for i, session in enumerate(report.unit_sessions):
        unit_name = (
            report.unit_names[i] if i < len(report.unit_names) else session.target
        )
        score = session.verdict.score if session.verdict else "—"
        findings = sum(len(r.findings) for r in session.rounds)
        fixes = sum(1 for r in session.rounds for f in r.fixes if f.applied)
        status = session.verdict.status.value if session.verdict else session.status
        lines.append(f"| `{unit_name}` | {score} | {findings} | {fixes} | {status} |")

    lines.append("")

    # Category breakdown
    if report.category_breakdown:
        lines.append("## Findings by Category")
        lines.append("")
        lines.append("| Category | Count |")
        lines.append("|----------|-------|")
        for cat, count in sorted(
            report.category_breakdown.items(), key=lambda x: -x[1]
        ):
            lines.append(f"| {cat} | {count} |")
        lines.append("")

    # Top findings across all units
    all_findings = []
    for i, session in enumerate(report.unit_sessions):
        unit_name = (
            report.unit_names[i] if i < len(report.unit_names) else session.target
        )
        for rnd in session.rounds:
            for f in rnd.findings:
                all_findings.append((unit_name, f))

    # Show top 20 findings by severity (errors first)
    severity_order = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.SUGGESTION: 2}
    all_findings.sort(key=lambda x: severity_order.get(x[1].severity, 9))
    top_findings = all_findings[:20]

    if top_findings:
        lines.append("## Top Findings")
        lines.append("")
        lines.append("| Unit | File | Line | Severity | Category | Message |")
        lines.append("|------|------|------|----------|----------|---------|")
        for unit_name, f in top_findings:
            lines.append(
                f"| `{unit_name}` | `{f.file}` | {f.line} | {f.severity.value} | {f.category} | {f.message} |"
            )
        lines.append("")

    return "\n".join(lines)


def save_scan_progress(
    scan_id: str,
    plan: ScanPlan,
    completed_sessions: list[ReviewSession],
    completed_unit_names: list[str],
    output_dir: Path,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> Path:
    """Save incremental scan progress after each unit completes."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"scan_{scan_id}_progress.json"
    data = {
        "scan_id": scan_id,
        "plan": plan.to_dict(),
        "completed_unit_names": completed_unit_names,
        "completed_sessions": [s.to_dict() for s in completed_sessions],
        "include": include,
        "exclude": exclude,
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return path


@dataclass
class ScanProgress:
    plan_dict: dict
    completed_names: list[str]
    sessions: list[ReviewSession]
    include: list[str] | None = None
    exclude: list[str] | None = None


def load_scan_progress(
    scan_id: str,
    output_dir: Path,
) -> ScanProgress | None:
    """Load scan progress from a previous run."""
    path = output_dir / f"scan_{scan_id}_progress.json"
    if not path.exists():
        return None
    with open(path) as f:
        data = json.load(f)

    return ScanProgress(
        plan_dict=data.get("plan", {}),
        completed_names=data.get("completed_unit_names", []),
        sessions=[
            ReviewSession.from_dict(s) for s in data.get("completed_sessions", [])
        ],
        include=data.get("include"),
        exclude=data.get("exclude"),
    )


def save_aggregated_report(report: AggregatedReport, output_dir: Path) -> tuple[Path, Path]:
    """Save aggregated report as JSON and Markdown. Returns (json_path, md_path)."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # JSON
    json_path = output_dir / f"scan_{report.scan_id}.json"
    with open(json_path, "w") as f:
        json.dump(report.to_dict(), f, indent=2)

    # Markdown
    md_path = output_dir / f"scan_{report.scan_id}.md"
    md_path.write_text(generate_aggregated_markdown(report))

    return json_path, md_path
