import {test} from 'node:test';
import assert from 'node:assert/strict';
import worker, {upstreamURL} from './worker.js';

test('movie recommendation keywords use the shared detail cache and stay route-limited', () => {
  const first = upstreamURL(new URL('https://gateway.test/3/movie/550?append_to_response=credits,keywords,translations'));
  const second = upstreamURL(new URL('https://gateway.test/3/movie/550?append_to_response=translations,keywords,credits'));
  assert.ok(first);
  assert.equal(first.href, second.href);
  assert.equal(first.searchParams.get('append_to_response'), 'credits,keywords,translations');
  for (const path of ['/3/tv/550?append_to_response=keywords', '/3/search/movie?query=x&append_to_response=keywords',
    '/3/movie/550?append_to_response=keywords,keywords', '/3/movie/550?append_to_response=keywords,account_states']) {
    assert.equal(upstreamURL(new URL('https://gateway.test' + path)), null);
  }
});

test('credits and translations share one bounded, canonical movie request', () => {
  const first = upstreamURL(new URL('https://gateway.test/3/movie/550?language=en-US&append_to_response=credits,translations'));
  const second = upstreamURL(new URL('https://gateway.test/3/movie/550?append_to_response=translations,credits&language=en-US'));
  assert.ok(first);
  assert.equal(first.href, second.href);
  assert.equal(first.searchParams.get('append_to_response'), 'credits,translations');
  for (const suffix of ['credits,account_states', 'credits,credits', 'translations,', ',translations', 'credits,translations,images']) {
    assert.equal(upstreamURL(new URL('https://gateway.test/3/movie/550?append_to_response=' + suffix)), null);
  }
  assert.equal(upstreamURL(new URL('https://gateway.test/3/search/movie?query=Alien&append_to_response=translations')), null);
  assert.equal(upstreamURL(new URL('https://gateway.test/3/tv/1399?append_to_response=credits,translations')), null);
});

test('catalog allowlist and credential/query injection rejection', () => {
  for (const path of ['/3/tv/1399?append_to_response=aggregate_credits', '/3/movie/550?append_to_response=credits', '/3/tv/1399/season/0', '/3/person/123?append_to_response=tv_credits', '/3/search/movie?query=Alien']) {
    assert.equal(upstreamURL(new URL('https://gateway.test' + path)).hostname, 'api.themoviedb.org');
  }
  for (const path of ['/3/authentication', '/3/account/123', '/3/search/tv?query=x&api_key=secret', '/3/search/tv?query=x&query=y', '/3/search/tv?query=x&page=501', '/3/tv/1?append_to_response=account_states', '/3/tv/1?url=https://evil.test', '/3/tv/1?constructor=x']) {
    assert.equal(upstreamURL(new URL('https://gateway.test' + path)), null);
  }
});

test('movie discovery allows fixed routes and calendar-valid filters', () => {
  const cases = [
    '/3/trending/movie/day?language=en-US&page=2',
    '/3/trending/movie/week?language=tr-TR',
    '/3/movie/top_rated?page=500',
    '/3/genre/movie/list?language=en-US',
    '/3/discover/movie?primary_release_date.gte=2024-02-29&primary_release_date.lte=2024-12-31&with_genres=18,878&vote_count.gte=100&sort_by=primary_release_date.desc&include_video=false',
    '/3/discover/movie?primary_release_date.gte=2000-02-29',
    '/3/discover/movie?primary_release_date.lte=1900-02-28',
  ];
  for (const path of cases) {
    const url = upstreamURL(new URL('https://gateway.test' + path));
    assert.ok(url, path);
    assert.equal(url.origin, 'https://api.themoviedb.org');
    assert.equal(url.pathname, new URL('https://gateway.test' + path).pathname);
    if (url.pathname === '/3/discover/movie') assert.equal(url.searchParams.get('include_adult'), 'false');
  }
});

test('discovery rejects invalid dates, reversed ranges and unsupported endpoints', () => {
  const paths = [
    '/3/trending/movie/year', '/3/trending/all/week', '/3/trending/tv/week',
    '/3/movie/top_rated/private', '/3/genre/tv/list',
    '/3/trending/movie/week?api_key=secret', '/3/movie/top_rated?url=https://evil.test',
    '/3/genre/movie/list?constructor=x', '/3/trending/movie/day?page=501',
    '/3/discover/movie?primary_release_date.gte=2026-02-29',
    '/3/discover/movie?primary_release_date.lte=1900-02-29',
    '/3/discover/movie?primary_release_date.lte=2026-04-31',
    '/3/discover/movie?primary_release_date.gte=0000-01-01',
    '/3/discover/movie?primary_release_date.gte=2026-00-01',
    '/3/discover/movie?primary_release_date.lte=2026-13-01',
    '/3/discover/movie?primary_release_date.lte=2026-01-00',
    '/3/discover/movie?primary_release_date.gte=2026-1-01',
    '/3/discover/movie?primary_release_date.gte=https://evil.test',
    '/3/discover/movie?primary_release_date.gte=2026-06-01&primary_release_date.lte=2026-01-01',
    '/3/discover/movie?primary_release_date.gte=2026-01-01&primary_release_date.gte=2026-02-01',
    '/3/discover/movie?include_adult=true', '/3/discover/movie?include_video=true',
  ];
  for (const path of paths) assert.equal(upstreamURL(new URL('https://gateway.test' + path)), null, path);
});

test('equivalent discovery filters have a canonical cache URL without credentials', () => {
  const first = upstreamURL(new URL('https://gateway.test/3/discover/movie?with_genres=18&page=2&primary_release_date.gte=2026-01-01'));
  const second = upstreamURL(new URL('https://gateway.test/3/discover/movie?primary_release_date.gte=2026-01-01&page=2&with_genres=18&include_adult=false'));
  assert.equal(first.href, second.href);
  assert.equal(first.searchParams.get('include_adult'), 'false');
  assert.equal(first.searchParams.has('api_key'), false);
});

test('discovery responses use bounded cache lifetimes and bypass upstream only after client checks', async () => {
  const originalFetch = globalThis.fetch, originalCaches = globalThis.caches;
  const cache = new Map(), jobs = [];
  globalThis.caches = {default:{
    match:async key => cache.get(key.url)?.clone(),
    put:async (key, response) => cache.set(key.url, response),
  }};
  const ctx = {waitUntil:job => jobs.push(job)};
  const credential = 'a'.repeat(32);
  let upstreamRequests = 0, clientChecks = 0, upstreamChecks = 0;
  const env = {
    TMDB_TOKEN:credential,
    CLIENT_LIMITER:{limit:async () => {clientChecks++; return {success:true};}},
    UPSTREAM_LIMITER:{limit:async () => {upstreamChecks++; return {success:true};}},
  };
  const request = path => new Request('https://gateway.test' + path, {headers:{
    'CF-Connecting-IP':'192.0.2.1', Authorization:'caller-secret', Cookie:'private-library',
  }});
  const cases = [
    ['/3/trending/movie/week?page=1', 900],
    ['/3/trending/movie/day?page=1', 900],
    ['/3/movie/top_rated?page=1', 3600],
    ['/3/genre/movie/list?language=tr-TR', 86400],
    ['/3/discover/movie?primary_release_date.gte=2026-01-01&primary_release_date.lte=2026-10-06', 3600],
  ];
  try {
    globalThis.fetch = async (url, options) => {
      upstreamRequests++;
      const target = new URL(url);
      assert.equal(target.origin, 'https://api.themoviedb.org');
      assert.equal(target.searchParams.get('api_key'), credential);
      assert.equal(options.headers.Authorization, undefined);
      assert.equal(options.headers.Cookie, undefined);
      assert.equal(options.redirect, 'manual');
      return Response.json(target.pathname === '/3/genre/movie/list' ? {genres:[{id:18,name:'Drama'}]} : {page:1,results:[{id:550}],total_pages:1});
    };
    for (const [path, ttl] of cases) {
      const response = await worker.fetch(request(path), env, ctx);
      assert.equal(response.status, 200, path);
      assert.equal(response.headers.get('Cache-Control'), `public, max-age=${ttl}`);
      await Promise.all(jobs);
      assert.equal((await worker.fetch(request(path), env, ctx)).status, 200);
    }
    assert.equal(upstreamRequests, cases.length);
    assert.equal(upstreamChecks, cases.length);
    assert.equal(clientChecks, cases.length * 2);
    assert([...cache.keys()].every(key => !key.includes(credential) && !key.includes('caller-secret')));
    const blocked = await worker.fetch(request(cases[0][0]), {...env, CLIENT_LIMITER:{limit:async () => ({success:false})}}, ctx);
    assert.equal(blocked.status, 429);
    assert.equal((await worker.fetch(request(cases[0][0]), {...env, DISABLED:'true'}, ctx)).status, 503);
    assert.equal((await worker.fetch(request(cases[0][0]), {TMDB_TOKEN:credential}, ctx)).status, 503);
  } finally {globalThis.fetch = originalFetch; globalThis.caches = originalCaches;}
});

test('discovery never caches provider errors, redirects or invalid JSON', async () => {
  const originalFetch = globalThis.fetch, originalCaches = globalThis.caches;
  const cache = new Map(), jobs = [];
  globalThis.caches = {default:{match:async () => undefined, put:async (key, response) => cache.set(key.url, response)}};
  const ctx = {waitUntil:job => jobs.push(job)}, limiter = {limit:async () => ({success:true})};
  const env = {TMDB_TOKEN:'test-secret', CLIENT_LIMITER:limiter, UPSTREAM_LIMITER:limiter};
  const request = () => new Request('https://gateway.test/3/trending/movie/week', {headers:{'CF-Connecting-IP':'192.0.2.1'}});
  const cases = [
    [() => new Response('private provider message', {status:401}), 502],
    [() => new Response('private provider message', {status:403}), 502],
    [() => new Response('private provider message', {status:404}), 404],
    [() => new Response('private provider message', {status:429}), 429],
    [() => new Response('private provider message', {status:500}), 502],
    [() => new Response('', {status:302,headers:{Location:'https://evil.test'}}), 502],
    [() => new Response('not JSON'), 503],
    [() => Response.json([]), 502],
  ];
  try {
    for (const [reply, status] of cases) {
      globalThis.fetch = async () => reply();
      const response = await worker.fetch(request(), env, ctx);
      assert.equal(response.status, status);
      assert.equal(response.headers.get('Cache-Control'), 'no-store');
      const text = await response.text();
      assert(!text.includes('private provider message') && !text.includes('test-secret'));
      await Promise.all(jobs);
      assert.equal(cache.size, 0);
    }
  } finally {globalThis.fetch = originalFetch; globalThis.caches = originalCaches;}
});
test('gateway fails closed, limits traffic, caches success and hides upstream errors', async () => {
  const originalFetch = globalThis.fetch;
  const originalCaches = globalThis.caches;
  const cache = new Map();
  globalThis.caches = {default:{match:async key => cache.get(key.url)?.clone(), put:async (key, value) => cache.set(key.url, value)}};
  const jobs = [];
  const ctx = {waitUntil:p => jobs.push(p)};
  const req = () => new Request('https://gateway.test/3/tv/1399', {headers:{'CF-Connecting-IP':'192.0.2.1', Authorization:'should-not-forward'}});
  const env = {TMDB_TOKEN:'test-secret', CLIENT_LIMITER:{limit:async () => ({success:true})}, UPSTREAM_LIMITER:{limit:async () => ({success:true})}};
  try {
    assert.equal((await worker.fetch(req(), {TMDB_TOKEN:'test-secret'}, ctx)).status, 503);
    let calls = 0;
    globalThis.fetch = async (url, options) => {
      calls++;
      assert.equal(new URL(url).hostname, 'api.themoviedb.org');
      assert.equal(options.headers.Authorization, 'Bearer test-secret');
      assert.equal(options.redirect, 'manual');
      return Response.json({id:1399});
    };
    assert.equal((await worker.fetch(req(), env, ctx)).status, 200);
    await Promise.all(jobs);
    assert.equal((await worker.fetch(req(), env, ctx)).status, 200);
    assert.equal(calls, 1);
    assert.equal((await worker.fetch(req(), {...env, DISABLED:'true'}, ctx)).status, 503);
    assert.equal((await worker.fetch(req(), {...env, CLIENT_LIMITER:{limit:async () => ({success:false})}}, ctx)).status, 429);
    cache.clear();
    globalThis.fetch = async () => new Response('secret upstream body', {status:401});
    const rejected = await worker.fetch(req(), env, ctx);
    assert.equal(rejected.status, 502);
    assert.deepEqual(await rejected.json(), {success:false, error:'tmdb_rejected_token'});
    assert.equal(cache.size, 0);
    globalThis.fetch = async () => { throw new Error('secret'); };
    assert.deepEqual(await (await worker.fetch(req(), env, ctx)).json(), {success:false, error:'tmdb_connection_failed'});
    assert.deepEqual(await (await worker.fetch(req(), {...env, CLIENT_LIMITER:{limit:async () => {throw new Error('private');}}}, ctx)).json(), {success:false, error:'client_limit_unavailable'});
    assert.deepEqual(await (await worker.fetch(req(), {...env, UPSTREAM_LIMITER:{limit:async () => {throw new Error('private');}}}, ctx)).json(), {success:false, error:'upstream_limit_unavailable'});
    globalThis.fetch = async () => new Response('not JSON');
    assert.equal((await (await worker.fetch(req(), env, ctx)).json()).error, 'invalid_upstream_response');
    globalThis.caches.default.match = async () => {throw new Error('cache unavailable');};
    globalThis.fetch = async () => Response.json({id:1399});
    assert.equal((await worker.fetch(req(), env, ctx)).status, 200);
    await Promise.all(jobs);
    assert.equal((await worker.fetch(new Request(req(), {method:'POST'}), env, ctx)).status, 405);
  } finally { globalThis.fetch = originalFetch; globalThis.caches = originalCaches; }
});
