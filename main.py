#!/usr/bin/env python3
"""
Autonomous Job Application Agent — CLI entry point.

Usage:
    python main.py --run-once       # One complete cycle: discover + score + apply
    python main.py --dry-run        # Discover + score only, no submissions
    python main.py --report         # Print today's report
    python main.py --daemon         # Run daily at 09:00 (APScheduler)
    python main.py --check-config   # Validate configuration and API keys
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Suppress noisy third-party loggers
    logging.getLogger("playwright").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)


async def cmd_run_once(dry_run: bool = False) -> None:
    from job_agent.agent import JobApplicationAgent
    from job_agent.config import config

    if dry_run:
        import os
        os.environ["DRY_RUN"] = "true"
        config.DRY_RUN = True

    agent = JobApplicationAgent()
    result = await agent.run()
    print(result)


async def cmd_report() -> None:
    from job_agent.agent import JobApplicationAgent

    agent = JobApplicationAgent()
    report = await agent.report_only()
    print(report)


def cmd_check_config() -> None:
    from job_agent.config import config

    print("=== Job Agent Configuration Check ===\n")
    missing = config.validate()

    print(f"Model:                  {config.MODEL}")
    print(f"Resume path:            {config.RESUME_PATH} ({'✓ exists' if config.RESUME_PATH.exists() else '✗ NOT FOUND'})")
    print(f"Database path:          {config.DB_PATH}")
    print(f"Max applications/day:   {config.MAX_APPLICATIONS_PER_DAY}")
    print(f"Min score threshold:    {config.MIN_SCORE_THRESHOLD:.0%}")
    print(f"Dry run:                {config.DRY_RUN}")
    print(f"Adzuna configured:      {'✓' if config.ADZUNA_APP_ID and config.ADZUNA_APP_KEY else '✗ (optional)'}")
    print(f"SerpAPI configured:     {'✓' if config.SERPAPI_KEY else '✗ (optional)'}")
    print(f"Anthropic API key:      {'✓ set' if config.ANTHROPIC_API_KEY else '✗ NOT SET'}")
    print(f"User name:              {config.USER_NAME}")
    print(f"User email:             {config.USER_EMAIL}")
    print(f"Target countries:       {', '.join(config.ADZUNA_COUNTRIES)}")
    print()

    if missing:
        print("⚠  Missing required configuration:")
        for item in missing:
            print(f"   - {item}")
        print("\nCopy .env.example to .env and fill in your details.")
        sys.exit(1)
    else:
        print("✓ Configuration looks good. Run `python main.py --run-once` to start.")


def cmd_daemon() -> None:
    """Run the agent on a daily schedule at 09:00."""
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ImportError:
        print("APScheduler not installed. Run: pip install apscheduler")
        sys.exit(1)

    scheduler = BlockingScheduler()

    def daily_job():
        print("Starting scheduled job application cycle...")
        asyncio.run(cmd_run_once())

    scheduler.add_job(daily_job, "cron", hour=9, minute=0)
    print("Job application agent scheduled daily at 09:00. Press Ctrl+C to stop.")
    print("Running first cycle immediately...\n")

    # Run immediately on start, then on schedule
    daily_job()

    try:
        scheduler.start()
    except KeyboardInterrupt:
        print("\nScheduler stopped.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Autonomous Job Application Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--run-once",
        action="store_true",
        help="Run one complete cycle: discover jobs, score, and apply",
    )
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover and score jobs only — no applications submitted",
    )
    group.add_argument(
        "--report",
        action="store_true",
        help="Print today's application report",
    )
    group.add_argument(
        "--daemon",
        action="store_true",
        help="Run continuously, scheduling one cycle per day at 09:00",
    )
    group.add_argument(
        "--check-config",
        action="store_true",
        help="Validate environment configuration and API keys",
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )

    args = parser.parse_args()
    _setup_logging(args.verbose)

    if args.check_config:
        cmd_check_config()
    elif args.report:
        asyncio.run(cmd_report())
    elif args.dry_run:
        asyncio.run(cmd_run_once(dry_run=True))
    elif args.run_once:
        asyncio.run(cmd_run_once(dry_run=False))
    elif args.daemon:
        cmd_daemon()


if __name__ == "__main__":
    main()
