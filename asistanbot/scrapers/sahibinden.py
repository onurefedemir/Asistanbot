from __future__ import annotations

import re
from urllib.parse import urlencode, urljoin

from ..models import Listing, Search
from .base import Scraper, parse_price, soup_of, split_year_km, text

PAGE_SIZE = 50


class SahibindenScraper(Scraper):
    name = "sahibinden"
    base_url = "https://www.sahibinden.com"

    def build_url(self, s: Search, page: int) -> str:
        params: dict[str, object] = {"pagingSize": PAGE_SIZE, "sorting": "price_asc"}
        if page > 1:
            params["pagingOffset"] = (page - 1) * PAGE_SIZE
        if s.min_price:
            params["price_min"] = s.min_price
        if s.max_price:
            params["price_max"] = s.max_price
        if s.min_year:
            params["a5_min"] = s.min_year  # a5 = Yıl
        if s.max_year:
            params["a5_max"] = s.max_year
        if s.max_km:
            params["a4_max"] = s.max_km  # a4 = KM
        return f"{self.base_url}/{s.slug}?{urlencode(params)}"

    def parse(self, html: str) -> list[Listing]:
        soup = soup_of(html)
        out: list[Listing] = []
        for row in soup.select("tr.searchResultsItem"):
            ext_id = row.get("data-id")
            a = row.select_one("a.classifiedTitle") or row.select_one("td.searchResultsTitleValue a[href]")
            if not ext_id or not a:  # reklam satırları
                continue
            price = parse_price(text(row.select_one("td.searchResultsPriceValue")))
            if not price:
                continue
            attrs = [text(td) for td in row.select("td.searchResultsAttributeValue")]
            year, km = split_year_km(attrs)
            loc = row.select_one("td.searchResultsLocationValue")
            location = re.sub(r"\s+", " ", loc.get_text(" ", strip=True)) if loc else None
            out.append(
                Listing(
                    source=self.name,
                    external_id=str(ext_id),
                    title=a.get("title") or text(a),
                    price=price,
                    url=urljoin(self.base_url, a["href"]),
                    year=year,
                    km=km,
                    location=location,
                    extra={"date": text(row.select_one("td.searchResultsDateValue"))},
                )
            )
        return out
