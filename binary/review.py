"""Claude'un günlük değerlendirmesi (TradingAgents fikri, ama dakika dakika değil günde bir kez).

Günün raporlarını (strateji araştırması, ML testi, varsa sanal işlem sonuçları) ve bir önceki
değerlendirmeyi okur, Türkçe kısa bir değerlendirme yazar: neyin işe yaradığı, neyin yaramadığı,
denenebilecek yeni fikirler. İşlem kararı vermez.

Kullanım:
    python -m binary.review --out review.md research_delay1.txt research_delay0.txt ml_report.txt
    python -m binary.review --paper-db paper.db ...   # sanal işlem sonuçlarını da ekle

ANTHROPIC_API_KEY gerekir. Anahtar yoksa hiçbir şey yapmadan çıkar.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import anthropic

MODEL = "claude-opus-5-5"

SYSTEM = """Sen bir nicel araştırma denetçisisin. Kullanıcı Pocket Option'da OTC olmayan döviz çiftlerinde ikili opsiyon (1-5 dk vade) stratejisi arıyor; şimdilik yalnızca veri toplanıyor, sanal işlem yapılıyor ve hiçbir gerçek işlem açılmıyor.

Sana günün otomatik raporları verilecek. Türkçe, kısa (en fazla ~25 satır) bir değerlendirme yaz:
1. Bugünkü durum: başa baş oranını (genelde %54,05) geçen bir şey var mı? Sayılarla söyle.
2. Gecikmesiz (delay 0) ve gecikmeli (delay 1) sonuçlar arasındaki farkı yorumla; gecikmesiz kazanç, verideki kotasyon gürültüsünden kaynaklanabilir ve gerçekte alınamayabilir.
3. Bir önceki değerlendirmeye göre ne değişti?
4. Denenebilecek en fazla 3 somut fikir (yeni strateji, özellik, filtre ya da test). Her biri için neden işe yarayabileceğini bir cümleyle yaz.
5. forward_validation.txt varsa: ön kayıtlı adayların kayıt sonrası durumunu (BEKLİYOR / GEÇTİ / KALDI) mutlaka yaz; yalnızca bu dosyadaki "GEÇTİ" gerçek bir kanıttır.
6. Tek cümlelik karar: "Gerçek paraya geçmek için henüz kanıt yok" ya da hangi koşulların sağlandığı.

Kurallar: Sayı uydurma; yalnızca raporlardaki sayıları kullan. Az işlemli (300'den az) sonuçları kanıt sayma. Çok sayıda kombinasyon denendiğinde bazılarının şans eseri iyi görüneceğini unutma. Kazanç vaadinde bulunma."""


def build_prompt(files: list[str], paper_text: str | None, previous: str | None) -> str:
    parts = [f"Bugün: {time.strftime('%Y-%m-%d')}"]
    for f in files:
        p = Path(f)
        if p.exists():
            parts.append(f"<rapor dosya=\"{p.name}\">\n{p.read_text(encoding='utf-8')[-12000:]}\n</rapor>")
    if paper_text:
        parts.append(f"<rapor dosya=\"sanal_islemler\">\n{paper_text}\n</rapor>")
    if previous:
        parts.append(f"<onceki_degerlendirme>\n{previous[-6000:]}\n</onceki_degerlendirme>")
    return "\n\n".join(parts)


def review(prompt: str, client: anthropic.Anthropic | None = None) -> str:
    client = client or anthropic.Anthropic()
    resp = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": "medium"},
        # Güvenlik sınıflandırıcısı reddederse istek önerilen yedek modelde tekrar çalışır
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if resp.stop_reason == "refusal":
        return "(Değerlendirme bugün üretilemedi: model isteği reddetti.)"
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--out", default="review.md")
    ap.add_argument("--paper-db")
    a = ap.parse_args()
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        print("ANTHROPIC_API_KEY yok; değerlendirme atlandı.")
        return 0
    paper_text = None
    if a.paper_db and Path(a.paper_db).exists():
        from . import paper

        paper_text = paper.report(paper._db(a.paper_db))
    out = Path(a.out)
    previous = out.read_text(encoding="utf-8") if out.exists() else None
    try:
        text = review(build_prompt(a.files, paper_text, previous))
    except anthropic.APIError as e:
        print(f"Değerlendirme alınamadı: {type(e).__name__}: {e}")
        return 0  # günlük veri toplama bu yüzden başarısız sayılmasın
    out.write_text(f"# Günlük değerlendirme — {time.strftime('%Y-%m-%d')}\n\n{text}\n", encoding="utf-8")
    print(out.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
