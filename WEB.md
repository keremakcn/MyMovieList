# MyMovieList on MyShelf

Web beta published at [myshelf.cloud](https://myshelf.cloud) on 10 October 2026.

The web app uses the same Supabase accounts and personal-library records as
Windows, Android and macOS. Movie catalog requests use the existing
`api.myshelf.cloud` gateway. Downloads point to the latest published GitHub
release; developing the website does not update those downloadable packages.

## Landing posters

The four landing-page posters expand on hover or keyboard focus and link to
`/movie/<TMDB ID>`, which also works when opened directly or refreshed. Detail
pages use the same ratings, notes and library actions as the catalog dialog.
The hero uses daily TMDB trends, cached per UTC date and language in the browser;
an open page checks the date every minute and on return to the tab. A failed
refresh keeps the last usable selection. The weekly grid below is unchanged.

## Using the web app

- Search and save films without creating an account. Browser records persist in
  IndexedDB, including ratings, private notes, favorites and watch dates.
- New registration follows email → code → permanent username → password,
  display name and one of the 16 bundled avatars. The signup screen explains
  that the browser library is copied into the new private account.
- Normal sign-in uses email and password. Recovery verifies the email code before
  opening the new-password step. Existing-account sign-in keeps guest records
  separate; copying them is an explicit action in Profile.
- Account changes sync automatically while connected. Offline changes remain in
  the browser and retry when connected. Sign into the same account in the app to
  restore the personal records; public film details and posters are fetched from
  the catalog rather than duplicated in Supabase.
- Profile shows the fixed username, editable display name/avatar and personal
  counts. Sharing is opt-in and exposes only up to six selected films, with
  optional ratings/counts. Notes and the rest of the library remain private.
- Export/import uses the app's portable JSON format, including recoverable
  competing versions. Clearing site data or using temporary/private browsing can
  erase browser records; an account or export preserves a separate copy.

## Edit times and compatibility

Apply SQL migrations 001–006 in order. On 10 October 2026, the owner applied
006 and the hosted anonymous `mml_time_sync_status` probe was verified.

Mutable personal fields carry separate UTC edit times. Independent changes
merge; competing edits with trustworthy distinct times choose the newer edit,
even if the older edit uploads later. The losing competing version is retained
in exportable history. Missing, equal or implausibly future clocks keep the
existing review path instead of inventing an edit time.

The cloud revision still controls atomic writes, retries and incremental pulls.
Operation IDs freeze the payload and edit times across retries. Deleted records
remain tombstones, and newer edits can restore an older deletion. Original
addition/order keys and numeric film identities are preserved.

Legacy native releases still use protocol 1. Migration 006 retains their RPCs
and existing receipt hashes; their changed fields have unknown edit times.
The 3.7.0 native source is shared across platforms, including the Android
packaging allowlist. It includes time-aware conflict handling and private person
favorites. Windows, Android and Mac 3.7.0 packages need fresh builds; existing
downloads retain the features of their original version.

## Cloudflare deployment

Source: `cloudflare/myshelf-web`. It has no frontend build dependencies.

1. Use the existing Cloudflare account and active `myshelf.cloud` zone.
2. In `cloudflare/myshelf-web`, run `npx.cmd wrangler@4 secret put SESSION_SECRET`.
   Supply 64 cryptographically random hexadecimal characters; keep this secret
   only in Cloudflare. Never put it in the repository or a native package.
3. Run `npx.cmd wrangler@4 deploy --dry-run`, then
   `npx.cmd wrangler@4 deploy`.
4. Verify `/api/status`, discovery, real email signup/recovery and a
   same-account native round trip before announcing the new release.

The root route is `myshelf.cloud/*`; the existing, more specific
`myshelf.cloud/u/*` public-profile route keeps priority. The catalog gateway,
its TMDB secret and the separate profile Worker are unchanged.

The only public Supabase configuration is its project URL and publishable key.
Access/refresh tokens are in authenticated encrypted, HttpOnly, Secure,
SameSite=Strict host-only cookies. They are never stored in browser JavaScript
storage. Private requests also carry the expected owner ID so a stale tab cannot
upload account A's records under account B after a cookie switch. Mutations
check Origin, content type and the app header. Production auth/API limiters fail
closed; private API responses are not cached. The service worker caches the
public shell only; personal offline records remain in account-scoped IndexedDB.

Optional localhost development requires `DEVELOPMENT=true` and a temporary
session secret. The production configuration never enables this mode.

## Checks

Run `node --test cloudflare/myshelf-web/tests/worker.mjs
cloudflare/myshelf-web/tests/sync-model.mjs cloudflare/myshelf-web/tests/hero.mjs
cloudflare/myshelf-web/tests/people.mjs` from the repository root. Python
regression tests include native field clocks, frozen retries, portable export,
legacy compatibility and recoverable conflict handling. Full verification is
recorded in [QA_RESULTS.md](QA_RESULTS.md).

Film credits and the approved TMDB logo are in `/credits`, following the
[official attribution instructions](https://developer.themoviedb.org/docs/faq).

## Private favorite actors and directors (007)

Person cards link to `/person/<TMDB ID>`, with biography and filmography.
Hearts record independent actor/director choices. `/people` is available to
guests; signed-in profiles link to the same private collection. Metadata is
cached separately from account preferences. Refresh retains choices, and
toggling a heart preserves unsaved movie notes.

Migration `supabase/migrations/007_person_favorites.sql` is installed on the
hosted service; its protocol-1 probe was verified on 12 October 2026. Apply it
after 001–006 when setting up another project. It exposes authenticated owner-bound RPCs over private tables. Cloud
payloads contain person ID, role, boolean and edit time, with no photographs,
names or biographies. Removals retain tombstones, retries keep operation IDs,
and newer edits win. Missing 007 retains choices locally and retries without
interrupting movie sync. Portable exports and new-account guest adoption
include these preferences. Existing native downloads need rebuilding; the
Android shared-source list includes the modules. Public showcases are unchanged.

Run `node --test cloudflare/myshelf-web/tests/people.mjs` and
`python -m pytest tests/test_people_favorites.py` alongside the existing checks.
