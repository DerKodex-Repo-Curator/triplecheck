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

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "line": self.line,
            "severity": self.severity.value,
            "category": self.category,
            "message": self.message,
            "suggestion": self.suggestion,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Finding:
        return cls(
            file=d["file"],
            line=d.get("line", 0),
            severity=Severity(d.get("severity", "warning")),
            category=d.get("category", "general"),
            message=d["message"],
            suggestion=d.get("suggestion", ""),
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
        return cls(
            status=VerdictStatus(d.get("status", "partial")),
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
