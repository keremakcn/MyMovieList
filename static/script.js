/* Shared interactions: the server owns library state; DOM state is disposable. */
(() => {
    'use strict';
    const csrf = document.querySelector('meta[name="csrf-token"]').content;
    const pendingMovies = new Set();
    const pendingForms = new WeakSet();
    const region = document.getElementById('toast-region');
    let lastUndo = null;
    let libraryVersion = 0;
    let libraryController;

    async function post(url, data) {
        const response = await fetch(url, {
            method: 'POST',
            body: data,
            headers: {
                'Accept': 'application/json',
                'X-CSRF-Token': csrf
            }
        });
        const result = await response.json().catch(() => ({
            error: 'Something went wrong. Please try again.'
        }));
        if (!response.ok) throw new Error(result.error || 'Something went wrong. Please try again.');
        return result;
    }

    function toast(message, action, actionLabel = 'Undo', persistent = false) {
        const box = document.createElement('div');
        box.className = 'toast';
        const text = document.createElement('span');
        text.textContent = message;
        box.append(text);
        if (action) {
            const button = document.createElement('button');
            button.textContent = actionLabel;
            button.addEventListener('click', async () => {
                button.disabled = true;
                try {
                    await action();
                    dismiss();
                } catch (error) {
                    button.disabled = false;
                    toast(error.message, null, '', true);
                }
            });
            box.append(button);
            if (actionLabel === 'Undo') lastUndo = button;
        }
        const close = document.createElement('button');
        close.textContent = '×';
        close.setAttribute('aria-label', 'Dismiss notification');
        close.addEventListener('click', dismiss);
        box.append(close);
        region.append(box);
        let timer;

        function dismiss() {
            if (box.contains(lastUndo)) lastUndo = null;
            clearTimeout(timer);
            box.remove();
        }

        function startTimer() {
            if (!persistent) timer = setTimeout(dismiss, 10000);
        }
        box.addEventListener('mouseenter', () => clearTimeout(timer));
        box.addEventListener('mouseleave', startTimer);
        box.addEventListener('focusin', () => clearTimeout(timer));
        box.addEventListener('focusout', startTimer);
        startTimer();
        return box;
    }
    region.addEventListener('click', event => event.target.closest('[data-dismiss]')?.closest('.toast')?.remove());

    async function refreshLibrary(url = location.href, replace = true) {
        if (!document.getElementById('library-results')) return;
        const version = ++libraryVersion;
        libraryController?.abort();
        libraryController = new AbortController();
        const response = await fetch(url, {
            signal: libraryController.signal
        });
        if (!response.ok) throw new Error('Could not refresh your library. Please try again.');
        const html = new DOMParser().parseFromString(await response.text(), 'text/html');
        if (version !== libraryVersion) return false;
        if (replace) {
            const fresh = html.getElementById('library-results');
            document.getElementById('library-results').replaceWith(fresh);
        }
        document.querySelector('.stats-grid')?.replaceWith(html.querySelector('.stats-grid'));
        return true;
    }

    function markAdded(id, result) {
        document.querySelectorAll(`.library-action[data-tmdb-id="${id}"]`).forEach(container => {
            const link = document.createElement('a');
            link.href = result.edit_url;
            link.className = 'in-library';
            link.textContent = '✓ Already in your library — Click to edit';
            const hadFocus = container.contains(document.activeElement);
            container.replaceChildren(link);
            if (hadFocus) link.focus();
        });
        document.querySelectorAll(`form[data-add-movie][data-tmdb-id="${id}"]`).forEach(form => form.remove());
    }

    document.addEventListener('submit', async event => {
        const form = event.target;
        if (!(form instanceof HTMLFormElement)) return;
        if (!form.matches('[data-add-movie], [data-delete], [data-quick-action]')) return;
        event.preventDefault();
        if (pendingForms.has(form)) return;
        const data = new FormData(form);
        const movieId = data.get('movie_id');
        if (movieId && pendingMovies.has(movieId)) return;
        pendingForms.add(form);
        if (movieId) pendingMovies.add(movieId);
        const buttons = [...form.querySelectorAll('button')];
        const label = buttons[0]?.textContent;
        buttons.forEach(button => button.disabled = true);
        form.setAttribute('aria-busy', 'true');
        if (form.matches('[data-add-movie]')) buttons[0].textContent = 'Adding…';
        try {
            const result = await post(form.action, data);
            if (form.matches('[data-add-movie]')) {
                markAdded(movieId, result);
                toast(result.created ? (result.status === 'Watched' ? 'Added as watched.' : 'Added to Want to Watch.') : '✓ In your library.');
            } else if (form.matches('[data-delete]')) {
                const card = form.closest('.movie-card');
                const detail = document.querySelector('[data-detail-id]');
                if (card) {
                    const next = card.nextElementSibling || card.previousElementSibling;
                    card.remove();
                    next?.querySelector('a,button')?.focus();
                } else if (detail) {
                    detail.hidden = true;
                    const notice = document.createElement('section');
                    notice.className = 'empty-state';
                    notice.id = 'removed-notice';
                    const message = document.createElement('p');
                    message.textContent = 'Movie removed. Use Undo below or restore it from Recently removed.';
                    const link = document.createElement('a');
                    link.className = 'edit-link';
                    link.href = '/?status=trash';
                    link.textContent = 'Recently removed';
                    notice.append(message, link);
                    detail.after(notice);
                }
                const undo = async () => {
                    const restoreData = new FormData();
                    restoreData.set('marker', result.marker);
                    await post(`/restore/${result.id}`, restoreData);
                    if (detail) detail.hidden = false;
                    document.getElementById('removed-notice')?.remove();
                    await refreshLibrary();
                    toast('Movie restored — notes, rating and original order preserved.');
                };
                const notification = toast('Movie removed.', undo);
                if (!card) notification.querySelector('button').focus();
                await refreshLibrary();
            } else {
                if (document.getElementById('library-results')) {
                    const cardId = form.closest('.movie-card')?.dataset.movieId;
                    const action = form.action.includes('/favorite/') ? 'favorite' : 'status';
                    await refreshLibrary();
                    document.querySelector(`[data-movie-id="${cardId}"] form[action^="/${action}/"] button`)?.focus();
                } else {
                    // Detail forms retain the editable note instead of reloading unsaved input.
                    const favoriteAction = form.action.includes('/favorite/');
                    if (favoriteAction) {
                        form.elements.value.value = result.favorite ? '0' : '1';
                        buttons[0].textContent = result.favorite ? '♥' : '♡';
                        buttons[0].setAttribute('aria-pressed', String(Boolean(result.favorite)));
                        buttons[0].setAttribute('aria-label', result.favorite ? 'Remove from favorites' : 'Add to favorites');
                    } else {
                        form.elements.value.value = result.status === 'Watched' ? 'Watchlist' : 'Watched';
                        buttons[0].textContent = result.status === 'Watched' ? 'Want to watch' : 'Mark watched';
                        document.querySelectorAll('.status-badge').forEach(badge => {
                            badge.textContent = result.status === 'Watched' ? 'Watched' : 'Want to watch';
                            badge.className = `status-badge ${result.status.toLowerCase()}`;
                        });
                        document.querySelectorAll('[data-watched-date]').forEach(label => {
                            label.hidden = !result.watched_date;
                            label.textContent = result.watched_date ? `Watched ${result.watched_date}` : '';
                        });
                        const dateInput = document.querySelector('input[name="watched_date"]');
                        if (dateInput && dateInput.value === dateInput.defaultValue) {
                            dateInput.value = result.watched_date || '';
                            dateInput.defaultValue = dateInput.value;
                        }
                    }
                }
            }
        } catch (error) {
            if (error.name !== 'AbortError') toast(error.message || 'Could not complete the request. Please try again.', null, '', true);
        } finally {
            pendingForms.delete(form);
            if (movieId) pendingMovies.delete(movieId);
            buttons.forEach(button => button.disabled = false);
            if (form.matches('[data-add-movie]') && buttons[0]) buttons[0].textContent = label;
            form.removeAttribute('aria-busy');
        }
    });

    const libraryForm = document.querySelector('[data-library-filter]');
    if (libraryForm) {
        const input = libraryForm.elements.q;
        let debounce;
        const run = async () => {
            const url = new URL('/', location.origin);
            new FormData(libraryForm).forEach((value, key) => url.searchParams.set(key, value));
            input.setAttribute('aria-busy', 'true');
            try {
                const applied = await refreshLibrary(url);
                if (!applied) return;
                history.replaceState(null, '', url);
                // Preserve the existing instant filter, including searches across all pages.
                document.querySelectorAll('.filter-group a').forEach(link => {
                    const target = new URL(link.href);
                    target.searchParams.set('q', input.value);
                    target.searchParams.set('sort', libraryForm.elements.sort.value);
                    link.href = target;
                });
            } catch (error) {
                if (error.name !== 'AbortError') toast(error.message);
            } finally {
                input.removeAttribute('aria-busy');
            }
        };
        input.addEventListener('input', () => {
            clearTimeout(debounce);
            libraryController?.abort();
            ++libraryVersion;
            const query = input.value.trim().toLowerCase();
            document.querySelectorAll('.movie-card').forEach(card => card.hidden = !card.dataset.title.includes(query));
            debounce = setTimeout(run, 250);
        });
        libraryForm.addEventListener('submit', event => {
            event.preventDefault();
            clearTimeout(debounce);
            run();
        });
        libraryForm.elements.sort.addEventListener('change', () => {
            clearTimeout(debounce);
            run();
        });
        addEventListener('popstate', () => location.reload());
    }

    const searchForm = document.querySelector('[data-autocomplete]');
    if (searchForm) {
        const input = searchForm.elements.q;
        const filters = [...searchForm.querySelectorAll('[name="category"]')];
        const filterHelp = searchForm.querySelector('.filter-help');
        const searchParams = () => new URLSearchParams(new FormData(searchForm));
        const list = document.getElementById('suggestions');
        const status = document.getElementById('suggestion-status');
        let timer, controller, revision = 0,
            selected = -1,
            results = [];
        const cache = new Map();

        function close() {
            ++revision;
            clearTimeout(timer);
            controller?.abort();
            list.hidden = true;
            input.setAttribute('aria-expanded', 'false');
            input.removeAttribute('aria-activedescendant');
            input.removeAttribute('aria-busy');
            selected = -1;
        }

        function select(index) {
            selected = index;
            [...list.children].forEach((option, i) => option.setAttribute('aria-selected', String(i === index)));
            if (index >= 0) {
                input.setAttribute('aria-activedescendant', `suggestion-${index}`);
                list.children[index].scrollIntoView({
                    block: 'nearest'
                });
            }
        }

        function openResult(index) {
            const target = new URL(results[index].url, location.origin);
            target.searchParams.set('back', '/search?' + searchParams());
            location.assign(target);
        }

        function render(items) {
            results = items;
            selected = -1;
            list.replaceChildren();
            items.forEach((item, index) => {
                const option = document.createElement('li');
                option.id = `suggestion-${index}`;
                option.setAttribute('role', 'option');
                option.setAttribute('aria-selected', 'false');
                const label = document.createElement('span');
                label.textContent = item.label;
                const detail = document.createElement('small');
                detail.textContent = item.subtitle;
                option.append(label, detail);
                option.addEventListener('pointerdown', event => event.preventDefault());
                option.addEventListener('click', () => openResult(index));
                option.addEventListener('pointermove', () => select(index));
                list.append(option);
            });
            list.hidden = !items.length;
            input.setAttribute('aria-expanded', String(Boolean(items.length)));
            status.textContent = items.length ? `${items.length} suggestions available. Use the arrow keys.` : 'No suggestions. Press Enter to search.';
        }

        function schedule() {
            close();
            if (input.value.trim().length < 2 || !filters.some(filter => filter.checked)) return;
            const current = revision;
            timer = setTimeout(async () => {
                const params = searchParams();
                params.set('q', input.value.trim());
                const key = params.toString();
                const saved = cache.get(key);
                if (saved && saved.expires > Date.now()) {
                    render(saved.items);
                    return;
                }
                controller = new AbortController();
                input.setAttribute('aria-busy', 'true');
                status.textContent = 'Loading suggestions…';
                try {
                    const response = await fetch(`/api/suggestions?${params}`, {
                        signal: controller.signal
                    });
                    const data = await response.json();
                    if (current !== revision) return;
                    if (!response.ok) throw new Error(data.error);
                    cache.set(key, {
                        items: data.results,
                        expires: Date.now() + 60000
                    });
                    if (cache.size > 40) cache.delete(cache.keys().next().value);
                    render(data.results);
                } catch (error) {
                    if (error.name !== 'AbortError' && current === revision) {
                        status.textContent = error.message;
                        list.replaceChildren();
                        const message = document.createElement('li');
                        message.textContent = error.message;
                        message.setAttribute('role', 'presentation');
                        list.append(message);
                        list.hidden = false;
                        results = [];
                        input.setAttribute('aria-expanded', 'true');
                    }
                } finally {
                    if (current === revision) input.removeAttribute('aria-busy');
                }
            }, 300);
        }
        input.addEventListener('input', schedule);
        input.addEventListener('focus', schedule);
        filters.forEach(filter => filter.addEventListener('change', () => {
            close();
            filterHelp.textContent = filters.some(item => item.checked)
                ? 'Press Search to apply your filters.' : 'Select at least one category.';
        }));
        searchForm.addEventListener('focusout', () => setTimeout(() => {
            if (!searchForm.contains(document.activeElement)) close();
        }, 0));
        document.addEventListener('pointerdown', event => {
            if (!searchForm.contains(event.target)) close();
        });
        input.addEventListener('keydown', event => {
            if (event.key === 'Escape') {
                event.preventDefault();
                close();
                return;
            }
            if (list.hidden || !results.length) return;
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                event.preventDefault();
                select(selected < 0 ? (event.key === 'ArrowDown' ? 0 : results.length - 1) :
                    (selected + (event.key === 'ArrowDown' ? 1 : -1) + results.length) % results.length);
            } else if (event.key === 'Enter' && selected >= 0) {
                event.preventDefault();
                openResult(selected);
            }
        });
        searchForm.addEventListener('submit', close);
    }

    document.addEventListener('keydown', event => {
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
            event.preventDefault();
            const input = document.getElementById('discover-input') || document.getElementById('library-search-input');
            if (input) {
                input.focus();
                input.select();
            } else location.assign('/search');
        }
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z' && lastUndo?.isConnected && !event.target.closest('input,textarea,[contenteditable]')) {
            event.preventDefault();
            lastUndo.click();
        }
    });
    document.addEventListener('error', event => {
        if (event.target instanceof HTMLImageElement) {
            const placeholder = document.createElement('span');
            placeholder.className = 'poster-placeholder';
            placeholder.textContent = '◈';
            placeholder.setAttribute('aria-label', 'Image unavailable');
            event.target.replaceWith(placeholder);
        }
    }, true);
})();
