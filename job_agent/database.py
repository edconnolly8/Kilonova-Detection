"""SQLite persistence layer using aiosqlite."""

import json
import aiosqlite
from datetime import date
from pathlib import Path

from .models import Job, Application

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    company TEXT DEFAULT '',
    title TEXT DEFAULT '',
    location TEXT DEFAULT '',
    description TEXT DEFAULT '',
    score REAL DEFAULT 0.0,
    score_reasoning TEXT DEFAULT '',
    matched_skills TEXT DEFAULT '[]',
    skill_gaps TEXT DEFAULT '[]',
    discovered_at TEXT NOT NULL,
    status TEXT DEFAULT 'discovered'
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    cover_letter TEXT DEFAULT '',
    applied_at TEXT NOT NULL,
    confirmation_text TEXT DEFAULT '',
    status TEXT DEFAULT 'pending'
);
"""


async def init_db(db_path: Path) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def upsert_job(db_path: Path, job: Job) -> int:
    """Insert or update a job. Returns the row id."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO jobs (url, company, title, location, description,
                              score, score_reasoning, matched_skills, skill_gaps,
                              discovered_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                company = excluded.company,
                title = excluded.title,
                location = excluded.location,
                description = CASE WHEN excluded.description != '' THEN excluded.description ELSE jobs.description END,
                score = CASE WHEN excluded.score > 0 THEN excluded.score ELSE jobs.score END,
                score_reasoning = CASE WHEN excluded.score_reasoning != '' THEN excluded.score_reasoning ELSE jobs.score_reasoning END,
                matched_skills = CASE WHEN excluded.matched_skills != '[]' THEN excluded.matched_skills ELSE jobs.matched_skills END,
                skill_gaps = CASE WHEN excluded.skill_gaps != '[]' THEN excluded.skill_gaps ELSE jobs.skill_gaps END,
                status = CASE WHEN excluded.status != 'discovered' THEN excluded.status ELSE jobs.status END
            """,
            (
                job.url,
                job.company,
                job.title,
                job.location,
                job.description,
                job.score,
                job.score_reasoning,
                json.dumps(job.matched_skills),
                json.dumps(job.skill_gaps),
                job.discovered_at,
                job.status,
            ),
        )
        await db.commit()
        cursor = await db.execute("SELECT id FROM jobs WHERE url = ?", (job.url,))
        row = await cursor.fetchone()
        return row[0]


async def get_job_by_url(db_path: Path, url: str) -> Job | None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM jobs WHERE url = ?", (url,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_job(row)


async def get_scored_jobs(db_path: Path, min_score: float) -> list[Job]:
    """Return jobs scored above threshold that haven't been applied to yet."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM jobs WHERE status = 'scored' AND score >= ? ORDER BY score DESC",
            (min_score,),
        )
        rows = await cursor.fetchall()
        return [_row_to_job(r) for r in rows]


async def get_applied_today(db_path: Path) -> int:
    """Return count of applications submitted today."""
    today = date.today().isoformat()
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM applications WHERE applied_at LIKE ? AND status IN ('submitted', 'confirmed')",
            (f"{today}%",),
        )
        row = await cursor.fetchone()
        return row[0]


async def save_application(db_path: Path, app: Application) -> int:
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """
            INSERT INTO applications (job_id, cover_letter, applied_at, confirmation_text, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (app.job_id, app.cover_letter, app.applied_at, app.confirmation_text, app.status),
        )
        await db.commit()
        return cursor.lastrowid


async def update_job_status(db_path: Path, job_id: int, status: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
        await db.commit()


async def get_all_jobs_today(db_path: Path) -> list[Job]:
    """Return all jobs discovered today."""
    today = date.today().isoformat()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM jobs WHERE discovered_at LIKE ? ORDER BY score DESC",
            (f"{today}%",),
        )
        rows = await cursor.fetchall()
        return [_row_to_job(r) for r in rows]


async def get_applied_jobs_today(db_path: Path) -> list[tuple[Job, Application]]:
    """Return (job, application) pairs applied today."""
    today = date.today().isoformat()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT j.*, a.id as app_id, a.cover_letter, a.applied_at as app_applied_at,
                   a.confirmation_text, a.status as app_status
            FROM applications a
            JOIN jobs j ON a.job_id = j.id
            WHERE a.applied_at LIKE ?
            ORDER BY a.applied_at DESC
            """,
            (f"{today}%",),
        )
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            job = _row_to_job(row)
            app = Application(
                job_id=row["id"],
                cover_letter=row["cover_letter"],
                applied_at=row["app_applied_at"],
                confirmation_text=row["confirmation_text"],
                status=row["app_status"],
                db_id=row["app_id"],
            )
            result.append((job, app))
        return result


async def get_manual_review_jobs(db_path: Path) -> list[Job]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM jobs WHERE status = 'manual_review' ORDER BY score DESC"
        )
        rows = await cursor.fetchall()
        return [_row_to_job(r) for r in rows]


def _row_to_job(row: aiosqlite.Row) -> Job:
    return Job(
        db_id=row["id"],
        url=row["url"],
        company=row["company"],
        title=row["title"],
        location=row["location"],
        description=row["description"],
        score=row["score"],
        score_reasoning=row["score_reasoning"],
        matched_skills=json.loads(row["matched_skills"]),
        skill_gaps=json.loads(row["skill_gaps"]),
        discovered_at=row["discovered_at"],
        status=row["status"],
    )
