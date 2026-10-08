# MyMovieList v3.5.0 — Your Library, Across Devices

Optional accounts and automatic cloud sync bring your personal movie library to Windows and Android while keeping offline use and private notes at the center.

## What's new

- **Optional accounts:** keep using the app without signing in, or create an account to sync your library across devices.
- **Automatic sync:** ratings, notes, favorites, watch status and personal dates save locally first. Pending edits retry when connected; sync can be paused. Conflicting edits preserve both versions for review.
- **Safer library separation:** account libraries stay separate from your original guest library. Copying a local library into an account is an explicit choice.
- **Step-by-step registration:** email → verification code → unique username → password. Regular sign-in uses email/password. Password recovery verifies its code before displaying the new-password screen.
- **Profiles and avatars:** a dedicated Profile page, editable display name and 16 bundled cat avatars. Only the avatar ID is synced, keeping profile data compact.
- **Unique profile addresses:** `myshelf.cloud/u/<username>`. Usernames are chosen once and cannot currently be changed; display names can repeat and remain editable.
- **Curated showcases:** choose and order up to six films. Public sharing starts off; ratings and library counts require their own choices. Only selected films are exposed. Notes, email, custom films and unselected library entries stay private.
- **Identity-name rules:** common abusive TR/EN names and numeric/separator variants are rejected. Personal movie notes are never filtered.
- **Updated Android packages:** the signed APK and Play bundle include the same accounts, profile and sync features as Windows, plus the existing bilingual discovery and recommendations.

## Upgrading

- **Windows:** close the old app and open `MyMovieList-v3.5.0.exe` from `MyMovieList-v3.5.0-windows.zip`. Your existing `%APPDATA%\MovieWatchlist` library is preserved.
- **Android:** install `MyMovieList-3.5.0-android-beta.1.apk` over the previous signed release. The package remains `com.moviewatchlist`, uses the existing signing certificate and increases `versionCode` to 5. Do not uninstall or clear storage to update.
- **Google Play:** use the `.aab` for a store submission; it is not the installable GitHub download. Android remains a beta pending physical-device lifecycle and upgrade testing.
- **Cloud service:** migrations 001–004 are required for the complete account service. Migration 004 must be applied in Supabase before announcing registration availability. See [cloud setup](supabase/README.md).

Movie discovery still requires no personal TMDB key. Saved library data remains available offline, and recommendation ranking stays on your device. See [QA results](QA_RESULTS.md) and [Android details](ANDROID.md).
