"""Cross-round knowledge accumulation — extract recurring patterns."""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from code_review.state import Finding


@dataclass
class Pattern:
    """A recurring pattern found across multiple findings."""
    description: str
    category: str
    occurrences: int
    example_files: list[str] = field(default_factory=list)


def _messages_similar(a: str, b: str, threshold: float = 0.55) -> bool:
    """Check if two finding messages describe the same pattern."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold


def extract_patterns(
    findings: list[Finding], min_occurrences: int = 2
) -> list[Pattern]:
    """Cluster similar findings and extract patterns that recur.

    Groups findings by similar message text across different files.
    Returns patterns that appear in >= min_occurrences distinct files.
    """
    # Cluster by message similarity
    clusters: list[list[Finding]] = []

    for finding in findings:
        merged = False
        for cluster in clusters:
            if _messages_similar(finding.message, cluster[0].message):
                cluster.append(finding)
                merged = True
                break
        if not merged:
            clusters.append([finding])

    # Convert clusters to patterns
    patterns = []
    for cluster in clusters:
        unique_files = list({f.file for f in cluster})
        if len(unique_files) >= min_occurrences:
            # Use the longest message as the description
            best_msg = max(cluster, key=lambda f: len(f.message)).message
            patterns.append(Pattern(
                description=best_msg,
                category=cluster[0].category,
                occurrences=len(cluster),
                example_files=unique_files[:5],
            ))

    return sorted(patterns, key=lambda p: p.occurrences, reverse=True)


class KnowledgeAccumulator:
    """Accumulates findings across rounds and generates prompt context."""

    def __init__(self):
        self._all_findings: list[Finding] = []
        self._patterns: list[Pattern] = []

    def ingest_round(self, findings: list[Finding]) -> None:
        """Ingest findings from a completed round."""
        self._all_findings.extend(findings)
        self._patterns = extract_patterns(self._all_findings)

    @property
    def patterns(self) -> list[Pattern]:
        return self._patterns

    def get_prompt_context(self) -> str:
        """Generate prompt context from accumulated knowledge."""
        if not self._patterns:
            return ""

        return format_patterns_for_prompt(self._patterns)


def format_patterns_for_prompt(patterns: list[Pattern]) -> str:
    """Format patterns as prompt context for the reviewer."""
    if not patterns:
        return ""

    lines = [
        "",
        "## Known patterns in this codebase",
        "The following recurring issues have been identified across multiple files. "
        "Pay extra attention to these patterns in the files you review:",
        "",
    ]
    for p in patterns:
        files_str = ", ".join(p.example_files[:3])
        lines.append(
            f"- **{p.category}** ({p.occurrences}x, e.g. {files_str}): {p.description}"
        )

    lines.append("")
    return "\n".join(lines)
