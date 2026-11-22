import {ALGORITHM_VERSION,validCandidate,buildProfile,profileFingerprint,rankCandidates,todayUTC} from './recommendation-model.mjs';
import {equal} from './sync-model.mjs';
const POOL_KEY='recommendation-public-catalog-v3',TTL=12*60*60*1000,LIMIT=1200;
const genres=['28|12','35|10749','18|36|10752|37|10770','878|14','16|10751','27|53','99|10402','80|9648'];
const languages=['ja','ko','fr','es','hi','tr','de','it'];
const integer=id=>Number.isInteger(id)&&id>0&&id<=9999999999;
export function publicMovie(raw){
  if(!raw || !integer(raw.id))return null;
  const result={id:raw.id,title:raw.title,original_title:raw.original_title || raw.title,
    release_date:raw.release_date || '',original_language:raw.original_language,
    poster_path:raw.poster_path,adult:!!raw.adult,vote_average:raw.vote_average ?? 0,vote_count:raw.vote_count ?? 0,
    genre_ids:Array.isArray(raw.genre_ids)?raw.genre_ids:(raw.genres || []).map(g=>g.id)};
  if(!validCandidate(result))return null;
  const people=list=>(Array.isArray(list)?list:[]).filter(p=>integer(p?.id)).map(p=>({id:p.id,name:p.name,profile_path:p.profile_path,popularity:typeof p.popularity==='number'&&Number.isFinite(p.popularity)?p.popularity:0}));
  result.entities={cast:people(raw.credits?.cast || raw.entities?.cast).slice(0,6),directors:people(raw.credits?.crew?.filter(p=>p.job==='Director') || raw.entities?.directors)};
  result.keyword_ids=(raw.keywords?.keywords || raw.keyword_ids || []).map(k=>typeof k==='object'?k?.id:k).filter(integer);
  result.collection_id=raw.belongs_to_collection?.id || raw.collection_id || null;
  result.features_complete=!!raw.keywords && !!raw.credits || raw.features_complete===true;
  return result;
}
const preferenceState=work=>work.recommendations ||= {history:{},dismissed:[]};
export function createRecommender(store,fetchCatalog,{online=()=>navigator.onLine,now=()=>Date.now()}={}){
  const sessions=new Map();
  async function feature(id,isCurrent){
    const cached=await store.metadata('recommendation-features:'+id);
    if(cached?.features_complete || !online())return cached;
    if(!isCurrent())throw Error('stale_view');
    const response=await fetchCatalog(`catalog/movie/${id}?language=en-US&append_to_response=credits,keywords`),value=publicMovie(response);
    if(value?.id!==id)throw Error('invalid_response');
    await store.cacheMetadata('recommendation-features:'+id,value);
    return value;
  }
  async function batchMetadata(keys){
    const unique=[...new Set(keys)];
    if(!unique.length)return {};
    if(store.metadataBatch)return store.metadataBatch(unique);
    const entries=await Promise.all(unique.map(async k=>[k,await store.metadata(k)]));
    return Object.fromEntries(entries);
  }
  async function enrich(rows,budget,isCurrent){
    let incomplete=0;
    const cached=await batchMetadata(rows.map(row=>'recommendation-features:'+row.id));
    const enriched=rows.map(row=>cached['recommendation-features:'+row.id] || row);
    const missing=enriched.filter(row=>!row.features_complete).slice(0,budget);
    if(online())for(let n=0;n<missing.length;n+=4){
      if(!isCurrent())throw Error('stale_view');
      const batch=await Promise.allSettled(missing.slice(n,n+4).map(row=>feature(row.id,isCurrent)));
      for(let i=0;i<batch.length;i++){
        const result=batch[i],id=missing[n+i].id;
        if(result.status==='fulfilled')enriched[enriched.findIndex(row=>row.id===id)]=result.value;
        else incomplete++;
      }
      if(batch.every(result=>result.status==='rejected'))break;
    }
    return {rows:enriched,incomplete};
  }
  async function candidatePool(refresh,isCurrent){
    const cached=await store.pref(POOL_KEY),valid=cached?.version===ALGORITHM_VERSION&&Array.isArray(cached.movies);
    const old=valid?cached.movies.filter(validCandidate).slice(-LIMIT):[];
    const fresh=valid&&cached.fetched_at<=now()&&now()-cached.fetched_at<TTL;
    if(!online() || fresh&&!refresh)return {rows:old,unavailable:!old.length};
    const page=Number.isInteger(cached?.next_page)?Math.max(1,Math.min(20,cached.next_page)):1,today=todayUTC();
    const base={language:'en-US',include_adult:'false',include_video:'false','vote_count.gte':'150','primary_release_date.lte':today,page:String(page),sort_by:'popularity.desc'};
    const jobs=genres.map(g=>({...base,with_genres:g}));
    jobs.push({...base,sort_by:'vote_average.desc','vote_count.gte':'1000','primary_release_date.lte':`${Number(today.slice(0,4))-10}-12-31`});
    jobs.push({...base,sort_by:'vote_average.desc',with_genres:'18|35|53|12','vote_count.gte':'30',page:String(Math.floor((page-1)/languages.length)+1),with_original_language:languages[(page-1)%languages.length]});
    const lists=[];let errors=0;
    for(let n=0;n<jobs.length;n+=4){
      if(!isCurrent())throw Error('stale_view');
      const results=await Promise.allSettled(jobs.slice(n,n+4).map(async params=>{
        const response=await fetchCatalog('catalog/discover/movie?'+new URLSearchParams(params));
        if(!Array.isArray(response.results))throw Error('invalid_response');return response.results.map(publicMovie).filter(Boolean);
      }));
      for(const r of results)if(r.status==='fulfilled')lists.push(r.value);else errors++;
      if(results.every(r=>r.status==='rejected'))break;
    }
    // Interleave fixed public sources before enriching. No personal seed/filter enters an API URL.
    const incoming=new Map();
    for(let i=0;i<Math.max(0,...lists.map(rows=>rows.length));i++)for(const rows of lists)if(rows[i]&&!incoming.has(rows[i].id))incoming.set(rows[i].id,rows[i]);
    const combined=[...old.filter(row=>!incoming.has(row.id)),...incoming.values()].slice(-LIMIT);
    if(!errors)await store.pref(POOL_KEY,{version:ALGORITHM_VERSION,movies:combined,next_page:page%20+1,fetched_at:now()});
    return {rows:combined,unavailable:!!errors};
  }
  async function libraryEvidence(work,lang,isCurrent){
    const active=Object.values(work.entries).filter(e=>!e.data.deleted_at);
    const tmdbIds=active.filter(e=>!e.data.custom).map(e=>Number(e.key.split(':')[1]));
    const meta=await batchMetadata(tmdbIds.flatMap(id=>['recommendation-features:'+id,'en:'+id,'tr:'+id,lang+':'+id]));
    const rows=active.map(entry=>{
      if(entry.data.custom)return {tmdb_id:null,title:entry.data.custom.title,year:entry.data.custom.year,genre:entry.data.custom.genre || '',rating:entry.data.rating,favorite:entry.data.favorite};
      const id=Number(entry.key.split(':')[1]);
      let publicData=meta['recommendation-features:'+id],fallback=meta['en:'+id] || meta['tr:'+id];
      publicData ||= publicMovie(fallback) || {id,title:'TMDB #'+id,genre_ids:[]};
      const display=meta[lang+':'+id];
      // Explicit personal projection: never copy a note, watch date, status or session into features/cache.
      return {...publicData,tmdb_id:id,title:display?.title || publicData.title,rating:entry.data.rating,favorite:entry.data.favorite};
    });
    const learning=rows.filter(row=>row.tmdb_id && (row.favorite || row.rating!=null));
    const enriched=await enrich(learning,12,isCurrent),features=new Map(enriched.rows.map(row=>[row.id,row]));
    return rows.map(row=>({...row,...features.get(row.id),tmdb_id:row.tmdb_id,
      title:row.title?.startsWith('TMDB #')?features.get(row.id)?.title || row.title:row.title,
      rating:row.rating,favorite:row.favorite}));
  }
  async function recommend(owner,{mode='balanced',lang='en',refresh=false,isCurrent=()=>true,progress=()=>{}}={}){
    let work=await store.read(owner);
    progress('profile');let profile=buildProfile(await libraryEvidence(work,lang,isCurrent)),fingerprint=profileFingerprint(profile);
    if(!isCurrent())throw Error('stale_view');
    let preferences=preferenceState(work);const key=owner+':'+mode;
    const exclusions=()=>new Set([...Object.keys(work.entries).filter(k=>k.startsWith('tmdb:')).map(k=>Number(k.slice(5))),...(preferences.dismissed || [])]);
    let excluded=exclusions();
    let current=sessions.get(key),unavailable=false;
    if(!current || refresh || current.picks.filter(m=>!excluded.has(m.id)).length<10){
      progress('catalog');const pool=await candidatePool(refresh,isCurrent);
      progress('details');const enriched=await enrich(pool.rows,24,isCurrent);
      unavailable=pool.unavailable || !!enriched.incomplete;
      if(!isCurrent())throw Error('stale_view');
      // A first cloud pull can finish while public metadata loads. Rank against
      // its latest library, so newly restored films never become suggestions.
      const latest=await store.read(owner);
      if(!equal(work.entries,latest.entries)){
        work=latest;profile=buildProfile(await libraryEvidence(work,lang,isCurrent));
        fingerprint=profileFingerprint(profile);preferences=preferenceState(work);excluded=exclusions();
        if(!isCurrent())throw Error('stale_view');
      }
      const previous=new Set(Object.values(preferences.history || {}).flat());
      for(const [savedKey,value] of sessions)if(savedKey.startsWith(owner+':'))for(const m of value.picks.slice(0,10))previous.add(m.id);
      const ranked=await rankCandidates(enriched.rows,profile,{excluded:[...excluded],mode,limit:Math.min(30,enriched.rows.length),previous:[...previous],seed:crypto.randomUUID()});
      if(!isCurrent())throw Error('stale_view');
      if(ranked.length && (!current || !unavailable))current={picks:ranked,fingerprint};
      current ||= {picks:[],fingerprint};sessions.set(key,current);
    }
    const results=current.picks.filter(m=>!excluded.has(m.id)).slice(0,10);
    await store.mutate(owner,w=>{
      const prefs=preferenceState(w),history=Array.isArray(prefs.history[mode])?prefs.history[mode]:[];
      prefs.history[mode]=[...history,...results.map(m=>m.id)].slice(-50);
    });
    const localized=[];
    for(let n=0;n<results.length;n+=4){
      if(!isCurrent())throw Error('stale_view');
      const batch=await Promise.all(results.slice(n,n+4).map(async raw=>{
        let m=await store.metadata(lang+':'+raw.id);
        if(lang==='tr' && m?.localized_language!=='tr' && online())try{
          const translated=await fetchCatalog(`catalog/movie/${raw.id}?language=tr-TR`);
          if(translated.id!==raw.id)throw Error('invalid_response');
          m={...translated,localized_language:'tr'};await store.cacheMetadata('tr:'+raw.id,m);
        }catch{}
        const title=lang==='tr'&&raw.original_language==='tr'?raw.original_title:m?.title || raw.title;
        return {...raw,title};
      }));
      localized.push(...batch);
    }
    return {movies:localized,profile,profile_changed:current.fingerprint!==fingerprint,unavailable};
  }
  async function dismiss(owner,id){if(!integer(id))throw Error('invalid_request');await store.mutate(owner,w=>{const preferences=preferenceState(w);preferences.dismissed=[...new Set([...preferences.dismissed,id])].slice(-10000);});}
  return {recommend,dismiss};
}
