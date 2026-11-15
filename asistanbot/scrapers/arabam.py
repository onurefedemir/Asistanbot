from __future__ import annotations

import json
import re
from urllib.parse import urlencode, urljoin

from bs4 import Tag

from ..models import Listing, Search
from .base import Scraper, parse_int, parse_price, soup_of, split_year_km, text

PAGE_SIZE = 50
_ID = re.compile(r"/ilan/.*?/(\d{5,})")


class ArabamScraper(Scraper):
    name = "arabam"
    base_url = "https://www.arabam.com"

    def build_url(self, s: Search, page: int) -> str:
        params: dict[str, object] = {"take": PAGE_SIZE, "sort": "price.asc"}
        if page > 1:
            params["page"] = page
        if s.min_price:
            params["minPrice"] = s.min_price
        if s.max_price:
            params["maxPrice"] = s.max_price
        if s.min_year:
            params["minYear"] = s.min_year
        if s.max_year:
            params["maxYear"] = s.max_year
        if s.max_km:
            params["maxkm"] = s.max_km
        return f"{self.base_url}/ikinci-el/otomobil/{s.slug}?{urlencode(params)}"

    def parse(self, html: str) -> list[Listing]:
        soup = soup_of(html)
        out = self._parse_rows(soup.select("tr.listing-list-item"))
        if not out:
            out = self._parse_jsonld(soup)
        if not out:
            out = self._parse_generic(soup)
        return out

    # --- 1) Liste tablosu
    def _parse_rows(self, rows: list[Tag]) -> list[Listing]:
        out = []
        for row in rows:
            a = row.select_one("a.link-overlay[href]") or row.select_one("a[href*='/ilan/']")
            if not a:
                continue
            m = _ID.search(a["href"])
            price = parse_price(text(row.select_one(".listing-price")) or text(row))
            if not m or not price:
                continue
            title = (
                text(row.select_one(".listing-title-lines"))
                or text(row.select_one("h3"))
                or a.get("title")
                or text(a)
            )
            cells = [text(td) for td in row.select("td.listing-text")]
            year, km = split_year_km(cells)
            loc = row.select_one(".listing-text .fade-out-content-wrapper") or row.select_one("[class*=location]")
            out.append(
                Listing(self.name, m.group(1), title, price, urljoin(self.base_url, a["href"]), year, km, text(loc) or None)
            )
        return out

    # --- 2) Sayfadaki JSON-LD (schema.org Car / Offer) verisi
    def _parse_jsonld(self, soup) -> list[Listing]:
        out = []
        for tag in soup.select("script[type='application/ld+json']"):
            try:
                data = json.loads(tag.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            items = data if isinstance(data, list) else data.get("itemListElement") or [data]
            for it in items:
                it = it.get("item", it) if isinstance(it, dict) else {}
                url = it.get("url") or ""
                m = _ID.search(url)
                offer = it.get("offers") or {}
                price = parse_int(str(offer.get("price", "")))
                if not m or not price:
                    continue
                mileage = it.get("mileageFromOdometer") or {}
                out.append(
                    Listing(
                        self.name,
                        m.group(1),
                        it.get("name", ""),
                        price,
                        urljoin(self.base_url, url),
                        parse_int(str(it.get("modelDate") or it.get("productionDate") or "")),
                        parse_int(str(mileage.get("value", ""))) if isinstance(mileage, dict) else None,
                    )
                )
        return out

    # --- 3) Son çare: /ilan/ linki + yakınındaki fiyat
    def _parse_generic(self, soup) -> list[Listing]:
        seen: dict[str, Listing] = {}
        for a in soup.select("a[href*='/ilan/']"):
            m = _ID.search(a["href"])
            if not m or m.group(1) in seen:
                continue
            box = a
            for _ in range(6):
                box = box.parent
                if box is None or parse_price(text(box)) and "TL" in text(box):
                    break
            if box is None:
                continue
            price = parse_price(text(box))
            if not price:
                continue
            cells = [t for t in box.stripped_strings]
            year, km = split_year_km(cells)
            seen[m.group(1)] = Listing(
                self.name, m.group(1), a.get("title") or text(a), price, urljoin(self.base_url, a["href"]), year, km
            )
        return list(seen.values())
