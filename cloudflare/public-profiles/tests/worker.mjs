import assert from 'node:assert/strict';
import {test,afterEach} from 'node:test';
import worker,{validateProfile} from '../worker.mjs';
const id='11111111-1111-4111-8111-111111111111';
const sample=()=>({found:true,share_id:id,display_name:'<script>safe text</script>',avatar_id:'cat-lilac',films:[{tmdb_id:603,rating:9}]});
const env={SUPABASE_URL:'https://qiztpurcgtlfvvvjmpma.supabase.co',SUPABASE_PUBLISHABLE_KEY:'sb_publishable_test',PROFILE_LIMITER:{limit:async()=>({success:true})},ASSETS:{fetch:async()=>new Response('<html>shell</html>',{headers:{'Content-Type':'text/html'}})}};
const originalFetch=globalThis.fetch;
afterEach(()=>{globalThis.fetch=originalFetch;});
const response=(v,status=200)=>new Response(JSON.stringify(v),{status,headers:{'Content-Type':'application/json'}});
const request=(path='/api/profiles/'+id,options={})=>new Request('https://profiles.myshelf.cloud'+path,options);
test('strict public DTO rejects private fields, duplicates, unsafe avatars and wrong types',()=>{
 assert.deepEqual(validateProfile({found:false}),{found:false});
 for(const v of [{found:false,note:'private'}, {...sample(),email:'private'}, {...sample(),avatar_id:'../secret'},
  {...sample(),films:[{tmdb_id:603,note:'private'}]}, {...sample(),films:[{tmdb_id:603},{tmdb_id:603}]},
  {...sample(),films:[{tmdb_id:true}]}, {...sample(),counts:{total:1,watched:2,favorites:0,watchlist:0}}]) assert.throws(()=>validateProfile(v));
});
test('anonymous read sends only public key to fixed RPC; metadata comes from shared gateway',async()=>{
 const calls=[]; globalThis.fetch=async(url,options)=>{calls.push([url,options]);return url.includes('supabase.co')?response(sample()):response({id:603,title:'The Matrix',release_date:'1999-03-31',poster_path:'/poster.jpg'});};
 const r=await worker.fetch(request('/api/profiles/'+id+'?invalid'),env);assert.equal(r.status,404);assert.equal(calls.length,0);
 const result=await worker.fetch(request('/api/profiles/'+id+'?language=tr',{headers:{Authorization:'Bearer ATTACKER',Cookie:'private'}}),env);
 assert.equal(result.status,200);const v=await result.json();assert.equal(v.films[0].title,'The Matrix');
 assert.equal(calls.length,2);assert.equal(calls[0][0],env.SUPABASE_URL+'/rest/v1/rpc/mml_public_profile');
 assert.deepEqual(calls[0][1].headers,{apikey:'sb_publishable_test','Content-Type':'application/json'});
 assert.deepEqual(JSON.parse(calls[0][1].body),{p_share_id:id});
 assert.equal(calls[0][1].redirect,'manual');assert.equal(result.headers.get('Cache-Control'),'no-store');
 assert.equal(result.headers.get('X-Robots-Tag'),'noindex, nofollow');
});
test('private and missing profiles return the same anonymous response and never load films',async()=>{
 let calls=0;globalThis.fetch=async()=>{calls++;return response({found:false});};
 const r=await worker.fetch(request(),env);assert.equal(r.status,404);assert.deepEqual(await r.json(),{found:false});assert.equal(calls,1);
});
test('revocation is re-read on every request, including after public success',async()=>{
 let visible=true,calls=0;globalThis.fetch=async url=>{if(url.includes('supabase.co')){calls++;return response(visible?sample():{found:false});}return response({id:603,title:'Movie'});};
 assert.equal((await worker.fetch(request(),env)).status,200);visible=false;
 assert.equal((await worker.fetch(request(),env)).status,404);assert.equal(calls,2);
});
test('no arbitrary target, authenticated RPC, method or static file can be proxied',async()=>{
 globalThis.fetch=async()=>{throw Error('Must not fetch');};
 for(const path of ['/api/profiles/'+id+'?url=https://attacker.test','/api/profiles/not-uuid','/rest/v1/mml_library','/worker.mjs','/avatars/secret.svg'])assert.equal((await worker.fetch(request(path),env)).status,404);
 assert.equal((await worker.fetch(request('/api/profiles/'+id,{method:'POST'}),env)).status,405);
 assert.equal((await worker.fetch(request('/api/profiles/'+id+'?language=xx'),env)).status,400);
});
test('limiter is required, rate exhaustion blocks provider calls',async()=>{
 globalThis.fetch=async()=>{throw Error('Must not fetch');};
 assert.equal((await worker.fetch(request(),{...env,PROFILE_LIMITER:null})).status,503);
 assert.equal((await worker.fetch(request(),{...env,PROFILE_LIMITER:{limit:async()=>({success:false})}})).status,429);
});
test('provider errors, redirects, large or untrusted JSON fail closed without leaked diagnostics',async()=>{
 for(const data of [response({error:'SECRET-UPSTREAM'},500),response({...sample(),note:'SECRET-NOTE'}),response({found:true,display_name:'x'.repeat(20000)}),new Response('redirect',{status:302})]){
  globalThis.fetch=async()=>data;const r=await worker.fetch(request(),env);assert.equal(r.status,503);assert.deepEqual(await r.json(),{error:'service_unavailable'});
 }
});
test('missing catalog metadata preserves profile and only public film ID',async()=>{
 globalThis.fetch=async url=>url.includes('supabase.co')?response(sample()):response({error:'quota'},429);
 const r=await worker.fetch(request(),env);assert.equal(r.status,200);const film=(await r.json()).films[0];assert.equal(film.title,'#603');assert.equal(film.poster_path,null);
});
test('shell and bundled avatars carry privacy headers; HEAD has no body',async()=>{
 for(const path of ['/u/'+id,'/app.js','/avatars/cat-lilac.svg']){
  const r=await worker.fetch(request(path),env);assert.equal(r.status,200);assert.equal(r.headers.get('Cache-Control'),'no-store');assert.ok(r.headers.get('Content-Security-Policy').includes("frame-ancestors 'none'"));
 }
 const head=await worker.fetch(request('/u/'+id,{method:'HEAD'}),env);assert.equal(await head.text(),'');
});
test('named profile uses the anonymous username RPC and rejects a mismatched projection',async()=>{
 const calls=[];
 globalThis.fetch=async(url,options)=>{calls.push([url,options]);return url.includes('supabase.co')?response({...sample(),username:'deniz'}):response({id:603,title:'Film'});};
 const r=await worker.fetch(request('/u/_api/DeNiZ'),env);assert.equal(r.status,200);
 assert.equal((await r.json()).username,'deniz');
 assert.equal(calls[0][0],env.SUPABASE_URL+'/rest/v1/rpc/mml_public_profile_by_username');
 assert.deepEqual(JSON.parse(calls[0][1].body),{p_username:'deniz'});
 assert.deepEqual(calls[0][1].headers,{apikey:'sb_publishable_test','Content-Type':'application/json'});
 globalThis.fetch=async()=>response({...sample(),username:'another_name'});
 assert.equal((await worker.fetch(request('/u/_api/deniz'),env)).status,503);
});
test('root-domain profile assets stay within /u and never expose source files',async()=>{
 const paths=[];const rootEnv={...env,ASSETS:{fetch:async r=>{paths.push(new URL(r.url).pathname);return new Response('asset');}}};
 for(const [path,asset] of [['/u/deniz','/index.html'],['/u/','/index.html'],['/u/_assets/app.js','/app.js'],['/u/_assets/avatars/cat-luna.svg','/avatars/cat-luna.svg']]){
  const r=await worker.fetch(new Request('https://myshelf.cloud'+path),rootEnv);
  assert.equal(r.status,200);assert.equal(paths.at(-1),asset);
 }
 for(const path of ['/u/_assets/worker.mjs','/u/_assets/avatars/private.svg','/u/_api/a','/u/_assets/private.sql'])assert.equal((await worker.fetch(request(path),rootEnv)).status,404);
});
test('named private profile still hides identity and never fetches movie metadata',async()=>{
 let calls=0;globalThis.fetch=async()=>{calls++;return response({found:false});};
 const r=await worker.fetch(request('/u/_api/deniz'),env);
 assert.equal(r.status,404);assert.deepEqual(await r.json(),{found:false});assert.equal(calls,1);
});
