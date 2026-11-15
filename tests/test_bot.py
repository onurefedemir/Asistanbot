from pathlib import Path

import pytest

from asistanbot.analysis import PriceModel, rank_deals
from asistanbot.commands import ParseError, parse_amount, parse_takip
from asistanbot.db import DB
from asistanbot.models import Listing, Search, slugify
from asistanbot.scrapers import ArabamScraper, SahibindenScraper
from asistanbot.scrapers.base import parse_price, split_year_km
from asistanbot.tracker import check_search

FX = Path(__file__).parent / "fixtures"


# ------------------------------------------------------------- parsing helpers
def test_slugify():
    assert slugify("Renault Clio") == "renault-clio"
    assert slugify("Şkoda Süperb  1.6") == "skoda-superb-1-6"


def test_parse_price():
    assert parse_price("845.000 TL") == 845000
    assert parse_price("1.250.000 ₺") == 1250000
    assert parse_price("Fiyat: 999.999TL") == 999999


def test_split_year_km():
    assert split_year_km(["2020", "78.500", "Beyaz"]) == (2020, 78500)
    assert split_year_km(["185.000 km", "2016"]) == (2016, 185000)


# ------------------------------------------------------------- commands
def test_parse_amount():
    assert parse_amount("900bin") == 900_000
    assert parse_amount("1.2m") == 1_200_000
    assert parse_amount("1,5milyon") == 1_500_000
    assert parse_amount("850.000") == 850_000


def test_parse_takip():
    s = parse_takip("renault clio fiyat=400bin-900bin yil=2018- km=150000".split())
    assert (s.query, s.min_price, s.max_price, s.min_year, s.max_year, s.max_km) == (
        "renault clio", 400_000, 900_000, 2018, None, 150_000,
    )
    s = parse_takip("fiat egea fiyat=700bin yil=2019".split())
    assert (s.min_price, s.max_price, s.min_year) == (None, 700_000, 2019)
    with pytest.raises(ParseError):
        parse_takip(["fiyat=1m"])


# ------------------------------------------------------------- scrapers
def test_sahibinden_parse_and_url():
    sc = SahibindenScraper()
    items = sc.parse((FX / "sahibinden.html").read_text())
    assert len(items) == 2  # reklam satırı atlanır
    a = items[0]
    assert (a.external_id, a.price, a.year, a.km) == ("1180000001", 845000, 2020, 78500)
    assert a.url.startswith("https://www.sahibinden.com/ilan/")
    assert "İstanbul" in a.location
    url = sc.build_url(Search("Renault Clio", max_price=900000, min_year=2018, max_km=150000), 2)
    assert url.startswith("https://www.sahibinden.com/renault-clio?")
    assert "price_max=900000" in url and "a5_min=2018" in url and "a4_max=150000" in url and "pagingOffset=50" in url


def test_arabam_parse_rows():
    items = ArabamScraper().parse((FX / "arabam.html").read_text())
    assert [(i.external_id, i.price, i.year, i.km) for i in items] == [
        ("31234567", 915000, 2021, 45000),
        ("31234568", 540000, 2016, 185000),
    ]
    assert items[0].title.startswith("Galeriden Renault Clio")


def test_arabam_generic_fallback():
    items = ArabamScraper().parse((FX / "arabam_cards.html").read_text())
    assert {(i.external_id, i.price, i.year, i.km) for i in items} == {
        ("39990001", 1050000, 2022, 30000),
        ("39990002", 720000, 2019, 99000),
    }


def test_search_matches_filters():
    s = Search("renault clio", max_price=900000, min_year=2018)
    ok = Listing("x", "1", "Renault Clio Touch", 800000, "u", 2019, 50000)
    assert s.matches(ok)
    assert not s.matches(Listing("x", "2", "Renault Clio", 950000, "u", 2019))
    assert not s.matches(Listing("x", "3", "Renault Clio", 800000, "u", 2015))
    assert not s.matches(Listing("x", "4", "Renault Megane", 800000, "u", 2019))


# ------------------------------------------------------------- analysis
def _rows(data):
    return [{"price": p, "year": y, "km": k, "id": i} for i, (p, y, k) in enumerate(data)]


def test_price_model_finds_underpriced():
    data = [(500_000 + (y - 2015) * 60_000 - k // 10, y, k) for y in range(2015, 2023) for k in (40_000, 90_000)]
    data.append((600_000, 2021, 50_000))  # beklenen ~855k → büyük fırsat
    rows = _rows(data)
    m = PriceModel(rows)
    assert m.coef is not None
    best, ratio = rank_deals(rows, 1)[0]
    assert best["price"] == 600_000 and ratio < 0.8


def test_price_model_median_fallback():
    m = PriceModel(_rows([(100, None, None), (200, None, None), (300, None, None)]))
    assert m.coef is None and m.expected(None, None) == 200


# ------------------------------------------------------------- tracker end-to-end
class FakeScraper:
    name = "fake"

    def __init__(self):
        self.batches = []

    def scrape(self, search, fetcher):
        return self.batches.pop(0)


def L(i, price, year=2020, km=50000):
    return Listing("fake", str(i), "Renault Clio", price, f"https://x/{i}", year, km)


def test_tracker_new_drop_removed(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    s = Search("renault clio", chat_id=1)
    db.add_search(s)
    sc = FakeScraper()
    base = [L(i, 800_000 + i * 10_000, 2015 + i % 8, 40_000 + i * 5000) for i in range(10)]
    sc.batches = [base, base[:9] + [L(99, 400_000, 2021, 30_000)], [L(1, 700_000, 2016, 45_000)] + base[2:9]]

    r1 = check_search(db, s, fetcher=object(), scrapers=[sc])
    assert r1.first_run and len(r1.new) == 10 and not r1.has_news

    r2 = check_search(db, s, fetcher=object(), scrapers=[sc])
    assert not r2.first_run
    assert [r["external_id"] for r in r2.new] == ["99"]
    assert r2.deals and r2.deals[0][0]["external_id"] == "99"
    assert r2.removed == 1  # ilan 9 kalktı

    r3 = check_search(db, s, fetcher=object(), scrapers=[sc])
    assert [(r["external_id"], r["prev_price"], r["price"]) for r in r3.drops] == [("1", 810_000, 700_000)]
    lid = r3.drops[0]["id"]
    assert [h["price"] for h in db.history(lid)] == [810_000, 700_000]
    assert db.get_listing(lid)["min_price"] == 700_000


def test_tracker_error_isolated(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    s = Search("renault clio", chat_id=1)
    db.add_search(s)

    class Boom:
        name = "boom"

        def scrape(self, *a):
            raise RuntimeError("site değişti")

    ok = FakeScraper()
    ok.batches = [[L(1, 500_000)]]
    rep = check_search(db, s, fetcher=object(), scrapers=[Boom(), ok])
    assert rep.per_source == {"fake": 1} and "boom" in rep.errors[0]


def test_formatting_report(tmp_path):
    from asistanbot import formatting as fmt

    db = DB(str(tmp_path / "t.db"))
    s = Search("renault clio", chat_id=1)
    db.add_search(s)
    sc = FakeScraper()
    sc.batches = [[L(1, 500_000)], [L(1, 450_000)]]
    check_search(db, s, fetcher=object(), scrapers=[sc])
    text = fmt.report(check_search(db, s, fetcher=object(), scrapers=[sc]))
    assert "Fiyatı düşenler" in text and "450.000" in text and "<s>500.000</s>" in text
    assert "En ucuzlar" in fmt.cheapest(s, db.active_listings(s.id))
