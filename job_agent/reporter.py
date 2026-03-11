"""Generate daily Markdown reports summarising agent activity."""

import logging
from datetime import date
from pathlib import Path

from .config import config
from .database import get_all_jobs_today, get_applied_jobs_today, get_manual_review_jobs, get_scored_jobs
from .models import Application, DailyReport, Job

logger = logging.getLogger(__name__)


def _job_table_row(job: Job) -> str:
    score_pct = f"{job.score * 100:.0f}%" if job.score else "—"
    return f"| {job.company} | {job.title} | {job.location} | {score_pct} | {job.status} | [Link]({job.url}) |"


def _application_table_row(job: Job, app: Application) -> str:
    score_pct = f"{job.score * 100:.0f}%" if job.score else "—"
    date_str = app.applied_at[:10] if app.applied_at else "—"
    return f"| {job.company} | {job.title} | {job.location} | {score_pct} | {date_str} | {app.status} | [Link]({job.url}) |"


async def build_daily_report(db_path: Path) -> DailyReport:
    today = date.today().isoformat()
    report = DailyReport(date=today)

    report.jobs_discovered = await get_all_jobs_today(db_path)
    report.jobs_applied = await get_applied_jobs_today(db_path)
    report.manual_review = await get_manual_review_jobs(db_path)

    # Top uncontacted = scored jobs above threshold not yet applied
    scored = await get_scored_jobs(db_path, config.MIN_SCORE_THRESHOLD)
    applied_urls = {job.url for job, _ in report.jobs_applied}
    report.top_uncontacted = [j for j in scored if j.url not in applied_urls][:10]

    return report


def render_report(report: DailyReport) -> str:
    lines = [
        f"# Daily Job Application Report — {report.date}",
        "",
        f"> {report.summary_line}",
        "",
    ]

    # ── Jobs Discovered ──────────────────────────────────────────────────────
    lines += [
        f"## 1. Jobs Discovered Today ({len(report.jobs_discovered)})",
        "",
        "| Company | Role | Location | Score | Status | Link |",
        "|---------|------|----------|-------|--------|------|",
    ]
    if report.jobs_discovered:
        for job in report.jobs_discovered:
            lines.append(_job_table_row(job))
    else:
        lines.append("| — | No new jobs discovered today | — | — | — | — |")
    lines.append("")

    # ── Jobs Applied ─────────────────────────────────────────────────────────
    lines += [
        f"## 2. Applications Submitted Today ({len(report.jobs_applied)})",
        "",
        "| Company | Role | Location | Score | Date | Status | Link |",
        "|---------|------|----------|-------|------|--------|------|",
    ]
    if report.jobs_applied:
        for job, app in report.jobs_applied:
            lines.append(_application_table_row(job, app))
    else:
        lines.append("| — | No applications submitted today | — | — | — | — | — |")
    lines.append("")

    # ── Manual Review ────────────────────────────────────────────────────────
    lines += [
        f"## 3. Applications Requiring Manual Input ({len(report.manual_review)})",
        "",
        "These jobs require your attention — CAPTCHA, Workday account, or multi-step forms:",
        "",
        "| Company | Role | Location | Score | Link |",
        "|---------|------|----------|-------|------|",
    ]
    if report.manual_review:
        for job in report.manual_review:
            score_pct = f"{job.score * 100:.0f}%" if job.score else "—"
            lines.append(f"| {job.company} | {job.title} | {job.location} | {score_pct} | [Apply]({job.url}) |")
    else:
        lines.append("| — | None requiring manual review | — | — | — |")
    lines.append("")

    # ── Top Uncontacted ──────────────────────────────────────────────────────
    lines += [
        f"## 4. Suggested High-Priority Roles (Not Yet Applied — {len(report.top_uncontacted)})",
        "",
        "| Company | Role | Location | Score | Matched Skills | Link |",
        "|---------|------|----------|-------|----------------|------|",
    ]
    if report.top_uncontacted:
        for job in report.top_uncontacted:
            score_pct = f"{job.score * 100:.0f}%"
            skills = ", ".join(job.matched_skills[:3]) if job.matched_skills else "—"
            lines.append(f"| {job.company} | {job.title} | {job.location} | {score_pct} | {skills} | [View]({job.url}) |")
    else:
        lines.append("| — | All high-scoring jobs have been processed | — | — | — | — |")
    lines.append("")

    return "\n".join(lines)


async def save_report(report: DailyReport, output_dir: Path = Path(".")) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"daily_report_{report.date}.md"
    content = render_report(report)
    report_path.write_text(content, encoding="utf-8")
    logger.info("Report saved: %s", report_path)
    return report_path
