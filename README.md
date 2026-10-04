# MyMovieList v3.3.0

**Your personal film library, with discovery ready from the start.** Version 3.3.0 uses our shared discovery service at `api.myshelf.cloud`: no personal TMDB account, API key or token is needed. Your library and private journal remain on your device. See the [release notes](RELEASE_NOTES.md) and [UI design and verification notes](UI_DESIGN.md).

A local-first personal film library for Windows and the browser. Flask + Jinja + SQLite, with a small JavaScript interaction layer and a native pywebview window.

Keep your collection close, explore the people and studios behind your favorite films, and find something to watch tonight. Saved library information and downloaded posters remain available offline; discovery uses TMDB.

## Your films. Your thoughts. Your space.

Not every thought needs an audience. A film might leave you angry, challenge your beliefs, or bring back a memory you would rather keep to yourself. Write an honest reaction, a detailed review or a single sentence—without having to turn it into something for everyone else to read.

MyMovieList is also your personal film journal. Your ratings and notes are saved on your own computer, without being published to a public profile or shared with other users. Your notes are not sent to TMDB.

Local storage is not encryption: someone with access to your database or its backups could read your notes. Keep those files protected if they contain personal thoughts.

## What's new in 3.3.0

- **No API-key setup:** search movies, explore actors/directors and studios, and get recommendations through our shared Cloudflare service.
- **Our own discovery address:** `https://api.myshelf.cloud` replaces the default `workers.dev` address.
- **Simpler Settings:** no credential form; legacy local TMDB token settings are removed on startup.
- **Local privacy preserved:** notes, ratings, favorites and viewing history stay on your computer. Only catalog requests and search terms pass through the discovery service.
- **Verified Windows integration:** 68 automated tests passed, and live search was verified in the packaged Windows app.

## Interface improvements retained from 3.2.0

- **A new visual identity:** charcoal surfaces, lavender accents, editorial headings and a shared SVG icon set.
- **A more focused library:** compact statistics, clearer filters, aligned movie cards and one-line note previews. View note opens the detail page without expanding the card.
- **Navigation that fits the screen:** the desktop sidebar extends down the page and scrolls with the collection. Tablets use a compact rail; phones use a fixed bottom navigation bar.
- **A new Explore landing page:** film, filmmaker and studio starting points lead into the existing connected discovery experience.
- **Simpler recommendation controls:** discovery mode and New suggestions sit together; changing mode applies immediately. The recommendation algorithm is unchanged.
- **Consistent pages:** refreshed film details, actor/director and company profiles, taste onboarding, settings and editing forms.
- **Smoother interactions:** improved loading and empty states, keyboard focus after quick actions, and removal/Undo behavior in the editor.

The existing library features, recommendation modes and database schema are retained. The Windows release continues using your library in `%APPDATA%\MovieWatchlist`, including its notes, ratings, favorites, saved posters and settings.

## Included from 3.1.1

- **New suggestions:** refresh recommendations without restarting the app. Normal page reloads keep the current selection.
- **Fewer repeats:** the candidate pool expands on refresh, and up to 50 recently shown films per mode are held back while alternatives exist.
- **Distinct discovery modes:** Close to my taste, A little discovery and Surprise me use different familiarity and novelty targets.
- **Reliable refresh:** library and hidden films stay excluded; failed refreshes preserve the current selection.
- **Simpler cards:** removed the Why this film explanation panels.
- **Validation:** 46 automated tests plus isolated browser checks for repeated refreshes and error recovery.

## Introduced in 3.1

- **For you:** personal suggestions based on ratings, favorites and taste selections, ranked locally.
- **Taste onboarding:** choose films you enjoyed; new selections enter your library as watched without duplicating existing entries.
- **Session-based discovery:** stable picks while the app is running, with a fresh selection on restart and fewer repeats from the previous session.
- **Discovery controls:** choose how adventurous your picks should be, add films directly or hide individual suggestions with Undo.
- **Simple recommendation cards:** focus on the film and its actions without explanation panels.

## Library and discovery features

- **Explore:** one search box with Movies, Actors, Directors and Companies checkboxes. Movies, actors and directors start selected. Suggestions, results and pagination respect the selection; press Search to apply changed filters.
- **One-click collection:** add from search, film details, a person's filmography or a studio's films without leaving the page. Existing entries link to the rating/note editor.
- **Connected discovery:** film → actor/director → filmography and film → studio → films. Writers and producers are also linked from film details, with multiple contributions preserved and duplicate names within a credit group removed.
- **Your library:** favorites independent of watched status, 1–10 ratings, notes, watched dates, title filtering across the entire library, and eleven sort choices.
- **Compact cards:** aligned posters, two-line titles, fixed action rows and a single-line note preview. View note opens the note on the movie detail page; cards never expand. Lazy-loaded posters and 36 films per page.
- **Recoverable removal:** a 10-second Undo notification plus a permanent **Recently removed** view. Restore preserves the original row, metadata and ordering. There is no automatic purge.
- **Keyboard support:** Ctrl/Command+K focuses search. Ctrl/Command+Z triggers the most recent visible Undo when you are not editing text. Standard Tab/Enter controls work throughout.
- **Local storage:** saved film information and downloaded posters remain available offline. If a poster download fails, its online URL is retained; the rest of the movie is still saved.

## Personal recommendations

Open **For you** to get up to ten suggestions, or choose **Choose films you love** for a short, skippable taste survey.

- Start with a varied selection of up to 12 films, including different genres, older films and non-English cinema. Browse another selection or search for a title; your selections remain checked while browsing.
- Pick 3–5 films you enjoyed (up to 24). On **Save picks & continue**, new films enter the library as **Watched**, with no invented rating, favorite or watched date. Existing entries retain their personal data and status. Previously removed entries are restored with their metadata.
- Survey likes are separate from favorites and ratings. Editing your picks changes their recommendation signal without deleting library films. Skipping does not add anything.
- Ratings, favorites and survey likes shape a local genre profile. A single film has limited influence; repeated evidence increases confidence. Related films from the same director count as less independent evidence, and contradictory signals reduce confidence. Low explicit ratings override older survey likes.
- Picks stay in the same order while the app process is running, including page reloads, unless you choose **New suggestions**. Restarting the desktop app creates a fresh selection. Up to 50 recently shown film IDs per mode are kept locally; unseen candidates take priority over these recent picks. Limited candidate pools may still repeat films. Adding or hiding a film removes it from the current selection, with replacements taken from the same saved order. Editing survey picks explicitly rebuilds the selection; each discovery mode has its own session selection. In browser mode, restarting the local server starts a new recommendation session.
- Use **New suggestions** to refresh the current discovery mode at any time. Reloading the page keeps the current selection; reopening the desktop app also creates new picks. Refreshing loads the next page of eight fixed public genre queries and ranks a rolling pool of up to 800 films. Recent picks are held back while unseen alternatives exist; library and hidden films remain excluded. If an online refresh fails, the previous selection stays available. Films can appear again in later sessions if they have not been added or hidden.
- Choose **Close to my taste**, **A little discovery** or **Surprise me**. With sufficient preference evidence and available candidates, the modes target roughly 8, 5 and 2 familiar-genre films out of ten, respectively. Exploration also receives a higher novelty weight; negative ratings still count against a film. Sparse pools and limited taste evidence soften these distinctions.
- **Not interested** hides only that film; Undo and **Hidden suggestions → Show again** restore it.
- Existing library entries are excluded from new discoveries. Up to three Want to Watch entries are shown separately as films to consider tonight.

This first version uses genre-level matching, not plot-twist detection, semantic analysis of notes or a trained machine-learning model. It ranks a bounded public TMDB candidate pool locally; taste-derived IDs, notes, ratings and favorites are not sent to TMDB. Explicit title searches and fetching films you choose to add still use TMDB normally. Without enough consistent evidence, the screen labels results as starting suggestions rather than fully personal picks.

## Screenshots

Screenshots show the redesigned interface with isolated example data.

### Your movie library

Collection statistics, compact cards, quick actions and a sidebar that follows the page's full height.

![Redesigned movie library with sidebar navigation and compact movie cards](screenshots/frontend-library.png)

### Search and discovery

Search films, actors, directors and companies, or start exploring from a film, filmmaker or studio.

![Redesigned Explore page with search filters and discovery starting points](screenshots/frontend-explore.png)

## Mobile layout

On narrow screens, cards stack into a single column, controls wrap to fit, and main navigation moves to a fixed bottom bar. Notes remain compact and open on the film detail page.

Browser checks at 320 and 390 CSS pixels found no horizontal page overflow in the tested flows. Tablet and smaller desktop layouts were also checked at 768 and 1024 pixels. These are browser viewport checks, not tests on physical phones; touch interaction, the on-screen keyboard and mobile Safari still need device testing. The Windows executable does not run on phones, and the default local server is not configured for phone access over a network.

### Standalone Android beta

The new `android/` project packages the shared library code inside an Android app, so the phone does not need a running computer or a hosted server. Its library lives in private app storage and is independent of the Windows library. Phone controls have larger touch targets and 16px form text.

Android builds are tracked separately as `3.2.0-android-beta.1`; this does not replace the stable Windows release. APK is the installable format for direct downloads, while AAB is intended for a future Play Store submission. Actual device verification is required before promoting the Android beta to stable. See [Android setup, signing and data storage](ANDROID.md).

## Quick start

1. Download and extract `MyMovieList-v3.3.0-windows.zip`, then open `MyMovieList-v3.3.0.exe` on Windows. For a local build, open `dist/MyMovieList-v3.3.0.exe`, or follow the source instructions below.
2. Open the app and start exploring. No TMDB account, API key or token is required.
3. Open **Explore**, enter a title or name, choose the categories below the search box, then press **Search**.
4. Use **Add to Want to Watch** on a result or film page. A film already in your library links to its editor instead of creating another entry.
5. Manage watched status, favorites, ratings and notes in **Library**. After removal, use **Undo** or restore the film from **Recently removed**.

### Search filters

There is one search box with independently selectable categories, replacing the previous All/type dropdown:

| Filter | Includes | Selected by default |
| --- | --- | --- |
| Movies | Film title matches | Yes |
| Actors | People primarily known for acting | Yes |
| Directors | People primarily known for directing | Yes |
| Companies | Production company name matches | No |

Uncheck anything you do not want to search. Press **Search** to apply changes to the results; autocomplete uses the selected categories too. Selections stay in the URL, pagination and return links from detail pages. Select at least one category to run a search.

People are labelled by TMDB's primary profession: a director is not labelled as an actor. Writer-only and producer-only primary professions are excluded from search, but their credits and filmographies remain accessible from movie details. Classification follows TMDB's primary profession rather than checking every job a person has ever held.

Autocomplete supports **↑ / ↓**, **Enter** and **Escape**. Movie searches match titles; they do not automatically search the film's cast or director by that title. Follow the credits on the film page to explore those people.

TMDB person results are filtered page by page. Combined and profession-filtered result counts describe the current page, and another page may contain additional matches. Search, remote film details and online posters require an internet connection; locally stored library data does not.

## Run from source

Python 3.12 is tested. On Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Or use Flask's application factory:

```powershell
.\.venv\Scripts\python.exe -m flask --app app:create_app run
```

Open `http://127.0.0.1:5000`. The app is intended for one user on the local machine, not for public hosting.

## Desktop

The release executable is `dist/MyMovieList-v3.3.0.exe`. It uses `%APPDATA%\MovieWatchlist`, the same data directory as earlier releases. Close the running application before opening the new version. Replacing or moving the executable does not move or erase your library; no adjacent `data/` folder is required.

To run the native window from source after installing the desktop requirements, run `.\.venv\Scripts\python.exe run_desktop.py`.

To build the executable and a clean release ZIP:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
.\scripts\build_release.ps1
```

The desktop server binds to an available loopback port before opening the window, avoiding fixed-port collisions. Windows needs the Edge WebView2 runtime.

The build script reads `version.py`, creates `dist/MyMovieList-v3.3.0.exe`, and packages only that executable and the release notes. Upload `dist/releases/v3.3.0/MyMovieList-v3.3.0-windows.zip` and its `SHA256SUMS.txt` to your release. Personal databases, `.env` files, posters and old executables are excluded. The script accepts `-Python` if your environment is stored elsewhere.

## Data and upgrades

- Source mode: `movies.db` and `posters/` in the project directory.
- Packaged Windows release: `%APPDATA%\MovieWatchlist\movies.db` and `%APPDATA%\MovieWatchlist\posters/`.
- `MOVIE_WATCHLIST_DATA_DIR` explicitly overrides the data directory in both source and packaged mode; remove an old override if you want the default AppData library.
- Before migrating an existing database, the app creates `movies.db.before-v2-<timestamp>.bak` beside it using SQLite's backup API.
- Application version **3.3.0** keeps database schema version **2**. This release adds no schema migration.
- Migrations run in a transaction and never automatically delete duplicate records. If a legacy database contains duplicate TMDB IDs, the migration stops with a diagnostic so they can be reconciled without losing notes.
- New records store creation/update timestamps. Older records keep their IDs and original ordering; their unknown creation dates are not invented.
- Removing a film sets `deleted_at`. Restoring clears it on the same row. Re-adding a removed TMDB movie restores that original entry, including its previous status and personal data.
- Schema 2 adds separate survey-like and hidden-suggestion tables; existing movie columns are preserved.
- A removal marker prevents an old Undo notification from undoing a later deletion.
- The retired `movie_catalog` table is preserved but not used. `import_movies.py` is now a non-destructive compatibility notice.

To restore an entire backup, close the app, keep a copy of the current database, and replace `movies.db` with the chosen backup. Keep `posters/` together with library backups. Do not copy an actively written SQLite database; use SQLite's backup API or close the app first.

If you tried the separate frontend preview, its adjacent `data/` library remains separate. The release does not overwrite AppData with that test library or automatically merge it. Keep the preview files if you need to recover notes added there.

## TMDB configuration and privacy

Discovery connects through the shared Cloudflare Worker at `https://api.myshelf.cloud`. The TMDB credential is stored only as a Cloudflare Secret. Users do not need a TMDB account, API key or token; Settings no longer collects credentials. Legacy `tmdb_token` settings are removed on application startup, and `TMDB_ACCESS_TOKEN` is no longer used.

Search terms and requests for catalog information pass through Cloudflare to TMDB. Private notes, ratings, favorites and viewing history remain local. Poster images still load from TMDB's image service when not downloaded locally. Discovery requires the gateway and an internet connection; saved library data and downloaded posters remain available offline. The anonymous gateway has rate limits, but does not guarantee that only our applications can call it. See `cloudflare/watchlist-api/README.md` for deployment details.

For deployment, `MOVIE_WATCHLIST_GATEWAY_URL` can select the same gateway on a custom HTTPS domain (for example `https://api.example.com`). Credentials, query strings and unrelated base paths are rejected. This is an operator configuration, not a user API-key requirement. The default address is `https://api.myshelf.cloud`; the custom domain avoids reliance on the workers.dev hostname.

Optional `FLASK_SECRET_KEY` keeps session signing stable between launches. Without it, sessions are deliberately invalidated on restart and an old open page may need a refresh.

Writes require a session CSRF token. The app validates local host names, uses same-site cookies, and sends a restrictive content security policy. All TMDB requests use a shared, bounded cache and single-flight request handling. Search results expire after two minutes; detail responses after six hours; ordinary failures after three seconds. Rate-limit responses respect Retry-After and pause further requests. The refresh action invalidates the relevant movie cache.

This product uses the TMDB API but is not endorsed or certified by TMDB.

## Structure

```text
app.py                  Application factory, views, validation and security
storage.py              SQLite transactions, migration, membership and recovery
tmdb_client.py          TMDB requests, cache, error handling and normalization
recommendations.py      Local taste profile, public candidate pool and diverse ranking
recommendation_routes.py Survey, recommendation and feedback routes
run_desktop.py          Native window lifecycle using the shared data configuration
version.py              Application version shared by the UI, launcher and build
scripts/build_release.ps1 Clean Windows release packaging and SHA-256 checksums
android/                Standalone Android shell, embedded Python and local authentication
scripts/build_android.ps1 Android APK/AAB packaging
static/script.js        Shared actions, toasts, autocomplete and library filtering
static/recommendations.js Recommendation and taste-survey interactions
static/style.css        Design tokens, shared components and responsive layouts
templates/base.html     Shared page shell and navigation
templates/_icons.html   Shared SVG icon set
templates/_*.html       Shared result cards, actions, pagination and entity links
tests/                  Isolated library, migration, recommendation and concurrency tests
tests/frontend.e2e.cjs   Browser layout and interaction checks
tests/frontend_fixture_server.py Isolated UI fixtures with mocked TMDB responses
```

## Development checks

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check app.py storage.py tmdb_client.py run_desktop.py import_movies.py recommendations.py recommendation_routes.py tests --select F
node --check static/script.js
node --check static/recommendations.js
```

The latest verification passed **68 tests**, covering credential-free gateway requests, secure custom-domain configuration, legacy-token cleanup, offline library preservation, migration and recovery, duplicate/race handling, request safeguards, caching, discovery navigation, checkbox filtering, autocomplete, pagination and desktop data-directory selection. Desktop launcher tests simulate a packaged application and verify preservation of existing records in AppData and in an explicitly overridden data directory. Tests use temporary databases and mocked TMDB responses; they do not modify the personal library. Node.js is only needed for JavaScript checks and browser testing, not to run the app.

Frontend checks covered ten desktop pages, four responsive widths, equal card heights, long titles, missing posters, removal/Undo and keyboard focus. No JavaScript errors were reported in those scenarios. The latest sidebar change was also checked for desktop scrolling and fixed mobile navigation.

See [UI_DESIGN.md](UI_DESIGN.md) for browser test instructions and limitations, and [QA_RESULTS.md](QA_RESULTS.md) for verification details.


## Name and existing libraries

MyMovieList was previously called Movie Watchlist. Existing Windows libraries continue using `%APPDATA%\MovieWatchlist` so upgrading does not create an empty library or require a manual transfer. Existing data-directory and gateway environment variable names remain supported. The repository and source folder names may still use the original name.
