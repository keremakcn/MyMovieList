import {equal,timestamp,iso} from './sync-model.mjs';
export const personKey=r=>r.role+':'+r.person_id;
export function validatePerson(value){
  if(!value || typeof value!=='object' || !equal(Object.keys(value).sort(),['edited_at','favorite','person_id','role']) || !['actor','director'].includes(value.role) || !Number.isSafeInteger(value.person_id) || value.person_id<1 || value.person_id>9999999999 || typeof value.favorite!=='boolean')throw Error('invalid_person_favorite');
  return {...value,edited_at:timestamp(value.edited_at)};
}
export function validatePeopleExport(value=[]){
  if(!Array.isArray(value) || value.length>10000)throw Error('invalid_import');
  const rows=value.map(validatePerson);if(new Set(rows.map(personKey)).size!==rows.length)throw Error('invalid_import');return rows;
}
export const peopleState=work=>work.people ||= {entries:{},cursor:0};
export const peoplePending=work=>Object.values(peopleState(work).entries).filter(e=>e.outbox || !equal(e.data,e.baseline)).length;
export function personEdit(work,id,role,favorite){
  const s=peopleState(work),key=personKey({person_id:id,role}),old=s.entries[key];
  if(old && old.data.favorite===favorite)return;
  if(!old && Object.keys(s.entries).length>=10000)throw Error('peopleFull');
  let now=Date.now()+(work.clock_offset || 0),last=Date.parse(work.clock_last);
  if(Number.isFinite(last) && last<=now+300000)now=Math.max(now,last+1);
  const value=validatePerson({person_id:id,role,favorite,edited_at:iso(now)});work.clock_last=value.edited_at;
  if(old)old.data=value;else s.entries[key]={data:value,baseline:null,revision:0,outbox:null};
}
export function nextPerson(work){
  const e=Object.values(peopleState(work).entries).find(e=>e.outbox || !equal(e.data,e.baseline));
  if(!e)return null;e.outbox ||= {operation_id:crypto.randomUUID(),...structuredClone(e.data)};return structuredClone(e.outbox);
}
export function receivePerson(work,remote,ack=false){
  const {revision,...fields}=remote,value=validatePerson(fields);
  if(!Number.isSafeInteger(revision) || revision<1)throw Error('invalid_response');
  const s=peopleState(work),key=personKey(value),old=s.entries[key];
  if(old && (old.revision>revision || old.revision===revision && !ack))return;
  if(old?.outbox)throw Error('push_first');
  const data=old && old.data.edited_at>value.edited_at ? old.data : value;
  s.entries[key]={data,baseline:value,revision,outbox:null};
  if(Date.parse(value.edited_at)<=Date.now()+(work.clock_offset || 0)+300000 && value.edited_at>(work.clock_last || ''))work.clock_last=value.edited_at;
}
export function ackPerson(work,operation,reply){
  if(reply?.status!=='applied' || personKey(reply.record || {})!==personKey(operation))throw Error('invalid_response');
  const {revision,...fields}=reply.record;validatePerson(fields);
  if(!Number.isSafeInteger(revision) || revision<1)throw Error('invalid_response');
  const entry=peopleState(work).entries[personKey(operation)];
  if(!equal(entry?.outbox,operation))throw Error('operation_changed');
  entry.outbox=null;receivePerson(work,reply.record,true);
}
export function peoplePage(work,page){
  if(page?.protocol!==1 || !Array.isArray(page.changes) || page.changes.length>100)throw Error('invalid_response');
  let cursor=peopleState(work).cursor;
  for(const r of page.changes){if(!Number.isSafeInteger(r.revision) || r.revision<=cursor)throw Error('invalid_response');receivePerson(work,r);cursor=r.revision;}
  if(page.cursor!==cursor)throw Error('invalid_response');peopleState(work).cursor=cursor;
}
export function importPeople(work,rows){
  const s=peopleState(work);
  if(new Set([...Object.keys(s.entries),...rows.map(personKey)]).size>10000)throw Error('peopleFull');
  for(const r of rows){const key=personKey(r);if(!s.entries[key])s.entries[key]={data:structuredClone(r),baseline:null,revision:0,outbox:null};}
}
