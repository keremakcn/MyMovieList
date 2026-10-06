import {gameGateway} from './games.js';

// TMDB_TOKEN must be a Cloudflare Secret, never a literal in this file.
const routes = [
  /^search\/(movie|tv|person|company)$/,
  /^(movie|tv)\/[1-9]\d{0,9}$/,
  /^movie\/[1-9]\d{0,9}\/(recommendations|similar)$/,
  /^tv\/[1-9]\d{0,9}\/season\/\d{1,3}$/,
  /^(person|company)\/[1-9]\d{0,9}$/,
  /^discover\/movie$/,
  /^trending\/movie\/(day|week)$/,
  /^movie\/top_rated$/,
  /^genre\/movie\/list$/,
];
function isISODate(value) {
  if (!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(value)) return false;
  const [year, month, day] = value.split('-').map(Number);
  if (year < 1 || month < 1 || month > 12) return false;
  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return day >= 1 && day <= days[month - 1];
}
const validators = {
  query: v => v.trim().length > 0 && v.length <= 200 && !/[\x00-\x1f]/.test(v),
  page: v => /^[1-9]\d{0,2}$/.test(v) && Number(v) <= 500,
  language: v => /^[a-z]{2}(?:-[A-Z]{2})?$/.test(v),
  include_adult: v => v === 'false',
  include_video: v => v === 'false',
  sort_by: v => /^(popularity|vote_average|vote_count|primary_release_date)\.(asc|desc)$/.test(v),
  with_genres: v => /^\d{1,6}([,|]\d{1,6}){0,9}$/.test(v),
  with_companies: v => /^[1-9]\d{0,9}$/.test(v),
  with_original_language: v => /^[a-z]{2}$/.test(v),
  'vote_count.gte': v => /^\d{1,7}$/.test(v),
  'primary_release_date.gte': isISODate,
  'primary_release_date.lte': isISODate,
};
function json(body, status = 200, extra = {}) {
  return new Response(JSON.stringify(body), {status, headers: {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', ...extra,
  }});
}
function error(code, status, extra) {
  return json({success:false, error:code}, status, extra);
}
function safeFailureMessage(failure, credential) {
  let message = String(failure?.message || 'Unknown failure');
  const token = String(credential || '').trim();
  for (const value of [token, token.replace(/^Bearer\s+/i, '')]) {
    if (value) {
      message = message.split(value).join('[redacted]');
      message = message.split(encodeURIComponent(value)).join('[redacted]');
    }
  }
  return message.replace(/https?:\/\/[^\s"'<>]+/gi, '[url]')
    .replace(/Bearer\s+[^\s"'<>]+/gi, 'Bearer [redacted]')
    .replace(/api_key=[^&\s"'<>]+/gi, 'api_key=[redacted]')
    .replace(/[\r\n]/g, ' ').slice(0, 240);
}
export function upstreamURL(input) {
  const path = input.pathname.replace(/^\/3\//, '');
  if (!input.pathname.startsWith('/3/') || !routes.some(rule => rule.test(path))) return null;
  const target = new URL('https://api.themoviedb.org/3/' + path);
  const seen = new Set();
  for (const [key, value] of input.searchParams) {
    if (seen.has(key)) return null;
    seen.add(key);
    if (key === 'append_to_response') {
      const allowed = /^movie\/\d+$/.test(path) ? ['credits', 'keywords', 'translations'] :
        /^tv\/\d+$/.test(path) ? ['aggregate_credits'] :
        /^person\/\d+$/.test(path) ? ['movie_credits', 'tv_credits'] : [];
      const parts = value.split(',');
      if (!parts.length || parts.length > allowed.length || new Set(parts).size !== parts.length
          || parts.some(part => !allowed.includes(part))) return null;
      target.searchParams.set(key, parts.sort().join(','));
      continue;
    } else if (!Object.hasOwn(validators, key) || !validators[key](value)) return null;
    target.searchParams.set(key, key === 'query' ? value.trim() : value);
  }
  if (path.startsWith('search/') && !target.searchParams.has('query')) return null;
  const startDate = target.searchParams.get('primary_release_date.gte');
  const endDate = target.searchParams.get('primary_release_date.lte');
  // ISO dates sort chronologically after calendar validation.
  if (startDate && endDate && startDate > endDate) return null;
  if (path.startsWith('search/') && path !== 'search/company' || path === 'discover/movie') {
    target.searchParams.set('include_adult', 'false');
  }
  target.searchParams.sort();
  return target;
}
export default {
  async fetch(request, env, ctx) {
    if (request.method !== 'GET') return error('method_not_allowed', 405, {Allow:'GET'});
    const url = new URL(request.url);
    if (url.pathname.startsWith('/rawg/')) return gameGateway(request, env, ctx);
    if (url.pathname === '/' || url.pathname === '/health') {
      return json({service:'watchlist-api', games_status: env.RAWG_API_KEY && env.CLIENT_LIMITER && env.RAWG_LIMITER ? 'configured' : 'setup_required', status:
        env.TMDB_TOKEN && env.CLIENT_LIMITER && env.UPSTREAM_LIMITER ? 'configured' : 'setup_required'});
    }
    if (env.DISABLED === 'true') return error('temporarily_disabled', 503);
    if (request.url.length > 2048) return error('invalid_request', 400);
    const upstream = upstreamURL(url);
    if (!upstream) return error('unsupported_request', 400);
    // Fail closed: dashboard code alone must not create an unlimited public proxy.
    if (!env.TMDB_TOKEN || !env.CLIENT_LIMITER || !env.UPSTREAM_LIMITER) {
      return error('setup_required', 503);
    }
    let stage = 'client_limit';
    let timeout;
    let timedOut = false;
    try {
      const ip = request.headers.get('CF-Connecting-IP');
      if (!ip) return error('missing_client_address', 400);
      if (!(await env.CLIENT_LIMITER.limit({key:ip})).success) {
        return error('rate_limited', 429, {'Retry-After':'60'});
      }
      stage = 'cache_read';
      const cache = caches.default;
      const cacheURL = new URL(upstream.pathname + upstream.search, url.origin);
      const key = new Request(cacheURL);
      // A cache outage must not prevent a bounded upstream request.
      const cached = await cache.match(key).catch(() => undefined);
      if (cached) return cached;
      stage = 'upstream_limit';
      if (!(await env.UPSTREAM_LIMITER.limit({key:'tmdb'})).success) {
        return error('service_busy', 429, {'Retry-After':'60'});
      }
      stage = 'credentials';
      const token = env.TMDB_TOKEN.trim();
      if (!token || /[^\x21-\x7e]/.test(token)) return error('invalid_token_format', 503);
      const headers = {Accept:'application/json'};
      if (/^[a-fA-F0-9]{32}$/.test(token)) upstream.searchParams.set('api_key', token);
      else headers.Authorization = 'Bearer ' + token.replace(/^Bearer\s+/i, '');
      stage = 'tmdb_connection';
      const controller = new AbortController();
      timeout = setTimeout(() => { timedOut = true; controller.abort(); }, 8000);
      const response = await fetch(upstream.toString(), {
        headers,
        // Do not follow redirects: credentials must stay on the fixed TMDB host.
        redirect:'manual', signal:controller.signal,
      });
      if (response.status >= 300 && response.status < 400) return error('unexpected_tmdb_redirect', 502);
      if (!response.ok) {
        if (response.status === 401 || response.status === 403) return error('tmdb_rejected_token', 502);
        const status = response.status === 404 ? 404 : response.status === 429 ? 429 : 502;
        return error(status === 404 ? 'not_found' : 'upstream_unavailable', status,
          status === 429 ? {'Retry-After':'60'} : {});
      }
      stage = 'tmdb_response';
      const data = await response.json();
      if (!data || Array.isArray(data) || typeof data !== 'object') return error('invalid_upstream_response', 502);
      const ttl = upstream.pathname.includes('/search/') ? 120 :
        upstream.pathname.startsWith('/3/trending/') ? 900 :
        upstream.pathname === '/3/genre/movie/list' ? 86400 : 3600;
      const result = json(data, 200, {'Cache-Control':`public, max-age=${ttl}`});
      stage = 'cache_write';
      ctx.waitUntil(Promise.resolve().then(() => cache.put(key, result.clone())).catch(() => {}));
      return result;
    } catch (failure) {
      // Fixed diagnostic codes only: never expose exception text or credentials.
      console.error('gateway_failure', {stage, message:safeFailureMessage(failure, env.TMDB_TOKEN)});
      const codes = {
        client_limit:'client_limit_unavailable', upstream_limit:'upstream_limit_unavailable',
        cache_read:'cache_unavailable', credentials:'invalid_token_format',
        tmdb_connection:'tmdb_connection_failed', tmdb_response:'invalid_upstream_response',
        cache_write:'cache_unavailable',
      };
      return error(timedOut ? 'tmdb_timeout' : codes[stage] || 'service_unavailable', 503);
    } finally {
      clearTimeout(timeout);
    }
  },
};
