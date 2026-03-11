"""Playwright-based browser automation for submitting job applications."""

import logging
import re
from pathlib import Path

from .config import config
from .models import Job

logger = logging.getLogger(__name__)

# Known ATS platform URL patterns
ATS_PATTERNS = {
    "greenhouse": re.compile(r"greenhouse\.io|boards\.greenhouse\.io"),
    "lever": re.compile(r"jobs\.lever\.co"),
    "workday": re.compile(r"myworkdayjobs\.com|workday\.com"),
    "smartrecruiters": re.compile(r"smartrecruiters\.com"),
    "icims": re.compile(r"icims\.com"),
}


async def submit_application(
    job: Job,
    cover_letter: str,
    resume_path: Path,
) -> dict:
    """
    Attempt to automatically submit a job application via Playwright.

    Returns:
        {
            "status": "submitted" | "manual_review" | "failed",
            "confirmation": str,
            "reason": str  (if manual_review or failed)
        }
    """
    try:
        from playwright.async_api import async_playwright, TimeoutError as PWTimeout
    except ImportError:
        return {
            "status": "manual_review",
            "confirmation": "",
            "reason": "Playwright not installed. Run: pip install playwright && playwright install chromium",
        }

    if not resume_path.exists():
        return {
            "status": "manual_review",
            "confirmation": "",
            "reason": f"Resume file not found: {resume_path}",
        }

    ats = _detect_ats(job.url)
    logger.info("Submitting to %s (ATS: %s)", job.url, ats or "unknown")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            await page.goto(job.url, timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)

            # Dispatch to ATS-specific handler or generic handler
            if ats == "greenhouse":
                result = await _submit_greenhouse(page, job, cover_letter, resume_path)
            elif ats == "lever":
                result = await _submit_lever(page, job, cover_letter, resume_path)
            elif ats == "workday":
                result = {
                    "status": "manual_review",
                    "confirmation": "",
                    "reason": "Workday requires account creation — flagged for manual application.",
                }
            elif ats == "smartrecruiters":
                result = await _submit_smartrecruiters(page, job, cover_letter, resume_path)
            else:
                result = await _submit_generic(page, job, cover_letter, resume_path)

        except PWTimeout:
            result = {
                "status": "manual_review",
                "confirmation": "",
                "reason": "Page load timeout — may require manual application.",
            }
        except Exception as exc:
            logger.warning("Browser submission failed for %s: %s", job.url, exc)
            result = {
                "status": "failed",
                "confirmation": "",
                "reason": str(exc),
            }
        finally:
            await browser.close()

    return result


def _detect_ats(url: str) -> str | None:
    for name, pattern in ATS_PATTERNS.items():
        if pattern.search(url):
            return name
    return None


async def _submit_greenhouse(page, job: Job, cover_letter: str, resume_path: Path) -> dict:
    """Handle Greenhouse ATS application form."""
    from playwright.async_api import TimeoutError as PWTimeout

    try:
        # Fill first name
        first, *rest = config.USER_NAME.split()
        last = " ".join(rest) if rest else first

        first_name_field = page.locator("input#first_name, input[name='job_application[first_name]']")
        if await first_name_field.count():
            await first_name_field.fill(first)

        last_name_field = page.locator("input#last_name, input[name='job_application[last_name]']")
        if await last_name_field.count():
            await last_name_field.fill(last)

        email_field = page.locator("input#email, input[type='email']")
        if await email_field.count():
            await email_field.fill(config.USER_EMAIL)

        phone_field = page.locator("input#phone, input[type='tel']")
        if await phone_field.count():
            await phone_field.fill(config.USER_PHONE)

        # Resume upload
        resume_input = page.locator("input[type='file'][name*='resume'], input[accept*='.pdf']")
        if await resume_input.count():
            await resume_input.set_input_files(str(resume_path))

        # Cover letter textarea
        cover_letter_field = page.locator(
            "textarea[name*='cover_letter'], textarea[id*='cover_letter'], textarea[placeholder*='cover']"
        )
        if await cover_letter_field.count():
            await cover_letter_field.fill(cover_letter)

        # Submit button
        submit_btn = page.locator("input[type='submit'], button[type='submit'], button:has-text('Submit')")
        if await submit_btn.count():
            await submit_btn.first.click()
            await page.wait_for_load_state("networkidle", timeout=15000)
            confirmation = await _capture_confirmation(page)
            return {"status": "submitted", "confirmation": confirmation, "reason": ""}

        return {
            "status": "manual_review",
            "confirmation": "",
            "reason": "Submit button not found on Greenhouse form.",
        }

    except PWTimeout:
        return {
            "status": "manual_review",
            "confirmation": "",
            "reason": "Greenhouse form timed out.",
        }


async def _submit_lever(page, job: Job, cover_letter: str, resume_path: Path) -> dict:
    """Handle Lever ATS application form."""
    try:
        name_field = page.locator("input[name='name'], input[placeholder*='Name']")
        if await name_field.count():
            await name_field.fill(config.USER_NAME)

        email_field = page.locator("input[name='email'], input[type='email']")
        if await email_field.count():
            await email_field.fill(config.USER_EMAIL)

        phone_field = page.locator("input[name='phone'], input[type='tel']")
        if await phone_field.count():
            await phone_field.fill(config.USER_PHONE)

        resume_input = page.locator("input[type='file']")
        if await resume_input.count():
            await resume_input.set_input_files(str(resume_path))

        cover_field = page.locator("textarea[name*='comments'], textarea[placeholder*='cover'], textarea[name='comments']")
        if await cover_field.count():
            await cover_field.fill(cover_letter)

        submit_btn = page.locator("button[type='submit'], input[type='submit']")
        if await submit_btn.count():
            await submit_btn.first.click()
            await page.wait_for_load_state("networkidle", timeout=15000)
            confirmation = await _capture_confirmation(page)
            return {"status": "submitted", "confirmation": confirmation, "reason": ""}

        return {
            "status": "manual_review",
            "confirmation": "",
            "reason": "Submit button not found on Lever form.",
        }
    except Exception as exc:
        return {"status": "manual_review", "confirmation": "", "reason": str(exc)}


async def _submit_smartrecruiters(page, job: Job, cover_letter: str, resume_path: Path) -> dict:
    """Handle SmartRecruiters application form."""
    try:
        # SmartRecruiters often has a multi-step form; handle first step
        apply_btn = page.locator("button:has-text('Apply'), a:has-text('Apply Now')")
        if await apply_btn.count():
            await apply_btn.first.click()
            await page.wait_for_load_state("networkidle", timeout=10000)

        name_field = page.locator("input[name*='firstName'], input[placeholder*='First']")
        if await name_field.count():
            first, *rest = config.USER_NAME.split()
            await name_field.fill(first)

        last_field = page.locator("input[name*='lastName'], input[placeholder*='Last']")
        if await last_field.count():
            last = " ".join(config.USER_NAME.split()[1:]) or config.USER_NAME
            await last_field.fill(last)

        email_field = page.locator("input[type='email']")
        if await email_field.count():
            await email_field.fill(config.USER_EMAIL)

        resume_input = page.locator("input[type='file']")
        if await resume_input.count():
            await resume_input.set_input_files(str(resume_path))

        next_btn = page.locator("button:has-text('Next'), button:has-text('Continue')")
        if await next_btn.count():
            await next_btn.first.click()
            await page.wait_for_load_state("networkidle", timeout=10000)

        # SmartRecruiters multi-step: flag as manual_review after first step
        return {
            "status": "manual_review",
            "confirmation": "",
            "reason": "SmartRecruiters multi-step form — started first step, requires manual completion.",
        }

    except Exception as exc:
        return {"status": "manual_review", "confirmation": "", "reason": str(exc)}


async def _submit_generic(page, job: Job, cover_letter: str, resume_path: Path) -> dict:
    """Generic form submission attempt for unknown ATS platforms."""
    try:
        # Check for CAPTCHA first
        captcha = await page.query_selector("iframe[src*='recaptcha'], .h-captcha, #cf-challenge")
        if captcha:
            return {
                "status": "manual_review",
                "confirmation": "",
                "reason": "CAPTCHA detected — requires manual completion.",
            }

        # Try to find and fill common form fields
        email_fields = await page.query_selector_all("input[type='email']")
        for field in email_fields:
            await field.fill(config.USER_EMAIL)

        name_fields = await page.query_selector_all("input[type='text'][name*='name'], input[placeholder*='name' i]")
        for field in name_fields[:1]:
            await field.fill(config.USER_NAME)

        file_inputs = await page.query_selector_all("input[type='file']")
        for fi in file_inputs[:1]:
            await fi.set_input_files(str(resume_path))

        cover_areas = await page.query_selector_all(
            "textarea[name*='cover'], textarea[placeholder*='cover' i], textarea[name*='letter']"
        )
        for area in cover_areas[:1]:
            await area.fill(cover_letter)

        # Attempt to click submit
        submit_candidates = await page.query_selector_all(
            "button[type='submit'], input[type='submit'], button:has-text('Submit'), button:has-text('Apply')"
        )
        if submit_candidates:
            await submit_candidates[0].click()
            await page.wait_for_load_state("networkidle", timeout=15000)
            confirmation = await _capture_confirmation(page)
            return {"status": "submitted", "confirmation": confirmation, "reason": ""}

        return {
            "status": "manual_review",
            "confirmation": "",
            "reason": "Generic form handler could not locate submit button.",
        }

    except Exception as exc:
        return {"status": "failed", "confirmation": "", "reason": str(exc)}


async def _capture_confirmation(page) -> str:
    """Try to extract a confirmation message from the page after submission."""
    try:
        await page.wait_for_timeout(2000)
        # Look for common confirmation text patterns
        for selector in [
            "[class*='confirmation']",
            "[class*='success']",
            "[class*='thank']",
            "h1, h2",
        ]:
            el = await page.query_selector(selector)
            if el:
                text = await el.inner_text()
                if any(kw in text.lower() for kw in ["thank", "success", "received", "submitted", "confirm"]):
                    return text.strip()[:500]
        return await page.title()
    except Exception:
        return ""
