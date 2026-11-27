/* ============================================================================
   MyMovieList · Cinema Atmosphere, 3D Tactile Physics, FLIP & Spotlight Engine
   100% Strict CSP Safe · Respects prefers-reduced-motion & Offline Library Scope
   ============================================================================ */
(() => {
    'use strict';

    const i18n = window.MovieListI18n || {t: s => s};
    const {t} = i18n;
    const reducedMotionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    let reduceMotion = reducedMotionQuery.matches;
    reducedMotionQuery.addEventListener?.('change', e => { reduceMotion = e.matches; });

    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    const csrf = csrfMeta ? csrfMeta.content : '';

    /* ----------------------------------------------------------------------
       1. Collapsible Floating Desktop Sidebar Persistence
       ---------------------------------------------------------------------- */
    const SIDEBAR_KEY = 'mml-sidebar-collapsed';
    try {
        if (localStorage.getItem(SIDEBAR_KEY) === '1') {
            document.body.classList.add('sidebar-collapsed');
        }
    } catch (_) {}

    document.querySelectorAll('[data-sidebar-toggle]').forEach(btn => {
        const syncState = () => {
            const collapsed = document.body.classList.contains('sidebar-collapsed');
            btn.setAttribute('aria-pressed', String(collapsed));
        };
        syncState();
        btn.addEventListener('click', () => {
            const next = !document.body.classList.contains('sidebar-collapsed');
            document.body.classList.toggle('sidebar-collapsed', next);
            try { localStorage.setItem(SIDEBAR_KEY, next ? '1' : '0'); } catch (_) {}
            syncState();
        });
    });

    /* ----------------------------------------------------------------------
       2. Real-Time Ambient Backdrop Bleed Projector (<canvas>)
       Samples local posters or derives a rich harmonic palette per film
       ---------------------------------------------------------------------- */
    const ambientCanvas = document.getElementById('ambient-canvas');
    const ambientState = {
        curR1: 196, curG1: 177, curB1: 255,
        curR2: 235, curG2: 208, curB2: 150,
        tgtR1: 196, tgtG1: 177, tgtB1: 255,
        tgtR2: 235, tgtG2: 208, tgtB2: 150,
        raf: 0
    };
    const sampleCache = new Map();
    const samplerCanvas = document.createElement('canvas');
    samplerCanvas.width = 12;
    samplerCanvas.height = 12;
    const samplerCtx = samplerCanvas.getContext('2d', {willReadFrequently: true});

    function hashPalette(seedText) {
        let h = 2166136261;
        const str = String(seedText || 'MyMovieList');
        for (let i = 0; i < str.length; i++) {
            h ^= str.charCodeAt(i);
            h = Math.imul(h, 16777619);
        }
        const palettes = [
            [[196, 168, 255], [235, 204, 142]],
            [[116, 182, 246], [218, 165, 255]],
            [[242, 142, 168], [238, 202, 136]],
            [[118, 214, 178], [186, 168, 255]],
            [[236, 172, 118], [174, 138, 242]],
            [[156, 142, 252], [244, 152, 178]]
        ];
        return palettes[Math.abs(h) % palettes.length];
    }

    function extractImagePalette(img, fallbackSeed) {
        const key = img?.currentSrc || img?.src || fallbackSeed || '';
        if (sampleCache.has(key)) return sampleCache.get(key);
        let result = null;
        if (img && img.complete && img.naturalWidth > 0 && samplerCtx) {
            try {
                const sameOrigin = key.startsWith(location.origin) || key.startsWith('/');
                if (sameOrigin) {
                    samplerCtx.drawImage(img, 0, 0, 12, 12);
                    const data = samplerCtx.getImageData(0, 0, 12, 12).data;
                    let r1 = 0, g1 = 0, b1 = 0, c1 = 0;
                    let r2 = 0, g2 = 0, b2 = 0, c2 = 0;
                    for (let i = 0; i < data.length; i += 4) {
                        const r = data[i], g = data[i + 1], b = data[i + 2];
                        const lum = (r + g + b) / 3;
                        if (lum < 22 || lum > 242) continue;
                        if (i < data.length / 2) { r1 += r; g1 += g; b1 += b; c1++; }
                        else { r2 += r; g2 += g; b2 += b; c2++; }
                    }
                    if (c1 > 4) {
                        const p1 = [Math.min(245, Math.round(r1 / c1 * 1.18)), Math.min(245, Math.round(g1 / c1 * 1.18)), Math.min(255, Math.round(b1 / c1 * 1.22))];
                        const p2 = c2 > 4
                            ? [Math.min(245, Math.round(r2 / c2 * 1.18)), Math.min(245, Math.round(g2 / c2 * 1.18)), Math.min(255, Math.round(b2 / c2 * 1.18))]
                            : [235, 208, 150];
                        result = [p1, p2];
                    }
                }
            } catch (_) {
                result = null;
            }
        }
        if (!result) result = hashPalette(fallbackSeed || key);
        if (sampleCache.size > 120) sampleCache.clear();
        sampleCache.set(key, result);
        return result;
    }

    function renderAmbientFrame() {
        ambientState.raf = 0;
        const lerp = 0.08;
        ambientState.curR1 += (ambientState.tgtR1 - ambientState.curR1) * lerp;
        ambientState.curG1 += (ambientState.tgtG1 - ambientState.curG1) * lerp;
        ambientState.curB1 += (ambientState.tgtB1 - ambientState.curB1) * lerp;
        ambientState.curR2 += (ambientState.tgtR2 - ambientState.curR2) * lerp;
        ambientState.curG2 += (ambientState.tgtG2 - ambientState.curG2) * lerp;
        ambientState.curB2 += (ambientState.tgtB2 - ambientState.curB2) * lerp;

        const r1 = Math.round(ambientState.curR1), g1 = Math.round(ambientState.curG1), b1 = Math.round(ambientState.curB1);
        const r2 = Math.round(ambientState.curR2), g2 = Math.round(ambientState.curG2), b2 = Math.round(ambientState.curB2);

        document.documentElement.style.setProperty('--ambient-r', String(r1));
        document.documentElement.style.setProperty('--ambient-g', String(g1));
        document.documentElement.style.setProperty('--ambient-b', String(b1));
        document.documentElement.style.setProperty('--ambient-2-r', String(r2));
        document.documentElement.style.setProperty('--ambient-2-g', String(g2));
        document.documentElement.style.setProperty('--ambient-2-b', String(b2));

        if (ambientCanvas) {
            const ctx = ambientCanvas.getContext('2d');
            if (ctx) {
                const w = ambientCanvas.width = Math.min(window.innerWidth, 960);
                const h = ambientCanvas.height = Math.min(window.innerHeight, 640);
                ctx.clearRect(0, 0, w, h);
                const grad1 = ctx.createRadialGradient(w * 0.56, h * 0.14, 10, w * 0.56, h * 0.14, w * 0.58);
                grad1.addColorStop(0, `rgba(${r1}, ${g1}, ${b1}, 0.20)`);
                grad1.addColorStop(1, 'rgba(0, 0, 0, 0)');
                ctx.fillStyle = grad1;
                ctx.fillRect(0, 0, w, h);

                const grad2 = ctx.createRadialGradient(w * 0.88, h * 0.42, 10, w * 0.88, h * 0.42, w * 0.46);
                grad2.addColorStop(0, `rgba(${r2}, ${g2}, ${b2}, 0.13)`);
                grad2.addColorStop(1, 'rgba(0, 0, 0, 0)');
                ctx.fillStyle = grad2;
                ctx.fillRect(0, 0, w, h);
            }
        }

        const delta = Math.abs(ambientState.tgtR1 - ambientState.curR1) + Math.abs(ambientState.tgtG1 - ambientState.curG1) + Math.abs(ambientState.tgtB1 - ambientState.curB1);
        if (delta > 0.8 && !reduceMotion) {
            ambientState.raf = requestAnimationFrame(renderAmbientFrame);
        }
    }

    function setAmbientTarget(p1, p2) {
        ambientState.tgtR1 = p1[0]; ambientState.tgtG1 = p1[1]; ambientState.tgtB1 = p1[2];
        ambientState.tgtR2 = p2[0]; ambientState.tgtG2 = p2[1]; ambientState.tgtB2 = p2[2];
        if (!ambientState.raf) ambientState.raf = requestAnimationFrame(renderAmbientFrame);
    }

    // Seed ambient light from detail poster/backdrop on page open
    const heroImg = document.querySelector('.detail-poster, .detail-backdrop img');
    if (heroImg) {
        const applyDetailBleed = () => {
            const titleSeed = document.querySelector('h1')?.textContent || '';
            const [p1, p2] = extractImagePalette(heroImg, titleSeed);
            setAmbientTarget(p1, p2);
        };
        if (heroImg.complete) applyDetailBleed();
        else heroImg.addEventListener('load', applyDetailBleed, {once: true});
    } else {
        renderAmbientFrame();
    }

    /* ----------------------------------------------------------------------
       3. 3D Perspective Tilt & Specular Holographic Glare (60fps GPU)
       ---------------------------------------------------------------------- */
    const TILT_SELECTOR = '.movie-card, .discovery-card, .profile-film-poster, .taste-card';
    let activeTiltEl = null;

    document.addEventListener('pointermove', event => {
        if (reduceMotion || event.pointerType === 'touch') return;
        const card = event.target.closest(TILT_SELECTOR);
        if (!card || card.closest('.view-shelf')) {
            if (activeTiltEl) {
                activeTiltEl.classList.remove('is-tilting');
                activeTiltEl.style.setProperty('--glare-opacity', '0');
                activeTiltEl = null;
            }
            if (card && card.closest('.view-shelf')) {
                const img = card.querySelector('.shelf-card-backdrop-img, .movie-card-poster, .shelf-spine-art');
                const seed = card.dataset.title || card.querySelector('h2, h3, strong')?.textContent || '';
                if (card.dataset.ambientSynced !== '1') {
                    document.querySelectorAll('.view-shelf .movie-card[data-ambient-synced="1"]').forEach(c => { delete c.dataset.ambientSynced; });
                    card.dataset.ambientSynced = '1';
                    const [p1, p2] = extractImagePalette(img, seed);
                    setAmbientTarget(p1, p2);
                }
            }
            return;
        }
        if (activeTiltEl && activeTiltEl !== card) {
            activeTiltEl.classList.remove('is-tilting');
            activeTiltEl.style.setProperty('--glare-opacity', '0');
        }
        if (activeTiltEl !== card) {
            activeTiltEl = card;
            const img = card.querySelector('img');
            const seed = card.dataset.title || card.querySelector('h2, h3, strong')?.textContent || '';
            const [p1, p2] = extractImagePalette(img, seed);
            setAmbientTarget(p1, p2);
        }
        const rect = card.getBoundingClientRect();
        if (!rect.width || !rect.height) return;
        const px = (event.clientX - rect.left) / rect.width;
        const py = (event.clientY - rect.top) / rect.height;
        const ry = ((px - 0.5) * 9).toFixed(2) + 'deg';
        const rx = ((0.5 - py) * 9).toFixed(2) + 'deg';
        card.classList.add('is-tilting');
        card.style.setProperty('--rx', rx);
        card.style.setProperty('--ry', ry);
        card.style.setProperty('--gx', Math.round(px * 100) + '%');
        card.style.setProperty('--gy', Math.round(py * 100) + '%');
        card.style.setProperty('--glare-opacity', '1');
    }, {passive: true});

    document.addEventListener('pointerleave', () => {
        if (activeTiltEl) {
            activeTiltEl.classList.remove('is-tilting');
            activeTiltEl.style.setProperty('--glare-opacity', '0');
            activeTiltEl = null;
        }
    }, {passive: true});

    // Touch / click support for 3D Spatial Shelf spines
    document.addEventListener('click', event => {
        const spine = event.target.closest('.shelf-spine-face');
        if (!spine) return;
        const card = spine.closest('.movie-card');
        if (!card) return;
        const list = card.closest('.view-shelf');
        if (!list) return;
        const alreadyOpen = card.classList.contains('is-shelf-open');
        list.querySelectorAll('.movie-card.is-shelf-open').forEach(c => c.classList.remove('is-shelf-open'));
        if (!alreadyOpen) {
            card.classList.add('is-shelf-open');
            const img = card.querySelector('.shelf-card-backdrop-img, .movie-card-poster, .shelf-spine-art');
            const seed = card.dataset.title || card.querySelector('h2, h3, strong')?.textContent || '';
            const [p1, p2] = extractImagePalette(img, seed);
            setAmbientTarget(p1, p2);
        }
    });

    /* ----------------------------------------------------------------------
       4. Zero-Cut Cinema Shared-Element FLIP Poster Transitions
       ---------------------------------------------------------------------- */
    const FLIP_KEY = 'mml-poster-flip';
    document.addEventListener('click', event => {
        if (reduceMotion || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey) return;
        const link = event.target.closest('a[href*="/movie/"], a[href*="/catalog_movie/"]');
        if (!link) return;
        const card = link.closest('.movie-card, .discovery-card, .catalog-card, .profile-film, .lobby-hero');
        const img = card?.querySelector('img');
        if (!img) return;
        const rect = img.getBoundingClientRect();
        if (rect.width < 20 || rect.height < 20) return;
        try {
            sessionStorage.setItem(FLIP_KEY, JSON.stringify({
                href: new URL(link.href, location.origin).pathname,
                left: rect.left,
                top: rect.top,
                width: rect.width,
                height: rect.height,
                ts: Date.now()
            }));
        } catch (_) {}
    });

    (() => {
        if (reduceMotion) return;
        let saved = null;
        try {
            const raw = sessionStorage.getItem(FLIP_KEY);
            if (raw) {
                sessionStorage.removeItem(FLIP_KEY);
                saved = JSON.parse(raw);
            }
        } catch (_) {}
        if (!saved || Date.now() - saved.ts > 2500 || saved.href !== location.pathname) return;
        const target = document.querySelector('.detail-poster');
        if (!target) return;
        const end = target.getBoundingClientRect();
        if (!end.width || !end.height) return;
        const dx = saved.left - end.left;
        const dy = saved.top - end.top;
        const sw = saved.width / end.width;
        const sh = saved.height / end.height;
        target.animate([
            {transformOrigin: 'top left', transform: `translate(${dx}px, ${dy}px) scale(${sw}, ${sh})`, borderRadius: '9px'},
            {transformOrigin: 'top left', transform: 'translate(0, 0) scale(1, 1)', borderRadius: '14px'}
        ], {
            duration: 420,
            easing: 'cubic-bezier(0.22, 1, 0.36, 1)'
        });
    })();

    /* ----------------------------------------------------------------------
       5. Sliding Pill Filter Capsule Indicator
       ---------------------------------------------------------------------- */
    function updateSlidingPill() {
        const group = document.querySelector('.filter-group');
        if (!group) return;
        let pill = group.querySelector('.filter-pill-indicator');
        if (!pill) {
            pill = document.createElement('span');
            pill.className = 'filter-pill-indicator';
            pill.setAttribute('aria-hidden', 'true');
            group.prepend(pill);
        }
        const active = group.querySelector('.active-filter');
        if (!active) {
            pill.style.setProperty('opacity', '0');
            return;
        }
        group.classList.add('has-sliding-pill');
        const gRect = group.getBoundingClientRect();
        const aRect = active.getBoundingClientRect();
        const x = aRect.left - gRect.left - 5;
        const y = aRect.top - gRect.top - 5;
        pill.style.setProperty('width', `${aRect.width}px`);
        pill.style.setProperty('height', `${aRect.height}px`);
        pill.style.setProperty('transform', `translate(${x}px, ${y}px)`);
        pill.style.setProperty('opacity', '1');
    }
    updateSlidingPill();
    window.addEventListener('resize', updateSlidingPill, {passive: true});

    /* ----------------------------------------------------------------------
       6. Micro-Particle Heart Burst on Person / Movie Favorite Toggle
       ---------------------------------------------------------------------- */
    const particleCanvas = document.getElementById('particle-canvas');
    const particles = [];
    let particleRaf = 0;

    function tickParticles() {
        if (!particleCanvas) { particleRaf = 0; return; }
        const ctx = particleCanvas.getContext('2d');
        particleCanvas.width = window.innerWidth;
        particleCanvas.height = window.innerHeight;
        ctx.clearRect(0, 0, particleCanvas.width, particleCanvas.height);
        for (let i = particles.length - 1; i >= 0; i--) {
            const p = particles[i];
            p.x += p.vx;
            p.y += p.vy;
            p.vy += 0.14;
            p.life -= 0.026;
            if (p.life <= 0) {
                particles.splice(i, 1);
                continue;
            }
            ctx.globalAlpha = Math.max(0, p.life);
            ctx.fillStyle = p.color;
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
            ctx.fill();
        }
        particleRaf = particles.length ? requestAnimationFrame(tickParticles) : 0;
    }

    function spawnHeartBurst(originEl) {
        if (reduceMotion || !particleCanvas || !originEl) return;
        const rect = originEl.getBoundingClientRect();
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        const colors = ['#ff7695', '#ebd096', '#cbb9ff', '#ff9eb5'];
        for (let i = 0; i < 16; i++) {
            const angle = (Math.PI * 2 * i) / 16 + (Math.random() - 0.5) * 0.3;
            const speed = 1.8 + Math.random() * 3.2;
            particles.push({
                x: cx,
                y: cy,
                vx: Math.cos(angle) * speed,
                vy: Math.sin(angle) * speed - 1.2,
                size: 2 + Math.random() * 2.5,
                color: colors[i % colors.length],
                life: 1
            });
        }
        if (!particleRaf) particleRaf = requestAnimationFrame(tickParticles);
    }

    document.addEventListener('click', event => {
        const favBtn = event.target.closest('.person-favorite-button, form[action*="/favorite/"] button');
        if (favBtn && favBtn.getAttribute('aria-pressed') !== 'true') {
            spawnHeartBurst(favBtn);
        }
    });

    /* ----------------------------------------------------------------------
       7. Scrollytelling Counters & Reveal Observer (/stats & Lists)
       ---------------------------------------------------------------------- */
    function animateCounters() {
        document.querySelectorAll('[data-count-target]').forEach(node => {
            if (node.dataset.counted) return;
            node.dataset.counted = '1';
            const raw = Number(node.dataset.countTarget);
            if (!Number.isFinite(raw) || reduceMotion || raw === 0) return;
            const decimals = Number(node.dataset.countDecimals || '0');
            const prefix = node.dataset.countPrefix || '';
            const suffix = node.dataset.countSuffix || '';
            const start = performance.now();
            const duration = 760;
            const step = now => {
                const progress = Math.min(1, (now - start) / duration);
                const eased = 1 - Math.pow(1 - progress, 3);
                const current = (raw * eased).toFixed(decimals);
                node.textContent = `${prefix}${current}${suffix}`;
                if (progress < 1) requestAnimationFrame(step);
                else node.textContent = `${prefix}${raw.toFixed(decimals).replace(/\.0$/, decimals ? '.0' : '')}${suffix}`;
            };
            requestAnimationFrame(step);
        });
    }
    animateCounters();

    /* ----------------------------------------------------------------------
       8. Discovery Dial ("Keşif Kadranı") Interactive Station Controller
       ---------------------------------------------------------------------- */
    const tuner = document.querySelector('[data-discovery-tuner]');
    if (tuner) {
        const modeSelect = document.getElementById('discovery-mode');
        const modeForm = modeSelect?.closest('form');
        tuner.addEventListener('click', event => {
            const btn = event.target.closest('[data-dial-mode]');
            if (!btn || !modeSelect || !modeForm) return;
            const nextMode = btn.dataset.dialMode;
            tuner.dataset.activeMode = nextMode;
            tuner.querySelectorAll('[data-dial-mode]').forEach(b => {
                b.setAttribute('aria-pressed', String(b === btn));
            });
            if (modeSelect.value !== nextMode) {
                modeSelect.value = nextMode;
                modeForm.requestSubmit();
            }
        });
    }

    /* ----------------------------------------------------------------------
       9. Explore Cinema Lobby — Live Hero Showcase & Hide-Library Switch
       ---------------------------------------------------------------------- */
    const lobbyHero = document.querySelector('[data-lobby-hero]');
    if (lobbyHero) {
        let heroItems = [];
        let heroIdx = 0;
        let heroTimer = 0;

        function renderHeroSlide(idx) {
            if (!heroItems.length) return;
            heroIdx = (idx + heroItems.length) % heroItems.length;
            const item = heroItems[heroIdx];
            const titleEl = lobbyHero.querySelector('[data-hero-title]');
            const metaEl = lobbyHero.querySelector('[data-hero-meta]');
            const linkEl = lobbyHero.querySelector('[data-hero-open]');
            const posterLinkEl = lobbyHero.querySelector('[data-hero-poster-link]');
            const posterImgEl = lobbyHero.querySelector('[data-hero-poster]');
            const bgImgEl = lobbyHero.querySelector('[data-hero-bg]');
            if (titleEl) titleEl.textContent = item.title;
            if (metaEl) metaEl.textContent = item.meta;
            if (linkEl) linkEl.href = item.href;
            if (posterLinkEl) posterLinkEl.href = item.href;
            if (posterImgEl) {
                if (item.posterSrc) {
                    posterImgEl.src = item.posterSrc;
                    posterImgEl.alt = item.title;
                    posterImgEl.hidden = false;
                } else {
                    posterImgEl.hidden = true;
                }
            }
            if (bgImgEl) {
                if (item.posterSrc) {
                    bgImgEl.src = item.posterSrc;
                    bgImgEl.hidden = false;
                } else {
                    bgImgEl.hidden = true;
                }
            }
            if (item.posterSrc) {
                const img = lobbyHero.querySelector(`[data-hero-slide="${heroIdx}"] img`);
                const [p1, p2] = extractImagePalette(img, item.title);
                setAmbientTarget(p1, p2);
            }
            lobbyHero.querySelectorAll('[data-hero-slide]').forEach((btn, i) => {
                btn.classList.toggle('is-active', i === heroIdx);
                btn.setAttribute('aria-pressed', String(i === heroIdx));
            });
        }

        function hydrateHeroFromTrending() {
            const cards = [...document.querySelectorAll('#discovery-trending .discovery-card')].slice(0, 5);
            if (!cards.length) return;
            heroItems = cards.map(card => {
                const titleLink = card.querySelector('h3 a');
                const img = card.querySelector('.discovery-poster img');
                const meta = card.querySelector('.discovery-card-meta')?.textContent.replace(/\s+/g, ' ').trim() || '';
                return {
                    title: titleLink?.textContent.trim() || '',
                    href: titleLink?.getAttribute('href') || '/search',
                    posterSrc: img?.getAttribute('src') || '',
                    meta
                };
            }).filter(x => x.title);
            if (!heroItems.length) return;
            const thumbsWrap = lobbyHero.querySelector('[data-hero-thumbs]');
            if (thumbsWrap) {
                thumbsWrap.replaceChildren(...heroItems.map((item, idx) => {
                    const btn = document.createElement('button');
                    btn.type = 'button';
                    btn.className = 'lobby-hero-thumb' + (idx === 0 ? ' is-active' : '');
                    btn.dataset.heroSlide = String(idx);
                    btn.setAttribute('aria-label', item.title);
                    btn.setAttribute('aria-pressed', String(idx === 0));
                    if (item.posterSrc) {
                        const im = document.createElement('img');
                        im.src = item.posterSrc;
                        im.alt = '';
                        im.loading = 'lazy';
                        btn.append(im);
                    } else {
                        btn.textContent = '◈';
                    }
                    btn.addEventListener('click', () => {
                        clearInterval(heroTimer);
                        renderHeroSlide(idx);
                    });
                    return btn;
                }));
            }
            lobbyHero.hidden = false;
            renderHeroSlide(0);
            clearInterval(heroTimer);
            if (!reduceMotion) {
                heroTimer = setInterval(() => {
                    if (!document.hidden) renderHeroSlide(heroIdx + 1);
                }, 6500);
            }
        }

        const trendingFeed = document.querySelector('#discovery-trending [data-discovery-feed]');
        if (trendingFeed) {
            const mo = new MutationObserver(() => hydrateHeroFromTrending());
            mo.observe(trendingFeed, {childList: true});
            hydrateHeroFromTrending();
        }
    }

    // Live "Hide films in my library" switch on Explore Lobby
    const lobbyHideToggle = document.querySelector('[data-lobby-hide-library]');
    if (lobbyHideToggle) {
        const applyLobbyHide = () => {
            const hide = lobbyHideToggle.checked;
            document.querySelectorAll('.discovery-home .discovery-card').forEach(card => {
                const inLib = Boolean(card.querySelector('.in-library, .discovery-library-badge'));
                card.classList.toggle('is-hidden-by-toggle', hide && inLib);
            });
        };
        lobbyHideToggle.addEventListener('change', applyLobbyHide);
        document.addEventListener('library-movie-added', () => setTimeout(applyLobbyHide, 40));
    }

    /* ----------------------------------------------------------------------
       10. Live Public/Private Showcase Visibility Matrix & Drag-Drop Booth
       ---------------------------------------------------------------------- */
    const showcaseForm = document.querySelector('[data-showcase-editor]');
    if (showcaseForm) {
        const syncVisibilityPreview = () => {
            const showRatings = showcaseForm.querySelector('input[name="show_ratings"]')?.checked;
            const showStats = showcaseForm.querySelector('input[name="show_stats"]')?.checked;
            const ratingItem = document.querySelector('[data-vis-item="ratings"]');
            const statsItem = document.querySelector('[data-vis-item="stats"]');
            if (ratingItem) ratingItem.dataset.visOff = String(!showRatings);
            if (statsItem) statsItem.dataset.visOff = String(!showStats);
        };
        showcaseForm.addEventListener('change', syncVisibilityPreview);
        syncVisibilityPreview();
    }

    // External Import Drag-and-Drop Booth + Spinning 35mm Reel state
    const importCard = document.getElementById('external-import');
    if (importCard) {
        const fileInput = document.getElementById('external-import-file');
        const booth = importCard.querySelector('[data-import-booth]');
        const fileReadout = importCard.querySelector('[data-import-filename]');
        const form = importCard.querySelector('form');

        if (fileInput && fileReadout) {
            fileInput.addEventListener('change', () => {
                const f = fileInput.files?.[0];
                if (f) fileReadout.textContent = `${f.name} (${Math.max(1, Math.round(f.size / 1024))} KB)`;
            });
        }
        if (booth && fileInput) {
            booth.addEventListener('dragover', e => { e.preventDefault(); booth.classList.add('is-dragover'); });
            booth.addEventListener('dragleave', () => booth.classList.remove('is-dragover'));
            booth.addEventListener('drop', e => {
                e.preventDefault();
                booth.classList.remove('is-dragover');
                if (e.dataTransfer?.files?.length) {
                    fileInput.files = e.dataTransfer.files;
                    fileInput.dispatchEvent(new Event('change', {bubbles: true}));
                }
            });
        }
        if (form) {
            form.addEventListener('submit', () => {
                importCard.classList.add('is-importing');
            });
        }
    }

    /* ----------------------------------------------------------------------
       11. Universal Ctrl+K / ⌘K Spotlight Command Palette
       ---------------------------------------------------------------------- */
    const dialog = document.getElementById('command-palette');
    if (dialog) {
        const cmdInput = document.getElementById('command-palette-input');
        const cmdBody = document.getElementById('command-palette-body');
        let cmdIndex = 0;
        let cmdRows = [];
        let cmdTimer = 0;
        let cmdController = null;
        let lastSearchCache = {q: '', library: [], catalog: []};

        function getStaticCommands() {
            const currentLang = document.documentElement.lang === 'tr' ? 'tr' : 'en';
            const nextLang = currentLang === 'tr' ? 'en' : 'tr';
            const nextLangLabel = nextLang === 'tr' ? 'Türkçe (TR)' : 'English (EN)';
            return [
                {
                    group: t('Quick actions'),
                    title: t('3D Spatial Shelf view'),
                    subtitle: t('View your collection as physical 3D spines'),
                    badge: '1',
                    run: () => switchViewCommand('shelf')
                },
                {
                    group: t('Quick actions'),
                    title: t('Cinematic Poster Grid'),
                    subtitle: t('Portrait posters with dynamic glare & note badges'),
                    badge: '2',
                    run: () => switchViewCommand('posters')
                },
                {
                    group: t('Quick actions'),
                    title: t("Critic's Editorial List"),
                    subtitle: t('Filmstrip dossier with director, date & journal'),
                    badge: '3',
                    run: () => switchViewCommand('cards')
                },
                {
                    group: t('Quick actions'),
                    title: `${t('Switch interface language')} → ${nextLangLabel}`,
                    subtitle: t('Instant bilingual interface switch'),
                    badge: nextLang.toUpperCase(),
                    run: () => switchLanguageCommand(nextLang)
                },
                {
                    group: t('Navigate'),
                    title: t('Library'),
                    subtitle: t('Your personal collection'),
                    badge: 'G L',
                    run: () => location.assign('/')
                },
                {
                    group: t('Navigate'),
                    title: t('Explore'),
                    subtitle: t('Trending, top rated & genre portals'),
                    badge: 'G E',
                    run: () => location.assign('/search')
                },
                {
                    group: t('Navigate'),
                    title: t('For you'),
                    subtitle: t('3-mode personal discovery frequency dial'),
                    badge: 'G R',
                    run: () => location.assign('/recommendations')
                },
                {
                    group: t('Navigate'),
                    title: t('Cinema stats'),
                    subtitle: t('Constellation radar, heatmap & auteur podium'),
                    badge: 'G S',
                    run: () => location.assign('/stats')
                },
                {
                    group: t('Navigate'),
                    title: t('Social'),
                    subtitle: t('Public showcases & watched this week'),
                    badge: 'G C',
                    run: () => location.assign('/social')
                },
                {
                    group: t('Navigate'),
                    title: t('Favorite people'),
                    subtitle: t('Private actors & directors collection'),
                    badge: 'G P',
                    run: () => location.assign('/people/favorites')
                },
                {
                    group: t('Navigate'),
                    title: t('Import from Letterboxd or IMDb'),
                    subtitle: t('Bring .zip or .csv history into your vault'),
                    badge: '↗',
                    run: () => location.assign('/settings#external-import')
                }
            ];
        }

        function switchViewCommand(mode) {
            try { localStorage.setItem('mml-library-view', mode); } catch (_) {}
            dialog.close();
            const btn = document.querySelector(`[data-library-view="${mode}"]`);
            if (btn) btn.click();
            else location.assign('/');
        }

        async function switchLanguageCommand(lang) {
            const fd = new FormData();
            fd.set('language', lang);
            fd.set('stay', '1');
            try {
                const res = await window.MovieListHTTP.fetch('/settings/language', {
                    method: 'POST',
                    body: fd,
                    headers: {'X-CSRF-Token': csrf, 'Accept': 'application/json'}
                });
                if (res.ok) location.reload();
            } catch (_) {}
        }

        async function quickAddFromSpotlight(tmdbId, watched, buttonEl) {
            buttonEl.disabled = true;
            const fd = new FormData();
            fd.set('movie_id', String(tmdbId));
            fd.set('next', location.pathname + location.search);
            try {
                const endpoint = watched ? '/add_watched_from_catalog' : '/add_from_catalog';
                const res = await window.MovieListHTTP.fetch(endpoint, {
                    method: 'POST',
                    body: fd,
                    headers: {'X-CSRF-Token': csrf, 'Accept': 'application/json'}
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.error || 'Error');
                const parent = buttonEl.closest('.command-inline-actions');
                if (parent) {
                    const badge = document.createElement('span');
                    badge.className = 'command-mini-btn is-saved';
                    badge.textContent = watched ? `✓ ${t('Watched')}` : `✓ ${t('In your library')}`;
                    parent.replaceChildren(badge);
                }
                const hit = lastSearchCache.catalog.find(c => c.kind === 'movie' && c.tmdb_id === tmdbId);
                if (hit) hit.library = {id: data.id, status: data.status};
                document.dispatchEvent(new CustomEvent('library-movie-added', {
                    detail: {tmdbId: String(tmdbId), restoreFocus: false, status: data.status, editUrl: data.edit_url}
                }));
            } catch (_) {
                buttonEl.disabled = false;
            }
        }

        function setActiveRow(nextIdx) {
            if (!cmdRows.length) return;
            cmdIndex = (nextIdx + cmdRows.length) % cmdRows.length;
            cmdRows.forEach((r, idx) => {
                r.el.setAttribute('aria-selected', String(idx === cmdIndex));
                if (idx === cmdIndex) r.el.scrollIntoView({block: 'nearest'});
            });
        }

        function renderCommandPalette() {
            const q = (cmdInput?.value || '').trim();
            const qFold = q.toLowerCase();
            cmdBody.replaceChildren();
            cmdRows = [];

            const addSection = (label, items) => {
                if (!items.length) return;
                const heading = document.createElement('div');
                heading.className = 'command-group-label';
                heading.textContent = label;
                const ul = document.createElement('ul');
                ul.className = 'command-list';
                ul.setAttribute('role', 'listbox');
                for (const item of items) {
                    const li = document.createElement('li');
                    li.className = 'command-row';
                    li.setAttribute('role', 'option');
                    li.setAttribute('aria-selected', 'false');

                    const main = document.createElement('div');
                    main.className = 'command-row-main';

                    if (item.image) {
                        const img = document.createElement('img');
                        img.className = 'command-thumb';
                        img.src = item.image;
                        img.alt = '';
                        main.append(img);
                    } else {
                        const chip = document.createElement('span');
                        chip.className = item.isMedia ? 'command-thumb' : 'command-icon-chip';
                        chip.textContent = item.symbol || '✦';
                        main.append(chip);
                    }

                    const text = document.createElement('div');
                    text.className = 'command-row-text';
                    const st = document.createElement('strong');
                    st.textContent = item.title;
                    const sm = document.createElement('small');
                    sm.textContent = item.subtitle || '';
                    text.append(st, sm);
                    main.append(text);
                    li.append(main);

                    const actions = document.createElement('div');
                    actions.className = 'command-inline-actions';
                    if (item.tmdbMovie) {
                        if (item.tmdbMovie.library) {
                            const saved = document.createElement('span');
                            saved.className = 'command-mini-btn is-saved';
                            saved.textContent = item.tmdbMovie.library.status === 'Watched' ? `✓ ${t('Watched')}` : `✓ ${t('In your library')}`;
                            actions.append(saved);
                        } else {
                            const btnWant = document.createElement('button');
                            btnWant.type = 'button';
                            btnWant.className = 'command-mini-btn';
                            btnWant.textContent = `+ ${t('Want to watch')}`;
                            btnWant.addEventListener('click', e => {
                                e.stopPropagation();
                                quickAddFromSpotlight(item.tmdbMovie.tmdb_id, false, btnWant);
                            });
                            const btnWatched = document.createElement('button');
                            btnWatched.type = 'button';
                            btnWatched.className = 'command-mini-btn';
                            btnWatched.textContent = `✓ ${t('Mark watched')}`;
                            btnWatched.addEventListener('click', e => {
                                e.stopPropagation();
                                quickAddFromSpotlight(item.tmdbMovie.tmdb_id, true, btnWatched);
                            });
                            actions.append(btnWant, btnWatched);
                        }
                    } else if (item.badge) {
                        const k = document.createElement('kbd');
                        k.textContent = item.badge;
                        actions.append(k);
                    }
                    li.append(actions);

                    const rowIdx = cmdRows.length;
                    li.addEventListener('pointermove', () => setActiveRow(rowIdx));
                    li.addEventListener('click', () => item.run());
                    cmdRows.push({el: li, run: item.run});
                    ul.append(li);
                }
                cmdBody.append(heading, ul);
            };

            if (q.length >= 2 && lastSearchCache.q === q) {
                addSection(
                    t('Your library'),
                    lastSearchCache.library.map(m => ({
                        isMedia: true,
                        image: m.poster_path,
                        symbol: '◈',
                        title: m.title,
                        subtitle: [m.year, m.status === 'Watched' ? t('Watched') : t('Want to watch'), m.rating ? `★ ${m.rating}/10` : ''].filter(Boolean).join(' · '),
                        badge: '↵',
                        run: () => location.assign(m.url)
                    }))
                );
                addSection(
                    t('Catalog · Movies, Filmmakers & Studios'),
                    lastSearchCache.catalog.map(c => c.kind === 'movie' ? ({
                        isMedia: true,
                        image: c.poster_url,
                        symbol: '◈',
                        title: c.title,
                        subtitle: [t('Movie'), c.year, c.score_percent !== null && c.score_percent !== undefined ? `TMDB ${c.score_percent}%` : ''].filter(Boolean).join(' · '),
                        tmdbMovie: c,
                        run: () => location.assign(c.url)
                    }) : ({
                        isMedia: true,
                        image: c.image,
                        symbol: '◎',
                        title: c.name,
                        subtitle: [c.role_label, c.subtitle].filter(Boolean).join(' · '),
                        badge: '→',
                        run: () => location.assign(c.url)
                    }))
                );
            }

            const commands = getStaticCommands().filter(c =>
                !qFold || c.title.toLowerCase().includes(qFold) || c.subtitle.toLowerCase().includes(qFold)
            );
            const quickGroup = commands.filter(c => c.group === t('Quick actions'));
            const navGroup = commands.filter(c => c.group === t('Navigate'));
            addSection(t('Quick actions'), quickGroup);
            addSection(t('Navigate'), navGroup);

            if (cmdRows.length) setActiveRow(0);
        }

        function scheduleCommandSearch() {
            clearTimeout(cmdTimer);
            cmdController?.abort();
            const q = (cmdInput?.value || '').trim();
            renderCommandPalette();
            if (q.length < 2) return;
            if (lastSearchCache.q === q) {
                renderCommandPalette();
                return;
            }
            cmdTimer = setTimeout(async () => {
                cmdController = new AbortController();
                try {
                    const res = await window.MovieListHTTP.fetch('/api/command-search?' + new URLSearchParams({q}), {
                        signal: cmdController.signal,
                        headers: {'Accept': 'application/json'}
                    });
                    if (!res.ok) return;
                    const data = await res.json();
                    lastSearchCache = {q, library: data.library || [], catalog: data.catalog || []};
                    renderCommandPalette();
                } catch (_) {}
            }, 200);
        }

        function openSpotlight() {
            if (!dialog.open) {
                renderCommandPalette();
                dialog.showModal();
            }
            cmdInput?.focus();
            cmdInput?.select();
        }

        document.querySelectorAll('[data-open-spotlight]').forEach(trigger => {
            trigger.addEventListener('click', event => {
                event.preventDefault();
                openSpotlight();
            });
        });

        document.getElementById('command-palette-close')?.addEventListener('click', () => dialog.close());
        dialog.addEventListener('click', event => {
            if (event.target === dialog) dialog.close();
        });

        cmdInput?.addEventListener('input', scheduleCommandSearch);
        cmdInput?.addEventListener('keydown', event => {
            if (event.key === 'ArrowDown') {
                event.preventDefault();
                setActiveRow(cmdIndex + 1);
            } else if (event.key === 'ArrowUp') {
                event.preventDefault();
                setActiveRow(cmdIndex - 1);
            } else if (event.key === 'Enter' && cmdRows[cmdIndex]) {
                event.preventDefault();
                cmdRows[cmdIndex].run();
            }
        });

        document.addEventListener('keydown', event => {
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
                event.preventDefault();
                if (dialog.open) dialog.close();
                else openSpotlight();
            }
        }, true);
    }

    // Expose a refresh hook so script.js AJAX library updates re-sync the sliding pill
    window.MovieListCinema = Object.freeze({
        refreshSlidingPill: updateSlidingPill
    });
})();
