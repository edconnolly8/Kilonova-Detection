"""Generate tailored cover letters using Claude."""

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


COVER_LETTER_SYSTEM = """\
You are a professional cover letter writer for a physics graduate seeking roles in space, \
aerospace, data science, quantitative analysis, and research.

Write a tailored, professional cover letter that:
1. Opens with genuine enthusiasm for the specific company and role
2. Highlights 2-3 most relevant skills/experiences from the resume that match the job description
3. References the kilonova detection project as a concrete example of scientific Python and data analysis
4. Demonstrates understanding of what the company does
5. Closes with a clear call to action

Style guidelines:
- Professional but not stiff — show personality and genuine interest
- 3-4 paragraphs, ~250-350 words
- No generic filler phrases ("I am writing to apply for...")
- Specific and evidence-based
- Do NOT include the address block or date — just the letter body starting with "Dear Hiring Manager," \
  (or the specific contact if known)
"""


async def generate_cover_letter(job: Job, resume: str) -> str:
    """Generate a tailored cover letter for a job posting."""
    client = _get_client()

    prompt = f"""
## Job Details

**Company:** {job.company}
**Role:** {job.title}
**Location:** {job.location}

### Job Description
{job.description[:3000]}

### Key Skills Required (from scoring analysis)
Matched skills: {', '.join(job.matched_skills) if job.matched_skills else 'See description'}
Skill gaps to address: {', '.join(job.skill_gaps) if job.skill_gaps else 'None identified'}

---

## Candidate Resume

{resume[:3000]}

---

Write a tailored cover letter for this position.
"""

    try:
        message = await client.messages.create(
            model=config.MODEL,
            max_tokens=800,
            system=COVER_LETTER_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        letter = message.content[0].text.strip()
        logger.info("Generated cover letter for: %s @ %s", job.title, job.company)
        return letter

    except anthropic.APIError as exc:
        logger.error("Claude API error generating cover letter: %s", exc)
        return _fallback_cover_letter(job)


def _fallback_cover_letter(job: Job) -> str:
    """Minimal fallback if Claude API fails."""
    return (
        f"Dear Hiring Manager,\n\n"
        f"I am writing to express my strong interest in the {job.title} position at {job.company}.\n\n"
        f"As a physics graduate with experience in Python, data analysis, and scientific modelling, "
        f"I believe I have the skills and drive to contribute effectively to your team.\n\n"
        f"I would welcome the opportunity to discuss how my background aligns with your requirements.\n\n"
        f"Yours sincerely,\n{config.USER_NAME}"
    )
