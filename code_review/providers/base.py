"""Base provider ABC for LLM backends."""

from __future__ import annotations

from abc import ABC, abstractmethod

from code_review.state import FileContent, Finding, FixResult, Verdict


class BaseProvider(ABC):
    """Abstract base for all LLM providers."""

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def review(
        self,
        files: list[FileContent],
        system_prompt: str,
        previous_feedback: list[dict] | None = None,
    ) -> list[Finding]:
        """Review files and return findings."""
        ...

    @abstractmethod
    def fix(
        self,
        file: FileContent,
        findings: list[Finding],
        system_prompt: str,
    ) -> FixResult:
        """Fix a file based on findings."""
        ...

    @abstractmethod
    def judge(
        self,
        session_history: str,
        system_prompt: str,
    ) -> Verdict:
        """Evaluate all rounds and produce a verdict."""
        ...
