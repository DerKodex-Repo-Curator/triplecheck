"""Multi-pass review with vote aggregation."""

from __future__ import annotations

import random
from difflib import SequenceMatcher

import click

from code_review.file_grouper import batch_files
from code_review.state import FileContent, Finding

# Focus angles for each pass — each emphasizes different concerns
FOCUS_ANGLES = [
    {
        "name": "bugs_correctness",
        "instruction": (
            "FOCUS THIS PASS: Prioritize bugs and correctness issues — "
            "logic errors, off-by-one, nil/None dereferences, race conditions, "
            "incorrect state transitions, wrong return values."
        ),
    },
    {
        "name": "security",
        "instruction": (
            "FOCUS THIS PASS: Prioritize security vulnerabilities — "
            "injection (SQL/command/path), hardcoded secrets, unsafe deserialization, "
            "SSRF, path traversal, broken auth, missing input validation."
        ),
    },
    {
        "name": "error_handling",
        "instruction": (
            "FOCUS THIS PASS: Prioritize error handling issues — "
            "swallowed exceptions, missing error checks, panic/crash paths, "
            "incomplete cleanup, resource leaks, unhelpful error messages."
        ),
    },
    {
        "name": "performance",
        "instruction": (
            "FOCUS THIS PASS: Prioritize performance issues — "
            "unnecessary allocations, O(n^2) where O(n) suffices, missing caching, "
            "unbounded growth, N+1 queries, blocking calls in hot paths."
        ),
    },
    {
        "name": "concurrency",
        "instruction": (
            "FOCUS THIS PASS: Prioritize concurrency issues — "
            "data races, deadlocks, missing synchronization, unsafe shared state, "
            "goroutine/thread leaks, incorrect use of channels/locks/atomics."
        ),
    },
]


def _augment_prompt(base_prompt: str, focus: dict) -> str:
    """Append focus instruction to the base reviewer prompt."""
    return f"{base_prompt}\n\n{focus['instruction']}"


def _similar(a: str, b: str, threshold: float = 0.6) -> bool:
    """Check if two strings are similar using SequenceMatcher."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold


def _lines_close(a: int, b: int, tolerance: int = 5) -> bool:
    """Check if two line numbers are within tolerance."""
    return abs(a - b) <= tolerance


def aggregate_findings(
    all_pass_findings: list[list[Finding]],
    min_votes: int = 2,
) -> list[Finding]:
    """Aggregate findings across passes using vote-based deduplication.

    Findings matching on file + line(+-5) + message similarity are clustered.
    Clusters with >= min_votes passes are marked high confidence;
    others are marked low confidence.
    """
    # Flatten with pass IDs
    tagged: list[tuple[int, Finding]] = []
    for pass_id, findings in enumerate(all_pass_findings):
        for f in findings:
            tagged.append((pass_id, f))

    # Cluster findings
    clusters: list[list[tuple[int, Finding]]] = []

    for pass_id, finding in tagged:
        merged = False
        for cluster in clusters:
            # Check if this finding matches any in the cluster
            _, representative = cluster[0]
            if (
                finding.file == representative.file
                and _lines_close(finding.line, representative.line)
                and _similar(finding.message, representative.message)
            ):
                # Don't count the same pass twice
                existing_passes = {pid for pid, _ in cluster}
                if pass_id not in existing_passes:
                    cluster.append((pass_id, finding))
                merged = True
                break

        if not merged:
            clusters.append([(pass_id, finding)])

    # Convert clusters to findings with confidence
    result: list[Finding] = []
    for cluster in clusters:
        pass_ids = sorted({pid for pid, _ in cluster})
        # Use the finding with the most detail (longest message) as representative
        _, best = max(cluster, key=lambda x: len(x[1].message))

        confidence = "high" if len(pass_ids) >= min_votes else "low"
        result.append(Finding(
            file=best.file,
            line=best.line,
            severity=best.severity,
            category=best.category,
            message=best.message,
            suggestion=best.suggestion,
            confidence=confidence,
            source=best.source,
            pass_ids=pass_ids,
        ))

    return result


def multi_pass_review(
    reviewer,
    files: list[FileContent],
    base_prompt: str,
    num_passes: int = 3,
    batch_max_lines: int = 6000,
    min_votes: int = 2,
    previous_feedback: list[dict] | None = None,
) -> list[Finding]:
    """Run multiple review passes with different focus angles, then aggregate.

    Each pass shuffles file order and uses a different focus angle.
    Results are aggregated by vote count.
    """
    all_pass_findings: list[list[Finding]] = []

    for pass_idx in range(num_passes):
        focus = FOCUS_ANGLES[pass_idx % len(FOCUS_ANGLES)]
        prompt = _augment_prompt(base_prompt, focus)

        # Shuffle file order for each pass to reduce position bias
        shuffled = list(files)
        random.shuffle(shuffled)

        batches = batch_files(shuffled, max_lines=batch_max_lines)
        pass_findings: list[Finding] = []

        click.echo(f"    Pass {pass_idx + 1}/{num_passes} (focus: {focus['name']})")
        for i, batch in enumerate(batches):
            click.echo(f"      Batch {i + 1}/{len(batches)} ({len(batch)} files)...")
            findings = reviewer.review(batch, prompt, previous_feedback)
            pass_findings.extend(findings)

        click.echo(f"      → {len(pass_findings)} findings")
        all_pass_findings.append(pass_findings)

    # Aggregate across passes
    aggregated = aggregate_findings(all_pass_findings, min_votes=min_votes)
    high = sum(1 for f in aggregated if f.confidence == "high")
    low = sum(1 for f in aggregated if f.confidence == "low")
    click.echo(f"    Aggregated: {len(aggregated)} unique ({high} high, {low} low confidence)")

    return aggregated
