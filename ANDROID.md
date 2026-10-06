# Android — standalone beta

The Android app runs the film library on the phone itself. It does not connect to a desktop computer or require a hosted MyMovieList server. Android `3.4.0-android-beta.1` shares the current language, discovery and recommendation features with Windows v3.4.0; each device keeps a separate library.

## Architecture

- `android/` contains a native Android activity and the build configuration.
- Chaquopy packages Python 3.12 with the existing Flask, SQLite, TMDB and recommendation modules.
- Android WebView renders the shared interface. A local server binds only to `127.0.0.1` on an available port; a random per-process token authenticates the native window before any library content is served.
- External HTTPS links open in the phone's browser. File/content access and JavaScript-to-native interfaces are disabled.
- Shared source files and assets are staged from an explicit allowlist during the build. Personal databases, API tokens, desktop packages and private keys are never part of that list.

## Library and privacy

Films and notes are stored in the app's private `files/library/` directory. They are independent of the Windows AppData library; there is no automatic synchronization or desktop import in this beta. A normal signed application update preserves this directory. Uninstalling the app or clearing its storage deletes it.

The release application ID is `com.moviewatchlist`. Its usual private data path is `/data/user/0/com.moviewatchlist/files/library/`. Builds with a different application ID have separate storage and do not automatically transfer their library.

Cloud backup and device-transfer backup are disabled for the private library. Local storage is not an application-level encrypted vault. Discovery and remote images require internet access; saved film information and downloaded posters remain available offline. Discovery uses the shared https://api.myshelf.cloud service. No personal TMDB account or token is required, and no developer credential is embedded in the APK.

## Requirements

- Android 7.0 / API 24 or newer, with a current Android System WebView.
- A 64-bit ARM phone (`arm64-v8a`) or an `x86_64` emulator. Older 32-bit-only devices are not supported by this Python 3.12 build.
- For building: Java 17, Python 3.12, Android SDK platform 36 and Build Tools 35.0.0. The Gradle wrapper pins Gradle 8.13; the project pins AGP 8.13.2 and Chaquopy 17.0.0.

Set `JAVA_HOME` and `ANDROID_HOME`, or configure the SDK location through Android Studio's local settings. Open the `android/` directory in Android Studio. `CHAQUOPY_BUILD_PYTHON` can select the build Python interpreter.

## Build a test APK

From the repository root on Windows:

```powershell
.\scripts\build_android.ps1
```

The debug APK has a separate application ID and is intended for development. It does not share its library with the release APK.

## Build a signed APK and Play bundle

Create the signing key once:

```powershell
.\scripts\create_android_signing.ps1
```

Keep secure backups of **both** `.android-signing/release.jks` and `android/keystore.properties`. They are ignored by Git and must never be uploaded to a release. Future direct APK updates must use the same key; generating a different key breaks the upgrade path.

Then build:

```powershell
.\scripts\build_android.ps1 -Release
```

Outputs are placed in `dist/android/3.4.0-android-beta.1/`:

- `.apk`: installable download for a GitHub prerelease.
- `.aab`: Android App Bundle for a future Google Play submission; it is not installed directly by users.
- `SHA256SUMS.txt`: checksums for the generated packages.

The version name is based on `version.py`; Android's independent, increasing `versionCode` is in `android/app/build.gradle`. Increment it for every published Android update.

## Build with GitHub Actions

After committing the Android sources, open **Actions → Android packages → Run workflow**. The default `debug` mode builds a test APK without a local Android SDK. Download the package from the workflow's artifacts; the workflow does not create or publish a GitHub Release.

For `release` mode, configure repository secrets `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS` and `ANDROID_KEY_PASSWORD` from the same private signing key used locally. Do not generate a new key for each workflow run. The workflow builds signed APK/AAB files and uploads only those packages.

## Verification and release scope

Build verification on October 3, 2026: signed release APK and AAB generated; APK v2 signature and 16 KB ZIP/ELF alignment verified; shared assets present and private data excluded. All 50 Python tests passed. Android release lint passed with two non-blocking warnings (the API 33 back-navigation attribute is ignored on older devices, and a newer Gradle version is available). The pinned toolchain remains compatible with this build.

Python tests cover native-session protection, blocked unauthenticated requests, CSRF, and data preservation. `tests/mobile.e2e.cjs` checks four phone widths, touch target sizes, equal card heights, suggestions, note saving and Undo with mocked TMDB responses. A reduced browser viewport approximates keyboard space; it is not an Android IME test.

Before promoting this beta to a stable phone release, test the actual APK on devices: first launch, TMDB search, adding films, notes and ratings, offline reading, back navigation, keyboard, rotation, background/process restart and installing an update without losing the library. Browser checks alone cannot establish that the native application works correctly.

Google Play publication is a separate step requiring your developer account, signing setup, privacy disclosures and store review. A successful APK/AAB build alone does not mean the app is ready or approved for the Play Store.

Technical references: [Chaquopy](https://chaquo.com/chaquopy/doc/current/android.html), [Android WebView](https://developer.android.com/develop/ui/views/layout/webapps/webview), [Android App Bundles](https://developer.android.com/guide/app-bundle).

## Latest build — October 6, 2026

Signed `MyMovieList-3.4.0-android-beta.1.apk` and `.aab` were generated in `dist/android/3.4.0-android-beta.1/` from the main project. Both include the current bilingual interface, automatic metadata storage, Explore shelves and richer local recommendations.

- The release keeps `com.moviewatchlist`, uses the same signing certificate as 3.3.0 and raises `versionCode` to 3. Install the APK over the previous signed release to preserve its private library.
- Release lint completed with no errors and four warnings: an API 33 attribute ignored on older devices, an available Gradle update, an unused legacy icon and the existing square launcher-icon shape.
- APK signature, 16 KB ZIP alignment, AAB structure and AAB signature checks passed. Shared application and responsive UI checks are recorded in [QA results](QA_RESULTS.md).
- Archive inspection verified the current version, all shared modules, 35 matching UI assets, 16 KB native-library alignment and exclusion of personal data and private keys. Mobile browser checks passed at four phone widths; native-device testing remains separate.
- Copies of the APK and AAB are also collected with the Windows package in `dist/releases/v3.4.0/`, with combined SHA-256 checksums.
- Physical-device installation, keyboard/insets, lifecycle and update testing are still pending. These packages remain an Android beta; generating a signed AAB does not publish the app to Google Play.

## Previous build — October 5, 2026

Signed `MyMovieList-3.3.0-android-beta.1.apk` and `.aab` generated in `dist/android/3.3.0-android-beta.1/`. The APK uses the existing release signing certificate, retains `com.moviewatchlist`, and increments `versionCode` to 2. The new logo and shared discovery gateway are included. Signature and package alignment verified; physical-device testing is pending.
