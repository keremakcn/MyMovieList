# MyMovieList v3.5.0 — Your Library, Across Devices

Optional accounts and automatic cloud sync bring your personal movie library across devices while keeping offline use and private notes at the center.

## What's new

- **Social discovery:** find public members by name or username, open chosen showcases directly in the app, and browse this week's dated watches from selected showcase films. Private notes and unselected films stay private. Personal ratings follow the owner's showcase option.
- **macOS beta:** separate Apple Silicon (`arm64`) and Intel (`x86_64`) builds include the shared Social interface and require macOS 15 or later. The current source bundles trusted HTTPS certificates to address reported discovery/account connection failures, and package verification now checks both services online. Refreshed DMGs require a new native build and actual-Mac testing. They use ad-hoc signatures and are not notarized by Apple. [Mac build details](MACOS.md).

- **Optional accounts:** keep using the app without signing in, or create an account to sync your library across devices.
- **Automatic sync:** ratings, notes, favorites, watch status and personal dates save locally first. Pending edits retry when connected; sync can be paused. Conflicting edits preserve both versions for review.
- **Keep your films when registering:** new registration automatically copies the device's guest library into the account after explaining this on screen. Notes, ratings, favorites and original added order are preserved; the original guest library stays intact. Signing in to an existing account keeps libraries separate and offers manual copying.
- **Step-by-step registration:** email → verification code → unique username → password. Regular sign-in uses email/password. Password recovery verifies its code before displaying the new-password screen.
- **Profiles and avatars:** a dedicated Profile page, editable display name and 16 bundled cat avatars. Only the avatar ID is synced, keeping profile data compact.
- **Unique profile addresses:** `myshelf.cloud/u/<username>`. Usernames are chosen once and cannot currently be changed; display names can repeat and remain editable.
- **Curated showcases:** choose and order up to six films. Public sharing starts off; ratings and library counts require their own choices. Only selected films are exposed. Notes, email, custom films and unselected library entries stay private.
- **Identity-name rules:** common abusive TR/EN names and numeric/separator variants are rejected. Personal movie notes are never filtered.
- **Updated Android packages:** the signed APK and Play bundle include the same accounts, profile and sync features as Windows, plus the existing bilingual discovery and recommendations.

## Upgrading

- **Windows:** close the old app and open `MyMovieList-v3.5.0.exe` from `MyMovieList-v3.5.0-windows.zip`. Your existing `%APPDATA%\MovieWatchlist` library is preserved.
- **macOS beta:** use the DMG matching your Mac, drag the app to Applications and keep `~/Library/Application Support/MyMovieList` when updating. See [Mac installation](MACOS.md) for the first-open security prompt.
- **Android:** install `MyMovieList-3.5.0-android-beta.3.apk` over the previous signed release. The package remains `com.moviewatchlist`, uses the existing signing certificate and increases `versionCode` to 7. Do not uninstall or clear storage to update.
- **Google Play:** use the `.aab` for a store submission; it is not the installable GitHub download. Android remains a beta pending physical-device lifecycle and upgrade testing.
- **Cloud service:** migrations 001–004 enable accounts and 005 enables Social. These are installed on the hosted service; new deployments must apply them in order. See [cloud setup](supabase/README.md).

Movie discovery still requires no personal TMDB key. Saved library data remains available offline, and recommendation ranking stays on your device. See [QA results](QA_RESULTS.md) and [Android details](ANDROID.md).

## Build verification — October 9, 2026

Windows EXE/ZIP and signed Android beta.3 APK/AAB were rebuilt from the current main source. All **480 source tests passed**. Packaged shared modules and UI assets match the source; the actual Windows EXE passed isolated startup, language/restart, account and Social checks. Android signature, archive, bundle and 16 KB alignment checks passed with the existing signing certificate. Shared version remains **3.5.0**; Android remains **beta.3 / versionCode 7**. Installation and lifecycle testing on a physical phone remains pending.

The subsequent Mac-only HTTPS correction passed **489 local source tests** and both real service probes in an isolated frozen diagnostic. Corrected ARM/Intel DMGs still need a fresh native workflow and testing on a Mac. The Windows and Android binaries retain their verified app code.
