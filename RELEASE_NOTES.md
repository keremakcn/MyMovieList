# MyMovieList v3.6.0 — One Library, Web and App

## What's new

- **Web beta:** use [myshelf.cloud](https://myshelf.cloud) with the same account
  and private library as the Windows, Android and Mac apps. Save without an
  account, or sign in for automatic cloud sync across devices.
- **Time-aware sync:** independent field edits merge; newer trustworthy competing
  edits win even if an older edit uploads later. Offline changes remain queued,
  and earlier competing versions stay recoverable.
- **Better recommendations:** localized genre tags, more weight for suitable
  recognizable classics and bounded bonuses for recent films with familiar casts.
- **Richer details:** actor and director photo cards, with a silhouette when a
  photo is unavailable. Saved cast and bilingual details remain available offline.
- **Profiles and accounts:** fixed usernames, editable display names and 16
  bundled avatars. Optional showcases expose only selected films and opted-in
  ratings/counts; private notes and the rest of the library stay private.
- **Guest library preservation:** new registration copies local films into the
  account and keeps the guest copy. Existing-account login offers a separate
  copy action, keeping libraries from different accounts apart.

## Downloads and updating

- **Windows:** `MyMovieList-v3.6.0-windows.zip`. Extract and open
  `MyMovieList-v3.6.0.exe`. Close the old app before replacing it; the library
  remains in `%APPDATA%\MovieWatchlist`.
- **Android:** `MyMovieList-3.6.0-android-beta.1.apk`, versionCode 10. The existing
  application ID and signing certificate are retained. Install over the old
  app without uninstalling. The `.aab` is for Google Play submission.
- **macOS:** `MyMovieList-v3.6.0-macos-arm64-beta.dmg` or
  `MyMovieList-v3.6.0-macos-x86_64-beta.dmg`. Push the current source and run the
  macOS packages workflow to generate these native packages. Existing data stays
  in `~/Library/Application Support/MyMovieList`.

Accounts are optional. The hosted cloud service already has migrations 001–006;
existing users do not need API keys or manual server setup. Older native releases
remain compatible with legacy sync. Mac sources include trusted HTTPS
certificates; Mac betas are ad-hoc signed and not notarized by Apple.

## Validation

**546 full isolated Python tests passed.** Windows compiled source/assets
and packaged startup checks passed; Android APK/AAB signatures, payloads, metadata
and 16 KB alignment checks passed. Details are in [QA_RESULTS.md](QA_RESULTS.md). Android physical-device
installation/update and lifecycle testing remain separate; macOS 3.6.0 package
and real-Mac checks run after a fresh successful native workflow. No GitHub release
or Google Play submission is made by the local build scripts.
