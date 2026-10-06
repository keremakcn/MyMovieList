/* Explicit UI messages only. Never translate DOM contents or movie data. */
(() => {
    'use strict';
    const messages = JSON.parse(document.getElementById('ui-translations').textContent);
    window.MovieListI18n = Object.freeze({
        t(message, values = {}) {
            const translated = Object.hasOwn(messages, message) ? messages[message] : message;
            return translated.replace(/\{([a-z_]+)\}/g, (match, key) =>
                Object.hasOwn(values, key) ? String(values[key]) : match);
        }
    });
    // Back/forward may revive an old-language document after Settings changed.
    // Read the saved preference only; never re-detect the operating system.
    addEventListener('pageshow', async event => {
        if (!event.persisted) return;
        try {
            const response = await fetch('/api/ui-language');
            if (!response.ok) return;
            const data = await response.json();
            if (['en', 'tr'].includes(data.language) && data.language !== document.documentElement.lang) location.reload();
        } catch { /* An offline library remains usable in its current language. */ }
    });
})();
