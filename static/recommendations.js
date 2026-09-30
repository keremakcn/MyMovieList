/* UI for local recommendations and taste onboarding. */
(() => {
    'use strict';
    const csrf = document.querySelector('meta[name="csrf-token"]').content;
    async function read(response) {
        const data = await response.json().catch(() => ({error: 'Something went wrong. Please try again.'}));
        if (!response.ok) throw new Error(data.error || 'Could not complete the request. Please try again.');
        return data;
    }
    const region = document.getElementById('recommendation-results');
    if (region) {
        const refreshButton = document.getElementById("refresh-recommendations");
        const refreshStatus = document.getElementById("recommendation-status");
        let loading = false, refreshPending = false;
        async function load(fresh = false) {
            if (loading) { refreshPending = true; return; }
            loading = true; region.setAttribute('aria-busy', 'true');
            refreshButton.disabled = true;
            refreshButton.textContent = fresh ? 'Refreshing…' : 'New suggestions';
            refreshStatus.textContent = '';
            try {
                const data = await read(await fetch(fresh ? '/api/recommendations/refresh' : '/api/recommendations', fresh ? {method: 'POST', headers: {'X-CSRF-Token': csrf}} : {}));
                region.innerHTML = data.html; // Escaped same-origin Jinja fragment.
            } catch (error) {
                if (fresh) { refreshStatus.textContent = error.message; return; }
                const message = document.createElement('p'); message.className = 'form-error'; message.textContent = error.message;
                const retry = document.createElement('button'); retry.type = 'button'; retry.dataset.recommendationRetry = ''; retry.textContent = 'Try again';
                region.replaceChildren(message, retry);
            } finally {
                loading = false; region.setAttribute('aria-busy', 'false');
                refreshButton.disabled = false; refreshButton.textContent = 'New suggestions';
                if (refreshPending) { refreshPending = false; load(); }
            }
        }
        refreshButton.addEventListener('click', () => { if (!loading) load(true); });
        document.addEventListener('library-movie-added', event => {
            const id = event.detail.tmdbId;
            const card = [...region.querySelectorAll('.library-action')].find(node => node.dataset.tmdbId === String(id))?.closest('.recommendation-item');
            if (card) card.remove();
            load();
        });
        region.addEventListener('click', event => { if (event.target.closest('[data-recommendation-retry]')) load(); });
        region.addEventListener('submit', async event => {
            const form = event.target.closest('[data-dismiss-pick]');
            if (!form) return;
            event.preventDefault();
            const button = form.querySelector('button'); if (button.disabled) return;
            button.disabled = true;
            try {
                await read(await fetch(form.action, {method: 'POST', body: new FormData(form), headers: {'X-CSRF-Token': csrf, Accept: 'application/json'}}));
                const card = form.closest('.recommendation-item');
                const notice = document.createElement('div'); notice.className = 'taste-invitation';
                const text = document.createElement('p'); text.textContent = 'Suggestion hidden. Other films in this genre are unaffected.';
                const undo = document.createElement('form'); undo.action = '/recommendations/restore'; undo.method = 'post';
                for (const [name, value] of [['csrf_token', csrf], ['movie_id', form.elements.movie_id.value]]) {
                    const input = document.createElement('input'); input.type = 'hidden'; input.name = name; input.value = value; undo.append(input);
                }
                const restore = document.createElement('button'); restore.textContent = 'Undo'; undo.append(restore);
                notice.append(text, undo); card.replaceWith(notice); restore.focus();
            } catch (error) {
                button.disabled = false;
                let message = form.querySelector('[role="alert"]');
                if (!message) { message = document.createElement('p'); message.setAttribute('role', 'alert'); form.append(message); }
                message.textContent = error.message;
            }
        });
        load();
    }
    const grid = document.getElementById('taste-grid'); if (!grid) return;
    const status = document.getElementById('taste-status');
    const input = document.getElementById('taste-query');
    const selectedRegion = document.getElementById('taste-selected');
    const count = document.getElementById('taste-count');
    const more = document.getElementById('taste-more');
    const saveForm = document.getElementById('taste-save');
    const saveStatus = document.getElementById('taste-save-status');
    const continueButton = document.getElementById('taste-continue');
    const selected = new Map([...selectedRegion.querySelectorAll('[data-selected-id]')].map(button => [Number(button.dataset.selectedId), button.dataset.selectedTitle]));
    let revision = 0, controller, timer, page = 1, query = '', busy = false, saving = false;
    function sync() {
        count.textContent = `(${selected.size})`; selectedRegion.replaceChildren();
        for (const [id, title] of selected) {
            const button = document.createElement('button'); button.type = 'button'; button.textContent = `${title} ×`;
            button.setAttribute('aria-label', `Remove ${title} from your picks`);
            button.addEventListener('click', () => { if (!saving) { selected.delete(id); sync(); } }); selectedRegion.append(button);
        }
        grid.querySelectorAll('input[type="checkbox"]').forEach(box => { box.checked = selected.has(Number(box.value)); box.disabled = saving; });
        continueButton.disabled = saving || !selected.size;
    }
    function draw(movies) {
        grid.replaceChildren();
        for (const movie of movies) {
            const label = document.createElement('label'); label.className = 'taste-card';
            const box = document.createElement('input'); box.type = 'checkbox'; box.value = movie.tmdb_id; box.setAttribute('aria-label', `I liked ${movie.title}`);
            const art = document.createElement('div'); art.className = 'taste-poster';
            if (movie.poster_url) { const image = document.createElement('img'); image.src = movie.poster_url; image.alt = ''; image.loading = 'lazy'; art.append(image); }
            else art.textContent = '◈';
            const title = document.createElement('strong'); title.textContent = movie.title;
            const year = document.createElement('small'); year.textContent = movie.year || 'Year unknown';
            box.addEventListener('change', () => {
                if (box.checked && selected.size >= 24) { box.checked = false; status.textContent = 'You can select up to 24 films.'; return; }
                if (box.checked) selected.set(movie.tmdb_id, movie.title); else selected.delete(movie.tmdb_id);
                sync();
            });
            label.append(box, art, title, year); grid.append(label);
        }
        sync();
    }
    async function load(nextQuery, nextPage) {
        const current = ++revision;
        controller?.abort(); controller = new AbortController(); busy = true;
        more.disabled = true; grid.setAttribute('aria-busy', 'true'); status.textContent = 'Loading films…';
        try {
            const params = new URLSearchParams({q: nextQuery, page: nextPage});
            const data = await read(await fetch(`/api/taste/choices?${params}`, {signal: controller.signal}));
            if (current !== revision) return;
            query = nextQuery; page = nextPage; draw(data.movies);
            more.hidden = page >= data.pages; more.textContent = query ? 'Next results' : 'Show different films';
            status.textContent = data.errors.length ? data.errors.join(' ') : data.movies.length ? 'Select films you have seen and enjoyed. Your picks stay selected as you browse.' : 'No films found. Try another title.';
        } catch (error) {
            if (error.name !== 'AbortError' && current === revision) {
                status.textContent = error.message; more.hidden = false; more.textContent = 'Try again'; more.dataset.retry = 'true';
            }
        } finally { if (current === revision) { busy = false; more.disabled = false; grid.setAttribute('aria-busy', 'false'); } }
    }
    document.getElementById('taste-search').addEventListener('submit', event => {
        event.preventDefault(); clearTimeout(timer); delete more.dataset.retry; load(input.value.trim(), 1);
    });
    input.addEventListener('input', () => {
        clearTimeout(timer); ++revision; controller?.abort(); busy = false;
        timer = setTimeout(() => { delete more.dataset.retry; load(input.value.trim(), 1); }, 350);
    });
    more.addEventListener('click', () => {
        if (busy) return;
        if (more.dataset.retry) { delete more.dataset.retry; load(input.value.trim(), 1); } else load(query, page + 1);
    });
    document.getElementById('taste-browse').addEventListener('click', () => {
        clearTimeout(timer); input.value = ''; delete more.dataset.retry; load('', 1);
    });
    saveForm.addEventListener('submit', async event => {
        event.preventDefault(); if (saving || !selected.size) return;
        saving = true; sync(); saveStatus.textContent = 'Saving your picks. Please keep this page open…';
        const data = new FormData(saveForm); for (const id of selected.keys()) data.append('movie_id', id);
        try {
            const result = await read(await fetch(saveForm.action, {method: 'POST', body: data, headers: {'X-CSRF-Token': csrf, Accept: 'application/json'}}));
            location.assign(result.url);
        } catch (error) { saveStatus.textContent = `${error.message} Your selections are still here. Please try again.`; saving = false; sync(); }
    });
    sync(); load('', 1);
})();
