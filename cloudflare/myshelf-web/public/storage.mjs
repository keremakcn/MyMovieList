import {EDITABLE,equal,iso,merge,newRecord,timestamp,validateRecord,versions} from './sync-model.mjs';

const database=new Promise((resolve,reject)=>{
  const request=indexedDB.open('myshelf-web',1);
  request.onupgradeneeded=()=>{for(const name of ['workspaces','catalog','preferences'])request.result.createObjectStore(name,{keyPath:'key'});};
  request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);
});
const empty=owner=>({key:owner,entries:{},cursor:0,archive:[],generation:0,clock_offset:0,clock_last:'',enabled:true,sharing:null,share_outbox:null,profile_pending:null});
export async function read(owner) {
  const db=await database;return new Promise((resolve,reject)=>{const r=db.transaction('workspaces').objectStore('workspaces').get(owner);r.onsuccess=()=>resolve(r.result || empty(owner));r.onerror=()=>reject(r.error);});
}
export async function mutate(owner,change) {
  const db=await database;
  return new Promise((resolve,reject)=>{
    const tx=db.transaction('workspaces','readwrite'),store=tx.objectStore('workspaces');let value,result;
    const r=store.get(owner);r.onsuccess=()=>{
      try{value=r.result || empty(owner);result=change(value);value.generation++;store.put(value);}
      catch(error){reject(error);tx.abort();}
    };
    tx.oncomplete=()=>resolve(result);tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error || Error('storage_unavailable'));
  });
}
export async function cacheMetadata(key,value) {
  const db=await database;
  return new Promise((resolve,reject)=>{const tx=db.transaction('catalog','readwrite'),table=tx.objectStore('catalog'),r=table.get(key);r.onsuccess=()=>table.put({key,value:{...r.result?.value,...value}});tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);});
}
export async function metadata(key) {
  const db=await database;return new Promise((resolve,reject)=>{const r=db.transaction('catalog').objectStore('catalog').get(key);r.onsuccess=()=>resolve(r.result?.value || null);r.onerror=()=>reject(r.error);});
}
export async function pref(key,value=undefined) {
  const db=await database;return new Promise((resolve,reject)=>{
    const tx=db.transaction('preferences',value===undefined ? 'readonly' : 'readwrite');
    const r=value===undefined ? tx.objectStore('preferences').get(key) : tx.objectStore('preferences').put({key,value});
    let result;r.onsuccess=()=>result=value===undefined ? r.result?.value : value;
    tx.oncomplete=()=>resolve(result);tx.onerror=()=>reject(tx.error);
  });
}
function when(work) {
  let current=Date.now()+work.clock_offset;
  const last=Date.parse(work.clock_last);if(Number.isFinite(last) && last<current+300000) current=Math.max(current,last+1);
  return work.clock_last=iso(current);
}
export async function add(owner,id,details={}) {
  return mutate(owner,work=>{
    const known=id && work.entries['tmdb:'+id];
    if(known){if(known.data.deleted_at){known.data.deleted_at=null;known.versions.deleted_at=when(work);known.conflict=null;}return known.key;}
    const entry=newRecord(id,{...details,now:Date.now()+work.clock_offset});work.entries[entry.key]=entry;return entry.key;
  });
}
export async function edit(owner,key,changes) {
  return mutate(owner,work=>{
    const entry=work.entries[key];if(!entry)throw Error('not_found');
    const value=validateRecord(key,{...entry.data,...changes});
    const changed=EDITABLE.filter(k=>!equal(value[k],entry.data[k]));
    if(changed.length){const time=when(work);for(const k of changed)entry.versions[k]=time;entry.data=value;}
  });
}
export function pending(work) {return Object.values(work.entries).filter(e=>e.outbox || !e.conflict && (!equal(e.data,e.baseline) || !equal(e.versions,e.baseVersions))).length;}
export async function next(owner) {
  return mutate(owner,work=>{
    const entry=Object.values(work.entries).find(e=>e.outbox || !e.conflict && (!equal(e.data,e.baseline) || !equal(e.versions,e.baseVersions)));
    if(!entry)return null;
    if(!entry.outbox)entry.outbox={operation_id:crypto.randomUUID(),record_key:entry.key,expected_revision:entry.revision,data:structuredClone(entry.data),field_versions:structuredClone(entry.versions)};
    return structuredClone(entry.outbox);
  });
}
export async function acknowledge(owner,op,revision) {
  if(!Number.isSafeInteger(revision) || revision<=op.expected_revision)throw Error('invalid_response');
  return mutate(owner,work=>{
    const e=work.entries[op.record_key];if(e.outbox?.operation_id!==op.operation_id)throw Error('operation_changed');
    e.baseline=op.data;e.baseVersions=op.field_versions;e.revision=revision;e.outbox=null;
  });
}
function receive(work,change) {
  const key=change.record_key,data=validateRecord(key,change.data),clocks=versions(change.field_versions || {});
  if(!Number.isSafeInteger(change.revision) || change.revision<1)throw Error('invalid_response');
  let e=work.entries[key];
  if(e && e.revision>=change.revision)return;
  if(e?.outbox)throw Error('push_first');
  const now=Date.now()+work.clock_offset;
  const observed=Object.values(clocks).filter(t=>Date.parse(t)<=now+300000).sort().at(-1);
  if(observed && observed>work.clock_last)work.clock_last=observed;
  if(!e){e={key,data,versions:clocks,baseline:data,baseVersions:clocks,revision:change.revision,outbox:null,conflict:null};work.entries[key]=e;return;}
  const dirty=!equal(e.data,e.baseline) || e.conflict;
  let merged={data,versions:clocks,conflict:false};
  if(dirty) {
    const legacy=merge(e.baseline,e.data,data,e.versions,null,Date.now()+work.clock_offset);
    if(legacy.conflict){work.archive.push({id:crypto.randomUUID(),record_key:key,local_json:JSON.stringify(e.data),remote_json:JSON.stringify(data),remote_revision:change.revision,created_at:iso()});}
    merged=merge(e.baseline,e.data,data,e.versions,change.field_versions ?? null,Date.now()+work.clock_offset);
  }
  if(merged.conflict)e.conflict={revision:change.revision,remote:data,versions:clocks};
  else {e.data=merged.data;e.versions=merged.versions;e.conflict=null;}
  e.baseline=data;e.baseVersions=clocks;e.revision=change.revision;
  // Observe only plausible clocks, ensuring a later local action sorts later.
}
export async function reject(owner,op,remote) {
  if(!remote || !Number.isSafeInteger(remote.revision) || remote.revision<=op.expected_revision)throw Error('invalid_response');
  return mutate(owner,work=>{const e=work.entries[op.record_key];if(e.outbox?.operation_id!==op.operation_id)throw Error('operation_changed');e.outbox=null;receive(work,{record_key:op.record_key,...remote});});
}
export async function page(owner,value) {
  if(value.protocol!==1 || !Array.isArray(value.changes) || value.changes.length>200)throw Error('invalid_response');
  return mutate(owner,work=>{
    let previous=work.cursor;
    for(const change of value.changes){if(!Number.isSafeInteger(change.revision) || change.revision<=previous)throw Error('invalid_response');previous=change.revision;receive(work,change);}
    if(value.cursor!==previous)throw Error('invalid_response');work.cursor=previous;
  });
}
export async function resolve(owner,key,choice,revision) {
  return mutate(owner,work=>{
    const e=work.entries[key],c=e?.conflict;
    if(!c || c.revision!==revision || !['local','remote'].includes(choice))throw Error('conflict_changed');
    work.archive.push({id:crypto.randomUUID(),record_key:key,local_json:JSON.stringify(e.data),remote_json:JSON.stringify(c.remote),remote_revision:revision,created_at:iso()});
    if(choice==='remote'){e.data=c.remote;e.versions=c.versions;}
    else {const time=when(work);for(const k of EDITABLE)if(!equal(e.data[k],c.remote[k]))e.versions[k]=time;e.data.added_at=c.remote.added_at;e.data.order_key=c.remote.order_key;}
    e.conflict=null;
  });
}
export async function copyGuest(owner) {
  if(owner==='guest')return;
  const guest=await read('guest');
  return mutate(owner,work=>{let copied=0;for(const [key,e] of Object.entries(guest.entries)){if(!work.entries[key]){work.entries[key]={...structuredClone(e),baseline:null,baseVersions:{},revision:0,outbox:null,conflict:null};copied++;}}return copied;});
}
export async function exportLibrary(owner) {
  const w=await read(owner);
  return {format:'mymovielist-personal-library',version:1,exported_at:iso(),records:Object.values(w.entries).map(e=>({record_key:e.key,data:e.data})),field_versions:Object.fromEntries(Object.values(w.entries).map(e=>[e.key,e.versions])),conflict_versions:w.archive};
}
export async function importLibrary(owner,document) {
  if(document?.format!=='mymovielist-personal-library' || document.version!==1 || !Array.isArray(document.records) || document.records.length>10000)throw Error('invalid_import');
  const records=document.records.map(r=>({key:r.record_key,data:validateRecord(r.record_key,r.data),versions:versions(document.field_versions?.[r.record_key] || {})}));
  if(document.conflict_versions!==undefined && (!Array.isArray(document.conflict_versions) || document.conflict_versions.length>50000))throw Error('invalid_import');
  // Validate archive records before any commit, retaining their portable contract.
  const archives=(document.conflict_versions || []).map(r=>{
    if(!/^[0-9a-f-]{36}$/.test(r.id) || !Number.isSafeInteger(r.remote_revision) || r.remote_revision<1)throw Error('invalid_import');
    validateRecord(r.record_key,JSON.parse(r.local_json));validateRecord(r.record_key,JSON.parse(r.remote_json));
    return {...r,created_at:timestamp(r.created_at)};
  });
  return mutate(owner,w=>{let count=0;for(const r of records)if(!w.entries[r.key]){w.entries[r.key]={...r,baseline:null,baseVersions:{},revision:0,outbox:null,conflict:null};count++;}const known=new Set(w.archive.map(r=>r.id));for(const a of archives)if(!known.has(a.id))w.archive.push(a);return count;});
}
