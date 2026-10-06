# Shared catalog gateway

`https://api.myshelf.cloud` serves MyMovieList, MySeriesList and MyGameList. Movie/TV routes use `/3/`; games use `/rawg/`. Personal notes, ratings, favorites and progress are never sent here.

## Configuration

- Cloudflare Secrets: `TMDB_TOKEN` and `RAWG_API_KEY`. Never commit them, bundle them in applications or put them in config files.
- Wrangler bindings: CLIENT_LIMITER 120 requests/60 seconds per client IP; UPSTREAM_LIMITER 600 requests/60 seconds for TMDB misses; RAWG_LIMITER 60 requests/60 seconds for RAWG misses.
- Deploy with Wrangler 4.36+ from this directory; the configuration keeps the existing custom domain `api.myshelf.cloud`. Existing Secrets are retained.
- `/health` reports `status` for TMDB and `games_status` for RAWG. Configuration alone does not confirm provider connectivity: verify movie, TV and game searches after deploying.

## Limits and privacy

This is an anonymous public metadata gateway, not authenticated app-only access. Shared-IP users share client limits. Cloudflare rate-limit bindings are per-location and eventually consistent: neither upstream limiter is a strict global or monthly quota cap. RAWG's free plan lists 20,000 requests/month for the shared key; monitor provider usage separately. Cache cannot guarantee the quota will last. Keep RAWG attribution in each app page that uses its data.

Only fixed catalog endpoints and validated parameters are forwarded. Caller credentials and cookies are never forwarded. RAWG credentials in pagination URLs are removed: `next` and `previous` expose booleans only. RAWG exceptions are never logged because URLs contain its key. Review Cloudflare request-log retention separately: search text is part of request URLs.

Successful TMDB searches cache for 2 minutes, movie trends for 15 minutes, movie genres for 24 hours, and other movie/TV details and discovery lists for 1 hour. RAWG searches cache for 10 minutes and game details for 6 hours. Errors are not cached. Client limits apply even to cache hits; successful cache hits do not consume upstream-limit requests. Set `DISABLED=true` to stop all catalog traffic, or `RAWG_DISABLED=true` to stop games alone, including cached responses.

## Movie discovery

MyMovieList uses these fixed public catalog routes for its Explore page:

- `/3/trending/movie/week` (also supports `/day`).
- `/3/movie/top_rated`.
- `/3/genre/movie/list`.
- `/3/discover/movie` for recent releases and genre browsing.

Discovery supports bounded page numbers (1–500), locale, the existing genre/company/vote-count/sort filters, and `primary_release_date.gte` / `primary_release_date.lte`. Dates must be valid calendar dates in `YYYY-MM-DD` format; reversed ranges are rejected. Movie discovery continues to force `include_adult=false` and accepts only `include_video=false`. Requests cannot select an upstream host, inject credentials, repeat parameters or reach authentication/account APIs. Query parameters are sorted for consistent cache keys, and provider credentials are added only after constructing the cache key.

Deploy this updated Worker before using the new Explore lists: the previous allowlist rejects the trend, top-rated and movie-genre routes. No new bindings or Secrets are required. Updating application files alone does not update the live Worker.

Movie details also allow `append_to_response=credits,keywords,translations` so the app can save full credits, recommendation theme IDs and bilingual synopses in one request. Existing shorter combinations remain supported. Reversed append order shares the same cache key; unknown/duplicate additions and account endpoints remain blocked. Deploy this allowlist before running the richer recommendation client; no new binding or credential is needed.

Run `node --test worker.test.js games.test.js` for mocked regression checks. Client Python code uses bounded local caching and coalesces identical simultaneous requests. Desktop image downloads use provider image URLs directly; images are not stored in this Worker.

Provider references: [TMDB](https://developer.themoviedb.org/) · [RAWG](https://rawg.io/apidocs) · [Cloudflare rate limits](https://developers.cloudflare.com/workers/runtime-apis/bindings/rate-limit/)
