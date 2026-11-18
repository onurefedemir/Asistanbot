# İkili Opsiyon Strateji Araştırması — İlk Sonuçlar

Tarih: 2026-11-18. Kaynak: Yahoo Finance 1 dakikalık veri, OTC olmayan 10 döviz çifti.

## 1. Gecikmesiz giriş (sinyal mumunun kapanışından)

```
Eğitim: 2026-10-20 06:18 → 2026-11-10 00:00
Test:   2026-11-10 00:00 → 2026-11-18 06:19
Ödeme %85 → başa baş kazanma oranı %54.05
Giriş gecikmesi: 0 mum
Denenen kombinasyon: 1056

strateji            parametre                    vade      seans |          eğitim |            test       p  geçti
zscore_reversion    n=10,z=2.5                     2d        all | %63.92 n=898    | % 66.1 n=410        0.0  EVET
zscore_reversion    n=10,z=2.5                     5d        all | %63.51 n=888    | %63.93 n=402        0.0  EVET
zscore_reversion    n=10,z=2.5                     3d        all | %63.18 n=888    | % 64.6 n=404        0.0  EVET
zscore_reversion    n=10,z=2.5                     1d        all | %62.57 n=895    | %67.85 n=395        0.0  EVET
zscore_reversion    n=20,z=3.0                     5d        all | % 60.7 n=743    | %59.81 n=316     0.0229  hayır
roc_reversion       n=1,z=3.0                      1d        all | %59.91 n=1938   | %59.53 n=850     0.0008  EVET
rsi_reversion       n=5,lo=10,hi=90                2d ny_overlap | %59.65 n=518    | %59.89 n=177     0.0692  hayır
roc_reversion       n=1,z=3.0                      1d       asya | %59.01 n=444    | %58.48 n=224     0.1033  hayır
roc_reversion       n=1,z=2.0                      1d        all | %58.92 n=9329   | %61.46 n=3931       0.0  EVET
rsi_reversion       n=5,lo=10,hi=90                1d ny_overlap | %58.89 n=754    | %56.88 n=269     0.1927  hayır
zscore_reversion    n=20,z=3.0                     1d        all | %58.65 n=873    | %60.05 n=378      0.011  hayır
zscore_reversion    n=20,z=3.0                     3d        all | %58.57 n=770    | %61.52 n=330     0.0039  hayır
zscore_reversion    n=50,z=3.0                     5d        all | %58.53 n=1143   | %65.87 n=501        0.0  EVET
zscore_reversion    n=20,z=3.0                     2d        all | %58.43 n=789    | %63.42 n=339     0.0003  EVET
roc_reversion       n=1,z=1.5                      2d       asya | %58.05 n=5356   | %59.01 n=2408       0.0  EVET

Testi geçen strateji: 9 / 15 (eşik p < 0.0033)
```

## 2. Gerçekçi giriş (1 dakika gecikmeli)

```
Eğitim: 2026-10-20 06:18 → 2026-11-10 00:00
Test:   2026-11-10 00:00 → 2026-11-18 06:19
Ödeme %85 → başa baş kazanma oranı %54.05
Giriş gecikmesi: 1 mum
Denenen kombinasyon: 1056

strateji            parametre                    vade      seans |          eğitim |            test       p  geçti
streak_momentum     m=6                            5d       asya | %55.15 n=437    | %53.72 n=188     0.5652  hayır
roc_momentum        n=1,z=3.0                      1d       asya | % 55.1 n=412    | %43.56 n=202     0.9989  hayır
rsi_reversion       n=5,lo=10,hi=90                3d     londra | %55.06 n=474    | %51.48 n=169      0.773  hayır
zscore_reversion    n=20,z=2.5                     3d     londra | %54.93 n=670    | %54.44 n=259     0.4751  hayır
zscore_reversion    n=20,z=3.0                     1d        all | %54.91 n=754    | %52.02 n=321     0.7839  hayır
rsi_reversion       n=5,lo=10,hi=90                2d     londra | %54.85 n=505    | %48.07 n=181     0.9546  hayır
rsi_reversion       n=5,lo=10,hi=90                1d ny_overlap | %54.24 n=507    | %57.71 n=175     0.1852  hayır
roc_reversion       n=15,z=2.0                     3d ny_overlap | %54.23 n=662    | %51.62 n=308     0.8194  hayır
rsi_reversion       n=5,lo=10,hi=90                1d     londra | %53.95 n=582    | %52.34 n=214     0.7166  hayır
roc_reversion       n=15,z=2.0                     5d ny_overlap | %53.85 n=546    | %47.83 n=253     0.9799  hayır
zscore_reversion    n=50,z=2.5                     1d     londra | %53.72 n=1009   | %52.14 n=397     0.7925  hayır
rsi_reversion       n=5,lo=10,hi=90                2d ny_overlap | %53.54 n=452    | %50.65 n=154     0.8235  hayır
streak_momentum     m=6                            3d ny_overlap | %53.44 n=378    | %47.01 n=134     0.9574  hayır
streak_momentum     m=7                            5d        all | %53.42 n=657    | %48.59 n=249     0.9635  hayır
zscore_reversion    n=20,z=3.0                     5d        all | %53.34 n=748    | %50.47 n=319       0.91  hayır

Testi geçen strateji: 0 / 15 (eşik p < 0.0033)
```

## 3. Neden bu kadar farklı?

Gecikmesiz girişte bazı stratejiler %60–68 kazanıyor gibi görünüyor, ama:

- Dakikalık getirilerde güçlü **negatif otokorelasyon** var (USDCAD -0,31, GBPJPY -0,16, EURUSD -0,13). Gerçek döviz piyasası bu kadar düzenli tersine dönmez; bu, veri akışındaki fiyat sıçramalarının (kotasyon gürültüsü) izidir.
- Giriş yalnızca **1 dakika** geciktirildiğinde aynı stratejilerin kazanma oranı her çiftte **%49–52**'ye düşüyor.
- Gecikmeli testte 1056 kombinasyonun **hiçbiri** test döneminde başa baş oranını (%54,05) anlamlı şekilde geçmedi.

**Sonuç:** Bu veride ikili opsiyonda kullanılabilir bir avantaj bulunmadı. Görünen kazanç, ancak sinyalden saniyeler içinde ve gürültünün aynısını taşıyan bir fiyat akışında işlem açılırsa var olabilir. Pocket Option'ın akışında böyle bir durum olup olmadığı bilinmiyor; bunu yalnızca demo hesapla `python -m binary.live` ölçebilir.

## 4. Sınırlar

- Yalnızca ~1 aylık veri (Yahoo 1 dakikalık veriyi 30 günle sınırlıyor). `python -m binary.data` her gün çalıştırılırsa veri birikir; araştırma birkaç ay sonra tekrarlanmalı.
- EURUSD, GBPUSD ve AUDUSD için Yahoo yalnızca kapanış fiyatı veriyor.
- Pocket Option'ın fiyat akışı Yahoo'dan farklıdır.

---

# 2. ve 3. tur: elenenlerin yerine denenmemiş aileler

**Hedef:** günde 200 $. %85 ödemede işlem başı beklenen kâr = stake × (kazanma × 1,85 − 1). Örneğin günde 50 işlemle 200 $ için en az **%58** kazanma ve ~55 $ stake gerekir. %54'ün altında her işlem ortalamada para kaybettirir.

## 1. tur — elendi
zscore, RSI, ardışık mum, ROC momentum/geri dönüş, EMA geri çekilme: gerçekçi girişte 1056 kombinasyonun hiçbiri geçmedi (%49–52). Canlı sanal motordan çıkarıldı.

## 2. tur — denenmemiş 7 aile (236 kombinasyon)

```
lead_lag      k=2,z=2.5                                1d | % 52.9 n=1554   | %52.97 n=623     0.7202  hayır
lead_lag      k=2,z=2.0                                2d | %52.18 n=3494   | %51.78 n=1406     0.959  hayır
triangle      n=240,z=2.5                              3d | %53.94 n=1370   | %53.12 n=544     0.6836  hayır
triangle      n=240,z=2.5                              1d | %53.03 n=1567   | %52.93 n=631     0.7276  hayır
usd_basket    k=5,z=2.0                                3d | %53.92 n=855    | %51.55 n=322     0.8306  hayır
usd_basket    k=15,z=2.0                               2d | %52.95 n=542    | %53.53 n=170     0.5848  hayır
breakout      n=120,mode=rev                           3d | %51.32 n=6699   | %51.82 n=2667    0.9903  hayır
breakout      n=120,mode=rev                           2d | %51.19 n=7626   | %51.23 n=3020    0.9991  hayır
mtf_pullback  slow=12,rsi_n=3                          2d | %51.47 n=12692  | %51.57 n=5521    0.9999  hayır
mtf_pullback  slow=6,rsi_n=3                           3d | %51.41 n=10814  | %51.92 n=4663    0.9984  hayır
vol_filtered  regime=high,z=2.5                        3d | %51.89 n=607    | % 54.2 n=286     0.5045  hayır
vol_filtered  regime=high,z=2.5                        5d | %51.85 n=594    | %54.74 n=285     0.4318  hayır
seasonality   min_obs=15,bias=0.2                      2d | %75.74 n=6524   | %50.81 n=2535    0.9995  hayır
seasonality   min_obs=10,bias=0.2                      1d | %75.73 n=20563  | %49.56 n=8766       1.0  hayır

Aile bazında test döneminin en iyisi (en az 100 işlem):
  lead_lag         64 kombinasyon, en iyi test %56.17 (n=235)
  triangle         36 kombinasyon, en iyi test %55.15 (n=544)
  usd_basket       48 kombinasyon, en iyi test %57.58 (n=422)
  breakout         32 kombinasyon, en iyi test %52.5 (n=3556)
  mtf_pullback     24 kombinasyon, en iyi test %54.26 (n=1410)
  vol_filtered     16 kombinasyon, en iyi test %54.74 (n=285)
  seasonality      16 kombinasyon, en iyi test %51.17 (n=7846)

Testi geçen: 0 / 14 (eşik p < 0.0036)
```

- **Mevsimsellik (saat × dakika):** eğitimde %75, testte %50. Veri madenciliğinin klasik tuzağı; elendi.
- **Kırılım, çoklu zaman dilimi:** %51–52; elendi.
- **Çiftler arası aileler (lead_lag, triangle, usd_basket) ve yüksek oynaklık filtresi:** %52–55. Tek çift stratejilerinden belirgin şekilde iyi ama anlamlı değil. Canlı sanal motora bunlar alındı; seçici canlıda ölçecek. ("En iyi test" sütunu, test dönemine bakılarak seçildiği için kanıt değildir.)

## 3. tur — çiftler arası özellikli ML (Qlib alfa faktörü fikri)

```

 expiry  threshold  trades  win_rate   edge  ev_per_trade  p_value
      1       0.53     630     53.65  -0.40         -0.75   0.5960
      1       0.55      69     46.38  -7.68        -14.20   0.9193
      1       0.57       5     40.00 -14.05        -26.00   0.8598
      1       0.60       0       NaN    NaN           NaN      NaN
      2       0.53    2134     52.67  -1.38         -2.56   0.9038
      2       0.55     395     54.18   0.12          0.23   0.5005
      2       0.57      87     56.32   2.27          4.20   0.3757
      2       0.60       3    100.00  45.95         85.00   0.1544
      3       0.53    3099     50.44  -3.62         -6.69   1.0000
      3       0.55     719     54.38   0.33          0.61   0.4449
      3       0.57     222     50.00  -4.05         -7.50   0.8996
      3       0.60      43     46.51  -7.54        -13.95   0.8740
      5       0.53    4779     50.66  -3.39         -6.28   1.0000
      5       0.55    1488     51.28  -2.78         -5.14   0.9852
      5       0.57     482     56.85   2.79          5.17   0.1181
      5       0.60     115     51.30  -2.75         -5.09   0.7534
```

Şimdiye kadarki en yakın sonuç: birçok satır başa başın hemen altında ya da üstünde (%53–57). Ama 16 test arasında en iyisi bile p = 0,12; anlamlı değil. Günde 200 $ için gereken %58'e ulaşan, kanıtlanmış bir şey yok.

## GitHub'daki ajan/projeler — karar

| Proje | Karar | Gerekçe |
|---|---|---|
| FreqAI (Freqtrade) | **Fikri alındı** | Günlük yeniden eğitim → `binary/ml.py` |
| Microsoft Qlib | **Fikri alındı** | Alfa faktörleri + kayan pencere testi → `binary/round3.py` |
| TradingAgents | **Fikri alındı** (sınırlı) | LLM yalnızca günlük değerlendirme yapar → `binary/review.py`; dakikalık kararda gürültüye boğulur ve pahalıdır |
| FinRL | **Alınmadı** | Pekiştirmeli öğrenme bu veri miktarında ezberler; avantaj kaynağı eklemez |
| Freqtrade, Jesse, Hummingbot (botun kendisi) | **Alınmadı** | Kripto borsaları için; ikili opsiyonla çalışmaz |
| "Pocket Option bot / sinyal" depoları | **Kesinlikle alınmadı** | Resmî olmayan API kullanır (hesap kapatma riski), bir kısmı giriş bilgisi toplar; hiçbiri doğrulanabilir sonuç sunmaz |

**Asıl darboğaz ajan değil, veri.** Yahoo verisi Pocket Option'ın fiyat akışı değil; saniye düzeyinde de değil. En değerli sonraki adım: kullanıcının PC'sindeki Pocket Option kayıtlarıyla (platformun kendi akışı) aynı testleri tekrarlamak.

---

# 4. Pocket Option'ın kendi verisiyle test (16 Kasım canlı demo kaydı)

Kaynak: kullanıcının PC'sindeki "Yön tahmini botu" oturumunun canlı kaydı (`results_20261116.jsonl`, 222.763 sinyal, 41 strateji, 19 parite, 09:36–16:37 UTC). Veri depoya eklenmedi; analiz kodu `binary/pocket_log.py`.

## Ödemeler beklenenden çok düşük
- Medyan ödeme **%75**; sinyallerin **%41,7**'sinde ödeme %70'in altında, %10'unda %40 ve altında.
- Pariteye göre büyük fark: GBPUSD medyan %50 (başa baş %66,7), GBPJPY %86.
- Gün içinde düşüyor: 09 UTC medyan %89 → 12 UTC %69.
- Gerçek ödemelerle ağırlıklı başa baş **%60,3**; kayıttaki genel isabet **%48,84** → işlem başı beklenen **−%18**.
- Yalnızca yüksek ödemeli işlemler: ödeme ≥ %85'te isabet %48,74 (başa baş %53,16); ≥ %90'da %48,20 (başa baş %52,19).

## Gizli avantajlı köşe var mı?
Strateji (40), parite (19), vade (4), saat (7), strateji×vade (148), strateji×parite (472) hücrelerinin **hiçbiri** Bonferroni eşiğini geçmedi. En iyi görünen strateji×parite hücreleri (%62–67, 100–377 işlem) 472 hücre arasında şans eseri beklenecek düzeyde.

## Yahoo'daki "sahte ortalamaya dönüş" Pocket'ta var mı?
Pocket akışında dakikalık getirilerin otokorelasyonu Yahoo'dakinden belirgin şekilde zayıf (EURUSD 0,000 vs Yahoo −0,13; USDCAD −0,12 vs −0,31). Yahoo'da gecikmesiz girişte görülen %60+ kazanç büyük ölçüde Yahoo verisine özgüydü; Pocket'ta yakalanacak bir şey değil.

## Bu oturumun adayları, Pocket verisinde (örneklem dışı)
Yahoo'da seçilmiş 6 aday × 4 vade × 2 gecikme = 48 test; gerçek ödemelerle **hiçbiri** Bonferroni eşiğini (p < 0,00104) geçmedi. Çiftler arası adaylar 7 saatlik seride çok az sinyal üretti (1–18 işlem); değerlendirilemez.

## Sonuç
İki bağımsız çalışma (Yahoo + HistData + Pocket'ın kendi akışı + 222 bin canlı demo sinyal) aynı sonuca varıyor: 1–5 dk vadede Pocket Option'da kârlı bir yön tahmini yok. Düşük ve değişken ödemeler, isabet %50'nin biraz üstüne çıksa bile işlemi zarara sokuyor.

---

# 5. Daha uzun vade: 15 ve 30 dakika

Tüm turlar 15/30 dk vadeyle yeniden çalıştırıldı (Yahoo, 30 gün, 10 parite, 1 dk giriş gecikmesi). 15+ dk için daha uzun geriye bakan parametreler eklendi (z-skor 60–240, ROC 15–60, kırılım 240–480, üçgen 480–960 vb.).

| Tur | Kombinasyon | Testi geçen | Test döneminde en iyi (yeterli işlemle) |
|---|---|---|---|
| 1 — kural stratejileri | 856 | 0 / 15 | eğitimin en iyileri testte %44–55 |
| 2 — çiftler arası, kırılım, mevsimsellik… | 166 | 0 / 14 | %48–53 (mevsimsellik yine eğitimde %75 → testte %51) |
| ML (tek parite) | 8 | 0 | 30 dk, eşik 0,60: %56,4 (n=172, p=0,29) |
| 3 — çiftler arası ML | 8 | 0 | 30 dk, eşik 0,60: %56,1 (n=540, p=0,18) |

**Gözlem:** Çiftler arası ML'de 30 dk vadede eşik yükseldikçe isabet düzenli artıyor (%52,1 → %54,8 → %56,1). Zayıf bir sinyalin işareti olabilir; ancak anlamlı değil, test dönemi yalnızca ~8 gün ve Pocket'ın gerçekçi ödemesinde (%75 → başa baş %57,1) yine zararda. Daha fazla veri biriktikçe (günlük görev) yeniden bakılmalı.

**Sonuç:** Vadeyi 15–30 dk'ya uzatmak tabloyu değiştirmedi; kalıcı ve kanıtlanmış avantaj yok.

---

# 6. Daha fazla veri ve ön kayıt

**Neden ön kayıt?** "Testi geçene kadar dene" yaklaşımında yeterince deneme yapılınca bir şey mutlaka şans eseri geçer. Bu yüzden keşifte iyi görünen her aday parametreleri dondurularak `binary/candidates.json`'a tarihle yazılır ve yalnızca **kayıt tarihinden sonra oluşan** veride test edilir (`binary/registry.py`, günlük görevde `forward_validation.txt`).

**5 dk veriyle (≈84 gün) çiftler arası ML, 30 dk vade, eşik 0,60:**
- Keşif: 2.856 işlem, **%56,86** (%85 ödemede başa baş %54,05); 10 paritenin 9'u, 9 haftanın 7'si başa başın üstünde. Giriş 5 dk gecikmeli (temkinli).
- **Zayıflıyor:** ilk yarı %59,2 → ikinci yarı %54,7; son haftalar %51,7 / %55,4 / %50,9 / %56,2.
- **1 Kasım'da kaydedilmiş olsaydı:** sonraki 17 günde 691 işlem, %54,56, p = 0,41 → **KALDI**.
- %75 ödemede (Pocket medyanı) başa baş %57,14; keşif sonucu bile bu eşiğin altında.

Aday `cross_ml_30m_p60` olarak 18 Kasım'da kaydedildi. Günde ~45 işlem ürettiği için 300 işleme ~7 iş gününde ulaşır; o zamana kadar durum **BEKLİYOR**.
