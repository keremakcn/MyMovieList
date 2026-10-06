// RAWG_API_KEY is a Cloudflare Secret. Only this app's catalog routes are exposed.
const routes = /^(games(?:\/[1-9]\d{0,9})?|developers|publishers)$/;
const validators = {
  search: value => value.trim().length > 0 && value.length <= 200 && !/[\x00-\x1f]/.test(value),
  page: value => /^[1-9]\d{0,2}$/.test(value) && Number(value) <= 500,
  page_size: value => /^[1-9]\d?$/.test(value) && Number(value) <= 40,
  exclude_additions: value => value === 'true',
  developers: value => /^[1-9]\d{0,9}$/.test(value),
  publishers: value => /^[1-9]\d{0,9}$/.test(value),
  ordering: value => value === '-added',
};
export function rawgURL(input) {
  if (!input.pathname.startsWith('/rawg/')) return null;
  const path = input.pathname.slice(6);
  if (!routes.test(path)) return null;
  const target = new URL('https://api.rawg.io/api/' + path);
  const seen = new Set();
  for (const [name, value] of input.searchParams) {
    if (seen.has(name) || !Object.hasOwn(validators, name) || !validators[name](value)) return null;
    if (/^games\/\d+$/.test(path)) return null;
    if (path !== 'games' && !['search', 'page', 'page_size'].includes(name)) return null;
    seen.add(name);
    target.searchParams.set(name, name === 'search' ? value.trim() : value);
  }
  if (!/^games\/\d+$/.test(path)) {
    if (!seen.has('search') && !seen.has('developers') && !seen.has('publishers')) return null;
    if (!seen.has('page')) target.searchParams.set('page', '1');
    if (!seen.has('page_size')) target.searchParams.set('page_size', '20');
    if (path === 'games') target.searchParams.set('exclude_additions', 'true');
  }
  target.searchParams.sort();
  return target;
}
function json(data, status = 200, headers = {}) {
  return Response.json(data, {status, headers:{'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff', ...headers}});
}
function error(code, status, headers) { return json({success:false, error:code}, status, headers); }
function publicData(data, credential) {
  // RAWG's next/previous URLs include the secret. The client only needs page availability.
  const clean = value => {
    if (typeof value === 'string') return value.split(credential).join('[redacted]');
    if (Array.isArray(value)) return value.map(clean);
    if (value && typeof value === 'object') {
      return Object.fromEntries(Object.entries(value).filter(([key])=>!['api_key','key'].includes(key))
        .map(([key, child])=>[key, ['next','previous'].includes(key) ? Boolean(child) : clean(child)]));
    }
    return value;
  };
  return clean(data);
}
export async function gameGateway(request, env, ctx) {
  if (request.method !== 'GET') return error('method_not_allowed', 405, {Allow:'GET'});
  if (env.DISABLED === 'true' || env.RAWG_DISABLED === 'true') return error('temporarily_disabled', 503);
  if (request.url.length > 2048) return error('invalid_request', 400);
  const input = new URL(request.url);
  const upstream = rawgURL(input);
  if (!upstream) return error('unsupported_request', 400);
  if (!env.RAWG_API_KEY || !env.CLIENT_LIMITER || !env.RAWG_LIMITER) return error('games_setup_required', 503);
  const credential = String(env.RAWG_API_KEY).trim();
  if (!/^[a-f0-9]{32}$/i.test(credential)) return error('invalid_game_credential', 503);
  let timer;
  let timedOut = false;
  let stage = 'client_limit';
  try {
    const ip = request.headers.get('CF-Connecting-IP');
    if (!ip) return error('missing_client_address', 400);
    if (!(await env.CLIENT_LIMITER.limit({key:ip})).success) return error('rate_limited', 429, {'Retry-After':'60'});
    const key = new Request(new URL('/rawg/' + upstream.pathname.slice(5) + upstream.search, input.origin));
    const cache = caches.default;
    const cached = await cache.match(key).catch(()=>undefined);
    if (cached) return cached;
    stage = 'upstream_limit';
    if (!(await env.RAWG_LIMITER.limit({key:'rawg'})).success) return error('service_busy', 429, {'Retry-After':'60'});
    upstream.searchParams.set('key', credential);
    const controller = new AbortController();
    timer = setTimeout(()=>{timedOut=true; controller.abort();},8000);
    stage = 'rawg_connection';
    const response = await fetch(upstream.toString(), {headers:{Accept:'application/json'}, redirect:'manual', signal:controller.signal});
    if (response.status >= 300 && response.status < 400) return error('unexpected_game_redirect', 502);
    if (!response.ok) {
      const status = response.status === 404 ? 404 : response.status === 429 ? 429 : 502;
      return error(status === 404 ? 'not_found' : 'game_provider_unavailable', status, status === 429 ? {'Retry-After':'60'} : {});
    }
    stage = 'rawg_response';
    const data = await response.json();
    if (!data || Array.isArray(data) || typeof data !== 'object' || data.error) return error('invalid_game_response', 502);
    if (/\/games\/\d+$/.test(upstream.pathname)) {
      if (!data.id || typeof data.name !== 'string') return error('invalid_game_response',502);
    } else if (!Array.isArray(data.results)) return error('invalid_game_response',502);
    const ttl = /^\/api\/games\/\d+$/.test(upstream.pathname) ? 21600 : 600;
    const result = json(publicData(data,credential),200,{'Cache-Control':`public, max-age=${ttl}`});
    ctx.waitUntil(Promise.resolve().then(()=>cache.put(key,result.clone())).catch(()=>{}));
    return result;
  } catch {
    // Never log exceptions: upstream URLs contain the RAWG credential.
    console.error('game_gateway_failure',{stage});
    return error(timedOut ? 'game_provider_timeout' : 'game_service_unavailable',503);
  } finally { clearTimeout(timer); }
}
