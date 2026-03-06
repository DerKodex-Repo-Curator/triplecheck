"""Data classes for review session state."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"
    SUGGESTION = "suggestion"


class VerdictStatus(Enum):
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"


@dataclass
class FileContent:
    path: Path
    content: str
    language: str = ""

    def __post_init__(self):
        if not self.language:
            suffix_map = {
                ".py": "python", ".js": "javascript", ".ts": "typescript",
                ".rs": "rust", ".go": "go", ".java": "java", ".rb": "ruby",
                ".c": "c", ".cpp": "cpp", ".h": "c", ".hpp": "cpp",
                ".sh": "bash", ".yml": "yaml", ".yaml": "yaml",
                ".json": "json", ".toml": "toml", ".md": "markdown",
            }
            self.language = suffix_map.get(Path(self.path).suffix, "")


@dataclass
class Finding:
    file: str
    line: int
    severity: Severity
    category: str
    message: str
    suggestion: str = ""
    confidence: str = "high"  # high | low
    source: str = "reviewer"  # reviewer | static_analysis | layer_<name>
    pass_ids: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {
            "file": self.file,
            "line": self.line,
            "severity": self.severity.value,
            "category": self.category,
            "message": self.message,
            "suggestion": self.suggestion,
        }
        if self.confidence != "high":
            d["confidence"] = self.confidence
        if self.source != "reviewer":
            d["source"] = self.source
        if self.pass_ids:
            d["pass_ids"] = self.pass_ids
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Finding:
        # Map non-standard severity values from LLMs to valid ones
        raw_sev = d.get("severity", "warning")
        severity_map = {
            "error": "error", "warning": "warning", "suggestion": "suggestion",
            "critical": "error", "high": "error", "medium": "warning",
            "low": "suggestion", "info": "suggestion",
            "performance": "warning", "security": "error", "bug": "error",
        }
        sev = severity_map.get(raw_sev, "warning")
        return cls(
            file=d["file"],
            line=d.get("line", 0),
            severity=Severity(sev),
            category=d.get("category", "general"),
            message=d.get("message", ""),
            suggestion=d.get("suggestion", ""),
            confidence=d.get("confidence", "high"),
            source=d.get("source", "reviewer"),
            pass_ids=d.get("pass_ids", []),
        )


@dataclass
class FixResult:
    file: str
    applied: bool
    original: str
    fixed: str
    explanation: str = ""
    findings_addressed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "applied": self.applied,
            "explanation": self.explanation,
            "findings_addressed": self.findings_addressed,
        }


@dataclass
class Verdict:
    status: VerdictStatus
    score: float  # 0-10
    summary: str
    category_scores: dict[str, float] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "score": self.score,
            "summary": self.summary,
            "category_scores": self.category_scores,
            "recommendations": self.recommendations,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Verdict:
        raw_status = d.get("status", "partial")
        status_map = {
            "pass": "pass", "fail": "fail", "partial": "partial",
            "passed": "pass", "failed": "fail",
            "success": "pass", "error": "fail",
            "running": "partial", "pending": "partial",
            "approved": "pass", "rejected": "fail",
        }
        status = status_map.get(raw_status, "partial")
        return cls(
            status=VerdictStatus(status),
            score=d.get("score", 0.0),
            summary=d.get("summary", ""),
            category_scores=d.get("category_scores", {}),
            recommendations=d.get("recommendations", []),
        )


@dataclass
class ReviewRound:
    round_number: int
    findings: list[Finding] = field(default_factory=list)
    fixes: list[FixResult] = field(default_factory=list)
    ci_passed: bool | None = None
    ci_output: str = ""

    def to_dict(self) -> dict:
        return {
            "round_number": self.round_number,
            "findings": [f.to_dict() for f in self.findings],
            "fixes": [f.to_dict() for f in self.fixes],
            "ci_passed": self.ci_passed,
            "ci_output": self.ci_output,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ReviewRound:
        return cls(
            round_number=d.get("round_number", 0),
            findings=[Finding.from_dict(f) for f in d.get("findings", [])],
            fixes=[],  # Fixes aren't needed for resume (no original/fixed content)
            ci_passed=d.get("ci_passed"),
            ci_output=d.get("ci_output", ""),
        )


@dataclass
class ReviewSession:
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    target: str = ""
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    config_snapshot: dict = field(default_factory=dict)
    rounds: list[ReviewRound] = field(default_factory=list)
    verdict: Verdict | None = None
    status: str = "running"  # running | completed | failed | interrupted

    def to_dict(self) -> dict:
        d = {
            "session_id": self.session_id,
            "target": self.target,
            "started_at": self.started_at,
            "config_snapshot": self.config_snapshot,
            "rounds": [r.to_dict() for r in self.rounds],
            "status": self.status,
        }
        if self.verdict:
            d["verdict"] = self.verdict.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> ReviewSession:
        verdict = Verdict.from_dict(d["verdict"]) if d.get("verdict") is not None else None
        return cls(
            session_id=d.get("session_id", uuid.uuid4().hex[:12]),
            target=d.get("target", ""),
            started_at=d.get("started_at", ""),
            config_snapshot=d.get("config_snapshot", {}),
            rounds=[ReviewRound.from_dict(r) for r in d.get("rounds", [])],
            verdict=verdict,
            status=d.get("status", "completed"),
        )


@dataclass
class AggregatedReport:
    scan_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    plan: dict = field(default_factory=dict)
    unit_sessions: list[ReviewSession] = field(default_factory=list)
    unit_names: list[str] = field(default_factory=list)  # Parallel to unit_sessions
    aggregate_score: float = 0.0
    total_findings: int = 0
    total_fixes: int = 0
    category_breakdown: dict[str, int] = field(default_factory=dict)
    status: str = "running"  # running | completed | failed

    def to_dict(self) -> dict:
        return {
            "scan_id": self.scan_id,
            "plan": self.plan,
            "unit_sessions": [s.to_dict() for s in self.unit_sessions],
            "unit_names": self.unit_names,
            "aggregate_score": self.aggregate_score,
            "total_findings": self.total_findings,
            "total_fixes": self.total_fixes,
            "category_breakdown": self.category_breakdown,
            "status": self.status,
        }
