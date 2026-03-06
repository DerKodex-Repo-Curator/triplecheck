"""Tests for knowledge accumulation."""

from triplecheck.knowledge import (
    KnowledgeAccumulator,
    extract_patterns,
    format_patterns_for_prompt,
)
from triplecheck.state import Finding, Severity


def _make_finding(file: str, message: str, category: str = "bug") -> Finding:
    return Finding(
        file=file, line=1, severity=Severity.WARNING,
        category=category, message=message,
    )


class TestExtractPatterns:
    def test_clusters_similar_messages(self):
        findings = [
            _make_finding("a.py", "Missing null check before access"),
            _make_finding("b.py", "Missing null check before access"),
            _make_finding("c.py", "Missing null check before access"),
        ]
        patterns = extract_patterns(findings, min_occurrences=2)
        assert len(patterns) == 1
        assert patterns[0].occurrences == 3
        assert len(patterns[0].example_files) == 3

    def test_ignores_single_occurrence(self):
        findings = [
            _make_finding("a.py", "Missing null check"),
            _make_finding("b.py", "Completely different issue"),
        ]
        patterns = extract_patterns(findings, min_occurrences=2)
        assert len(patterns) == 0

    def test_same_file_doesnt_count_as_recurring(self):
        findings = [
            _make_finding("a.py", "Missing null check"),
            _make_finding("a.py", "Missing null check"),
        ]
        patterns = extract_patterns(findings, min_occurrences=2)
        assert len(patterns) == 0  # only 1 unique file

    def test_multiple_distinct_patterns(self):
        findings = [
            _make_finding("a.py", "Missing null check"),
            _make_finding("b.py", "Missing null check"),
            _make_finding("c.py", "SQL injection risk"),
            _make_finding("d.py", "SQL injection risk"),
        ]
        patterns = extract_patterns(findings, min_occurrences=2)
        assert len(patterns) == 2


class TestFormatPatterns:
    def test_empty(self):
        assert format_patterns_for_prompt([]) == ""

    def test_contains_pattern_text(self):
        findings = [
            _make_finding("a.py", "Missing error handling"),
            _make_finding("b.py", "Missing error handling"),
        ]
        patterns = extract_patterns(findings)
        text = format_patterns_for_prompt(patterns)
        assert "Missing error handling" in text
        assert "Known patterns" in text


class TestKnowledgeAccumulator:
    def test_accumulates_across_rounds(self):
        acc = KnowledgeAccumulator()
        acc.ingest_round([_make_finding("a.py", "Missing null check")])
        assert acc.get_prompt_context() == ""  # only 1 file

        acc.ingest_round([_make_finding("b.py", "Missing null check")])
        ctx = acc.get_prompt_context()
        assert "Missing null check" in ctx

    def test_empty_accumulator(self):
        acc = KnowledgeAccumulator()
        assert acc.get_prompt_context() == ""
        assert acc.patterns == []
