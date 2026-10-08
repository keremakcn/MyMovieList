/* Account forms never put passwords or cloud tokens into browser storage. */
(() => {
    'use strict';
    document.querySelectorAll('[data-password-toggle]').forEach(button => {
        button.addEventListener('click', () => {
            const input = document.getElementById(button.dataset.passwordToggle);
            const visible = input.type === 'password';
            input.type = visible ? 'text' : 'password';
            button.setAttribute('aria-pressed', String(visible));
            button.textContent = visible ? button.dataset.hide : button.dataset.show;
        });
    });
    const code = document.querySelector('.auth-code');
    code?.addEventListener('input', () => { code.value = code.value.replace(/[\s-]/g, ''); });
    document.querySelector('[data-auth-error]')?.focus();
    document.querySelectorAll('.account-form').forEach(form => {
        const password = form.querySelector('[name="password"], [name="new_password"]');
        const confirmation = form.querySelector('[name="confirm_password"]');
        if (password && confirmation) {
            const validate = () => confirmation.setCustomValidity(
                confirmation.value && confirmation.value !== password.value ? form.dataset.mismatch : ''
            );
            password.addEventListener('input', validate);
            confirmation.addEventListener('input', validate);
        }
        form.addEventListener('submit', event => {
            if (form.dataset.pending) { event.preventDefault(); return; }
            if (!form.checkValidity()) return;
            form.dataset.pending = '1';
            const button = form.querySelector('button[type="submit"]');
            const label = button.querySelector('[data-submit-label]') || button;
            form.dataset.buttonLabel = label.textContent;
            button.disabled = true;
            label.textContent = form.dataset.loading;
            form.setAttribute('aria-busy', 'true');
        });
    });
    window.addEventListener('pageshow', () => {
        document.querySelectorAll('.account-form[data-pending]').forEach(form => {
            const button = form.querySelector('button[type="submit"]');
            button.disabled = false;
            const label = button.querySelector('[data-submit-label]') || button;
            label.textContent = form.dataset.buttonLabel;
            delete form.dataset.pending;
            form.removeAttribute('aria-busy');
        });
    });
    const menu = document.querySelector('.account-menu');
    const sharing = document.querySelector('[data-profile-sharing]');
    if (sharing) {
        const copy = sharing.querySelector('[data-copy-share]');
        copy.addEventListener('click', async () => {
            const field = sharing.querySelector('[data-sharing-url]');
            try {
                await navigator.clipboard.writeText(field.value);
                copy.textContent = copy.dataset.copied;
                setTimeout(() => { copy.textContent = copy.dataset.copy; }, 2000);
            } catch (_) { field.focus(); field.select(); }
        });
    }
    document.addEventListener('click', event => {
        if (menu?.open && !menu.contains(event.target)) menu.open = false;
    });
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && menu?.open) {
            menu.open = false;
            menu.querySelector('summary').focus();
        }
    });
    document.querySelectorAll('.avatar-option input').forEach(input => {
        input.addEventListener('change', () => {
            const image = input.nextElementSibling;
            const preview = document.querySelector('[data-profile-preview]');
            if (preview) preview.src = image.src;
        });
    });
    const editor = document.querySelector('[data-profile-editor], [data-showcase-editor]');
    const usernameInput = document.querySelector('[data-username-input]');
    usernameInput?.addEventListener('input', () => {
        const preview = document.querySelector('[data-username-preview]');
        preview.textContent = usernameInput.value.trim().toLowerCase();
    });
    if (editor) {
        const snapshot = () => JSON.stringify([...new FormData(editor)]
            .filter(([name]) => name !== 'csrf_token'));
        const initial = snapshot();
        let leaving = false;
        const dirty = () => !leaving && !editor.dataset.pending && snapshot() !== initial;
        window.addEventListener('beforeunload', event => {
            if (!dirty()) return;
            event.preventDefault();
            event.returnValue = '';
        });
        document.addEventListener('click', event => {
            const link = event.target.closest('a[href]');
            if (!link || event.defaultPrevented || event.button !== 0 ||
                event.ctrlKey || event.metaKey || event.shiftKey || event.altKey ||
                link.target === '_blank' || !dirty()) return;
            if (!window.confirm(editor.dataset.discard)) event.preventDefault();
            else leaving = true;
        });
    }
    const resend = document.querySelector('[data-resend]');
    if (resend) {
        const until = Date.now() + Number(resend.dataset.seconds) * 1000;
        const tick = () => {
            const seconds = Math.max(0, Math.ceil((until - Date.now()) / 1000));
            resend.disabled = seconds > 0;
            resend.textContent = seconds ? resend.dataset.countdown.replace('{seconds}', seconds) : resend.dataset.ready;
            if (!seconds) clearInterval(timer);
        };
        let timer;
        const start = () => {
            clearInterval(timer);
            timer = setInterval(tick, 1000);
            tick();
        };
        start();
        window.addEventListener('pagehide', () => clearInterval(timer));
        window.addEventListener('pageshow', start);
    }
    // Status checks are local. The backend owns synchronization and retry limits.
    // Anonymous browsing requires no polling or hosted requests.
    if (!menu && !document.querySelector('.profile-form')) return;
    let pending = false;
    async function update() {
        if (pending || document.hidden) return;
        pending = true;
        try {
            const response = await window.MovieListHTTP.fetch('/api/account/status', {headers: {'Accept':'application/json'}, cache:'no-store'});
            if (!response.ok) return;
            const status = await response.json();
            document.querySelectorAll('[data-cloud-label]').forEach(label => {
                label.textContent = status.label;
                label.dataset.state = status.state;
            });
            document.querySelectorAll('[data-cloud-pending]').forEach(label => label.textContent = status.pending);
            document.querySelectorAll('[data-cloud-conflicts]').forEach(label => label.textContent = status.conflicts);
            document.querySelectorAll('[data-cloud-message]').forEach(label => label.textContent = status.message);
            const notice = document.querySelector('[data-profile-sync-notice]');
            if (notice) notice.hidden = !['offline', 'waiting', 'attention'].includes(status.state);
            const conflictLink = document.querySelector('[data-conflicts-link]');
            if (conflictLink) conflictLink.hidden = !status.conflicts;
            const name = document.querySelector('[data-account-name]');
            if (name) name.textContent = status.profile.display_name || name.dataset.accountEmpty;
            const avatar = document.querySelector('[data-account-avatar]');
            if (avatar) avatar.src = '/static/avatars/' + status.profile.avatar_id + '.svg';
            const profileName = document.querySelector('[data-profile-name]');
            if (profileName) profileName.textContent = status.profile.display_name || profileName.dataset.profileEmpty;
            const profileAvatar = document.querySelector('[data-profile-avatar]');
            if (profileAvatar) profileAvatar.src = '/static/avatars/' + status.profile.avatar_id + '.svg';
            const profileUsername = document.querySelector('[data-profile-username]');
            if (profileUsername && status.username) {
                profileUsername.hidden = !status.username.username;
                profileUsername.textContent = status.username.username ? '@' + status.username.username : '';
            }
            if (sharing && status.sharing) {
                const value = status.sharing;
                sharing.querySelector('[data-sharing-label]').textContent = value.label;
                sharing.querySelector('[data-sharing-paused]').hidden = status.enabled;
                const badge = document.querySelector('[data-sharing-badge-text]');
                if (badge) badge.textContent = value.badge;
                sharing.querySelector('[data-sharing-link]').hidden = !value.is_public || value.pending === 'unpublish';
                sharing.querySelector('[data-sharing-url]').value = value.url || '';
                sharing.querySelector('[data-sharing-preview]').href = value.visitor_path || '#';
                sharing.querySelector('[data-sharing-publish]').hidden = value.is_public || Boolean(value.pending);
                sharing.querySelector('[data-sharing-publish-button]').disabled = !value.ready || !value.checked || Boolean(value.error) || !status.enabled;
                sharing.querySelector('[data-sharing-revoke]').hidden = !value.is_public && value.pending !== 'publish';
            }
        } catch (_) { /* Keep the rendered local state when the connection fails. */ }
        finally { pending = false; }
    }
    let timer;
    function start() {
        clearInterval(timer);
        update();
        timer = setInterval(update, 15000);
    }
    start();
    window.addEventListener('pageshow', start);
    window.addEventListener('pagehide', () => clearInterval(timer));
    document.addEventListener('visibilitychange', () => { if (!document.hidden) update(); });
})();
