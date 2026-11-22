export const LIBRARY_PAGE_SIZE=48;
export const LIBRARY_FILTERS=['all','favorites','watched','watchlist'];
export const LIBRARY_SORTS=['default','added_desc','added_asc','rating_desc','rating_asc','year_desc','year_asc','watched_desc','watched_asc','title_asc'];

// Turkish-safe, case- and diacritic-insensitive fold used for search and dedup (parity with storage.search_fold).
export function foldTitle(text){
  return String(text ?? '')
    .replace(/\u0131/g,'i')
    .replace(/\u0130/g,'i')
    .replace(/\u00df/g,'ss')
    .normalize('NFKD')
    .replace(/\p{M}/gu,'')
    .toLowerCase()
    .replace(/\s+/g,' ')
    .trim();
}

const fallbackLang=lang=>lang==='tr' ? 'en' : 'tr';
const orderKey=x=>String(x?.data?.order_key || '');
const byOrderDesc=(a,b)=>{
  const x=orderKey(a),y=orderKey(b);
  return x<y ? 1 : x>y ? -1 : 0;
};

export function tmdbIdOf(entry){
  const key=String(entry?.key || '');
  if(!key.startsWith('tmdb:'))return null;
  const id=Number(key.slice(5));
  return Number.isSafeInteger(id) && id>0 ? id : null;
}

function lookup(meta,key){
  if(!meta || typeof meta!=='object' || !Object.hasOwn(meta,key))return null;
  const value=meta[key];
  return value && typeof value==='object' ? value : null;
}

// Resolve cached TMDB metadata for an entry: `${lang}:${id}`, fallback language, `tmdb:${id}`, or bare id.
export function entryMetadata(entry,meta,lang='en'){
  const id=tmdbIdOf(entry);
  if(id===null)return null;
  return lookup(meta,lang+':'+id) || lookup(meta,fallbackLang(lang)+':'+id) || lookup(meta,'tmdb:'+id) || lookup(meta,String(id));
}

export function entryTitles(entry,meta,lang='en'){
  const custom=entry?.data?.custom;
  if(custom)return [custom.title].filter(Boolean);
  const id=tmdbIdOf(entry);
  if(id===null)return [];
  const titles=[];
  for(const m of [lookup(meta,lang+':'+id),lookup(meta,fallbackLang(lang)+':'+id),lookup(meta,'tmdb:'+id),lookup(meta,String(id))]){
    if(!m)continue;
    for(const t of [m.title,m.original_title,m.name])if(typeof t==='string' && t.trim())titles.push(t);
  }
  return titles;
}

export function entryTitle(entry,meta,lang='en'){
  const custom=entry?.data?.custom;
  if(custom)return String(custom.title || '');
  const m=entryMetadata(entry,meta,lang);
  return String(m?.title || m?.original_title || '');
}

export function entryYear(entry,meta,lang='en'){
  const custom=entry?.data?.custom;
  if(custom)return Number.isInteger(custom.year) ? custom.year : null;
  const m=entryMetadata(entry,meta,lang);
  const raw=String(m?.release_date || m?.year || '');
  const match=raw.match(/^(\d{4})/);
  return match ? Number(match[1]) : null;
}

function compareNullable(a,b,dir){
  const na=a===null || a===undefined || a==='',nb=b===null || b===undefined || b==='';
  if(na && nb)return 0;
  if(na)return 1;
  if(nb)return -1;
  if(a===b)return 0;
  return (a<b ? -1 : 1)*dir;
}

function sortEntries(list,sort,meta,lang){
  if(!LIBRARY_SORTS.includes(sort) || sort==='default')return list.sort(byOrderDesc);
  const [field,direction]=sort.split('_');
  const dir=direction==='asc' ? 1 : -1;
  if(field==='title'){
    const collator=new Intl.Collator(lang==='tr' ? 'tr' : 'en',{sensitivity:'base',numeric:true});
    const titles=new Map(list.map(x=>[x,entryTitle(x,meta,lang).trim()]));
    return list.sort((a,b)=>{
      const x=titles.get(a),y=titles.get(b);
      if(!x || !y){
        if(x!==y)return x ? -1 : 1;
        return byOrderDesc(a,b);
      }
      return collator.compare(x,y) || byOrderDesc(a,b);
    });
  }
  let value;
  if(field==='added')value=x=>x.data.added_at || orderKey(x) || null;
  else if(field==='rating')value=x=>Number.isInteger(x.data.rating) ? x.data.rating : null;
  else if(field==='year'){
    const years=new Map(list.map(x=>[x,entryYear(x,meta,lang)]));
    value=x=>years.get(x);
  }
  else value=x=>x.data.watched_date || null;
  return list.sort((a,b)=>{
    if(field==='added'){
      // Added order is defined by the monotonic order_key; fall back to added_at only if missing.
      const x=orderKey(a),y=orderKey(b);
      if(x && y)return x===y ? 0 : (x<y ? -1 : 1)*dir;
    }
    return compareNullable(value(a),value(b),dir) || byOrderDesc(a,b);
  });
}

function normalizeOptions(filterOrOptions,meta){
  if(filterOrOptions && typeof filterOrOptions==='object'){
    const o=filterOrOptions;
    return {filter:o.filter ?? 'all',query:o.query ?? '',sort:o.sort ?? 'default',meta:o.meta ?? meta ?? {},lang:o.lang ?? 'en'};
  }
  return {filter:filterOrOptions ?? 'all',query:'',sort:'default',meta:meta ?? {},lang:'en'};
}

export function selectLibraryEntries(entries,filterOrOptions='all',meta=null){
  const {filter,query,sort,meta:metadata,lang}=normalizeOptions(filterOrOptions,meta);
  let active=Object.values(entries || {}).filter(x=>x && x.data && !x.data.deleted_at);
  if(filter==='favorites')active=active.filter(x=>x.data.favorite);
  else if(filter==='watched')active=active.filter(x=>x.data.status==='Watched');
  else if(filter==='watchlist')active=active.filter(x=>x.data.status==='Watchlist');
  const needle=foldTitle(query);
  if(needle)active=active.filter(x=>entryTitles(x,metadata,lang).some(t=>foldTitle(t).includes(needle)));
  return sortEntries(active,sort,metadata,lang);
}

export function sliceLibrary(entries,options={}){
  const {filter='all',query='',sort='default',meta={},lang='en',page=1,pageSize=LIBRARY_PAGE_SIZE}=options || {};
  const selected=selectLibraryEntries(entries,{filter,query,sort,meta,lang});
  const total=selected.length;
  const safeSize=Number.isInteger(pageSize) && pageSize>0 ? pageSize : LIBRARY_PAGE_SIZE;
  const safePage=Number.isInteger(page) && page>0 ? page : 1;
  const limit=Math.min(total,safePage*safeSize);
  const items=selected.slice(0,limit);
  return {items,shown:items.length,total,hasMore:items.length<total,page:safePage,pageSize:safeSize};
}

export function libraryMetadataKeys(items,lang='en'){
  const fallback=fallbackLang(lang);
  const keys=[];
  for(const x of items || []){
    if(x?.data?.custom)continue;
    const id=Number(String(x.key).split(':')[1]);
    keys.push(lang+':'+id,fallback+':'+id);
  }
  return keys;
}
