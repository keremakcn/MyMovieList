# MyMovieList v3.8.0 — Cinema Stats, Letterboxd & IMDb Import, Unified UI

## What's new

- **Letterboxd & IMDb import (Web & Desktop):** bring your existing film history
  into your shelf in seconds from a Letterboxd export `.zip` / `.csv` or IMDb
  `.csv`. Ratings (0.5–5.0 stars converted to 1–10), watched dates, watchlists
  and reviews are merged automatically; existing records are never overwritten
  and unmatched or offline titles are preserved as custom films.
- **Personal Cinema Statistics (`/stats`):** private, on-device analytics with
  pure CSP-safe SVG charts for your 1–10 rating distribution, monthly watch
  cadence, top genres with average scores, decade breakdown, total watch time
  and most-watched directors and actors.
- **Unified editorial cinema UI & backdrops:** `myshelf.cloud` now shares the
  desktop app's obsidian, lavender and cinema-gold aesthetic with editorial
  serif headings, cinematic TMDB backdrop headers on film pages, an interactive
  1–10 quick-rating strip, library search, 10 sort modes and 48-film pagination
  backed by per-entry IndexedDB v2 storage.
- **PWA, Open Graph cards & update banner:** install `myshelf.cloud` as a
  standalone app, share `/movie/<id>` and `/person/<id>` links with rich poster
  preview cards, and receive a quiet in-app notification on desktop when a new
  GitHub release is available.
- **Social scale indexes (migration 008):** `pg_trgm` trigram search and partial
  `watched_date` indexes accelerate public directory search and weekly feeds.
- **Favorite actors and directors (from 3.7):** keep separate private
  collections with automatic account sync and person filmography pages.

## Updating

Release filenames for 3.8.0:

- **Windows:** `MyMovieList-v3.8.0-windows.zip`, containing
  `MyMovieList-v3.8.0.exe`. Close the previous app before replacing it.
- **Android:** `MyMovieList-3.8.0-android-beta.1.apk`, versionCode 12.
  Install the signed update over the previous app without uninstalling.
  The matching `.aab` is for Google Play submission.
- **macOS:** `MyMovieList-v3.8.0-macos-arm64-beta.dmg` for Apple Silicon, or
  `MyMovieList-v3.8.0-macos-x86_64-beta.dmg` for Intel. Build from the current
  commit through the macOS workflow, then replace the app in Applications.

Accounts remain optional. Saved libraries and account ownership keep their
existing data paths. Hosted Supabase migrations 001–008 are installed;
users need no API key or manual cloud setup.

## Türkçe

- **Letterboxd ve IMDb içe aktarma (Web ve Masaüstü):** Letterboxd `.zip` /
  `.csv` veya IMDb `.csv` dışa aktarma dosyalarını saniyeler içinde kütüphanene
  taşı. Puanlar (0.5–5.0 yıldız → 1–10), izleme tarihleri, izlenecekler ve
  inceleme notları birleştirilir; mevcut kayıtların üzerine yazılmaz.
- **Kişisel Sinema İstatistikleri (`/stats`):** tamamen cihazda yerel hesaplanan
  1–10 puan dağılımı, aylık izleme ritmi, öne çıkan türler ve ortalama puanlar,
  on yıllara göre dağılım, toplam izleme süresi ve en çok izlenen
  yönetmen/oyuncu grafikleri.
- **Birleşik sinema arayüzü ve backdrop afişler:** `myshelf.cloud` artık
  masaüstüyle aynı obsidiyen, lavanta ve altın sinema temasına, film detayında
  sinematik arka plan (backdrop) görsellerine, tek tıkla 1–10 hızlı puan
  şeridine, kütüphane içi Türkçe duyarlı aramaya, 10 sıralama moduna ve kayıt
  bazlı IndexedDB v2 + 48'li sayfalamaya sahip.
- **PWA, Open Graph paylaşım kartları ve sürüm bildirimi:** web sürümünü
  uygulama olarak yükle, film/kişi bağlantılarını posterli zengin kartla paylaş
  ve masaüstünde yeni sürüm çıktığında uygulama içi bildirim al.
