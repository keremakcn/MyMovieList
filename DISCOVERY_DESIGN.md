# Movie discovery — design and implementation

Reviewed on 2026-10-06. Changes are in the primary Desktop/MyMovieList project.

## Benchmark findings

[Letterboxd's popular films](https://letterboxd.com/films/popular/) groups discovery by time window and offers genre filters and ways to hide library films. [Seerr's Discover implementation](https://github.com/seerr-team/seerr/blob/develop/src/components/Discover/index.tsx) reuses poster shelves with “View all” links; its [title cards](https://github.com/seerr-team/seerr/blob/develop/src/components/TitleCard/index.tsx) communicate existing media status. These patterns suit a personal library: scanning a short shelf, opening the full collection and adding a film should be one continuous flow.

The resulting Explore landing page uses three manually controlled shelves, followed by eight genre shortcuts and a link to personal recommendations. It keeps the existing search form and the application's typography, colors and navigation. Shelves do not rotate automatically. Buttons, horizontal touch scrolling and native keyboard navigation provide control, following [W3C carousel accessibility guidance](https://www.w3.org/WAI/tutorials/carousels/).

## Collections and data semantics

| Collection | Provider request | Behavior |
|---|---|---|
| Trending films | `trending/movie/day` or `week` | Weekly by default; switch to Today |
| Highest rated | `movie/top_rated` | TMDB's aggregate collection, including its minimum-vote criteria |
| New releases | `discover/movie` | Release date from today minus 90 days through today, sorted by popularity |
| Genres | `discover/movie` with `with_genres` | One selected genre, excluding future releases |

The [top-rated API](https://developer.themoviedb.org/reference/movie-top-rated-list) uses a minimum of 200 votes. This avoids presenting a film with one perfect vote as a widely highly rated film. The [trending API](https://developer.themoviedb.org/reference/trending-movies) supports day and week windows. The [discover API](https://developer.themoviedb.org/reference/discover-movie) supports the bounded release-date and genre filters.

“New releases” is not the provider's [now-playing list](https://developer.themoviedb.org/reference/movie-now-playing-list), which concerns theatrical availability. The UI describes the actual 90-day period and does not imply that films can be streamed inside the app.

No application-wide viewing/search statistics or user tracking were introduced. Existing general TMDB attribution remains in the footer; collection headings do not have a provider caption.

## Implementation choices

- A discovery service normalizes and deduplicates provider films, rejects adult/video results and malformed IDs, and reads active local library membership in one batch. It never mutates cached provider data.
- A small Flask blueprint exposes full collection pages and first-page shelf fragments. Full lists have 20 provider results per page, up to the provider's 500-page limit. Shelves show up to 12 films.
- Library visibility filtering applies to the current provider page. The interface reports the visible count on that page instead of claiming a recalculated catalog total. Empty filtered pages retain pagination.
- Existing movie detail and add/edit actions handle discovery cards too. CSRF validation, duplicate protection, status preservation and library persistence remain centralized.
- Provider list caching lasts 30 minutes; details retain their six-hour cache. Membership is always read afresh. The bounded cache and single-flight request behavior are reused.
- Shelves load independently when near the viewport. Each has its own loading, empty and error/retry states. Period changes cancel old requests and ignore stale responses.
- Successful additions update all visible copies and reconcile shelves that finish loading later. Back/forward restoration refreshes local membership.
- Closed cards have equal heights, fixed poster proportions, two-line title slots and aligned actions. On small screens, selected genres use a compact native selector.
- The Android Python packaging allowlist includes the two new modules. This change has not produced a new Android release or substituted for physical-device testing.

## Validation

106 Python regression tests passed, including 38 discovery tests. Additional isolated browser checks covered independent errors and retries, quick-add failures and recovery, duplicate submissions across shelves, period changes, keyboard focus, library visibility, pagination/back destinations and six discovery views at 320, 390, 768, 1024 and 1365 pixels. The discovery fixture always uses a newly created temporary database; it never opens the personal AppData library.
