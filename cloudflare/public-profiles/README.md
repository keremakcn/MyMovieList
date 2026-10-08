# MyMovieList public showcases

Read-only public profile site at `https://myshelf.cloud/u/<username>`.
Requires Supabase migrations 001, 002 and 003. Existing
`https://profiles.myshelf.cloud/u/<share-id>` links continue to work.
Only the root domain’s `/u/*` path is routed to this Worker; unrelated root paths
and the movie API domain retain their existing routing. A shared link needs neither a login nor
the installed application. No profile is public until its owner explicitly opts in.

The Worker reads only the anonymous `mml_public_profile` and
`mml_public_profile_by_username` RPCs. It never receives
owner access tokens, calls privileged RPCs, uploads notes or proxies arbitrary
URLs. Only strict public fields are accepted. Missing and private profiles return
the same 404; upstream/setup errors return a redacted 503. Profile responses are
not cached. Catalog metadata alone is cached for one hour; requests go to the
existing movie gateway. Avatars and styles are bundled static assets.

The per-IP limiter permits 60 profile reads per minute, enforced using Cloudflare's
rate-limit binding. It is a per-location best-effort protection, not a global
billing cap or proof of client identity. There is no public user enumeration API.

## Development and deployment

Install Node.js LTS, then in this folder:

```powershell
npx.cmd wrangler@4 login
npx.cmd wrangler@4 dev
node --test tests/worker.mjs
npx.cmd wrangler@4 deploy --dry-run
npx.cmd wrangler@4 deploy
```

`wrangler.jsonc` contains only public configuration. Never add Supabase database
passwords, service-role keys, SMTP credentials or TMDB secrets. The separate
Worker and hostname preserve the existing `watchlist-api` deployment.

The gateway uses a Custom Domain, which supports calls from another Worker on
the same zone: [Cloudflare Custom Domains](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/).

After deploying, apply `../../supabase/migrations/002_public_showcases.sql` and
`../../supabase/migrations/003_unique_usernames.sql` in the
Supabase project SQL Editor. The desktop/Android source includes the controls;
existing binaries need a later rebuild to include them.

Check a dedicated test owner's shared link from a signed-out browser, then revoke
sharing and reload. Already seen/copied information cannot be recalled. An offline
revocation remains pending until the account is signed in and connected.

The root-domain route requires an existing proxied DNS record in the zone.
Static assets and the anonymous API stay under `/u/_assets/*` and `/u/_api/*`,
so no unrelated root endpoints need to be routed. See [Cloudflare routes](https://developers.cloudflare.com/workers/configuration/routing/routes/).
