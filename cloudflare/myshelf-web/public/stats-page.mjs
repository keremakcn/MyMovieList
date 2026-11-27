// CSP-safe pure SVG Personal Cinema Statistics Scrollytelling page for MyShelf Web.
import {computeCinemaStats} from './stats-model.mjs';
import {libraryMetadataKeys} from './library-model.mjs';
import {formatDecadeLabel,openStatsCardDialog} from './stats-card.mjs';
import {NOIR_SILHOUETTE_SVG} from './cinema-ux.mjs';

function formatWatchTime(totalMinutes,t){
  if(!totalMinutes || totalMinutes<=0)return '—';
  const hours=Math.floor(totalMinutes/60),mins=totalMinutes%60;
  if(hours>=48){
    const days=(hours/24).toFixed(1).replace(/\.0$/,'');
    return `${hours.toLocaleString()} ${t('statsHours')} · ${days} ${t('statsDays')}`;
  }
  return mins ? `${hours} ${t('statsHours')} ${mins} ${t('statsMinutesShort')}` : `${hours} ${t('statsHours')}`;
}

function renderVerticalSvg(items,{labelKey,ariaLabel,barClass='svg-bar-accent',highlightFn=null,emptyText}){
  const hasAny=items.some(x=>x.count>0);
  if(!hasAny)return `<p class="stats-empty-note">${emptyText}</p>`;
  const count=items.length;
  const colW=36,gap=8,padX=10,padTop=22,chartH=112,padBottom=24;
  const width=padX*2+count*colW+(count-1)*gap;
  const height=padTop+chartH+padBottom;
  const bars=items.map((item,i)=>{
    const x=padX+i*(colW+gap);
    const barH=item.count>0 ? Math.max(6,Math.round(item.share*chartH)) : 2;
    const y=padTop+chartH-barH;
    const activeCls=highlightFn && highlightFn(item,i) ? 'svg-bar-gold' : barClass;
    const cls=item.count>0 ? activeCls : 'svg-bar-zero';
    const label=String(item[labelKey]);
    return `<g>`+
      (item.count>0 ? `<text class="svg-val" x="${x+colW/2}" y="${y-6}" text-anchor="middle">${item.count}</text>` : '')+
      `<rect class="${cls}" x="${x}" y="${y}" width="${colW}" height="${barH}" rx="6"><title>${label}: ${item.count}</title></rect>`+
      `<text class="svg-axis" x="${x+colW/2}" y="${padTop+chartH+17}" text-anchor="middle">${label}</text>`+
    `</g>`;
  }).join('');
  return `<svg class="stats-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${ariaLabel}">${bars}</svg>`;
}

function renderHorizontalRows(items,{e,t,barClass='svg-bar-accent',highlightFn=null,showAvg=false,filmstrip=false,emptyText}){
  if(!items.length)return `<p class="stats-empty-note">${emptyText}</p>`;
  return `<div class="stats-hbar-list ${filmstrip?'filmstrip-decade-list':''}">${items.map((item,i)=>{
    const w=item.count>0 ? Math.max(4,Math.round((item.share || 0)*100)) : 0;
    const activeCls=highlightFn && highlightFn(item,i) ? 'svg-bar-gold' : barClass;
    return `<div class="stats-hbar-row ${filmstrip?'filmstrip-decade-frame':''}">`+
      `<div class="stats-hbar-head"><strong>${e(item.label || item.name || item.decade)}</strong><span class="stats-hbar-meta">${item.count} ${t('filmCount')}${showAvg && item.avgRating!==null ? ` · <span class="gold-text">★ ${item.avgRating}</span>` : ''}</span></div>`+
      `<svg class="stats-hbar-svg" viewBox="0 0 100 8" preserveAspectRatio="none" aria-hidden="true"><rect class="svg-track" x="0" y="0" width="100" height="8" rx="4"/>${w>0 ? `<rect class="${activeCls}" x="0" y="0" width="${w}" height="8" rx="4"/>` : ''}</svg>`+
    `</div>`;
  }).join('')}</div>`;
}

function renderGenreRadar(radar,{e,t}){
  if(!radar || !radar.hasData)return '';
  return `<div class="genre-constellation-wrap"><svg class="genre-radar-svg" viewBox="0 0 260 220" role="img" aria-label="${e(t('statsConstellationTitle'))}">`+
    radar.rings.map(pts=>`<polygon class="radar-ring" points="${pts}" fill="none"></polygon>`).join('')+
    radar.axes.map(ax=>`<line class="radar-axis" x1="130" y1="110" x2="${ax.x2}" y2="${ax.y2}"></line>`).join('')+
    `<polygon class="radar-shape" points="${radar.polygon}"></polygon>`+
    radar.axes.map(ax=>`<circle class="radar-dot" cx="${ax.dotX}" cy="${ax.dotY}" r="4"><title>${e(ax.name)}: ${ax.count}</title></circle><text class="radar-label" x="${ax.lx}" y="${ax.ly}" text-anchor="${ax.anchor}">${e(ax.name)}</text>`).join('')+
  `</svg></div>`;
}

function renderWatchHeatmap(heatmap,months,weekdaysShort,{e,t,year}){
  if(!heatmap)return '';
  return `<section class="stats-panel stats-full-panel">`+
    `<div class="stats-panel-head"><div><h2>${year} · ${e(t('statsHeatmapTitle'))}</h2></div><span class="stats-privacy-pill">${heatmap.activeDays} ${e(t('statsHeatmapActive'))}</span></div>`+
    `<div class="heatmap-scroll"><svg class="watch-heatmap-svg" viewBox="0 0 ${heatmap.width} ${heatmap.height}" role="img" aria-label="${year} ${e(t('statsHeatmapTitle'))}">`+
      heatmap.monthMarkers.map(m=>`<text class="heatmap-month-label" x="${m.x}" y="12">${e(months[m.month-1] || '')}</text>`).join('')+
      `<text class="heatmap-day-label" x="2" y="26">${e(weekdaysShort[0] || 'Mon')}</text>`+
      `<text class="heatmap-day-label" x="2" y="52">${e(weekdaysShort[2] || 'Wed')}</text>`+
      `<text class="heatmap-day-label" x="2" y="78">${e(weekdaysShort[4] || 'Fri')}</text>`+
      heatmap.cells.map(c=>`<rect class="heatmap-cell heatmap-lvl-${c.level}" x="${c.x}" y="${c.y}" width="10" height="10" rx="2.5"><title>${c.date} · ${c.count} ${e(t('filmCount'))}</title></rect>`).join('')+
    `</svg></div>`+
    `<div class="heatmap-legend" aria-hidden="true"><span>${e(t('statsQuiet'))}</span><i class="heatmap-swatch heatmap-lvl-0"></i><i class="heatmap-swatch heatmap-lvl-1"></i><i class="heatmap-swatch heatmap-lvl-2"></i><i class="heatmap-swatch heatmap-lvl-3"></i><i class="heatmap-swatch heatmap-lvl-4"></i><span>${e(t('statsMarathon'))}</span></div>`+
  `</section>`;
}

function renderPeopleList(people,{e,t,image,emptyText}){
  if(!people.length)return `<p class="stats-empty-note">${emptyText}</p>`;
  return `<div class="stats-people-grid">${people.map((p,idx)=>{
    const photo=image(p.profile_path,'w185');
    const avatar=photo ? `<img src="${photo}" alt="" loading="lazy">` : `<span class="stats-person-fallback noir-thumb">${NOIR_SILHOUETTE_SVG}</span>`;
    const meta=`${p.count} ${t('filmCount')}${p.avgRating!==null ? ` · ★ ${p.avgRating}` : ''}`;
    const medal=idx<3 ? `<span class="podium-medal">#${idx+1}</span>` : '';
    const rankCls=idx<3 ? `podium-rank-${idx+1}` : '';
    const inner=`${medal}${avatar}<div><strong>${e(p.name)}</strong><span>${e(meta)}</span></div>`;
    return p.id ? `<a class="stats-person-card ${rankCls}" href="/person/${p.id}" data-route>${inner}</a>` : `<div class="stats-person-card ${rankCls}">${inner}</div>`;
  }).join('')}</div>`;
}

function renderStudiosList(studios,{e,t,emptyText}){
  if(!studios.length)return `<p class="stats-empty-note">${emptyText}</p>`;
  return `<div class="stats-people-grid stats-studios-grid">${studios.map(s=>{
    const avatar=`<span class="stats-person-fallback stats-studio-badge">${e(s.name?.[0] || '◈')}</span>`;
    const meta=`${s.count} ${t('filmCount')}${s.avgRating!==null ? ` · ★ ${s.avgRating}` : ''}`;
    return `<div class="stats-person-card">${avatar}<div><strong>${e(s.name)}</strong><span>${e(meta)}</span></div></div>`;
  }).join('')}</div>`;
}

export function createStatsPage({state,store,t,e,image,toast}){
  let selectedYear=new Date().getFullYear();
  let lastStats=null;

  async function computeCurrentStats(){
    const owner=state.owner;
    const work=await store.read(owner);
    const active=Object.values(work.entries || {}).filter(x=>x?.data && !x.data.deleted_at);
    const keys=libraryMetadataKeys(active,state.lang);
    const meta=keys.length ? await store.metadataBatch(keys) : {};
    return {owner,stats:computeCinemaStats(active,meta,{lang:state.lang,year:selectedYear})};
  }

  async function statsPage(view){
    const {owner,stats}=await computeCurrentStats();
    if(view!==state.view || owner!==state.owner)return;
    lastStats=stats;
    selectedYear=stats.year;

    const {totals,overview,records}=stats;
    const main=document.querySelector('#main');

    if(totals.total===0){
      main.innerHTML=`<div class="page-head"><div class="eyebrow"><span class="dot"></span>${t('statsEyebrow')}</div><h1>${t('statsTitle')}</h1><p>${t('statsIntro')}</p></div>`+
        `<div class="empty"><h2>${t('statsEmptyTitle')}</h2><p>${t('statsEmptyP')}</p><div class="actions center-actions"><a class="button" href="/discover" data-route>${t('browse')} →</a><button class="button secondary" data-action="external-import">${t('importExternal')}</button></div></div><div class="section"></div>`;
      return;
    }

    const months=String(t('monthsShort')).split(',');
    const monthlyItems=stats.monthlyActivity.map((m,i)=>({...m,label:months[i] || String(m.month)}));
    const ratingItems=stats.ratingDistribution.map(r=>({...r,label:String(r.rating)}));
    const weekdaysLabels=String(t('weekdaysShort')).split(',');
    const weekdayItems=stats.weekdays.map((w,i)=>({...w,label:weekdaysLabels[i] || String(w.day)}));
    const runtimeItems=stats.runtimeBuckets.map(b=>({...b,label:t('statsRuntime_'+b.key)}));
    const decadeItems=stats.decades.map(d=>({...d,label:formatDecadeLabel(d.decade,state.lang)}));

    const yearSwitcher=stats.availableYears.length>0
      ? `<nav class="stats-year-switcher" aria-label="${e(t('statsSelectYear'))}">${stats.availableYears.slice(0,6).map(y=>`<button type="button" class="stats-year-pill ${y===stats.year?'is-active':''}" data-stats-year="${y}" aria-pressed="${y===stats.year}">${y}</button>`).join('')}</nav>`
      : '';

    const insightChips=[];
    if(overview.topDecade)insightChips.push(`<span class="stats-insight-chip">${e(t('statsPeakEra').replace('{era}',formatDecadeLabel(overview.topDecade,state.lang)))}</span>`);
    if(overview.criticDelta!==null){
      const deltaLabel=overview.criticDelta>0
        ? t('statsCriticAbove').replace('{delta}',`+${overview.criticDelta}`)
        : overview.criticDelta<0
          ? t('statsCriticBelow').replace('{delta}',String(overview.criticDelta))
          : t('statsCriticMatch').replace('{avg}',String(overview.tmdbAvg));
      insightChips.push(`<span class="stats-insight-chip stats-chip-gold">${e(deltaLabel)}</span>`);
    }
    if(overview.longestStreak>1)insightChips.push(`<span class="stats-insight-chip">${e(t('statsBestStreak').replace('{days}',String(overview.longestStreak)))}</span>`);
    if(overview.tenCount>0)insightChips.push(`<span class="stats-insight-chip stats-chip-gold">${e(t('statsMasterpieces').replace('{count}',String(overview.tenCount)))}</span>`);
    if(overview.avgRuntime)insightChips.push(`<span class="stats-insight-chip">${e(t('statsAvgRuntimeChip').replace('{min}',String(overview.avgRuntime)))}</span>`);

    const heroHeadline=overview.topGenreName
      ? t('statsDrawnTo').replace('{genre}',overview.topGenreName)
      : t('statsArchiveShaping');

    const heroBanner=
      `<section class="stats-hero-banner" aria-label="${e(t('statsHeroEyebrow'))}">`+
        `<div class="stats-ring-wrap">`+
          `<svg class="stats-ring-svg" viewBox="0 0 100 100" role="img" aria-label="${e(overview.completionPct+'% '+t('statsWatched'))}">`+
            `<circle class="stats-ring-track" cx="50" cy="50" r="40" fill="none" stroke-width="8"></circle>`+
            `<circle class="stats-ring-fill" cx="50" cy="50" r="40" fill="none" stroke-width="8" stroke-linecap="round" stroke-dasharray="${overview.completionRingDash} ${overview.ringCircumference}" transform="rotate(-90 50 50)"></circle>`+
          `</svg>`+
          `<div class="stats-ring-center"><strong>${overview.completionPct}%</strong><span>${e(t('statsWatched'))}</span></div>`+
        `</div>`+
        `<div class="stats-hero-copy">`+
          `<div class="eyebrow"><span class="dot"></span>${e(t('statsHeroEyebrow'))}</div>`+
          `<h2>${e(heroHeadline)}</h2>`+
          (insightChips.length ? `<div class="stats-insight-chips">${insightChips.join('')}</div>` : '')+
        `</div>`+
      `</section>`;

    const kpis=[
      {value:totals.watched.toLocaleString(),label:t('statsWatched'),sub:`${totals.total} ${t('filmCount')}`},
      {value:totals.avgRating!==null ? `★ ${totals.avgRating}` : '—',label:t('statsAvgRating'),sub:overview.medianRating!==null ? `${totals.rated} ${t('statsRatedCount')} · ${t('statsMedianShort')} ${overview.medianRating}` : `${totals.rated} ${t('statsRatedCount')}`,gold:true},
      {value:totals.favorites.toLocaleString(),label:t('statsFavorites'),sub:`${overview.favoriteRate}% · ${totals.withNotes} ${t('statsNotesCount')}`},
      {value:totals.watchedThisYear.toLocaleString(),label:`${stats.year} · ${t('statsThisYear')}`,sub:`${totals.watchlist} ${t('statsWatchlist')}`},
      {value:formatWatchTime(totals.totalMinutes,t),label:t('statsWatchTime'),sub:totals.runtimeCount ? `${totals.runtimeCount} ${t('filmCount')}` : t('statsRuntimePending'),wide:true},
    ];

    const milestoneDefs=[
      {label:t('statsRecordLongest'),rec:records.longest,detail:records.longest ? `${records.longest.runtime} ${t('minutes')}` : ''},
      {label:t('statsRecordShortest'),rec:records.shortest,detail:records.shortest ? `${records.shortest.runtime} ${t('minutes')}` : ''},
      {label:t('statsRecordOldest'),rec:records.oldest,detail:records.oldest ? String(records.oldest.year || '') : ''},
      {label:t('statsRecordNewest'),rec:records.newest,detail:records.newest ? String(records.newest.year || '') : ''},
    ].filter(m=>Boolean(m.rec));

    const recordsMarkup=milestoneDefs.length
      ? `<section class="stats-records-grid" aria-label="${e(t('statsMilestonesTitle'))}">${milestoneDefs.map(m=>{
          const openAttr=m.rec.tmdbId ? `data-movie="${m.rec.tmdbId}"` : `data-custom="${e(m.rec.key)}"`;
          const metaText=[m.detail,m.rec.rating ? `★ ${m.rec.rating}/10` : ''].filter(Boolean).join(' · ');
          return `<button type="button" class="stats-record-card" ${openAttr}><span class="stats-record-label">${e(m.label)}</span><strong>${e(m.rec.title)}</strong><span class="stats-record-meta">${e(metaText)}</span></button>`;
        }).join('')}</section>`
      : '';

    const highestMarkup=stats.highestRated.length ? `<section class="stats-panel stats-full-panel"><div class="stats-panel-head"><div><h2>${t('statsHighestRatedTitle')}</h2></div><a class="text-link" href="/library" data-route>${t('openLibrary')} →</a></div><div class="movie-grid">${stats.highestRated.map(f=>{
      const poster=image(f.poster_path);
      const openAttr=f.tmdbId ? `data-movie="${f.tmdbId}"` : `data-custom="${e(f.key)}"`;
      return `<article class="movie-card"><div class="poster-button"><button class="poster-open" ${openAttr} aria-label="${e(f.title)}">${poster ? `<img src="${poster}" alt="${e(f.title)}" loading="lazy">` : `<span class="poster-fallback">${e(f.title)}</span>`}</button><span class="poster-label gold-pill">★ ${f.rating}/10</span>${f.favorite ? `<span class="favorite-pill" aria-hidden="true">♥</span>` : ''}</div><h3 class="card-title"><button class="plain-title" ${openAttr}>${e(f.title)}</button></h3><div class="card-meta"><span>${e(f.year || '')}</span><span class="card-rating">★ ${f.rating}</span></div></article>`;
    }).join('')}</div></section>` : '';

    const peakMonthSub=overview.peakMonth
      ? `${t('statsMonthlyP')} · ${t('statsPeakMonthLabel')}: ${months[overview.peakMonth-1] || overview.peakMonth} (${overview.peakMonthCount})`
      : t('statsMonthlyP');

    main.innerHTML=
      `<div class="page-head"><div class="eyebrow"><span class="dot"></span>${t('statsEyebrow')}</div><div class="stats-title-row"><div><h1>${t('statsTitle')}</h1><p>${t('statsIntro')}</p></div>${yearSwitcher}</div><div class="stats-head-actions"><button type="button" class="button small" data-action="stats-card">✦ ${t('statsShareCard')}</button><span class="stats-privacy-pill">${t('statsPrivateNote')}</span><a class="text-link" href="/library" data-route>← ${t('library')}</a></div></div>`+
      heroBanner+
      `<section class="stats-kpis" aria-label="${t('stats')}">${kpis.map(k=>`<div class="stat stats-kpi ${k.wide?'stats-kpi-wide':''}"><strong class="${k.gold?'gold-text':''}">${e(k.value)}</strong><span>${e(k.label)}</span><small>${e(k.sub)}</small></div>`).join('')}</section>`+
      recordsMarkup+
      renderWatchHeatmap(stats.watchHeatmap,months,weekdaysLabels,{e,t,year:stats.year})+
      `<section class="stats-grid">`+
        `<article class="stats-panel"><div class="stats-panel-head"><div><h2>${t('statsGenresTitle')}</h2><p>${t('statsGenresP')}</p></div></div>${renderGenreRadar(stats.genreRadar,{e,t})}${renderHorizontalRows(stats.topGenres,{e,t,barClass:'svg-bar-accent',showAvg:true,emptyText:e(t('statsNoGenres'))})}</article>`+
        `<article class="stats-panel"><div class="stats-panel-head"><div><h2>${t('statsRatingsTitle')}</h2><p>${t('statsRatingsP')}</p></div></div>${renderVerticalSvg(ratingItems,{labelKey:'label',ariaLabel:e(t('statsRatingsTitle')),barClass:'svg-bar-accent',highlightFn:item=>item.rating>=8,emptyText:e(t('statsNoRatings'))})}</article>`+
        `<article class="stats-panel"><div class="stats-panel-head"><div><h2>${stats.year} · ${t('statsMonthlyTitle')}</h2><p>${e(peakMonthSub)}</p></div></div>${renderVerticalSvg(monthlyItems,{labelKey:'label',ariaLabel:e(t('statsMonthlyTitle')),barClass:'svg-bar-accent',emptyText:e(t('statsNoDatedYear'))})}</article>`+
        `<article class="stats-panel"><div class="stats-panel-head"><div><h2>${t('statsWeekdaysTitle')}</h2><p>${t('statsWeekdaysP')}</p></div></div>${renderVerticalSvg(weekdayItems,{labelKey:'label',ariaLabel:e(t('statsWeekdaysTitle')),barClass:'svg-bar-accent',highlightFn:item=>item.day>=4,emptyText:e(t('statsNoDatedWatches'))})}</article>`+
        `<article class="stats-panel"><div class="stats-panel-head"><div><h2>${t('statsDecadesTitle')}</h2><p>35MM · ${t('statsDecadesP')}</p></div></div>${renderHorizontalRows(decadeItems,{e,t,barClass:'svg-bar-gold',filmstrip:true,showAvg:false,emptyText:e(t('statsNoDecades'))})}</article>`+
        `<article class="stats-panel"><div class="stats-panel-head"><div><h2>${t('statsRuntimeTitle')}</h2><p>${overview.avgRuntime ? e(t('statsAvgRuntimeChip').replace('{min}',String(overview.avgRuntime))) : t('statsRuntimeP')}</p></div></div>${totals.runtimeCount ? renderHorizontalRows(runtimeItems,{e,t,barClass:'svg-bar-accent',highlightFn:item=>item.key==='epic',showAvg:false,emptyText:e(t('statsRuntimePending'))}) : `<p class="stats-empty-note">${e(t('statsRuntimePending'))}</p>`}</article>`+
      `</section>`+
      `<section class="stats-grid">`+
        `<article class="stats-panel"><div class="stats-panel-head"><div><h2>${t('statsDirectorsTitle')}</h2></div></div>${renderPeopleList(stats.topDirectors,{e,t,image,emptyText:e(t('statsNoPeople'))})}</article>`+
        `<article class="stats-panel"><div class="stats-panel-head"><div><h2>${t('statsActorsTitle')}</h2></div></div>${renderPeopleList(stats.topActors,{e,t,image,emptyText:e(t('statsNoPeople'))})}</article>`+
      `</section>`+
      (stats.topStudios.length ? `<section class="stats-panel stats-full-panel"><div class="stats-panel-head"><div><h2>${t('statsStudiosTitle')}</h2><p>${t('statsStudiosP')}</p></div></div>${renderStudiosList(stats.topStudios,{e,t,emptyText:e(t('statsNoStudios'))})}</section>` : '')+
      highestMarkup+
      `<div class="section"></div>`;
  }

  statsPage.handleClick=async function(button){
    if(button.dataset.statsYear){
      const y=Number(button.dataset.statsYear);
      if(Number.isInteger(y) && y>=1800 && y<=2200){
        selectedYear=y;
        await statsPage(state.view);
      }
      return true;
    }
    if(button.dataset.action==='stats-card'){
      const current=lastStats && lastStats.year===selectedYear ? lastStats : (await computeCurrentStats()).stats;
      lastStats=current;
      openStatsCardDialog(current,{t,lang:state.lang,user:state.user,toast});
      return true;
    }
    return false;
  };

  return statsPage;
}
