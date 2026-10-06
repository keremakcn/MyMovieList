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
