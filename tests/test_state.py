"""Tests for state data classes."""

from triplecheck.state import (
    FileContent,
    Finding,
    ReviewRound,
    ReviewSession,
    Severity,
    Verdict,
    VerdictStatus,
)


class TestFileContent:
    def test_auto_detect_python(self):
        fc = FileContent(path="src/main.py", content="x = 1")
        assert fc.language == "python"

    def test_auto_detect_go(self):
        fc = FileContent(path="main.go", content="package main")
        assert fc.language == "go"

    def test_unknown_extension(self):
        fc = FileContent(path="data.xyz", content="stuff")
        assert fc.language == ""

    def test_explicit_language(self):
        fc = FileContent(path="main.py", content="x", language="custom")
        assert fc.language == "custom"


class TestFinding:
    def test_from_dict_standard(self):
        f = Finding.from_dict({
            "file": "app.py",
            "line": 42,
            "severity": "error",
            "category": "bug",
            "message": "null deref",
            "suggestion": "add check",
        })
        assert f.severity == Severity.ERROR
        assert f.file == "app.py"
        assert f.line == 42

    def test_from_dict_severity_mapping(self):
        """LLMs sometimes return non-standard severity values."""
        assert Finding.from_dict({"file": "a.py", "severity": "critical", "message": ""}).severity == Severity.ERROR
        assert Finding.from_dict({"file": "a.py", "severity": "high", "message": ""}).severity == Severity.ERROR
        assert Finding.from_dict({"file": "a.py", "severity": "medium", "message": ""}).severity == Severity.WARNING
        assert Finding.from_dict({"file": "a.py", "severity": "low", "message": ""}).severity == Severity.SUGGESTION
        assert Finding.from_dict({"file": "a.py", "severity": "info", "message": ""}).severity == Severity.SUGGESTION

    def test_from_dict_unknown_severity_defaults_to_warning(self):
        f = Finding.from_dict({"file": "a.py", "severity": "banana", "message": ""})
        assert f.severity == Severity.WARNING

    def test_to_dict_roundtrip(self):
        f = Finding(
            file="app.py", line=10, severity=Severity.WARNING,
            category="bug", message="issue", suggestion="fix it",
        )
        d = f.to_dict()
        f2 = Finding.from_dict(d)
        assert f2.file == f.file
        assert f2.severity == f.severity
        assert f2.message == f.message

    def test_to_dict_omits_defaults(self):
        f = Finding(
            file="a.py", line=1, severity=Severity.ERROR,
            category="bug", message="x",
        )
        d = f.to_dict()
        assert "confidence" not in d  # high is default, omitted
        assert "source" not in d  # reviewer is default, omitted
        assert "pass_ids" not in d  # empty is default, omitted

    def test_to_dict_includes_non_defaults(self):
        f = Finding(
            file="a.py", line=1, severity=Severity.ERROR,
            category="bug", message="x", confidence="low",
            source="static_analysis", pass_ids=[1, 2],
        )
        d = f.to_dict()
        assert d["confidence"] == "low"
        assert d["source"] == "static_analysis"
        assert d["pass_ids"] == [1, 2]


class TestVerdict:
    def test_from_dict_standard(self):
        v = Verdict.from_dict({
            "status": "pass", "score": 8.5,
            "summary": "Good code",
        })
        assert v.status == VerdictStatus.PASS
        assert v.score == 8.5

    def test_from_dict_status_mapping(self):
        assert Verdict.from_dict({"status": "passed"}).status == VerdictStatus.PASS
        assert Verdict.from_dict({"status": "failed"}).status == VerdictStatus.FAIL
        assert Verdict.from_dict({"status": "success"}).status == VerdictStatus.PASS
        assert Verdict.from_dict({"status": "rejected"}).status == VerdictStatus.FAIL
        assert Verdict.from_dict({"status": "unknown_thing"}).status == VerdictStatus.PARTIAL

    def test_roundtrip(self):
        v = Verdict(
            status=VerdictStatus.PASS, score=9.0, summary="Nice",
            category_scores={"security": 8.0}, recommendations=["add tests"],
        )
        d = v.to_dict()
        v2 = Verdict.from_dict(d)
        assert v2.status == v.status
        assert v2.score == v.score
        assert v2.recommendations == v.recommendations


class TestReviewSession:
    def test_roundtrip(self):
        session = ReviewSession(target="/tmp/test")
        rnd = ReviewRound(round_number=1)
        rnd.findings.append(Finding(
            file="a.py", line=1, severity=Severity.ERROR,
            category="bug", message="oops",
        ))
        session.rounds.append(rnd)
        session.verdict = Verdict(
            status=VerdictStatus.PASS, score=8.0, summary="ok",
        )
        d = session.to_dict()
        s2 = ReviewSession.from_dict(d)
        assert s2.session_id == session.session_id
        assert len(s2.rounds) == 1
        assert len(s2.rounds[0].findings) == 1
        assert s2.verdict.score == 8.0
