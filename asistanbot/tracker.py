from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .analysis import PriceModel
from .config import config
from .db import DB
from .models import Search
from .scrapers import SCRAPERS, BlockedError, Scraper, make_fetcher

log = logging.getLogger(__name__)


@dataclass
class Report:
    search: Search
    first_run: bool = False
    total: int = 0
    per_source: dict[str, int] = field(default_factory=dict)
    new: list = field(default_factory=list)  # yeni ilan satırları
    deals: list = field(default_factory=list)  # (satır, oran) – piyasanın altında yeni ilanlar
    drops: list = field(default_factory=list)  # fiyatı düşen satırlar (prev_price içerir)
    removed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def has_news(self) -> bool:
        return bool(self.deals or self.drops or (self.new and not self.first_run))


def check_search(db: DB, search: Search, fetcher=None, scrapers: list[Scraper] | None = None) -> Report:
    own_fetcher = fetcher is None
    fetcher = fetcher or make_fetcher()
    rep = Report(search=search, first_run=db.is_first_run(search.id))
    try:
        for sc in scrapers or SCRAPERS:
            try:
                listings = sc.scrape(search, fetcher)
            except BlockedError as e:
                rep.errors.append(f"{sc.name}: engellendi ({e}). FETCHER=playwright deneyin.")
                continue
            except Exception as e:  # noqa: BLE001 – bir site çökse de diğeri çalışsın
                log.exception("%s hata", sc.name)
                rep.errors.append(f"{sc.name}: {type(e).__name__}: {e}")
                continue

            rep.per_source[sc.name] = len(listings)
            for l in listings:
                status, row = db.upsert_listing(search.id, l)
                if status == "new":
                    rep.new.append(row)
                elif status == "drop" and row["prev_price"] and (row["prev_price"] - row["price"]) / row["prev_price"] >= config.min_drop_ratio:
                    rep.drops.append(row)
            # Sadece başarılı ve boş olmayan taramada pasifleştir (geçici hata = 'satıldı' sanılmasın)
            if listings:
                rep.removed += db.deactivate_missing(search.id, sc.name, {l.external_id for l in listings})
    finally:
        if own_fetcher:
            fetcher.close()

    active = db.active_listings(search.id)
    rep.total = len(active)
    if active:
        model = PriceModel(active)
        for row in rep.new:
            r = model.ratio(row)
            if r is not None and r <= config.deal_ratio:
                rep.deals.append((row, r))
        rep.deals.sort(key=lambda x: x[1])
    if not rep.errors or rep.per_source:
        db.mark_run(search.id)
    return rep
