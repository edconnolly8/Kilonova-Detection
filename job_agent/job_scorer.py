"""Score job relevance against the user's resume using Claude."""

import json
import logging

import anthropic

from .config import config
from .models import Job

logger = logging.getLogger(__name__)

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


SCORER_SYSTEM = """\
You are an expert career advisor evaluating job suitability for a physics graduate.

The candidate's background:
- BSc/MSc in Physics
- Strong Python programming (NumPy, Pandas, Matplotlib, SciPy, Astropy)
- Data analysis, statistical modelling, Monte Carlo simulation
- Scientific research experience (kilonova detection, astrophysics simulation)
- Looking for graduate/early-career roles in: space, aerospace, data science, quantitative analysis, engineering, research
- Preferred locations: Ireland, UK, EU, Remote

When evaluating a job, respond with a JSON object only (no markdown, no explanation outside JSON):
{
  "score": <float 0.0 to 1.0>,
  "reasoning": "<2-3 sentence explanation>",
  "matched_skills": ["skill1", "skill2", ...],
  "skill_gaps": ["gap1", "gap2", ...],
  "entry_level_fit": <true|false>,
  "location_fit": <true|false>
}

Scoring criteria:
- 0.8–1.0: Excellent match — physics/data/research role, entry-level, good location
- 0.6–0.8: Good match — related field, transferable skills, acceptable location
- 0.4–0.6: Partial match — some relevant skills but significant gaps or wrong level
- 0.0–0.4: Poor match — wrong field, senior role, or incompatible requirements
"""


async def score_job(job: Job, resume: str) -> Job:
    """
    Score a job against the user's resume using Claude.
    Modifies and returns the job with score, score_reasoning, matched_skills, skill_gaps set.
    """
    client = _get_client()

    user_message = f"""
## Job Posting

**Company:** {job.company}
**Title:** {job.title}
**Location:** {job.location}
**URL:** {job.url}

### Description
{job.description[:3000]}

---

## Candidate Resume (summary)

{resume[:2000]}

---

Evaluate this job's suitability for the candidate. Respond with JSON only.
"""

    try:
        message = await client.messages.create(
            model=config.MODEL,
            max_tokens=512,
            system=SCORER_SYSTEM,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = message.content[0].text.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        result = json.loads(raw)
        job.score = float(result.get("score", 0.0))
        job.score_reasoning = result.get("reasoning", "")
        job.matched_skills = result.get("matched_skills", [])
        job.skill_gaps = result.get("skill_gaps", [])
        job.status = "scored"

    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse scorer JSON for '%s': %s", job.title, exc)
        job.score = 0.0
        job.status = "scored"
    except anthropic.APIError as exc:
        logger.error("Claude API error scoring '%s': %s", job.title, exc)
        job.score = 0.0

    logger.info("Scored: %s — %.2f", job.display(), job.score)
    return job


async def score_jobs_batch(jobs: list[Job], resume: str, concurrency: int = 5) -> list[Job]:
    """Score a list of jobs with bounded concurrency."""
    import asyncio

    semaphore = asyncio.Semaphore(concurrency)

    async def _score_with_sem(job: Job) -> Job:
        async with semaphore:
            return await score_job(job, resume)

    return list(await asyncio.gather(*[_score_with_sem(j) for j in jobs]))
