# Local recommendation model

`recommendation_model.py` contains pure preference modelling, candidate scoring and list selection. `recommendations.py` coordinates the shared public catalog, persistent metadata cache, local exclusions and session/history state. Routes handle rendering and device-language projection.

## Evidence

Ratings combine absolute preference with the user's average rating. Ratings of 4 or less remain negative even when the same film is a favorite or an onboarding selection. Unrated favorites and explicit liked onboarding picks provide positive evidence; merely adding an unrated movie does not.

Feature IDs are independent of translated names. Genres, theme keywords, director IDs and the first six distinct cast IDs provide the main evidence; release decade and original language provide small secondary signals. Shared franchises and directors discount repeated evidence. Priors keep a single enthusiastic rating from becoming a strong preference. Confidence reflects usable evidence and consistency, so a large collection of moderate positive ratings can still personalize suggestions.

Default weights are genres 0.34, keywords 0.30, directors 0.19, cast 0.11, decades 0.04 and original language 0.02. Missing metadata falls back to the available signals. These are hand-chosen heuristics, not accuracy measurements or a trained collaborative model. Notes are neither parsed nor scored.

## Public catalog and privacy

Ten fixed public feeds supply popular genre groups, classics across all genres and a rotating original-language selection (Japanese, Korean, French, Spanish, Hindi, Turkish, German and Italian). The classic feed sorts by rating with at least 1,000 votes and a rolling ten-year release cutoff. It uses only filters supported by the existing gateway; no worker deployment is required. Filters and detail-enrichment IDs are independent of the private preference profile. Personal notes, ratings, favorites, library IDs and director/theme preferences are never sent as recommendation filters or seed IDs.

The public pool is capped at 1,200 unique movies, refreshed after 12 hours or explicitly with New suggestions, and persisted in the existing settings table. Only public summary/feature data enters this cache. Catalog metadata reuses `movie_metadata`, including the bilingual content cache. No new schema migration is needed.

Sources are interleaved before enriching at most 24 public candidates per fetch. Credits, keywords and translations share one verified detail request, with at most four simultaneous requests. A wholly failed detail batch stops remaining optional requests; genre-based suggestions stay available. Candidate and metadata requests reuse existing single-flight/cache protection. Existing library metadata is read locally rather than fetching every saved movie during recommendation loading. Old entries without theme IDs retain genre/credit-based scoring until their metadata is updated.

## Selection and session behavior

- Exclude all library IDs, including recently removed records, plus explicitly hidden suggestions. Reject invalid, adult, future-release and duplicate candidates.
- Score taste fit, repeated negative evidence, a vote-count-adjusted quality prior and the mode's novelty preference. Algorithm version 3 adds bounded recognition and classic bonuses, described below.
- With sufficient evidence and available alternatives, target 8, 5 or 2 familiar picks per ten for Close to my taste, A little discovery and Surprise me. A weak profile reduces the familiar mode to six. Established rich metadata can distinguish novel themes within an otherwise familiar genre.
- Greedy diversity uses genre, keyword, director and cast overlap. Weighted genre coverage keeps secondary positive interests present. Soft caps prefer at most one film from a franchise and two from a director, while theme limits adapt to that theme's share of positive evidence. Caps relax when alternatives are exhausted.
- Recent picks from all modes are deprioritized, with the last 50 IDs retained per mode. Sparse pools may repeat rather than produce duplicates or empty lists.
- Rank only a 30-movie session reserve instead of the entire pool. Adding or hiding a film removes it without moving the other visible cards. Exhausted reserves refill locally.
- Session cards stay stable until refresh or restart. New ratings/favorites update the next explicit refresh; a profile fingerprint shows a reminder without including notes or translated titles. A failed refresh preserves the current cards and does not advance the public-feed cursor.

## Recognition and portraits — 2026-10-10

Vote counts supply a logarithmic recognition proxy, capped at 10,000 votes. Reception uses the existing Bayesian adjusted rating. An acclaimed-classic label requires at least ten years since release, 1,000 votes and an average of 7.4 or higher. This is an application heuristic for recognizable, well-received classics; it is not an official cult-film classification. Older, unpopular or poorly rated films do not qualify through age alone.

Recognition/reception contributes at most 0.18 and classic recognition adds at most 0.22. Recent films (up to four years old, at least 50 votes) can gain at most 0.14 from the first three credited actors' capped popularity, fading with age. Reception suppresses the entire bonus for poorly received films. These bonuses have weights 1.15/1/0.55 in familiar/balanced/explore modes and are reduced to a quarter for off-taste candidates once a profile is ready. Genre coverage, novelty lanes, negative evidence, exclusions and diversity still apply. This favors suitable classics without making every recommendation a classic or suppressing discovery completely.

TMDB person popularity reflects daily attention, not acting quality or permanent fame ([TMDB documentation](https://developer.themoviedb.org/docs/popularity-and-trending)). It is deliberately a weak signal. Saved ratings/favorites already supply stronger evidence for actors the user likes. No private actor preference is sent to the server.

Genre IDs survive ranking and translate only at render time. New public-pool entries use the version-3 cache key; a verified version-2 pool remains available offline until it can be refreshed. Personal-library rows and preferences are retained. Portrait URLs and capped person popularity share the existing verified `credits,keywords,translations` request. Metadata feature version 2 upgrades an old cache on its next detail request; successful null portraits count as complete. Failed optional upgrades reuse verified cached content and a retry cooldown. Photo/recognition fields merge by numeric person ID without changing notes, ratings, favorites, watched dates, film identity or order. No SQL migration or cloud-storage upload of portraits is needed. Remote image bytes require connectivity or browser caching; names and silhouette fallbacks remain available offline.

## Verification and limits

Run `python -m pytest -q`. Model/service regression scenarios include rich feature ranking, secondary interests, single-versus-consistent theme preference, negative feedback, language/identity invariance, public-request privacy, restart/offline caches, damaged data, reserve refill, concurrency and mode/refresh behavior.

For isolated UI checks, run `python tests/recommendations_fixture_server.py`, then `node tests/recommendations.e2e.cjs` with Playwright available. The fixture uses disposable data and mocked provider responses. It never opens AppData. `PLAYWRIGHT_MODULE` and `EDGE_PATH` can select an existing local test runtime.

Synthetic timings and behavioral fixtures demonstrate implementation properties, not recommendation accuracy for real users. Catalog coverage remains limited by the fetched public pool, enriched subset and provider availability. Held-out ratings and explicit user feedback are the next evidence needed to tune weights and evaluate relevance; private notes remain a separate future feature.
