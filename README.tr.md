<p align="center">
  <img src="static/branding/mymovielist-256.png" alt="MyMovieList logosu" width="110">
</p>
<h1 align="center">MyMovieList</h1>
<p align="center"><strong>Filmlerin, düşüncelerin, sana ait bir alan.</strong></p>
<p align="center">İzlemek istediklerini biriktir, yeni filmler keşfet, aklında kalanları kendin için yaz. Hesap açman veya API anahtarı ayarlaman gerekmez.</p>
<p align="center"><a href="https://github.com/keremakcn/MyMovieList/releases/latest"><strong>İndir</strong></a> · <a href="https://github.com/keremakcn/MyMovieList/releases">Tüm sürümler</a></p>

[English](README.md) | **Türkçe**

## Başlarken

**Windows — v3.4.0**

1. Sürüm sayfasının **Assets** bölümünden `MyMovieList-v3.4.0-windows.zip` dosyasını indir.
2. Arşivi çıkar ve `MyMovieList-v3.4.0.exe` dosyasını aç. Python kurman gerekmez.
3. Bir film arayıp kütüphanene ekle. Keşif için ek ayar gerekmez.

**Android — 3.4.0-android-beta.1**

**Assets** bölümünden `MyMovieList-3.4.0-android-beta.1.apk` dosyasını indirip telefonunda aç. Android 7.0 veya üzeri, 64 bit ARM cihaz ve güncel Android System WebView gerekir. Android uygulaması kendi başına çalışır ve kendi kütüphanesini tutar; Windows ile eşitleme yoktur. Bu bir beta sürümüdür ve fiziksel cihaz testleri henüz tamamlanmamıştır. [Android ayrıntıları](ANDROID.md).

## Neler yapabilirsin?

- **Türkçe veya İngilizce kullan.** İlk açılışta cihazının arayüz dili esas alınır; Türkçe dışındaki diller için İngilizce kullanılır. Tercihini **Ayarlar → Dil** bölümünden değiştirebilirsin. Türkçe filmler özgün Türkçe adlarıyla gösterilir; özetlerde mevcut Türkçe çeviri, bulunamazsa İngilizce metin kullanılır.
- **Kendi film kütüphaneni oluştur.** İzlediklerini ve izlemek istediklerini takip et; puan, favori ve kişisel not ekle. Kütüphaneni filtrele, sırala ve yanlışlıkla sildiğin bir filmi bilgilerini kaybetmeden geri al.
- **Film ayrıntılarını sakla.** Oyuncular, yönetmenler, senaristler, yapımcılar ve stüdyolar film eklenirken kaydedilir. Eski kayıtların eksik bilgileri çevrimiçi gezinirken tamamlanır; kaydedilen ayrıntılar ve iki dildeki mevcut özetler çevrimdışı da okunabilir.
- **Keşfet.** Günlük veya haftalık trendler, en yüksek puanlı filmler, yeni çıkanlar ve türler arasında gezin. Kütüphanendeki filmleri gizle, afiş kartından doğrudan film ekle; oyuncu, yönetmen ve yapım şirketlerinin diğer filmlerine göz at.
- **Zevkine göre öneriler bul.** Puanların, favorilerin ve sevdiğin film seçimlerin; türler, mevcut temalar, yönetmenler ve başrol oyuncularıyla birlikte değerlendirilir. Üç keşif seçeneği tanıdık tercihlerle yeni ilgi alanlarını farklı oranlarda bir araya getirir. Yeni öneriler istediğinde, seçenekler elverdiği ölçüde yakın zamanda gösterilen filmler ve benzer temalar daha az tekrarlanır.
- **Aradığını hızlıca bul.** Arama sonuçlarından ayrılmadan film ekle. **Ctrl+K** ile aramayı aç; önerilerde ve arayüzde klavyeyle gezinebilirsin.

## Ekran görüntüleri

Görüntüler güncel uygulamadan, örnek bir kütüphane ve herkese açık katalog verileriyle alınmıştır. [İngilizce ekran görüntülerine](README.md#screenshots) de göz atabilirsin.

### Film kütüphanen

![MyMovieList Türkçe film kütüphanesi](screenshots/tr/library.png)

### Yeni filmler keşfet

![MyMovieList Türkçe Keşfet sayfası](screenshots/tr/explore.png)

### Sana göre öneriler

![MyMovieList Türkçe kişisel film önerileri](screenshots/tr/recommendations.png)

<details>
<summary>Film ayrıntıları ve yönetmen sayfası</summary>

![MyMovieList Türkçe film ayrıntıları](screenshots/tr/movie-details.png)

![MyMovieList Türkçe yönetmen sayfası](screenshots/tr/director.png)

</details>

<details>
<summary>Telefon boyutunda görünümler</summary>

Bu görseller, arayüzün dar ekranlara uyarlanan görünümünü gösterir.

<p align="center">
  <img src="screenshots/tr/mobile-library.png" alt="Türkçe film kütüphanesinin mobil görünümü" width="44%">
  <img src="screenshots/tr/mobile-explore.png" alt="Türkçe Keşfet sayfasının mobil görünümü" width="44%">
</p>

</details>

## Düşüncelerin sana ait kalsın

Her filmin ardından yazdıklarını paylaşmak zorunda değilsin. Kütüphanen, notların, puanların ve favorilerin cihazında kalır; keşif servisine veya TMDB’ye yüklenmez. Öneri sıralaması cihazında yapılır; kişisel notların analiz edilmez.

Aramalar ve film kataloğu istekleri `api.myshelf.cloud` üzerinden TMDB’ye iletilir. Keşif ve uzak görseller için internet gerekir; kaydedilmiş film bilgileri ve indirilmiş afişler çevrimdışı kullanılabilir. Önerilerde kullanılan herkese açık film havuzu cihazında önbelleğe alınır; çevrimdışı sonuçlar bu havuzdaki verilere bağlıdır. Uygulama yerel verileri ayrıca şifrelemez.

**Windows güncellemeleri kütüphaneni korur.** EXE dosyasını değiştirmeden önce uygulamayı kapat. Verilerin `%APPDATA%\MovieWatchlist` içinde kalır; eski klasör adı uyumluluk için korunur. Android’de veriler uygulamanın özel depolama alanında tutulur ve aynı imzalı sürümle yapılan normal güncellemede korunur. Uygulamayı kaldırmak veya depolama alanını temizlemek telefondaki kütüphaneyi siler. İki cihazın kütüphaneleri birbirinden bağımsızdır.

## Kaynak koddan çalıştırma

Python 3.12 önerilir. Windows’ta proje klasöründen:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-desktop.txt
.\.venv\Scripts\python run_desktop.py
```

Geliştirme ayrıntıları için [sürüm notları](RELEASE_NOTES.md), [test sonuçları](QA_RESULTS.md), [Android derleme yönergeleri](ANDROID.md) ve [keşif servisi kurulumu](cloudflare/watchlist-api/README.md) belgelerine bakabilirsin.

## Teşekkürler

Film verileri ve görseller [TMDB](https://www.themoviedb.org) tarafından sağlanır. Bu ürün TMDB API’sini kullanır ancak TMDB tarafından onaylanmış veya sertifikalandırılmış değildir.
