from __future__ import annotations

import logging
import random
import re
import time
from abc import ABC, abstractmethod

from bs4 import BeautifulSoup, Tag

from ..config import config
from ..models import Listing, Search

log = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0",
]


class BlockedError(RuntimeError):
    """Site bot koruması / captcha döndürdü."""


# ---------------------------------------------------------------- fetchers


class HttpxFetcher:
    def __init__(self) -> None:
        import httpx

        self.client = httpx.Client(
            timeout=25,
            follow_redirects=True,
            headers={
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.6",
            },
        )

    def get(self, url: str) -> str:
        r = self.client.get(url)
        if r.status_code in (403, 429):
            raise BlockedError(f"{url} -> HTTP {r.status_code}")
        r.raise_for_status()
        return r.text

    def close(self) -> None:
        self.client.close()


class PlaywrightFetcher:
    """Gerçek Chromium ile sayfa açar; JS/bot korumalı sayfalarda daha başarılıdır."""

    def __init__(self) -> None:
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        self._ctx = self._browser.new_context(locale="tr-TR", user_agent=USER_AGENTS[0])

    def get(self, url: str) -> str:
        page = self._ctx.new_page()
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(1500)
            if resp and resp.status in (403, 429):
                raise BlockedError(f"{url} -> HTTP {resp.status}")
            return page.content()
        finally:
            page.close()

    def close(self) -> None:
        self._ctx.close()
        self._browser.close()
        self._pw.stop()


def make_fetcher():
    return PlaywrightFetcher() if config.fetcher == "playwright" else HttpxFetcher()


# ---------------------------------------------------------------- parse helpers

_NUM = re.compile(r"\d{1,3}(?:[.\s]\d{3})+|\d+")
_PRICE = re.compile(r"(\d{1,3}(?:[.\s]\d{3})+|\d{4,})\s*(?:TL|₺)", re.I)
_YEAR = re.compile(r"^(19[5-9]\d|20[0-4]\d)$")


def parse_int(text: str | None) -> int | None:
    if not text:
        return None
    m = _NUM.search(text)
    return int(re.sub(r"\D", "", m.group())) if m else None


def parse_price(text: str | None) -> int | None:
    if not text:
        return None
    m = _PRICE.search(text)
    if m:
        return int(re.sub(r"\D", "", m.group(1)))
    return parse_int(text)


def split_year_km(cells: list[str]) -> tuple[int | None, int | None]:
    """Özellik hücrelerinden yılı ve km'yi tahmin eder (sütun sırası değişse de çalışır)."""
    year = km = None
    for c in cells:
        c = c.strip()
        if year is None and _YEAR.match(c):
            year = int(c)
            continue
        n = parse_int(c)
        if km is None and n is not None and re.fullmatch(r"[\d.\s]+(km)?", c, re.I):
            km = n
    return year, km


def text(el: Tag | None) -> str:
    return el.get_text(" ", strip=True) if el else ""


def soup_of(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


# ---------------------------------------------------------------- scraper base


class Scraper(ABC):
    name: str = ""
    base_url: str = ""

    @abstractmethod
    def build_url(self, search: Search, page: int) -> str: ...

    @abstractmethod
    def parse(self, html: str) -> list[Listing]: ...

    def is_blocked(self, html: str) -> bool:
        low = html.lower()
        return any(s in low for s in (
            "captcha", "olağandışı", "olağan dışı", "olagan disi", "cf-challenge",
            "just a moment", "enable javascript and cookies", "are you a robot",
        ))

    def scrape(self, search: Search, fetcher, max_pages: int | None = None) -> list[Listing]:
        max_pages = max_pages or config.max_pages
        out: dict[str, Listing] = {}
        for page in range(1, max_pages + 1):
            url = self.build_url(search, page)
            log.info("[%s] %s", self.name, url)
            html = fetcher.get(url)
            items = self.parse(html)
            if not items:
                if self.is_blocked(html):
                    raise BlockedError(f"{self.name}: bot koruması / captcha")
                break
            new = [i for i in items if i.key not in out]
            for i in new:
                out[i.key] = i
            if not new:  # sayfalama bitti, aynı sonuçlar dönüyor
                break
            if page < max_pages:
                time.sleep(config.request_delay + random.uniform(0, 2))
        return [l for l in out.values() if search.matches(l)]
