# Verification — Discovery edition

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
- Release executable launched with the isolated test data directory and exposed its own **Movie Watchlist** window.
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
