# Optional cloud sync and provider exit plan

## Optional public showcases — enabled October 8, 2026

Public sharing is separate from Auth user metadata and remains off by default.
`profile_sharing.py` stores durable publication/revocation intent in the active
account's SQLite settings. `002_public_showcases.sql` introduces a private
sharing table and three narrowly scoped RPCs. Owner-only status/write RPCs
derive ownership from `auth.uid()`. Anonymous visitors can call only the
public projection RPC, which rechecks visibility on every read.

The public projection contains a random share UUID (not the Auth user ID),
display name, bundled avatar ID and up to six chosen TMDB IDs in order.
Ratings and aggregate counts require their own showcase options. Custom films,
notes, email, watched dates and unselected film IDs are excluded. The private
library retains its RLS and direct-write prohibitions. Library soft deletion
hides a chosen film; Undo restores its original showcase position.

Publication requires an explicit checkbox and enabled account sync. The worker
uploads private records before publishing references. Showcase/profile edits
update the public projection automatically. Server revisions prevent stale
updates or old publication retries from undoing another device's revocation.
Pending publication keeps newer edits as a follow-up operation.

Revocation is attempted before ordinary library retry/pause handling. Offline
requests remain durable and the UI says visibility may persist until connected.
A signed-in session is required to finish pending revocation; signing out does
not itself remove an already public profile. Already copied information cannot
be recalled. Public responses use `no-store` and `noindex` headers.

The separate read-only `myshelf-profiles` Cloudflare Worker serves
`profiles.myshelf.cloud/u/<share-id>`. Visitors need neither an account nor
the app. EN/TR pages bundle the same sixteen avatar SVGs; public film metadata
comes from the existing `api.myshelf.cloud` gateway with bounded requests and
cached metadata. Visibility responses are never cached. The existing TMDB/games
Worker is unchanged. There is no user directory or public note API.

The desktop visitor route `/profiles/<share-id>` uses the same strict public DTO
and adds film actions against the visiting device's own active library.

Verification: isolated PostgreSQL permission/revision tests, synthetic account
and offline tests, Worker unit tests, and EN/TR desktop/mobile browser checks.
The website is deployed. The user applied migration 002 successfully; live
anonymous projection and private-table/owner-RPC denial checks passed. The
authenticated main-source preview checked its sharing status successfully.
The owner then enabled sharing through the UI; a separate browser read the
empty public showcase successfully. No real profile was published by development tests. Hosted
two-owner and concurrent-connection checks remain release QA requirements.

## Product contract

- SQLite remains the application's working library. Reading, editing, rating, notes, favorites, recommendations and removal/Undo continue when the cloud is unavailable.
- Account creation and cloud sync are optional. Enabling them explicitly explains that private notes and other personal library fields will be uploaded to the user's private cloud library. Notes are not public comments.
- User data is written locally before attempting a cloud request. A failed or restricted cloud service must not undo a successful local edit.
- The shared implementation exchanges personal data between device libraries. Native Android support is prepared but has not been built or device-tested in this change. Public catalog details and posters remain locally cached and are rehydrated through the existing gateway.
- Disabling sync or removing a cloud dependency preserves the local library. Deleting a cloud account and deleting a device's library are separate, explicit operations.

## Cloud data boundary

Synchronize only user-owned records:

- A stable application record ID and logical movie key: a TMDB ID for catalog films, or a generated UUID for custom films.
- Personal rating, note, favorite, Want to watch/Watched status and watched date.
- Original addition date/order, deletion state and revision information.
- Custom-film title, year and other user-entered fields that cannot be reconstructed from a catalog ID.
- User recommendation choices and dismissals if these are included in the first sync release. References must use logical movie keys, not device-specific SQLite integer IDs.

Do not synchronize downloaded posters, catalog synopses, actor/crew metadata, public recommendation pools or provider credentials. Locale and cached recommendation sessions remain device preferences unless a later feature explicitly changes that contract.

Keep public movie information separate from personal records. A cached or translated movie title is never used to identify or merge a user's record.

## Implemented application boundaries

Storage schema 4 adds stable record/order keys and durable queue, baseline and conflict tables. Schema-3 libraries are backed up before migration. Existing integer IDs and user fields are retained. An unknown original addition date remains null; separate `sync_added_at` supplies a stable portable date without inventing an original local date.

1. `personal_data.py` defines versioned provider-neutral data. JSON export/import includes personal/custom fields, tombstones and archived conflicts; tokens and public metadata are excluded. Import validates everything before committing and keeps existing records. This is a personal export, not a full poster/cache backup; a full user-facing backup is separate work.
2. `sync_store.py` owns a durable outbox and three-way merges. Frozen operations retain their exact UUID/payload through restart and retries. Later local edits remain dirty for the next operation. Portable order retains legacy library order on another device.
3. Storage helpers commit personal edits and queue entries together for add/edit, favorites/status, survey additions, removal and Undo. Public hydration never queues a user change. Recommendation dismissals/likes remain local in protocol v1.
4. `cloud_sync.py` separates guest and account libraries while preserving the AppData path. Account databases live in `accounts/<Supabase-user-UUID>/library.db`. New signup stages a disclosed guest copy before completing the password; existing-account sign-in never copies guest data. The manual copy action uses the same `SyncStore.copy_from` transaction. Both paths retain the source and existing account personal fields. Requests bind their account; stale CSRF/scoped API requests reject a changed account.

   Copying reads personal records, conflict archives and available public details
   from one SQLite snapshot, then commits the target in one transaction. A failed
   copy rolls back before remote password completion. If completion commits but
   its response or secure session save fails, the staged account library remains
   available on later sign-in. Repeated submissions never duplicate stable IDs.
   A conflicting existing server record uses the usual two-version review and
   preserves the server's immutable first-add date/order.
5. `cloud_client.py` handles HTTPS Auth/RPC with redacted errors and refused redirects. `account_routes.py` and its bilingual UI provide optional sign-in/up, code verification/recovery, automatic sync/pause, conflict resolution and export/import. Windows sessions use DPAPI, Android Keystore support is prepared, and unsupported OSes keep sessions only in memory. Native loopback authentication and CSRF protection remain intact.

Keep provider HTTP calls out of cards, templates and movie-rating logic. A compact provider boundary handles authentication, pulling changes and pushing changes. There is no need to replace the application with a new frontend or move catalog discovery into Supabase.

## Synchronization correctness

- Cloud rows belong to the authenticated user. Supabase-specific policies and identity handling stay in its adapter and SQL migrations. Clients ship only a publishable key; privileged administration credentials remain outside application packages.
- Use server revisions and conditional writes to detect concurrent changes. Device clock timestamps are insufficient for deciding which note wins.
- Give queued operations idempotency IDs. Retry a timed-out submission without creating a second film or applying the same operation twice.
- Keep conflicting note versions until resolution; do not silently overwrite a user's text. Handle independent field edits without unnecessarily replacing the entire record.
- Preserve deletion markers. A stale device must not resurrect a removed film. Undo is a new restore operation that retains the original record and order.
- Pull changes incrementally with a durable cursor and deterministic tie-breaking. Advance the cursor only after the batch is committed locally. An expired change history requires a safe full reconciliation.
- On network or quota errors, retain the outbox and reduce retry frequency. Distinguish transient restrictions from authentication failures. Resume only with a valid session for the same account and successful service checks; avoid treating every quota as a monthly reset.
- Merge local records into place instead of discarding cached movie details. Newly restored catalog films can fetch missing metadata and posters in bounded background work.

## Exiting Supabase

### Stop cloud sync

Pull the latest accessible remote changes and verify the local record count before disconnecting. Keep locally pending edits. Export the personal library and optionally create a full device backup. Turn off sync without deleting local records.

A disconnected device cannot contain cloud changes it never downloaded. If Supabase is unavailable, exit with the data already present locally and report the unverified remote portion rather than promising that every device is complete.

### Move to another hosted service or our own backend

1. Create an administrator-controlled database export and a provider-neutral personal-data export. Local exports provide an additional recovery path for unsent changes.
2. Import into the replacement service, preserving application record IDs, user ownership, original dates/order, notes and deletion state. PostgreSQL storage can reuse much of the application schema; another database needs a field/schema conversion.
3. Migrate authentication separately. Preserve application user identity or maintain an explicit mapping to the new identity provider. Existing sessions need not remain valid, and password/OAuth compatibility must be verified; renewed login or a password-reset flow may be necessary.
4. Verify ownership isolation, counts, representative notes, timestamps, deletion/Undo and recovery before cutover. Do not run two unrestricted writers against independent backends.
5. Release the new provider adapter/configuration. Reconcile pending device edits against the imported revisions using the same conflict and idempotency rules. Preserve snapshots of the old provider until migration is verified.

The initial direct-to-Supabase integration should assume a client update may be needed for a provider change. Do not promise a transparent endpoint swap when authentication issuers, tokens and policies also change.

### Self-host Supabase

This retains more of the existing authentication/API model, but requires operating the server, updates, security, backups and restore checks. A hosted-to-self-hosted move still requires testing application data, auth configuration, keys and login flows; a SQL dump alone is not the entire application.

## Verification before enabling real cloud sync

- Existing schema-3 library migration, portable ordering and complete export/import round trip.
- Atomic local writes/outbox persistence through process termination, offline usage and quota failures.
- Duplicate submissions, interrupted uploads/downloads and cursor recovery.
- Concurrent notes/ratings, removal from an offline device and stale Undo.
- Two-user isolation, account switching, RLS denial and session refresh/logout behavior.
- Restore on a second device with missing posters and an unavailable catalog service.
- Provider-neutral export/import migration rehearsal and local-only exit without data loss.
- Native Windows and Android login/session lifecycle checks with protected session storage.

Use synthetic data for verification. Do not upload the existing personal library as a development test.

## First external setup

Public configuration is in `supabase/project.json`. The user ran the migration and shared its success result. Live Auth health and protocol status returned HTTP 200 (`mymovielist-sync`, protocol 1). Anonymous access to the library table and download RPC returned HTTP 401/SQLSTATE 42501. These probes created no accounts and read/wrote no personal records; they do not prove authenticated two-owner isolation. Follow `supabase/README.md` for remaining access checks and email-code templates/custom SMTP. Supabase's built-in sender is not a public registration service. Signing in starts automatic account-library sync; the UI explains the uploaded fields. Current source brings the guest library into a newly registered account after a signup disclosure; existing-account sign-in still requires an explicit copy action.

## References

- [Supabase database backup and restore](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore)
- [Supabase self-hosting](https://supabase.com/docs/guides/self-hosting/docker)
- [Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security)
- [Publishable API keys](https://supabase.com/docs/guides/getting-started/migrating-to-new-api-keys)

## Account flow and profile update — October 8, 2026

`auth_flows.py` owns a bounded set of scoped, short-lived verification steps.
Only an opaque random ID enters the signed browser cookie. Signup and recovery
steps have separate purposes, so credentials cannot cross flows. Verification
and password completion serialize per step; completed, expired or account-switched
steps cannot be reused. Auth failures never claim a password was saved offline.

`account_profile.py` validates display names, the fixed 16-avatar catalog and
optional showcase settings: at most six distinct stable `record_key` values in
chosen order, plus strict boolean rating/count display preferences. Older profiles
start with an empty showcase. Supabase Auth stores these compact preferences with
the display name and avatar ID; images, descriptions and notes are not copied into
profile metadata. This is private metadata, not a public sharing permission.

Profile metadata is separate from the movie sync protocol, with a durable
device-side pending flag and generation check. Partial identity/showcase updates
merge inside the SQLite write transaction. New selections must exist in the
owner's active library; existing missing keys can be retained because profile
metadata may arrive before the library on a new device. Rendering resolves only
that owner's active rows. Removal hides a chosen film without removing its key;
Undo restores it in place. The editor lets the owner remove unavailable picks.
Unknown future avatar IDs render the default locally. Verified Auth IDs and
RLS/RPC checks still control library access; profile metadata never establishes
ownership. No schema or public permission change is needed for this private update.

Automatic sync wakes after successful local writes and runs periodically while
the app is open. Pending data survives restart. Explicit pause is remembered
across sign-out/sign-in. Header/profile status is read from the local service;
it does not send extra hosted requests for every UI poll.


## Unique profile addresses — October 8, 2026

`account_username.py` keeps a server-confirmed handle separately from the local
display name/avatar queue. Auth metadata cannot prove ownership of a name.
Migration 003 adds an inaccessible private username table with unique username
and owner constraints, authenticated first-claim/status RPCs and an anonymous
read-only username resolver over the existing consented public projection.
Concurrent inserts rely on PostgreSQL uniqueness, not an availability pre-check.
Display names can repeat; handles normalize to lowercase ASCII and remain fixed
after the first successful claim. Retrying the same claim is safe after response
loss. No automatic names are assigned to existing accounts.

The canonical public address is `https://myshelf.cloud/u/<username>`. A path-only
Cloudflare route uses the existing public-profile Worker and keeps assets/API
under `/u/*`. Existing share UUID links remain valid. Choosing a name never
publishes a profile. Private/missing profiles continue to return the same 404;
private avatars and names are not exposed by this change. Supporting visible
private-profile identities would require a separately disclosed privacy change.

The local handle cache is per account. A bounded read refresh is independent of
ordinary movie-sync pause; startup checks can recover a handle claimed elsewhere.
Only an acknowledged server result is shown as reserved. Missing setup or an
offline claim gives an explicit message without disabling private library sync.
No session tokens, notes, emails or full library records enter the public API.
Hosted migration 003 is installed and RPC availability was verified. A hosted
two-client simultaneous claim rehearsal remains a release check.


## Registration username selection and moderation — October 8, 2026

The signup state machine is email → code → username → password. The handle is
claimed with the verified short-lived Auth token and cannot be renamed. A claim
committed before a lost response is recovered on retry using the owner's existing
handle. The password step displays that confirmed handle. Once accepted, the
local cache writes only to that account, never the request's earlier guest scope.
Password recovery retains its separate email → code → password flow.

Migration 004 preserves the 003 RPC response contracts and unique constraints.
It adds a setup probe and a small private name-policy helper, enforces claims,
checks public display-name writes and suppresses disallowed legacy projections.
Privacy revocation remains possible for old invalid names. The application checks
new display-name edits before saving locally; reads preserve existing metadata.
Private film notes are never moderated. Reserved handles and short abusive words
are distinct rules; short-word substring bans would wrongly reject real names.

No real accounts are renamed, no profiles are automatically published, and no
library tables or movie records are migrated. The user applied hosted migration
004; its anonymous setup probe returned the expected username protocol 2 on
October 8. Windows 3.5.0 and Android 3.5.0 beta.1 packages already include the
corresponding application code; applying the server migration requires no rebuild.
