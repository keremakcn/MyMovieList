# Watchlist TMDB gateway

Shared movie/series gateway. No credentials belong in this directory.

## Dashboard setup

1. Create `watchlist-api` and set Secret `TMDB_TOKEN` to the TMDB Read Access Token (without `Bearer`).
2. In Edit code replace the starter code with `worker.js`, then Deploy.
3. `/health` returns `setup_required` until both rate limiting bindings are configured. This is intentional: catalog requests fail closed.
4. Deploy this directory with Wrangler 4.36 or newer to apply `wrangler.jsonc` bindings (authenticate to the correct Cloudflare account first). Existing TMDB Secret stays in Cloudflare. Check namespace IDs 1001/1002 are not already used by unrelated limiters.
5. `/health` returning `configured` confirms configuration only. Verify `/3/search/tv?query=Dark` for real upstream access before connecting applications.

Applications are NOT yet switched to this gateway. They will use its `/3/` base URL without sending a TMDB token. Images continue to use TMDB image URLs.

## Limits and privacy

This is an anonymous public metadata API, not authenticated application-only access. No CORS permissions are granted; this does not prevent other servers from calling it. Shared-IP users share the client limit. Cloudflare bindings are eventually consistent and per-location; the upstream limiter is NOT a strict global spending cap. Distributed abuse remains possible. Set plain variable `DISABLED=true` to stop catalog requests, including cached responses.

Only fixed TMDB catalog routes and validated parameters are forwarded. Incoming authorization/cookies are never forwarded. Successful metadata is cached (search 2 minutes, other requests 1 hour); errors are not cached. There is no app-level request logging. Review Cloudflare observability retention separately because request URLs can contain search terms. Notes and library contents are never part of this API.

## Verification

Run `node --test worker.test.js`. Tests mock Cloudflare bindings, cache and TMDB; live deployment still requires verification. Maintain TMDB attribution in both applications.

Reference: https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/
