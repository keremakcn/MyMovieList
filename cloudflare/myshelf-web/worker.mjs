import {upstreamURL} from '../watchlist-api/worker.js';
import {validateRecord, versions} from './public/sync-model.mjs';
import {nameAllowed} from './public/name-policy.mjs';

const RELEASES='https://github.com/keremakcn/MyMovieList/releases/latest';
const encoder=new TextEncoder(), decoder=new TextDecoder();
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const avatars=new Set(['luna','cocoa','sunshine','sage','coral','cloud','midnight','peach','sky','mocha','lilac','mint','cherry','gold','ocean','silver'].map(s=>'cat-'+s));
class Failure extends Error {constructor(code,status=400){super(code);this.code=code;this.status=status;}}
const security={
  'X-Content-Type-Options':'nosniff','Referrer-Policy':'strict-origin-when-cross-origin',
  'Permissions-Policy':'camera=(), microphone=(), geolocation=()',
  'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' https://image.tmdb.org data:; connect-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
};
function json(value,status=200,cookies=[]) {
  const headers=new Headers({...security,'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});
  for (const c of cookies) headers.append('Set-Cookie',c);
  return new Response(JSON.stringify(value),{status,headers});
}
function cookieName(env,type) {return (env.DEVELOPMENT==='true' ? '' : '__Host-')+'myshelf_'+type;}
function cookie(env,type,value,age) {return `${cookieName(env,type)}=${value}; Path=/; HttpOnly; SameSite=Strict; Max-Age=${age}${env.DEVELOPMENT==='true' ? '' : '; Secure'}`;}
function readCookie(request,env,type) {
  return request.headers.get('Cookie')?.split(';').map(s=>s.trim()).find(s=>s.startsWith(cookieName(env,type)+'='))?.split('=').slice(1).join('=');
}
function b64(bytes) {return btoa(String.fromCharCode(...bytes)).replaceAll('+','-').replaceAll('/','_').replaceAll('=','');}
function unb64(value) {return Uint8Array.from(atob(value.replaceAll('-','+').replaceAll('_','/')),c=>c.charCodeAt(0));}
async function key(env) {
  if (!/^[0-9a-f]{64}$/.test(env.SESSION_SECRET || '')) throw new Failure('setup_required',503);
  return crypto.subtle.importKey('raw',Uint8Array.from(env.SESSION_SECRET.match(/../g),h=>parseInt(h,16)),{name:'AES-GCM'},false,['encrypt','decrypt']);
}
export async function seal(env,payload,type) {
  const iv=crypto.getRandomValues(new Uint8Array(12));
  const data=await crypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:encoder.encode('myshelf-v1:'+type)},await key(env),encoder.encode(JSON.stringify(payload)));
  return b64(iv)+'.'+b64(new Uint8Array(data));
}
async function open(request,env,type) {
  const value=readCookie(request,env,type);
  if (!value || value.length>7000) return null;
  try {
    const [iv,data,...extra]=value.split('.'); if(extra.length) return null;
    const plain=await crypto.subtle.decrypt({name:'AES-GCM',iv:unb64(iv),additionalData:encoder.encode('myshelf-v1:'+type)},await key(env),unb64(data));
    const result=JSON.parse(decoder.decode(plain));
    return result.deadline>Date.now() && uuid.test(result.user_id) ? result : null;
  } catch {return null;}
}
function configured(env) {
  if (!/^https:\/\/[a-z0-9-]+\.supabase\.co$/.test(env.SUPABASE_URL || '') || !/^sb_publishable_[A-Za-z0-9_-]+$/.test(env.SUPABASE_PUBLISHABLE_KEY || '')) throw new Failure('setup_required',503);
}
async function upstream(env,path,body,token,method='POST') {
  configured(env);
  let response;
  try {
    response=await fetch(env.SUPABASE_URL+path,{method,redirect:'manual',signal:AbortSignal.timeout(12000),headers:{apikey:env.SUPABASE_PUBLISHABLE_KEY,'Content-Type':'application/json',Accept:'application/json',...(token ? {Authorization:'Bearer '+token} : {})},body:body===undefined ? undefined : JSON.stringify(body)});
  } catch {throw new Failure('cloud_unavailable',503);}
  const raw=await response.text();
  if(raw.length>5*1024*1024) throw new Failure('invalid_response',502);
  let value; try{value=raw ? JSON.parse(raw) : {};}catch{throw new Failure('invalid_response',502);}
  if(!response.ok) {
    if(response.status===429 || response.status===402) throw new Failure('temporarily_limited',429);
    if(value.code==='22023') throw new Failure('invalid_fields',422);
    if(value.code==='PGRST202' || response.status===404) throw new Failure('setup_required',503);
    if(value.code==='otp_expired' || value.error_code==='otp_expired') throw new Failure('invalid_code',422);
    if(response.status===401) throw new Failure('sign_in_required',401);
    if(response.status===400 && path.startsWith('/auth/')) throw new Failure('check_credentials',422);
    throw new Failure('cloud_unavailable',503);
  }
  return value;
}
function session(value,deadline=Date.now()+30*86400000) {
  const user=value.user;
  if (!user || !uuid.test(user.id) || typeof user.email!=='string' || !value.access_token || !value.refresh_token || !Number.isInteger(value.expires_in) || value.expires_in<1 || value.expires_in>86400) throw new Failure('invalid_response',502);
  return {user_id:user.id,email:user.email,access:value.access_token,refresh:value.refresh_token,expires:Date.now()+value.expires_in*1000,deadline};
}
async function active(request,env,cookies,scoped=true) {
  let value=await open(request,env,'session');
  if (!value) throw new Failure('sign_in_required',401);
  if (scoped && request.headers.get('X-MyShelf-Owner')!==value.user_id) throw new Failure('account_changed',409);
  if(value.expires<Date.now()+30000) {
    const refreshed=await upstream(env,'/auth/v1/token?grant_type=refresh_token',{refresh_token:value.refresh});
    const next=session(refreshed,value.deadline);
    if(next.user_id!==value.user_id) throw new Failure('invalid_response',502);
    value=next; cookies.push(cookie(env,'session',await seal(env,value,'session'),Math.max(1,Math.floor((value.deadline-Date.now())/1000))));
  }
  return value;
}
function email(value) {if(typeof value!=='string' || value.length>254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) throw new Failure('invalid_email',422);return value.trim();}
function password(value) {if(typeof value!=='string' || value.length<8 || value.length>512) throw new Failure('invalid_password',422);return value;}
function profile(value) {
  if(!value || typeof value.display_name!=='string' || value.display_name.length>40 || !nameAllowed(value.display_name) || /[\x00-\x1f]/.test(value.display_name) || !avatars.has(value.avatar_id)) throw new Failure('invalid_fields',422);
  return {display_name:value.display_name.trim(),avatar_id:value.avatar_id};
}
function sanitizeProfile(value) {
  try {return profile(value?.mml_profile);} catch {return {display_name:'',avatar_id:'cat-luna'};}
}
async function body(request) {
  if(!request.headers.get('Content-Type')?.startsWith('application/json')) throw new Failure('invalid_request',415);
  if(Number(request.headers.get('Content-Length') || 0)>180000) throw new Failure('invalid_request',413);
  const raw=await request.text();if(encoder.encode(raw).length>180000) throw new Failure('invalid_request',413);
  try {const value=JSON.parse(raw);if(!value || typeof value!=='object' || Array.isArray(value))throw Error();return value;}catch{throw new Failure('invalid_request',400);}
}
async function limit(request,env,auth) {
  const binding=auth ? env.AUTH_LIMITER : env.API_LIMITER;
  if(!binding && env.DEVELOPMENT!=='true') throw new Failure('setup_required',503);
  if(binding && !(await binding.limit({key:request.headers.get('CF-Connecting-IP') || 'unknown'})).success) throw new Failure('temporarily_limited',429);
}
async function api(request,env,url,cookies) {
  const path=url.pathname.slice(5);
  if(!['GET','POST'].includes(request.method)) throw new Failure('method_not_allowed',405);
  const readPath=path==='session' || path==='status' || path==='releases' || path.startsWith('catalog/');
  if(request.method!==(readPath ? 'GET' : 'POST'))throw new Failure('method_not_allowed',405);
  if(request.method==='POST' && (request.headers.get('Origin')!==url.origin || request.headers.get('X-MyShelf-Client')!=='web-v1')) throw new Failure('invalid_origin',403);
  await limit(request,env,path.startsWith('auth/'));
  if(path==='status' && request.method==='GET') {
    let timing=null;
    try{timing=await upstream(env,'/rest/v1/rpc/mml_time_sync_status',{});}catch(e){if(e.code!=='setup_required')throw e;}
    return json({field_sync:timing?.service==='mymovielist-field-sync',server_time:timing?.server_time || new Date().toISOString()},200);
  }
  if(path==='session' && request.method==='GET') {
    if(!await open(request,env,'session')) return json({user:null},200,[cookie(env,'session','',0)]);
    const s=await active(request,env,cookies,false);
    const user=await upstream(env,'/auth/v1/user',undefined,s.access,'GET');
    if(user.id!==s.user_id)throw new Failure('invalid_response',502);
    const handle=await upstream(env,'/rest/v1/rpc/mml_username_status',{},s.access);
    return json({user:{id:s.user_id,email:user.email,username:handle.username,profile:sanitizeProfile(user.user_metadata)}},200,cookies);
  }
  if(path.startsWith('catalog/') && request.method==='GET') {
    const candidate=new URL('https://api.myshelf.cloud/3/'+path.slice(8));candidate.search=url.search;
    const validated=upstreamURL(candidate);
    if(!validated || !/^(search\/movie|trending\/movie\/(day|week)|discover\/movie|movie\/[1-9]\d{0,9})$/.test(candidate.pathname.slice(3))) throw new Failure('invalid_request',400);
    let response;try{response=await fetch(candidate,{redirect:'manual',signal:AbortSignal.timeout(12000),headers:{Accept:'application/json'}});}catch{throw new Failure('catalog_unavailable',503);}
    if(!response.ok)throw new Failure('catalog_unavailable',response.status===429 ? 429 : 503);
    const value=await response.json();return json(value);
  }
  if(path==='releases' && request.method==='GET') {
    const fallback={url:RELEASES,tag:null,assets:[]};
    try {
      const response=await fetch('https://api.github.com/repos/keremakcn/MyMovieList/releases/latest',{headers:{Accept:'application/vnd.github+json','User-Agent':'MyShelf-web'},redirect:'manual',signal:AbortSignal.timeout(7000),cf:{cacheTtl:300,cacheEverything:true}});
      if(!response.ok)return json(fallback);
      const value=await response.json();
      return json({url:RELEASES,tag:typeof value.tag_name==='string' ? value.tag_name.slice(0,40) : null,assets:(value.assets || []).filter(a=>/^https:\/\/github\.com\/keremakcn\/MyMovieList\/releases\/download\//.test(a.browser_download_url) && /\.(zip|exe|apk|dmg)$/.test(a.name)).slice(0,12).map(a=>({name:a.name.slice(0,140),url:a.browser_download_url}))});
    }catch{return json(fallback);}
  }
  const input=request.method==='POST' ? await body(request) : {};
  if(path==='auth/signin') {
    const response=await upstream(env,'/auth/v1/token?grant_type=password',{email:email(input.email),password:password(input.password)});
    const s=session(response);return json({user:{id:s.user_id}},200,[cookie(env,'session',await seal(env,s,'session'),30*86400),cookie(env,'flow','',0)]);
  }
  if(path==='auth/begin-signup' || path==='auth/begin-recovery') {
    const address=email(input.email);
    await upstream(env,path.endsWith('signup') ? '/auth/v1/otp' : '/auth/v1/recover',path.endsWith('signup') ? {email:address,create_user:true,data:{mml_registration:'pending-v1'}} : {email:address});
    return json({sent:true},200,[cookie(env,'flow','',0)]);
  }
  if(path==='auth/verify') {
    if(!['signup','recovery'].includes(input.flow) || typeof input.code!=='string' || !/^\d{6,10}$/.test(input.code))throw new Failure('invalid_code',422);
    const result=await upstream(env,'/auth/v1/verify',{email:email(input.email),token:input.code,type:input.flow==='signup' ? 'email' : 'recovery'});
    const s=session(result,Date.now()+600000);
    if(input.flow==='signup' && result.user.user_metadata?.mml_registration!=='pending-v1')return json({existing:true},200,[cookie(env,'flow','',0)]);
    s.flow=input.flow;return json({verified:true,user_id:s.user_id},200,[cookie(env,'flow',await seal(env,s,'flow'),600)]);
  }
  if(path==='auth/claim-username' || path==='auth/complete-signup' || path==='auth/reset-password') {
    const flow=await open(request,env,'flow');
    if(!flow || flow.flow!==(path==='auth/reset-password' ? 'recovery' : 'signup'))throw new Failure('verify_first',401);
    if(path==='auth/claim-username') {
      if(typeof input.username!=='string' || !/^[a-z][a-z0-9_]{2,23}$/.test(input.username))throw new Failure('invalid_username',422);
      return json(await upstream(env,'/rest/v1/rpc/mml_claim_username',{p_username:input.username},flow.access));
    }
    if(path==='auth/reset-password') {
      await upstream(env,'/auth/v1/user',{password:password(input.password)},flow.access,'PUT');
      return json({updated:true},200,[cookie(env,'flow','',0)]);
    }
    const handle=await upstream(env,'/rest/v1/rpc/mml_username_status',{},flow.access);
    if(!handle.username)throw new Failure('choose_username',422);
    await upstream(env,'/auth/v1/user',{password:password(input.password),data:{mml_registration:'complete-v1',mml_profile:profile(input.profile)}},flow.access,'PUT');
    const response=await upstream(env,'/auth/v1/token?grant_type=refresh_token',{refresh_token:flow.refresh});
    const s=session(response);return json({user:{id:s.user_id}},200,[cookie(env,'session',await seal(env,s,'session'),30*86400),cookie(env,'flow','',0)]);
  }
  if(path==='auth/signout') {
    const s=await open(request,env,'session');
    if(s && request.headers.get('X-MyShelf-Owner')!==s.user_id)throw new Failure('account_changed',409);
    if(s)try{await upstream(env,'/auth/v1/logout?scope=local',{},s.access);}catch{}
    return json({signed_out:true},200,[cookie(env,'session','',0),cookie(env,'flow','',0)]);
  }
  const s=await active(request,env,cookies);
  let value;
  if(path==='sync/pull') {
    if(!Number.isSafeInteger(input.cursor) || input.cursor<0)throw new Failure('invalid_request');
    value=await upstream(env,input.timed===true ? '/rest/v1/rpc/mml_pull_changes_timed' : '/rest/v1/rpc/mml_pull_changes',{p_cursor:input.cursor,p_limit:100},s.access);
  } else if(path==='sync/push') {
    const op=input.operation;
    if(!op || !uuid.test(op.operation_id) || !Number.isSafeInteger(op.expected_revision) || op.expected_revision<0)throw new Failure('invalid_request');
    let data,clocks;try{data=validateRecord(op.record_key,op.data);clocks=versions(op.field_versions || {});}catch{throw new Failure('invalid_fields',422);}
    const payload={p_operation_id:op.operation_id,p_record_key:op.record_key,p_expected_revision:op.expected_revision,p_data:data};
    if(input.timed===true)payload.p_field_versions=clocks;
    value=await upstream(env,input.timed===true ? '/rest/v1/rpc/mml_push_change_timed' : '/rest/v1/rpc/mml_push_change',payload,s.access);
  } else if(path==='profile/update') {
    await upstream(env,'/auth/v1/user',{data:{mml_profile:profile(input.profile)}},s.access,'PUT');value={updated:true};
  } else if(path==='profile/sharing-status') {
    try{value=await upstream(env,'/rest/v1/rpc/mml_showcase_owner_status',{},s.access);}
    catch(error){if(error.code!=='setup_required')throw error;value=await upstream(env,'/rest/v1/rpc/mml_sharing_status',{},s.access);}
  }
  else if(path==='profile/share') {
    if(!uuid.test(input.operation_id) || !Number.isSafeInteger(input.expected_revision) || input.expected_revision<0 || !['publish','update','unpublish'].includes(input.action))throw new Failure('invalid_request');
    value=await upstream(env,'/rest/v1/rpc/mml_write_showcase',{p_operation_id:input.operation_id,p_expected_revision:input.expected_revision,p_action:input.action,p_payload:input.payload},s.access);
  } else throw new Failure('not_found',404);
  return json(value,200,cookies);
}
export default {
  async fetch(request,env) {
    const url=new URL(request.url);
    const cookies=[];
    try {
      if(url.pathname.startsWith('/api/'))return await api(request,env,url,cookies);
      if(request.method!=='GET' && request.method!=='HEAD')throw new Failure('method_not_allowed',405);
      if(url.pathname.startsWith('/u/'))return fetch(new Request('https://profiles.myshelf.cloud'+url.pathname+url.search,{method:request.method}));
      const appRoute=/^\/(?:discover|library|account|updates|profile|movie\/[1-9]\d{0,9})?\/?$/.test(url.pathname);
      const target=new URL(request.url);if(appRoute)target.pathname='/index.html';if(url.pathname==='/credits')target.pathname='/credits.html';
      const result=await env.ASSETS.fetch(new Request(target,{method:request.method}));
      const response=new Response(result.body,result);
      for(const [k,v] of Object.entries(security))response.headers.set(k,v);
      response.headers.set('Cache-Control',/\.(html|mjs|js|css)$/.test(target.pathname) ? 'no-cache' : 'public, max-age=3600');
      return response;
    } catch(error) {
      return json({error:error instanceof Failure ? error.code : 'service_unavailable'},error instanceof Failure ? error.status : 503,cookies);
    }
  },
};
