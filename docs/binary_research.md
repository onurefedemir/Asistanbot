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
