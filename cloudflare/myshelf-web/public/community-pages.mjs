import {createRecommender} from './recommendation-catalog.mjs';
import {GENRES} from './recommendation-model.mjs';
import {socialQuery,socialCursor,socialPage} from './social-model.mjs';
const trGenres={28:'Aksiyon',12:'Macera',16:'Animasyon',35:'Komedi',80:'Suç',99:'Belgesel',18:'Dram',10751:'Aile',14:'Fantastik',36:'Tarih',27:'Korku',10402:'Müzik',9648:'Gizem',10749:'Romantik',878:'Bilim-Kurgu',10770:'TV Filmi',53:'Gerilim',10752:'Savaş',37:'Western'};
export function createCommunityPages({state,store,api,t,e,image,card,render,navigate,errorText,toast}){
  const recommender=createRecommender(store,api);
  let mode='balanced',refresh=false,requestNumber=0;
  const date=value=>new Intl.DateTimeFormat(state.lang==='tr'?'tr-TR':'en-US',{day:'numeric',month:'short',timeZone:'UTC'}).format(new Date(value+'T00:00:00Z'));
  const skeleton=(label='recommendLoading')=>`<div class="recommendation-loading" role="status"><span class="spinner"></span><p>${t(label)}</p></div>`;
  function recommendationCard(m,work){
    const genres=(m.genre_ids || []).filter(id=>GENRES[id]).slice(0,3).map(id=>`<span class="genre-tag">${e(state.lang==='tr'?trGenres[id]:GENRES[id])}</span>`).join('');
    const reason=m.liked_title?t('recommendShared').replace('{title}',m.liked_title):t('recommendDiscovery');
    return `<div class="recommendation-item">${card(m,work,m.recommendation_highlight?t('classicBadge'):'')}<div class="recommendation-tags">${genres}</div><p class="recommendation-reason">${e(reason)}</p><button class="quiet recommendation-hide" data-recommendation-owner="${e(state.owner)}" data-hide-recommendation="${m.id}">${t('hideSuggestion')}</button></div>`;
  }
  async function recommendations(view){
    const owner=state.owner,number=++requestNumber;
    const isCurrent=()=>state.view===view && owner===state.owner && number===requestNumber;
    document.querySelector('#main').innerHTML=`<div class="page-head"><div class="eyebrow">${t('recommendEyebrow')}</div><h1>${t('recommendTitle')}</h1><p>${t('recommendIntro')}</p></div><div class="recommendation-toolbar"><div class="tabs">${['familiar','balanced','explore'].map(k=>`<button class="tab ${mode===k?'selected':''}" data-recommendation-mode="${k}" aria-pressed="${mode===k}">${t('mode_'+k)}</button>`).join('')}</div><button class="button secondary small" data-refresh-recommendations>${t('newSuggestions')} ↻</button></div><p class="form-hint recommendation-mode-hint">${t('modeHint_'+mode)}</p><section id="recommendation-results" aria-live="polite" aria-busy="true">${skeleton()}</section><div class="section"></div>`;
    const refreshButton=document.querySelector('[data-refresh-recommendations]');refreshButton.disabled=true;
    try{
      const requestedRefresh=refresh;refresh=false;
      const result=await recommender.recommend(owner,{mode,lang:state.lang,refresh:requestedRefresh,isCurrent});
      if(!isCurrent())return;
      const work=await store.read(owner);
      const intro=!result.profile.ready?`<div class="recommendation-invitation"><strong>${t('recommendWarmup')}</strong><p>${t('recommendWarmupP')}</p><a class="text-link" href="/library" data-route>${t('openLibrary')} →</a></div>`:'';
      const changed=result.profile_changed?`<div class="info-banner">${t('recommendChanged')}</div>`:'';
      const warning=result.unavailable?`<p class="form-hint recommendation-notice">${t('recommendLimited')}</p>`:'';
      const prefs=work.recommendations || {},hidden=Array.isArray(prefs.dismissed)?prefs.dismissed:[];
      const recentHidden=hidden.slice(-30).reverse();
      const hiddenMeta=recentHidden.length && store.metadataBatch ? await store.metadataBatch(recentHidden.flatMap(id=>[state.lang+':'+id,'recommendation-features:'+id])) : null;
      const hiddenRows=hiddenMeta ? recentHidden.map(id=>({id,movie:hiddenMeta[state.lang+':'+id] || hiddenMeta['recommendation-features:'+id]})) : await Promise.all(recentHidden.map(async id=>({id,movie:await store.metadata(state.lang+':'+id) || await store.metadata('recommendation-features:'+id)})));
      if(!isCurrent())return;
      const restore=hidden.length?`<details class="hidden-suggestions"><summary>${t('hiddenSuggestions')} (${hidden.length})</summary><p>${t('hiddenExplanation')}</p><button class="quiet red" data-recommendation-owner="${e(owner)}" data-restore-all-recommendations>${t('restoreAllSuggestions')}</button>${hiddenRows.map(row=>`<div><span>${e(row.movie?.title || 'TMDB #'+row.id)}</span><button class="quiet red" data-recommendation-owner="${e(owner)}" data-restore-recommendation="${row.id}">${t('showAgain')}</button></div>`).join('')}</details>`:'';
      document.querySelector('#recommendation-results').innerHTML=intro+changed+warning+(result.movies.length?`<div class="movie-grid recommendation-grid">${result.movies.map(m=>recommendationCard(m,work)).join('')}</div>`:`<div class="empty"><h2>${t('recommendEmpty')}</h2><p>${t('recommendEmptyP')}</p><a class="button secondary" href="/discover" data-route>${t('browse')} →</a></div>`)+restore;
      document.querySelector('#recommendation-results').setAttribute('aria-busy','false');
      for(const m of result.movies)await store.cacheMetadata(state.lang+':'+m.id,{id:m.id,title:m.title,poster_path:m.poster_path,genre_ids:m.genre_ids,release_date:m.release_date,vote_average:m.vote_average});
    }catch(error){
      if(isCurrent()){
        document.querySelector('#recommendation-results').innerHTML=`<div class="empty"><h2>${t('recommendEmpty')}</h2><p>${e(errorText(error))}</p><a class="button secondary" href="/library" data-route>${t('openLibrary')}</a></div>`;
        document.querySelector('#recommendation-results').setAttribute('aria-busy','false');
      }
    }finally{if(isCurrent())refreshButton.disabled=false;}
  }
  const memberCard=row=>`<a class="member-card" href="/u/${e(row.username)}"><img src="/assets/avatars/${e(row.avatar_id)}.svg" alt="" width="68" height="68"><div><strong>${e(row.display_name || row.username)}</strong><span>@${e(row.username)}</span></div><span class="member-arrow" aria-hidden="true">↗</span></a>`;
  const activityCard=(row,m)=>`<article class="activity-card"><a class="activity-person" href="/u/${e(row.username)}"><img src="/assets/avatars/${e(row.avatar_id)}.svg" alt="" width="36" height="36"><div><strong>${e(row.display_name || row.username)}</strong><span>@${e(row.username)}</span></div></a><a class="activity-film" href="/movie/${row.tmdb_id}" data-route>${image(m.poster_path)?`<img src="${image(m.poster_path)}" alt="" width="72" height="108" loading="lazy">`:`<span class="activity-placeholder">${row.tmdb_id}</span>`}<div><span class="activity-watched">${t('watched')}</span><h3>${e(m.title || 'TMDB #'+row.tmdb_id)}</h3><p>${e(date(row.watched_date))}${row.rating?` <span class="card-rating">· ★ ${row.rating}/10</span>`:''}</p></div></a></article>`;
  async function social(view){
    const params=new URLSearchParams(location.search),kind=params.get('view')==='week'?'week':'people',query=socialQuery(params.get('q') || '');
    const tabURL=tab=>'/social?'+new URLSearchParams({view:tab,q:query});
    document.querySelector('#main').innerHTML=`<div class="page-head"><div class="eyebrow">${t('socialEyebrow')}</div><h1>${t('socialTitle')}</h1><p>${t('socialIntro')}</p></div><div class="toolbar social-toolbar"><div class="tabs"><a class="tab ${kind==='people'?'selected':''}" href="${e(tabURL('people'))}" data-route ${kind==='people'?'aria-current="page"':''}>${t('socialPeople')}</a><a class="tab ${kind==='week'?'selected':''}" href="${e(tabURL('week'))}" data-route ${kind==='week'?'aria-current="page"':''}>${t('socialWeek')}</a></div><form id="social-search-form" class="search-box"><input name="query" value="${e(query)}" placeholder="${t('socialSearch')}" aria-label="${t('socialSearch')}" maxlength="60"><button aria-label="${t('searchButton')}">⌕</button></form></div><p class="form-hint social-privacy">${t('socialPrivacy')}</p><section id="social-results" aria-live="polite" aria-busy="true">${skeleton('socialLoading')}</section><div class="section"></div>`;
    try{
      const request=new URLSearchParams({view:kind,q:query});if(params.get('cursor'))request.set('cursor',params.get('cursor'));
      const page=socialPage(await api('social?'+request),kind);if(view!==state.view)return;
      const next=page.next_cursor?`<div class="social-pagination"><a class="button secondary small" href="/social?${e(new URLSearchParams({view:kind,q:query,cursor:socialCursor(kind,query,page.next_cursor)}).toString())}" data-route>${t('nextPage')} →</a></div>`:'';
      const range=kind==='week'?`<p class="social-week-range">${e(date(page.week_start))} — ${e(date(page.week_end))}</p>`:'';
      const empty=`<div class="empty"><h2>${t(query?'socialNoMatches':kind==='people'?'socialEmptyPeople':'socialEmptyWeek')}</h2><p>${t(query?'socialTrySearch':kind==='people'?'socialEmptyPeopleP':'socialEmptyWeekP')}</p>${state.user&&!query?`<a class="text-link" href="/profile" data-route>${t('openProfile')} →</a>`:''}</div>`;
      const rows=kind==='people'?page.rows.map(memberCard).join(''):page.rows.map(row=>`<div data-activity-film="${row.tmdb_id}" data-activity-user="${e(row.username)}">${activityCard(row,{})}</div>`).join('');
      document.querySelector('#social-results').innerHTML=range+(page.rows.length?`<div class="${kind==='people'?'member-grid':'activity-grid'}">${rows}</div>`:empty)+next;
      document.querySelector('#social-results').setAttribute('aria-busy','false');
      if(kind==='week')for(let n=0;n<page.rows.length;n+=4){
        if(view!==state.view)return;
        const batch=await Promise.allSettled(page.rows.slice(n,n+4).map(async row=>{
          let movie=await store.metadata(state.lang+':'+row.tmdb_id);
          if(!movie){movie=await api(`catalog/movie/${row.tmdb_id}?language=${state.lang==='tr'?'tr-TR':'en-US'}`);if(movie.id!==row.tmdb_id)throw Error('invalid_response');await store.cacheMetadata(state.lang+':'+row.tmdb_id,movie);}
          return {row,movie};
        }));
        if(view!==state.view)return;
        for(const result of batch)if(result.status==='fulfilled'){
          const {row,movie}=result.value,element=document.querySelector(`[data-activity-film="${row.tmdb_id}"][data-activity-user="${row.username}"]`);
          if(element)element.innerHTML=activityCard(row,movie);
        }
        if(batch.every(r=>r.status==='rejected'))break;
      }
    }catch(error){if(view===state.view){document.querySelector('#social-results').innerHTML=`<div class="empty"><h2>${t('socialUnavailable')}</h2><p>${e(errorText(error))}</p><button class="button secondary small" data-retry-community>${t('retry')}</button></div>`;document.querySelector('#social-results').setAttribute('aria-busy','false');}}
  }
  async function handleClick(button){
    if(button.dataset.recommendationOwner && button.dataset.recommendationOwner!==state.owner)throw Error('account_changed');
    if(button.dataset.recommendationMode){mode=button.dataset.recommendationMode;await render();return true;}
    if(button.hasAttribute('data-refresh-recommendations')){refresh=true;await render();return true;}
    if(button.dataset.hideRecommendation){await recommender.dismiss(state.owner,Number(button.dataset.hideRecommendation));toast(t('suggestionHidden'));await render();return true;}
    if(button.dataset.restoreRecommendation){const id=Number(button.dataset.restoreRecommendation);await store.mutate(state.owner,w=>{if(w.recommendations)w.recommendations.dismissed=w.recommendations.dismissed.filter(v=>v!==id);});await render();return true;}
    if(button.hasAttribute('data-restore-all-recommendations')){await store.mutate(state.owner,w=>{if(w.recommendations)w.recommendations.dismissed=[];});await render();return true;}
    if(button.hasAttribute('data-retry-community')){await render();return true;}
    return false;
  }
  async function handleSubmit(form){
    if(form.id!=='social-search-form')return false;
    const query=socialQuery(new FormData(form).get('query') || ''),kind=new URLSearchParams(location.search).get('view')==='week'?'week':'people';
    navigate('/social?'+new URLSearchParams({view:kind,q:query}));return true;
  }
  return {recommendations,social,handleClick,handleSubmit};
}
