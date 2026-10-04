<p align="center">
  <img src="static/branding/mymovielist-256.png" alt="MyMovieList logo" width="110">
</p>
<h1 align="center">MyMovieList</h1>
<p align="center"><strong>Your films. Your thoughts. Your space.</strong></p>
<p align="center">A personal movie library with discovery, recommendations and a private journal. No account or API key required.</p>
<p align="center"><a href="https://github.com/keremakcn/MyMovieList/releases/latest"><strong>Download</strong></a> · <a href="https://github.com/keremakcn/MyMovieList/releases">All releases</a></p>

## Get started

**Windows — v3.3.0**

1. Download `MyMovieList-v3.3.0-windows.zip` from the release’s **Assets**.
2. Extract it and open `MyMovieList-v3.3.0.exe`. No Python installation is needed.
3. Search for a film and add it to your library. Discovery is ready without setup.

**Android — 3.3.0 beta**

Download the Android `.apk` from the release’s **Assets**, if attached. Android 7.0 or newer and a 64-bit ARM device are required. The Android app runs independently and keeps its own library; it does not sync with Windows. This is a beta: physical-device testing is still required. See [Android details](ANDROID.md).

## Features

- Track **Want to watch** and **Watched**, with ratings, favorites and private notes.
- Add films directly from search without losing your results.
- Explore actors, directors and production companies, then discover their films.
- Get personal recommendations with **Close to my taste**, **A little discovery** and **Surprise me** modes. Refresh for new suggestions.
- Choose films you enjoyed to help personalize recommendations.
- Filter and sort your library. Undo removal without losing notes, ratings or the original added order.
- Compact cards with a one-line note preview; open the detail page to read or edit.
- Keyboard-friendly search, suggestions and navigation. Press **Ctrl+K** to search.

## Screenshots

### Your library

![MyMovieList library](screenshots/frontend-library.png)

### Explore films

![MyMovieList discovery](screenshots/frontend-explore.png)

### Cast and filmmakers

![Actor profile](screenshots/actor.png)

![Director profile](screenshots/director.png)

## Your thoughts stay yours

Not every reaction needs an audience. Write honestly without publishing your notes to a public profile. Your library, notes, ratings and favorites stay on your device and are not uploaded to our discovery service or TMDB.

Searches and catalog requests pass through `api.myshelf.cloud` to TMDB. Discovery and remote images need internet; saved library information and downloaded posters remain available offline. Local storage is not encrypted.

**Updates preserve your Windows library.** Close the app before replacing the EXE. Existing data remains in `%APPDATA%\MovieWatchlist`; the original folder name is retained for compatibility. Android data stays in private app storage; uninstalling the app or clearing its storage deletes that library.

## Run from source

Python 3.12 recommended:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-desktop.txt
.\.venv\Scripts\python run_desktop.py
```

Build Windows with `.\scripts\build_release.ps1`. See [release notes](RELEASE_NOTES.md), [QA results](QA_RESULTS.md), [Android build instructions](ANDROID.md) and [discovery service setup](cloudflare/watchlist-api/README.md) for development details.

## Credits

Movie data and images are provided by [TMDB](https://www.themoviedb.org). This product uses the TMDB API but is not endorsed or certified by TMDB.
