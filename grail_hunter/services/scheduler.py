"""Scheduled job runner using APScheduler.

Runs automatic scans at configured intervals.
"""

import asyncio
from datetime import datetime
from typing import Callable, Awaitable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from grail_hunter.config import get_settings
from grail_hunter.logging import get_logger
from grail_hunter.scrapers import SellpyScraper
from grail_hunter.services.arbitrage import ArbitrageService, DealRating
from grail_hunter.services.notifications import TelegramNotifier

log = get_logger(__name__)


class GrailHunterScheduler:
    """
    Scheduled task runner for Grail Hunter.

    Runs periodic scans and sends notifications for deals.
    """

    def __init__(self) -> None:
        """Initialize scheduler."""
        self.settings = get_settings()
        self._scheduler = AsyncIOScheduler()
        self._running = False
        self._last_scan: datetime | None = None
        self._scan_count = 0
        self._deals_found = 0

    def start(self) -> None:
        """Start the scheduler."""
        if self._running:
            return

        # Add main scan job
        self._scheduler.add_job(
            self._run_scan,
            trigger=IntervalTrigger(minutes=self.settings.scrape_interval_minutes),
            id="grail_scan",
            name="Grail Hunter Scan",
            replace_existing=True,
        )

        # Add health check job
        self._scheduler.add_job(
            self._health_check,
            trigger=IntervalTrigger(minutes=30),
            id="health_check",
            name="Health Check",
            replace_existing=True,
        )

        self._scheduler.start()
        self._running = True
        log.info(
            "scheduler_started",
            interval_minutes=self.settings.scrape_interval_minutes,
        )

    def stop(self) -> None:
        """Stop the scheduler."""
        if not self._running:
            return

        self._scheduler.shutdown(wait=True)
        self._running = False
        log.info("scheduler_stopped")

    async def _run_scan(self) -> None:
        """Run a single scan cycle."""
        log.info("scan_started")
        self._scan_count += 1
        self._last_scan = datetime.now()

        try:
            # Fetch items from Sellpy
            async with SellpyScraper() as scraper:
                items = await scraper.hunt_grails(
                    category="Miehet",
                    include_trash=False,
                )

            log.info("scan_items_fetched", count=len(items))

            if not items:
                return

            # Analyze arbitrage for top items
            async with ArbitrageService() as arbitrage:
                # Only analyze Tier 1 and high-scoring items
                top_items = [
                    i for i in items
                    if i.brand_tier == "TIER_1" or i.item_score >= 80
                ][:20]  # Limit to avoid rate limiting

                if not top_items:
                    log.info("scan_no_top_items")
                    return

                deals = await arbitrage.find_deals(
                    top_items,
                    min_rating=DealRating.GOOD,
                    min_confidence=30.0,
                )

            log.info("scan_deals_found", count=len(deals))

            # Send notifications for good deals
            if deals:
                async with TelegramNotifier() as notifier:
                    # Notify INSANE and GREAT deals
                    hot_deals = [
                        d for d in deals
                        if d.deal_rating in (DealRating.INSANE, DealRating.GREAT)
                    ]

                    sent = await notifier.notify_deals_batch(hot_deals)
                    self._deals_found += sent

                    # Send summary if we found deals
                    if sent > 0:
                        await notifier.send_summary(
                            total_scanned=len(items),
                            deals_found=len(deals),
                            top_deal=deals[0] if deals else None,
                        )

            log.info(
                "scan_completed",
                items_scanned=len(items),
                deals_found=len(deals),
            )

        except Exception as e:
            log.error("scan_failed", error=str(e))

    async def _health_check(self) -> None:
        """Run health check and log status."""
        log.info(
            "health_check",
            running=self._running,
            scan_count=self._scan_count,
            deals_found=self._deals_found,
            last_scan=self._last_scan.isoformat() if self._last_scan else None,
        )

    def run_now(self) -> None:
        """Trigger an immediate scan."""
        if self._running:
            self._scheduler.add_job(
                self._run_scan,
                id="manual_scan",
                replace_existing=True,
            )

    def get_status(self) -> dict:
        """Get scheduler status."""
        return {
            "running": self._running,
            "scan_count": self._scan_count,
            "deals_found": self._deals_found,
            "last_scan": self._last_scan.isoformat() if self._last_scan else None,
            "next_scan": (
                self._scheduler.get_job("grail_scan").next_run_time.isoformat()
                if self._running and self._scheduler.get_job("grail_scan")
                else None
            ),
        }


# Global scheduler instance
_scheduler: GrailHunterScheduler | None = None


def get_scheduler() -> GrailHunterScheduler:
    """Get or create the global scheduler."""
    global _scheduler
    if _scheduler is None:
        _scheduler = GrailHunterScheduler()
    return _scheduler
