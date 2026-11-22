// CSP-safe pure SVG Personal Cinema Statistics page for MyShelf Web.
import {computeCinemaStats} from './stats-model.mjs';
import {libraryMetadataKeys} from './library-model.mjs';

function formatWatchTime(totalMinutes,t){
  if(!totalMinutes || totalMinutes<=0)return '—';
  const hours=Math.floor(totalMinutes/60),mins=totalMinutes%60;
  if(hours>=48){
    const days=(hours/24).toFixed(1).replace(/\.0$/,'');
    return `${hours.toLocaleString()} ${t('statsHours')} · ${days} ${t('statsDays')}`;
  }
  return mins ? `${hours} ${t('statsHours')} ${mins} ${t('statsMinutesShort')}` : `${hours} ${t('statsHours')}`;
}

function renderVerticalSvg(items,{labelKey,ariaLabel,barClass='svg-bar',emptyText}){
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
    const cls=item.count>0 ? barClass : 'svg-bar-zero';
    const label=String(item[labelKey]);
    return `<g>`+
      (item.count>0 ? `<text class="svg-val" x="${x+colW/2}" y="${y-6}" text-anchor="middle">${item.count}</text>` : '')+
      `<rect class="${cls}" x="${x}" y="${y}" width="${colW}" height="${barH}" rx="6"><title>${label}: ${item.count}</title></rect>`+
      `<text class="svg-axis" x="${x+colW/2}" y="${padTop+chartH+17}" text-anchor="middle">${label}</text>`+
    `</g>`;
  }).join('');
  return `<svg class="stats-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${ariaLabel}">${bars}</svg>`;
}

function renderHorizontalRows(items,{e,t,barClass='svg-bar-accent',showAvg=false,emptyText}){
  if(!items.length)return `<p class="stats-empty-note">${emptyText}</p>`;
  return `<div class="stats-hbar-list">${items.map(item=>{
    const w=Math.max(4,Math.round((item.share || 0)*100));
    return `<div class="stats-hbar-row">`+
      `<div class="stats-hbar-head"><strong>${e(item.name || item.decade)}</strong><span class="stats-hbar-meta">${item.count} ${t('filmCount')}${showAvg && item.avgRating!==null ? ` · <span class="gold-text">★ ${item.avgRating}</span>` : ''}</span></div>`+
      `<svg class="stats-hbar-svg" viewBox="0 0 100 8" preserveAspectRatio="none" aria-hidden="true"><rect class="svg-track" x="0" y="0" width="100" height="8" rx="4"/><rect class="${barClass}" x="0" y="0" width="${w}" height="8" rx="4"/></svg>`+
    `</div>`;
  }).join('')}</div>`;
}

function renderPeopleList(people,{e,t,image,emptyText}){
  if(!people.length)return `<p class="stats-empty-note">${emptyText}</p>`;
  return `<div class="stats-people-grid">${people.map(p=>{
    const photo=image(p.profile_path,'w185');
    const avatar=photo ? `<img src="${photo}" alt="" loading="lazy">` : `<span class="stats-person-fallback">${e(p.name?.[0] || '?')}</span>`;
    const meta=`${p.count} ${t('filmCount')}${p.avgRating!==null ? ` · ★ ${p.avgRating}` : ''}`;
    const inner=`${avatar}<div><strong>${e(p.name)}</strong><span>${e(meta)}</span></div>`;
    return p.id ? `<a class="stats-person-card" href="/person/${p.id}" data-route>${inner}</a>` : `<div class="stats-person-card">${inner}</div>`;
  }).join('')}</div>`;
}

export function createStatsPage({state,store,t,e,image}){
  return async function statsPage(view){
    const owner=state.owner;
    const work=await store.read(owner);
    const active=Object.values(work.entries || {}).filter(x=>x?.data && !x.data.deleted_at);
    const keys=libraryMetadataKeys(active,state.lang);
    const meta=keys.length ? await store.metadataBatch(keys) : {};
    if(view!==state.view || owner!==state.owner)return;

    const stats=computeCinemaStats(active,meta,{lang:state.lang});
    const {totals}=stats;
    const main=document.querySelector('#main');

    if(totals.total===0){
      main.innerHTML=`<div class="page-head"><div class="eyebrow"><span class="dot"></span>${t('statsEyebrow')}</div><h1>${t('statsTitle')}</h1><p>${t('statsIntro')}</p></div>`+
        `<div class="empty"><h2>${t('statsEmptyTitle')}</h2><p>${t('statsEmptyP')}</p><div class="actions center-actions"><a class="button" href="/discover" data-route>${t('browse')} →</a><button class="button secondary" data-action="external-import">${t('importExternal')}</button></div></div><div class="section"></div>`;
      return;
    }

    const months=String(t('monthsShort')).split(',');
    const monthlyItems=stats.monthlyActivity.map((m,i)=>({...m,label:months[i] || String(m.month)}));
    const ratingItems=stats.ratingDistribution.map(r=>({...r,label:String(r.rating)}));

    const kpis=[
      {value:totals.watched.toLocaleString(),label:t('statsWatched'),sub:`${totals.total} ${t('filmCount')}`},
      {value:totals.avgRating!==null ? `★ ${totals.avgRating}` : '—',label:t('statsAvgRating'),sub:`${totals.rated} ${t('statsRatedCount')}`,gold:true},
      {value:totals.favorites.toLocaleString(),label:t('statsFavorites'),sub:`${totals.withNotes} ${t('statsNotesCount')}`},
      {value:totals.watchedThisYear.toLocaleString(),label:`${stats.year} · ${t('statsThisYear')}`,sub:`${totals.watchlist} ${t('statsWatchlist')}`},
      {value:formatWatchTime(totals.totalMinutes,t),label:t('statsWatchTime'),sub:totals.runtimeCount ? `${totals.runtimeCount} ${t('filmCount')}` : t('statsRuntimePending'),wide:true},
    ];

    const highestMarkup=stats.highestRated.length ? `<section class="stats-panel"><div class="stats-panel-head"><div><h2>${t('statsHighestRatedTitle')}</h2></div><a class="text-link" href="/library" data-route>${t('openLibrary')} →</a></div><div class="movie-grid">${stats.highestRated.map(f=>{
      const poster=image(f.poster_path);
      const openAttr=f.tmdbId ? `data-movie="${f.tmdbId}"` : `data-custom="${e(f.key)}"`;
      return `<article class="movie-card"><div class="poster-button"><button class="poster-open" ${openAttr} aria-label="${e(f.title)}">${poster ? `<img src="${poster}" alt="${e(f.title)}" loading="lazy">` : `<span class="poster-fallback">${e(f.title)}</span>`}</button><span class="poster-label gold-pill">★ ${f.rating}/10</span></div><h3 class="card-title"><button class="plain-title" ${openAttr}>${e(f.title)}</button></h3><div class="card-meta"><span>${e(f.year || '')}</span><span>${f.favorite ? '♥' : ''}</span></div></article>`;
    }).join('')}</div></section>` : '';

    main.innerHTML=
      `<div class="page-head"><div class="eyebrow"><span class="dot"></span>${t('statsEyebrow')}</div><h1>${t('statsTitle')}</h1><p>${t('statsIntro')}</p><div class="stats-head-actions"><span class="stats-privacy-pill">${t('statsPrivateNote')}</span><a class="text-link" href="/library" data-route>← ${t('library')}</a></div></div>`+
      `<section class="stats-kpis" aria-label="${t('stats')}">${kpis.map(k=>`<div class="stat stats-kpi ${k.wide?'stats-kpi-wide':''}"><strong class="${k.gold?'gold-text':''}">${e(k.value)}</strong><span>${e(k.label)}</span><small>${e(k.sub)}</small></div>`).join('')}</section>`+
      `<section class="stats-grid">`+
        `<article class="stats-panel"><div class="stats-panel-head"><div><h2>${t('statsRatingsTitle')}</h2><p>${t('statsRatingsP')}</p></div></div>${renderVerticalSvg(ratingItems,{labelKey:'label',ariaLabel:e(t('statsRatingsTitle')),barClass:'svg-bar-gold',emptyText:e(t('statsNoRatings'))})}</article>`+
        `<article class="stats-panel"><div class="stats-panel-head"><div><h2>${stats.year} · ${t('statsMonthlyTitle')}</h2><p>${t('statsMonthlyP')}</p></div></div>${renderVerticalSvg(monthlyItems,{labelKey:'label',ariaLabel:e(t('statsMonthlyTitle')),barClass:'svg-bar-accent',emptyText:e(t('statsNoDatedYear'))})}</article>`+
        `<article class="stats-panel"><div class="stats-panel-head"><div><h2>${t('statsGenresTitle')}</h2><p>${t('statsGenresP')}</p></div></div>${renderHorizontalRows(stats.topGenres,{e,t,barClass:'svg-bar-accent',showAvg:true,emptyText:e(t('statsNoGenres'))})}</article>`+
        `<article class="stats-panel"><div class="stats-panel-head"><div><h2>${t('statsDecadesTitle')}</h2><p>${t('statsDecadesP')}</p></div></div>${renderHorizontalRows(stats.decades,{e,t,barClass:'svg-bar-gold',showAvg:false,emptyText:e(t('statsNoDecades'))})}</article>`+
      `</section>`+
      `<section class="stats-grid">`+
        `<article class="stats-panel"><div class="stats-panel-head"><div><h2>${t('statsDirectorsTitle')}</h2></div></div>${renderPeopleList(stats.topDirectors,{e,t,image,emptyText:e(t('statsNoPeople'))})}</article>`+
        `<article class="stats-panel"><div class="stats-panel-head"><div><h2>${t('statsActorsTitle')}</h2></div></div>${renderPeopleList(stats.topActors,{e,t,image,emptyText:e(t('statsNoPeople'))})}</article>`+
      `</section>`+
      highestMarkup+
      `<div class="section"></div>`;
  };
}
