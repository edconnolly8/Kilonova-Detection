"""Job discovery via Adzuna API, SerpAPI (Google Jobs), and Playwright portal scraping."""

import asyncio
import logging
import urllib.parse
from datetime import datetime

import aiohttp

from .config import config
from .models import Job

logger = logging.getLogger(__name__)


# ── Adzuna API ────────────────────────────────────────────────────────────────

async def search_adzuna(session: aiohttp.ClientSession, query: str, country: str) -> list[Job]:
    """Search Adzuna job API for a given query and country code (gb, ie, nl, de, at)."""
    if not config.ADZUNA_APP_ID or not config.ADZUNA_APP_KEY:
        logger.debug("Adzuna credentials not configured, skipping.")
        return []

    url = (
        f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
        f"?app_id={config.ADZUNA_APP_ID}"
        f"&app_key={config.ADZUNA_APP_KEY}"
        f"&results_per_page=20"
        f"&what={urllib.parse.quote(query)}"
        f"&content-type=application/json"
    )
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                logger.warning("Adzuna API returned %s for query '%s' (%s)", resp.status, query, country)
                return []
            data = await resp.json()
    except Exception as exc:
        logger.warning("Adzuna request failed: %s", exc)
        return []

    jobs = []
    for item in data.get("results", []):
        job_url = item.get("redirect_url", "")
        if not job_url:
            continue
        jobs.append(
            Job(
                url=job_url,
                company=item.get("company", {}).get("display_name", ""),
                title=item.get("title", ""),
                location=item.get("location", {}).get("display_name", ""),
                description=item.get("description", ""),
                discovered_at=datetime.utcnow().isoformat(),
            )
        )
    logger.info("Adzuna [%s/%s]: found %d jobs", country, query, len(jobs))
    return jobs


# ── SerpAPI (Google Jobs) ────────────────────────────────────────────────────

async def search_serpapi(session: aiohttp.ClientSession, query: str) -> list[Job]:
    """Search Google Jobs via SerpAPI."""
    if not config.SERPAPI_KEY:
        logger.debug("SerpAPI key not configured, skipping.")
        return []

    params = {
        "engine": "google_jobs",
        "q": query,
        "location": "Ireland, United Kingdom, Europe",
        "api_key": config.SERPAPI_KEY,
        "hl": "en",
        "gl": "ie",
    }
    url = "https://serpapi.com/search?" + urllib.parse.urlencode(params)
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                logger.warning("SerpAPI returned %s for query '%s'", resp.status, query)
                return []
            data = await resp.json()
    except Exception as exc:
        logger.warning("SerpAPI request failed: %s", exc)
        return []

    jobs = []
    for item in data.get("jobs_results", []):
        # Build a stable URL from the job id or apply_options
        apply_options = item.get("apply_options", [])
        job_url = apply_options[0].get("link", "") if apply_options else ""
        if not job_url:
            job_url = f"https://www.google.com/search?q={urllib.parse.quote(item.get('title', ''))}"

        jobs.append(
            Job(
                url=job_url,
                company=item.get("company_name", ""),
                title=item.get("title", ""),
                location=item.get("location", ""),
                description=item.get("description", ""),
                discovered_at=datetime.utcnow().isoformat(),
            )
        )
    logger.info("SerpAPI [%s]: found %d jobs", query, len(jobs))
    return jobs


# ── Playwright portal scraping ───────────────────────────────────────────────

async def scrape_esa_jobs(query: str) -> list[Job]:
    """Scrape ESA Jobs portal."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return []

    jobs = []
    search_url = f"https://jobs.esa.int/search/?q={urllib.parse.quote(query)}"
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(search_url, timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)

            # ESA uses a standard job listing structure
            job_cards = await page.query_selector_all("article.job-listing, .job-item, li[data-job]")
            for card in job_cards[:10]:
                title_el = await card.query_selector("h2, h3, .job-title, a[href*='/job/']")
                link_el = await card.query_selector("a[href*='/job/']")
                location_el = await card.query_selector(".location, .job-location")

                title = await title_el.inner_text() if title_el else ""
                href = await link_el.get_attribute("href") if link_el else ""
                location = await location_el.inner_text() if location_el else "ESTEC/ESAC/Remote"

                if href and title:
                    full_url = href if href.startswith("http") else f"https://jobs.esa.int{href}"
                    jobs.append(
                        Job(
                            url=full_url,
                            company="ESA – European Space Agency",
                            title=title.strip(),
                            location=location.strip(),
                            discovered_at=datetime.utcnow().isoformat(),
                        )
                    )
            await browser.close()
    except Exception as exc:
        logger.warning("ESA scraping failed: %s", exc)

    logger.info("ESA scraper [%s]: found %d jobs", query, len(jobs))
    return jobs


async def scrape_cern_jobs(query: str) -> list[Job]:
    """Scrape CERN SmartRecruiters jobs."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return []

    jobs = []
    search_url = f"https://jobs.smartrecruiters.com/CERN?search={urllib.parse.quote(query)}"
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(search_url, timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)

            job_cards = await page.query_selector_all("li.job-listing, .opening-job, article[data-id]")
            for card in job_cards[:10]:
                title_el = await card.query_selector("h2, h4, .job-title, strong")
                link_el = await card.query_selector("a")
                title = await title_el.inner_text() if title_el else ""
                href = await link_el.get_attribute("href") if link_el else ""

                if href and title:
                    full_url = href if href.startswith("http") else f"https://jobs.smartrecruiters.com{href}"
                    jobs.append(
                        Job(
                            url=full_url,
                            company="CERN",
                            title=title.strip(),
                            location="Geneva, Switzerland",
                            discovered_at=datetime.utcnow().isoformat(),
                        )
                    )
            await browser.close()
    except Exception as exc:
        logger.warning("CERN scraping failed: %s", exc)

    logger.info("CERN scraper [%s]: found %d jobs", query, len(jobs))
    return jobs


async def scrape_wellfound_jobs(query: str) -> list[Job]:
    """Scrape Wellfound (AngelList) jobs."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return []

    jobs = []
    search_url = f"https://wellfound.com/jobs?q={urllib.parse.quote(query)}&l=Remote"
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            # Set realistic user agent to reduce bot detection
            await page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"})
            await page.goto(search_url, timeout=30000)
            await page.wait_for_timeout(3000)  # Allow JS to render

            job_cards = await page.query_selector_all("[data-test='StartupResult'], .styles_component__Ey28k, .job-listing")
            for card in job_cards[:10]:
                title_el = await card.query_selector("h2, h3, [class*='title'], [class*='role']")
                company_el = await card.query_selector("[class*='company'], [class*='startup']")
                link_el = await card.query_selector("a[href*='/jobs/']")

                title = await title_el.inner_text() if title_el else ""
                company = await company_el.inner_text() if company_el else ""
                href = await link_el.get_attribute("href") if link_el else ""

                if href and title:
                    full_url = href if href.startswith("http") else f"https://wellfound.com{href}"
                    jobs.append(
                        Job(
                            url=full_url,
                            company=company.strip(),
                            title=title.strip(),
                            location="Remote",
                            discovered_at=datetime.utcnow().isoformat(),
                        )
                    )
            await browser.close()
    except Exception as exc:
        logger.warning("Wellfound scraping failed: %s", exc)

    logger.info("Wellfound scraper [%s]: found %d jobs", query, len(jobs))
    return jobs


# ── Main discovery function ───────────────────────────────────────────────────

async def discover_jobs(queries: list[str] | None = None) -> list[Job]:
    """
    Run all discovery channels concurrently.
    Returns deduplicated list of Job objects (by URL).
    """
    if queries is None:
        queries = config.SEARCH_QUERIES

    all_jobs: list[Job] = []
    seen_urls: set[str] = set()

    async with aiohttp.ClientSession() as session:
        tasks = []

        # Adzuna: run each query × country combination
        for query in queries[:5]:  # limit to avoid rate limits
            for country in config.ADZUNA_COUNTRIES[:3]:
                tasks.append(search_adzuna(session, query, country))

        # SerpAPI: run each query
        for query in queries[:5]:
            tasks.append(search_serpapi(session, query))

        results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            logger.warning("Discovery task failed: %s", result)
            continue
        for job in result:
            if job.url not in seen_urls:
                seen_urls.add(job.url)
                all_jobs.append(job)

    # Research portals (run sequentially to be polite)
    for query in queries[:2]:
        for scraper in [scrape_esa_jobs, scrape_cern_jobs, scrape_wellfound_jobs]:
            portal_jobs = await scraper(query)
            for job in portal_jobs:
                if job.url not in seen_urls:
                    seen_urls.add(job.url)
                    all_jobs.append(job)

    logger.info("Total unique jobs discovered: %d", len(all_jobs))
    return all_jobs
