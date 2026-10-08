# macOS CI launcher-test correction — 2026-10-08

- The first hosted ARM/Intel workflow stopped in source validation before
  PyInstaller or DMG creation. The supplied ARM log reports **2 failed,
  475 passed, 1 skipped**. Both failures were launcher-library tests; installation
  steps succeeded.
- Those tests globally changed sys.platform to win32. Mac Python's ssl module
  then tried to call its unavailable Windows enum_certificates function. The
  exact NameError was reproduced in an isolated Windows diagnostic process
  with a Mac flag and no Windows certificate enumerator.
- Launcher tests now preserve the real interpreter platform and use an isolated
  home to cover the runner's native installed folder and explicit data override.
  Existing-library fields and native startup/shutdown assertions are retained.
  No test is skipped to bypass the problem; production TLS checks are unchanged.
- **32 launcher/Mac checks passed** under that reproducer after the fix.
  The complete Windows suite passed **478 tests** with isolated libraries.
- The workflow uses current checkout/setup-python v7 actions, retains all tests
  and read-only repository permissions, disables persistent checkout credentials,
  and uploads JUnit reports after successful or failed source validation.
  Workflow YAML and targeted test lint pass.
- Only tests, CI and these documents changed. Shared version remains **3.5.0**.
  Windows and Android downloads require no rebuild for this correction.
  The corrected workflow must still be uploaded and run on both native Macs;
  successful DMGs and physical-device tests remain pending.

# Current Windows and Android packages — 2026-10-08

- Rebuilt from the authoritative **Desktop/movie-watchlist** source, including
  Social, public showcases, accounts and automatic sync. Shared version is
  **3.5.0**; Android is **3.5.0-android-beta.3**, versionCode **7**, application ID
  **com.moviewatchlist**. The existing Desktop EXE was updated as well.
- **478 isolated Python tests passed**, including 44 Social and 30 Mac-source
  cases. Targeted lint passed. Temporary test libraries and synthetic credentials
  were used; personal AppData and signing materials were not changed.
- Windows package verification matched the compiled code for **27 shared
  modules**, all **69 UI assets**, and the public cloud configuration to main
  source. The ZIP contains the matching EXE and current release notes.
- The real rebuilt Windows EXE passed isolated startup, EN/TR switching and
  restart persistence, offline saved cast/synopses, preservation of personal
  movie fields, registration disclosure and Social routes in both languages.
- Clean signed Android APK and AAB builds passed archive CRC, all **27**
  shared/bridge bytecode provenance checks through the build intermediates and
  all **69** UI asset hashes. The signing certificate matches beta.2, allowing
  upgrades without replacing the application identity.
- APK v2 signature and 16 KB ZIP alignment, AAB signature, bundle structure,
  manifest/version and requested 16 KB page alignment checks passed. Native ELF
  inspection passed for **138 libraries / 408 load segments** per package.
  Release lint reported **0 errors and 4 existing warnings**.
- Final release copies and SHA-256 checksums match the verified build outputs.
  Previous download copies were preserved in the ignored QA backup directory.
  Current release assets are the Windows ZIP, Android beta.3 APK and beta.3 AAB.
- EN/TR README screenshots include Social with fictional showcase members.
  Earlier browser QA below covers 24 checks at 320, 390, 768 and 1365 pixels.
- No phone was connected, so physical Android installation/runtime tests remain
  pending. macOS sources, module verification and bilingual offline Social smoke
  checks are current; **no Mac workflow or DMG build was run**. Native Mac,
  graphical-window and hosted two-owner release rehearsals remain pending.

# Earlier Social source preparation — 2026-10-08

- Shared version remains **3.5.0**. Added in-app People and This week views,
  member search, cursor pagination, profile/film navigation, loading and clear
  setup/offline/empty states. No posting features or full-history sharing.
- **477 isolated Python tests passed**, including 44 Social cases. A final
  focused check of Social and Mac preparation passed **73 tests** after the
  final UI copy updates. Guest libraries, private notes, ratings, favorites,
  order, account ownership and the existing public-profile contract are covered.
- All three PostgreSQL/PGlite contract scripts passed. Migrations 001–005 are
  exercised with synthetic owners, including privacy/direct-access denial,
  moderated legacy names, only chosen and dated watches, optional ratings,
  literal search, bounded multi-page results, safe week rollover, revocation,
  RLS/grant preservation and migration replay. No live admin SQL was executed.
- Edge browser QA passed **24 checks with 19 screenshots** and no script errors.
  English/Turkish People and weekly views fit 320, 390, 768 and 1365 pixels.
  Verified five mobile nav targets, long names, keyboard search/focus, single
  submit/loading announcement, pagination, back navigation, profile visits,
  owned/unowned movie details and setup/offline/empty states. Fixtures contain
  fictional members and disposable SQLite files; real AppData was not used.
- New/changed feature modules, Mac verifier and tests pass targeted Ruff;
  JavaScript syntax checks pass. Existing local-calendar date validation in
  app.py is intentionally retained (its pre-existing DTZ warnings are excluded
  from that file's targeted lint).
- Android's source allowlist and the Mac verifier include all new shared modules.
  **No Windows, Android or Mac native packages were rebuilt in this update.**
  Existing download archives contain the earlier 3.5.0 implementation.
- The user applied migration 005 successfully on October 8. Both hosted Social
  views passed anonymous protocol-1 probes with empty results.
  No admin SQL was executed by this source update. A hosted opted-in/private
  owner rehearsal and native-device testing remain pending; local tests do not
  replace them. Main-install verification: **112 focused tests passed**; all
  **217 prepared public source/asset files** match the installed main project.

# macOS source preparation — 2026-10-08

- Shared version remains **3.5.0**. The manual `macOS packages` workflow targets
  macOS 15+ with separate native Apple Silicon (`arm64`) and Intel (`x86_64`) jobs.
  It creates ad-hoc signed beta DMGs, checksums and verification reports; it does
  not publish releases or require Apple Developer credentials.
- **433 isolated Python tests passed** on Windows, including 29 new Mac cases.
  These cover installed/source data paths, explicit data overrides, retained
  movie fields, secure-session reopen/logout, separate data-folder namespaces,
  locked/missing/unavailable Keychain services, rejected malformed/oversized
  sessions, redacted SDK errors, Android precedence, native language preference
  and fallback, platform shortcut labels and safe native-test preconditions.
- Changed modules, Mac packaging scripts and tests pass targeted Ruff. The
  workflow YAML, manual trigger, runner matrix and read-only permissions parse
  correctly. The complete suite also retains native Windows DPAPI checks and
  existing account, onboarding, sync, recommendation and discovery coverage.
- Installed Mac libraries use `~/Library/Application Support/MyMovieList`; cloud
  sessions use the explicit Apple Keychain backend without a plaintext fallback.
  Existing Windows and Android storage and session protection remain intact.
- Native build verification checks compiled modules, UI/configuration hashes,
  binary architecture, nested signatures, private-file exclusion and the actual
  executable's isolated loopback/Keychain/language/data behavior. It mounts and
  rechecks the delivered DMG before uploading artifacts. The current logo is
  converted to ICNS during the native build.
- **No native Mac build or graphical/physical-Mac test has run yet. No DMG is
  available from this Windows preparation.** These are pending Actions and
  actual-device checks documented in `MACOS.md`. Automated synthetic Keychain
  checks do not replace real sign-in, window, download or cross-device testing.
- QA uses temporary libraries and synthetic credentials. No personal AppData
  library, account or signing key was used. No new Supabase migration is needed.
  Existing Windows/Android download packages are unchanged by this preparation;
  their earlier validation is recorded below.

# Earlier Windows and Android packages — 2026-10-08

- Rebuilt from the authoritative `Desktop/movie-watchlist` source after the
  automatic guest-library-copy update. Shared version remains **3.5.0**; Android
  is **3.5.0-android-beta.2**, `versionCode=6`, package `com.moviewatchlist`.
- **14 onboarding-copy regression tests passed again** against the main source.
  The earlier complete 404-test run and 40 browser-view checks remain recorded
  below; this packaging update does not change their runtime implementation.
- Windows package verification compares compiled code for all 23 shared Python
  modules against main source, all 66 UI assets and public cloud configuration.
  The ZIP contains only the matching EXE and current release notes.
- The actual rebuilt Windows EXE passed isolated-library startup, TR/EN language
  switching, restart persistence, offline movie details/full cast, unchanged
  personal film fields, and registration disclosure before email submission.
  One initial launch in the restricted test environment failed before startup;
  rerunning under normal Windows permissions passed. User AppData was not used.
- Clean signed Android APK and AAB builds passed archive CRC, all 24 shared/bridge
  bytecode checks and 66 asset hashes. Both contain the guest-library-copy update.
  The upgrade certificate matches the previous APK; APK v2 signing and 16 KB ZIP
  alignment, AAB signing, bundle structure and manifest/version checks passed.
- Native ELF inspection passed for 138 libraries and 408 load segments per
  package. Release lint has no errors and four existing warnings. No connected
  phone was available, so installation/runtime and native lifecycle remain
  unverified on a physical device.
- The release folder contains the Windows ZIP, Android beta.2 APK/AAB and combined
  SHA-256 checksums. The desktop EXE copy was updated. Previous packages were
  backed up; earlier Android outputs remain available. No signing key was replaced.
- Hosted migrations 001–004 are already installed; no new Supabase migration
  is required by this library-copy update. Earlier source-only/package-pending
  notes below record the state before this rebuild.

# New registration keeps the local library — 2026-10-08

- New accounts automatically receive the guest library after disclosure before
  email submission and password completion. Existing-account sign-in and password
  recovery do not copy guest data. Manual copying shares the same transaction.
- **404 isolated Python tests passed**, including 14 onboarding-copy scenarios:
  empty/20-film libraries, notes/ratings/favorites/watch dates/original order,
  offline details, unknown legacy dates, deletion markers, retry/replayed forms,
  source edits during copying, target rollback, lost completion responses,
  session-save failures, account switching and duplicate/conflicting records.
- Personal data and available catalog details use one source read snapshot and
  one target write transaction. Original libraries remain intact. Existing
  account personal fields are retained; server conflicts keep both versions for
  review and retain the server's first-add date/order.
- **40 EN/TR browser views passed** at 320/390/768/1365px: the complete registration
  flow, disclosure on email/password screens, Enter navigation, 20 preserved
  guest films and 20 account films queued for sync, without horizontal overflow,
  nested forms or script errors. Turkish phone screenshots were visually reviewed.
- Changed runtime modules and tests pass targeted Ruff. QA used fictional
  accounts, local fixtures and temporary databases; no real account was created
  and no personal AppData library was used for these automated tests.
- No additional Supabase SQL migration is required. The shared source applies
  to Windows and Android; **existing 3.5.0 EXE/APK/AAB packages were not rebuilt**
  for this follow-up. Previous package checks below describe the earlier builds.

# Hosted registration setup completed — 2026-10-08

- After the user ran migration 004, the anonymous live setup probe returned
  `registration_setup_ready: true` with the expected username protocol 2.
  It created no accounts and accessed no private library records.
- Windows 3.5.0 and Android 3.5.0 beta.1 already contain the corresponding
  registration, immutable-username, name-policy, profile and automatic-sync code.
  Applying this server migration does not require rebuilding the downloads.
- Earlier SQL-pending statements below record the state before this follow-up.
  Complete real email-first registration and physical-device lifecycle testing
  remain separate from this read-only setup verification.

# Registration usernames and name policy — 2026-10-08

- Usernames remain fixed after their first successful claim, as requested. The
  profile editor exposes a read-only handle; display name and avatar stay editable.
  There is no rename RPC, username revision or alias registry in migration 004.
- Signup is email → verification code → unique username → password → optional
  profile details. Existing confirmed accounts cannot change passwords through
  signup; recovery retains its own verified-code flow.
- **386 isolated Python tests passed**, including forbidden/taken names, expired
  and cross-purpose steps, response-loss recovery, simultaneous form submissions,
  immutable claims, setup failures before email delivery, redacted policy errors
  and prevention of guest-cache contamination at account acceptance.
- PostgreSQL/PGlite contract checks passed for migrations 001/002/003/004. Direct
  RPC calls cannot bypass the name policy; canonical ownership remains unique,
  legacy invalid names are suppressed publicly without deletion, and privacy
  revocation/safe migration replay work. This does not prove hosted multi-session
  concurrency.
- **64 EN/TR browser views passed** at 320/390/768/1365px: the complete signup
  flow, forbidden/taken-name errors, Enter navigation, fixed-handle profile screen
  and editable display names, with no overflow, nested forms or script errors.
  Turkish phone screenshots were visually reviewed.
- Changed runtime modules and the new tests pass Ruff; JavaScript syntax passes.
  A broader lint scan found existing findings outside this update; no repository-
  wide lint-clean claim is made. No personal library was used for QA.
- Hosted 003 is installed. **004 still requires SQL Editor execution**. New
  registration checks its availability before sending email; existing sign-in,
  recovery and private library sync remain available. No real username was
  claimed and no showcase was published on a user's behalf. No binary was built.
- Twenty source/documentation files were transferred with verified backups and
  matching SHA256 hashes. On the authoritative Desktop/movie-watchlist source,
  **62 username/registration tests** and targeted Ruff passed again. Eight
  read-only views of the real isolated preview passed with sharing preserved and
  no script errors. An anonymous hosted probe confirmed 004 is not installed yet.

# Unique usernames and profile addresses — 2026-10-08

- Main source now separates a canonical username from a non-unique display
  name. The public address is `https://myshelf.cloud/u/<username>`; existing
  share UUID links continue to work. Choosing a username never publishes a
  profile. Private profiles continue to hide identity from anonymous readers.
- The full isolated Python suite passed: **346 tests**. After adding protection
  against a late background null status erasing a foreground username claim,
  all **23 username tests** and lint checks passed. Coverage includes duplicate
  display names, case-insensitive handles, reserved/invalid names, idempotence,
  per-account cache isolation, paused sync, setup/offline errors, public visits,
  revocation and legacy links.
- PostgreSQL/PGlite contract checks passed for migrations 001/002/003, including
  unique owner/name constraints, canonical claims, privilege denial, duplicate
  display names, strict private projection, stable old RPCs and safe reruns.
  This isolated contract does not prove hosted multi-connection behavior.
- **12 Worker tests** passed: fixed anonymous username/UUID lookup, response
  identity checks, privacy, bounded responses, gateway fallback, request limits,
  no open proxy or source exposure, and `/u/*` asset routing.
- **56 EN/TR browser views** passed at 320/390/768/1365px with isolated fake
  accounts. Actual form flow: choose canonical username → save display name →
  consented publication → named visitor page. No overflow, nested forms or
  script errors. Phone screenshots were visually reviewed.
- Updated Worker deployed with `myshelf.cloud/u/*` and the existing profile
  Custom Domain. Root-domain shell/script/style and the existing live UUID
  shell returned HTTP 200/no-store. Eight read-only main-source views passed.
- Hosted migration **003 was subsequently applied and RPC availability verified**. No real
  username was claimed or profile automatically published for QA. Native
  Windows/Android builds and a hosted two-account simultaneous claim rehearsal
  remain release checks. No APK/EXE was rebuilt in this change.

# Optional public showcases — 2026-10-08

- Public consent is separate from private Auth metadata. Profiles remain private
  by default. Anonymous projection exposes only identity, ordered TMDB picks and
  explicitly enabled ratings/counts. Notes, email, custom films and unselected
  film IDs are excluded. Public share UUID differs from account UUID.
- The 322-test Python regression suite passed with isolated databases, followed
  by 62 final cloud/sharing tests including duplicate publication and paused
  visibility refresh. New coverage checks consent,
  automatic edits, pending publication follow-ups, durable offline revocation
  while sync is paused, stale-device privacy protection, unavailable setup,
  guest visitor rendering and strict rejection of private/invalid fields.
- Isolated PGlite/PostgreSQL showcase migration tests passed: owner/anonymous
  privileges, private library and sharing-table denial, two-user separation,
  ordered picks, flags, deletion/Undo, stale writes, idempotency and safe rerun.
- Nine Worker tests passed: fixed anonymous RPC, no client JWT forwarding, strict
  DTO, visibility re-read/no-store, limits, closed arbitrary-proxy paths,
  malformed/oversized responses, provider errors and catalog fallback.
- 80 EN/TR headless Edge views passed at 320/390/768/1365px: owner and public
  pages, consent/publish/link/visitor/revoke flows, private/error/empty/offline/
  setup/paused states, no horizontal overflow and zero browser script errors.
  Desktop and phone screenshots were visually inspected using synthetic art.
- Separate `myshelf-profiles` Worker deployed at `profiles.myshelf.cloud`.
  Root HTML returned HTTP 200/no-store. After the user applied migration 002,
  a random profile probe returned HTTP 404/no-store with only `found:false`.
  Direct anonymous projection returned HTTP 200, while private library reads
  (zero rows requested), owner status and write RPCs returned HTTP 401/42501.
  Authenticated preview sharing status was checked/private with no setup error.
  The owner subsequently enabled sharing through the UI. A separate signed-out
  browser and HTTP probe read the empty public projection with HTTP 200/no-store;
  390/1365px live views had no overflow or script errors. Live chosen-film
  metadata hydration still needs a populated showcase rehearsal.
  Eight main-source desktop/mobile views passed without script errors.
  No real profile was published or personal AppData library opened for QA.
- Hosted two-owner sharing and multi-connection concurrency verification remain
  release QA requirements. All 48 initially transferred files were SHA256 checked;
  follow-up fixes and documentation were also copied with backups/hash checks.
  Existing Windows/Android packages were not rebuilt for this source update.

# Curated private profile showcase — 2026-10-08

- The default Profile tab is now My showcase. It starts empty and shows only the owner's explicit, ordered selection of up to six library films. Picks are independent of favorites; rating badges and library counts are off until enabled. Automatic favorites/recent watches and filter shortcuts remain in the separate owner-only Personal overview tab.
- The editor searches the local library in pages of 20 with cached localized titles, a 250 ms debounce, request cancellation and stale-response protection. Keyboard selection, move/remove controls, a six-film cap, loading/empty/error/retry feedback and a discard guard are implemented. The save bar stays visible above phone navigation while scrolling.
- The profile's private Auth metadata stores stable record keys and two boolean display preferences. Identity/showcase partial saves merge inside a SQLite write transaction. Invalid, duplicate, excessive or newly foreign-library picks are rejected. Existing unavailable picks can be retained or removed; rendering resolves only the active owner's local rows, and deletion/Undo hides/restores a pick in the same position. No notes, posters or descriptions are added to profile metadata. No hosted schema, RLS or public sharing permission was changed.
- 308 full Python regression tests and 50 focused profile/account tests passed in the source staging copy. New coverage checks private empty defaults, optional fields, explicit order, favorite independence, deletion/Undo, validation rollback, account/guest/stale-scope isolation, bounded literal/localized search, concurrent partial writes, metadata recovery, offline persistence and restoration on a second device with different numeric movie IDs. No real account or personal AppData library was mutated by these tests.
- 80 final isolated Edge views passed in EN/TR at 320/390/768/1365 px, covering empty/populated/long-name/offline/paused profiles, optional information, private overview and editors. Interaction checks verify keyboard add, reorder/remove, pagination, search/empty/error/retry, cap, discard cancellation, save/reopen, stale-request cancellation and film navigation. No overflow, unlabeled fields, short tested controls or script errors. A separate 16-position check confirms the sticky save button remains visible and clickable across four widths and four scroll positions. Desktop and phone screenshots were visually reviewed; sample poster art exists only in QA.
- Changed Python lint/format and JavaScript syntax checks passed, with the pre-existing calendar-date DTZ finding excluded. English/Turkish READMEs and the cloud design document describe the selected showcase and distinguish it from future public sharing. No desktop or Android build was performed.

# Private profile showcase — 2026-10-08

- Profile now leads with the account avatar/name, a private badge and a separate edit action. Four compact counters open the corresponding library filters. Favorite posters and dated recent watches show at most six films each; without saved watch dates, the second shelf shows recent additions.
- The shelves use only the selected local library and cached catalog translations; removed films are excluded, Undo restores them, personal notes are not selected, and profile viewing makes no hosted catalog request. No schema or public cloud permissions changed.
- Name/avatar editing lives on its own screen, with keyboard radio selection, live avatar preview, local-first saves, validation that retains the draft and an unsaved-change guard. Account/email, sync pause/resume, guest-library copying, conflict resolution and security actions live under Settings → Account & sync. Import/export remains in Settings.
- 288 full regression tests passed against the transferred main source, after 287 staging regression and 30 focused account/profile tests during implementation. New coverage verifies shelf limits, account/guest isolation, deletion/Undo, date ordering/fallback, offline reads, safe translated identity, separate editing/settings and preserved conflict review. Ruff lint/format passed for changed Python files, excluding existing calendar-date DTZ findings.
- 72 isolated Edge browser views passed in English/Turkish at 320/390/768/1365px: populated/empty/long-name/offline/paused/undated profiles, editor and account settings. Verified keyboard edit/avatar/save, discard cancellation, film-detail navigation, sync pause/resume, image fallback, four-item phone navigation, no page overflow and zero script errors. Desktop, phone, empty and edit screenshots were visually reviewed; sample artwork exists only in the QA fixture.
- Nineteen changed source/documentation files were transferred to the authoritative Desktop/movie-watchlist project with optimistic hash checks, backups and SHA256 verification. The main-source preview passed read-only profile/editor/settings/signup/phone checks; its existing test account/library was preserved. Public sharing remains unimplemented and private by default. No personal AppData library, desktop binary or Android package was changed by the design work.

# Private profile overview and sidebar — 2026-10-08

- Desktop/tablet sidebar adds Profile between For you and Settings, with its own active state. Phone navigation keeps four items; account access stays in the header.
- Profile shows total, watched, favorite and want-to-watch counts. Each is a keyboard-accessible shortcut to the corresponding library filter. The same SQLite summary query serves Library and Profile; removed films are excluded and Undo restores their contribution.
- Counts use only the selected account's local library. No additional statistics, favorite IDs or notes are sent to the cloud by this change, and no public profile endpoint is enabled.
- 91 focused account/cloud/application tests passed. Added coverage checks owner separation, guest exclusion, empty accounts, removal/Undo counts, rating averages and filter links/active navigation. Ruff passed with unchanged calendar-date DTZ findings excluded.
- 24 isolated headless Edge views passed in English/Turkish at 320/390/768/1365px: correct counters, profile selection, filtered-library navigation, four-item phone bar, no horizontal overflow and no script errors. Turkish phone profile visually reviewed.
- Public sharing remains a documented proposal in CLOUD_SYNC_DESIGN.md. A separate sharing table, field-specific consent, permission tests and hosted migration are needed before users can visit one another's profiles. No personal library or public cloud permissions were changed; no app build was performed.

# Hosted SQL preliminary verification — 2026-10-07

The user applied the SQL migration and shared `Success. No rows returned.`.
Live checks returned HTTP 200 for Auth health and protocol status
(`mymovielist-sync`, protocol 1). Anonymous library-table and download-RPC access
were rejected with HTTP 401 / SQLSTATE 42501. The table probe requested zero rows;
no personal records were read or written and no Auth users/emails were created.

This verifies public service readiness and anonymous denial only. Authenticated
two-user isolation, email delivery, concurrent transactions and native devices
still require verification. `accounts_enabled` remains false; no packages were built.
The staging/SQL-pending statements below describe the earlier local verification.

---

# Optional cloud integration — 2026-10-07

Prepared in a source-only staging copy and verified with synthetic data. The
personal AppData library was not opened, migrated or uploaded. Cloud accounts
remain disabled in `supabase/project.json`; the hosted SQL setup is still pending.

- **250 Python tests passed**, including all existing application regressions and
  **38 cloud tests**, after the final validation/configuration changes.
- Schema-3/v4 backup and migration checks retain original fields, null legacy
  dates, stable identities and order. Personal writes and queued changes roll
  back together if interrupted.
- Synthetic two-device checks cover personal restoration, offline placeholders,
  public catalog hydration without uploads, independent edits, competing notes,
  deletion/Undo and retained order. Conflicting versions survive resolution and
  neutral JSON export/import.
- Restart/frozen-operation retries, timeout after commit, service limits, offline
  usage, explicit sync consent, account switching and stale page/CSRF isolation
  passed. A delayed refresh cannot block local reads or revive a signed-out session.
- HTTPS adapter checks cover authenticated RPC headers, refused redirects,
  redacted errors, retry bounds and malformed/oversized responses. Tokens and
  passwords are absent from rendered pages and personal exports.
- Windows DPAPI session round-trip/clear tests passed; saved sessions are sealed,
  and failed writes do not replace the previous session.
- Isolated PGlite PostgreSQL checks passed: two-owner RLS, anonymous/direct-write
  denial, RPC ownership, idempotent retries, conflict revisions, tombstones/Undo,
  immutable addition fields, validation, pagination and safe migration reruns.
- **42 responsive account views passed**: setup, sign-in/up, verification,
  recovery/reset and signed-in conflict screens in EN/TR at 320, 390 and 1365 px.
  No horizontal overflow, unlabeled inputs, exposed tokens or browser errors.
  Enabled account buttons provide at least 44 px of touch height. Desktop/phone
  screenshots were inspected. This is browser QA, not an Android device test.
- New cloud-module lint, changed existing-module E9/F checks, account-template
  lint and application JavaScript syntax checks passed. Runtime dependencies are
  unchanged. Windows/Android packaging source includes only the public project
  configuration and shared modules; private data remains excluded.

**Not yet verified:** hosted migration/grants/RLS, real Auth/email delivery,
multi-connection PostgreSQL concurrency, Android Keystore/device lifecycle and
new native packages. No desktop/Android build or cloud deployment was performed.
These checks are required before enabling public accounts. Historical package
checks below describe existing downloads, not the new cloud source.

---

# Android clean rebuild — 2026-10-07

- Clean release build completed in the main `Desktop/movie-watchlist` project: signed APK and AAB for `3.4.0-android-beta.2`, Android `versionCode=4`, unchanged `com.moviewatchlist` identity and release signing certificate. Windows remains v3.4.0.
- APK metadata confirms Android API 24 minimum, API 36 target and ARM64/x86_64 support. This is a single standalone APK, with no split filters.
- APK v2 signature and 16 KB ZIP alignment passed. The certificate matches the previous 3.3.0 and 3.4.0 beta.1 releases. Bundletool structure validation and AAB JAR signature verification passed.
- Both ZIP packages and their eight nested Python archives passed CRC checks. Each package contains 12 matching shared/bridge modules and 35 UI assets. Python verification follows main/staged/build source hashes to packaged bytecode; UI assets are compared directly to main source.
- Each package passed ELF checks for 138 native libraries and 408 load segments, including the nested Python archives, at 16 KB or greater. Personal databases, environment files and private signing material are excluded.
- Release lint completed with zero errors and the same four existing warnings. Build-script syntax and artifact names derived from the compiled metadata were verified.
- New artifacts and checksums are also collected in `dist/releases/v3.4.0/`. Earlier beta.1 files are retained as historical artifacts.
- The previous APK passed independent package checks after a reported installation failure on a Xiaomi 14T Pro. No device was connected for installation testing; the exact failure cause and successful installation of beta.2 remain unconfirmed.
- Shared application code and Windows binaries are unchanged. The earlier source/UI checks below remain historical; they were not rerun for this Android-only packaging update.

---

# Release verification — MyMovieList v3.4.0 — 2026-10-06

This release packages the current shared application for Windows and Android. Test writes used synthetic libraries; the personal AppData library was not opened or rewritten.

- **212 Python tests passed** in the main project, including local storage, migrations, identity preservation, bilingual content, recommendation diversity, concurrency, native-session protection and desktop data paths. Python E9/F checks and all four application JavaScript syntax checks passed.
- **11 shared TMDB/RAWG gateway tests passed.** No gateway deployment was required for this packaging update.
- **Recommendation UI checks passed:** stable reloads, refresh, discovery modes, keyboard actions, failed-refresh recovery, English/Turkish identity and four viewport widths (320, 390, 768 and 1365 px).
- **Bilingual catalog UI checks passed:** 30 responsive views, automatic legacy enrichment, full cast storage, actor/company navigation, direct search addition, title aliases, offline details and editing, preservation of every movie field, and no JavaScript errors.
- **Mobile UI checks passed:** touch targets, equal card heights at 320, 360, 390 and 412 px, touch autocomplete, note saving with a reduced viewport and removal/Undo. These browser checks do not replace Android keyboard/insets or device testing.
- **Windows build completed:** `dist/MyMovieList-v3.4.0.exe` and `dist/releases/v3.4.0/MyMovieList-v3.4.0-windows.zip`.
- **Signed Android builds completed:** APK and AAB in `dist/android/3.4.0-android-beta.1/`. Package identity remains `com.moviewatchlist`; `versionCode` is 3 and `versionName` is `3.4.0-android-beta.1`. The APK certificate matches the previous 3.3.0 release, and its v2 signature and 16 KB ZIP alignment passed. Bundletool validated the AAB structure; AAB signature verification passed.
- **Archive verification passed:** EXE, APK and AAB contain all shared modules and 35 UI assets matching the source. Packaged versions, Windows ZIP contents and SHA-256 checksums match. No personal database, environment file, Git history or private signing key is included. All 80 native-library ELF alignment checks across the APK/AAB passed at 16 KB or larger.
- **Release downloads are collected in `dist/releases/v3.4.0/`:** Windows ZIP, Android APK, Android AAB, current release notes and a combined `SHA256SUMS.txt`.
- **Android release lint passed** with no errors and four non-blocking warnings: an API 33 attribute on older devices, an available Gradle update, an unused legacy icon and the existing square launcher-icon shape.
- **Git packaging checks passed:** `.env`, personal SQLite data, signing material, build outputs, Node dependencies, local Wrangler state and `.dev.vars` are ignored. Tests, application/Worker source and public documentation remain eligible for version control. `git diff --check` passed; Git reported only LF/CRLF conversion notices.
- Physical Android-device testing and Google Play publication remain separate. Desktop and Android keep independent libraries. Personal statistics and cloud sync are not included.

Earlier verification records below describe the source updates and older builds; their version numbers and historical limitations are retained for context.

---
# Recommendation update verification — 2026-10-06

- Added **23 recommendation regression cases** covering rich features, moderate-rating confidence, limited lead-cast evidence, a single versus consistent theme preference, smaller interests, franchise/director diversity, different themes within one genre, negative feedback, language identity, cache corruption, offline restarts, optional detail failures and reserve refill. Existing survey/refresh/privacy/concurrency tests remain included.
- The full **main-folder run passed 212 Python tests**. One warning concerned an unwritable pytest cache, with no test failures. Python E9/F checks and **11 shared TMDB/RAWG gateway tests passed**.
- **Isolated recommendation UI checks passed**: stable page reload, fresh picks, mode changes, keyboard add/refresh, failed refresh retaining cards, English/Turkish identity and no horizontal overflow at 320, 390, 768 and 1365 px. All UI writes used a synthetic library; personal AppData was not opened. The in-app browser could not reach localhost, so the checks used an isolated headless Edge session through Playwright.
- **Live metadata smoke passed**: movie 550 returned 14 keyword IDs, 75 cast members and one director through `api.myshelf.cloud`; existing TV search returned 20 results. The tested allowlist was deployed as Worker version `8233cb00-dc3e-4e48-9860-161ce9d3f222`, preserving provider credentials and rate-limit bindings.
- **Live recommendation smoke passed** with a separate empty library: 126 public candidates, 24 enriched records and ten unique picks without errors. First load took 6.08 seconds; repeating the same selection took 0.006 seconds and preserved the cards. Network timing is illustrative, not a guaranteed response time.
- **Windows build refreshed and verified**: `dist/MyMovieList-v3.3.0.exe` (15.72 MB) contains the new recommendation module and matching UI/locale assets. The release ZIP contains only the EXE and current release notes; its SHA-256 checksum matches. The packaged launcher data-path tests passed with isolated AppData. The new EXE was inspected without starting it against the personal library.
- **Synthetic timing, median of five runs**: the old session strategy ranked an entire 800-movie pool in 669 ms; the new richer model ranked a 30-movie reserve from 1,200 candidates in 340 ms. The simpler old ten-pick calculation was faster (30 ms for 800 candidates versus 136 ms for the richer 1,200-candidate calculation). The reserve limit reduces total session work; these timings exclude network/image costs and do not measure recommendation accuracy.
- Private notes are not parsed or scored. No database schema migration, personal-library rewrite, telemetry or Android APK/AAB build is part of this recommendation update. Android's source packaging allowlist includes the new shared module for a future build.

See [recommendation design and reproducible checks](RECOMMENDATIONS_DESIGN.md). Earlier verification follows.

---

# Discovery update verification — 2026-10-06

This section covers the current source update; previous release checks are retained below.

- **106 Python tests passed**, including **38 new discovery cases** covering provider selection, validation before network calls, malformed/duplicate/adult results, fresh library membership over cached feeds, quick-add/duplicates, hidden-library filtering, offline genre choice, error isolation and pagination/back links.
- **Isolated browser regression passed**: a failed shelf leaves the others usable; retry restores keyboard focus; latest trending period wins; failed quick-add remains retryable; simultaneous submissions for the same film across three shelves issue one add request and update all copies.
- Hide-library addition removes only that card, updates the visible page count and focuses the next title. Pagination and movie-detail return links retain period/filter/page choices.
- Six discovery views were checked at **320, 390, 768, 1024 and 1365 px**, without horizontal document overflow. A long title and a missing poster retain equal card height and aligned actions. Selected genres use a compact native selector on mobile.
- Back/forward cache restoration refreshes membership; library/Watched status is included in accessible action labels. These two behaviors were also covered by a separate source review.
- **9 Worker/RAWG regression tests passed**. The shared gateway was deployed as version `916a7fed-b84d-4ef4-bc53-969c87107d20`; all four live movie collection requests returned HTTP 200 and 20 results each. Existing provider credentials and limits were retained.
- **Live UI preview passed**: all three shelves rendered, all 36 requested poster images loaded, and the Science Fiction mobile grid had no document overflow. Screenshots are saved under `screenshots/discovery-*.png`.
- **Main Windows build refreshed:** `dist/MyMovieList-v3.3.0.exe` and `dist/releases/v3.3.0/MyMovieList-v3.3.0-windows.zip` now include the discovery update. Embedded UI assets match the source, ZIP contents match the EXE/release notes, and the SHA-256 checksum was verified.
- **Windows Discovery Preview built successfully** (15.7 MB). Archive inspection confirmed the two new Python modules and UI assets and excluded library/credential files. This is a preview build, not a newly published GitHub release.
- New modules were added to Android's packaging allowlist. No new APK/AAB was built for this source update; physical-device and screen-reader testing remain separate checks.

Reproduce the browser regression using a newly created temporary fixture library:

```powershell
$env:DISCOVERY_SCENARIO = "errors"
$env:PREVIEW_TEST_PORT = "5063"
.\.venv\Scripts\python tests/discovery_fixture_server.py
# In another terminal, with Playwright available:
node tests/discovery.e2e.cjs
```

The fixture also supports `DISCOVERY_LIVE=1` for an isolated read-only catalog preview with real provider results. Tests never use the personal library or print provider secrets.

---

# Verification — MyMovieList v3.2.0

Verified on Windows, 2026-10-02. All test writes used isolated databases. The release continues using the existing AppData library; it adds no schema migration and does not merge the earlier frontend preview's separate data.

- **48 automated tests passed**, including two new desktop launcher checks simulating packaged execution: default AppData selection and explicit data-directory override. Existing notes, ratings, favorites and row metadata remained intact.
- Ruff F checks and both JavaScript syntax checks passed.
- The frontend suite covers ten desktop routes and 320, 390, 768 and 1024 CSS-pixel widths, card alignment, long titles, missing posters, deletion/Undo, editor removal, taste selection focus and keyboard autocomplete.
- The release uses one shared version value for its footer, window title and build name.
- The public release ZIP contains only the executable and release notes. Personal databases, credentials and poster files are excluded.

Physical phone testing, mobile Safari and a full screen-reader audit remain outside this verification. Online flows use mocked TMDB responses during testing; live service availability is not guaranteed by these checks.

## Historical verification — Discovery edition

The following records describe earlier versions, including card expansion that has since been replaced by a fixed single-line note preview.

Verified on Windows, 2026-09-29 / 2026-09-30. Test writes used isolated temporary databases and `.qa/`; the original project library remained at 6 movies, schema version 0. Its migration will run on the first normal launch, with an automatic backup.

## Automated checks

- `pytest -q`: **17 passed**.
- Ruff undefined-name / import / syntax-family checks: passed.
- JavaScript syntax check: passed.
- `git diff --check`: passed.

Coverage includes: fresh and legacy migration; backup preservation; refusal to destroy duplicate legacy records; repeated and concurrent adds; concurrent restore/re-add; restoration of every stored column; original rendered ordering under four sorts; stale Undo rejection; independent favorites and preserved watched dates; manual form validation and draft retention; HTML escaping; CSRF, origin and host validation; safe redirect targets; pagination and whole-library search; settings preservation; TMDB failures; bounded single-flight caching, failed-response expiry and rate-limit cooldown.

## Browser checks

The local application was exercised with deterministic TMDB fixtures so error, empty and delayed responses were reproducible.

- Movies, People and Companies search; result navigation and pagination links.
- Direct add with a fast double click: remained on search, changed to the green edit link, one library record.
- Movie → person → movie and movie → company → movie.
- Suggestions: arrow selection, Escape dismissal, newer empty query replacing an in-flight slow query.
- Remove → Undo: movie returned to its original list position.
- Library title filter, clearing it, and independent release-year sorting.
- Equal closed-card height: **279 px** including a very long title and missing poster.
- Opening a long note increased that card to about **732 px**; all other cards stayed **279 px**.
- Responsive checks at 390, 900 and 1280 px: no horizontal page overflow in the checked library views.
- No browser console errors during the checked discovery flows.

Keyboard support uses native links/buttons in addition to autocomplete controls and search/Undo shortcuts. Not every assistive-technology/browser combination has been audited.

## Live TMDB checks

Read-only requests using the existing project configuration successfully returned:

- movie search (`Interstellar`): 20 results;
- person search (`Tom Hanks`): 1 result;
- company search (`Disney`): 20 results;
- discovery by company ID 174: 20 results.

Credentials were not printed. UI mutation tests used fixtures and the isolated library.

## Large-library check

A separate SQLite database was seeded with 5,000 movies. Flask test-client observations on this machine:

| Request | Server response time | Rendered cards | HTML size |
|---|---:|---:|---:|
| Library | 25 ms | 36 | 109,583 bytes |
| Filter matching one title | 4 ms | 1 | 8,749 bytes |
| Rating sort, page 20 | 6 ms | 36 | 114,250 bytes |

These are local server observations, not end-to-end browser or network benchmarks.

## Windows package

- PyInstaller build succeeded: `dist/MovieWatchlist-Discovery.exe`.
- The original `dist/MovieWatchlist.exe` was preserved.
- Release executable launched with the isolated test data directory and exposed its own **MyMovieList** window.
- Package archive inspection found no `.env`, `movies.db` or personal poster directory.
- Full native UI automation was not completed: the desktop state-capture approval timed out. Interactive flows were instead verified in the in-app browser; the native check confirms process/window startup.

## Intentional limits

- Favorites no longer change watched state or overwrite watched dates.
- Unknown creation dates in older records remain unknown; IDs preserve their prior order.
- Existing records load person/company IDs through **Load people & studios**, rather than making network requests while opening the offline library.
- The token is stored locally in plaintext SQLite, as documented in Settings. Backups should be kept private.
- Removed films are retained until restored; automatic permanent deletion is deliberately absent.
- Only one user's local library is supported; there is no public-hosting authentication system.

## Note-preview refinement

The expandable-card interaction above was subsequently replaced at the user's request. Cards now show one truncated note line and a **View note** link to the film detail's `#note` section, preserving the library return URL. Browser verification found all eight test cards at 281 px with no expandable details elements, and confirmed that View note opens the full note on the detail page.

## Unified search refinement

All is now the default search, combining independently cached movie, actor and company search pages. Results are interleaved and tagged by type; Movies, Actors and Companies remain available as filters. A failed source leaves successful sources visible with an explicit warning. The suite now has **20 passing tests**, including mixed autocomplete destinations, per-type IDs, partial failures and combined pagination. Browser checks verified All results, the Actors filter, and keyboard selection of an actor from mixed suggestions.

## Profession-aware discovery

Actors & Directors is one shared search category and search box. All includes movies and people whose primary profession is Acting or Directing. Companies are searched only with their dedicated filter. Profile headings and autocomplete use the same labels. Unknown professions no longer default to Actor. Both roles share the existing person cache without additional detail requests.

TMDB has no department search parameter: this category filters Acting and Directing on each upstream page. Counts describe matches on the current page; empty pages retain pagination. Categories reflect the primary profession, not every credit.

The 21-test suite covers mixed actor/director results, producer and unknown labels, All inclusion, profile labels, suggestions and pagination.
`nBrowser verification confirmed the combined Actors & Directors option and Nolan with a DIRECTOR label after submitting the shared form. The desktop executable was rebuilt successfully.


## Focused All and film credits

All now makes only movie and person searches, and excludes companies and other primary professions from both results and suggestions. Shared filters retain actors/directors; counts reflect the current page. Writing and producer credits are clickable on movie details, deduplicated per role group while preserving multiple jobs and participation across groups. No database changes or additional credit requests are needed. All 22 tests pass, including source failure recovery, excluded company requests, role filtering, dedicated company search, and writer/producer navigation.
Browser fixtures verified focused All and dedicated company results. Build succeeded; because the previous executable was locked, the new package is dist/MovieWatchlist-Discovery-Updated.exe in the same directory.


## Checkbox search filters

Replaced the type dropdown with four checkbox filters beneath the query. Default: movies, actors and directors. Filter state is encoded in the URL and preserved in pagination, detail return links and autocomplete. A shared person request serves both profession filters. No selection triggers guidance without TMDB requests. Legacy type URLs still work.

23 tests pass, including multiple selected categories across pagination, no selection, excluded network sources and filtered autocomplete. Browser fixtures verified default selections and a director-only query.


## Taste onboarding and local recommendations

Schema 2 adds separate survey-like and dismissed-suggestion tables. A pre-migration SQLite backup is created for older libraries; movie metadata remains unchanged. Survey saves are atomic and retry-safe, including concurrent saves. Newly selected films become Watched without inferred rating, favorite or watched date. Existing entries retain every personal field.

The initial recommendation engine uses locally derived genre affinities, evidence shrinkage, director-group independence weighting and consistency-aware confidence. Public candidate requests are identical before and after changing private preferences. No taste-derived IDs or filters are sent to TMDB. Explicit survey searches and selected-film detail requests use the existing API integration. Notes, fine-grained themes, actors and candidate-director matching are not analyzed in this version.

35 Python tests pass. Added coverage: weak single-film evidence, strong repeated signals, contradictory ratings, order independence, negative feedback, diversity, deduplication, survey atomicity/failure/retries/concurrency, unchanged existing personal fields, schema 1 migration and backup, public-request independence, hide/restore, survey search and validation, and offline local-watchlist rendering.

Isolated headless Edge UI checks with deterministic TMDB fixtures passed: 12 choices; preserving picks across browse/search; four picks saved as watched; 10 recommendations; explanation disclosure; hide/Undo; library entries; 390px pages without horizontal overflow; no JavaScript errors. Browser-control tools were unavailable in this session, so this used a separate test browser, not the user's active browser. Test databases and screenshots are under ignored .qa/. No personal library was used for verification.
Additional headless UI checks passed for Space-key selection, retaining picks after an injected save error, and aborting stale search responses. Python lint and both JavaScript syntax checks pass.


## Stable recommendations within an app session

Selections are now cached per recommender/app instance and discovery mode, under a lock. Page reloads do not rerank or refetch a successful pool. A new app process generates a new selection with small local score variation and a repeat penalty for the previous successful session's first ten picks per mode. History is bounded in the existing settings table; there is no schema change or external preference transmission. Limited pools can repeat candidates. Survey edits explicitly invalidate the selection. Current library and dismissal exclusions remain live; added films trigger a queued UI refresh and are replaced without reordering remaining picks.

Added tests cover stable requests and rating changes, same-profile restarts, live exclusion with stable surviving order, sparse-pool fallback, failed-fetch retries, and parallel requests sharing a single generation.
Session update verified: all 40 Python tests pass. Isolated headless UI checks also passed for page reload/navigation stability, removal after Add to Want to Watch or Not interested, stable ordering of the remaining suggestions, and no JavaScript errors.


## Manual recommendation refresh — 2026-10-01

- 42 automated tests passed.
- Refresh changes the selected mode while retaining library/hidden exclusions and stability on subsequent reads. Other discovery modes retain their selection.
- A failed candidate fetch preserves the previous selection; refresh requires a CSRF-protected POST.
- JavaScript syntax, Ruff F checks and diff whitespace checks passed.


## Recommendation diversity correction — 2026-10-01

- 46 automated tests passed, using mocked TMDB data.
- Controlled strong-profile fixture: familiar/balanced/explore produced 8/5/2 familiar-genre films, with no disliked-genre films in the ten picks.
- Six successive selections from a fixed 100-film pool produced 60 distinct films. Last 50 IDs per mode survive restart.
- Refresh advances public query pages; modes reuse the pool. Failed fetches preserve the pool, cursor and current selection. Sparse pools fall back to repeats without duplicates.
- These fixtures verify selection rules, not subjective recommendation quality on live TMDB data.

- Headless Edge with isolated fixtures: five selections showed 50 distinct films; reloads preserved order; simulated HTTP failure preserved cards; no JavaScript errors.
# Hosted discovery gateway — 2026-10-04

- MyMovieList now uses the shared Cloudflare gateway for catalog requests. No local token is required or sent; local and environment credentials are no longer read by discovery.
- Settings no longer accepts credential writes. Startup removes the legacy `tmdb_token` setting with SQLite secure deletion; other settings and all library records are preserved.
- 62 isolated Python tests passed, including credential-free requests, cache/single-flight/cooldown, offline failures, legacy-token cleanup, Android local authentication and installed desktop library selection.
- Existing browser checks passed: 10 desktop pages, four responsive widths, aligned cards, removal/Undo, survey focus and search keyboard controls. The updated Settings screen was visually inspected.
- Direct live gateway verification from the agent environment was blocked by an SSL connection failure. The user verified TV search on the deployed Worker, but live movie discovery from the rebuilt executable still needs a device check.


Hosted gateway packaged verification (2026-10-04): rebuilt Windows EXE starts with isolated data, Settings has no token field and library loads. Live search returned no catalog results in the agent environment; direct HTTPS probing failed with SSL WRONG_VERSION_NUMBER. Device verification remains required. Main-project tests: 62 passed (temporary cache permission warning only). Existing AppData/source library records and noncredential settings were verified unchanged during credential cleanup; sanitized library backups are in .qa.


Gateway network follow-up: 68 isolated tests passed. Custom HTTPS gateway configuration added and obsolete Settings links removed from discovery errors. Default workers.dev TLS fails in Python (including TLS 1.2), PowerShell and Windows curl while Cloudflare main site succeeds and direct TMDB returns expected unauthenticated 401. User reports Chrome also fails but the in-app browser succeeds. Custom-domain selection and live verification remain pending; no replacement EXE is built until an accessible endpoint is verified.



## Custom domain desktop build — 2026-10-05

- Primary project: Desktop/movie-watchlist. Default gateway changed to https://api.myshelf.cloud/3/.
- Identifiable MovieWatchlist/version User-Agent resolves Cloudflare Error 1010 for the default Python user agent; covered by the request-header test.
- 68 automated tests passed with temporary databases.
- Windows EXE and release ZIP rebuilt successfully; packaged startup, library and token-free Settings verified in an isolated data directory.
- Cloudflare resolver returns valid A/AAAA and nameserver records. HTTPS search using a test-only resolved IP returned 20 results. No IP override was added to the app and certificate verification remained enabled.
- Final live search in the packaged app did not pass: the machine default DNS resolver could not resolve api.myshelf.cloud. Recheck normal discovery after DNS resolution recovers before public release.

Follow-up: Cleared Windows DNS client cache after stale negative resolution. Normal application TMDBClient search returned 20 results; rebuilt EXE smoke test passed startup, token-free Settings, isolated library and LIVE search. No DNS server settings or hosts entries were changed.

MyMovieList rebrand (2026-10-05): 68 tests passed; packaged MyMovieList-v3.3.0.exe verified with new branding and live movie search in an isolated data directory. Existing AppData/MovieWatchlist data path retained.

## MyMovieList logo and Android 3.3.0 beta — 2026-10-05

- Approved generated logo converted to transparent PNG, 256px PNG and ICO with nine sizes from 16 through 256px. Windows icon, sidebar, favicon, README and Android launcher updated.
- 68 Python tests, desktop browser flows, four mobile widths and mobile interaction tests passed. New Windows EXE live search passed with isolated data.
- Signed Android APK and AAB built successfully; release package keeps com.moviewatchlist identity, raises versionCode to 2, and uses the same signing certificate as the previous 3.2.0 APK.
- APK signature v2 and 16KB ZIP alignment verified. Shared logo assets included; personal databases, environment files and private signing files excluded.
- Android app label MyMovieList and versionName 3.3.0-android-beta.1 verified. Physical Android-device installation/runtime verification remains pending.


## English/Turkish interface — 2026-10-06

- Main project: Desktop/movie-watchlist. Only known UI labels/messages are translated; no DOM-wide replacements, title matching or catalog-language switching.
- Windows UI language is read on the first start without a saved preference. `settings.ui_language` is stored in the existing local database and reused across sessions/restarts. Frozen builds retain AppData/MovieWatchlist. The database schema is unchanged.
- Settings → Language uses a CSRF-protected POST, validates en/tr and redirects to the refreshed Settings screen. HTML lang, accessible labels, notifications, error messages and asynchronous fragments use the saved language. BFcache pages check the saved preference before showing stale-language content.
- TMDB requests remain en-US. All movie IDs, form values, status enums, URL parameters, titles, genres, biographies, descriptions and notes remain canonical. A mismatched movie-detail ID is rejected before display/add/refresh.
- 146 isolated Python tests passed, including first-start/restart persistence, concurrent initialization, whole-row preservation across repeated switches, original-order Undo, quick-add duplicates, canonical TMDB requests, invalid/CSRF language changes, localized partial failures, escaping and mismatched provider data.
- Browser regression passed 80 views across English/Turkish at 320/390/768/1024/1365px with zero JavaScript errors. Verified keyboard language save, persisted selection, add failure/retry, fixed movie IDs/statuses, Ctrl+Z Undo with notes/rating/favorite, autocomplete + Enter, genre IDs, taste selections and recommendation labels.
- English/Turkish Settings screenshots inspected at desktop and 390px. Longer button labels adjusted to fit existing compact cards. Shared client dictionary includes only the 51 messages used by JavaScript.
- No Android build, gateway deployment, version bump, Git commit or release publication performed for this change. User AppData and source libraries were not opened by QA; all checks use isolated libraries.

Windows packaging verified: rebuilt standard MyMovieList-v3.3.0.exe and Windows ZIP. The real EXE starts with an isolated library, changes Turkish to English, retains English after restart, and leaves every movie field unchanged. Packaged UI assets match current source; i18n and identity guards are included; ZIP/SHA256 contents verified. Android artifacts were not rebuilt.


## Automatic credits and bilingual movie content — 2026-10-06

- Primary project: Desktop/movie-watchlist. New movies and taste-survey additions fetch verified English details, complete credits and translations in one `credits,translations` request. A separate SQLite metadata cache stores both display languages; movie IDs and canonical library titles are never matched or rewritten by translated text.
- Turkish-original movies use their original title in Turkish. Available Turkish synopses are preferred, with English fallback for missing/blank translations. Search, suggestions, discovery, filmographies, taste choices and recommendation display use the chosen language while ranking and stored genre/status values remain canonical.
- Schema v3 adds the metadata table with an automatic before-v3 SQLite backup for existing libraries. Migration, bilingual switching, refresh failures, Undo, original order and personal-field preservation are covered by tests. No AppData/source library was used by QA.
- Cast, directors and companies load without a detail-page refresh button. Complete cast lists are saved; the first 12 appear directly and a native keyboard-accessible disclosure shows the rest. Older visible entries hydrate with two bounded background workers and retain all personal data, including timestamps. Interrupted/offline fetches leave saved library pages usable.
- Duplicate metadata requests coalesce by movie ID. Malformed credits, mismatched movie/translation IDs and damaged cache entries are handled safely. Foreground transient failures retain a short retry cooldown and correct error status; background scans back off separately. Rate limits remain 120/client-IP, 600/TMDB and 60/RAWG per minute.
- Library filtering supports original/English/Turkish aliases, Unicode case and diacritics; İstanbul/istanbul and Sınıfı/Sinifi match without modifying stored titles.
- 189 isolated Python tests passed. Test fixtures block actual catalog network access unless explicitly mocked; the live opt-in verification runs separately. Ruff, JavaScript syntax and diff whitespace checks passed.
- 10 shared-gateway tests passed, including movie credits/translations append validation, canonical cache keys, injection rejection and unchanged TV/game behavior. Deployed Worker version: 9c58d1d3-860a-461a-8dc5-995d7a27390d at api.myshelf.cloud.
- Browser checks passed 110 bilingual responsive views at 320/390/768/1024/1365px with zero JavaScript errors: language persistence, add/retry, autocomplete, Undo, actor/company navigation, automatic older-entry hydration, complete cast, title-alias filtering, offline details/editing and full movie-row preservation after metadata completion. Turkish film detail was visually inspected on desktop and at 390px.
- Separate live validation of the 1975 Hababam Sınıfı (TMDB 83651) saved its Turkish synopsis and all 57 cast members, displayed The Chaos Class in English, and preserved the entire completed movie row through the language switch.
- Android was not rebuilt, and no version bump, Git commit or GitHub release publication was performed.

Windows package verification: rebuilt MyMovieList-v3.3.0.exe and Windows ZIP. The real executable displayed saved Turkish/English movie titles, synopses and full cast offline, retained the English selection after restart, and preserved every completed movie field in an isolated library. All 32 packaged UI files match current source; the catalog/i18n modules and ID guard are included. Personal database/env/signing files are excluded; ZIP contents and SHA256 verified. No Android artifacts were rebuilt.


## Stepped accounts, private profiles and automatic sync — 2026-10-08

- Signup now separates email, code verification and password creation. Normal sign-in uses email/password. Recovery verifies its code before displaying the new-password form. Confirmed existing accounts cannot replace their password through signup.
- Short-lived flow credentials remain in bounded server memory; browser sessions contain only opaque flow IDs. Purpose, stage, expiry and account-scope checks prevent bypass and cross-flow reuse. A per-step lock serializes concurrent completion; resend has a server-side cooldown.
- Sixteen SVG avatars ship with the app. Only a validated avatar ID and optional display name sync through private Auth user metadata. Offline profile edits survive restart; generation checks preserve newer edits during upload. This profile metadata is never used for authorization.
- Signed-in account libraries sync automatically. Explicit pause survives sign-out/sign-in; enable/pause flags update atomically. Local writes wake a coalesced worker; bounded retries retain offline edits. Guest adoption remains an explicit action explaining that copied private notes upload to the account.
- The header offers Sign in/Create account or a profile menu. Import/export moved to Settings. English/Turkish forms support password reveal, mismatch validation, code paste, resend countdown, keyboard avatars and Escape to close the menu. Touch controls stay usable at phone/tablet widths while desktop cards retain their compact controls.
- Full regression: 278 isolated Python tests passed. After the final backend adjustments, 66 focused auth/cloud tests passed. New account modules pass Ruff; app.py passes with existing calendar-date DTZ lint findings excluded (local watched-date semantics preserved).
- Headless Edge passed 96 English/Turkish views at 320/390/768/1365px: no horizontal overflow, unlabelled fields, leaked synthetic credentials or browser script errors. End-to-end synthetic signup, recovery, password reveal/mismatch, keyboard avatar selection, menu Escape and Settings backup access passed. Desktop and phone signup/profile screenshots were visually reviewed; remaining profile translations corrected.
- Main source transfer is backed up and verified by SHA256. QA uses isolated libraries; no personal AppData/source database, SMTP secret or signing key is modified. No EXE/APK/AAB build, version bump, commit or release publication is included.
- Hosted SQL and anonymous access denial were checked earlier; the user verified SMTP, authentication/recovery and one-account restoration in two isolated instances. The new email-first signup still needs live SMTP verification. Hosted two-owner access isolation, multi-connection PostgreSQL concurrency and native Android lifecycle remain release checks.
- Post-transfer verification from Desktop/movie-watchlist: all 278 Python tests passed again in isolated temporary libraries; all 41 transferred SHA256 hashes matched. Main-source browser checks passed for the profile form, all 16 loaded avatars, Turkish labels, 390px layout, email-first signup and Settings backups with zero script errors.
- The previous separate live-auth preview was restarted from the updated main source. Its protected test-account session restored successfully; automatic sync was enabled, current, and had zero pending changes/conflicts. No personal AppData library was accessed. The final 96-view synthetic UI run passed again using a fresh test email so confirmed-account signup protection remains exercised independently.

## MyMovieList 3.5.0 release verification — 2026-10-08

- The authoritative source is Desktop/movie-watchlist. APP_VERSION is 3.5.0; README.md, README.tr.md, Android documentation and English release notes match the new downloads. Historical build records retain their original version numbers.
- All 390 isolated Python tests passed from the main project. Added Android-wrapper coverage exercises native authentication, account/guest separation, offline upload retries, account restoration after restart, sign-out and stale native-token rejection. Java session-bridge tests verify round-trip/error handling; they do not substitute for real Android Keystore execution.
- Python F lint and all six browser JavaScript syntax checks passed. The .gitignore rules were verified in an isolated Git repository: 27 private/generated paths ignored and 13 source/configuration paths remain trackable. Source tests, SQL migrations and the public Supabase configuration remain in version control; libraries, sessions, exports, signing keys and compiled downloads do not.
- Windows MyMovieList-v3.5.0.exe and its release ZIP were rebuilt. The real executable started with an isolated test library, displayed Turkish/English saved metadata, offered email-first signup/recovery forms, retained English after restart and preserved every saved movie field. All 66 packaged UI assets and the public cloud configuration match the main source; all 23 shared Python modules are present. The public ZIP contains only the EXE and release notes.
- A clean signed Android release build produced APK and AAB 3.5.0-android-beta.1. The application ID remains com.moviewatchlist; versionCode rises to 5. The SHA-256 signing-certificate fingerprint matches the previous 3.4.0 beta.2 APK and the new AAB. APK v2 signing, 16 KB ZIP alignment, AAB signature and bundletool structure validation passed.
- Both Android packages pass nested archive CRC and private-file exclusion checks. All 24 Python modules, 66 UI assets, bundled avatars, public cloud configuration and the compiled CloudSessionStore class are included. Main/staged/build source hashes and packaged bytecode hashes match. Each package has 138 native libraries whose ELF LOAD segments pass 16 KB alignment checks.
- Android release lint has zero errors and four existing warnings: UnusedAttribute, AndroidGradlePluginVersion, UnusedResources and IconLauncherShape. Build success and archive verification do not prove physical-device behavior. No phone was connected; installation/update, WebView keyboard/navigation, process lifecycle and real Keystore restoration still need device testing. The current wrapper has no native backup file picker/download handler.
- Read-only live Supabase registration setup probing still reports setup incomplete. Apply supabase/migrations/004_registration_usernames.sql after 001–003 before announcing new registration. Existing password sign-in, recovery and private library sync are independent of this new protocol. No privileged database credential was supplied, so migration 004 was not applied by this local packaging work.
- Downloads are collected in dist/releases/v3.5.0/ with combined SHA256SUMS.txt. Earlier downloads remain untouched. No Git commit, push, GitHub Release or Play Store submission was made. QA did not access or alter the user's personal AppData library.
