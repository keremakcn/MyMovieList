# MyMovieList v3.5.1 — Profile & Connection Fixes

## What's fixed

- **Fixed usernames:** the profile editor no longer offers username entry, including while account status is loading. Your fixed `@username` appears on your profile separately from the editable display name. Confirmed usernames also reject rename attempts locally, even offline. Older accounts without a username can make their first choice in Account & sync.
- **Mac HTTPS:** Mac packages include a trusted CA certificate bundle for movie discovery and Supabase connections. The native workflow tests both services from the built app and mounted DMG with certificate verification enabled.
- **Android update:** clean signed APK/AAB packages include the latest shared profile controls. Android uses `3.5.1-android-beta.1` / versionCode 8 and retains the existing application ID and signing certificate.

## Downloads and updating

- Windows: `MyMovieList-v3.5.1-windows.zip`. Close the app before replacing the EXE; your library remains in `%APPDATA%\MovieWatchlist`.
- Android: install `MyMovieList-3.5.1-android-beta.1.apk` over the previous signed release to keep its local library. Do not uninstall first. The `.aab` is for Google Play submission, not direct installation.
- Mac: `MyMovieList-v3.5.1-macos-arm64-beta.dmg` or `MyMovieList-v3.5.1-macos-x86_64-beta.dmg`. These require a fresh successful **macOS packages** workflow after the source is pushed. Existing data remains in `~/Library/Application Support/MyMovieList`.

Accounts remain optional. Local films, notes, ratings and favorites are preserved. Existing cloud installations need no additional Supabase migration. Discovery, Social, bilingual support and automatic account sync remain available.

## Validation

All **497 source tests passed**. Release package checks are recorded in [QA results](QA_RESULTS.md). Android remains a beta pending physical-device update and lifecycle tests. Mac 3.5.1 native build and real-Mac testing are still required; Mac betas are ad-hoc signed and not notarized by Apple.
