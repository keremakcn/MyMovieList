# MyMovieList cloud setup

Status: optional accounts enabled in source, October 8, 2026. The hosted SQL
001 was applied on October 7; optional sharing migration 002 was applied on
October 8, followed by username migration 003. Registration/name-policy migration
004 was applied by the user and its anonymous setup probe verified on October 8
(`mymovielist-usernames`, protocol 2). Resend SMTP, email verification, password recovery and
library restoration on a second isolated device instance were tested by the user.
The updated registration/profile UI and sync behavior are covered by local tests.
Windows 3.5.0 and signed Android 3.5.0 beta.1 downloads were rebuilt with the
registration, profile and sync modules. No further rebuild is needed after applying 004. Hosted two-owner
access separation and native Android lifecycle still require final release QA.

## Apply the database setup

1. Open the MyMovieList project in the Supabase dashboard.
2. Open **SQL Editor → New query**.
3. Paste the complete contents of `migrations/001_personal_library.sql`.
4. Click **Run**. The expected result is **Success. No rows returned.**
5. Run `select public.mml_cloud_status();`. It should report service
   `mymovielist-sync` and protocol `1`.

The migration is transactional and can be run again without deleting records.
No accounts are created and no device library is imported by this SQL.
Only its own table policies and functions are replaced; it does not change access
to unrelated application tables.

`project.json` contains the Project URL and a **publishable** key. These are public
client configuration. Never add a database password, `sb_secret_...` key, or
`service_role` key to this file or to a desktop/Android package.

## Enable optional public showcases

The original private library migration 001 is already installed. For public
showcases, run the complete `migrations/002_public_showcases.sql` in **SQL Editor
→ New query → Run**. Expect **Success. No rows returned.** It is transactional,
safe to rerun, and does not publish any profile or change private library RLS.

Live project status: the user applied 002 successfully on October 8. Anonymous
public projection is available; anonymous library reads and owner status/write
RPCs are denied. Owner status and a user-published empty showcase were verified.
A live two-owner
sharing rehearsal is still required before a public binary release.

The `myshelf-profiles` Worker is deployed at `profiles.myshelf.cloud`; its source
and deployment instructions are in `../cloudflare/public-profiles`. Only a public
Supabase key is used. There is no service-role key or privileged SQL access in
the application, so this admin setup must be run in the dashboard.

After setup, open **Profile → Share your showcase**, review the displayed fields
and explicitly enable sharing. Copy the link and open it in a signed-out browser.
Turn sharing off and verify that another fresh visit cannot read the profile.
Notes, email, custom films and unselected film IDs must never appear.
If offline, privacy removal remains pending until the account is signed in and
connected. Do not assume that signing out revokes a public link.

The public schema exposes only the narrow `mml_public_profile(uuid)` and,
after migration 003, `mml_public_profile_by_username(text)` public projections
to anonymous clients.
Owner status/write RPCs require authentication. The sharing table is in
`mml_private` with no direct client privileges.

## Authentication emails

Keep email/password sign-in and email confirmation enabled in Supabase Auth.
The shared interface accepts email codes, avoiding localhost redirects or deep
links for verification and password recovery.

1. In Auth's email templates, replace **Confirm signup** with
   `email-templates/confirm-signup.html`. Suggested subject:
   `MyMovieList — Confirm your email / E-postanı doğrula`.
2. Replace **Reset password** with `email-templates/reset-password.html`.
   Suggested subject: `MyMovieList — Reset your password / Şifreni yenile`.
3. Replace **Magic link or OTP** with `email-templates/verification-code.html`.
   Suggested subject: `MyMovieList — Verification code / Doğrulama kodu`.
   All three templates must use `{{ .Token }}`. New accounts may receive the
   Confirm signup template; confirmed accounts receive Magic link or OTP.
   The app verifies codes through Supabase Auth before opening a password form.
4. Configure a custom SMTP sender before public registration. Supabase's built-in
   sender currently delivers only to project team members with a very small limit.
   Keep SMTP credentials in the Supabase dashboard; never bundle them in the app.

The sender domain/DNS requirements depend on the chosen email provider. Do not
disable email confirmation to bypass missing SMTP. Verify delivery, expired codes,
confirmation and recovery using dedicated test accounts.

## Account experience

`"accounts_enabled": true` in `project.json` enables accounts in the current
source. Rebuilding is necessary before this appears in distributed applications.

- Registration: email → code → unique username → password → optional display name/avatar.
  Supabase OTP creates a pending account; a short-lived verified server-side
  step allows password creation. Existing confirmed users are returned to
  password sign-in without changing their passwords.
- Sign-in uses email and password; it does not send an email code.
- Password recovery: email → recovery code → new password. Recovery credentials
  stay only in server memory for up to ten minutes; never in browser cookies,
  URLs, localStorage, exports or the persistent account session vault.
- Signed-in account libraries sync automatically unless the user paused sync.
  Successful local writes wake the background worker, with brief coalescing.
  Network/quota failures retain the outbox and use bounded retry delays.
- The header contains account access and a profile menu. Import/export is in
  Settings. Conflicting notes keep both versions and can be reviewed in Profile.
- Guest adoption is explicit and leaves the original library intact. Copied
  private notes are included in automatic sync; the UI states this before copying.
- A private display name and one avatar ID are stored in `user_metadata.mml_profile`
  through the authenticated Auth user endpoint. The SVG avatar pack ships in
  `static/avatars`; no Storage bucket or additional SQL migration is needed.
  Profile edits have a persistent local queue and a generation guard so an upload
  acknowledgement cannot erase a newer edit. Profiles use last successful upload
  semantics across devices; movie notes retain the stronger revision/conflict protocol.
  User metadata is used only for display/onboarding, never authorization.
- Windows sessions use DPAPI. Android Keystore support is prepared but needs
  native testing. Unsupported OSes use memory-only sessions.
- Pause retains the local account library. Sign-out returns to the guest library;
  account files and pending edits remain on the device.

## Data and access

- `public.mml_library`: private personal records, keyed by authenticated owner
  and `tmdb:<id>` or `custom:<uuid>`.
- Stored fields: status, personal rating/note/favorite, watched date, original
  addition time/order and deletion marker. Custom films also keep the user's
  title/year/genre.
- Public posters, synopses, cast/crew and TMDB credentials are not accepted.
- Anonymous clients cannot read the library or call synchronization operations.
- Signed-in users can read only their own records through Row Level Security.
- Clients cannot directly insert, update or hard-delete records. The write RPC
  checks the owner and expected server revision before making an atomic change.
- `mml_private.sync_heads` serializes revisions per account so an incremental
  download does not miss a transaction committed later.
- `mml_private.sync_receipts` records successful operation IDs and request hashes
  without copying notes into a second history table. A retry cannot repeat an
  operation or reuse its ID for a different request. Receipts currently remain
  until account deletion; their space must be included in quota monitoring.
- Cloud privacy relies on authentication and database permissions. This is not
  end-to-end encryption; project administrators can access the stored data.

## Protocol v1

Public health check: `mml_cloud_status()`.

Authenticated write: `mml_push_change(p_operation_id, p_record_key,
p_expected_revision, p_data)`. Expected revision `0` creates a new logical film.
On a stale revision it returns `status: conflict` with the current remote record;
the device must keep both versions and ask the user to resolve conflicting
personal data. An applied or replayed operation returns its original revision.
An old receipt does not mean the remote record still has that revision: pull
changes after acknowledging it.

Authenticated download: `mml_pull_changes(p_cursor, p_limit)`, with at most 200
records per page. Start with cursor `0` on a new account-specific local database.
Advance the cursor only after committing the entire page locally. Changed rows
are ordered by server revision; a deleted film remains a row with a deletion
marker. Undo is a subsequent revision clearing that marker. Original addition
time and order cannot be changed by an update or restore.

Personal data has exactly these keys:

```json
{
  "status": "Watchlist",
  "rating": null,
  "note": null,
  "favorite": false,
  "watched_date": null,
  "added_at": "2026-10-07T12:00:00+00:00",
  "order_key": "00000000000000000001:00000000-0000-4000-8000-000000000001",
  "deleted_at": null,
  "custom": null
}
```

The device must persist each operation's UUID and exact payload until it receives
an acknowledgement. For custom films `custom` is an object with `title`, nullable
`year` and nullable `genre`. Recommendation survey choices, dismissal history
and device settings are not included in protocol v1.

## Developer verification

This uses PGlite, an isolated WebAssembly PostgreSQL runtime. It is a development
test dependency only; Node.js and PGlite are not needed by application users.

```powershell
Set-Location -LiteralPath "C:\Users\AKCAN\Desktop\movie-watchlist\supabase"
npm.cmd ci --ignore-scripts
npm.cmd test
```

Tests create two synthetic owners and mock the Supabase `auth.uid()` contract
inside the isolated database. They check RLS ownership, anonymous denial, direct
write denial, migration reruns, duplicate retries, stale edits, tombstones/Undo,
immutable addition order/time, Unicode, invalid values and incremental pages.
They do not call the hosted project or open personal SQLite libraries. Do not
paste the test bootstrap into a real Supabase SQL Editor.

The hosted migration and anonymous-denial checks have passed, and the user
verified authentication and restoration with one account on two instances.
Authenticated hosted two-owner isolation and multi-connection PostgreSQL
concurrency checks remain public-release requirements. Local tests do not
certify the live project's settings or authentication email delivery.

## Remaining live verification

The migration is applied and preliminary anonymous-denial checks passed. Follow
`../CLOUD_SYNC_DESIGN.md` and `../QA_RESULTS.md`. Isolated SQL and synthetic
two-device tests do not replace authenticated hosted two-owner verification,
multi-connection PostgreSQL checks, email delivery or Android device tests.
Do not upload a personal library for development verification.

## References

- [Supabase API keys](https://supabase.com/docs/guides/getting-started/api-keys)
- [Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security)
- [Database functions and execution privileges](https://supabase.com/docs/guides/database/functions)
- [SMTP limits and custom delivery](https://supabase.com/docs/guides/auth/auth-smtp)
- [Email templates and tokens](https://supabase.com/docs/guides/auth/auth-email-templates)


## Unique usernames — migration 003

Hosted migration 003 was applied and its RPC availability verified on October 8.
For a new project, run **SQL Editor → New query → Run** using all of
`migrations/003_unique_usernames.sql`. Expected: **Success. No rows returned.**
It is transactional, safe to rerun, and does not rename accounts, change private
library policies, expose private identities or automatically publish showcases.

- `mml_private.usernames` owns handles independently of Auth display metadata.
  Unique constraints arbitrate simultaneous claims, one username per owner.
- Usernames are canonical lowercase ASCII, 3–24 characters, start with a letter,
  and use letters/digits/underscores. Reserved system names cannot be claimed.
- Authenticated `mml_username_status` and `mml_claim_username` use `auth.uid()`.
  Anonymous claims and direct table access are denied. Repeating an accepted
  claim is idempotent. A claimed username stays fixed; display names remain editable
  and non-unique. Username reservation requires connectivity and does not queue
  an unconfirmed success locally. A lost response can safely be retried.
- New public lookup resolves the username to the existing consented projection;
  private and missing profiles still have identical `found:false` results.
  Existing UUID links and RPC contracts remain unchanged for older clients.
- App status reads the cached handle locally. The account worker checks the
  authenticated owner’s handle at bounded intervals, including when movie sync
  is paused. Missing 003 does not interrupt private movie/profile synchronization.

After setup, open **Profile → Edit profile**, choose a test username, then verify
the URL `https://myshelf.cloud/u/<username>` from a signed-out browser. A different
account must not claim the same name, even with different capitalization.
Two accounts may both use the display name “Kerem”. Private notes never enter
the username table or public projection.


## Registration and identity-name rules — migration 004

Apply `migrations/004_registration_usernames.sql` **after 001 → 002 → 003** in
SQL Editor. Expected: **Success. No rows returned.** This transaction is safe
to rerun. Do not reapply older migrations alone afterwards: they replace RPC
definitions; if they must be reapplied, finish by running 004 again.

- New registration verifies email before claiming a username, then requests a
  password. A verified existing account returns to ordinary password sign-in.
- `mml_username_protocol()` is a read-only setup check performed before sending
  a registration email. Missing 004 does not disable existing-account sign-in,
  password recovery or private library sync.
- Usernames stay immutable. There is no rename RPC, alias registry or revision
  column. Existing users without a handle can still make their first claim from
  Edit profile. Display names remain non-unique and avatars remain editable.
- Python and private SQL validation share reviewed TR/EN name rules, including
  distinctive abusive roots and common numeric/separator variants. Short terms
  use boundaries so legitimate names such as Nazım and Nazife are accepted.
  This is a limited deterministic policy, not comprehensive language moderation.
- Server validation cannot be bypassed with an older app or a direct claim RPC.
  Existing disallowed identities are not renamed or deleted; their public
  projections are suppressed. Owners can still revoke public sharing.
- Only usernames and display names are filtered. Personal movie notes, ratings,
  favorites, ordering and library ownership/permissions remain unchanged.

Verify `select public.mml_username_protocol();`: service must be
`mymovielist-usernames`, protocol `2`. Test real SMTP registration with an account
you control after setup. Automated tests use synthetic accounts only.
