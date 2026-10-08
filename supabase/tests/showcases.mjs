import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
const require = createRequire(process.env.PGLITE_TEST_RUNTIME || import.meta.url);
const {PGlite} = require('@electric-sql/pglite');
const db = new PGlite();
const A = 'aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa', B = 'bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb';
const id = n => `00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const migration = await readFile(new URL('../migrations/002_public_showcases.sql', import.meta.url),'utf8');
await db.exec(`create role anon noinherit; create role authenticated noinherit;
create schema auth; create table auth.users(id uuid primary key);
insert into auth.users values ('${A}'),('${B}');
create function auth.uid() returns uuid language sql stable as
$$select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$;
grant usage on schema auth to anon,authenticated;
grant execute on function auth.uid() to anon,authenticated;`);
await db.exec(await readFile(new URL('../migrations/001_personal_library.sql',import.meta.url),'utf8'));
await db.exec(migration);
async function actor(owner=null,role='authenticated') {
  await db.exec('reset role');
  await db.query("select set_config('request.jwt.claim.sub',$1,false)",[owner||'']);
  await db.exec(`set role ${role}`);
}
async function call(name,args=[]) {
  return (await db.query(`select public.${name}(${args.map((_,i)=>'$'+(i+1)).join(',')}) as value`,args)).rows[0].value;
}
const denied = (task,code='42501') => assert.rejects(task,e=>e.code===code);
const data = (extra={}) => ({status:'Watched',rating:9,note:'SECRET-NOTE',favorite:true,
 watched_date:'2024-01-05',added_at:'2024-01-01T00:00:00.000000+00:00',
 order_key:`00000000000000000001:${id(1)}`,deleted_at:null,custom:null,...extra});
const push = (op,key,rev,payload=data())=>call('mml_push_change',[id(op),key,rev,JSON.stringify(payload)]);
const payload = (extra={})=>({display_name:'Deniz',avatar_id:'cat-lilac',tmdb_ids:[603,550],show_ratings:false,show_stats:false,...extra});
const write = (op,rev,action='publish',p=payload())=>call('mml_write_showcase',[id(op),rev,action,JSON.stringify(p)]);
await actor(null,'anon');
await denied(()=>call('mml_sharing_status'));
await denied(()=>write(1,0));
await denied(()=>db.query('select * from public.mml_library'));
await denied(()=>db.query('select * from mml_private.profiles'));
assert.deepEqual(await call('mml_public_profile',[id(900)]),{found:false});
await actor(A);
assert.deepEqual(await call('mml_sharing_status'),{share_id:null,is_public:false,revision:0});
await push(1,'tmdb:603',0); await push(2,'tmdb:550',0,data({status:'Watchlist',rating:null}));
await denied(()=>db.query('insert into mml_private.profiles(user_id) values ($1)',[A]));
await denied(()=>write(10,0,'update',payload({tmdb_ids:[999]})),'22023');
for (const [i,p] of [payload({note:'LEAK'}),payload({tmdb_ids:[603,603]}),payload({tmdb_ids:['603']}),
 payload({tmdb_ids:[603.2]}),payload({tmdb_ids:[1,2,3,4,5,6,7]}),payload({avatar_id:'../../secret'}),
 payload({show_stats:1}),payload({show_ratings:null}),payload({display_name:'x'.repeat(41)}),
 payload({display_name:'control\ncharacter'}),payload({user_id:B})].entries()) {
 await denied(()=>write(50+i,0,'publish',p),'22023');
}
let published=await write(100,0);
assert.equal(published.status,'applied'); assert.equal(published.settings.is_public,true);
const share=published.settings.share_id;
assert.notEqual(share,A); assert.equal(published.settings.revision,1);
assert.deepEqual(await write(100,0),published); // response-loss replay
await denied(()=>write(100,0,'publish',payload({display_name:'Different'})),'22023');
await actor(null,'anon');
let publicView=await call('mml_public_profile',[share]);
assert.deepEqual(publicView,{found:true,share_id:share,display_name:'Deniz',avatar_id:'cat-lilac',films:[{tmdb_id:603},{tmdb_id:550}]});
assert.ok(!JSON.stringify(publicView).includes('SECRET-NOTE'));
await actor(B);
assert.deepEqual(await call('mml_sharing_status'),{share_id:null,is_public:false,revision:0});
await denied(()=>write(200,0),'22023'); // another owner's films cannot be selected
assert.equal((await db.query('select * from public.mml_library')).rows.length,0);
await actor(A);
published=await write(101,1,'update',payload({tmdb_ids:[550,603],show_ratings:true,show_stats:true}));
assert.equal(published.settings.revision,2);
await actor(null,'anon');
publicView=await call('mml_public_profile',[share]);
assert.deepEqual(publicView.films,[{tmdb_id:550},{tmdb_id:603,rating:9}]);
assert.deepEqual(publicView.counts,{total:2,watched:1,watchlist:1,favorites:2});
await actor(A);
await push(3,'tmdb:603',1,data({deleted_at:'2026-10-08T12:00:00+00:00'}));
assert.deepEqual((await call('mml_public_profile',[share])).films,[{tmdb_id:550}]);
await push(4,'tmdb:603',3,data());
assert.deepEqual((await call('mml_public_profile',[share])).films,[{tmdb_id:550},{tmdb_id:603,rating:9}]);
const revoked=await write(102,0,'unpublish',{}); // stale client may always revoke
assert.equal(revoked.settings.is_public,false); assert.equal(revoked.settings.revision,3);
assert.equal((await write(103,2,'update')).status,'conflict');
assert.equal((await write(104,2)).status,'conflict');
await actor(null,'anon');
assert.deepEqual(await call('mml_public_profile',[share]),{found:false});
await actor(A);
assert.equal((await write(105,3,'update')).status,'conflict'); // updates cannot publish
const again=await write(106,3);
assert.equal(again.settings.share_id,share); assert.equal(again.settings.revision,4);
await denied(()=>write(107,4,'unpublish',{tmdb_ids:[]}),'22023');
await actor(null);
await denied(()=>write(108,4));
await db.exec('reset role'); await db.exec(migration);
await actor(A);
assert.deepEqual(await call('mml_sharing_status'),again.settings);
await denied(()=>db.query('select * from mml_private.profiles'));
await actor(null,'anon');
await denied(()=>db.query('select * from public.mml_library'));
await denied(()=>db.query('select * from mml_private.profiles'));
const usernamesMigration = await readFile(new URL('../migrations/003_unique_usernames.sql',import.meta.url),'utf8');
await db.exec('reset role'); await db.exec(usernamesMigration);
await actor(null,'anon');
await denied(()=>call('mml_username_status'));
await denied(()=>call('mml_claim_username',['deniz']));
await denied(()=>db.query('select * from mml_private.usernames'));
assert.deepEqual(await call('mml_public_profile_by_username',['deniz']),{found:false});
await actor(A);
assert.deepEqual(await call('mml_username_status'),{username:null});
for(const name of ['ab','1deniz','has space','şirin','Kerem','x'.repeat(25),'../admin','ADMIN','support',null]) {
 await denied(()=>call('mml_claim_username',[name]),'22023');
}
const claimed=await call('mml_claim_username',['  DeNiZ_1  ']);
assert.deepEqual(claimed,{status:'claimed',username:'deniz_1'});
assert.deepEqual(await call('mml_claim_username',['DENIZ_1']),claimed);
assert.deepEqual(await call('mml_claim_username',['other_name']),{status:'locked',username:'deniz_1'});
assert.deepEqual(await call('mml_sharing_status'),again.settings); // no changed consent or revision
await actor(B);
assert.deepEqual(await call('mml_claim_username',['DENIZ_1']),{status:'taken',username:null});
assert.deepEqual(await call('mml_claim_username',['another_deniz']),{status:'claimed',username:'another_deniz'});
assert.deepEqual(await call('mml_username_status'),{username:'another_deniz'});
// Two independent profiles can use the exact same display name.
assert.equal((await write(300,0,'publish',payload({tmdb_ids:[]}))).status,'applied');
await actor(null,'anon');
const named=await call('mml_public_profile_by_username',['DENIZ_1']);
assert.equal(named.username,'deniz_1'); assert.equal(named.share_id,share);
assert.equal(named.display_name,'Deniz');
assert.equal((await call('mml_public_profile_by_username',['another_deniz'])).display_name,'Deniz');
assert.deepEqual(await call('mml_public_profile',[share]),Object.fromEntries(Object.entries(named).filter(([k])=>k!=='username')));
assert.ok(!JSON.stringify(named).includes('SECRET-NOTE'));
await actor(A);
await write(301,0,'unpublish',{});
await actor(null,'anon');
assert.deepEqual(await call('mml_public_profile_by_username',['deniz_1']),{found:false});
assert.deepEqual(await call('mml_public_profile_by_username',['missing_name']),{found:false});
assert.deepEqual(await call('mml_public_profile',[share]),{found:false});
await db.exec('reset role'); await db.exec(usernamesMigration);
await actor(A);
assert.deepEqual(await call('mml_username_status'),{username:'deniz_1'});
await denied(()=>db.query('update mml_private.usernames set username=\'stolen\''));
console.log('PASS: public showcase and username SQL: owner isolation, strict validation, non-unique display names, canonical uniqueness, stable/idempotent claims, reserved names, anonymous projection, legacy links, revocation, safe rerun.');
// Legacy disallowed identities are preserved privately, but never projected.
const C='cccccccc-cccc-4ccc-cccc-cccccccccccc', D='dddddddd-dddd-4ddd-dddd-dddddddddddd', E='eeeeeeee-eeee-4eee-eeee-eeeeeeeeeeee';
await db.exec('reset role');
await db.query('insert into auth.users values ($1),($2),($3)',[C,D,E]);
await db.query('insert into mml_private.usernames(user_id,username) values ($1,$2)',[C,'hitler']);
await db.query('insert into mml_private.profiles(user_id,is_public,display_name) values ($1,true,$2),($3,true,$4)',[C,'Safe name',D,'H1TL3R']);
const legacyShares=(await db.query('select user_id,share_id from mml_private.profiles where user_id in ($1,$2)',[C,D])).rows;
const registrationMigration=await readFile(new URL('../migrations/004_registration_usernames.sql',import.meta.url),'utf8');
await db.exec(registrationMigration);
const blocked=['hitler','H1TL3R','h_i_t_l_e_r','user_hitler88','orospu','s1kt1r','yarrak','amcık','götveren',
 'nazi','nazi88','na_zi','fuck_you','shit123','faggot','ＦＵＣＫ','HİTLER','hítler'];
for(const name of blocked) assert.equal((await db.query('select mml_private.name_allowed($1) ok',[name])).rows[0].ok,false,name);
for(const name of ['Nazim','Nazım','Nazife','Scunthorpe','Nigel','Nigeria','Kerem','ClassicFilmFan','CharlieChaplin','Deniz_34','Su Şirin','']) {
 assert.equal((await db.query('select mml_private.name_allowed($1) ok',[name])).rows[0].ok,true,name);
}
await actor(null,'anon');
assert.deepEqual(await call('mml_username_protocol'),{service:'mymovielist-usernames',protocol:2});
await denied(()=>db.query('select mml_private.name_allowed($1)',['safe_name']));
for(const legacy of legacyShares) assert.deepEqual(await call('mml_public_profile',[legacy.share_id]),{found:false});
assert.deepEqual(await call('mml_public_profile_by_username',['hitler']),{found:false});
await actor(E);
for(const name of blocked.filter(n=>/^[a-zA-Z][a-zA-Z0-9_]{2,23}$/.test(n))) {
 await denied(()=>call('mml_claim_username',[name]),'22023');
}
assert.deepEqual(await call('mml_username_status'),{username:null});
assert.deepEqual(await call('mml_claim_username',['nazim']),{status:'claimed',username:'nazim'});
assert.deepEqual(await call('mml_claim_username',['other_name']),{status:'locked',username:'nazim'});
await actor(B);
const state=await call('mml_sharing_status');
await denied(()=>write(400,state.revision,'update',payload({display_name:'H1TL3R',tmdb_ids:[]})),'22023');
assert.deepEqual(await call('mml_sharing_status'),state);
await actor(C);
assert.deepEqual(await call('mml_username_status'),{username:'hitler'});
assert.equal((await write(401,0,'unpublish',{})).settings.is_public,false);
await actor(D);
assert.equal((await write(402,0,'unpublish',{})).settings.is_public,false);
await db.exec('reset role'); await db.exec(registrationMigration);
await actor(E);
assert.deepEqual(await call('mml_username_status'),{username:'nazim'});
await denied(()=>db.query("update mml_private.usernames set username='rename_attempt'"));
await db.exec('reset role');
assert.equal((await db.query("select count(*)::int n from information_schema.columns where table_schema='mml_private' and table_name='usernames' and column_name='revision'")).rows[0].n,0);
console.log('PASS: registration SQL: server-side moderation, normalized variants, legitimate-name boundaries, immutable ownership, private notes unaffected, legacy projection suppression, privacy revocation, migration replay.');
await db.close();
