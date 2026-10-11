import assert from 'node:assert/strict';
import {test} from 'node:test';
import worker,{seal} from '../worker.mjs';

const A='aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa',B='bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb';
const env={SESSION_SECRET:'11'.repeat(32),SUPABASE_URL:'https://example.supabase.co',SUPABASE_PUBLISHABLE_KEY:'sb_publishable_test',AUTH_LIMITER:{limit:async()=>({success:true})},API_LIMITER:{limit:async()=>({success:true})},ASSETS:{fetch:async()=>new Response('<html>public shell</html>',{headers:{'Content-Type':'text/html'}})}};
const auth={user:{id:A,email:'a@example.test',user_metadata:{mml_registration:'pending-v1'}},access_token:'PRIVATE-ACCESS',refresh_token:'PRIVATE-REFRESH',expires_in:3600};
const data={status:'Watchlist',rating:null,note:'PRIVATE NOTE',favorite:false,watched_date:null,added_at:'2026-10-09T10:00:00.000000+00:00',order_key:'00000000000000000001:'+A,deleted_at:null,custom:null};
async function mock(run,handler){const original=globalThis.fetch,calls=[];globalThis.fetch=async(url,options={})=>{calls.push({url:String(url),options});return handler(String(url),options,calls);};try{return await run(calls);}finally{globalThis.fetch=original;}}
function request(path,body={},headers={}){return new Request('https://myshelf.cloud/api/'+path,{method:'POST',headers:{'Content-Type':'application/json',Origin:'https://myshelf.cloud','X-MyShelf-Client':'web-v1',...headers},body:JSON.stringify(body)});}
const ok=v=>new Response(JSON.stringify(v),{headers:{'Content-Type':'application/json'}});
function value(s={}){return {user_id:A,email:'a@example.test',access:'PRIVATE-ACCESS',refresh:'PRIVATE-REFRESH',expires:Date.now()+3600000,deadline:Date.now()+86400000,...s};}
async function sessionCookie(s={}){return '__Host-myshelf_session='+await seal(env,value(s),'session');}

test('cross-origin mutations and GET writes are denied before contacting Supabase',async()=>{
  await mock(async calls=>{
    const cross=await worker.fetch(request('auth/signin',{email:'a@example.test',password:'secret-password'},{Origin:'https://evil.test'}),env);assert.equal(cross.status,403);
    assert.equal((await worker.fetch(new Request('https://myshelf.cloud/api/auth/signout'),env)).status,405);assert.equal(calls.length,0);
  },()=>{throw Error('must not reach upstream');});
});
test('sessions are encrypted HttpOnly host-only cookies, never browser JSON tokens',async()=>{
  await mock(async()=>{
    const response=await worker.fetch(request('auth/signin',{email:'a@example.test',password:'secret-password'}),env);
    assert.equal(response.status,200);const raw=await response.text();assert(!raw.includes('PRIVATE-ACCESS') && !raw.includes('PRIVATE-REFRESH'));
    const c=response.headers.getSetCookie().find(c=>c.startsWith('__Host-myshelf_session='));
    for(const flag of ['HttpOnly','Secure','SameSite=Strict','Path=/'])assert(c.includes(flag));assert(!c.includes('PRIVATE-ACCESS'));assert(!c.includes('Domain='));
  },()=>ok(auth));
});
test('password creation and recovery require a verified matching flow',async()=>{
  await mock(async calls=>{
    assert.equal((await worker.fetch(request('auth/reset-password',{password:'new-password'}),env)).status,401);
    assert.equal((await worker.fetch(request('auth/complete-signup',{password:'new-password',profile:{display_name:'User',avatar_id:'cat-luna'}}),env)).status,401);
    assert.equal(calls.length,0);
  },()=>{throw Error('unverified password update');});
});
test('email-code verification for an existing account cannot change its password',async()=>{
  await mock(async()=>{
    const response=await worker.fetch(request('auth/verify',{email:'a@example.test',flow:'signup',code:'123456'}),env);
    assert.deepEqual(await response.json(),{existing:true});assert(response.headers.get('Set-Cookie').includes('Max-Age=0'));
  },()=>ok({...auth,user:{...auth.user,user_metadata:{mml_registration:'complete-v1'}}}));
});
test('signup flow is restricted to verified username and then password',async()=>{
  await mock(async calls=>{
    const response=await worker.fetch(request('auth/verify',{email:'a@example.test',flow:'signup',code:'123456'}),env);
    assert.equal((await response.clone().json()).user_id,A);
    const c=response.headers.getSetCookie()[0].split(';')[0];
    const attempt=await worker.fetch(request('auth/reset-password',{password:'new-password'},{Cookie:c}),env);
    assert.equal(attempt.status,401);assert.equal(calls.length,1);
    const claim=await worker.fetch(request('auth/claim-username',{username:'alice'},{Cookie:c}),env);
    assert.deepEqual(await claim.json(),{status:'claimed',username:'alice'});
    assert.equal(calls.at(-1).options.headers.Authorization,'Bearer PRIVATE-ACCESS');
  },url=>url.endsWith('mml_claim_username')?ok({status:'claimed',username:'alice'}):ok(auth));
});
test('stale account tabs cannot upload one owner’s library into another owner’s account',async()=>{
  await mock(async calls=>{
    const c=await sessionCookie();const response=await worker.fetch(request('sync/pull',{cursor:0,timed:true},{Cookie:c,'X-MyShelf-Owner':B}),env);
    assert.equal(response.status,409);assert.equal(calls.length,0);
  },()=>{throw Error('wrong owner upstream');});
});
test('public-facing profile fields reject prohibited names before Auth is updated',async()=>{
  await mock(async calls=>{const c=await sessionCookie();const response=await worker.fetch(request('profile/update',{profile:{display_name:'h1tl3r',avatar_id:'cat-luna'}},{Cookie:c,'X-MyShelf-Owner':A}),env);assert.equal(response.status,422);assert.equal(calls.length,0);},()=>{throw Error('invalid name must not reach Auth');});
});
test('tampered cookie is rejected and private notes cannot select upstream routes',async()=>{
  await mock(async calls=>{
    const response=await worker.fetch(request('sync/pull',{cursor:0},{Cookie:'__Host-myshelf_session=invalid','X-MyShelf-Owner':A}),env);
    assert.equal(response.status,401);assert.equal(calls.length,0);
    const proxy=await worker.fetch(new Request('https://myshelf.cloud/api/catalog/movie/603?api_key=attacker'),env);assert.equal(proxy.status,400);assert.equal(calls.length,0);
  },()=>{throw Error('invalid request upstream');});
});
test('timed sync matches desktop record contract and retains operation IDs',async()=>{
  await mock(async calls=>{
    const cookie=await sessionCookie();const operation={operation_id:A,record_key:'tmdb:603',expected_revision:4,data,field_versions:{note:'2026-10-09T11:00:00.000000+00:00'}};
    const response=await worker.fetch(request('sync/push',{operation,timed:true},{Cookie:cookie,'X-MyShelf-Owner':A}),env);
    assert.equal(response.status,200);const call=calls.at(-1);assert(call.url.endsWith('/mml_push_change_timed'));
    const body=JSON.parse(call.options.body);assert.equal(body.p_operation_id,A);assert.deepEqual(body.p_data,data);assert.deepEqual(body.p_field_versions,operation.field_versions);
    assert.equal(call.options.headers.Authorization,'Bearer PRIVATE-ACCESS');
    assert.equal(response.headers.get('Cache-Control'),'no-store');
  },()=>ok({status:'applied',record_key:'tmdb:603',revision:5}));
});
test('public catalog requests never forward account credentials',async()=>{
  await mock(async calls=>{
    const response=await worker.fetch(new Request('https://myshelf.cloud/api/catalog/movie/603?language=tr-TR',{headers:{Cookie:await sessionCookie(),Authorization:'Bearer MUST-NOT-FORWARD'}}),env);
    assert.equal(response.status,200);assert.equal(calls[0].url,'https://api.myshelf.cloud/3/movie/603?language=tr-TR');assert(!calls[0].options.headers.Authorization);
  },()=>ok({id:603}));
});
test('upstream errors redact submitted data and retain refreshed sessions',async()=>{
  await mock(async()=>{
    const cookie=await sessionCookie({expires:Date.now()-1000});
    const response=await worker.fetch(request('sync/pull',{cursor:0},{Cookie:cookie,'X-MyShelf-Owner':A}),env);
    assert.equal(response.status,503);assert.equal((await response.json()).error,'cloud_unavailable');assert(response.headers.get('Set-Cookie')?.includes('myshelf_session='));
  },url=>url.includes('grant_type=refresh_token')?ok(auth):new Response('{"message":"PRIVATE NOTE A PRIVATE-ACCESS"}',{status:500}));
});
test('limits fail closed and assets have strict script/frame policy',async()=>{
  const broken={...env,API_LIMITER:null};assert.equal((await worker.fetch(new Request('https://myshelf.cloud/api/status'),broken)).status,503);
  const response=await worker.fetch(new Request('https://myshelf.cloud/library'),env);assert.equal(response.status,200);assert(response.headers.get('Content-Security-Policy').includes("frame-ancestors 'none'"));assert(!response.headers.get('Content-Security-Policy').includes('unsafe-inline'));
});

test('person preference writes are authenticated, owner-bound and validated',async()=>{
  await mock(async calls=>{
    const cookie=await sessionCookie(),headers={Cookie:cookie,'X-MyShelf-Owner':A};
    const operation={operation_id:A,person_id:6384,role:'actor',favorite:true,edited_at:'2026-10-11T12:00:00Z'};
    const response=await worker.fetch(request('people/push',{operation},headers),env);
    assert.equal(response.status,200);const call=calls.at(-1);assert(call.url.endsWith('/mml_write_person_favorite'));
    const body=JSON.parse(call.options.body);assert.equal(body.p_person_id,6384);assert.equal(body.p_role,'actor');assert(!('p_user_id' in body));
    assert.equal(call.options.headers.Authorization,'Bearer PRIVATE-ACCESS');
    assert.equal((await worker.fetch(request('people/push',{operation},{...headers,'X-MyShelf-Owner':B}),env)).status,409);
    assert.equal((await worker.fetch(request('people/push',{operation:{...operation,photo:'PRIVATE'}},headers),env)).status,422);
    assert.equal((await worker.fetch(request('people/pull',{cursor:-1},headers),env)).status,400);
  },()=>ok({status:'applied'}));
});
test('internal person pages use public catalog calls without private credentials',async()=>{
  await mock(async calls=>{
    const response=await worker.fetch(new Request('https://myshelf.cloud/api/catalog/person/6384?language=tr-TR&append_to_response=movie_credits',{headers:{Cookie:await sessionCookie()}}),env);
    assert.equal(response.status,200);assert(calls[0].url.includes('/3/person/6384?'));assert(!calls[0].options.headers.Authorization);
    for(const path of ['/people','/person/6384'])assert.equal((await worker.fetch(new Request('https://myshelf.cloud'+path),env)).status,200);
  },()=>ok({id:6384}));
});
