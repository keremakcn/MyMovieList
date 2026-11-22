import {EDITABLE,equal,iso,merge,newRecord,timestamp,validateRecord,versions} from './sync-model.mjs';

import {validatePeopleExport,peopleState,importPeople} from './people-model.mjs';

const DB_VERSION=2;
const emptyMeta=owner=>({key:owner,cursor:0,archive:[],generation:0,clock_offset:0,clock_last:'',enabled:true,sharing:null,share_outbox:null,profile_pending:null});
const isEntryPending=e=>Boolean(e.outbox || (!e.conflict && (!equal(e.data,e.baseline) || !equal(e.versions,e.baseVersions))));

function stripOwner(row) {
  if(!row)return null;
  const {owner:_owner,...entry}=row;
  return entry;
}

function toEntryRow(owner,entry,fallbackKey) {
  const key=entry.key || fallbackKey;
  return {...entry,owner,key};
}

function entriesFromRows(rows) {
  const map={};
  for(const row of rows || [])map[row.key]=stripOwner(row);
  return map;
}

function when(work) {
  let current=Date.now()+work.clock_offset;
  const last=Date.parse(work.clock_last);
  if(Number.isFinite(last) && last<current+300000) current=Math.max(current,last+1);
  return work.clock_last=iso(current);
}

function receiveEntry(meta,existing,change) {
  const key=change.record_key,data=validateRecord(key,change.data),clocks=versions(change.field_versions || {});
  if(!Number.isSafeInteger(change.revision) || change.revision<1)throw Error('invalid_response');
  let e=existing;
  if(e && e.revision>=change.revision)return {changed:false,entry:e};
  if(e?.outbox)throw Error('push_first');
  const now=Date.now()+meta.clock_offset;
  const observed=Object.values(clocks).filter(t=>Date.parse(t)<=now+300000).sort().at(-1);
  if(observed && observed>meta.clock_last)meta.clock_last=observed;
  if(!e){
    e={key,data,versions:clocks,baseline:data,baseVersions:clocks,revision:change.revision,outbox:null,conflict:null};
    return {changed:true,entry:e};
  }
  const dirty=!equal(e.data,e.baseline) || e.conflict;
  let merged={data,versions:clocks,conflict:false};
  if(dirty) {
    const legacy=merge(e.baseline,e.data,data,e.versions,null,Date.now()+meta.clock_offset);
    if(legacy.conflict){meta.archive.push({id:crypto.randomUUID(),record_key:key,local_json:JSON.stringify(e.data),remote_json:JSON.stringify(data),remote_revision:change.revision,created_at:iso()});}
    merged=merge(e.baseline,e.data,data,e.versions,change.field_versions ?? null,Date.now()+meta.clock_offset);
  }
  if(merged.conflict)e.conflict={revision:change.revision,remote:data,versions:clocks};
  else {e.data=merged.data;e.versions=merged.versions;e.conflict=null;}
  e.baseline=data;e.baseVersions=clocks;e.revision=change.revision;
  // Observe only plausible clocks, ensuring a later local action sorts later.
  return {changed:true,entry:e};
}

export function pending(work) {
  return Object.values(work.entries).filter(isEntryPending).length;
}

export function createStorage(idbProvider=()=>globalThis.indexedDB,dbName='myshelf-web') {
  let dbPromise=null;

  function getDB() {
    if(!dbPromise){
      const idb=typeof idbProvider==='function' ? idbProvider() : idbProvider;
      if(!idb)return Promise.reject(Error('storage_unavailable'));
      dbPromise=new Promise((resolve,reject)=>{
        const request=idb.open(dbName,DB_VERSION);
        request.onupgradeneeded=()=>{
          const db=request.result;
          for(const name of ['workspaces','catalog','preferences']){
            if(!db.objectStoreNames.contains(name))db.createObjectStore(name,{keyPath:'key'});
          }
          if(!db.objectStoreNames.contains('entries')){
            const entriesStore=db.createObjectStore('entries',{keyPath:['owner','key']});
            entriesStore.createIndex('by_owner','owner',{unique:false});
          }
        };
        request.onsuccess=()=>resolve(request.result);
        request.onerror=()=>{dbPromise=null;reject(request.error);};
      });
    }
    return dbPromise;
  }

  function runWorkTx(owner,handler) {
    return getDB().then(db=>new Promise((resolve,reject)=>{
      const tx=db.transaction(['workspaces','entries'],'readwrite');
      const workspaces=tx.objectStore('workspaces'),entries=tx.objectStore('entries');
      let result,abortedError=null;
      const fail=error=>{
        if(!abortedError)abortedError=error;
        try{tx.abort();}catch{}
        reject(error);
      };
      const safe=fn=>(...args)=>{try{fn(...args);}catch(error){fail(error);}};
      const finish=value=>{result=value;};

      const wsReq=workspaces.get(owner);
      wsReq.onsuccess=safe(()=>{
        const raw=wsReq.result;
        if(!raw || !Object.hasOwn(raw,'entries')){
          const meta=raw ? {...emptyMeta(owner),...raw} : emptyMeta(owner);
          handler({tx,workspaces,entries,meta,safe,finish});
          return;
        }
        // Transparently migrate legacy v1 workspace blob into per-entry rows.
        const keysReq=entries.index('by_owner').getAllKeys(owner);
        keysReq.onsuccess=safe(()=>{
          const existing=new Set((keysReq.result || []).map(k=>Array.isArray(k) ? k[1] : k));
          const legacy=raw.entries && typeof raw.entries==='object' ? raw.entries : {};
          for(const [k,entry] of Object.entries(legacy)){
            if(!entry || typeof entry!=='object')continue;
            const entryKey=entry.key || k;
            if(!existing.has(entryKey)){
              entries.put(toEntryRow(owner,entry,entryKey));
              existing.add(entryKey);
            }
          }
          const {entries:_dropped,...rest}=raw;
          const meta={...emptyMeta(owner),...rest};
          workspaces.put(meta);
          handler({tx,workspaces,entries,meta,safe,finish});
        });
      });

      tx.oncomplete=()=>resolve(result);
      tx.onerror=()=>reject(abortedError || tx.error);
      tx.onabort=()=>reject(abortedError || tx.error || Error('storage_unavailable'));
    }));
  }

  async function read(owner) {
    const db=await getDB();
    const first=await new Promise((resolve,reject)=>{
      const tx=db.transaction(['workspaces','entries'],'readonly');
      const workspaces=tx.objectStore('workspaces'),entries=tx.objectStore('entries');
      let needsMigration=false,assembled=null;
      const wsReq=workspaces.get(owner);
      wsReq.onsuccess=()=>{
        const raw=wsReq.result;
        if(raw && Object.hasOwn(raw,'entries')){needsMigration=true;return;}
        const rowsReq=entries.index('by_owner').getAll(owner);
        rowsReq.onsuccess=()=>{
          assembled={...emptyMeta(owner),...(raw || {}),entries:entriesFromRows(rowsReq.result)};
        };
      };
      tx.oncomplete=()=>resolve({needsMigration,assembled});
      tx.onerror=()=>reject(tx.error);
      tx.onabort=()=>reject(tx.error || Error('storage_unavailable'));
    });
    if(!first.needsMigration)return first.assembled;
    return runWorkTx(owner,({entries,meta,safe,finish})=>{
      const rowsReq=entries.index('by_owner').getAll(owner);
      rowsReq.onsuccess=safe(()=>{
        finish({...meta,entries:entriesFromRows(rowsReq.result)});
      });
    });
  }

  async function mutate(owner,change) {
    return runWorkTx(owner,({workspaces,entries,meta,safe,finish})=>{
      const rowsReq=entries.index('by_owner').getAll(owner);
      rowsReq.onsuccess=safe(()=>{
        const rows=rowsReq.result || [];
        let entriesTouched=false,entriesMap=null,beforeMap=null;
        const initEntries=()=>{
          if(!entriesTouched){
            entriesTouched=true;
            beforeMap=new Map();
            entriesMap={};
            for(const row of rows){
              const clean=stripOwner(row);
              beforeMap.set(row.key,structuredClone(clean));
              entriesMap[row.key]=clean;
            }
          }
        };
        Object.defineProperty(meta,'entries',{
          enumerable:true,
          configurable:true,
          get(){initEntries();return entriesMap;},
          set(v){initEntries();entriesMap=v && typeof v==='object' ? v : {};},
        });
        const out=change(meta);
        if(entriesTouched){
          for(const [k,entry] of Object.entries(entriesMap)){
            if(!beforeMap.has(k) || !equal(entry,beforeMap.get(k))){
              entries.put(toEntryRow(owner,entry,k));
            }
          }
          for(const k of beforeMap.keys()){
            if(!Object.hasOwn(entriesMap,k))entries.delete([owner,k]);
          }
        }
        delete meta.entries;
        meta.generation++;
        workspaces.put(meta);
        finish(out);
      });
    });
  }

  async function cacheMetadata(key,value) {
    const db=await getDB();
    return new Promise((resolve,reject)=>{
      const tx=db.transaction('catalog','readwrite'),table=tx.objectStore('catalog'),r=table.get(key);
      r.onsuccess=()=>table.put({key,value:{...r.result?.value,...value}});
      tx.oncomplete=()=>resolve();
      tx.onerror=()=>reject(tx.error);
      tx.onabort=()=>reject(tx.error || Error('storage_unavailable'));
    });
  }

  async function metadata(key) {
    const db=await getDB();
    return new Promise((resolve,reject)=>{
      const r=db.transaction('catalog').objectStore('catalog').get(key);
      r.onsuccess=()=>resolve(r.result?.value || null);
      r.onerror=()=>reject(r.error);
    });
  }

  async function metadataBatch(keys) {
    const unique=[...new Set(keys || [])];
    if(!unique.length)return {};
    const db=await getDB();
    return new Promise((resolve,reject)=>{
      const tx=db.transaction('catalog','readonly'),table=tx.objectStore('catalog'),result={};
      for(const key of unique){
        const r=table.get(key);
        r.onsuccess=()=>{
          const val=r.result?.value || null;
          if(key==='__proto__')Object.defineProperty(result,key,{value:val,enumerable:true,configurable:true,writable:true});
          else result[key]=val;
        };
      }
      tx.oncomplete=()=>resolve(result);
      tx.onerror=()=>reject(tx.error);
      tx.onabort=()=>reject(tx.error || Error('storage_unavailable'));
    });
  }

  async function pref(key,value=undefined) {
    const db=await getDB();
    return new Promise((resolve,reject)=>{
      const tx=db.transaction('preferences',value===undefined ? 'readonly' : 'readwrite');
      const r=value===undefined ? tx.objectStore('preferences').get(key) : tx.objectStore('preferences').put({key,value});
      let result;
      r.onsuccess=()=>result=value===undefined ? r.result?.value : value;
      tx.oncomplete=()=>resolve(result);
      tx.onerror=()=>reject(tx.error);
      tx.onabort=()=>reject(tx.error || Error('storage_unavailable'));
    });
  }

  async function add(owner,id,details={}) {
    return runWorkTx(owner,({workspaces,entries,meta,safe,finish})=>{
      if(id){
        const knownKey='tmdb:'+id;
        const req=entries.get([owner,knownKey]);
        req.onsuccess=safe(()=>{
          if(req.result){
            const known=stripOwner(req.result);
            if(known.data.deleted_at){
              known.data.deleted_at=null;
              known.versions.deleted_at=when(meta);
              known.conflict=null;
              entries.put(toEntryRow(owner,known,knownKey));
            }
            meta.generation++;
            workspaces.put(meta);
            finish(known.key);
            return;
          }
          const entry=newRecord(id,{...details,now:Date.now()+meta.clock_offset});
          entries.put(toEntryRow(owner,entry));
          meta.generation++;
          workspaces.put(meta);
          finish(entry.key);
        });
        return;
      }
      const entry=newRecord(id,{...details,now:Date.now()+meta.clock_offset});
      entries.put(toEntryRow(owner,entry));
      meta.generation++;
      workspaces.put(meta);
      finish(entry.key);
    });
  }

  async function edit(owner,key,changes) {
    return runWorkTx(owner,({workspaces,entries,meta,safe,finish})=>{
      const req=entries.get([owner,key]);
      req.onsuccess=safe(()=>{
        if(!req.result)throw Error('not_found');
        const entry=stripOwner(req.result);
        const value=validateRecord(key,{...entry.data,...changes});
        const changed=EDITABLE.filter(k=>!equal(value[k],entry.data[k]));
        if(changed.length){
          const time=when(meta);
          for(const k of changed)entry.versions[k]=time;
          entry.data=value;
          entries.put(toEntryRow(owner,entry,key));
        }
        meta.generation++;
        workspaces.put(meta);
        finish(undefined);
      });
    });
  }

  async function next(owner) {
    return runWorkTx(owner,({workspaces,entries,meta,safe,finish})=>{
      const cursorReq=entries.index('by_owner').openCursor(owner);
      cursorReq.onsuccess=safe(()=>{
        const cursor=cursorReq.result;
        if(!cursor){
          meta.generation++;
          workspaces.put(meta);
          finish(null);
          return;
        }
        const entry=stripOwner(cursor.value);
        if(isEntryPending(entry)){
          if(!entry.outbox){
            entry.outbox={operation_id:crypto.randomUUID(),record_key:entry.key,expected_revision:entry.revision,data:structuredClone(entry.data),field_versions:structuredClone(entry.versions)};
            entries.put(toEntryRow(owner,entry));
          }
          meta.generation++;
          workspaces.put(meta);
          finish(structuredClone(entry.outbox));
          return;
        }
        cursor.continue();
      });
    });
  }

  async function acknowledge(owner,op,revision) {
    if(!Number.isSafeInteger(revision) || revision<=op.expected_revision)throw Error('invalid_response');
    return runWorkTx(owner,({workspaces,entries,meta,safe,finish})=>{
      const req=entries.get([owner,op.record_key]);
      req.onsuccess=safe(()=>{
        const e=stripOwner(req.result);
        if(!e || e.outbox?.operation_id!==op.operation_id)throw Error('operation_changed');
        e.baseline=op.data;e.baseVersions=op.field_versions;e.revision=revision;e.outbox=null;
        entries.put(toEntryRow(owner,e,op.record_key));
        meta.generation++;
        workspaces.put(meta);
        finish(undefined);
      });
    });
  }

  async function reject(owner,op,remote) {
    if(!remote || !Number.isSafeInteger(remote.revision) || remote.revision<=op.expected_revision)throw Error('invalid_response');
    return runWorkTx(owner,({workspaces,entries,meta,safe,finish})=>{
      const req=entries.get([owner,op.record_key]);
      req.onsuccess=safe(()=>{
        const e=stripOwner(req.result);
        if(!e || e.outbox?.operation_id!==op.operation_id)throw Error('operation_changed');
        e.outbox=null;
        const {entry:updated}=receiveEntry(meta,e,{record_key:op.record_key,...remote});
        entries.put(toEntryRow(owner,updated,op.record_key));
        meta.generation++;
        workspaces.put(meta);
        finish(undefined);
      });
    });
  }

  async function page(owner,value) {
    if(value.protocol!==1 || !Array.isArray(value.changes) || value.changes.length>200)throw Error('invalid_response');
    return runWorkTx(owner,({workspaces,entries,meta,safe,finish})=>{
      if(!value.changes.length){
        if(value.cursor!==meta.cursor)throw Error('invalid_response');
        meta.generation++;
        workspaces.put(meta);
        finish(undefined);
        return;
      }
      if(value.changes.some(c=>typeof c?.record_key!=='string'))throw Error('invalid_response');
      const uniqueKeys=[...new Set(value.changes.map(c=>c.record_key))];
      const loaded=new Map();
      let remaining=uniqueKeys.length;
      for(const key of uniqueKeys){
        const req=entries.get([owner,key]);
        req.onsuccess=safe(()=>{
          loaded.set(key,stripOwner(req.result));
          if(--remaining===0){
            let previous=meta.cursor;
            const dirty=new Set();
            for(const change of value.changes){
              if(!Number.isSafeInteger(change.revision) || change.revision<=previous)throw Error('invalid_response');
              previous=change.revision;
              const res=receiveEntry(meta,loaded.get(change.record_key) || null,change);
              if(res.changed){
                loaded.set(change.record_key,res.entry);
                dirty.add(change.record_key);
              }
            }
            if(value.cursor!==previous)throw Error('invalid_response');
            meta.cursor=previous;
            for(const k of dirty)entries.put(toEntryRow(owner,loaded.get(k),k));
            meta.generation++;
            workspaces.put(meta);
            finish(undefined);
          }
        });
      }
    });
  }

  async function resolve(owner,key,choice,revision) {
    return runWorkTx(owner,({workspaces,entries,meta,safe,finish})=>{
      const req=entries.get([owner,key]);
      req.onsuccess=safe(()=>{
        const e=stripOwner(req.result),c=e?.conflict;
        if(!c || c.revision!==revision || !['local','remote'].includes(choice))throw Error('conflict_changed');
        meta.archive.push({id:crypto.randomUUID(),record_key:key,local_json:JSON.stringify(e.data),remote_json:JSON.stringify(c.remote),remote_revision:revision,created_at:iso()});
        if(choice==='remote'){e.data=c.remote;e.versions=c.versions;}
        else {const time=when(meta);for(const k of EDITABLE)if(!equal(e.data[k],c.remote[k]))e.versions[k]=time;e.data.added_at=c.remote.added_at;e.data.order_key=c.remote.order_key;}
        e.conflict=null;
        entries.put(toEntryRow(owner,e,key));
        meta.generation++;
        workspaces.put(meta);
        finish(undefined);
      });
    });
  }

  async function copyGuest(owner) {
    if(owner==='guest')return;
    const guest=await read('guest');
    return runWorkTx(owner,({workspaces,entries,meta,safe,finish})=>{
      importPeople(meta,Object.values(peopleState(guest).entries).map(e=>e.data));
      const keysReq=entries.index('by_owner').getAllKeys(owner);
      keysReq.onsuccess=safe(()=>{
        const existing=new Set((keysReq.result || []).map(k=>Array.isArray(k) ? k[1] : k));
        let copied=0;
        for(const [key,e] of Object.entries(guest.entries)){
          if(!existing.has(key)){
            entries.put(toEntryRow(owner,{...structuredClone(e),baseline:null,baseVersions:{},revision:0,outbox:null,conflict:null},key));
            existing.add(key);
            copied++;
          }
        }
        meta.generation++;
        workspaces.put(meta);
        finish(copied);
      });
    });
  }

  async function exportLibrary(owner) {
    const w=await read(owner);
    return {format:'mymovielist-personal-library',version:1,exported_at:iso(),person_favorites:Object.values(peopleState(w).entries).map(e=>e.data),records:Object.values(w.entries).map(e=>({record_key:e.key,data:e.data})),field_versions:Object.fromEntries(Object.values(w.entries).map(e=>[e.key,e.versions])),conflict_versions:w.archive};
  }

  async function importLibrary(owner,document) {
    if(document?.format!=='mymovielist-personal-library' || document.version!==1 || !Array.isArray(document.records) || document.records.length>10000)throw Error('invalid_import');
    const people=validatePeopleExport(document.person_favorites);
    const records=document.records.map(r=>({key:r.record_key,data:validateRecord(r.record_key,r.data),versions:versions(document.field_versions?.[r.record_key] || {})}));
    if(document.conflict_versions!==undefined && (!Array.isArray(document.conflict_versions) || document.conflict_versions.length>50000))throw Error('invalid_import');
    // Validate archive records before any commit, retaining their portable contract.
    const archives=(document.conflict_versions || []).map(r=>{
      if(!/^[0-9a-f-]{36}$/.test(r.id) || !Number.isSafeInteger(r.remote_revision) || r.remote_revision<1)throw Error('invalid_import');
      validateRecord(r.record_key,JSON.parse(r.local_json));validateRecord(r.record_key,JSON.parse(r.remote_json));
      return {...r,created_at:timestamp(r.created_at)};
    });
    return runWorkTx(owner,({workspaces,entries,meta,safe,finish})=>{
      importPeople(meta,people);
      const keysReq=entries.index('by_owner').getAllKeys(owner);
      keysReq.onsuccess=safe(()=>{
        const existing=new Set((keysReq.result || []).map(k=>Array.isArray(k) ? k[1] : k));
        let count=0;
        for(const r of records){
          if(!existing.has(r.key)){
            entries.put(toEntryRow(owner,{...r,baseline:null,baseVersions:{},revision:0,outbox:null,conflict:null},r.key));
            existing.add(r.key);
            count++;
          }
        }
        const known=new Set(meta.archive.map(r=>r.id));
        for(const a of archives)if(!known.has(a.id))meta.archive.push(a);
        meta.generation++;
        workspaces.put(meta);
        finish(count);
      });
    });
  }

  return {read,mutate,cacheMetadata,metadata,metadataBatch,pref,add,edit,pending,next,acknowledge,reject,page,resolve,copyGuest,exportLibrary,importLibrary};
}

const defaultStore=createStorage();
export const {read,mutate,cacheMetadata,metadata,metadataBatch,pref,add,edit,next,acknowledge,reject,page,resolve,copyGuest,exportLibrary,importLibrary}=defaultStore;
