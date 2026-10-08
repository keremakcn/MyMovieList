// Read-only public showcase site. No Auth sessions, personal writes or open proxy.
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const USERNAME = /^[a-z][a-z0-9_]{2,23}$/;
const AVATARS = new Set(['luna','cocoa','sunshine','sage','coral','cloud','midnight','peach','sky','mocha','lilac','mint','cherry','gold','ocean','silver'].map(x=>'cat-'+x));
const security = {
  'Cache-Control': 'no-store', 'X-Content-Type-Options':'nosniff',
  'Referrer-Policy':'no-referrer', 'X-Frame-Options':'DENY', 'X-Robots-Tag':'noindex, nofollow',
  'Content-Security-Policy': "default-src 'self'; img-src 'self' https://image.tmdb.org; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
};
const json = (value,status=200) => new Response(JSON.stringify(value),{status,headers:{...security,'Content-Type':'application/json; charset=utf-8'}});
const exact = (value,keys) => value && typeof value==='object' && !Array.isArray(value) && Object.keys(value).sort().join(',') === [...keys].sort().join(',');
const integer = (n,min=0,max=Number.MAX_SAFE_INTEGER) => Number.isSafeInteger(n) && n>=min && n<=max;
export function validateProfile(v) {
  if (exact(v,['found']) && v.found===false) return v;
  const fields=['found','share_id','display_name','avatar_id','films'];
  if ('username' in v) { if(typeof v.username!=='string' || !USERNAME.test(v.username))throw Error('Invalid username'); fields.push('username'); }
  if ((!exact(v,fields) && !exact(v,[...fields,'counts'])) || v.found!==true || !UUID.test(v.share_id) ||
      typeof v.display_name!=='string' || [...v.display_name].length>40 || /[\u0000-\u001f\u007f]/.test(v.display_name) ||
      !AVATARS.has(v.avatar_id) || !Array.isArray(v.films) || v.films.length>6) throw Error('Invalid projection');
  const seen=new Set();
  for (const film of v.films) {
    if ((!exact(film,['tmdb_id']) && !exact(film,['tmdb_id','rating'])) ||
        !integer(film.tmdb_id,1,9999999999) || seen.has(film.tmdb_id) ||
        ('rating' in film && !integer(film.rating,1,10))) throw Error('Invalid film');
    seen.add(film.tmdb_id);
  }
  if ('counts' in v && (!exact(v.counts,['total','watched','favorites','watchlist']) ||
    !Object.values(v.counts).every(n=>integer(n)) || v.counts.watched+v.counts.watchlist!==v.counts.total ||
    v.counts.favorites>v.counts.total)) throw Error('Invalid counts');
  return v;
}
async function bounded(response,limit) {
  if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) throw Error('Upstream unavailable');
  const reader=response.body.getReader(); let length=0; const chunks=[];
  try {
    for (;;) { const {value,done}=await reader.read(); if(done)break; length+=value.length;
      if(length>limit)throw Error('Response too large'); chunks.push(value); }
  } finally { await reader.cancel().catch(()=>{}); }
  const bytes=new Uint8Array(length); let offset=0;
  for (const part of chunks) { bytes.set(part,offset); offset+=part.length; }
  return JSON.parse(new TextDecoder().decode(bytes));
}
async function metadata(id,locale,env) {
  const url=`https://api.myshelf.cloud/3/movie/${id}?language=${locale==='tr'?'tr-TR':'en-US'}`;
  const key=new Request(url), cache=globalThis.caches?.default;
  try {
    let response=await cache?.match(key);
    if(!response) {
      response=await fetch(url,{redirect:'manual',signal:AbortSignal.timeout(8000)});
      const raw=await bounded(response,256*1024);
      if(raw.id!==id)throw Error('Wrong film');
      const title=locale==='tr' && ['tr','en'].includes(raw.original_language) ? raw.original_title || raw.title : raw.title;
      const value={title:typeof title==='string'?title.slice(0,300):'#'+id,
        year:/^\d{4}-/.test(raw.release_date||'')?Number(raw.release_date.slice(0,4)):null,
        poster_path:/^\/[\w.-]+\.(jpg|png|webp)$/.test(raw.poster_path||'')?raw.poster_path:null};
      if(cache)await cache.put(key,new Response(JSON.stringify(value),{headers:{'Content-Type':'application/json','Cache-Control':'public, max-age=3600'}}));
      return value;
    }
    return await response.json();
  } catch (_) { return {title:'#'+id,year:null,poster_path:null}; }
}
export default {
  async fetch(request,env) {
    const url=new URL(request.url);
    if(!['GET','HEAD'].includes(request.method))return json({error:'method_not_allowed'},405);
    let response;
    const match=url.pathname.match(/^\/(?:api\/profiles|u\/_api)\/([^/]+)$/);
    if(match) {
      const key=match[1].toLowerCase(), legacy=UUID.test(key);
      if((!legacy && !USERNAME.test(key)) || url.searchParams.size>1 || [...url.searchParams.keys()].some(k=>k!=='language'))return json({found:false},404);
      const locale=url.searchParams.get('language')||'en';
      if(!['en','tr'].includes(locale))return json({error:'invalid_language'},400);
      if(!env.PROFILE_LIMITER)return json({error:'service_unavailable'},503);
      let limited;
      try { limited=await env.PROFILE_LIMITER.limit({key:request.headers.get('CF-Connecting-IP')||'unknown'}); }
      catch (_) { return json({error:'service_unavailable'},503); }
      if(!limited.success)return json({error:'try_later'},429);
      try {
        // Fixed provider and RPC. Client-supplied URLs, keys and auth never forwarded.
        if(env.SUPABASE_URL!=='https://qiztpurcgtlfvvvjmpma.supabase.co' || !env.SUPABASE_PUBLISHABLE_KEY?.startsWith('sb_publishable_'))throw Error('Configuration');
        const upstream=await fetch(env.SUPABASE_URL+'/rest/v1/rpc/'+(legacy?'mml_public_profile':'mml_public_profile_by_username'),{
          method:'POST',redirect:'manual',signal:AbortSignal.timeout(8000),
          headers:{apikey:env.SUPABASE_PUBLISHABLE_KEY,'Content-Type':'application/json'},
          body:JSON.stringify(legacy?{p_share_id:key}:{p_username:key})
        });
        const value=validateProfile(await bounded(upstream,16384));
        if(!value.found)return json({found:false},404);
        if(legacy?value.share_id.toLowerCase()!==key:value.username!==key)throw Error('Wrong profile');
        // Read visibility on every visit, then fetch catalog metadata in groups of 3.
        const films=[];
        for(let i=0;i<value.films.length;i+=3) {
          films.push(...await Promise.all(value.films.slice(i,i+3).map(async film=>({...film,...await metadata(film.tmdb_id,locale,env)}))));
        }
        response=json({...value,films});
      } catch (_) { response=json({error:'service_unavailable'},503); }
    } else {
      const path=url.pathname.replace(/^\/u\/_assets\//,'/');
      const name=url.pathname.match(/^\/u\/([^/]+)$/)?.[1];
      const shell=url.pathname==='/' || url.pathname==='/u/' || (name && (UUID.test(name) || USERNAME.test(name.toLowerCase())));
      const avatar=path.match(/^\/avatars\/(cat-[a-z]+)\.svg$/);
      if(!shell && !['/app.js','/style.css','/logo.png'].includes(path) && !(avatar && AVATARS.has(avatar[1])))return json({found:false},404);
      if(!env.ASSETS)return json({error:'service_unavailable'},503);
      const asset=new URL(url); asset.pathname=shell?'/index.html':path; asset.search='';
      const result=await env.ASSETS.fetch(new Request(asset,{method:request.method}));
      response=new Response(result.body,result);
      for(const [key,value] of Object.entries(security))response.headers.set(key,value);
    }
    return request.method==='HEAD'?new Response(null,response):response;
  }
};
