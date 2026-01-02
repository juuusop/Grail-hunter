"""Telegram notification service for grail alerts.

Sends notifications for INSANE and GREAT deals.
"""

import asyncio
from dataclasses import dataclass
from enum import Enum

from telegram import Bot
from telegram.constants import ParseMode

from grail_hunter.config import get_settings
from grail_hunter.logging import get_logger
from grail_hunter.services.arbitrage import ArbitrageResult, DealRating

log = get_logger(__name__)


class NotificationPriority(str, Enum):
    """Notification priority levels."""

    CRITICAL = "CRITICAL"  # INSANE deals
    HIGH = "HIGH"  # GREAT deals
    MEDIUM = "MEDIUM"  # GOOD deals
    LOW = "LOW"  # Info


@dataclass
class NotificationConfig:
    """Notification service configuration."""

    bot_token: str
    chat_id: str
    enabled: bool = True
    min_deal_rating: DealRating = DealRating.GREAT


class TelegramNotifier:
    """
    Telegram notification service.

    Sends formatted messages with item images for deals.
    """

    def __init__(self, config: NotificationConfig | None = None) -> None:
        """Initialize with configuration."""
        if config:
            self.config = config
        else:
            # Load from settings
            settings = get_settings()
            self.config = NotificationConfig(
                bot_token=settings.telegram_bot_token,
                chat_id=settings.telegram_chat_id,
                enabled=bool(settings.telegram_bot_token and settings.telegram_chat_id),
            )

        self._bot: Bot | None = None
        self._seen_items: set[str] = set()  # Deduplication

    async def __aenter__(self) -> "TelegramNotifier":
        """Initialize bot."""
        if self.config.enabled:
            self._bot = Bot(token=self.config.bot_token)
        return self

    async def __aexit__(self, *args) -> None:
        """Cleanup."""
        pass

    def _format_deal_message(self, result: ArbitrageResult) -> str:
        """Format a deal as a Telegram message."""
        item = result.sellpy_item

        # Emoji based on rating
        emoji = {
            DealRating.INSANE: "🔥🔥🔥",
            DealRating.GREAT: "💰💰",
            DealRating.GOOD: "✅",
            DealRating.FAIR: "➖",
        }.get(result.deal_rating, "")

        # Build message
        lines = [
            f"{emoji} *{result.deal_rating.value} DEAL* {emoji}",
            "",
            f"*{item.brand}*",
            f"_{item.title}_",
            "",
            f"💵 *Sellpy:* €{item.price:.0f}",
        ]

        if result.estimated_market_value:
            lines.append(f"📊 *Market:* €{result.estimated_market_value:.0f}")

        if result.potential_profit:
            lines.append(f"💰 *Profit:* +€{result.potential_profit:.0f} ({result.profit_margin_pct:.0f}%)")

        lines.extend([
            "",
            f"📏 Size: {item.size or 'N/A'}",
            f"🏷️ Condition: {item.condition or 'N/A'}",
            "",
            f"[Open on Sellpy]({item.item_url})",
        ])

        # Add market links
        if item.brand:
            brand_encoded = item.brand.replace(" ", "+")
            lines.extend([
                "",
                f"[Search Grailed](https://www.grailed.com/shop?query={brand_encoded})",
                f"[Search eBay](https://www.ebay.com/sch/i.html?_nkw={brand_encoded})",
            ])

        return "\n".join(lines)

    async def notify_deal(self, result: ArbitrageResult) -> bool:
        """
        Send notification for a deal.

        Args:
            result: Arbitrage analysis result

        Returns:
            True if notification was sent
        """
        if not self.config.enabled or not self._bot:
            log.debug("notifications_disabled")
            return False

        # Check if meets minimum rating
        rating_order = {
            DealRating.INSANE: 4,
            DealRating.GREAT: 3,
            DealRating.GOOD: 2,
            DealRating.FAIR: 1,
            DealRating.OVERPRICED: 0,
            DealRating.UNKNOWN: -1,
        }

        if rating_order[result.deal_rating] < rating_order[self.config.min_deal_rating]:
            return False

        # Deduplication
        item_id = result.sellpy_item.object_id
        if item_id in self._seen_items:
            log.debug("notification_skipped_duplicate", item_id=item_id)
            return False

        self._seen_items.add(item_id)

        try:
            message = self._format_deal_message(result)

            # Send photo with caption if image available
            if result.sellpy_item.image_url:
                await self._bot.send_photo(
                    chat_id=self.config.chat_id,
                    photo=result.sellpy_item.image_url,
                    caption=message,
                    parse_mode=ParseMode.MARKDOWN,
                )
            else:
                await self._bot.send_message(
                    chat_id=self.config.chat_id,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=False,
                )

            log.info(
                "notification_sent",
                item_id=item_id,
                rating=result.deal_rating.value,
                brand=result.sellpy_item.brand,
            )
            return True

        except Exception as e:
            log.error("notification_failed", error=str(e), item_id=item_id)
            return False

    async def notify_deals_batch(self, results: list[ArbitrageResult]) -> int:
        """
        Send notifications for multiple deals.

        Args:
            results: List of arbitrage results

        Returns:
            Number of notifications sent
        """
        sent = 0
        for result in results:
            if await self.notify_deal(result):
                sent += 1
                # Avoid rate limiting
                await asyncio.sleep(1)
        return sent

    async def send_summary(
        self,
        total_scanned: int,
        deals_found: int,
        top_deal: ArbitrageResult | None = None,
    ) -> bool:
        """Send a summary message after a scan."""
        if not self.config.enabled or not self._bot:
            return False

        lines = [
            "📊 *Scan Complete*",
            "",
            f"🔍 Scanned: {total_scanned} items",
            f"💎 Deals found: {deals_found}",
        ]

        if top_deal:
            lines.extend([
                "",
                f"🏆 *Best Deal:*",
                f"{top_deal.sellpy_item.brand} - €{top_deal.sellpy_item.price:.0f}",
                f"Potential profit: +€{top_deal.potential_profit:.0f}" if top_deal.potential_profit else "",
            ])

        try:
            await self._bot.send_message(
                chat_id=self.config.chat_id,
                text="\n".join(lines),
                parse_mode=ParseMode.MARKDOWN,
            )
            return True
        except Exception as e:
            log.error("summary_notification_failed", error=str(e))
            return False

    def clear_seen(self) -> None:
        """Clear the deduplication cache."""
        self._seen_items.clear()
