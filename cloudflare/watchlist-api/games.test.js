import {test} from 'node:test';
import assert from 'node:assert/strict';
import worker from './worker.js';
import {rawgURL} from './games.js';

test('game catalog accepts only fixed endpoints and bounded parameters',()=>{
  for(const path of ['/rawg/games?search=Alien','/rawg/games/123','/rawg/developers?search=Valve','/rawg/publishers?search=Sony','/rawg/games?developers=12&page=2&page_size=40&ordering=-added']) {
    assert.equal(rawgURL(new URL('https://gateway.test'+path)).hostname,'api.rawg.io');
  }
  for(const path of ['/rawg/games?search=x&key=secret','/rawg/games?search=x&page=501','/rawg/games?search=x&search=y','/rawg/games?search=x&page_size=99','/rawg/games?url=https://evil.test','/rawg/games','/rawg/games/1?key=secret','/rawg/accounts','/rawg/developers?developers=1','/rawg/games?constructor=x']) {
    assert.equal(rawgURL(new URL('https://gateway.test'+path)),null,path);
  }
});

test('game gateway protects secrets, separates cache, preserves TMDB and handles failures',async()=>{
  const oldFetch=globalThis.fetch, oldCaches=globalThis.caches;
  const cache=new Map(), jobs=[];
  globalThis.caches={default:{match:async key=>cache.get(key.url)?.clone(),put:async (key,response)=>cache.set(key.url,response)}};
  const ctx={waitUntil:job=>jobs.push(job)};
  const credential='a'.repeat(32);
  const limiter={limit:async ()=>({success:true})};
  const env={RAWG_API_KEY:credential,CLIENT_LIMITER:limiter,RAWG_LIMITER:limiter};
  const request=()=>new Request('https://gateway.test/rawg/games?search=Alien',{headers:{'CF-Connecting-IP':'192.0.2.1',Authorization:'must-not-forward',Cookie:'private'}});
  try {
    assert.equal((await worker.fetch(request(),{},ctx)).status,503);
    assert.equal((await worker.fetch(request(),{...env,RAWG_DISABLED:'true'},ctx)).status,503);
    let calls=0;
    globalThis.fetch=async(url,options)=>{
      calls++;
      assert.equal(new URL(url).hostname,'api.rawg.io');
      assert.equal(new URL(url).searchParams.get('key'),credential);
      assert.equal(options.headers.Authorization,undefined);
      assert.equal(options.headers.Cookie,undefined);
      assert.equal(options.redirect,'manual');
      return Response.json({results:[{id:1,name:'Alien'}],next:`https://api.rawg.io/api/games?key=${credential}&page=2`,previous:null});
    };
    const first=await worker.fetch(request(),env,ctx);
    assert.equal(first.status,200);
    assert.deepEqual(await first.json(),{results:[{id:1,name:'Alien'}],next:true,previous:false});
    await Promise.all(jobs);
    assert.equal((await worker.fetch(request(),env,ctx)).status,200);
    assert.equal(calls,1);
    assert([...cache.keys()].every(key=>key.includes('/rawg/') && !key.includes(credential)));
    assert.equal((await worker.fetch(request(),{...env,CLIENT_LIMITER:{limit:async()=>({success:false})}},ctx)).status,429);
    cache.clear();
    assert.equal((await worker.fetch(request(),{...env,RAWG_LIMITER:{limit:async()=>({success:false})}},ctx)).status,429);
    for(const status of [401,403,429,500,302]){
      globalThis.fetch=async()=>new Response(credential,{status});
      const response=await worker.fetch(request(),env,ctx);
      assert.notEqual(response.status,200);
      assert(!(await response.text()).includes(credential));
    }
    globalThis.fetch=async()=>Response.json({wrong:'payload'});
    assert.equal((await worker.fetch(request(),env,ctx)).status,502);
    globalThis.fetch=async()=>{throw Error('private credential '+credential)};
    assert.equal((await worker.fetch(request(),env,ctx)).status,503);
    globalThis.fetch=async()=>Response.json({id:1});
    const tmdb=await worker.fetch(new Request('https://gateway.test/3/movie/1',{headers:{'CF-Connecting-IP':'192.0.2.1'}}),{...env,TMDB_TOKEN:'tmdb-test',UPSTREAM_LIMITER:limiter},ctx);
    assert.equal(tmdb.status,200);
  } finally {globalThis.fetch=oldFetch;globalThis.caches=oldCaches;}
});
