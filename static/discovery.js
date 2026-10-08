/* General discovery shares movie actions with search and the personal library. */
(() => {
    'use strict';
    const {t} = window.MovieListI18n;
    const states = new WeakMap();
    const addedMovies = new Map();
    const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
    let observer;

    function updateScrollButtons(shelf) {
        const rail = shelf.querySelector('.discovery-rail');
        const controls = shelf.querySelector('.discovery-scroll-controls');
        if (!rail || !controls) { if (controls) controls.hidden = true; return; }
        const overflow = rail.scrollWidth - rail.clientWidth;
        controls.hidden = overflow < 2;
        const left = controls.querySelector('[data-scroll="-1"]');
        const right = controls.querySelector('[data-scroll="1"]');
        // aria-disabled retains keyboard focus after reaching either end.
        left.setAttribute('aria-disabled', String(rail.scrollLeft < 2));
        right.setAttribute('aria-disabled', String(rail.scrollLeft >= overflow - 2));
    }

    function showLibraryState(card, detail) {
        if (!card.querySelector('.discovery-library-badge')) {
            const badge = document.createElement('span');
            badge.className = 'discovery-library-badge';
            badge.textContent = t(detail.status === 'Watched' ? 'Watched' : 'In your library');
            card.querySelector('.discovery-poster')?.append(badge);
        }
        // A shelf may finish loading after an add from another shelf succeeded.
        const action = card.querySelector('.library-action');
        if (detail.editUrl && action?.querySelector('form')) {
            const link = document.createElement('a');
            link.href = detail.editUrl;
            link.className = 'in-library';
            link.textContent = t('✓ In your library');
            link.setAttribute('aria-label', t('Edit {title} — {status}', {title: action.dataset.movieTitle, status: t(detail.status === 'Watched' ? 'Watched' : 'In your library')}));
            action.replaceChildren(link);
        }
    }

    function failure(feed, shelf, message, restoreFocus) {
        const panel = document.createElement('div');
        panel.className = 'discovery-empty';
        panel.setAttribute('role', 'status');
        const text = document.createElement('p');
        text.textContent = message;
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'secondary-button';
        button.textContent = t('Try again');
        button.addEventListener('click', () => load(shelf));
        panel.append(text, button);
        feed.replaceChildren(panel);
        updateScrollButtons(shelf);
        if (restoreFocus) button.focus();
    }

    async function load(shelf) {
        let state = states.get(shelf);
        if (!state) { state = {sequence: 0, window: 'week', loaded: false}; states.set(shelf, state); }
        state.controller?.abort();
        state.controller = new AbortController();
        const sequence = ++state.sequence;
        const feed = shelf.querySelector('[data-discovery-feed]');
        const restoreFocus = feed.contains(document.activeElement);
        feed.setAttribute('aria-busy', 'true');
        feed.classList.add('is-loading');
        const parameters = new URLSearchParams({limit: '12'});
        if (shelf.dataset.discoveryShelf === 'trending') parameters.set('window', state.window);
        const viewAll = shelf.querySelector('.discovery-view-all');
        if (shelf.dataset.discoveryShelf === 'trending') viewAll.href = `/discover/trending?window=${state.window}`;
        try {
            const response = await window.MovieListHTTP.fetch(`/api/discovery/${shelf.dataset.discoveryShelf}?${parameters}`, {
                signal: state.controller.signal, headers: {'Accept': 'application/json'}
            });
            const result = await response.json().catch(() => ({error: t('Could not load these films. Please try again.')}));
            if (sequence !== state.sequence) return;
            if (!response.ok || typeof result.html !== 'string') throw new Error(result.error || t('Could not load these films. Please try again.'));
            // HTML is rendered by our local Flask templates, never by a provider.
            feed.innerHTML = result.html;
            for (const card of feed.querySelectorAll('[data-discovery-movie]')) {
                const detail = addedMovies.get(card.dataset.discoveryMovie);
                if (detail) showLibraryState(card, detail);
            }
            state.loaded = true;
            const rail = feed.querySelector('.discovery-rail');
            rail?.addEventListener('scroll', () => updateScrollButtons(shelf), {passive: true});
            updateScrollButtons(shelf);
            if (restoreFocus) (rail || shelf.querySelector('.discovery-view-all')).focus();
        } catch (error) {
            if (error.name === 'AbortError' || sequence !== state.sequence) return;
            failure(feed, shelf, error instanceof TypeError ? t('Could not load these films. Check your connection and try again.') : error.message || t('Could not load these films. Please try again.'), restoreFocus);
        } finally {
            if (sequence === state.sequence) { feed.setAttribute('aria-busy', 'false'); feed.classList.remove('is-loading'); }
        }
    }

    for (const shelf of document.querySelectorAll('[data-discovery-shelf]')) {
        shelf.addEventListener('click', event => {
            const period = event.target.closest('[data-trending-window]');
            if (period) {
                const state = states.get(shelf) || {sequence: 0, window: 'week', loaded: false};
                states.set(shelf, state);
                if (state.window === period.dataset.trendingWindow && state.loaded) return;
                state.window = period.dataset.trendingWindow;
                for (const button of shelf.querySelectorAll('[data-trending-window]')) button.setAttribute('aria-pressed', String(button === period));
                observer?.unobserve(shelf);
                load(shelf);
            }
            const scroll = event.target.closest('[data-scroll]');
            if (scroll && scroll.getAttribute('aria-disabled') !== 'true') {
                const rail = shelf.querySelector('.discovery-rail');
                rail?.scrollBy({left: Number(scroll.dataset.scroll) * Math.max(rail.clientWidth * 0.8, 180), behavior: reduceMotion ? 'instant' : 'smooth'});
            }
        });
        if ('ResizeObserver' in window) new ResizeObserver(() => updateScrollButtons(shelf)).observe(shelf);
    }
    if ('IntersectionObserver' in window) {
        observer = new IntersectionObserver(entries => {
            for (const entry of entries) if (entry.isIntersecting) { observer.unobserve(entry.target); load(entry.target); }
        }, {rootMargin: '180px'});
        document.querySelectorAll('[data-discovery-shelf]').forEach(shelf => observer.observe(shelf));
    } else document.querySelectorAll('[data-discovery-shelf]').forEach(load);
    addEventListener('pagehide', () => document.querySelectorAll('[data-discovery-shelf]').forEach(shelf => states.get(shelf)?.controller?.abort()));
    // Back/forward can restore a document without running its scripts again.
    // Refresh local membership even when provider results are still cached.
    addEventListener('pageshow', event => {
        if (!event.persisted) return;
        addedMovies.clear();
        if (document.querySelector('.discovery-collection')) { location.reload(); return; }
        for (const shelf of document.querySelectorAll('[data-discovery-shelf]')) {
            if (states.has(shelf)) { observer?.unobserve(shelf); load(shelf); }
        }
    });

    const filter = document.querySelector('[data-discovery-filter]');
    if (filter) {
        filter.querySelector('button[type="submit"]').hidden = true;
        filter.addEventListener('change', () => filter.requestSubmit());
    }
    document.addEventListener('library-movie-added', event => {
        addedMovies.set(String(event.detail.tmdbId), event.detail);
        const cards = [...document.querySelectorAll(`[data-discovery-movie="${event.detail.tmdbId}"]`)];
        for (const card of cards) {
            const hiddenCollection = card.closest('[data-hide-library]');
            if (hiddenCollection) {
                const next = card.nextElementSibling || card.previousElementSibling;
                const hadFocus = card.contains(document.activeElement) || event.detail.restoreFocus;
                card.remove();
                const remaining = hiddenCollection.querySelectorAll('.discovery-card').length;
                const count = document.querySelector('[data-discovery-count]');
                if (count) count.textContent = t(remaining === 1 ? '{count} film on this page' : '{count} films on this page', {count: remaining});
                if (!remaining) {
                    const empty = document.createElement('p');
                    empty.className = 'discovery-empty';
                    empty.setAttribute('role', 'status');
                    empty.textContent = t('All films on this page are in your library. Try the next page.');
                    hiddenCollection.append(empty);
                }
                if (hadFocus) (next?.querySelector('h3 a') || document.getElementById('collection-heading'))?.focus();
            } else showLibraryState(card, event.detail);
        }
    });
})();
