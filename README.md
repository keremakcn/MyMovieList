# 🎬 Movie Watchlist

A personal movie tracking application for organizing movies, keeping track of what you've watched, and managing your personal watchlist.

The app searches TMDB live for movies. Once you add one to your library, everything about it — poster, overview, runtime, director, cast, TMDB score — is downloaded and cached locally, so your library works **fully offline** afterward. Only searching for new movies needs an internet connection.

Runs as a normal Flask web app, or as a **standalone Windows desktop app** with its own window and icon (no browser tab, no console) via `run_desktop.py`.

---

## ✨ Features

### 🎞️ Movie Management

- Search TMDB directly for movies (live results, not a static local catalog)
- Preview a movie's full details before adding it
- Add movies to your watchlist, or straight to watched
- Mark movies as watched or move them back to the watchlist
- Edit rating, notes, and watched date at any time
- Delete movies from your library, with a themed confirmation dialog
- Quick actions (favorite / status / delete) available right from the Edit page

### ❤️ Favorites

- Add or remove movies from favorites
- Favorite movies are automatically marked as watched
- Favorites are prioritized on the main library

### ⭐ Ratings, Notes & TMDB Score

- Rate movies from **1 to 10**, add personal notes
- View your library's average rating
- Each movie shows TMDB's own community score as a colored badge

### 🔎 Search & Discovery

- Search movies by title via TMDB's live search
- View overview, runtime, director, cast, and genre before adding
- Search for a movie's trailer on YouTube

### 📊 Library & Organization

- Watchlist count, watched count, favorite count, average rating
- Filter by All / Watchlist / Watched / Favorites
- Sort by your rating, TMDB score, release year, watched date, or date added (each newest/oldest) — filters and sorting combine freely and never reset each other

### 🌐 Works Offline

- Posters are downloaded once and stored locally, not hot-linked to TMDB
- Overview, runtime, director, cast, and score are cached in the database the moment you add a movie
- Your library, a movie's detail page, editing, and favoriting all work with no internet connection
- Only searching for new movies, or previewing one you haven't added yet, needs internet

### 🖥️ Desktop App

- Packaged as a single Windows `.exe` with its own native window and custom icon (via `pywebview` + PyInstaller)
- Each person supplies their own free TMDB token from the in-app **Settings** page — no shared or embedded API key
- Your library and posters persist between runs in your Windows user profile, independent of where the `.exe` is placed

### 📱 Responsive Design

Works on both desktop and mobile screen sizes.

---

## 🛠️ Technologies

| Technology | Purpose |
|------------|---------|
| Python | Application logic |
| Flask | Web framework |
| SQLite (`sqlite3`, standard library) | Local database |
| Waitress | Production-grade server used by `python app.py` and the desktop app |
| pywebview | Native window for the desktop build |
| PyInstaller | Packages the app into a standalone `.exe` |
| HTML / CSS / JavaScript | Front end |
| TMDB API | Live movie search, posters, overviews, cast, crew, ratings |

---

## 📁 Project Structure

```text
Movie-Watchlist/
│
├── app.py                 # Flask app: routes, TMDB integration, database
├── run_desktop.py         # Desktop entry point (native window via pywebview)
├── app_icon.ico            # Desktop app / .exe icon
├── README.md
├── .gitignore
│
├── templates/
│   ├── index.html
│   ├── search.html
│   ├── movie.html
│   ├── catalog_movie.html
│   ├── add.html
│   ├── edit.html
│   ├── settings.html
│   ├── _confirm_modal.html   # shared delete-confirmation dialog
│   ├── _info_badges.html     # shared release year / genre / runtime / cast badges
│   └── _tmdb_info.html       # shared overview text block
│
└── static/
    ├── style.css
    └── script.js
```

Created automatically at runtime (not tracked in git):

- Running from source: `movies.db` and `posters/` appear in the project folder.
- Running as the packaged `.exe`: they instead live under `%APPDATA%\MovieWatchlist\`, so they survive between runs no matter where the `.exe` sits.

---

## ⚙️ Setup (running from source)

### 1. Clone the repository

```bash
git clone <repository-url>
cd Movie-Watchlist
```

### 2. Install dependencies

```bash
pip install flask waitress python-dotenv
```

`pywebview` and `pyinstaller` are only needed for building the desktop `.exe` (see below).

### 3. Get a TMDB token

Either:
- create a `.env` file in the project root with `TMDB_ACCESS_TOKEN=your_token_here`, **or**
- skip this and add your token later from the in-app **Settings** page (kept in your browser session, never written to the repo).

Get a free token at [themoviedb.org](https://www.themoviedb.org/signup) → Settings → API → "API Read Access Token".

### 4. Run the application

```bash
flask run
```

or, to run it the same way the desktop build does (Waitress server, auto-opens a browser tab):

```bash
python app.py
```

---

## 🔐 Environment Variables

| Variable | Purpose |
|---|---|
| `TMDB_ACCESS_TOKEN` | Optional. Fallback TMDB token if no per-session token is set via Settings. |
| `FLASK_SECRET_KEY` | Optional. Keeps sessions stable across restarts. A random one is generated if not set. |

Keep `.env` out of the repository — it already is, via `.gitignore`.

---

## 🖥️ Building the Desktop App

```bash
pip install pywebview waitress pyinstaller

pyinstaller --noconfirm --onefile --windowed --name MovieWatchlist --icon=app_icon.ico --add-data "templates;templates" --add-data "static;static" run_desktop.py
```

The `.exe` appears in `dist/MovieWatchlist.exe`. It's fully self-contained — people running it don't need Python, pip, or any of the above installed.

---

## 🎬 TMDB

This product uses the TMDB API but is not endorsed or certified by TMDB.

---

## 🚀 Future Development

Planned improvements may include:

- Manually refreshing/re-caching a movie's TMDB data
- Genre-based filtering
- Detailed viewing statistics
- Movie recommendations

---

## 📌 Version

**v2.0**