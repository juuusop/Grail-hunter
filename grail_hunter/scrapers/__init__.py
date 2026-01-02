"""Scraper modules for various thrift platforms."""

from grail_hunter.scrapers.base import BaseScraper, ScraperConfig, ScraperError
from grail_hunter.scrapers.sellpy import SellpyScraper, SellpyItem
from grail_hunter.scrapers.grailed import GrailedScraper, GrailedListing
from grail_hunter.scrapers.ebay import EbayScraper, EbayListing
from grail_hunter.scrapers.vinted import VintedScraper, VintedListing

__all__ = [
    # Base
    "BaseScraper",
    "ScraperConfig",
    "ScraperError",
    # Sellpy
    "SellpyScraper",
    "SellpyItem",
    # Grailed
    "GrailedScraper",
    "GrailedListing",
    # eBay
    "EbayScraper",
    "EbayListing",
    # Vinted
    "VintedScraper",
    "VintedListing",
]
