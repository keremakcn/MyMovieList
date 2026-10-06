# MyMovieList v3.4.0 — Bilingual Discovery & Smarter Recommendations

Discover your next film in English or Turkish, with richer recommendations and automatically saved movie details. This release brings the current shared application to Windows and the signed Android beta.

## What's new

- **English and Turkish:** the first launch follows your device's UI language, then saves your choice locally. Switch languages in Settings. Available Turkish synopses and Turkish-original film names are supported, with English fallback where necessary.
- **Automatic movie details:** cast, directors, writers, producers, studios and bilingual content are saved when adding a film. Older library entries fill missing details as you browse online. Saved details remain readable offline.
- **Smarter personal recommendations:** ratings, favorites and selected films inform a local model using genres, available themes, directors and lead cast. Private notes are not analyzed.
- **More varied discovery:** a broader candidate pool includes classics and rotating international selections. Smaller interests are preserved, with limits on repeated themes, franchises and directors.
- **Distinct discovery modes:** familiar, balanced and adventurous choices use different mixes when enough information is available. New suggestions avoid recent repeats when alternatives exist.
- **Stable suggestions:** browsing and switching interface languages keep the current picks. Added and hidden films stay excluded; changed preferences take effect when you request new suggestions.
- **Explore shelves:** browse Trending by day or week, Highest rated, New releases and Genres. Hide library films and add directly from poster cards.
- **Android update:** the signed `3.4.0-android-beta.1` APK and Play bundle include the current language, discovery and recommendation features. No TMDB account or API key is required.

## Reliability and privacy

- Catalog responses are checked against the requested movie ID before saving or displaying details. Language changes preserve movie identity, notes, ratings, favorites and library order.
- Personal library data and recommendation ranking remain on your device. Catalog requests use the shared discovery service; no developer API credential is embedded in the app.
- The locally cached public recommendation pool can supply suggestions offline after an online fetch. Available results still depend on the cached pool and metadata.
- Existing removal/Undo behavior preserves personal fields and the original library order.

## Upgrading

- **Windows:** close the previous app, extract `MyMovieList-v3.4.0-windows.zip` and open `MyMovieList-v3.4.0.exe`. Your existing library remains in `%APPDATA%\MovieWatchlist`; an explicit `MOVIE_WATCHLIST_DATA_DIR` override is still respected.
- **Android:** install `MyMovieList-3.4.0-android-beta.1.apk` over the previous signed release. The application ID and signing certificate are retained, and `versionCode` increases to 3. Do not uninstall or clear app storage if you want to keep the phone's library.
- Windows and Android keep separate libraries; cloud sync is not included.
- The recommendation update requires no additional schema migration. The bilingual metadata-cache migration preserves existing movie IDs and personal fields.
- Android remains a beta pending physical-device testing. The `.apk` is the installable download; the `.aab` is for a future Google Play submission and is not installed directly.

See [QA results](QA_RESULTS.md) for verification and [Android build instructions](ANDROID.md) for package details.
