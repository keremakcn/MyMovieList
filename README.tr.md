<p align="center">
  <img src="static/branding/mymovielist-256.png" alt="MyMovieList logosu" width="110">
</p>
<h1 align="center">MyMovieList</h1>
<p align="center"><strong>Filmlerin, düşüncelerin, sana ait bir alan.</strong></p>
<p align="center">İzlemek istediklerini biriktir, yeni filmler keşfet, interaktif sinema istatistiklerini incele ve aklında kalanları kendin için yaz. Hesap açman veya API anahtarı ayarlaman gerekmez.</p>
<p align="center"><a href="https://github.com/keremakcn/MyMovieList/releases/latest"><strong>İndir</strong></a> · <a href="https://github.com/keremakcn/MyMovieList/releases">Tüm sürümler</a></p>

[English](README.md) | **Türkçe**

**Sürüm 4.0.0 — Obsidian Screening Room:** Windows, Android ve Web genelinde tam ekran sinematik tasarım yenilemesi — üç farklı kütüphane modu (**Günlük**, **3D Raf**, **Afişler**), favori veya `8+` puanlı filmlerinden dönen canlı ortam arka planları, tıklanabilir afiş inceleyicili **Sinema İstatistikleri** (`/stats`), aylık dalga grafiği, kristal tür radarı, 10 basamaklı puan merdiveni, yönetmen/oyuncu portreleri ve önbellekli stüdyo logoları, festival kartlı **Sana Özel** önerileri, çerçevesiz **Keşfet** duvarı, boydan boya film detay sayfaları ve **40+ karakter otomatik not kaydı**.

## Başlarken

Windows ve Android `4.0.0` sürüm paketleri doğrudan bu kaynaktan derlenir. macOS paketleri de aynı `4.0.0` kaynağını paylaşır.

**Windows — v4.0.0**

1. Sürüm sayfasının **Assets** bölümünden `MyMovieList-v4.0.0-windows.zip` dosyasını indir.
2. Arşivi çıkar ve `MyMovieList-v4.0.0.exe` dosyasını aç. Python kurman gerekmez.
3. Bir film arayıp kütüphanene ekle. Keşif için ek ayar gerekmez.

**Android — 4.0.0-android-beta.1**

**Assets** bölümünden `MyMovieList-4.0.0-android-beta.1.apk` dosyasını indirip telefonunda aç (Play Store için eşleşen `.aab` paketi de derlenir). Android 7.0 veya üzeri, 64 bit ARM cihaz ve güncel Android System WebView gerekir. Android uygulaması kendi başına çalışır, kütüphaneni telefonda saklar ve giriş yaparsan hesap kütüphaneni Windows ve Web ile eşitleyebilir. Hesap açmak isteğe bağlıdır. [Android ayrıntıları](ANDROID.md).

**macOS — v4.0.0 beta**

macOS 15 veya üzeri gerekir. Apple Silicon (M serisi) için `arm64`, Intel için `x86_64` DMG'yi seç; açıp MyMovieList'i **Applications** klasörüne taşı. `4.0.0` kaynakları Obsidian Screening Room tasarımını, interaktif sinema istatistiklerini, Letterboxd/IMDb içe aktarmayı, otomatik not kaydını, favori oyuncu/yönetmenleri, alan bazlı zamanlı eşitlemeyi ve paketlenmiş HTTPS sertifikalarını içerir. DMG dosyaları bu sürümden macOS iş akışıyla derlenir; bu betalar Apple tarafından noterlenmemiştir. [Mac derleme ve kurulum ayrıntıları](MACOS.md).

## Web

[Web’de kullan](https://myshelf.cloud) — web PWA.

MyShelf web sürümü uygulamayla aynı hesabı ve özel kütüphaneyi kullanır: kayıt bazlı IndexedDB depolama, çevrimdışı PWA desteği, otomatik eşitleme, e-postayla başlayan kayıt akışı, profil avatarları, seçilen vitrinler, dinamik Open Graph kartları ve otomatik uzun not kaydı. Kurulum ayrıntıları [WEB.md](WEB.md)'de.

Alan bazında değişiklik zamanları web, Windows, Android ve macOS arasında taşınır; güvenilir çakışmalarda güncel değişiklik seçilir, bağımsız düzenlemeler birleştirilir ve eski çakışmalar kurtarılabilir tutulur.

## Neler yapabilirsin?

- **Üç sinematik kütüphane modu (`Günlük → 3D Raf → Afişler`):** koleksiyonunu geniş ekran film sahneleri (**Günlük**), tıklandığında tam sahneye açılan fiziksel 3D kitap sırtları (**3D Raf**) veya çerçevesiz 2:3 galeri duvarı (**Afişler**) olarak gez.
- **Canlı Kütüphane Arkaplanı:** kütüphane ve istatistik sayfaları her açıldığında yalnızca favori (`♥`) veya `8+` puanlı filmlerinden birinin geniş ekran sahnesiyle aydınlanır.
- **İnteraktif Sinema İstatistikleri (`/stats`):** 53 haftalık tıklanabilir izleme ısı haritası (üzerine gelince o gün izlenen filmleri anlık gösterir), ışıklı aylık dalga grafiği, haftanın günleri ekolayzır sütunları, altıgen kristal tür radarı, 10 basamaklı puan merdiveni, mini afişli 35mm on yıl şeritleri, 2×2 film süresi kartları, TMDB yönetmen/oyuncu portreleri, önbellekli stüdyo logoları + film afiş desteleri, her grafiğe tıklayınca açılan **Film İnceleyici** penceresi ve cihazda yerel üretilen **1080×1350 Sinema Pasaportu PNG** (kişisel notlar asla dahil edilmez).
- **Boydan Boya Film Detayı ve Otomatik Not Kaydı:** tek bütün tam ekran film sahnesi, buzlu cam üst/yan menü, satır içi 1–10 hızlı puanlama, yan yana **Özel Eleştirmen Kasası (Notun) & Özet** düzeni ve 40 karakteri geçen kişisel notların sessizce otomatik kaydedilmesi.
- **Letterboxd ve IMDb İçe Aktarma:** Letterboxd (`.zip`/`.csv`) veya IMDb (`.csv`) geçmişini **Ayarlar** üzerinden mevcut notlarını ve puanlarını bozmadan kütüphanene aktar.
- **Keşfet ve Sana Özel Festival Kartları:** trendler, en yüksek puanlılar, yeni çıkanlar ve tür portallarını çerçevesiz afiş duvarı olarak gez; 3 modlu keşif frekans kadranıyla (**Zevkime yakın**, **Biraz keşif**, **Beni şaşırt**) sıralı gösterim kartları al.
- **Sinemacılar, Stüdyolar ve Favori Kişiler:** oyuncular, yönetmenler ve yapım şirketlerini fotoğraflı kartlar ve kariyer zaman çizelgesiyle keşfet; beğendiğin oyuncu ve yönetmenleri gizli listende topla.
- **Sosyal:** isim veya kullanıcı adıyla açık profilleri bul, seçilmiş vitrinlere uygulama içinden ulaş. Özel notların ve kütüphanenin geri kalanı daima gizli kalır.
- **Türkçe ve İngilizce arayüz:** ilk açılışta cihazının dilini izler, tercihini **Ayarlar → Dil** altından istediğin an değiştirebilirsin.
- **Hızlı Komut Paleti (`Ctrl+K` / `⌘K`):** her sayfadan anında film ara, görünüm modu değiştir veya bölümler arasında atla.

## Ekran görüntüleri

Ekran görüntüleri doğrudan **v4.0.0** sürümünden, örnek bir demo kütüphanesi ve canlı katalog verileriyle alınmıştır. [İngilizce arayüze göz at](README.md#screenshots).

### Kütüphanen — Günlük, 3D Raf ve Afişler

![Canlı ortam arka planı, buzlu cam sayaçlar ve tam genişlik film sahnesi kartlarıyla MyMovieList v4.0.0 Günlük kütüphanesi](screenshots/tr/library.png)

<details>
<summary>3D Raf ve çerçevesiz Afişler görünümleri</summary>

![Afiş sırtları ve tam ekran sahneye açılan filmiyle 3D Fiziksel Raf görünümü](screenshots/tr/library-shelf.png)

![Çerçevesiz 2:3 Afişler galeri duvarı](screenshots/tr/library-posters.png)

</details>

### İnteraktif Sinema İstatistikleri

Isı haritasındaki her aktif gün, dalga noktaları, radar köşeleri, puan basamakları, on yıl şeritleri ve süre kartları tıklanabilir — cihazında yerel hesaplanır, kişisel notların asla dışarı çıkmaz.

![Tamamlama halkası, temel göstergeler, mini afişli arşiv rekorları ve tıklanabilir ısı haritasıyla Sinema İstatistikleri](screenshots/tr/stats.png)

<details>
<summary>Tür Takımyıldızı Radarı, 10 Basamaklı Puan Merdiveni, Portreler ve Stüdyo Logoları</summary>

![Kristal Tür Takımyıldızı Radarı, 10 basamaklı Puan Dağılımı ve 35mm on yıl şeritleri](screenshots/tr/stats-constellation.png)

![TMDB portreli en çok izlenen yönetmenler ve oyuncular ile logolu ve afiş desteli stüdyolar](screenshots/tr/stats-podium.png)

</details>

### Boydan boya film detayı ve özel not kasası

![Interstellar için tam ekran arka planlı, hızlı puanlamalı, özel not kasalı ve özetli film detay sayfası](screenshots/tr/movie-details.png)

### Keşfet ve sana özel öneriler

![Sinema Lobisi ve çerçevesiz 2:3 Trend filmler duvarıyla Keşfet sayfası](screenshots/tr/explore.png)

![3 modlu keşif frekans kadranı ve festival gösterim kartlarıyla Sana özel sayfası](screenshots/tr/recommendations.png)

<details>
<summary>Yönetmen profilleri, Sosyal ve isteğe bağlı hesap ekranları</summary>

![Christopher Nolan profili ve kronolojik filmografisi](screenshots/tr/director.png)

![Açık vitrinlerle MyMovieList Sosyal sayfası](screenshots/tr/social.png)

![Doğrulama adımları ve yerel kütüphane kopyalama şemasıyla e-posta üzerinden kayıt](screenshots/tr/registration.png)

![E-posta ve şifreyle giriş, hesap açmadan devam etme seçeneği](screenshots/tr/sign-in.png)

</details>

<details>
<summary>Telefon görünümü: kütüphane, keşif, sana özel ve istatistikler</summary>

Ortak v4.0.0 arayüzünün yüzen alt menüyle telefon boyutundaki (`390×844`) görünümü.

<p align="center">
  <img src="screenshots/tr/mobile-library.png" alt="Türkçe kütüphane telefon görünümü" width="44%">
  <img src="screenshots/tr/mobile-explore.png" alt="Türkçe keşif sayfası telefon görünümü" width="44%">
</p>
<p align="center">
  <img src="screenshots/tr/mobile-recommendations.png" alt="Türkçe sana özel öneriler telefon görünümü" width="44%">
  <img src="screenshots/tr/mobile-stats.png" alt="Türkçe sinema istatistikleri telefon görünümü" width="44%">
</p>

</details>

## İsteğe bağlı hesap ve profil

Hesap açmadan kullanmaya devam edebilir veya özel kütüphaneni cihazlar arasında taşımak için giriş yapabilirsin.

- **Otomatik eşitleme:** puanların, notların, favorilerin ve izleme durumun önce cihazına kaydedilir, bağlantı varsa buluta eşitlenir. Eşitle düğmesine basman gerekmez. Eşitlemeyi duraklatabilirsin; bekleyen değişiklikler cihazında kalır.
- **Kayıt olurken filmlerin korunur:** yeni hesap oluşturduğunda bu cihazda kayıtlı filmler; notları, puanları, favorileri ve eklenme sırasıyla otomatik olarak hesabına kopyalanır. Kayıt ekranında işlem önceden açıklanır. İlk yerel kopyan cihazında kalır.
- **Ayrı kütüphaneler:** mevcut hesaba giriş yaptığında o hesabın kütüphanesi açılır. İlk yerel kütüphaneni hesap ayarlarından kopyalayabilirsin; hesapta zaten bulunan filmlerin notları ve puanları korunur.
- **Adım adım kayıt:** e-posta → doğrulama kodu → benzersiz kullanıcı adı → şifre. Normal giriş e-posta ve şifreyle yapılır. Şifre yenilemede önce kod doğrulanır, sonra yeni şifre istenir.
- **Sana ait profil:** görünen isim ve 16 hazır kedi avatarından birini seç. Benzersiz `@kullanıcı_adın` profilinde görünür, bir kez seçilir ve şu an değiştirilemez.
- **Vitrinin:** sergilemek istediğin en fazla altı filmi kendin seçip sırala. Paylaşım başlangıçta kapalıdır. Açarsan adresin `myshelf.cloud/u/<kullanıcı_adı>` olur. Yalnızca seçtiğin filmler paylaşılır; puanları ve kütüphane sayaçlarını göstermek de isteğe bağlıdır.
- **Özel notların:** film notların, e-postan, elle eklediğin filmler ve kütüphanenin geri kalanı herkese açık profilde veya paylaşılabilir sinema kartlarında asla görünmez.

## Düşüncelerin sana ait kalsın

Her filmin ardından yazdıklarını paylaşmak zorunda değilsin. Kütüphanen, notların, puanların ve favorilerin cihazına kaydedilir; keşif servisine veya TMDB’ye yüklenmez. İsteğe bağlı bir hesap kullanırsan hesaba ait kütüphane Supabase üzerinden özel olarak eşitlenir.

Öneri sıralaması ve sinema istatistikleri cihazında hesaplanır; kişisel notların analiz edilmez.

Aramalar ve film kataloğu istekleri `api.myshelf.cloud` üzerinden TMDB’ye iletilir. Keşif ve uzak görseller için internet gerekir; kaydedilmiş film bilgileri ve indirilmiş afişler çevrimdışı kullanılabilir. Uygulama yerel verileri ayrıca şifrelemez.

**Windows güncellemeleri kütüphaneni korur.** EXE dosyasını değiştirmeden önce uygulamayı kapat. Verilerin `%APPDATA%\MovieWatchlist` içinde kalır; eski klasör adı uyumluluk için korunur. Android’de veriler uygulamanın özel depolama alanında tutulur ve aynı imzalı sürümle yapılan normal güncellemede korunur.

## Kaynak koddan çalıştırma

Python 3.12 önerilir. Windows’ta proje klasöründen:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-desktop.txt
.\.venv\Scripts\python run_desktop.py
```

Windows derlemesi için `.\scripts\build_release.ps1`, Android sürüm paketi için `.\scripts\build_android.ps1 -Release` kullanılır. Ayrıntılar için [sürüm notları](RELEASE_NOTES.md), [test sonuçları](QA_RESULTS.md), [Android derleme yönergeleri](ANDROID.md) ve [keşif servisi kurulumu](cloudflare/watchlist-api/README.md) belgelerine bakabilirsin.

Geliştiriciler için: [bulut kurulumu](supabase/README.md) ve [veri taşıma tasarımı](CLOUD_SYNC_DESIGN.md). Veritabanı geçişleri `001–008` hesapları, Sosyal özelliğini ve ölçeklenme indekslerini etkinleştirir. [Sosyal tasarım ve doğrulama](SOCIAL_DESIGN.md).

## Teşekkürler

Film verileri ve görseller [TMDB](https://www.themoviedb.org) tarafından sağlanır. Bu ürün TMDB API’sini kullanır ancak TMDB tarafından onaylanmış veya sertifikalandırılmış değildir.
