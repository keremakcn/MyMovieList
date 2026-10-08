<p align="center">
  <img src="static/branding/mymovielist-256.png" alt="MyMovieList logosu" width="110">
</p>
<h1 align="center">MyMovieList</h1>
<p align="center"><strong>Filmlerin, düşüncelerin, sana ait bir alan.</strong></p>
<p align="center">İzlemek istediklerini biriktir, yeni filmler keşfet, aklında kalanları kendin için yaz. Hesap açman veya API anahtarı ayarlaman gerekmez.</p>
<p align="center"><a href="https://github.com/keremakcn/MyMovieList/releases/latest"><strong>İndir</strong></a> · <a href="https://github.com/keremakcn/MyMovieList/releases">Tüm sürümler</a></p>

[English](README.md) | **Türkçe**

## Başlarken

**Windows — v3.5.0**

1. Sürüm sayfasının **Assets** bölümünden `MyMovieList-v3.5.0-windows.zip` dosyasını indir.
2. Arşivi çıkar ve `MyMovieList-v3.5.0.exe` dosyasını aç. Python kurman gerekmez.
3. Bir film arayıp kütüphanene ekle. Keşif için ek ayar gerekmez.

**Android — 3.5.0-android-beta.3**

**Assets** bölümünden `MyMovieList-3.5.0-android-beta.3.apk` dosyasını indirip telefonunda aç. Android 7.0 veya üzeri, 64 bit ARM cihaz ve güncel Android System WebView gerekir. Android uygulaması kendi başına çalışır, kütüphaneni telefonda saklar ve giriş yaparsan hesap kütüphaneni Windows ile eşitleyebilir. Hesap açmak isteğe bağlıdır. Bu bir beta sürümüdür ve fiziksel cihaz testleri henüz tamamlanmamıştır. [Android ayrıntıları](ANDROID.md).

**macOS — v3.5.0 beta**

macOS 15 veya üzeri gerekir. Apple Silicon (M serisi) için `arm64`, Intel için `x86_64` DMG'yi seç; açıp MyMovieList'i **Applications** klasörüne taşı. Güncel kaynakta HTTPS sertifika düzeltmesi bulunuyor; yeni DMG'lerin Mac ortamında yeniden derlenmesi ve denenmesi gerekiyor. Önceki beta dosyaları açılıyor ancak keşif ve hesap bağlantılarında sorun bildirildi. Bu betalar Apple tarafından noterlenmemiştir. [Mac derleme ve kurulum ayrıntıları](MACOS.md).

## Neler yapabilirsin?

- **Sosyal.** İsim veya kullanıcı adıyla açık profilleri bul, seçilmiş vitrinlere uygulama içinden ulaş. Bu hafta bölümünde yalnızca vitrindeki izleme tarihi girilmiş filmler görünür. Özel notlar ve kütüphanenin geri kalanı gizli kalır. Vitrinini paylaşmak isteğe bağlıdır; profil paylaşımını açana kadar hesabın gizli kalır.
- **Türkçe veya İngilizce kullan.** İlk açılışta cihazının arayüz dili esas alınır; Türkçe dışındaki diller için İngilizce kullanılır. Tercihini **Ayarlar → Dil** bölümünden değiştirebilirsin. Türkçe filmler özgün Türkçe adlarıyla gösterilir; özetlerde mevcut Türkçe çeviri, bulunamazsa İngilizce metin kullanılır.
- **Kendi film kütüphaneni oluştur.** İzlediklerini ve izlemek istediklerini takip et; puan, favori ve kişisel not ekle. Kütüphaneni filtrele, sırala ve yanlışlıkla sildiğin bir filmi bilgilerini kaybetmeden geri al.
- **Film ayrıntılarını sakla.** Oyuncular, yönetmenler, senaristler, yapımcılar ve stüdyolar film eklenirken kaydedilir. Eski kayıtların eksik bilgileri çevrimiçi gezinirken tamamlanır; kaydedilen ayrıntılar ve iki dildeki mevcut özetler çevrimdışı da okunabilir.
- **Keşfet.** Günlük veya haftalık trendler, en yüksek puanlı filmler, yeni çıkanlar ve türler arasında gezin. Kütüphanendeki filmleri gizle, afiş kartından doğrudan film ekle; oyuncu, yönetmen ve yapım şirketlerinin diğer filmlerine göz at.
- **Zevkine göre öneriler bul.** Puanların, favorilerin ve sevdiğin film seçimlerin; türler, mevcut temalar, yönetmenler ve başrol oyuncularıyla birlikte değerlendirilir. Üç keşif seçeneği tanıdık tercihlerle yeni ilgi alanlarını farklı oranlarda bir araya getirir. Yeni öneriler istediğinde, seçenekler elverdiği ölçüde yakın zamanda gösterilen filmler ve benzer temalar daha az tekrarlanır.
- **Aradığını hızlıca bul.** Arama sonuçlarından ayrılmadan film ekle. **Ctrl+K** (Mac'te **⌘K**) ile aramayı aç; önerilerde ve arayüzde klavyeyle gezinebilirsin.

## Ekran görüntüleri

Güncel v3.5.0 arayüzünden, örnek bir hesap ve kütüphaneyle alınmıştır. Film bilgileri ve afişler herkese açık katalog verileridir. [İngilizce arayüze göz at](README.md#screenshots).

### Filmlerin, sana ait bir alan

![İzlenen filmler, puanlar, favoriler ve kişisel not önizlemeleriyle MyMovieList kütüphanesi](screenshots/tr/library.png)

### Profilin ve seçtiğin filmler

Seni anlatan filmleri kendin seç. Kişisel özetin ve kütüphanenin geri kalanı herkese açık vitrinden ayrı tutulur.

![Kedi avatarı, benzersiz kullanıcı adı ve altı seçilmiş filmle MyMovieList profili](screenshots/tr/profile.png)

### Filmseverlerle tanış

Açık vitrinlere uygulama içinden ulaş. Bu hafta bölümünde yalnızca seçilmiş,
izleme tarihi girilmiş filmler görünür; kişisel notlar gizli kalır.
Görüntüdeki kullanıcılar örnek hesaplardan oluşur.

![Seçilmiş vitrin filmleriyle MyMovieList Sosyal ve Bu hafta görünümü](screenshots/tr/social.png)

### Yeni favorini keşfet

![Trendler ve yüksek puanlı filmlerle MyMovieList Keşfet sayfası](screenshots/tr/explore.png)

<details>
<summary>Öneriler, film ayrıntıları ve yönetmen keşfi</summary>

![Üç keşif seçeneğiyle kişisel film önerileri](screenshots/tr/recommendations.png)

![Kişisel not, film özeti ve kayıtlı oyuncu ve ekip bilgileri](screenshots/tr/movie-details.png)

![Christopher Nolan'ın profili ve filmografisi](screenshots/tr/director.png)

</details>

<details>
<summary>Kayıt, giriş ve kişisel özetin</summary>

Adım adım kayıt: e-posta → kod → kullanıcı adı → şifre. Kayıt ekranında, cihazındaki filmlerin yeni hesabına nasıl alınacağı açıklanır.

![Doğrulama adımları ve yerel kütüphane aktarım açıklamasıyla e-posta üzerinden kayıt](screenshots/tr/registration.png)

![E-posta ve şifreyle giriş, hesap açmadan devam etme seçeneği](screenshots/tr/sign-in.png)

![Kütüphane sayaçları ve favori filmlerle özel kişisel özet](screenshots/tr/profile-personal.png)

</details>

<details>
<summary>Telefon görünümü: kütüphane, keşif, profil ve kayıt</summary>

Ortak arayüzün telefon boyutuna uyarlanan görünümü; kaynak kod önizlemesinden alınmıştır.

<p align="center">
  <img src="screenshots/tr/mobile-library.png" alt="Türkçe film kütüphanesinin telefon görünümü" width="44%">
  <img src="screenshots/tr/mobile-explore.png" alt="Türkçe keşif sayfasının telefon görünümü" width="44%">
</p>
<p align="center">
  <img src="screenshots/tr/mobile-profile.png" alt="Türkçe profil ve seçilen vitrin filmlerinin telefon görünümü" width="44%">
  <img src="screenshots/tr/mobile-registration.png" alt="Türkçe kayıt ve yerel kütüphane açıklamasının telefon görünümü" width="44%">
</p>

</details>

## İsteğe bağlı hesap ve profil

Hesap açmadan kullanmaya devam edebilir veya özel kütüphaneni cihazlar arasında taşımak için giriş yapabilirsin.

- **Otomatik eşitleme:** puanların, notların, favorilerin ve izleme durumun önce cihazına kaydedilir, bağlantı varsa buluta eşitlenir. Eşitle düğmesine basman gerekmez. Eşitlemeyi duraklatabilirsin; bekleyen değişiklikler cihazında kalır.
- **Kayıt olurken filmlerin korunur:** yeni hesap oluşturduğunda bu cihazda kayıtlı filmler; notları, puanları, favorileri ve eklenme sırasıyla otomatik olarak hesabına kopyalanır. Kayıt ekranında işlem önceden açıklanır. İlk yerel kopyan cihazında kalır.
- **Ayrı kütüphaneler:** mevcut hesaba giriş yaptığında o hesabın kütüphanesi açılır. İlk yerel kütüphaneni hesap ayarlarından kopyalayabilirsin; hesapta zaten bulunan filmlerin notları ve puanları korunur.
- **Adım adım kayıt:** e-posta → doğrulama kodu → benzersiz kullanıcı adı → şifre. Normal giriş e-posta ve şifreyle yapılır. Şifre yenilemede önce kod doğrulanır, sonra yeni şifre istenir.
- **Sana ait profil:** görünen isim ve 16 hazır kedi avatarından birini seç. Görünen isimler aynı olabilir. Benzersiz kullanıcı adı bir kez seçilir ve şimdilik değiştirilemez.
- **Vitrinin:** sergilemek istediğin en fazla altı filmi kendin seçip sırala. Paylaşım başlangıçta kapalıdır. Açarsan adresin `myshelf.cloud/u/<kullanıcı_adı>` olur. Yalnızca seçtiğin filmler paylaşılır; puanları ve kütüphane sayaçlarını göstermek de isteğe bağlıdır.
- **Özel notların:** film notların, e-postan, elle eklediğin filmler ve kütüphanenin geri kalanı herkese açık profilde görünmez. İsim kontrolü kişisel film notlarını sansürlemez.

Profiline sol menüden veya üst çubuktan ulaşabilirsin. Masaüstünde içe/dışa aktarma **Ayarlar** bölümünde kalır. Çevrimdışı kullanım, o cihazda kaydedilen verilere dayanır; başka cihazdaki değişiklikleri almak için bağlantı gerekir.

## Düşüncelerin sana ait kalsın

Her filmin ardından yazdıklarını paylaşmak zorunda değilsin. Kütüphanen, notların, puanların ve favorilerin cihazına kaydedilir; keşif servisine veya TMDB’ye yüklenmez. İsteğe bağlı bir hesap kullanırsan hesaba ait kütüphane Supabase üzerinden özel olarak eşitlenir. Yeni kayıt, kayıt ekranında açıklandığı üzere yerel filmlerini hesaba taşır. Mevcut hesaba girişte ilk yerel kütüphane sen kopyalamayı seçene kadar ayrı kalır. Öneri sıralaması cihazında yapılır; kişisel notların analiz edilmez.

Aramalar ve film kataloğu istekleri `api.myshelf.cloud` üzerinden TMDB’ye iletilir. Keşif ve uzak görseller için internet gerekir; kaydedilmiş film bilgileri ve indirilmiş afişler çevrimdışı kullanılabilir. Önerilerde kullanılan herkese açık film havuzu cihazında önbelleğe alınır; çevrimdışı sonuçlar bu havuzdaki verilere bağlıdır. Uygulama yerel verileri ayrıca şifrelemez.

**Windows güncellemeleri kütüphaneni korur.** EXE dosyasını değiştirmeden önce uygulamayı kapat. Verilerin `%APPDATA%\MovieWatchlist` içinde kalır; eski klasör adı uyumluluk için korunur. Android’de veriler uygulamanın özel depolama alanında tutulur ve aynı imzalı sürümle yapılan normal güncellemede korunur. Uygulamayı kaldırmak veya depolama alanını temizlemek telefondaki kütüphaneyi siler. Hesapla eşitleme kullanılmıyorsa cihaz kütüphaneleri birbirinden bağımsızdır.

## Kaynak koddan çalıştırma

Python 3.12 önerilir. Windows’ta proje klasöründen:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-desktop.txt
.\.venv\Scripts\python run_desktop.py
```

Geliştirme ayrıntıları için [sürüm notları](RELEASE_NOTES.md), [test sonuçları](QA_RESULTS.md), [Android derleme yönergeleri](ANDROID.md) ve [keşif servisi kurulumu](cloudflare/watchlist-api/README.md) belgelerine bakabilirsin.

Geliştiriciler için: [bulut kurulumu](supabase/README.md) ve [veri taşıma tasarımı](CLOUD_SYNC_DESIGN.md). Hesaplar için 001–004, Sosyal için ayrıca 005 veritabanı kurulumu gerekir. [Sosyal tasarım ve doğrulama](SOCIAL_DESIGN.md).


## Teşekkürler

Film verileri ve görseller [TMDB](https://www.themoviedb.org) tarafından sağlanır. Bu ürün TMDB API’sini kullanır ancak TMDB tarafından onaylanmış veya sertifikalandırılmış değildir.
