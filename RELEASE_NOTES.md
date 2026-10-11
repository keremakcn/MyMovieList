# MyMovieList v3.7.0 — Favorite People

## What's new

- **Favorite actors and directors:** use the heart on a person card to keep
  separate private collections. Open Favorite people from your profile or
  the sidebar; the same person can be a favorite in both roles.
- **Person filmography:** open an actor or director to browse their films,
  portrait and available biography.
- **Automatic preference sync:** favorites save locally first and sync with
  your account when connected. New registration adopts guest choices, and
  library exports include them. Newer changes win; an older offline choice
  cannot bring back a person you removed later.
- **Private collections:** favorite people stay separate from public showcases.
  Only IDs, roles, choices and edit times sync; person photos and biographies
  remain catalog data cached on the device.
- **Web landing posters:** four daily trending-film posters expand on hover or
  keyboard focus and open the matching film details. If a refresh fails, the
  last usable selection stays visible.
- **Smooth favoriting:** toggling a person heart keeps you on the film page and
  preserves an unsaved film note in the web app.

## Updating

Native 3.7.0 packages are pending build and publication. Expected filenames:

- **Windows:** `MyMovieList-v3.7.0-windows.zip`, containing
  `MyMovieList-v3.7.0.exe`. Close the previous app before replacing it.
- **Android:** `MyMovieList-3.7.0-android-beta.1.apk`, versionCode 11.
  Install the signed update over the previous app without uninstalling.
  The matching `.aab` is for Google Play submission.
- **macOS:** `MyMovieList-v3.7.0-macos-arm64-beta.dmg` for Apple Silicon, or
  `MyMovieList-v3.7.0-macos-x86_64-beta.dmg` for Intel. Build from the current
  commit through the macOS workflow, then replace the app in Applications.

Accounts remain optional. Saved libraries and account ownership keep their
existing data paths. Hosted Supabase migrations 001–007 are installed;
users need no API key or manual cloud setup. Mac betas remain ad-hoc signed
and are not notarized by Apple. Source checks and build status are recorded
in [QA_RESULTS.md](QA_RESULTS.md).

## Türkçe

- Oyuncu ve yönetmenleri kalp düğmesiyle iki ayrı özel listede saklayabilirsin.
  Profilinden veya sol menüdeki **Favori kişiler** bölümünden listelerine ulaş.
- Kişinin fotoğrafına tıklayarak filmografisini ve mevcut biyografisini aç.
- Favoriler önce cihazda kaydedilir, giriş yaptığında otomatik eşitlenir.
  Yeni hesap açarken misafir tercihlerin de taşınır; dışa aktarmaya dahil edilir.
  Daha yeni tercih korunur, eski cihazdaki kayıt çıkarılan kişiyi geri getirmez.
- Favori kişiler herkese açık vitrininde görünmez. Fotoğraf ve biyografi gibi
  katalog bilgileri kişisel eşitleme verisine eklenmez.
- Web tanıtım sayfasındaki dört afiş günlük yenilenir, üzerine gelince veya
  klavyeyle odaklanınca açılır; tıklanınca ilgili filmin detayına gider.
- Film sayfasından ayrılmadan kişileri favorileyebilirsin. Web'de yazmakta
  olduğun film notu kalbe bastığında korunur.

3.7.0 kaynak kodu hazır; EXE, APK/AAB ve DMG dosyaları henüz yeniden derlenmedi.
