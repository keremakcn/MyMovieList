import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
const require = createRequire(process.env.PGLITE_TEST_RUNTIME || import.meta.url);
const {PGlite} = require('@electric-sql/pglite');
const db = new PGlite();
const uid = n => `00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
await db.exec(`create role anon noinherit; create role authenticated noinherit;
create schema auth; create table auth.users(id uuid primary key);
create function auth.uid() returns uuid language sql stable as
$$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
grant usage on schema auth to anon,authenticated;
grant execute on function auth.uid() to anon,authenticated;`);
for (const file of ['001_personal_library.sql','002_public_showcases.sql','003_unique_usernames.sql']) {
  await db.exec(await readFile(new URL('../migrations/'+file,import.meta.url),'utf8'));
}
for (let n=1;n<=30;n++) await db.query('insert into auth.users values ($1)',[uid(n)]);
const person = async(n,name,isPublic=true,display='Deniz',ids=[603],ratings=false) => {
  if(name) await db.query('insert into mml_private.usernames(user_id,username) values ($1,$2)',[uid(n),name]);
  await db.query('insert into mml_private.profiles(user_id,is_public,display_name,tmdb_ids,show_ratings) values ($1,$2,$3,$4,$5)',[uid(n),isPublic,display,ids,ratings]);
};
await person(1,'deniz',true,'Deniz',[603,550,13,22,30,55],true);
await person(2,'burcu',false,'PRIVATE-DISPLAY-NAME');
await person(3,'mert',true,'Deniz');
await person(4,'hitler',true,'Safe display'); // preserved legacy identity; must never project
await person(5,'safe_handle',true,'H1TL3R');
await person(6,null,true,'No handle');
for(let n=7;n<=30;n++) await person(n,'reader'+String(n).padStart(3,'0'),true,'Film lover '+n);
await db.exec(await readFile(new URL('../migrations/004_registration_usernames.sql',import.meta.url),'utf8'));
const dates=(await db.query("select (now() at time zone 'UTC')::date::text today, ((now() at time zone 'UTC')::date-(extract(isodow from (now() at time zone 'UTC')::date)::int-1))::text first")).rows[0];
const shift=(day,n)=>new Date(Date.parse(day+'T12:00:00Z')+n*86400000).toISOString().slice(0,10);
const data = (n,extra={}) => ({status:'Watched',rating:9,note:'SECRET-NOTE-'+n,favorite:true,
  watched_date:dates.today,added_at:'2024-01-01T00:00:00.000000+00:00',
  order_key:`00000000000000000001:${uid(n)}`,deleted_at:null,custom:null,...extra});
const film=async(n,mid,extra={})=>{
  const rev=(await db.query('select coalesce(max(revision),0)+1 rev from public.mml_library where user_id=$1',[uid(n)])).rows[0].rev;
  await db.query('insert into public.mml_library(user_id,record_key,data,revision) values ($1,$2,$3,$4)',[uid(n),'tmdb:'+mid,JSON.stringify(data(n,extra)),rev]);
};
await film(1,603); await film(1,550,{status:'Watchlist'}); await film(1,13,{watched_date:null});
await film(1,22,{watched_date:shift(dates.first,-1)}); await film(1,30,{deleted_at:'2026-10-01T00:00:00+00:00'});
await film(1,55,{watched_date:shift(dates.first,7)}); await film(1,999);
for(let n=2;n<=30;n++) await film(n,603);
const migration=await readFile(new URL('../migrations/005_social_discovery.sql',import.meta.url),'utf8');
await db.exec(migration);
await db.exec('set role anon');
const page=async(view='people',query='',cursor=null)=>(await db.query('select public.mml_social_page($1,$2,$3) value',[view,query,cursor===null?null:JSON.stringify(cursor)])).rows[0].value;
const denied=(fn,code='42501')=>assert.rejects(fn,e=>e.code===code);
await denied(()=>db.query('select * from public.mml_library'));
await denied(()=>db.query('select * from mml_private.profiles'));
await denied(()=>db.query('select * from mml_private.usernames'));
await denied(()=>db.query("select mml_private.name_allowed('deniz')"));
let first=await page();
assert.equal(first.rows.length,16); assert.ok(first.next_cursor);
const second=await page('people','',first.next_cursor);
assert.equal(second.rows.length,10); assert.equal(second.next_cursor,null);
const names=[...first.rows,...second.rows].map(p=>p.username);
assert.equal(new Set(names).size,26); assert.deepEqual(names,[...names].sort());
assert.ok(!names.includes('burcu')&&!names.includes('hitler')&&!names.includes('safe_handle'));
assert.ok(!JSON.stringify([first,second]).includes('SECRET')&&!JSON.stringify([first,second]).includes('PRIVATE'));
assert.deepEqual((await page('people','DENIZ')).rows.map(p=>p.username),['deniz','mert']);
assert.deepEqual((await page('people','deniz')).rows.map(p=>p.display_name),['Deniz','Deniz']);
for(const q of ['%',"' OR 1=1 --",'missing']) assert.equal((await page('people',q)).rows.length,0);
let weekly=await page('week'), events=[...weekly.rows];
while(weekly.next_cursor) { weekly=await page('week','',weekly.next_cursor); events.push(...weekly.rows); }
assert.equal(events.length,26); assert.equal(new Set(events.map(e=>e.username+':'+e.tmdb_id)).size,26);
assert.deepEqual(events.filter(e=>e.username==='deniz'),[{username:'deniz',display_name:'Deniz',avatar_id:'cat-luna',tmdb_id:603,watched_date:dates.today,rating:9}]);
assert.ok(!('rating' in events.find(e=>e.username==='mert')));
assert.ok(events.every(e=>e.tmdb_id===603 && e.watched_date===dates.today));
assert.ok(!JSON.stringify(events).includes('SECRET')&&!JSON.stringify(events).includes('favorite')&&!JSON.stringify(events).includes('user_id'));
assert.equal((await page('week','deniz')).rows.length,2);
const stale={...first.next_cursor,watched_date:shift(dates.first,-1),tmdb_id:603,week_start:shift(dates.first,-7)};
assert.deepEqual(await page('week','',stale),await page('week'));
for(const [v,q,c] of [['wrong','',null],['people','x'.repeat(61),null],['people','bad\nname',null],['people','',{}],
 ['people','',{username:'deniz',user_id:uid(2)}],['people','',{username:1}],['week','',{username:'deniz'}],
 ['week','',{username:'deniz',watched_date:'2026-99-00',tmdb_id:603,week_start:dates.first}],
 ['week','',{username:'deniz',watched_date:dates.today,tmdb_id:true,week_start:dates.first}]]) {
 await denied(()=>page(v,q,c),'22023');
}
await db.exec('reset role');
const countBefore=(await db.query('select count(*)::int n from public.mml_library')).rows[0].n;
await db.query("select set_config('request.jwt.claim.sub',$1,false)",[uid(1)]);
await db.exec('set role authenticated');
await db.query("select public.mml_write_showcase($1,0,'unpublish','{}')",[uid(900)]);
await db.exec('set role anon');
assert.equal((await page('people','deniz')).rows.length,1);
assert.equal((await page('week','deniz')).rows.length,1); // privacy revocation removes both projections immediately
await db.exec('reset role'); await db.exec(migration); // safe replay
assert.equal((await db.query('select count(*)::int n from public.mml_library')).rows[0].n,countBefore);
assert.equal((await db.query('select is_public from mml_private.profiles where user_id=$1',[uid(1)])).rows[0].is_public,false);
await db.exec('set role anon'); await denied(()=>db.query('select * from public.mml_library'));
await db.close();
console.log('PASS: Social SQL — public-only moderated discovery; curated dated watches; hidden ratings/notes/history; bounded keyset pages; safe week rollover; validation; privacy revocation; unchanged RLS and safe replay.');
