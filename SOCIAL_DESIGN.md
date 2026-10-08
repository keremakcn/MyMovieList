# Social discovery

Release rebuild, October 8, 2026. Shared version: **3.5.0**. Windows and
Android beta.3 packages include this feature. macOS source is prepared; its
native packages and tests are deferred.
The user applied migration 005 on October 8. Both hosted Social views passed
anonymous protocol-1 probes with empty results.
The rebuild does not deploy SQL or generate Mac downloads.

## Scope and references

The desktop app now has **Social → People / This week**, with direct in-app
profile navigation. People search uses display names and unique usernames.
The existing showcase still contains up to six films selected by its owner.
There are no posts, comments, messages, follows or activity-tracking events.

[Letterboxd's native app](https://letterboxd.com/apps/) combines profile/film
discovery with friends' activity. Its [welcome guide](https://letterboxd.com/welcome/)
distinguishes a watched flag from a dated diary entry. [Trakt's API](https://developer.trakt.tv/)
similarly models watched history using dates. These inform the navigation and
date semantics; this first implementation deliberately keeps the owner's
curated showcase as its sharing boundary.

## Public data boundary

`005_social_discovery.sql` adds one read-only RPC, `mml_social_page`, and a
partial index for public profile owners. It creates no event table and changes
no private library grants, RLS policies, ownership or account visibility.

Both views require an already-public profile, a claimed username and permitted
username/display name. Hidden profiles, accounts without handles and blocked
legacy names are excluded. Display names may repeat. Directory rows contain
only username, display name and one bundled avatar identifier.

Weekly rows additionally contain one chosen TMDB ID, its watched date, and an
optional personal rating governed by the existing **show ratings** option.
The RPC joins only the owner's selected IDs to that owner's library rows.
Unselected/custom/deleted films, Watchlist entries and undated films cannot
appear. Notes, email, Auth IDs, tokens, favorite flags and full history never
leave through this projection. Aggregate counts remain an independent option
on the existing profile page and are not part of Social.

The sharing screen explains directory discovery and dated showcase visibility
before publication. No account is made public by the migration. An existing
public showcase is discoverable once its owner has a handle. Revocation and
film removal take effect on the next successful read; offline revocation still
uses the existing durable queue and needs a connection to reach the server.

## Dates and navigation

**This week** is the UTC calendar week, Monday through Sunday. Only explicit
watched dates from Monday through the current UTC date are included. Creation,
import, modification and sync timestamps are never interpreted as watch dates.
Future dates are excluded. There is one current entry per chosen movie and
member; this is a window into showcases, not a permanent viewing diary feed.

People are ordered by username, with 16 rows per page. Weekly entries use
watched date descending, username ascending, then movie ID, with 12 per page.
The database reads one extra row to determine whether another page exists.
Cursor shape, ordering and page sizes are validated on both sides. A cursor
from a prior week restarts the current week's list. UI cursors are also bound
to the active view and query. Search is a literal substring, not SQL wildcards.

Search submits on Enter or its button, makes no request per keystroke and uses
normal GET navigation. It preserves the view/query and has a loading label,
announced status and duplicate-submit guard. Empty, setup and connection states
are separate. Public HTML uses `Cache-Control: no-store`; there is no durable
directory or feed cache that could outlive a visibility change.

`social.py` owns the strict DTO and cursor contract; `social_routes.py` renders
the feature. The Supabase adapter uses only a publishable key for anonymous
reads. `public_catalog.py` hydrates catalog data for both public profiles and
weekly entries, deduplicates movie IDs and caps concurrent metadata requests at
three. Existing catalog caching/localization is reused. An outage retains the
member/date and a movie-ID placeholder. Visiting someone else's profile does
not import their films into the visitor's library.

## Validation and hosted setup

- 478 isolated Python tests passed, including 44 Social cases. Existing private
  sync, account switching, Undo, registration, profiles, discovery and Mac
  source preparation remain covered.
- PostgreSQL contracts execute migrations 001–005 in disposable PGlite databases.
  Social tests cover private/direct-access denial, moderated legacy accounts,
  chosen/dated films, optional ratings, excluded notes/full history, literal
  search, multi-page ordering, week rollover, revocation and safe migration replay.
- Browser QA uses fictional profiles and disposable SQLite files. It checks
  English/Turkish layouts at 320, 390, 768 and 1365 pixels, keyboard search,
  pagination, profile/film navigation and state handling. Real account data and
  AppData are never used in this fixture.
- Android's shared-source allowlist and the Mac compiled-module verifier include
  the new modules. Windows/Android package checks are recorded in QA_RESULTS.md; native Mac
  builds and physical-device tests remain deferred.

Apply the complete [migration 005](supabase/migrations/005_social_discovery.sql)
after 001–004 in **Supabase → SQL Editor → New query → Run** on a new deployment. Expected result:
**Success. No rows returned.** A fresh request to `/social` then uses the hosted
RPC. A hosted rehearsal with public/private owners is still required; isolated
SQL tests do not prove the deployed database's configuration.
