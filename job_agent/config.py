"""Configuration loaded from environment variables."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Config:
    # AI
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    MODEL: str = "claude-sonnet-4-6"

    # Job board APIs
    ADZUNA_APP_ID: str = os.getenv("ADZUNA_APP_ID", "")
    ADZUNA_APP_KEY: str = os.getenv("ADZUNA_APP_KEY", "")
    SERPAPI_KEY: str = os.getenv("SERPAPI_KEY", "")

    # User profile
    USER_NAME: str = os.getenv("USER_NAME", "Your Name")
    USER_EMAIL: str = os.getenv("USER_EMAIL", "you@email.com")
    USER_PHONE: str = os.getenv("USER_PHONE", "")
    USER_LOCATION: str = os.getenv("USER_LOCATION", "Dublin, Ireland")

    # Agent settings
    MAX_APPLICATIONS_PER_DAY: int = int(os.getenv("MAX_APPLICATIONS_PER_DAY", "10"))
    MIN_SCORE_THRESHOLD: float = float(os.getenv("MIN_SCORE_THRESHOLD", "0.65"))
    DRY_RUN: bool = os.getenv("DRY_RUN", "false").lower() == "true"
    RESUME_PATH: Path = Path(os.getenv("RESUME_PATH", "resume.md"))
    DB_PATH: Path = Path(os.getenv("DB_PATH", "jobs.db"))

    # Job search queries — tuned to the user's physics/data profile
    SEARCH_QUERIES: list[str] = [
        "graduate physicist data analysis",
        "junior data scientist physics",
        "space research engineer graduate",
        "quantitative analyst graduate physics",
        "data analyst scientific research",
        "astrophysics research associate",
        "aerospace systems engineer graduate",
        "machine learning research engineer physics",
        "scientific software developer python",
        "graduate research scientist data",
    ]

    # Target locations for API searches
    ADZUNA_COUNTRIES: list[str] = ["gb", "ie", "nl", "de", "at"]

    # Research portal URLs to scrape
    RESEARCH_PORTALS: list[dict] = [
        {
            "name": "ESA Jobs",
            "url": "https://jobs.esa.int/job/",
            "search_url": "https://jobs.esa.int/search/?q={query}",
        },
        {
            "name": "CERN Jobs",
            "url": "https://jobs.smartrecruiters.com/CERN",
            "search_url": "https://jobs.smartrecruiters.com/CERN?search={query}",
        },
        {
            "name": "ESO Jobs",
            "url": "https://recruitment.eso.org",
            "search_url": "https://recruitment.eso.org/jobs/search?q={query}",
        },
        {
            "name": "Wellfound",
            "url": "https://wellfound.com/jobs",
            "search_url": "https://wellfound.com/jobs?q={query}&l=Remote",
        },
    ]

    def validate(self) -> list[str]:
        """Return list of missing required configuration keys."""
        missing = []
        if not self.ANTHROPIC_API_KEY:
            missing.append("ANTHROPIC_API_KEY")
        if not self.USER_EMAIL or self.USER_EMAIL == "you@email.com":
            missing.append("USER_EMAIL (update .env with your real email)")
        return missing


config = Config()
