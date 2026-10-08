import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {PGlite} from '@electric-sql/pglite';

// Isolated, synthetic PostgreSQL database. No remote credentials or user data.
const db = new PGlite();
const sql = await readFile(new URL('../migrations/001_personal_library.sql', import.meta.url), 'utf8');
const A = 'aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa';
const B = 'bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb';
const id = n => `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
const data = (extra = {}) => ({
  status: 'Watched', rating: 9, note: 'Özel not — original\nİkinci satır', favorite: true,
  watched_date: '2024-01-05', added_at: '2024-01-01T00:00:00.000000+00:00',
  order_key: `00000000000000000001:${id(1)}`, deleted_at: null, custom: null, ...extra,
});
await db.exec(`
  create role anon noinherit; create role authenticated noinherit;
  create schema auth;
  create table auth.users(id uuid primary key);
  insert into auth.users values ('${A}'),('${B}');
  create function auth.uid() returns uuid language sql stable as
  $$select nullif(current_setting('request.jwt.claim.sub', true),'')::uuid$$;
  grant usage on schema auth to anon, authenticated;
  grant execute on function auth.uid() to anon, authenticated;
`);
await db.exec(sql);
async function actor(user, role='authenticated') {
  await db.exec('reset role');
  await db.query("select set_config('request.jwt.claim.sub',$1,false)", [user || '']);
  await db.exec(`set role ${role}`);
}
async function call(name, params = []) {
  const placeholders = params.map((_, i) => `$${i+1}`).join(',');
  return (await db.query(`select public.${name}(${placeholders}) as value`, params)).rows[0].value;
}
const push = (op, key, expected, payload) => call('mml_push_change', [id(op), key, expected, JSON.stringify(payload)]);
async function denied(action, code = '42501') {
  await assert.rejects(action, e => e.code === code);
}
await actor(null,'anon');
assert.equal((await call('mml_cloud_status')).protocol, 1);
await denied(() => db.query('select * from public.mml_library'));
await denied(() => push(1,'tmdb:603',0,data()));
await denied(() => call('mml_pull_changes', [0,100]));

await actor(A);
let result = await push(1,'tmdb:603',0,data());
assert.deepEqual(result, {status:'applied',record_key:'tmdb:603',revision:1,replayed:false});
result = await push(1,'tmdb:603',0,data());
assert.equal(result.replayed,true); assert.equal(result.revision,1);
await denied(() => push(1,'tmdb:603',0,data({note:'Different request'})), '22023');
let pulled = await call('mml_pull_changes',[0,100]);
assert.equal(pulled.changes.length,1); assert.equal(pulled.cursor,1);
assert.equal(pulled.changes[0].data.note,data().note);
await denied(() => db.query('update public.mml_library set revision=999'));
await denied(() => db.query('delete from public.mml_library'));
await denied(() => db.query('select * from mml_private.sync_receipts'));

const removed = data({deleted_at:'2026-10-07T11:30:00+00:00'});
assert.equal((await push(2,'tmdb:603',1,removed)).revision,2);
const stale = await push(3,'tmdb:603',1,data({note:'stale device'}));
assert.equal(stale.status,'conflict'); assert.equal(stale.remote.data.note,data().note);
assert.equal(stale.remote.data.deleted_at,removed.deleted_at);
assert.equal((await push(4,'tmdb:603',2,data())).revision,3);
assert.equal((await push(1,'tmdb:603',0,data())).revision,1); // replay cannot undo later changes
pulled = await call('mml_pull_changes',[0,100]);
assert.equal(pulled.changes[0].revision,3);
assert.deepEqual(pulled.changes[0].data,data()); // all personal fields survive delete/Undo
await denied(() => push(5,'tmdb:603',3,data({order_key:`00000000000000000002:${id(1)}`})), '22023');
await denied(() => push(6,'tmdb:603',3,data({added_at:'2025-01-01T00:00:00Z'})), '22023');

await actor(B);
assert.equal((await db.query('select * from public.mml_library')).rows.length,0);
assert.deepEqual((await call('mml_pull_changes',[0,100])).changes,[]);
assert.equal((await push(1,'tmdb:603',0,data({note:'B private'}))).revision,1);
let rows = (await db.query('select user_id,data from public.mml_library')).rows;
assert.equal(rows.length,1); assert.equal(rows[0].user_id,B); assert.equal(rows[0].data.note,'B private');
await actor(A);
rows = (await db.query('select data from public.mml_library')).rows;
assert.equal(rows.length,1); assert.equal(rows[0].data.note,data().note);

for (const [i, invalid] of [
  data({rating:0}), data({rating:11}), data({rating:'9'}), data({rating:2.5}),
  data({favorite:1}), data({status:'Anything'}), data({note:'x'.repeat(20001)}),
  data({note:[]}), data({overview:'Public metadata'}), data({user_id:B}),
  data({watched_date:'2026-02-30'}), data({watched_date:'not a date'}),
  data({added_at:null}), data({deleted_at:'2026-10-07'}), data({custom:{title:'Title'}}),
].entries()) await denied(() => push(100+i,'tmdb:500',0,invalid), '22023');
await denied(() => push(130,'tmdb:0',0,data()),'22023');
await denied(() => call('mml_pull_changes',[999,100]),'22023');
await denied(() => call('mml_pull_changes',[0,201]),'22023');
await denied(() => push(131,'custom:'+id(7),0,data()),'22023');
await denied(() => push(132,'custom:'+id(7),0,data({custom:{title:'',year:null,genre:null}})),'22023');
await denied(() => push(133,'custom:'+id(7),0,data({custom:{title:'Film',year:1700,genre:null}})),'22023');
const custom = data({rating:null,note:null,watched_date:null,
  custom:{title:'My private home video',year:null,genre:null}});
assert.equal((await push(200,'custom:'+id(7),0,custom)).revision,4);
assert.equal((await push(201,'tmdb:500',0,data({note:'ş'.repeat(20000)}))).revision,5);
pulled = await call('mml_pull_changes',[0,2]);
assert.deepEqual(pulled.changes.map(r=>r.revision),[3,4]);
const next = await call('mml_pull_changes',[pulled.cursor,2]);
assert.deepEqual(next.changes.map(r=>r.revision),[5]);
assert.deepEqual((await call('mml_pull_changes',[next.cursor,2])).changes,[]);

await db.exec('reset role');
await db.exec(sql); // re-run must preserve records and idempotency receipts
await actor(A);
assert.equal((await db.query('select * from public.mml_library')).rows.length,3);
assert.equal((await push(1,'tmdb:603',0,data())).replayed,true);
await actor(null);
await denied(() => push(300,'tmdb:603',3,data()));
await denied(() => call('mml_pull_changes',[0,100]));
console.log('PASS: PostgreSQL migration and rerun; anonymous denial; two-user RLS isolation; direct-write denial; idempotency; stale write conflict; tombstone and Undo; original order/time; Unicode; invalid fields/types/dates; bounded incremental pages.');
await db.close();
