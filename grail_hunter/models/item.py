"""SQLAlchemy models for storing scraped items."""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Float, Integer, DateTime, Text, Boolean, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class Item(Base):
    """Scraped item from Sellpy or other platforms."""

    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    object_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)

    # Basic info
    title: Mapped[str] = mapped_column(String(500))
    brand: Mapped[Optional[str]] = mapped_column(String(200), index=True)
    price: Mapped[float] = mapped_column(Float)
    original_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    discount_pct: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Details
    condition: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    size: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # URLs
    image_url: Mapped[str] = mapped_column(String(500))
    item_url: Mapped[str] = mapped_column(String(500))

    # Classification
    brand_tier: Mapped[Optional[str]] = mapped_column(String(20), index=True, nullable=True)
    brand_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    item_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    detected_materials: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    filter_status: Mapped[str] = mapped_column(String(20), default="valid", index=True)

    # Tracking
    source: Mapped[str] = mapped_column(String(50), default="sellpy")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    sale_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_sold: Mapped[bool] = mapped_column(Boolean, default=False)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        Index("ix_items_tier_score", "brand_tier", "item_score"),
        Index("ix_items_brand_status", "brand", "filter_status"),
    )

    def __repr__(self) -> str:
        return f"<Item {self.object_id}: {self.brand} - {self.title[:50]}>"


class ScrapeRun(Base):
    """Record of a scraping run for tracking and debugging."""

    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Stats
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    new_items: Mapped[int] = mapped_column(Integer, default=0)
    grails_found: Mapped[int] = mapped_column(Integer, default=0)
    trash_filtered: Mapped[int] = mapped_column(Integer, default=0)

    # Status
    status: Mapped[str] = mapped_column(String(20), default="running")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<ScrapeRun {self.id}: {self.status} - {self.new_items} new>"
