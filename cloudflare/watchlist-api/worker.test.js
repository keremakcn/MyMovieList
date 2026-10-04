import {test} from 'node:test';
import assert from 'node:assert/strict';
import worker, {upstreamURL} from './worker.js';

test('catalog allowlist and credential/query injection rejection', () => {
  for (const path of ['/3/tv/1399?append_to_response=aggregate_credits', '/3/movie/550?append_to_response=credits', '/3/tv/1399/season/0', '/3/person/123?append_to_response=tv_credits', '/3/search/movie?query=Alien']) {
    assert.equal(upstreamURL(new URL('https://gateway.test' + path)).hostname, 'api.themoviedb.org');
  }
  for (const path of ['/3/authentication', '/3/account/123', '/3/search/tv?query=x&api_key=secret', '/3/search/tv?query=x&query=y', '/3/search/tv?query=x&page=501', '/3/tv/1?append_to_response=account_states', '/3/tv/1?url=https://evil.test', '/3/tv/1?constructor=x']) {
    assert.equal(upstreamURL(new URL('https://gateway.test' + path)), null);
  }
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
