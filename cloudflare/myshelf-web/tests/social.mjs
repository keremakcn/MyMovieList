import assert from 'node:assert/strict';
import {test} from 'node:test';
import {socialPage,socialQuery,socialCursor,decodeSocialCursor} from '../public/social-model.mjs';
const person={username:'alice',display_name:'Alice',avatar_id:'cat-luna'};
const page=(view,rows=[])=>({protocol:1,view,rows,next_cursor:null,week_start:'2026-10-12',week_end:'2026-10-18'});
test('only strict public member and selected activity fields can be displayed',()=>{
  assert.equal(socialPage(page('people',[person]),'people').rows[0].username,'alice');
  const row={...person,tmdb_id:603,watched_date:'2026-10-12',rating:9};
  assert.equal(socialPage(page('week',[row]),'week').rows[0].rating,9);
  for(const key of ['note','email','user_id','favorite','library'])assert.throws(()=>socialPage(page('week',[{...row,[key]:'PRIVATE'}]),'week'));
  assert.throws(()=>socialPage(page('people',[{...person,avatar_id:'../../private'}]),'people'));
  assert.throws(()=>socialPage(page('week',[{...row,watched_date:'2026-10-19'}]),'week'));
  assert.throws(()=>socialPage(page('week',[row,row]),'week'));
});
test('member ordering and cursors retain the selected view and search',()=>{
  const rows=Array.from({length:16},(_,i)=>({...person,username:'member_'+String(i).padStart(2,'0')})),position={username:rows.at(-1).username};
  assert.deepEqual(socialPage({...page('people',rows),next_cursor:position},'people').next_cursor,position);
  assert.throws(()=>socialPage(page('people',[...rows].reverse()),'people'));
  const query=socialQuery(' @Çağrı '),token=socialCursor('people',query,position);
  assert.deepEqual(decodeSocialCursor(token,'people',query),position);
  assert.throws(()=>decodeSocialCursor(token,'week',query));assert.throws(()=>decodeSocialCursor(token,'people','someone else'));
  for(const q of ['x'.repeat(61),'a\u0000b'])assert.throws(()=>socialQuery(q));
});
