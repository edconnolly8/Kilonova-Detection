"""Data models for the job application agent."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Job:
    url: str
    company: str = ""
    title: str = ""
    location: str = ""
    description: str = ""
    score: float = 0.0
    score_reasoning: str = ""
    matched_skills: list[str] = field(default_factory=list)
    skill_gaps: list[str] = field(default_factory=list)
    discovered_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    status: str = "discovered"  # discovered|scored|applying|applied|failed|manual_review
    db_id: Optional[int] = None

    def is_applicable(self, threshold: float) -> bool:
        return self.score >= threshold and self.status == "scored"

    def display(self) -> str:
        score_pct = f"{self.score * 100:.0f}%"
        return f"[{score_pct}] {self.title} @ {self.company} ({self.location})"


@dataclass
class Application:
    job_id: int
    cover_letter: str = ""
    applied_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    confirmation_text: str = ""
    status: str = "pending"  # pending|submitted|confirmed|manual_review|failed
    db_id: Optional[int] = None


@dataclass
class DailyReport:
    date: str
    jobs_discovered: list[Job] = field(default_factory=list)
    jobs_applied: list[tuple[Job, Application]] = field(default_factory=list)
    manual_review: list[Job] = field(default_factory=list)
    top_uncontacted: list[Job] = field(default_factory=list)

    @property
    def summary_line(self) -> str:
        return (
            f"Discovered: {len(self.jobs_discovered)} | "
            f"Applied: {len(self.jobs_applied)} | "
            f"Manual review: {len(self.manual_review)} | "
            f"Top uncontacted: {len(self.top_uncontacted)}"
        )
