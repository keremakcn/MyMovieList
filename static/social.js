/* Native GET navigation keeps searches bookmarkable and stale results isolated. */
(() => {
    'use strict';
    const form = document.querySelector('.social-search');
    if (!form) return;
    const button = form.querySelector('button[type="submit"]');
    const status = document.getElementById('social-search-status');
    const label = button.textContent;
    let submitting = false;
    function reset() {
        submitting = false;
        button.disabled = false;
        button.textContent = label;
        form.removeAttribute('aria-busy');
        status.textContent = '';
    }
    form.addEventListener('submit', event => {
        if (submitting) {
            event.preventDefault();
            return;
        }
        submitting = true;
        button.disabled = true;
        button.textContent = form.dataset.loading;
        status.textContent = form.dataset.loading;
        form.setAttribute('aria-busy', 'true');
    });
    window.addEventListener('pageshow', reset);
})();
