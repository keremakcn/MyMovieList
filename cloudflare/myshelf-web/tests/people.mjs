import assert from 'node:assert/strict';
import {test} from 'node:test';
import {personEdit,nextPerson,ackPerson,peoplePage,peopleState,peoplePending,importPeople,validatePeopleExport} from '../public/people-model.mjs';
const work=()=>({clock_offset:0,clock_last:''});
const remote=(op,revision=1)=>{const {operation_id,...r}=op;return {...r,revision};};
test('actor and director preferences are independent; frozen retry preserves a later removal',()=>{
  const w=work();personEdit(w,6384,'actor',true);personEdit(w,6384,'director',true);
  const op=nextPerson(w);assert.deepEqual(nextPerson(w),op);
  personEdit(w,6384,'actor',false);ackPerson(w,op,{status:'applied',record:remote(op)});
  const removal=nextPerson(w);assert.equal(removal.favorite,false);assert(removal.edited_at>op.edited_at);
  ackPerson(w,removal,{status:'applied',record:remote(removal,2)});
  assert.equal(peopleState(w).entries['actor:6384'].data.favorite,false);assert.equal(peoplePending(w),1);
  const other=work();peoplePage(other,{protocol:1,changes:[remote(removal,2)],cursor:2});
  assert.equal(peopleState(other).entries['actor:6384'].data.favorite,false);
});
test('a server decision at the same revision settles an older offline operation',()=>{
  const w=work();personEdit(w,6384,'actor',true);let op=nextPerson(w);
  const newer={...remote(op),favorite:false,edited_at:'2099-01-01T00:00:00.000000+00:00'};
  ackPerson(w,op,{status:'applied',record:newer});assert.equal(peoplePending(w),0);
  peopleState(w).entries['actor:6384'].data={...op,favorite:true,edited_at:'2000-01-01T00:00:00.000000+00:00'};delete peopleState(w).entries['actor:6384'].data.operation_id;
  op=nextPerson(w);ackPerson(w,op,{status:'applied',record:newer});assert.equal(peoplePending(w),0);
});
test('portable import retains existing decisions and sends no photo/name/biography',()=>{
  const source=work(),target=work();personEdit(source,6384,'actor',true);personEdit(target,6384,'actor',false);
  const rows=validatePeopleExport(Object.values(peopleState(source).entries).map(e=>e.data));importPeople(target,rows);
  assert.equal(peopleState(target).entries['actor:6384'].data.favorite,false);
  assert.deepEqual(Object.keys(rows[0]).sort(),['edited_at','favorite','person_id','role']);
  assert.throws(()=>validatePeopleExport([{...rows[0],person_id:true}]));assert.throws(()=>validatePeopleExport([rows[0],rows[0]]));
});
test('wrong acknowledgements cannot clear the durable outbox',()=>{
  const w=work();personEdit(w,6384,'actor',true);const op=nextPerson(w);
  assert.throws(()=>ackPerson(w,op,{status:'applied',record:{...remote(op),person_id:1}}));
  assert.deepEqual(nextPerson(w),op);
});
test('newer remote removal wins over an older local preference without losing newer local edits',()=>{
  const w=work();personEdit(w,1,'director',true);const entry=peopleState(w).entries['director:1'];entry.data.edited_at='2000-01-01T00:00:00.000000+00:00';
  peoplePage(w,{protocol:1,changes:[{...entry.data,favorite:false,edited_at:'2001-01-01T00:00:00Z',revision:1}],cursor:1});
  assert.equal(peoplePending(w),0);assert.equal(entry.data.favorite,true);
  assert.equal(peopleState(w).entries['director:1'].data.favorite,false);
  personEdit(w,1,'director',true);peoplePage(w,{protocol:1,changes:[{...peopleState(w).entries['director:1'].baseline,revision:2}],cursor:2});
  assert.equal(peopleState(w).entries['director:1'].data.favorite,true);assert.equal(peoplePending(w),1);
});
