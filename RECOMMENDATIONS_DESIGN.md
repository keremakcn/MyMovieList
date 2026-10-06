# Local recommendation model

`recommendation_model.py` contains pure preference modelling, candidate scoring and list selection. `recommendations.py` coordinates the shared public catalog, persistent metadata cache, local exclusions and session/history state. Routes handle rendering and device-language projection.

## Evidence

Ratings combine absolute preference with the user's average rating. Ratings of 4 or less remain negative even when the same film is a favorite or an onboarding selection. Unrated favorites and explicit liked onboarding picks provide positive evidence; merely adding an unrated movie does not.

Feature IDs are independent of translated names. Genres, theme keywords, director IDs and the first six distinct cast IDs provide the main evidence; release decade and original language provide small secondary signals. Shared franchises and directors discount repeated evidence. Priors keep a single enthusiastic rating from becoming a strong preference. Confidence reflects usable evidence and consistency, so a large collection of moderate positive ratings can still personalize suggestions.

Default weights are genres 0.34, keywords 0.30, directors 0.19, cast 0.11, decades 0.04 and original language 0.02. Missing metadata falls back to the available signals. These are hand-chosen heuristics, not accuracy measurements or a trained collaborative model. Notes are neither parsed nor scored.

## Public catalog and privacy

Ten fixed public feeds supply popular genre groups, pre-2000 classics and a rotating original-language selection (Japanese, Korean, French, Spanish, Hindi, Turkish, German and Italian). Filters and detail-enrichment IDs are independent of the private preference profile. Personal notes, ratings, favorites, library IDs and director/theme preferences are never sent as recommendation filters or seed IDs.

The public pool is capped at 1,200 unique movies, refreshed after 12 hours or explicitly with New suggestions, and persisted in the existing settings table. Only public summary/feature data enters this cache. Catalog metadata reuses `movie_metadata`, including the bilingual content cache. No new schema migration is needed.

Sources are interleaved before enriching at most 24 public candidates per fetch. Credits, keywords and translations share one verified detail request, with at most four simultaneous requests. A wholly failed detail batch stops remaining optional requests; genre-based suggestions stay available. Candidate and metadata requests reuse existing single-flight/cache protection. Existing library metadata is read locally rather than fetching every saved movie during recommendation loading. Old entries without theme IDs retain genre/credit-based scoring until their metadata is updated.

## Selection and session behavior

- Exclude all library IDs, including recently removed records, plus explicitly hidden suggestions. Reject invalid, adult, future-release and duplicate candidates.
- Score taste fit, repeated negative evidence, a vote-count-adjusted quality prior and the mode's novelty preference.
- With sufficient evidence and available alternatives, target 8, 5 or 2 familiar picks per ten for Close to my taste, A little discovery and Surprise me. A weak profile reduces the familiar mode to six. Established rich metadata can distinguish novel themes within an otherwise familiar genre.
- Greedy diversity uses genre, keyword, director and cast overlap. Weighted genre coverage keeps secondary positive interests present. Soft caps prefer at most one film from a franchise and two from a director, while theme limits adapt to that theme's share of positive evidence. Caps relax when alternatives are exhausted.
- Recent picks from all modes are deprioritized, with the last 50 IDs retained per mode. Sparse pools may repeat rather than produce duplicates or empty lists.
- Rank only a 30-movie session reserve instead of the entire pool. Adding or hiding a film removes it without moving the other visible cards. Exhausted reserves refill locally.
- Session cards stay stable until refresh or restart. New ratings/favorites update the next explicit refresh; a profile fingerprint shows a reminder without including notes or translated titles. A failed refresh preserves the current cards and does not advance the public-feed cursor.

## Verification and limits

Run `python -m pytest -q`. Model/service regression scenarios include rich feature ranking, secondary interests, single-versus-consistent theme preference, negative feedback, language/identity invariance, public-request privacy, restart/offline caches, damaged data, reserve refill, concurrency and mode/refresh behavior.

For isolated UI checks, run `python tests/recommendations_fixture_server.py`, then `node tests/recommendations.e2e.cjs` with Playwright available. The fixture uses disposable data and mocked provider responses. It never opens AppData. `PLAYWRIGHT_MODULE` and `EDGE_PATH` can select an existing local test runtime.

Synthetic timings and behavioral fixtures demonstrate implementation properties, not recommendation accuracy for real users. Catalog coverage remains limited by the fetched public pool, enriched subset and provider availability. Held-out ratings and explicit user feedback are the next evidence needed to tune weights and evaluate relevance; private notes remain a separate future feature.
