/* On-device 1080x1350 Shareable Cinema Passport PNG generator.
 * Pure HTML5 Canvas: zero external images/fonts, zero CORS taint, strict CSP safe, zero private notes.
 */
(() => {
    'use strict';

    const statsEl = document.getElementById('cinema-stats-data');
    const canvas = document.getElementById('stats-card-canvas');
    const dialog = document.getElementById('stats-card-dialog');
    const openBtn = document.getElementById('open-stats-card');
    if (!statsEl || !canvas || !dialog || !openBtn) return;

    const {t} = window.MovieListI18n;
    const isTr = document.documentElement.lang === 'tr';
    const ownerEl = document.getElementById('cinema-card-owner');
    const closeBtn = document.getElementById('close-stats-card');
    const downloadBtn = document.getElementById('stats-card-download');
    const copyBtn = document.getElementById('stats-card-copy');
    const statusEl = document.getElementById('stats-card-status');

    let stats;
    let owner = {name: '', username: ''};
    try {
        stats = JSON.parse(statsEl.textContent || '{}');
    } catch {
        return;
    }
    try {
        if (ownerEl) owner = JSON.parse(ownerEl.textContent || '{}') || owner;
    } catch {
        /* ignore malformed owner metadata */
    }

    const canCopyImage = Boolean(
        navigator.clipboard &&
        typeof navigator.clipboard.write === 'function' &&
        typeof window.ClipboardItem === 'function'
    );
    if (copyBtn && !canCopyImage) {
        copyBtn.hidden = true;
    }

    const SANS = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
    const SERIF = 'Georgia, "Times New Roman", serif';

    function roundRect(ctx, x, y, w, h, r) {
        const radius = Math.max(0, Math.min(r, w / 2, h / 2));
        ctx.beginPath();
        ctx.moveTo(x + radius, y);
        ctx.arcTo(x + w, y, x + w, y + h, radius);
        ctx.arcTo(x + w, y + h, x, y + h, radius);
        ctx.arcTo(x, y + h, x, y, radius);
        ctx.arcTo(x, y, x + w, y, radius);
        ctx.closePath();
    }

    function fitText(ctx, text, maxWidth) {
        const str = String(text || '');
        if (!str || ctx.measureText(str).width <= maxWidth) return str;
        let low = 0;
        let high = str.length;
        while (low < high) {
            const mid = Math.ceil((low + high) / 2);
            if (ctx.measureText(str.slice(0, mid) + '…').width <= maxWidth) {
                low = mid;
            } else {
                high = mid - 1;
            }
        }
        return str.slice(0, Math.max(1, low)) + '…';
    }

    function drawCornerMarks(ctx, x, y, w, h) {
        const len = 18;
        ctx.save();
        ctx.strokeStyle = 'rgba(229, 199, 135, 0.48)';
        ctx.lineWidth = 2;
        const corners = [
            [x, y + len, x, y, x + len, y],
            [x + w - len, y, x + w, y, x + w, y + len],
            [x, y + h - len, x, y + h, x + len, y + h],
            [x + w - len, y + h, x + w, y + h, x + w, y + h - len]
        ];
        for (const [x1, y1, cx, cy, x2, y2] of corners) {
            ctx.beginPath();
            ctx.moveTo(x1, y1);
            ctx.lineTo(cx, cy);
            ctx.lineTo(x2, y2);
            ctx.stroke();
        }
        ctx.restore();
    }

    function renderCinemaPassport() {
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const W = 1080;
        const H = 1350;
        const totals = stats.totals || {};
        const overview = stats.overview || {};
        const year = stats.year || new Date().getFullYear();

        ctx.clearRect(0, 0, W, H);

        // 1. Deep obsidian velvet gradient backdrop
        const bgGrad = ctx.createLinearGradient(0, 0, 0, H);
        bgGrad.addColorStop(0, '#0b0c12');
        bgGrad.addColorStop(0.5, '#141522');
        bgGrad.addColorStop(1, '#090a10');
        ctx.fillStyle = bgGrad;
        ctx.fillRect(0, 0, W, H);

        // Soft top lavender projector beam radial glow
        const topGlow = ctx.createRadialGradient(W * 0.52, -40, 20, W * 0.52, 120, 620);
        topGlow.addColorStop(0, 'rgba(196, 177, 255, 0.20)');
        topGlow.addColorStop(0.55, 'rgba(196, 177, 255, 0.06)');
        topGlow.addColorStop(1, 'rgba(196, 177, 255, 0)');
        ctx.fillStyle = topGlow;
        ctx.fillRect(0, 0, W, H);

        // Subtle warm tungsten gold side glow
        const goldGlow = ctx.createRadialGradient(W * 0.92, H * 0.24, 10, W * 0.92, H * 0.24, 520);
        goldGlow.addColorStop(0, 'rgba(229, 199, 135, 0.14)');
        goldGlow.addColorStop(0.6, 'rgba(229, 199, 135, 0.04)');
        goldGlow.addColorStop(1, 'rgba(229, 199, 135, 0)');
        ctx.fillStyle = goldGlow;
        ctx.fillRect(0, 0, W, H);

        // Subtle screen dot matrix texture
        ctx.fillStyle = 'rgba(255, 255, 255, 0.025)';
        for (let py = 64; py < H - 64; py += 28) {
            for (let px = 64; px < W - 64; px += 28) {
                ctx.fillRect(px, py, 1.5, 1.5);
            }
        }

        // Double hairline cinema frame + corner registration marks
        roundRect(ctx, 32, 32, W - 64, H - 64, 28);
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.11)';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        roundRect(ctx, 44, 44, W - 88, H - 88, 22);
        ctx.strokeStyle = 'rgba(196, 177, 255, 0.18)';
        ctx.lineWidth = 1;
        ctx.stroke();

        drawCornerMarks(ctx, 56, 56, W - 112, H - 112);

        // 2. Top Header: Eyebrow + Georgia Serif Headline + Owner Identity Pill
        const padX = 82;
        ctx.textAlign = 'left';
        ctx.textBaseline = 'alphabetic';

        ctx.font = `700 18px ${SANS}`;
        ctx.fillStyle = '#c4b1ff';
        const eyebrow = t('MYMOVIELIST · CINEMA PASSPORT · {year}', {year});
        ctx.fillText(eyebrow, padX, 106);

        ctx.font = `400 54px ${SERIF}`;
        ctx.fillStyle = '#f4f2fa';
        const headline = t('My Cinema Profile.');
        ctx.fillText(headline, padX, 166);

        // Editorial taste subtitle under headline
        let tasteLine = t('Your personal archive is taking shape');
        if (overview.top_genre_name) {
            const gLabel = overview.top_genre_known ? t(overview.top_genre_name) : overview.top_genre_name;
            tasteLine = t('Drawn to {genre}', {genre: gLabel});
        }
        ctx.font = `500 22px ${SANS}`;
        ctx.fillStyle = '#b4aec6';
        ctx.fillText(fitText(ctx, tasteLine, 560), padX, 204);

        // Optional Owner Badge on top-right
        const rawName = typeof owner.name === 'string' ? owner.name.trim() : '';
        const rawHandle = typeof owner.username === 'string'
            ? owner.username.trim()
            : (owner.username && typeof owner.username.username === 'string' ? owner.username.username.trim() : '');
        if (rawName || rawHandle) {
            const primaryIdentity = rawName || ('@' + rawHandle);
            const secondaryIdentity = (rawName && rawHandle) ? ('@' + rawHandle) : t('A film lover');
            const pillW = 280;
            const pillH = 74;
            const pillX = W - padX - pillW;
            const pillY = 92;

            roundRect(ctx, pillX, pillY, pillW, pillH, 16);
            ctx.fillStyle = 'rgba(26, 27, 39, 0.88)';
            ctx.fill();
            ctx.strokeStyle = 'rgba(196, 177, 255, 0.26)';
            ctx.lineWidth = 1.2;
            ctx.stroke();

            ctx.textAlign = 'right';
            ctx.font = `650 22px ${SANS}`;
            ctx.fillStyle = '#f4f2fa';
            ctx.fillText(fitText(ctx, primaryIdentity, pillW - 36), pillX + pillW - 20, pillY + 32);

            ctx.font = `500 17px ${SANS}`;
            ctx.fillStyle = '#e5c787';
            ctx.fillText(fitText(ctx, secondaryIdentity, pillW - 36), pillX + pillW - 20, pillY + 56);
            ctx.textAlign = 'left';
        }

        // 3. Hero Section: Completion Donut Ring (left) + 4 KPI Tiles (right)
        const heroY = 236;
        const heroH = 232;
        const donutCardW = 240;

        // Left Donut Card
        roundRect(ctx, padX, heroY, donutCardW, heroH, 20);
        const donutBg = ctx.createLinearGradient(padX, heroY, padX + donutCardW, heroY + heroH);
        donutBg.addColorStop(0, 'rgba(30, 31, 46, 0.92)');
        donutBg.addColorStop(1, 'rgba(20, 21, 32, 0.92)');
        ctx.fillStyle = donutBg;
        ctx.fill();
        ctx.strokeStyle = 'rgba(196, 177, 255, 0.24)';
        ctx.lineWidth = 1.2;
        ctx.stroke();

        const cx = padX + donutCardW / 2;
        const cy = heroY + heroH / 2;
        const radius = 74;
        const pct = Math.max(0, Math.min(100, Number(overview.completion_pct) || 0));

        ctx.beginPath();
        ctx.arc(cx, cy, radius, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.09)';
        ctx.lineWidth = 14;
        ctx.stroke();

        if (pct > 0) {
            const startAngle = -Math.PI / 2;
            const endAngle = startAngle + (Math.PI * 2 * pct) / 100;
            const arcGrad = ctx.createLinearGradient(cx - radius, cy - radius, cx + radius, cy + radius);
            arcGrad.addColorStop(0, '#c4b1ff');
            arcGrad.addColorStop(1, '#e5c787');
            ctx.beginPath();
            ctx.arc(cx, cy, radius, startAngle, endAngle);
            ctx.strokeStyle = arcGrad;
            ctx.lineWidth = 14;
            ctx.lineCap = 'round';
            ctx.stroke();
        }

        ctx.textAlign = 'center';
        ctx.font = `700 36px ${SANS}`;
        ctx.fillStyle = '#f4f2fa';
        ctx.fillText(`${pct}%`, cx, cy + 4);

        ctx.font = `600 16px ${SANS}`;
        ctx.fillStyle = '#a9a3bc';
        ctx.fillText(t('Watched'), cx, cy + 28);
        ctx.textAlign = 'left';

        // Right 2x2 KPI Grid
        const gridX = padX + donutCardW + 20;
        const gridW = W - padX - gridX;
        const gap = 16;
        const tileW = (gridW - gap) / 2;
        const tileH = (heroH - gap) / 2;

        const totalMinutes = Number(totals.total_minutes) || 0;
        const totalHours = Number(totals.total_hours) || 0;
        const runtimeCount = Number(totals.runtime_count) || 0;
        const watchTimeValue = totalMinutes > 0
            ? t('{hours}h {minutes}m', {hours: totalHours, minutes: totalMinutes % 60})
            : '0h';
        const watchTimeSub = runtimeCount > 0
            ? (Number(overview.total_days) >= 1
                ? t('{days} days · {count} films', {days: overview.total_days, count: runtimeCount})
                : t('{minutes} min across {count} films', {minutes: totalMinutes, count: runtimeCount}))
            : t('Watched');

        const hasAvg = totals.avg_rating !== null && totals.avg_rating !== undefined;
        const avgValue = hasAvg ? `★ ${totals.avg_rating}` : '—';
        const avgSub = overview.median_rating !== null && overview.median_rating !== undefined
            ? t('{count} rated · median {median}', {count: totals.rated || 0, median: overview.median_rating})
            : t('{count} rated', {count: totals.rated || 0});

        const kpis = [
            {
                label: t('Watched'),
                value: String(totals.watched || 0),
                sub: t('{count} in library', {count: totals.total || 0}),
                accent: '#c4b1ff',
                border: 'rgba(255, 255, 255, 0.10)',
                bg0: 'rgba(29, 30, 44, 0.9)',
                bg1: 'rgba(21, 22, 32, 0.9)'
            },
            {
                label: t('Watch time'),
                value: watchTimeValue,
                sub: watchTimeSub,
                accent: '#c4b1ff',
                border: 'rgba(255, 255, 255, 0.10)',
                bg0: 'rgba(29, 30, 44, 0.9)',
                bg1: 'rgba(21, 22, 32, 0.9)'
            },
            {
                label: t('Average rating'),
                value: avgValue,
                sub: avgSub,
                accent: '#e5c787',
                border: 'rgba(229, 199, 135, 0.28)',
                bg0: 'rgba(38, 33, 40, 0.92)',
                bg1: 'rgba(23, 22, 31, 0.92)'
            },
            {
                label: t('Favorites'),
                value: `♥ ${totals.favorites || 0}`,
                sub: t('{count} want to watch', {count: totals.watchlist || 0}),
                accent: '#ff8aa4',
                border: 'rgba(255, 122, 150, 0.28)',
                bg0: 'rgba(40, 25, 36, 0.92)',
                bg1: 'rgba(23, 21, 31, 0.92)'
            }
        ];

        kpis.forEach((tile, idx) => {
            const col = idx % 2;
            const row = Math.floor(idx / 2);
            const tx = gridX + col * (tileW + gap);
            const ty = heroY + row * (tileH + gap);

            roundRect(ctx, tx, ty, tileW, tileH, 16);
            const tGrad = ctx.createLinearGradient(tx, ty, tx + tileW, ty + tileH);
            tGrad.addColorStop(0, tile.bg0);
            tGrad.addColorStop(1, tile.bg1);
            ctx.fillStyle = tGrad;
            ctx.fill();
            ctx.strokeStyle = tile.border;
            ctx.lineWidth = 1.2;
            ctx.stroke();

            ctx.font = `600 16px ${SANS}`;
            ctx.fillStyle = '#a8a2bc';
            ctx.fillText(fitText(ctx, tile.label, tileW - 36), tx + 20, ty + 28);

            ctx.font = `700 32px ${SANS}`;
            ctx.fillStyle = tile.accent === '#c4b1ff' ? '#f4f2fa' : tile.accent;
            ctx.fillText(fitText(ctx, tile.value, tileW - 36), tx + 20, ty + 66);

            ctx.font = `500 15px ${SANS}`;
            ctx.fillStyle = '#8e88a4';
            ctx.fillText(fitText(ctx, tile.sub, tileW - 36), tx + 20, ty + 92);
        });

        // 4. Editorial Insight Pill Row (up to 4 pills)
        const pills = [];
        if (overview.critic_delta !== null && overview.critic_delta !== undefined) {
            const delta = Number(overview.critic_delta);
            const label = delta > 0
                ? t('+{delta} above TMDB avg', {delta})
                : (delta < 0
                    ? t('{delta} below TMDB avg', {delta})
                    : t('Matches TMDB avg ({avg})', {avg: overview.tmdb_avg}));
            pills.push({text: label, gold: true});
        }
        if (overview.top_decade) {
            const era = isTr ? (overview.top_decade_tr || overview.top_decade) : overview.top_decade;
            pills.push({text: t('Peak era: {era}', {era}), gold: false});
        }
        if (Number(overview.longest_streak) > 1) {
            pills.push({text: t('Best streak: {days} days', {days: overview.longest_streak}), gold: false});
        }
        if (Number(overview.ten_count) > 0) {
            pills.push({text: t('{count} masterpieces (10/10)', {count: overview.ten_count}), gold: true});
        }
        if (pills.length < 4 && Number(overview.avg_runtime) > 0) {
            pills.push({text: t('Avg runtime: {min} min', {min: overview.avg_runtime}), gold: false});
        }
        if (pills.length < 4) {
            pills.push({
                text: t('Watched in {year}: {count}', {year, count: totals.watched_this_year || 0}),
                gold: false
            });
        }

        const pillY = 486;
        const pillH = 40;
        let curPillX = padX;
        ctx.font = `600 16px ${SANS}`;
        for (const pill of pills.slice(0, 4)) {
            const textW = ctx.measureText(pill.text).width;
            const pw = Math.min(textW + 32, 280);
            if (curPillX + pw > W - padX) break;

            roundRect(ctx, curPillX, pillY, pw, pillH, 20);
            ctx.fillStyle = pill.gold ? 'rgba(229, 199, 135, 0.12)' : 'rgba(255, 255, 255, 0.05)';
            ctx.fill();
            ctx.strokeStyle = pill.gold ? 'rgba(229, 199, 135, 0.36)' : 'rgba(255, 255, 255, 0.13)';
            ctx.lineWidth = 1;
            ctx.stroke();

            ctx.fillStyle = pill.gold ? '#e5c787' : '#d8d3e8';
            ctx.fillText(fitText(ctx, pill.text, pw - 24), curPillX + 16, pillY + 26);
            curPillX += pw + 12;
        }

        // 5. Painted 1–10 Rating Distribution Curve
        const histY = 546;
        const histH = 216;
        const contentW = W - padX * 2;

        roundRect(ctx, padX, histY, contentW, histH, 20);
        ctx.fillStyle = 'rgba(23, 24, 36, 0.88)';
        ctx.fill();
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.10)';
        ctx.lineWidth = 1.2;
        ctx.stroke();

        ctx.font = `700 16px ${SANS}`;
        ctx.fillStyle = '#c4b1ff';
        ctx.fillText(t('RATING DISTRIBUTION (1–10)'), padX + 26, histY + 34);

        const histBadge = hasAvg
            ? t('★ {avg} average · {count} rated', {avg: totals.avg_rating, count: totals.rated || 0})
            : t('No ratings yet');
        ctx.textAlign = 'right';
        ctx.font = `600 16px ${SANS}`;
        ctx.fillStyle = '#e5c787';
        ctx.fillText(histBadge, padX + contentW - 26, histY + 34);
        ctx.textAlign = 'left';

        const dist = Array.isArray(stats.rating_distribution) && stats.rating_distribution.length === 10
            ? stats.rating_distribution
            : Array.from({length: 10}, (_, i) => ({rating: i + 1, count: 0, bar_height: 0}));

        const chartLeft = padX + 34;
        const chartRight = padX + contentW - 34;
        const chartW = chartRight - chartLeft;
        const colStep = chartW / 10;
        const barW = 42;
        const barTop = histY + 68;
        const barMaxH = 102;

        dist.forEach((bin, i) => {
            const rating = bin.rating || (i + 1);
            const count = Number(bin.count) || 0;
            const pctH = Math.max(0, Math.min(100, Number(bin.bar_height) || 0));
            const bx = chartLeft + i * colStep + (colStep - barW) / 2;

            // Track
            roundRect(ctx, bx, barTop, barW, barMaxH, 8);
            ctx.fillStyle = 'rgba(255, 255, 255, 0.05)';
            ctx.fill();

            // Fill bar
            if (count > 0 && pctH > 0) {
                const bh = Math.max(10, Math.round((pctH * barMaxH) / 100));
                const by = barTop + barMaxH - bh;
                roundRect(ctx, bx, by, barW, bh, 8);
                ctx.fillStyle = rating >= 8 ? '#e5c787' : '#c4b1ff';
                ctx.fill();

                ctx.textAlign = 'center';
                ctx.font = `700 15px ${SANS}`;
                ctx.fillStyle = rating >= 8 ? '#e5c787' : '#d8d3e8';
                ctx.fillText(String(count), bx + barW / 2, by - 7);
            }

            // Axis label 1..10
            ctx.textAlign = 'center';
            ctx.font = `600 15px ${SANS}`;
            ctx.fillStyle = rating >= 8 ? '#e5c787' : '#9690ab';
            ctx.fillText(`★ ${rating}`, bx + barW / 2, barTop + barMaxH + 26);
        });
        ctx.textAlign = 'left';

        // 6. Two-Column Lower Editorial Showcase
        const lowerY = 782;
        const lowerH = 434;
        const colGap = 20;
        const colW = (contentW - colGap) / 2;

        // Left Column: Top Genres (top 4) + Most Watched Director
        roundRect(ctx, padX, lowerY, colW, lowerH, 20);
        ctx.fillStyle = 'rgba(23, 24, 36, 0.88)';
        ctx.fill();
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.10)';
        ctx.lineWidth = 1.2;
        ctx.stroke();

        ctx.font = `700 16px ${SANS}`;
        ctx.fillStyle = '#c4b1ff';
        ctx.fillText(t('TOP GENRES'), padX + 24, lowerY + 34);

        const topGenres = Array.isArray(stats.top_genres) ? stats.top_genres.slice(0, 4) : [];
        if (topGenres.length > 0) {
            topGenres.forEach((genre, idx) => {
                const gy = lowerY + 68 + idx * 62;
                const gName = genre.known ? t(genre.name) : genre.name;
                const countLabel = t(genre.count === 1 ? '{count} film' : '{count} films', {count: genre.count});
                const metaLabel = genre.avg_rating !== null && genre.avg_rating !== undefined
                    ? `${countLabel} · ★ ${genre.avg_rating}`
                    : countLabel;

                ctx.font = `600 18px ${SANS}`;
                ctx.fillStyle = '#f4f2fa';
                ctx.fillText(fitText(ctx, gName, colW - 190), padX + 24, gy);

                ctx.textAlign = 'right';
                ctx.font = `500 15px ${SANS}`;
                ctx.fillStyle = '#a8a2bc';
                ctx.fillText(metaLabel, padX + colW - 24, gy);
                ctx.textAlign = 'left';

                // Progress bar
                const barX = padX + 24;
                const barY = gy + 12;
                const fullW = colW - 48;
                roundRect(ctx, barX, barY, fullW, 10, 5);
                ctx.fillStyle = 'rgba(255, 255, 255, 0.06)';
                ctx.fill();

                const fillW = Math.max(12, Math.round((Math.min(100, Number(genre.bar_width) || 0) * fullW) / 100));
                const gGrad = ctx.createLinearGradient(barX, barY, barX + fillW, barY);
                gGrad.addColorStop(0, '#c4b1ff');
                gGrad.addColorStop(1, '#e5c787');
                roundRect(ctx, barX, barY, fillW, 10, 5);
                ctx.fillStyle = gGrad;
                ctx.fill();
            });
        } else {
            ctx.font = `500 17px ${SANS}`;
            ctx.fillStyle = '#8e88a4';
            ctx.fillText(fitText(ctx, t('Genres will appear as you add films.'), colW - 48), padX + 24, lowerY + 120);
        }

        // Most Watched Director sub-box at bottom of Left Column
        const directors = Array.isArray(stats.top_directors) ? stats.top_directors : [];
        const subBoxY = lowerY + lowerH - 114;
        const subBoxH = 92;
        roundRect(ctx, padX + 20, subBoxY, colW - 40, subBoxH, 14);
        ctx.fillStyle = 'rgba(17, 18, 27, 0.85)';
        ctx.fill();
        ctx.strokeStyle = 'rgba(196, 177, 255, 0.20)';
        ctx.lineWidth = 1;
        ctx.stroke();

        ctx.font = `700 14px ${SANS}`;
        ctx.fillStyle = '#c4b1ff';
        ctx.fillText(t('MOST WATCHED DIRECTOR'), padX + 36, subBoxY + 28);

        if (directors.length > 0) {
            const dir = directors[0];
            ctx.font = `650 21px ${SANS}`;
            ctx.fillStyle = '#f4f2fa';
            ctx.fillText(fitText(ctx, dir.name, colW - 190), padX + 36, subBoxY + 58);

            const dirMeta = dir.avg_rating !== null && dir.avg_rating !== undefined
                ? `${t('{count} watched', {count: dir.count})} · ★ ${dir.avg_rating}`
                : t('{count} watched', {count: dir.count});
            ctx.font = `500 15px ${SANS}`;
            ctx.fillStyle = '#e5c787';
            ctx.fillText(dirMeta, padX + 36, subBoxY + 80);
        } else {
            ctx.font = `500 17px ${SANS}`;
            ctx.fillStyle = '#8e88a4';
            ctx.fillText('—', padX + 36, subBoxY + 60);
        }

        // Right Column: Highest Rated Picks (top 3) + Archive Milestone
        const rightX = padX + colW + colGap;
        roundRect(ctx, rightX, lowerY, colW, lowerH, 20);
        ctx.fillStyle = 'rgba(23, 24, 36, 0.88)';
        ctx.fill();
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.10)';
        ctx.lineWidth = 1.2;
        ctx.stroke();

        ctx.font = `700 16px ${SANS}`;
        ctx.fillStyle = '#e5c787';
        ctx.fillText(t('HIGHEST RATED PICKS'), rightX + 24, lowerY + 34);

        const topFilms = Array.isArray(stats.highest_rated) ? stats.highest_rated.slice(0, 3) : [];
        if (topFilms.length > 0) {
            topFilms.forEach((film, idx) => {
                const fy = lowerY + 54 + idx * 80;
                roundRect(ctx, rightX + 20, fy, colW - 40, 68, 13);
                ctx.fillStyle = 'rgba(255, 255, 255, 0.035)';
                ctx.fill();
                ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
                ctx.lineWidth = 1;
                ctx.stroke();

                // Rank badge
                ctx.font = `700 15px ${SANS}`;
                ctx.fillStyle = '#c4b1ff';
                ctx.fillText(`0${idx + 1}`, rightX + 36, fy + 30);

                // Film title & year
                const titleMaxW = colW - 196;
                ctx.font = `650 19px ${SANS}`;
                ctx.fillStyle = '#f4f2fa';
                ctx.fillText(fitText(ctx, film.title, titleMaxW), rightX + 70, fy + 29);

                const yearStr = film.year ? String(film.year) : '';
                const favStr = film.favorite ? ' · ♥' : '';
                ctx.font = `500 15px ${SANS}`;
                ctx.fillStyle = film.favorite ? '#ff8aa4' : '#9690ab';
                ctx.fillText(`${yearStr}${favStr}`, rightX + 70, fy + 52);

                // Gold rating pill on right
                if (film.rating) {
                    const rText = `★ ${film.rating}/10`;
                    ctx.font = `700 16px ${SANS}`;
                    const rw = ctx.measureText(rText).width + 24;
                    const rx = rightX + colW - 36 - rw;
                    const ry = fy + 16;
                    roundRect(ctx, rx, ry, rw, 36, 10);
                    ctx.fillStyle = 'rgba(229, 199, 135, 0.14)';
                    ctx.fill();
                    ctx.strokeStyle = 'rgba(229, 199, 135, 0.38)';
                    ctx.stroke();

                    ctx.fillStyle = '#e5c787';
                    ctx.fillText(rText, rx + 12, ry + 24);
                }
            });
        } else {
            ctx.font = `500 17px ${SANS}`;
            ctx.fillStyle = '#8e88a4';
            ctx.fillText(
                fitText(ctx, t('Rate watched films to highlight your top picks.'), colW - 48),
                rightX + 24,
                lowerY + 120
            );
        }

        // Archive Record sub-box at bottom of Right Column
        const records = stats.records || {};
        const milestone = records.longest
            ? {
                kind: t('Longest watched'),
                title: records.longest.title,
                detail: `${records.longest.runtime} ${t('min')}`
            }
            : (records.oldest
                ? {
                    kind: t('Oldest film'),
                    title: records.oldest.title,
                    detail: String(records.oldest.year || '')
                }
                : null);

        roundRect(ctx, rightX + 20, subBoxY, colW - 40, subBoxH, 14);
        ctx.fillStyle = 'rgba(17, 18, 27, 0.85)';
        ctx.fill();
        ctx.strokeStyle = 'rgba(229, 199, 135, 0.24)';
        ctx.lineWidth = 1;
        ctx.stroke();

        ctx.font = `700 14px ${SANS}`;
        ctx.fillStyle = '#e5c787';
        ctx.fillText(
            milestone ? `${t('ARCHIVE MILESTONE')} · ${milestone.kind.toUpperCase()}` : t('ARCHIVE MILESTONE'),
            rightX + 36,
            subBoxY + 28
        );

        if (milestone) {
            ctx.font = `650 21px ${SANS}`;
            ctx.fillStyle = '#f4f2fa';
            ctx.fillText(fitText(ctx, milestone.title, colW - 160), rightX + 36, subBoxY + 58);

            ctx.font = `500 15px ${SANS}`;
            ctx.fillStyle = '#c4b1ff';
            ctx.fillText(milestone.detail, rightX + 36, subBoxY + 80);
        } else {
            ctx.font = `500 17px ${SANS}`;
            ctx.fillStyle = '#8e88a4';
            ctx.fillText('—', rightX + 36, subBoxY + 60);
        }

        // 7. Bottom Cinema Ticket Stub (Perforated line + side notches + signature)
        const stubY = 1244;

        // Left & right ticket punch cutouts along the inner frame edge
        ctx.save();
        ctx.fillStyle = '#090a10';
        ctx.strokeStyle = 'rgba(196, 177, 255, 0.24)';
        ctx.lineWidth = 1.2;

        ctx.beginPath();
        ctx.arc(44, stubY, 14, -Math.PI / 2, Math.PI / 2);
        ctx.fill();
        ctx.stroke();

        ctx.beginPath();
        ctx.arc(W - 44, stubY, 14, Math.PI / 2, -Math.PI / 2);
        ctx.fill();
        ctx.stroke();

        // Dashed perforation line
        ctx.beginPath();
        ctx.setLineDash([8, 8]);
        ctx.moveTo(74, stubY);
        ctx.lineTo(W - 74, stubY);
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.16)';
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.restore();

        // Left footer copy
        ctx.font = `700 14px ${SANS}`;
        ctx.fillStyle = '#c4b1ff';
        ctx.fillText(t('PRIVATE SCREENING PASSPORT'), padX, 1276);

        ctx.font = `500 16px ${SANS}`;
        ctx.fillStyle = '#8e88a4';
        ctx.fillText(t('Private notes stay private'), padX, 1298);

        // Right footer signature: myshelf.cloud
        ctx.textAlign = 'right';
        ctx.font = `700 24px ${SERIF}`;
        ctx.fillStyle = '#e5c787';
        ctx.fillText('myshelf.cloud', W - padX, 1290);
        ctx.textAlign = 'left';
    }

    function setStatus(msg) {
        if (!statusEl) return;
        statusEl.textContent = msg;
        statusEl.hidden = !msg;
    }

    function canvasToBlob() {
        return new Promise(resolve => {
            if (typeof canvas.toBlob === 'function') {
                canvas.toBlob(blob => resolve(blob), 'image/png');
            } else {
                resolve(null);
            }
        });
    }

    openBtn.addEventListener('click', () => {
        renderCinemaPassport();
        setStatus('');
        if (typeof dialog.showModal === 'function') {
            dialog.showModal();
        } else {
            dialog.setAttribute('open', '');
        }
    });

    closeBtn?.addEventListener('click', () => {
        if (typeof dialog.close === 'function') {
            dialog.close();
        } else {
            dialog.removeAttribute('open');
        }
    });

    dialog.addEventListener('click', event => {
        if (event.target === dialog) {
            if (typeof dialog.close === 'function') {
                dialog.close();
            } else {
                dialog.removeAttribute('open');
            }
        }
    });

    downloadBtn?.addEventListener('click', async () => {
        renderCinemaPassport();
        const year = stats.year || new Date().getFullYear();
        const filename = `MyMovieList-Cinema-Passport-${year}.png`;
        const blob = await canvasToBlob();
        const link = document.createElement('a');
        link.download = filename;
        if (blob) {
            const url = URL.createObjectURL(blob);
            link.href = url;
            document.body.append(link);
            link.click();
            link.remove();
            setTimeout(() => URL.revokeObjectURL(url), 5000);
        } else {
            link.href = canvas.toDataURL('image/png');
            document.body.append(link);
            link.click();
            link.remove();
        }
        setStatus(t('Cinema card downloaded.'));
    });

    copyBtn?.addEventListener('click', async () => {
        if (!canCopyImage) return;
        renderCinemaPassport();
        try {
            const blob = await canvasToBlob();
            if (!blob) throw new Error('Blob unavailable');
            await navigator.clipboard.write([new window.ClipboardItem({'image/png': blob})]);
            setStatus(t('Cinema card copied to clipboard.'));
        } catch {
            setStatus(t('Could not copy image. Use Download PNG instead.'));
        }
    });

    renderCinemaPassport();

    /* Interactive Stats Drilldown Modal & Live Heatmap Preview (CSP-safe, zero innerHTML/inline styles) */
    const drilldownEl = document.getElementById('cinema-stats-drilldown');
    const drillDialog = document.getElementById('stats-drilldown-dialog');
    const drillTitle = document.getElementById('stats-drilldown-title');
    const drillSub = document.getElementById('stats-drilldown-subtitle');
    const drillGrid = document.getElementById('stats-drilldown-grid');
    const drillClose = document.getElementById('close-stats-drilldown');
    const heatmapPreview = document.getElementById('heatmap-live-preview');

    let drilldown = null;
    if (drilldownEl) {
        try {
            drilldown = JSON.parse(drilldownEl.textContent || '{}');
        } catch {
            drilldown = null;
        }
    }

    function openDrilldown(group, key, heading) {
        if (!drilldown || !drillDialog || !drillGrid) return;
        const bucket = drilldown[group];
        const films = (bucket && Array.isArray(bucket[key])) ? bucket[key] : [];
        if (drillTitle) drillTitle.textContent = heading || String(key || '');
        if (drillSub) {
            drillSub.textContent = films.length === 1
                ? t('{count} film', {count: 1})
                : t('{count} films', {count: films.length});
        }
        drillGrid.replaceChildren();
        if (!films.length) {
            const empty = document.createElement('p');
            empty.className = 'stats-empty-note';
            empty.textContent = t('No films recorded for this selection.');
            drillGrid.append(empty);
        } else {
            const frag = document.createDocumentFragment();
            for (const film of films) {
                const card = document.createElement('a');
                card.className = 'drilldown-film-card';
                card.href = `/movie/${encodeURIComponent(film.id)}?back=/stats`;

                const posterWrap = document.createElement('div');
                posterWrap.className = 'drilldown-film-poster';
                if (film.poster_path) {
                    const img = document.createElement('img');
                    img.src = film.poster_path;
                    img.alt = t('Poster for {title}', {title: film.title || ''});
                    img.loading = 'lazy';
                    img.decoding = 'async';
                    posterWrap.append(img);
                } else {
                    const ph = document.createElement('span');
                    ph.className = 'poster-placeholder';
                    ph.textContent = '◈';
                    posterWrap.append(ph);
                }

                if (film.favorite) {
                    const heart = document.createElement('span');
                    heart.className = 'stats-film-heart';
                    heart.setAttribute('aria-hidden', 'true');
                    heart.textContent = '♥';
                    posterWrap.append(heart);
                }
                if (film.rating !== null && film.rating !== undefined) {
                    const badge = document.createElement('span');
                    badge.className = 'profile-film-rating';
                    badge.textContent = `★ ${film.rating}/10`;
                    posterWrap.append(badge);
                }

                const titleEl = document.createElement('h3');
                titleEl.textContent = film.title || '';

                const metaEl = document.createElement('p');
                const metaParts = [];
                if (film.year) metaParts.push(String(film.year));
                if (film.runtime) metaParts.push(`${film.runtime} ${t('min')}`);
                if (group === 'by_date' || group === 'by_month' || group === 'by_weekday') {
                    if (film.watched_date) metaParts.push(film.watched_date);
                }
                metaEl.textContent = metaParts.join(' · ') || t('Year unknown');

                card.append(posterWrap, titleEl, metaEl);
                frag.append(card);
            }
            drillGrid.append(frag);
        }

        if (typeof drillDialog.showModal === 'function') {
            drillDialog.showModal();
        } else {
            drillDialog.setAttribute('open', '');
        }
    }

    function closeDrilldown() {
        if (!drillDialog) return;
        if (typeof drillDialog.close === 'function') {
            drillDialog.close();
        } else {
            drillDialog.removeAttribute('open');
        }
    }

    drillClose?.addEventListener('click', closeDrilldown);
    drillDialog?.addEventListener('click', event => {
        if (event.target === drillDialog) closeDrilldown();
    });

    if (drilldown) {
        const triggerDrill = target => {
            const node = target.closest?.('[data-drill-group][data-drill-key]');
            if (!node) return false;
            const group = node.getAttribute('data-drill-group');
            const key = node.getAttribute('data-drill-key');
            const title = node.getAttribute('data-drill-title') || key;
            if (group && key !== null) {
                openDrilldown(group, key, title);
                return true;
            }
            return false;
        };

        document.addEventListener('click', event => {
            const node = event.target?.closest?.('[data-drill-group][data-drill-key]');
            if (node && triggerDrill(node)) {
                node.blur?.();
            }
        });

        document.addEventListener('keydown', event => {
            if (event.key !== 'Enter' && event.key !== ' ') return;
            const node = event.target?.closest?.('[data-drill-group][data-drill-key]');
            if (!node || node.tagName === 'BUTTON' || node.tagName === 'A') return;
            event.preventDefault();
            triggerDrill(node);
        });

        if (heatmapPreview) {
            const previewText = heatmapPreview.querySelector('.heatmap-preview-text');
            const defaultPrompt = previewText ? previewText.textContent : '';
            const showPreview = cell => {
                if (!previewText) return;
                const d = cell.getAttribute('data-drill-key') || '';
                const titles = cell.getAttribute('data-heatmap-titles') || '';
                previewText.textContent = titles ? `${d} · ${titles}` : d;
                heatmapPreview.classList.add('is-active');
            };
            const resetPreview = () => {
                if (!previewText) return;
                previewText.textContent = defaultPrompt;
                heatmapPreview.classList.remove('is-active');
            };
            document.querySelectorAll('.heatmap-cell[data-drill-key]').forEach(cell => {
                cell.addEventListener('mouseenter', () => showPreview(cell));
                cell.addEventListener('focus', () => showPreview(cell));
                cell.addEventListener('mouseleave', resetPreview);
                cell.addEventListener('blur', resetPreview);
            });
        }
    }
})();
