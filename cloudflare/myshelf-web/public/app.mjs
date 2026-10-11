import * as store from './storage.mjs';
import * as peopleStore from './people-storage.mjs';
import {peopleState,peoplePending,personKey} from './people-model.mjs';
import {equal,iso} from './sync-model.mjs';
import {tr,en} from './strings.mjs';
import {nameAllowed} from './name-policy.mjs';
import {dailyPosters,posterDay,posterPicks} from './hero.mjs';

const $=s=>document.querySelector(s), e=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state={lang:localStorage.getItem('myshelf-language') || (navigator.language.toLowerCase().startsWith('tr') ? 'tr' : 'en'),user:null,owner:'guest',timed:false,syncing:false,error:null,view:0,query:'',discover:'trending',page:1,results:[],filter:'all',auth:{flow:'signin',step:'email',email:'',avatar:'cat-luna'},detail:null};
const avatarIds=['luna','cocoa','sunshine','sage','coral','cloud','midnight','peach','sky','mocha','lilac','mint','cherry','gold','ocean','silver'].map(s=>'cat-'+s);
const t=key=>(state.lang==='tr' ? tr : en)[key] || key;
const image=(path,size='w342')=>/^\/[A-Za-z0-9_-]+\.(jpg|jpeg|png|webp)$/.test(path || '') ? 'https://image.tmdb.org/t/p/'+size+path : '';
let peopleRetryAt=0,peopleRole='actor',peoplePageNumber=1;
let retryAt=0,failures=0,syncTimer,toastTimer;
function toast(text){$('#toast').textContent=text;$('#toast').classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.remove('visible'),4500);}
function errorText(error){return t(error?.code || error?.message)=== (error?.code || error?.message) ? t('genericError') : t(error.code || error.message);}
async function api(path,body,owner=state.owner){
  let response;
  try{response=await fetch('/api/'+path,{method:body===undefined ? 'GET' : 'POST',credentials:'same-origin',signal:AbortSignal.timeout(15000),headers:{...(body===undefined ? {} : {'Content-Type':'application/json','X-MyShelf-Client':'web-v1'}),...(owner!=='guest' ? {'X-MyShelf-Owner':owner} : {})},body:body===undefined ? undefined : JSON.stringify(body)});}catch{const err=Error('cloud_unavailable');err.code='cloud_unavailable';throw err;}
  let value;try{value=await response.json();}catch{throw Error('invalid_response');}
  if(!response.ok){const err=Error(value.error || 'genericError');err.code=value.error;err.status=response.status;throw err;}return value;
}
function translateShell(){document.documentElement.lang=state.lang;document.querySelectorAll('[data-i18n]').forEach(el=>el.textContent=t(el.dataset.i18n));$('#language').textContent=state.lang==='tr' ? 'EN' : 'TR';header();}
function header(){
  $('#account-actions').innerHTML=state.user ? `<button class="user-button" data-action="profile"><img src="/assets/avatars/${e(state.user.profile?.avatar_id || 'cat-luna')}.svg" alt=""><span>${e(state.user.profile?.display_name || state.user.username || t('profile'))}</span></button>` : `<div class="account-buttons"><button class="quiet" data-auth="signin">${t('signin')}</button><button class="quiet signup-link" data-auth="signup">${t('signup')}</button></div>`;
  document.querySelectorAll('nav a').forEach(a=>a.classList.toggle('active',a.pathname===location.pathname));
}
async function session(){
  const response=await api('session');state.user=response.user;state.owner=state.user?.id || 'guest';
  await store.pref('last-account',state.user);
  if(state.user){const adopt=await store.pref('pending-guest-adoption');if(adopt===state.owner){await store.copyGuest(state.owner);await store.pref('pending-guest-adoption',null);}}
  header();return response.user;
}
function card(movie,work,extra=''){
  const id=movie.id,key='tmdb:'+id,entry=work.entries[key],saved=entry && !entry.data.deleted_at;
  const title=movie.title || movie.original_title || 'TMDB #'+id,poster=image(movie.poster_path);
  return `<article class="movie-card"><div class="poster-button"><button class="poster-open" data-movie="${id}" aria-label="${e(title)}">${poster ? `<img src="${poster}" alt="${e(title)}" loading="lazy">` : `<span class="poster-fallback">${e(title)}</span>`}</button>${extra ? `<span class="poster-label">${e(extra)}</span>` : ''}<button class="quick-add ${saved?'saved':''}" data-add="${id}" aria-label="${e((saved?t('saved'):t('add'))+' · '+title)}">${saved?'✓':'+'}</button></div><h3 class="card-title"><button class="plain-title" data-movie="${id}">${e(title)}</button></h3><div class="card-meta"><span>${e(movie.release_date?.slice(0,4) || '')}</span><span class="card-rating">${saved && entry.data.rating ? '★ '+entry.data.rating : movie.vote_average ? '★ '+Number(movie.vote_average).toFixed(1) : ''}</span></div></article>`;
}
async function catalog(id){
  const key=state.lang+':'+id,old=await store.metadata(key);
  if(old?.credits || old && !navigator.onLine)return old;
  const value=await api(`catalog/movie/${id}?language=${state.lang==='tr'?'tr-TR':'en-US'}&append_to_response=credits`);
  if(value.id!==Number(id))throw Error('invalid_response');await store.cacheMetadata(key,value);return value;
}
async function gridLibrary(work){
  const entries=Object.values(work.entries).filter(x=>!x.data.deleted_at).sort((a,b)=>a.data.order_key.localeCompare(b.data.order_key)).reverse();
  const selected=entries.filter(x=>state.filter==='all' || state.filter==='favorites' && x.data.favorite || state.filter==='watched' && x.data.status==='Watched' || state.filter==='watchlist' && x.data.status==='Watchlist');
  const list=await Promise.all(selected.map(async x=>{
    if(x.data.custom)return {entry:x,custom:true};
    const id=Number(x.key.split(':')[1]),known=await store.metadata(state.lang+':'+id) || await store.metadata((state.lang==='tr'?'en':'tr')+':'+id);
    return {entry:x,movie:known || {id,title:'TMDB #'+id,release_date:''}};
  }));
  return list.map(({entry,movie,custom})=>custom ? `<article class="movie-card"><div class="poster-button"><button class="poster-open" data-custom="${e(entry.key)}"><span class="poster-fallback">${e(entry.data.custom.title)}</span></button></div><h3 class="card-title">${e(entry.data.custom.title)}</h3><div class="card-meta">${e(entry.data.custom.year || '')}</div></article>` : card(movie,work,entry.data.status==='Watched'?t('watched'):t('watchlist'))).join('');
}
function syncLabel(work){if(state.owner==='guest')return t('guest');if(!navigator.onLine)return t('offline');if(state.syncing)return t('syncing');if(state.error==='sign_in_required')return t('signInAgain');if(!work.enabled)return t('paused');if(Object.values(work.entries).some(e=>e.conflict))return t('conflictStatus');return store.pending(work) || peoplePending(work) || work.share_outbox || work.profile_pending || state.error ? t('pending') : t('upToDate');}
async function home(view){
  const work=await store.read(state.owner);
  $('#main').innerHTML=`<section class="hero"><div class="hero-copy"><div class="eyebrow"><span class="dot"></span>${t('eyebrow')}</div><h1>${t('hero1')}<br><span>${t('hero2')}</span></h1><p>${t('intro')}</p><div class="actions"><a class="button" href="/discover" data-route>${t('start')} <span>→</span></a><a class="button secondary" href="/library" data-route>${t('library')}</a></div><div class="hero-note">${t('guestNote')}</div></div><section class="poster-stage" aria-label="${t('dailyPosters')}"><div class="hero-fan" id="hero-posters"></div><div class="hero-caption" aria-live="polite" aria-atomic="true"><span class="hero-kicker">${t('dailyPosters')}</span><strong id="hero-caption-title">${t('posterHint')}</strong><span id="hero-caption-meta">${t('posterRefresh')}</span></div></section></section><section class="value-strip">${[1,2,3].map(n=>`<div><strong><span class="number">0${n}</span>${t('value'+n)}</strong><p>${t('value'+n+'p')}</p></div>`).join('')}</section><section class="section"><div class="section-heading"><div><h2>${t('trending')}</h2><p>${t('trendingp')}</p></div><a class="text-link" href="/discover" data-route>${t('seeAll')}</a></div><div class="movie-grid home-grid" id="home-films"><div class="status-line"><span class="spinner"></span></div></div></section><section class="join-banner"><div><h2>${t('join')}</h2><p>${t('joinp')}</p></div><a class="button secondary" href="https://github.com/keremakcn/MyMovieList/releases/latest" target="_blank" rel="noopener">${t('download')}</a></section>`;
  let weekly=[];
  await Promise.allSettled([
    refreshHero(view),
    (async()=>{
      try{
        const response=await api(`catalog/trending/movie/week?language=${state.lang==='tr'?'tr-TR':'en-US'}`);
        if(view!==state.view)return;
        weekly=(response.results || []).filter(m=>!m.adult).slice(0,6);
        $('#home-films').innerHTML=weekly.map(m=>card(m,work)).join('');
        for(const m of weekly)await store.cacheMetadata(state.lang+':'+m.id,m);
      }catch(err){if(view===state.view)$('#home-films').innerHTML=`<p>${e(errorText(err))}</p>`;}
    })()
  ]);
  if(view===state.view && !$('#hero-posters').children.length){
    const fallback=posterPicks(weekly);
    if(fallback.length)showHero(fallback,'');
    else $('#hero-caption-meta').textContent=t('posterUnavailable');
  }
}
async function refreshHero(view=state.view){
  const stage=$('#hero-posters');
  if(!stage || stage.dataset.day===posterDay())return;
  const language=state.lang;
  const selection=await dailyPosters(language,{pref:store.pref,fetchCatalog:api});
  if(view!==state.view || language!==state.lang || !stage.isConnected)return;
  if(stage.dataset.day!==selection.day || !stage.children.length)showHero(selection.films,selection.day);
}
function showHero(films,day){
  const stage=$('#hero-posters');stage.dataset.day=day;
  stage.innerHTML=films.map(m=>`<a class="hero-poster" href="/movie/${m.id}" data-route aria-label="${e((m.title || m.original_title)+' · '+t('filmDetails'))}"><img src="${image(m.poster_path,'w500')}" alt="${e(m.title || m.original_title)}" width="500" height="750" decoding="async"><span class="hero-poster-open" aria-hidden="true">↗</span></a>`).join('');
  const links=[...stage.children],captionTitle=$('#hero-caption-title'),captionMeta=$('#hero-caption-meta');
  const activate=link=>{
    const index=links.indexOf(link);
    links.forEach((item,i)=>{
      item.classList.toggle('is-active',i===index);
      item.classList.toggle('is-before',index>=0 && i<index);
      item.classList.toggle('is-after',index>=0 && i>index);
    });
    const film=films[index];
    captionTitle.textContent=film ? film.title || film.original_title : t('posterHint');
    captionMeta.textContent=film ? [film.release_date?.slice(0,4),film.vote_average>0?'★ '+Number(film.vote_average).toFixed(1):'',t('filmDetails')+' →'].filter(Boolean).join(' · ') : t('posterRefresh');
  };
  for(const link of links){
    link.addEventListener('pointerenter',event=>{if(event.pointerType!=='touch')activate(link);});
    link.addEventListener('focus',()=>activate(link));
  }
  stage.onpointerleave=()=>activate(links.includes(document.activeElement)?document.activeElement:null);
  stage.onfocusout=event=>activate(links.includes(event.relatedTarget)?event.relatedTarget:stage.querySelector('.hero-poster:hover'));
  activate(null);
}
async function moviePage(id,view){
  $('#movie-dialog').close();$('#movie-content').replaceChildren();state.detail=null;
  $('#main').innerHTML=`<section class="movie-page"><a class="text-link movie-back" href="/" data-route>← ${t('backHome')}</a><div id="movie-page-content"><div class="status-line"><span class="spinner"></span></div></div></section>`;
  await movie(id,null,{container:$('#movie-page-content'),modal:false,view});
  if(view===state.view && state.detail?.id===id)document.title=state.detail.movie.title+' · MyMovieList';
}

async function discover(view){
  $('#main').innerHTML=`<div class="page-head"><h1>${t('discoverTitle')}</h1><p>${t('discoverp')}</p></div><div class="toolbar"><form id="search-form" class="search-box"><input name="query" placeholder="${t('search')}" aria-label="${t('search')}" value="${e(state.query)}" maxlength="200"><button aria-label="${t('searchButton')}">⌕</button></form><div class="tabs">${['trending','topRated','classics'].map(k=>`<button class="tab ${state.discover===k?'selected':''}" data-discover="${k}">${t(k==='trending'?'trendingTab':k)}</button>`).join('')}</div></div><div class="movie-grid" id="discover-grid"></div><div class="load-more"><button class="button secondary" id="load-more">${t('loadMore')}</button></div>`;
  await loadDiscover(view);
}
async function loadDiscover(view=state.view){
  const button=$('#load-more');if(button)button.disabled=true;
  let path=state.query ? 'search/movie?query='+encodeURIComponent(state.query) : state.discover==='trending' ? 'trending/movie/week?' : 'discover/movie?sort_by=vote_average.desc&vote_count.gte=1000&'+(state.discover==='classics' ? 'primary_release_date.lte='+(new Date().getFullYear()-10)+'-12-31&' : '');
  path+=(path.endsWith('?') || path.endsWith('&') ? '' : '&')+'language='+(state.lang==='tr'?'tr-TR':'en-US')+'&page='+state.page;
  try{
    const response=await api('catalog/'+path);if(view!==state.view)return;
    const films=(response.results || []).filter(m=>!m.adult);state.results=state.page===1 ? films : [...state.results,...films];
    const unique=[...new Map(state.results.map(m=>[m.id,m])).values()],work=await store.read(state.owner);
    $('#discover-grid').innerHTML=unique.length ? unique.map(m=>card(m,work)).join('') : `<div class="empty"><h2>${t('emptySearch')}</h2><p>${t('emptySearchp')}</p></div>`;
    for(const m of films)await store.cacheMetadata(state.lang+':'+m.id,m);
    if(button)button.hidden=state.page>=response.total_pages || !films.length;
  }catch(err){if(view===state.view)toast(errorText(err));}finally{if(button)button.disabled=false;}
}
async function library(view){
  const work=await store.read(state.owner),count=Object.values(work.entries).filter(x=>!x.data.deleted_at).length;
  const cards=await gridLibrary(work);if(view!==state.view)return;
  $('#main').innerHTML=`<div class="page-head"><div class="eyebrow">${count} ${t('filmCount')}</div><h1>${t('libraryTitle')}</h1><p>${t('libraryp')}</p><a class="text-link" href="/people" data-route>♡ ${t('favoritePeople')} →</a><div class="status-line ${state.error || store.pending(work) ? 'attention':''}"><span class="dot"></span><span id="sync-label">${syncLabel(work)}</span></div></div>${state.owner==='guest' ? `<div class="info-banner">${t('guestBanner')} <button class="quiet red" data-auth="signup">${t('signup')} →</button></div>` : ''}<div class="toolbar"><div class="tabs">${['all','watchlist','watched','favorites'].map(k=>`<button class="tab ${state.filter===k?'selected':''}" data-filter="${k}">${t(k)}</button>`).join('')}</div><div class="actions"><button class="quiet" data-action="export">${t('export')} ↗</button><label class="quiet import-label">${t('import')}<input type="file" id="import-file" accept="application/json,.json" hidden></label></div></div>${cards ? `<div class="movie-grid">${cards}</div>` : `<div class="empty"><h2>${t('emptyLibrary')}</h2><p>${t('emptyLibraryp')}</p><a class="button" href="/discover" data-route>${t('browse')} →</a></div>`}<div class="section"></div>`;
  hydrate(work,view);
}
async function hydrate(work,view){
  const targets=Object.values(work.entries).filter(e=>e.key.startsWith('tmdb:') && !e.data.deleted_at).slice(-24);
  for(const entry of targets){if(!navigator.onLine || view!==state.view)return;const id=Number(entry.key.split(':')[1]);if((await store.metadata(state.lang+':'+id))?.credits)continue;try{await catalog(id);}catch{return;}}
  if(view===state.view && targets.length && location.pathname==='/library'){
    const markup=await gridLibrary(await store.read(state.owner));const grid=$('#main .movie-grid');if(grid)grid.innerHTML=markup;
  }
}
function personalSummary(data){
  return e([t('status')+': '+t(data.status==='Watched'?'watched':'watchlist'),t('rating')+': '+(data.rating || t('unrated')),t('favorite')+': '+(data.favorite?'✓':'—'),t('watchedDate')+': '+(data.watched_date || '—'),...(data.deleted_at?[t('removed')]:[]),'',t('note')+':',data.note || '—'].join('\n'));
}
async function profilePage(view){
  if(!state.user){navigate('/library');auth('signin');return;}
  const work=await store.read(state.owner),active=Object.values(work.entries).filter(e=>!e.data.deleted_at),p=state.user.profile;
  const conflicts=Object.values(work.entries).filter(e=>e.conflict);
  let share=work.sharing,draft=work.showcase_draft;
  if(navigator.onLine)try{
    share=await api('profile/sharing-status',{});await store.mutate(state.owner,w=>{w.sharing=share;if(!w.showcase_draft && share.owner_settings)w.showcase_draft=share.owner_settings;});draft=(await store.read(state.owner)).showcase_draft;
  }catch{}
  if(view!==state.view)return;
  draft ||= {tmdb_ids:[],show_ratings:false,show_stats:false};
  const picks=await Promise.all(active.filter(e=>e.key.startsWith('tmdb:')).map(async entry=>{const id=Number(entry.key.split(':')[1]),m=await store.metadata(state.lang+':'+id);return `<button class="showcase-pick ${draft.tmdb_ids.includes(id)?'selected':''}" data-pick="${id}" aria-label="${e(m?.title || 'TMDB #'+id)}" aria-pressed="${draft.tmdb_ids.includes(id)}">${image(m?.poster_path) ? `<img src="${image(m.poster_path)}" alt="${e(m.title)}" loading="lazy">` : `<span class="poster-fallback">${id}</span>`}${draft.tmdb_ids.includes(id) ? `<span>${draft.tmdb_ids.indexOf(id)+1}</span>` : ''}</button>`;}));
  $('#main').innerHTML=`<div class="profile-header"><img src="/assets/avatars/${e(p.avatar_id)}.svg" alt=""><div><h1>${e(p.display_name || state.user.username || t('yourProfile'))}</h1><div class="handle">${state.user.username?'@'+e(state.user.username):''}</div></div><button class="button secondary small" data-action="edit-profile">${t('editProfile')}</button></div><div class="stat-row">${[[active.length,'all'],[active.filter(e=>e.data.status==='Watched').length,'watched'],[active.filter(e=>e.data.favorite).length,'favorites']].map(([n,k])=>`<div class="stat"><strong>${n}</strong><span>${t(k)}</span></div>`).join('')}</div><div class="status-line"><span class="dot"></span><span id="sync-label">${syncLabel(work)}</span></div><section class="settings-panel"><h2>${t('favoritePeople')}</h2><p>${t('peoplePrivate')}</p><a class="button secondary small" href="/people" data-route>♡ ${t('viewPeople')} →</a></section><section class="settings-panel"><h2>${t('showcase')}</h2><p>${t('showcaseP')}</p>${share?.owner_settings || draft.tmdb_ids.length || state.timed ? `<div class="showcase-picks">${picks.join('')}</div><label class="check-row"><input type="checkbox" id="share-public" ${share?.is_public?'checked':''}>${t('publicShowcase')}</label><label class="check-row"><input type="checkbox" id="share-ratings" ${draft.show_ratings?'checked':''}>${t('shareRatings')}</label><label class="check-row"><input type="checkbox" id="share-stats" ${draft.show_stats?'checked':''}>${t('shareStats')}</label><div class="actions"><button class="button small" data-action="save-showcase">${t('saveShowcase')}</button>${state.user.username?`<a class="quiet" href="/u/${e(state.user.username)}" target="_blank" rel="noopener">${t('viewShowcase')}</a>`:''}</div>` : `<p>${t('showcaseApp')}</p>${state.user.username?`<a class="text-link" href="/u/${e(state.user.username)}" target="_blank" rel="noopener">${t('viewShowcase')}</a>`:''}`}<p class="form-hint">${t('privateNotice')}</p></section><section class="settings-panel"><h2>${t('backupTitle')}</h2><p>${t('backupP')}</p><div class="actions"><button class="button secondary small" data-action="export">${t('export')}</button><label class="button secondary small import-label">${t('import')}<input type="file" id="import-file" accept="application/json,.json" hidden></label></div><div class="actions"><button class="quiet red" data-action="copy-guest">${t('guestCopy')}</button></div><p class="form-hint">${t('copyP')}</p><label class="check-row"><input type="checkbox" id="sync-enabled" ${work.enabled?'checked':''}>${t('enableSync')}</label></section>${conflicts.length?`<section class="settings-panel"><h2>${t('conflicts')}</h2><p>${t('conflictsP')}</p>${conflicts.map(c=>`<div class="conflict"><div class="conflict-cols"><div><strong>${t('localVersion')}</strong><pre>${personalSummary(c.data)}</pre><button class="button secondary small" data-resolve="local" data-key="${e(c.key)}" data-revision="${c.conflict.revision}">${t('keepLocal')}</button></div><div><strong>${t('cloudVersion')}</strong><pre>${personalSummary(c.conflict.remote)}</pre><button class="button secondary small" data-resolve="remote" data-key="${e(c.key)}" data-revision="${c.conflict.revision}">${t('keepRemote')}</button></div></div></div>`).join('')}<p>${t('historyNotice')}</p></section>`:''}<div class="actions"><button class="quiet red" data-action="signout">${t('signout')}</button></div><div class="section"></div>`;
}
async function updates(view){
  $('#main').innerHTML=`<div class="page-head"><h1>${t('updatesTitle')}</h1><p>${t('updatesP')}</p></div><div class="updates-list"><section class="update-entry"><div class="eyebrow">${t('latestRelease')}</div><h2 id="release-tag">MyMovieList</h2><div class="actions"><a class="button secondary small" href="https://github.com/keremakcn/MyMovieList/releases/latest" target="_blank" rel="noopener">${t('releaseLink')}</a></div></section><section class="update-entry"><span class="updates-status">${t('webBeta')}</span><h2>${t('webUpdate')}</h2><p>${t('webUpdateP')}</p></section><section class="update-entry"><span class="updates-status">${t('development')}</span><h2>${t('recommendUpdate')}</h2><ul>${['recommend1','recommend2','recommend3'].map(k=>`<li>${t(k)}</li>`).join('')}</ul><p class="form-hint">${t('developmentNote')}</p></section></div><div class="section"></div>`;
  try{const r=await api('releases');if(view===state.view && r.tag)$('#release-tag').textContent='MyMovieList '+r.tag;}catch{}
}
async function render(){
  const view=++state.view;const personRoute=/^\/person\/([1-9]\d{0,9})\/?$/.exec(location.pathname);const filmRoute=/^\/movie\/([1-9]\d{0,9})\/?$/.exec(location.pathname);header();document.title=(location.pathname==='/library'?t('library'):location.pathname==='/profile'?t('profile'):location.pathname==='/discover'?t('discover'):location.pathname==='/people'?t('favoritePeople'):'MyMovieList')+' · MyShelf';
  try{if(location.pathname==='/discover')await discover(view);else if(location.pathname==='/library')await library(view);else if(location.pathname==='/profile' || location.pathname==='/account')await profilePage(view);else if(location.pathname==='/updates')await updates(view);else if(personRoute)await personPage(Number(personRoute[1]),view);else if(location.pathname==='/people')await favoritePeople(view);else if(filmRoute)await moviePage(Number(filmRoute[1]),view);else await home(view);}catch(err){if(view===state.view)$('#main').innerHTML=`<div class="empty"><h2>MyMovieList</h2><p>${e(errorText(err))}</p><a class="button" href="/" data-route>${t('browse')}</a></div>`;}
}
function navigate(path){history.pushState({},'',path);window.scrollTo(0,0);render();}
function avatars(selected){return `<div class="avatar-grid">${avatarIds.map(id=>`<button type="button" class="avatar-option ${id===selected?'selected':''}" data-avatar="${id}" aria-label="${e(id.replace('cat-',''))}" aria-pressed="${id===selected}"><img src="/assets/avatars/${id}.svg" alt=""></button>`).join('')}</div>`;}
function field(label,name,type='text',value='',attrs=''){return `<label class="field">${t(label)}<input name="${name}" type="${type}" value="${e(value)}" required ${attrs}></label>`;}
function auth(flow,step='email'){state.auth={flow,step,email:'',avatar:'cat-luna'};authRender();$('#auth-dialog').showModal();}
function authRender(){
  const a=state.auth;let title,description,fields,submit;
  if(a.flow==='signin'){title='loginTitle';description='loginp';fields=field('email','email','email',a.email,'autocomplete="email" maxlength="254"')+field('password','password','password','','autocomplete="current-password" minlength="8" maxlength="512"');submit='signin';}
  else if(a.step==='email'){title=a.flow==='signup'?'signupTitle':'recoveryTitle';description=a.flow==='signup'?'signupP':'recoveryP';fields=field('email','email','email',a.email,'autocomplete="email" maxlength="254"')+(a.flow==='signup'?`<p class="form-hint">${t('signupDisclosure')}</p>`:'');submit='sendCode';}
  else if(a.step==='code'){title='verifyTitle';description='verifyP';fields=`<p class="form-hint">${e(a.email)}</p>`+field('code','code','text','','inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6,10}" maxlength="10"');submit='verify';}
  else if(a.step==='username'){title='usernameTitle';description='usernameP';fields=field('username','username','text','','autocomplete="username" pattern="[a-z][a-z0-9_]{2,23}" minlength="3" maxlength="24"')+`<p class="form-hint">${t('usernameHint')}</p>`;submit='continue';}
  else{title=a.flow==='signup'?'passwordTitle':'resetTitle';description=a.flow==='signup'?'passwordP':'resetP';fields=field('newPassword','password','password','','autocomplete="new-password" minlength="8" maxlength="512"')+field('confirmPassword','confirm','password','','autocomplete="new-password" minlength="8" maxlength="512"')+(a.flow==='signup'?field('displayName','display_name','text','','maxlength="40" autocomplete="nickname"')+`<p class="subheading">${t('avatar')}</p>`+avatars(a.avatar):'');submit=a.flow==='signup'?'createAccount':'updatePassword';}
  $('#auth-content').innerHTML=`<div class="auth-body">${a.flow!=='signin'?`<div class="steps">${['email','code','username','password'].filter(k=>a.flow==='signup' || k!=='username').map(k=>`<span class="${['email','code','username','password'].indexOf(k)<=['email','code','username','password'].indexOf(a.step)?'done':''}"></span>`).join('')}</div>`:''}<h1 id="auth-title">${t(title)}</h1><p>${t(description)}</p><form id="auth-form">${fields}<div class="form-error" id="auth-error" role="alert"></div><button class="button full" type="submit">${t(submit)} →</button></form><div class="auth-links">${a.flow==='signin'?`<button class="quiet" data-auth="recovery">${t('forgot')}</button><button class="quiet red" data-auth="signup">${t('signup')}</button>`:a.step==='code'?`<button class="quiet" data-action="resend">${t('resend')}</button><button class="quiet" data-auth="signin">${t('signin')}</button>`:`<button class="quiet" data-auth="signin">${t('alreadyAccount')} ${t('signin')}</button>`}</div></div>`;
  if(a.flow==='signup' && a.step==='password')$('#auth-form [name="display_name"]').required=false;
}
async function submitAuth(form){
  const a=state.auth,fd=new FormData(form),button=form.querySelector('[type=submit]');button.disabled=true;$('#auth-error').textContent='';
  try{
    if(a.flow==='signin'){
      await api('auth/signin',{email:fd.get('email'),password:fd.get('password')});await session();$('#auth-dialog').close();retryAt=0;queueSync();navigate('/library');
    }else if(a.step==='email'){
      a.email=fd.get('email');await api('auth/begin-'+(a.flow==='signup'?'signup':'recovery'),{email:a.email});a.step='code';authRender();
    }else if(a.step==='code'){
      const r=await api('auth/verify',{email:a.email,code:fd.get('code'),flow:a.flow});
      if(r.existing){a.flow='signin';a.step='email';authRender();$('#auth-error').textContent=t('existingAccount');}
      else{if(a.flow==='signup' && r.user_id)await store.pref('pending-guest-adoption',r.user_id);a.step=a.flow==='signup'?'username':'password';authRender();}
    }else if(a.step==='username'){
      const r=await api('auth/claim-username',{username:fd.get('username')});if(r.status==='taken')throw Error('usernameTaken');if(r.status==='locked' && r.username!==fd.get('username'))throw Error('usernameLocked');a.step='password';authRender();
    }else{
      if(fd.get('password')!==fd.get('confirm'))throw Error('passwordMismatch');
      if(a.flow==='signup'){
        if(!nameAllowed(fd.get('display_name') || ''))throw Error('invalid_fields');
        await api('auth/complete-signup',{password:fd.get('password'),profile:{display_name:fd.get('display_name') || '',avatar_id:a.avatar}});await session();$('#auth-dialog').close();retryAt=0;queueSync();navigate('/library');
      }else{await api('auth/reset-password',{password:fd.get('password')});a.flow='signin';a.step='email';authRender();$('#auth-error').textContent=t('passwordUpdated');}
    }
  }catch(err){$('#auth-error').textContent=errorText(err);}finally{if(button.isConnected)button.disabled=false;}
}
async function movie(id,key=null,{container=$('#movie-content'),modal=true,view}={}){
  const owner=state.owner,work=await store.read(owner);key ||= 'tmdb:'+id;
  const entry=work.entries[key];let m;
  if(key.startsWith('custom:'))m={id:null,title:entry.data.custom.title,release_date:String(entry.data.custom.year || ''),overview:''};
  else{try{m=await catalog(id);}catch(err){m=await store.metadata(state.lang+':'+id) || {id:Number(id),title:'TMDB #'+id};toast(errorText(err));}}
  if(owner!==state.owner || view!==undefined && view!==state.view || !container.isConnected)return;
  state.detail={id:m.id,key,owner,movie:m,initial:entry ? structuredClone(entry.data) : null};
  const d=entry && !entry.data.deleted_at ? entry.data : null;
  const people=(m.credits?.cast || []).slice(0,12),directors=(m.credits?.crew || []).filter(p=>p.job==='Director');
  container.innerHTML=`<div class="movie-detail"><div class="detail-side">${image(m.poster_path)?`<img class="detail-poster" src="${image(m.poster_path,'w500')}" alt="${e(m.title)}">`:`<div class="detail-poster poster-fallback">${e(m.title)}</div>`}${!d?`<button class="button" data-add="${Number(id)}">${t('add')} +</button>`:''}</div><div><h1 id="movie-title">${e(m.title)}</h1><div class="detail-meta"><span>${e(m.release_date?.slice(0,4) || '')}</span>${m.runtime?`<span>${m.runtime} ${t('minutes')}</span>`:''}${m.vote_average?`<span class="card-rating">★ ${Number(m.vote_average).toFixed(1)}</span>`:''}</div><div class="genre-tags">${(m.genres || []).map(g=>`<span class="genre-tag">${e(g.name)}</span>`).join('')}</div><p class="overview">${e(m.overview || t('noOverview'))}</p>${directors.length?`<h2 class="subheading">${t('director')}</h2><div class="people-row">${directors.map(p=>personCard(p,'director',work)).join('')}</div>`:''}${people.length?`<h2 class="subheading">${t('cast')}</h2><div class="people-row">${people.map(p=>personCard(p,'actor',work)).join('')}</div>`:''}${d?`<form id="detail-form" class="detail-form"><div class="detail-row"><label class="field">${t('status')}<select name="status"><option value="Watchlist" ${d.status==='Watchlist'?'selected':''}>${t('watchlist')}</option><option value="Watched" ${d.status==='Watched'?'selected':''}>${t('watched')}</option></select></label><label class="field">${t('rating')}<select name="rating"><option value="">${t('unrated')}</option>${Array.from({length:10},(_,i)=>`<option value="${i+1}" ${d.rating===i+1?'selected':''}>${i+1}/10</option>`).join('')}</select></label></div><label class="field">${t('watchedDate')}<input type="date" name="watched_date" value="${e(d.watched_date || '')}"></label><label class="field">${t('note')}<textarea name="note" maxlength="20000" placeholder="${t('notePlaceholder')}">${e(d.note || '')}</textarea></label><label class="check-row"><input type="checkbox" name="favorite" ${d.favorite?'checked':''}>${t('favorite')}</label><div class="actions"><button class="button small" type="submit">${t('save')}</button><button type="button" class="quiet" data-action="remove">${t('remove')}</button></div><p class="form-hint">${t('privateNotice')}</p></form>`:''}</div></div>`;
  await Promise.all([...people,...directors].filter(p=>Number.isSafeInteger(p.id)).map(p=>store.cacheMetadata('person:'+p.id,{id:p.id,name:p.name,profile_path:p.profile_path})));
  if(modal && !$('#movie-dialog').open)$('#movie-dialog').showModal();
}
function editProfile(){const p=state.user.profile;state.profileAvatar=p.avatar_id;$('#profile-content').innerHTML=`<div class="auth-body"><h1 id="profile-title">${t('editProfile')}</h1><p>${t('fixedUsername')}</p><div class="handle">@${e(state.user.username || '')}</div><form id="profile-form">${field('displayName','display_name','text',p.display_name,'maxlength="40" autocomplete="nickname"')}<p class="subheading">${t('avatar')}</p>${avatars(p.avatar_id)}<div class="form-error" id="profile-error" role="alert"></div><button class="button full">${t('save')}</button></form></div>`;$('#profile-form [name=display_name]').required=false;$('#profile-dialog').showModal();}
const heartIcon=selected=>`<svg viewBox="0 0 24 24" width="18" height="18" fill="${selected?'currentColor':'none'}" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M20.5 5.5a5 5 0 0 0-7 0L12 7l-1.5-1.5a5 5 0 0 0-7 7L12 21l8.5-8.5a5 5 0 0 0 0-7z"/></svg>`;
const personAction=(role,selected)=>t(role==='actor'?(selected?'removeActor':'addActor'):(selected?'removeDirector':'addDirector'));
function personButton(p,role,work,label=false){
  const selected=!!peopleState(work).entries[role+':'+p.id]?.data.favorite;
  return `<button type="button" class="person-heart ${selected?'selected':''}" data-person-favorite="${Number(p.id)}" data-person-role="${role}" data-person-name="${e(p.name)}" title="${t(role==='actor'?'favoriteActor':'favoriteDirector')}" data-owner="${e(state.owner)}" ${label?'data-favorite-label':''} aria-pressed="${selected}" aria-label="${e(personAction(role,selected)+' · '+p.name)}">${heartIcon(selected)}${label?`<span>${t(role==='actor'?'favoriteActor':'favoriteDirector')}</span>`:''}</button>`;
}
function personCard(p,role,work){return `<div class="person-card-wrap"><a class="person" href="/person/${Number(p.id)}" data-route>${image(p.profile_path,'w185')?`<img src="${image(p.profile_path,'w185')}" alt="" loading="lazy">`:`<span class="person-placeholder">${e(p.name?.[0] || '?')}</span>`}<strong>${e(p.name)}</strong></a>${personButton(p,role,work)}</div>`;}
async function personCatalog(id,credits=false){
  const key='person:'+state.lang+':'+id,cached=await store.metadata(key);
  if(cached && (cached.movie_credits || !credits))return cached;
  try{
    const person=await api(`catalog/person/${id}?language=${state.lang==='tr'?'tr-TR':'en-US'}${credits?'&append_to_response=movie_credits':''}`);
    if(person.id!==id)throw Error('invalid_response');
    await store.cacheMetadata(key,person);await store.cacheMetadata('person:'+id,{id,name:person.name,profile_path:person.profile_path});return person;
  }catch(error){const fallback=cached || await store.metadata('person:'+id);if(fallback)return fallback;throw error;}
}
async function favoritePeople(view){
  const owner=state.owner,work=await store.read(owner),entries=Object.values(peopleState(work).entries).filter(x=>x.data.favorite);
  const counts=Object.fromEntries(['actor','director'].map(role=>[role,entries.filter(x=>x.data.role===role).length]));
  const list=entries.filter(x=>x.data.role===peopleRole).sort((a,b)=>b.data.edited_at.localeCompare(a.data.edited_at) || a.data.person_id-b.data.person_id);
  const pages=Math.max(1,Math.ceil(list.length/24));peoplePageNumber=Math.min(peoplePageNumber,pages);
  const selected=list.slice((peoplePageNumber-1)*24,peoplePageNumber*24);
  const known=await Promise.all(selected.map(async x=>await store.metadata('person:'+state.lang+':'+x.data.person_id) || await store.metadata('person:'+x.data.person_id) || {id:x.data.person_id,name:'TMDB #'+x.data.person_id}));
  if(view!==state.view || owner!==state.owner)return;
  $('#main').innerHTML=`<div class="page-head"><div class="eyebrow">${t('profile')}</div><h1>${t('favoritePeople')}</h1><p>${t('peopleIntro')}</p><a class="text-link" href="${state.user?'/profile':'/library'}" data-route>← ${t(state.user?'profile':'library')}</a></div><div class="toolbar"><div class="tabs">${['actor','director'].map(role=>`<button class="tab ${peopleRole===role?'selected':''}" data-people-role="${role}">${t(role==='actor'?'favoriteActors':'favoriteDirectors')} <span>${counts[role]}</span></button>`).join('')}</div></div><p class="form-hint">${t('peoplePrivate')}</p>${Date.now()<peopleRetryAt?`<p class="form-hint">${t('peopleSyncWaiting')}</p>`:''}<div class="favorite-people-grid">${known.map(p=>personCard(p,peopleRole,work)).join('')}</div>${!known.length?`<div class="empty"><p>${t('peopleEmpty')}</p><a class="button secondary" href="/discover" data-route>${t('browse')}</a></div>`:''}${pages>1?`<div class="actions people-pagination">${peoplePageNumber>1?`<button class="button secondary small" data-people-page="${peoplePageNumber-1}">${t('previousPage')}</button>`:''}<span>${peoplePageNumber} / ${pages}</span>${peoplePageNumber<pages?`<button class="button secondary small" data-people-page="${peoplePageNumber+1}">${t('nextPage')}</button>`:''}</div>`:''}<div class="section"></div>`;
  // Hydrate just the visible page; no unbounded background catalog downloads.
  if(navigator.onLine){
    for(let n=0;n<known.length;n+=4){
      if(view!==state.view || owner!==state.owner)return;
      const targets=known.slice(n,n+4).filter(p=>p.name.startsWith('TMDB #'));
      const results=await Promise.allSettled(targets.map(p=>personCatalog(p.id)));
      if(view!==state.view || owner!==state.owner)return;
      for(const result of results)if(result.status==='fulfilled'){
        const p=result.value,card=$(`.favorite-people-grid a[href="/person/${p.id}"]`)?.parentElement;
        if(card)card.outerHTML=personCard(p,peopleRole,await store.read(owner));
      }
      if(results.some(r=>r.status==='rejected'))break;
    }
  }
}
async function personPage(id,view){
  const owner=state.owner,work=await store.read(owner),p=await personCatalog(id,true),credits=p.movie_credits || {};
  if(view!==state.view || owner!==state.owner)return;
  const roles=[...(credits.cast?.length || p.known_for_department==='Acting'?['actor']:[]),...(credits.crew?.some(x=>x.job==='Director') || p.known_for_department==='Directing'?['director']:[])];
  const films=[...new Map([...(credits.cast || []),...(credits.crew || [])].filter(m=>m.id && !m.adult).sort((a,b)=>(b.popularity || 0)-(a.popularity || 0)).map(m=>[m.id,m])).values()].slice(0,48);
  document.title=p.name+' · MyShelf';
  $('#main').innerHTML=`<a class="text-link" href="/people" data-route>← ${t('favoritePeople')}</a><section class="person-profile">${image(p.profile_path,'w185')?`<img src="${image(p.profile_path,'w185')}" alt="${e(p.name)}">`:`<span class="person-placeholder">${e(p.name?.[0] || '?')}</span>`}<div><h1>${e(p.name)}</h1><div class="actions">${roles.map(role=>personButton(p,role,work,true)).join('')}</div>${p.biography?`<details class="person-biography"><summary>${t('biography')}</summary><p>${e(p.biography)}</p></details>`:''}</div></section><p class="form-hint">${t('peoplePrivate')}</p><h2 class="section-title">${t('filmography')}</h2><div class="movie-grid">${films.map(m=>card(m,work)).join('')}</div><div class="section"></div>`;
}
function refreshPersonButtons(work){
  document.querySelectorAll('[data-person-favorite]').forEach(button=>{
    if(button.dataset.owner!==state.owner)return;
    const selected=!!peopleState(work).entries[button.dataset.personRole+':'+button.dataset.personFavorite]?.data.favorite;
    button.setAttribute('aria-pressed',String(selected));button.classList.toggle('selected',selected);
    button.innerHTML=heartIcon(selected)+(button.dataset.favoriteLabel!==undefined?`<span>${t(button.dataset.personRole==='actor'?'favoriteActor':'favoriteDirector')}</span>`:'');
    button.setAttribute('aria-label',personAction(button.dataset.personRole,selected)+' · '+button.dataset.personName);
  });
}
async function syncPeople(owner){
  if(Date.now()<peopleRetryAt)return;
  try{
    for(let n=0;n<20;n++){
      if(owner!==state.owner)return;
      const op=await peopleStore.next(owner);if(!op)break;
      const reply=await api('people/push',{operation:op},owner);await peopleStore.acknowledge(owner,op,reply);
    }
    if(Object.values(peopleState(await store.read(owner)).entries).some(e=>e.outbox)){queueSync();return;}
    for(let n=0;n<10;n++){
      if(owner!==state.owner)return;
      const work=await store.read(owner),page=await api('people/pull',{cursor:peopleState(work).cursor},owner);
      await peopleStore.page(owner,page);if(page.changes.length<100)break;
    }
    peopleRetryAt=0;if(owner===state.owner)refreshPersonButtons(await store.read(owner));
  }catch(error){if(['sign_in_required','account_changed'].includes(error.code))throw error;peopleRetryAt=Date.now()+60000;}
}
async function updateStatus(){const label=$('#sync-label');if(label)label.textContent=syncLabel(await store.read(state.owner));}
function queueSync(){clearTimeout(syncTimer);syncTimer=setTimeout(()=>runSync(),650);}
async function runSync(){
  if(state.owner==='guest' || !navigator.onLine || state.syncing || Date.now()<retryAt)return;
  const owner=state.owner;
  const work=await store.read(owner);if(!work.enabled && work.share_outbox?.action!=='unpublish')return;
  const run=async()=>{
    if(owner!==state.owner)return;state.syncing=true;await updateStatus();
    try{
      const start=Date.now(),timing=await api('status',undefined,owner);state.timed=timing.field_sync===true;
      await store.mutate(owner,w=>w.clock_offset=Date.parse(timing.server_time)-(start+Date.now())/2);
      if(work.enabled){
        for(let n=0;n<20;n++){
          if(owner!==state.owner)return;
          const op=await store.next(owner);if(!op)break;
          const reply=await api('sync/push',{operation:op,timed:state.timed},owner);
          if(reply.record_key!==op.record_key)throw Error('invalid_response');
          if(reply.status==='applied')await store.acknowledge(owner,op,reply.revision);
          else if(reply.status==='conflict')await store.reject(owner,op,reply.remote);
          else throw Error('invalid_response');
        }
        if(Object.values((await store.read(owner)).entries).some(e=>e.outbox)){queueSync();return;}
        for(let n=0;n<10;n++){
          if(owner!==state.owner)return;
          const current=await store.read(owner),page=await api('sync/pull',{cursor:current.cursor,timed:state.timed},owner);await store.page(owner,page);if(page.changes.length<100)break;
        }
      }
      if(work.enabled)await syncPeople(owner);
      let current=await store.read(owner);
      if(current.profile_pending && work.enabled){
        const frozen=current.profile_pending;await api('profile/update',{profile:frozen.profile},owner);
        await store.mutate(owner,w=>{if(w.profile_pending?.id===frozen.id)w.profile_pending=null;});
      }
      current=await store.read(owner);
      if(current.share_outbox && (work.enabled || current.share_outbox.action==='unpublish') && (!store.pending(current) || current.share_outbox.action==='unpublish')){
        const frozen=current.share_outbox,reply=await api('profile/share',frozen,owner);
        if(!['applied','conflict'].includes(reply.status))throw Error('invalid_response');
        await store.mutate(owner,w=>{w.sharing={...reply.settings,owner_settings:w.showcase_draft};if(w.share_outbox?.operation_id===frozen.operation_id)w.share_outbox=null;});
        if(reply.status==='conflict')toast(t('privacyChanged'));
      }
      state.error=null;failures=0;retryAt=0;
      if(owner===state.owner && ['/library','/profile','/people'].includes(location.pathname))await render();
      if(store.pending(await store.read(owner)) || Date.now()>=peopleRetryAt && peoplePending(await store.read(owner)))queueSync();
    }catch(err){state.error=err.code || err.message;failures++;retryAt=Date.now()+Math.min(1800000,30000*2**Math.min(failures-1,5));}
    finally{state.syncing=false;await updateStatus();}
  };
  if(navigator.locks)await navigator.locks.request('myshelf-sync:'+owner,{ifAvailable:true},lock=>lock?run():undefined);else await run();
}
async function click(event){
  const button=event.target.closest('button,a,label');if(!button)return;
  if(button.dataset.route!==undefined && button.origin===location.origin){if(event.button!==0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)return;event.preventDefault();for(const d of document.querySelectorAll('dialog[open]'))d.close();navigate(button.pathname);return;}
  if(button.dataset.auth){if($('#auth-dialog').open)$('#auth-dialog').close();auth(button.dataset.auth);return;}
  if(button.dataset.close){$('#'+button.dataset.close).close();return;}
  if(button.dataset.personFavorite){
    const owner=state.owner,id=Number(button.dataset.personFavorite),role=button.dataset.personRole;
    if(button.dataset.owner!==owner)throw Error('account_changed');
    button.disabled=true;
    try{
      await peopleStore.editPerson(owner,id,role,button.getAttribute('aria-pressed')!=='true');
      if(owner!==state.owner)return;
      const work=await store.read(owner),selected=!!peopleState(work).entries[role+':'+id]?.data.favorite;
      document.querySelectorAll(`[data-person-favorite="${id}"][data-person-role="${role}"]`).forEach(b=>{b.setAttribute('aria-pressed',String(selected));b.classList.toggle('selected',selected);b.innerHTML=heartIcon(selected)+(b.dataset.favoriteLabel!==undefined?`<span>${t(role==='actor'?'favoriteActor':'favoriteDirector')}</span>`:'');b.setAttribute('aria-label',personAction(role,selected)+' · '+b.dataset.personName);});
      queueSync();toast(t(selected?'personAdded':'personRemoved'));
      if(location.pathname==='/people')await render();
    }finally{if(button.isConnected)button.disabled=false;}return;
  }
  if(button.dataset.peopleRole){peopleRole=button.dataset.peopleRole;peoplePageNumber=1;await render();return;}
  if(button.dataset.peoplePage){peoplePageNumber=Number(button.dataset.peoplePage);await render();return;}
  if(button.dataset.movie){await movie(Number(button.dataset.movie));return;}
  if(button.dataset.custom){await movie(null,button.dataset.custom);return;}
  if(button.dataset.add){
    const id=Number(button.dataset.add),owner=state.owner;button.disabled=true;
    try{await store.add(owner,id);catalog(id).catch(()=>{});toast(t('added'));queueSync();if($('#movie-dialog').open && state.detail?.id===id)await movie(id);else await render();}finally{button.disabled=false;}return;
  }
  if(button.dataset.filter){state.filter=button.dataset.filter;await render();return;}
  if(button.dataset.discover){state.discover=button.dataset.discover;state.query='';state.page=1;await render();return;}
  if(button.dataset.avatar){const id=button.dataset.avatar;if(!avatarIds.includes(id))return;if(button.closest('#profile-dialog'))state.profileAvatar=id;else state.auth.avatar=id;button.parentElement.querySelectorAll('button').forEach(b=>{b.classList.toggle('selected',b.dataset.avatar===id);b.setAttribute('aria-pressed',b.dataset.avatar===id);});return;}
  if(button.dataset.pick){
    const id=Number(button.dataset.pick),work=await store.read(state.owner),picks=[...(work.showcase_draft?.tmdb_ids || [])];
    if(picks.includes(id))picks.splice(picks.indexOf(id),1);else if(picks.length<6)picks.push(id);else{toast(t('chooseSix'));return;}
    await store.mutate(state.owner,w=>w.showcase_draft={...(w.showcase_draft || {show_ratings:false,show_stats:false}),tmdb_ids:picks});
    const settings={is_public:$('#share-public')?.checked,ratings:$('#share-ratings')?.checked,stats:$('#share-stats')?.checked};await render();if($('#share-public')){$('#share-public').checked=settings.is_public;$('#share-ratings').checked=settings.ratings;$('#share-stats').checked=settings.stats;}return;
  }
  if(button.dataset.resolve){await store.resolve(state.owner,button.dataset.key,button.dataset.resolve,Number(button.dataset.revision));queueSync();await render();return;}
  if(button.id==='load-more'){state.page++;await loadDiscover();return;}
  if(button.id==='language'){state.lang=state.lang==='tr'?'en':'tr';localStorage.setItem('myshelf-language',state.lang);translateShell();await render();if($('#movie-dialog').open)await movie(state.detail.id,state.detail.key);return;}
  const action=button.dataset.action;
  if(action==='profile'){navigate('/profile');}
  else if(action==='edit-profile')editProfile();
  else if(action==='resend'){button.disabled=true;try{await api('auth/begin-'+(state.auth.flow==='signup'?'signup':'recovery'),{email:state.auth.email});toast(t('sendCode'));}finally{button.disabled=false;}}
  else if(action==='signout'){
    await api('auth/signout',{});state.user=null;state.owner='guest';state.error=null;await store.pref('last-account',null);navigate('/');header();
  }else if(action==='export'){
    const doc=await store.exportLibrary(state.owner),url=URL.createObjectURL(new Blob([JSON.stringify(doc,null,2)],{type:'application/json'})),link=document.createElement('a');link.href=url;link.download='MyMovieList-library.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast(t('exported'));
  }else if(action==='copy-guest'){await store.copyGuest(state.owner);toast(t('copied'));queueSync();await render();}
  else if(action==='remove'){
    const {owner,key}=state.detail;if(owner!==state.owner)throw Error('account_changed');await store.edit(owner,key,{deleted_at:iso()});$('#movie-dialog').close();toast(t('removed'));state.undo={owner,key};$('#toast').appendChild(Object.assign(document.createElement('button'),{textContent:' '+t('undo'),className:'quiet red'})).dataset.action='undo';queueSync();await render();
  }else if(action==='undo' && state.undo?.owner===state.owner){await store.edit(state.owner,state.undo.key,{deleted_at:null});state.undo=null;queueSync();await render();toast(t('savedChanges'));}
  else if(action==='save-showcase'){
    const current=await store.read(state.owner),publish=$('#share-public').checked,draft={...state.user.profile,tmdb_ids:current.showcase_draft?.tmdb_ids || [],show_ratings:$('#share-ratings').checked,show_stats:$('#share-stats').checked};
    const action=publish ? (current.sharing?.is_public?'update':'publish') : 'unpublish';
    await store.mutate(state.owner,w=>{w.showcase_draft=draft;w.share_outbox={operation_id:crypto.randomUUID(),expected_revision:w.sharing?.revision || 0,action,payload:action==='unpublish'?{}:draft};});toast(t('sharePending'));queueSync();
  }
}
document.addEventListener('click',event=>click(event).catch(err=>toast(errorText(err))));
document.addEventListener('submit',async event=>{
  const form=event.target;event.preventDefault();
  try{
    if(form.id==='auth-form'){await submitAuth(form);return;}
    if(form.id==='search-form'){state.query=new FormData(form).get('query').trim();state.page=1;await loadDiscover();return;}
    if(form.id==='detail-form'){
      if(state.detail.owner!==state.owner)throw Error('account_changed');const data=new FormData(form);
      const submitted={status:data.get('status'),rating:data.get('rating')?Number(data.get('rating')):null,note:data.get('note') || null,favorite:data.has('favorite'),watched_date:data.get('watched_date') || null};
      const changed=Object.fromEntries(Object.entries(submitted).filter(([k,v])=>!equal(v,state.detail.initial?.[k])));
      await store.edit(state.owner,state.detail.key,changed);Object.assign(state.detail.initial,changed);toast(t('savedChanges'));queueSync();await render();
    }else if(form.id==='profile-form'){
      const p={display_name:new FormData(form).get('display_name').trim(),avatar_id:state.profileAvatar};
      if(!nameAllowed(p.display_name))throw Error('invalid_fields');
      await store.mutate(state.owner,w=>{w.profile_pending={id:crypto.randomUUID(),profile:p};if(w.sharing?.is_public && w.showcase_draft)w.share_outbox={operation_id:crypto.randomUUID(),expected_revision:w.sharing.revision,action:'update',payload:{...w.showcase_draft,...p}};});
      state.user.profile=p;await store.pref('last-account',state.user);header();$('#profile-dialog').close();queueSync();await render();toast(t('savedChanges'));
    }
  }catch(err){toast(errorText(err));}
});
document.addEventListener('change',async event=>{
  try{if(event.target.id==='import-file'){
    const file=event.target.files[0];if(!file)return;if(file.size>8*1024*1024)throw Error('invalid_import');const doc=JSON.parse(await file.text());await store.importLibrary(state.owner,doc);queueSync();await render();toast(t('imported'));
  }else if(event.target.id==='sync-enabled'){await store.mutate(state.owner,w=>w.enabled=event.target.checked);retryAt=0;queueSync();await updateStatus();}}catch(err){toast(errorText(err));}
});
document.addEventListener('error',event=>{if(event.target instanceof HTMLImageElement){const img=event.target;if(img.closest('.poster-open')){img.replaceWith(Object.assign(document.createElement('span'),{className:'poster-fallback',textContent:img.alt}));}else if(img.closest('.hero-poster')){img.replaceWith(Object.assign(document.createElement('span'),{className:'hero-poster-fallback',textContent:img.alt}));}else if(img.closest('.person')){img.replaceWith(Object.assign(document.createElement('span'),{className:'person-placeholder',textContent:img.alt[0] || '?'}));}}},true);
window.addEventListener('popstate',()=>{for(const d of document.querySelectorAll('dialog[open]'))d.close();render();});window.addEventListener('online',()=>{retryAt=0;queueSync();updateStatus();});window.addEventListener('offline',updateStatus);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'){queueSync();refreshHero().catch(()=>{});}});
setInterval(()=>{if(document.visibilityState==='visible')runSync();},30000);
setInterval(()=>{if(document.visibilityState==='visible')refreshHero().catch(()=>{});},60000);
translateShell();
try{
  await session();
}catch(err){
  if(err.status===401){state.user=null;state.owner='guest';await store.pref('last-account',null);}
  else{const last=await store.pref('last-account');if(last){state.user=last;state.owner=last.id;}state.error=err.code || 'cloud_unavailable';}
}
translateShell();await render();queueSync();
if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});
