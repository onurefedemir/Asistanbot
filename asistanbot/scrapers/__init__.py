from .arabam import ArabamScraper
from .base import BlockedError, Scraper, make_fetcher
from .sahibinden import SahibindenScraper

SCRAPERS: list[Scraper] = [SahibindenScraper(), ArabamScraper()]

__all__ = ["SCRAPERS", "BlockedError", "Scraper", "make_fetcher", "ArabamScraper", "SahibindenScraper"]
