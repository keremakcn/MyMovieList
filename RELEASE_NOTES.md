# MyMovieList v3.3.0 — Movie Discovery Without API-Key Setup

A fresh look for your personal film library, with a cleaner desktop experience and responsive layouts. Keep your ratings, reactions and personal notes on your own computer, without publishing them to a public profile.

## What's new

- Movie discovery works without a personal TMDB account or token, through the shared Cloudflare gateway at `api.myshelf.cloud`.
- Settings no longer asks for API credentials; obsolete saved tokens are removed on startup while library data stays local.
- Redesigned interface with charcoal surfaces, lavender accents, refined typography and consistent icons.
- A cleaner library with compact statistics, aligned cards and one-line notes that open on the detail page.
- Full-height desktop sidebar that scrolls with the collection, a compact tablet rail and fixed bottom navigation on phones.
- A new Explore landing page with film, filmmaker and studio starting points.
- Refreshed film details, profiles, settings, editing and taste onboarding screens.
- Streamlined recommendation controls with automatic discovery-mode switching.

## Fixes and polish

- Improved keyboard focus after removing films, adding suggestions and changing taste selections.
- Removing a film from its editor now hides the full form; Undo restores it.
- Taste-search retries return to the failed page.
- More consistent loading, empty, hover and focus states.

## Upgrading

- Close the old application, extract the release ZIP and open `MyMovieList-v3.3.0.exe`.
- Your existing library, notes, ratings, favorites and settings remain in `%APPDATA%\MovieWatchlist`. No manual data transfer is needed when upgrading from a standard release.
- An explicit `MOVIE_WATCHLIST_DATA_DIR` override is still respected.
- The earlier frontend preview's separate `data/` library is not automatically merged into your main library.
- Recommendation ranking and the database schema are unchanged.
- Validation: 68 automated tests, including credential-free gateway requests, legacy-token cleanup and desktop data-path checks, ten desktop pages and responsive browser checks at 320, 390, 768 and 1024 CSS pixels. Physical phone testing is still pending.
