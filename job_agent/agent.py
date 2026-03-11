"""Main orchestration agent using Claude tool_use to coordinate all subsystems."""

import json
import logging
from datetime import date
from pathlib import Path

import anthropic

from .browser import submit_application
from .config import config
from .cover_letter import generate_cover_letter
from .database import (
    get_applied_today,
    get_scored_jobs,
    init_db,
    save_application,
    update_job_status,
    upsert_job,
)
from .job_scorer import score_jobs_batch
from .job_search import discover_jobs
from .models import Application, Job
from .reporter import build_daily_report, render_report, save_report

logger = logging.getLogger(__name__)


# ── Tool definitions for Claude ───────────────────────────────────────────────

TOOLS = [
    {
        "name": "search_jobs",
        "description": "Search for new job postings across Adzuna, SerpAPI (Google Jobs), and research portals (ESA, CERN, Wellfound). Returns a count of newly discovered jobs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of search queries. Defaults to the configured profile queries if omitted.",
                }
            },
        },
    },
    {
        "name": "score_pending_jobs",
        "description": "Score all newly discovered jobs for relevance against the user's resume. Returns a summary of scores.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "apply_to_top_jobs",
        "description": "Generate cover letters and submit applications to the highest-scoring jobs not yet applied to.",
        "input_schema": {
            "type": "object",
            "properties": {
                "max_applications": {
                    "type": "integer",
                    "description": "Maximum number of applications to submit in this batch. Defaults to remaining daily quota.",
                }
            },
        },
    },
    {
        "name": "get_daily_summary",
        "description": "Generate and return today's application report as a markdown string.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

AGENT_SYSTEM = f"""\
You are an autonomous job application agent for a physics graduate. Today is {date.today().isoformat()}.

Your goal each session:
1. Search for new jobs matching the candidate's profile
2. Score all new jobs for relevance
3. Apply to the best matches (respecting the daily limit of {config.MAX_APPLICATIONS_PER_DAY})
4. Generate a daily summary report

Use the provided tools to complete this workflow. Be systematic:
- First search for jobs
- Then score them
- Then apply to the top-scoring ones above the threshold ({config.MIN_SCORE_THRESHOLD:.0%})
- Finally get the daily summary

If dry_run is enabled, still discover and score but do not submit applications.
Dry run mode: {'ENABLED — discovery and scoring only, no submissions' if config.DRY_RUN else 'disabled'}
"""


class JobApplicationAgent:
    def __init__(self, db_path: Path | None = None, resume_path: Path | None = None):
        self.db_path = db_path or config.DB_PATH
        self.resume_path = resume_path or config.RESUME_PATH
        self.resume: str = ""
        self.client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
        self._new_jobs: list[Job] = []

    async def _load_resume(self) -> None:
        if not self.resume_path.exists():
            raise FileNotFoundError(
                f"Resume not found at {self.resume_path}. "
                "Please update resume.md with your details."
            )
        self.resume = self.resume_path.read_text(encoding="utf-8")
        logger.info("Loaded resume (%d chars)", len(self.resume))

    # ── Tool handlers ─────────────────────────────────────────────────────────

    async def _tool_search_jobs(self, queries: list[str] | None = None) -> str:
        jobs = await discover_jobs(queries)
        new_count = 0
        self._new_jobs = []
        for job in jobs:
            job_id = await upsert_job(self.db_path, job)
            job.db_id = job_id
            if job.status == "discovered":
                self._new_jobs.append(job)
                new_count += 1
        return json.dumps({
            "total_discovered": len(jobs),
            "new_jobs": new_count,
            "sample_titles": [j.title for j in self._new_jobs[:5]],
        })

    async def _tool_score_pending_jobs(self) -> str:
        if not self._new_jobs:
            # Reload from DB
            from .database import get_all_jobs_today
            all_today = await get_all_jobs_today(self.db_path)
            self._new_jobs = [j for j in all_today if j.status == "discovered"]

        if not self._new_jobs:
            return json.dumps({"message": "No unscored jobs to process."})

        scored = await score_jobs_batch(self._new_jobs, self.resume)
        for job in scored:
            await upsert_job(self.db_path, job)

        above_threshold = [j for j in scored if j.score >= config.MIN_SCORE_THRESHOLD]
        return json.dumps({
            "total_scored": len(scored),
            "above_threshold": len(above_threshold),
            "top_jobs": [
                {"title": j.title, "company": j.company, "score": round(j.score, 2)}
                for j in sorted(above_threshold, key=lambda x: x.score, reverse=True)[:5]
            ],
        })

    async def _tool_apply_to_top_jobs(self, max_applications: int | None = None) -> str:
        applied_today = await get_applied_today(self.db_path)
        remaining = config.MAX_APPLICATIONS_PER_DAY - applied_today
        if max_applications is not None:
            remaining = min(remaining, max_applications)

        if remaining <= 0:
            return json.dumps({"message": f"Daily application limit reached ({config.MAX_APPLICATIONS_PER_DAY})."})

        if config.DRY_RUN:
            return json.dumps({"message": "Dry run mode — no applications submitted."})

        top_jobs = await get_scored_jobs(self.db_path, config.MIN_SCORE_THRESHOLD)
        top_jobs = top_jobs[:remaining]

        results = []
        for job in top_jobs:
            await update_job_status(self.db_path, job.db_id, "applying")

            cover_letter = await generate_cover_letter(job, self.resume)
            submission = await submit_application(job, cover_letter, self.resume_path)

            app = Application(
                job_id=job.db_id,
                cover_letter=cover_letter,
                confirmation_text=submission.get("confirmation", ""),
                status=submission["status"],
            )
            app.db_id = await save_application(self.db_path, app)
            await update_job_status(self.db_path, job.db_id, submission["status"])

            results.append({
                "company": job.company,
                "title": job.title,
                "status": submission["status"],
                "reason": submission.get("reason", ""),
            })
            logger.info("Applied: %s — %s", job.display(), submission["status"])

        submitted = sum(1 for r in results if r["status"] == "submitted")
        manual = sum(1 for r in results if r["status"] == "manual_review")
        return json.dumps({
            "attempted": len(results),
            "submitted": submitted,
            "manual_review": manual,
            "details": results,
        })

    async def _tool_get_daily_summary(self) -> str:
        report = await build_daily_report(self.db_path)
        report_path = await save_report(report)
        return render_report(report) + f"\n\n---\n*Report saved to: {report_path}*"

    async def _dispatch_tool(self, tool_name: str, tool_input: dict) -> str:
        if tool_name == "search_jobs":
            return await self._tool_search_jobs(tool_input.get("queries"))
        elif tool_name == "score_pending_jobs":
            return await self._tool_score_pending_jobs()
        elif tool_name == "apply_to_top_jobs":
            return await self._tool_apply_to_top_jobs(tool_input.get("max_applications"))
        elif tool_name == "get_daily_summary":
            return await self._tool_get_daily_summary()
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    # ── Main agent loop ───────────────────────────────────────────────────────

    async def run(self) -> str:
        """Run one full agent cycle. Returns the daily report string."""
        await init_db(self.db_path)
        await self._load_resume()

        messages = [
            {
                "role": "user",
                "content": (
                    "Run a complete job search and application cycle for today. "
                    "Search for jobs, score them, apply to the best matches, "
                    "then provide a daily summary report."
                ),
            }
        ]

        logger.info("Starting job application agent cycle...")

        while True:
            response = await self.client.messages.create(
                model=config.MODEL,
                max_tokens=4096,
                system=AGENT_SYSTEM,
                tools=TOOLS,
                messages=messages,
            )

            # Add assistant response to history
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                # Extract final text response
                final_text = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        final_text = block.text
                logger.info("Agent cycle complete.")
                return final_text

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        logger.info("Agent calling tool: %s(%s)", block.name, json.dumps(block.input)[:100])
                        result = await self._dispatch_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                messages.append({"role": "user", "content": tool_results})
            else:
                logger.warning("Unexpected stop reason: %s", response.stop_reason)
                break

        return "Agent cycle ended unexpectedly."

    async def report_only(self) -> str:
        """Generate and return today's report without running a full cycle."""
        await init_db(self.db_path)
        report = await build_daily_report(self.db_path)
        await save_report(report)
        return render_report(report)
