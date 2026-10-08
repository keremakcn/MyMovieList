# MyMovieList for macOS — beta build preparation

The main repository now includes macOS data paths, native UI-language detection,
Keychain sessions and a manual GitHub Actions workflow for separate Apple Silicon
and Intel DMGs. The shared version remains **3.5.0**. Social discovery is included in the
shared modules, templates and bundled translations used by the Mac build.
Supabase migration 005 is installed on the hosted service. Windows and Android
packages are rebuilt separately.

**Status — October 9, 2026:** after the launcher-test fix, both native jobs
passed source validation. Run `37844056782` then stopped during packaging:
PyInstaller resolved relative asset paths from `build/macos/<arch>`, where
the generated spec lives, instead of the project root. The builder now uses
absolute project paths for templates, static assets, public cloud configuration
and the launcher; bundle destinations remain unchanged.

The exact missing-template failure was reproduced for both architectures using
PyInstaller's own command parser and data resolver. Those checks now pass,
alongside the existing launcher/Mac checks: **34 passed**. Native icon generation,
signing and DMG creation still require another hosted run. Push this correction
and start **Run workflow on main**; rerunning an old run uses its old commit.
No successful DMG or physical-Mac compatibility is claimed until native checks
and manual tests pass. Windows and Android packages need no rebuild for this fix.

## Requirements

- First beta target: **macOS 15 or later**.
- Apple Silicon: `arm64`, including M-series Macs. Intel: `x86_64`.
- Build on a Mac or a GitHub-hosted macOS runner, with Python 3.12.
- An Apple Developer membership is not required for these ad-hoc signed test
  builds. They have no Developer ID identity and are not notarized by Apple.

## Build from Windows through GitHub

1. Commit/push the updated project, including `.github/workflows/macos.yml`, to
   the repository's default branch. Do not upload local libraries or credentials.
2. Open the repository on GitHub and select **Actions → macOS packages**.
3. Select **Run workflow → main → Run workflow** (or the actual default branch).
4. The `macos-15` job builds Apple Silicon; `macos-15-intel` builds Intel.
5. Both jobs run all source tests, upload a per-architecture test report even
   if tests fail, generate the current logo's `.icns`, build the `.app`,
   verify the native package and assemble a DMG.
6. Download the two job artifacts after successful completion. Each artifact ZIP
   contains a DMG, its SHA-256 checksum and verification report.
7. Test on actual Macs, then attach the **DMG files themselves** and their
   checksums to the GitHub Release. Artifact ZIPs are transport wrappers.

Expected names:

- `MyMovieList-v3.5.0-macos-arm64-beta.dmg`
- `MyMovieList-v3.5.0-macos-x86_64-beta.dmg`

The workflow only uploads build artifacts. It does not publish a release or need
Apple credentials, repository write access, or a Supabase service-role key.
Standard GitHub-hosted runners are free for public repositories; private
repositories use the account's Actions allowance and applicable billing.

## Build on a Mac locally

From the repository root, with Python 3.12 installed:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-macos.txt
.venv/bin/python scripts/build_macos.py --arch arm64
```

On an Intel Mac, replace `arm64` with `x86_64`. Native builds are required; the
script rejects a mismatched interpreter architecture. It uses macOS's `sips`,
`iconutil`, `codesign`, `hdiutil`, `ditto` and `lipo` tools. A one-folder `.app`
bundle preserves native libraries and symlinks; no one-file unpacking is needed.

Outputs go to `dist/macos/v3.5.0/`. Build intermediates stay under
`build/macos/<architecture>/`. Both directories are ignored by Git.

## Install and update

1. Download the DMG for your Mac's processor and open it.
2. Drag **MyMovieList.app** to **Applications**.
3. Open the installed app. If macOS blocks the unidentified developer, try
   **System Settings → Privacy & Security → Open Anyway** after attempting to open
   it, if that option is offered. Follow Apple's instructions for software you
   trust; managed computers may prevent this exception.
4. To update, quit MyMovieList and replace the application in Applications.
   Keep its data directory; replacing the app does not reset the library.

These packages use PyInstaller's local ad-hoc signature, not Apple's Developer ID.
The build verifies the signature for integrity but does not claim Gatekeeper
acceptance. A notarized release can be added later with Developer ID signing.
The workflow does not disable Gatekeeper or remove quarantine attributes.

## Data, accounts and language

- Installed data: `~/Library/Application Support/MyMovieList/`.
- Guest library: `movies.db`; account libraries: `accounts/<user-id>/library.db`.
- `MOVIE_WATCHLIST_DATA_DIR` still selects an explicit custom or QA location.
  Source development retains its existing repository-local data behavior.
- Sessions are generic-password items in the user's macOS **Keychain**, under
  `cloud.myshelf.mymovielist.session`. A hash of the canonical data directory
  separates installed, development and test sessions. No token is passed on a
  command line or written to a plaintext fallback file. No passwords are saved.
- Locked, denied or unreadable Keychain access requires signing in again; saved
  libraries remain intact. Failed session writes do not replace in-memory state.
  macOS may request permission for Keychain access, including after an update.
- Windows keeps its established AppData folder and DPAPI sessions. Android keeps
  its private storage and Keystore sessions. Both use the same cloud account.
- First launch uses macOS's preferred UI language, selecting Turkish or English
  fallback. A saved language choice wins on later launches. Movie IDs and personal
  data are unaffected. Search/undo use **Cmd+K / Cmd+Z** on Mac.
- Discovery and private sync use the existing Cloudflare/Supabase services.
  No additional database migration or server deployment is needed.

## What the native workflow verifies

- Shared version, bundle identity, minimum OS and icon.
- All shared Python modules and the launcher match the source; static/template
  files and the public cloud configuration match byte for byte.
- Native binaries have the selected architecture; nested signatures verify.
- Private databases, session files, signing material and QA sources are absent.
- The real packaged executable imports Cocoa, starts its loopback server, loads
  its library, switches EN/TR, preserves movie fields and remembers the language.
  It checks the Social route's translated offline setup state without requiring
  a cloud connection.
- A synthetic session survives reopening through the actual Keychain backend and
  is removed on logout. Test libraries and Keychain identifiers are isolated.
- The delivered DMG is mounted read-only and checked again, preserving `.app`
  symlinks and signatures. Checksums cover the exact downloadable DMG.

These checks require macOS and will run in Actions. They do not replace graphical
window and physical-device tests. Before publishing, check first opening from a
downloaded DMG, keyboard/focus, resizing, external links, backup import/export,
real sign-in, restarting, offline edits and cross-device sync.

## References

- [GitHub: manually run a workflow](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)
- [GitHub: hosted Mac runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [Apple: open downloaded apps](https://support.apple.com/en-us/102445)
- [PyInstaller: Mac bundles](https://pyinstaller.org/en/stable/usage.html#building-macos-app-bundles)
- [Keyring: explicit macOS Keychain backend](https://keyring.readthedocs.io/en/stable/)
