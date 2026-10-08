/* Explicit profile picks. This screen only searches the owner's local library. */
(() => {
    'use strict';
    const form = document.querySelector('[data-showcase-editor]');
    if (!form) return;
    const {t} = window.MovieListI18n;
    const initial = JSON.parse(document.getElementById('showcase-data').textContent);
    const field = form.elements.record_keys;
    let keys = JSON.parse(field.value);
    let data = initial.choices;
    const films = new Map(initial.selection.map(movie => [movie.record_key, movie]));
    const selected = form.querySelector('[data-showcase-selected]');
    const grid = form.querySelector('[data-showcase-choices]');
    const search = document.getElementById('showcase-search');
    const status = form.querySelector('[data-showcase-status]');
    const retry = form.querySelector('[data-showcase-retry]');
    let controller, timer, revision = 0, loading = false;

    const node = (tag, className, text) => {
        const element = document.createElement(tag);
        if (className) element.className = className;
        if (text !== undefined) element.textContent = text;
        return element;
    };
    function thumbnail(movie) {
        const box = node('span', 'showcase-thumb');
        if (movie.poster_path) {
            const image = node('img');
            image.src = movie.poster_path;
            image.alt = '';
            image.width = 40; image.height = 60;
            image.loading = 'lazy'; image.decoding = 'async';
            box.append(image);
        } else box.append(node('span', 'poster-placeholder', '◈'));
        return box;
    }
    function update(focusKey, action = 'select') {
        field.value = JSON.stringify(keys);
        selected.replaceChildren();
        keys.forEach((key, index) => {
            const movie = films.get(key) || {record_key:key};
            const title = movie.title || t('Film not available on this device');
            const row = node('li', 'showcase-selected-film');
            row.dataset.showcaseKey = key;
            row.append(node('span', 'showcase-order', String(index + 1)), thumbnail(movie));
            const info = node('div', 'showcase-film-info');
            info.append(node('strong', '', title));
            if (!movie.title) info.append(node('small', '', t('Removed or not yet synced. You can remove this pick.')));
            else if (movie.year) info.append(node('small', '', String(movie.year)));
            row.append(info);
            const actions = node('div', 'showcase-film-actions');
            for (const [kind, symbol, label, disabled] of [
                ['earlier', '↑', 'Move {title} earlier', index === 0],
                ['later', '↓', 'Move {title} later', index === keys.length - 1],
                ['remove', '×', 'Remove {title} from showcase', false]
            ]) {
                const button = node('button', 'secondary', symbol);
                button.type = 'button'; button.disabled = disabled;
                button.dataset.showcaseAction = kind;
                button.setAttribute('aria-label', t(label, {title}));
                button.title = t(label, {title});
                button.addEventListener('click', () => {
                    if (kind === 'remove') keys = keys.filter(value => value !== key);
                    else {
                        const destination = index + (kind === 'earlier' ? -1 : 1);
                        [keys[index], keys[destination]] = [keys[destination], keys[index]];
                    }
                    update(kind === 'remove' ? keys[Math.min(index, keys.length - 1)] : key, kind);
                });
                actions.append(button);
            }
            row.append(actions); selected.append(row);
        });
        form.querySelector('[data-showcase-empty]').hidden = keys.length > 0;
        form.querySelector('[data-showcase-count]').textContent = keys.length + '/6';
        renderChoices();
        if (focusKey) {
            const selector = action === 'select' ? `[data-choice-key="${focusKey}"]` :
                `[data-showcase-key="${focusKey}"] [data-showcase-action="${action === 'remove' ? 'remove' : action}"]`;
            form.querySelector(selector)?.focus();
        } else if (action === 'remove') search.focus();
    }
    function renderChoices() {
        grid.replaceChildren();
        grid.setAttribute('aria-busy', String(loading));
        for (const movie of data.movies) {
            films.set(movie.record_key, movie);
            const chosen = keys.includes(movie.record_key);
            const button = node('button', 'showcase-choice');
            button.type = 'button'; button.dataset.choiceKey = movie.record_key;
            button.disabled = loading || (!chosen && keys.length >= 6);
            button.setAttribute('aria-pressed', String(chosen));
            button.setAttribute('aria-label', t(chosen ? 'Remove {title} from showcase' : 'Add {title} to showcase', {title:movie.title}));
            button.append(thumbnail(movie));
            const info = node('span', 'showcase-film-info');
            info.append(node('strong', '', movie.title), node('small', '', movie.year ? String(movie.year) : t('Year unknown')));
            button.append(info, node('span', 'showcase-choice-symbol', chosen ? '✓' : '+'));
            button.addEventListener('click', () => {
                if (chosen) keys = keys.filter(key => key !== movie.record_key);
                else if (keys.length < 6) keys.push(movie.record_key);
                update(movie.record_key);
                status.textContent = keys.length >= 6 ? t('Six films selected. Remove one to choose another.') : '';
            });
            grid.append(button);
        }
        form.querySelector('[data-showcase-page-label]').textContent = t('Page {page} of {pages}', data);
        form.querySelector('[data-showcase-page="previous"]').disabled = loading || data.page <= 1;
        form.querySelector('[data-showcase-page="next"]').disabled = loading || data.page >= data.pages;
    }
    async function load(page = 1) {
        clearTimeout(timer); controller?.abort();
        controller = new AbortController();
        const current = ++revision;
        loading = true; retry.hidden = true;
        status.textContent = t('Loading films…'); renderChoices();
        const params = new URLSearchParams({q:search.value.trim(), page:String(page)});
        try {
            const response = await window.MovieListHTTP.fetch(form.dataset.searchUrl + '?' + params,
                {signal:controller.signal,headers:{Accept:'application/json'},cache:'no-store'});
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || t('Could not load these films. Please try again.'));
            if (current !== revision) return;
            data = result;
            status.textContent = data.movies.length ? '' : t('No films found. Try another title.');
        } catch (error) {
            if (current !== revision || error.name === 'AbortError') return;
            status.textContent = error instanceof TypeError || error instanceof SyntaxError ?
                t('Could not load these films. Please try again.') : error.message;
            retry.hidden = false;
        } finally {
            if (current === revision) {
                loading = false;
                for (const movie of data.movies) films.set(movie.record_key, movie);
                update();
            }
        }
    }
    search.addEventListener('input', () => {
        clearTimeout(timer); controller?.abort(); ++revision;
        timer = setTimeout(() => load(1), 250);
    });
    search.addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); load(1); } });
    form.querySelectorAll('[data-showcase-page]').forEach(button => button.addEventListener('click', () =>
        load(data.page + (button.dataset.showcasePage === 'next' ? 1 : -1))));
    retry.addEventListener('click', () => load(data.page));
    window.addEventListener('pagehide', () => { clearTimeout(timer); controller?.abort(); });
    update();
})();
