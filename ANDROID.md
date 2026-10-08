# Android — MyMovieList 3.5.0 beta.2

The app runs its library on the phone itself and works without a desktop computer. Android `3.5.0-android-beta.2` includes the same bilingual discovery, recommendations, optional accounts, profiles and automatic library sync as Windows v3.5.0.

## Library and accounts

- Guest data stays in the app's private `files/library/` directory. Each signed-in account has a separate SQLite library under `files/library/accounts/`.
- Accounts are optional. Signing in to an existing account opens that account's library; copying the guest library is a separate choice. The same account can sync personal film data between Windows and Android.
- Successful local edits wake the sync worker while the app process is running. Offline edits remain queued for a later connection. Android may stop the background process; this app does not promise continuous background sync when closed.
- Authentication sessions are encrypted with an app-scoped Android Keystore key. Private notes sync only within the owner's account; public showcases expose only the selected films and opted-in fields.
- Normal signed updates preserve storage. Uninstalling or clearing storage deletes local data. Android OS backup/device-transfer backup is disabled. Movie databases are not encrypted by the application.

The release ID remains `com.moviewatchlist`; its usual data path is `/data/user/0/com.moviewatchlist/files/library/`. Keep the existing signing key for updates.

New registration automatically copies the guest library into the account after a disclosure on the registration screen. Notes, ratings, favorites and original order are preserved; the guest copy stays on the device. This is included in the Windows v3.5.0 rebuild and Android `3.5.0-android-beta.2` packages; it requires no additional Supabase migration.

## Architecture

Chaquopy packages Python 3.12, Flask, SQLite and the shared application. WebView renders the interface through a loopback-only server protected by a random per-process native token and CSRF. External HTTPS links open in the phone's browser. File/content access and JavaScript-to-native interfaces remain disabled.

Shared source uses an explicit packaging allowlist, including the account/sync/name-policy modules, bundled avatars and public Supabase configuration. Personal libraries, exports, session files, SQL admin setup, credentials and signing material are excluded. The Supabase publishable key is public client configuration; no service-role key or TMDB developer token is bundled.

Saved information works offline. Discovery uses `https://api.myshelf.cloud`; remote posters and uncached content need internet. Native file-picker/download support for desktop-style backup import/export is not provided by this WebView wrapper; use account sync to transfer supported personal library data between platforms.

## Build requirements

- Android 7.0 / API 24+, a current Android System WebView and `arm64-v8a` or `x86_64`. 32-bit-only devices are not supported.
- Java 17, Python 3.12, Android SDK platform 36 and Build Tools 35.0.0.
- Pinned Gradle 8.13, AGP 8.13.2 and Chaquopy 17.0.0.

Set `JAVA_HOME` and `ANDROID_HOME`, or open `android/` in Android Studio. `CHAQUOPY_BUILD_PYTHON` can select the build interpreter.

## Build and downloads

From the repository root:

```powershell
.\scripts\build_android.ps1                   # Separate debug application
.\scripts\build_android.ps1 -Release -Clean   # Signed APK + AAB + lint
```

Release signing must already be configured in `android/keystore.properties`. Use `scripts/create_android_signing.ps1` only for the initial setup; never replace the signing key for an update. Back up `.android-signing/release.jks` and `android/keystore.properties` privately.

Artifacts are written to `dist/android/3.5.0-android-beta.2/`:

- `MyMovieList-3.5.0-android-beta.2.apk`: installable GitHub download.
- `MyMovieList-3.5.0-android-beta.2.aab`: future Google Play submission.
- `SHA256SUMS.txt`: package hashes.

`version.py` supplies the shared 3.5.0 version. Android uses `versionCode=6` and the beta suffix from `android/app/build.gradle`. Package filenames come from compiled APK metadata. The application ID and existing release signing certificate are retained.

The **Android packages** GitHub Actions workflow also supports debug and release builds. Release mode needs the four Android signing secrets from the same existing key. It builds artifacts without publishing a GitHub Release.

## Verification and deployment

Source tests cover native authentication, CSRF, library preservation and account/sync flows with synthetic data. Release checks verify APK signatures, alignment, AAB structure and packaged source/assets; results are recorded in [QA_RESULTS.md](QA_RESULTS.md).

Apply Supabase migrations 001–004 before announcing the complete account service. The public profile Worker is already separate from the phone app; see [cloud setup](supabase/README.md). No real user account or library is needed for package verification.

Android remains a beta until the actual APK is tested for installation/update, keyboard/insets, navigation, rotation, process restart, Keystore session restoration and cross-device sync. An AAB build does not publish or approve the application on Google Play; store setup, privacy disclosures and review are separate steps.

## Current build — October 8, 2026

The Android beta.2 rebuild includes automatic guest-library copying on new registration and uses `versionCode=6`. Package verification results are recorded in [QA_RESULTS.md](QA_RESULTS.md). Copies are collected beside the Windows ZIP in `dist/releases/v3.5.0/`. Physical-device testing remains pending. Hosted Supabase migration 004 is installed; this update needs no additional server migration.

## Previous build — October 7, 2026

Clean signed rebuild: `MyMovieList-3.4.0-android-beta.2.apk` and `.aab` in `dist/android/3.4.0-android-beta.2/`, with copies in `dist/releases/v3.4.0/`.

- The standalone APK keeps `com.moviewatchlist`, retains the previous release signing certificate, and raises `versionCode` from 3 to 4. Windows remains v3.4.0.
- Release lint passed with no errors and four existing warnings. APK v2 signature, 16 KB ZIP alignment, AAB structure and AAB signature verification passed.
- Both archives passed CRC checks, including the nested Python payloads. All 12 shared/bridge modules and 35 UI assets match the main source and clean-build intermediates; private data and signing files are excluded.
- ELF checks covered 138 native libraries per package, including the nested Python archives, with 16 KB or larger load-segment alignment.
- The build script supports `-Clean` and derives artifact filenames from the compiled APK metadata, preventing beta-revision naming mismatches.
- An installation failure was reported on a Xiaomi 14T Pro. The previous APK passed independent signature, metadata and alignment checks; no device was connected for installation testing. This rebuild is verified as a package, but resolving that phone's installation error still needs a device retry.

## Previous build — October 6, 2026

Signed `MyMovieList-3.4.0-android-beta.1.apk` and `.aab` were generated in `dist/android/3.4.0-android-beta.1/` from the main project. Both include the current bilingual interface, automatic metadata storage, Explore shelves and richer local recommendations.

- The release keeps `com.moviewatchlist`, uses the same signing certificate as 3.3.0 and raises `versionCode` to 3. Install the APK over the previous signed release to preserve its private library.
- Release lint completed with no errors and four warnings: an API 33 attribute ignored on older devices, an available Gradle update, an unused legacy icon and the existing square launcher-icon shape.
- APK signature, 16 KB ZIP alignment, AAB structure and AAB signature checks passed. Shared application and responsive UI checks are recorded in [QA results](QA_RESULTS.md).
- Archive inspection verified the current version, all shared modules, 35 matching UI assets, 16 KB native-library alignment and exclusion of personal data and private keys. Mobile browser checks passed at four phone widths; native-device testing remains separate.
- Copies of the APK and AAB are also collected with the Windows package in `dist/releases/v3.4.0/`, with combined SHA-256 checksums.
- Physical-device installation, keyboard/insets, lifecycle and update testing are still pending. These packages remain an Android beta; generating a signed AAB does not publish the app to Google Play.

## Previous build — October 5, 2026

Signed `MyMovieList-3.3.0-android-beta.1.apk` and `.aab` generated in `dist/android/3.3.0-android-beta.1/`. The APK uses the existing release signing certificate, retains `com.moviewatchlist`, and increments `versionCode` to 2. The new logo and shared discovery gateway are included. Signature and package alignment verified; physical-device testing is pending.
