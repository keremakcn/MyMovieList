import assert from 'node:assert/strict';
import {test} from 'node:test';
import {createStorage,pending} from '../public/storage.mjs';
import {newRecord,iso} from '../public/sync-model.mjs';
import {LIBRARY_PAGE_SIZE,sliceLibrary,libraryMetadataKeys} from '../public/library-model.mjs';

function extractKey(value,keyPath){
  if(Array.isArray(keyPath))return keyPath.map(k=>value[k]);
  return value[keyPath];
}
function encodeKey(key){return JSON.stringify(key);}

function createMockIDB(){
  const dbs=new Map();
  const stats={
    transactions:[],
    puts:[],
    gets:[],
    deletes:[],
    reset(){this.transactions=[];this.puts=[];this.gets=[];this.deletes=[];},
  };

  function makeDBState(name){
    let state=dbs.get(name);
    if(!state){state={version:0,stores:new Map()};dbs.set(name,state);}
    return state;
  }

  function wrapDB(state){
    return {
      get version(){return state.version;},
      objectStoreNames:{
        contains:name=>state.stores.has(name),
      },
      createObjectStore(name,{keyPath}){
        if(state.stores.has(name))throw Error('store_exists');
        const storeState={name,keyPath,data:new Map(),indexes:new Map()};
        state.stores.set(name,storeState);
        return {
          createIndex(indexName,indexKeyPath,opts={}){
            storeState.indexes.set(indexName,{name:indexName,keyPath:indexKeyPath,unique:!!opts.unique});
          },
        };
      },
      transaction(storeNames,mode='readonly'){
        const names=Array.isArray(storeNames)?storeNames:[storeNames];
        for(const n of names)if(!state.stores.has(n))throw Error('NotFoundError: '+n);
        stats.transactions.push({stores:[...names],mode});

        const snapshots=mode==='readwrite'
          ? new Map(names.map(n=>[n,new Map([...state.stores.get(n).data.entries()].map(([k,v])=>[k,structuredClone(v)]))]))
          : null;

        let active=true,aborted=false,pendingReqs=0,completionScheduled=false;
        const tx={
          mode,
          error:null,
          oncomplete:null,
          onerror:null,
          onabort:null,
          abort(){
            if(aborted)return;
            aborted=true;active=false;
            if(snapshots){
              for(const [n,snap] of snapshots)state.stores.get(n).data=snap;
            }
            queueMicrotask(()=>{if(tx.onabort)tx.onabort();});
          },
          objectStore(name){
            if(!names.includes(name))throw Error('NotFoundError: '+name);
            const storeState=state.stores.get(name);
            return makeObjectStore(storeState);
          },
        };

        function scheduleCheck(){
          if(completionScheduled || aborted)return;
          completionScheduled=true;
          queueMicrotask(()=>{
            completionScheduled=false;
            if(aborted)return;
            if(pendingReqs===0 && active){
              active=false;
              if(tx.oncomplete)tx.oncomplete();
            }
          });
        }

        function runRequest(fn){
          if(!active || aborted)throw Error('TransactionInactiveError');
          const req={result:undefined,error:null,onsuccess:null,onerror:null};
          pendingReqs++;
          queueMicrotask(()=>{
            if(aborted){pendingReqs--;return;}
            try{
              req.result=fn();
              if(req.onsuccess)req.onsuccess({target:req});
            }catch(err){
              req.error=err;
              tx.error=err;
              if(req.onerror)req.onerror({target:req});
              tx.abort();
            }finally{
              pendingReqs--;
              scheduleCheck();
            }
          });
          return req;
        }

        function makeObjectStore(storeState){
          return {
            get(key){
              stats.gets.push({store:storeState.name,key:structuredClone(key)});
              return runRequest(()=>{
                const found=storeState.data.get(encodeKey(key));
                return found===undefined ? undefined : structuredClone(found);
              });
            },
            put(value){
              if(mode!=='readwrite')throw Error('ReadOnlyError');
              const cloned=structuredClone(value);
              const k=extractKey(cloned,storeState.keyPath);
              stats.puts.push({store:storeState.name,key:structuredClone(k),value:structuredClone(cloned)});
              return runRequest(()=>{
                storeState.data.set(encodeKey(k),cloned);
                return structuredClone(k);
              });
            },
            delete(key){
              if(mode!=='readwrite')throw Error('ReadOnlyError');
              stats.deletes.push({store:storeState.name,key:structuredClone(key)});
              return runRequest(()=>{
                storeState.data.delete(encodeKey(key));
              });
            },
            index(indexName){
              const idx=storeState.indexes.get(indexName);
              if(!idx)throw Error('NotFoundError: index '+indexName);
              const matchingEntries=query=>{
                const matched=[];
                for(const v of storeState.data.values()){
                  const idxVal=extractKey(v,idx.keyPath);
                  if(query===undefined || encodeKey(idxVal)===encodeKey(query)){
                    matched.push({
                      indexKey:idxVal,
                      primaryKey:extractKey(v,storeState.keyPath),
                      value:v,
                    });
                  }
                }
                matched.sort((a,b)=>encodeKey(a.primaryKey).localeCompare(encodeKey(b.primaryKey)));
                return matched;
              };
              return {
                getAll(query){
                  return runRequest(()=>matchingEntries(query).map(m=>structuredClone(m.value)));
                },
                getAllKeys(query){
                  return runRequest(()=>matchingEntries(query).map(m=>structuredClone(m.primaryKey)));
                },
                openCursor(query){
                  if(!active || aborted)throw Error('TransactionInactiveError');
                  const req={result:null,error:null,onsuccess:null,onerror:null};
                  let list=null,pos=0;
                  function step(){
                    pendingReqs++;
                    queueMicrotask(()=>{
                      if(aborted){pendingReqs--;return;}
                      try{
                        if(list===null)list=matchingEntries(query);
                        if(pos<list.length){
                          const item=list[pos++];
                          req.result={
                            key:structuredClone(item.indexKey),
                            primaryKey:structuredClone(item.primaryKey),
                            value:structuredClone(item.value),
                            continue(){step();},
                          };
                        }else{
                          req.result=null;
                        }
                        if(req.onsuccess)req.onsuccess({target:req});
                      }catch(err){
                        req.error=err;tx.error=err;
                        if(req.onerror)req.onerror({target:req});
                        tx.abort();
                      }finally{
                        pendingReqs--;
                        scheduleCheck();
                      }
                    });
                  }
                  step();
                  return req;
                },
              };
            },
          };
        }

        scheduleCheck();
        return tx;
      },
    };
  }

  return {
    stats,
    dbs,
    open(name,version=1){
      const req={result:null,error:null,onupgradeneeded:null,onsuccess:null,onerror:null};
      queueMicrotask(()=>{
        try{
          const state=makeDBState(name);
          const db=wrapDB(state);
          req.result=db;
          if(version>state.version){
            const oldVersion=state.version;
            state.version=version;
            if(req.onupgradeneeded)req.onupgradeneeded({oldVersion,newVersion:version,target:req});
          }
          if(req.onsuccess)req.onsuccess({target:req});
        }catch(err){
          req.error=err;
          if(req.onerror)req.onerror({target:req});
        }
      });
      return req;
    },
  };
}

async function seedLegacyV1(idb,dbName,owner,legacyWorkspace){
  const db=await new Promise((resolve,reject)=>{
    const req=idb.open(dbName,1);
    req.onupgradeneeded=()=>{
      for(const name of ['workspaces','catalog','preferences'])req.result.createObjectStore(name,{keyPath:'key'});
    };
    req.onsuccess=()=>resolve(req.result);
    req.onerror=()=>reject(req.error);
  });
  await new Promise((resolve,reject)=>{
    const tx=db.transaction('workspaces','readwrite');
    tx.objectStore('workspaces').put({key:owner,...legacyWorkspace});
    tx.oncomplete=resolve;
    tx.onerror=()=>reject(tx.error);
  });
}

test('legacy v1 workspace blob migrates transparently on first read with zero data loss',async()=>{
  const idb=createMockIDB();
  const baseTime=Date.parse('2026-10-10T00:00:00Z');
  const legacyEntries={};
  for(let i=1;i<=20;i++){
    const rec=newRecord(100+i,{now:baseTime+i*1000});
    rec.data.status=i%2===0 ? 'Watched' : 'Watchlist';
    rec.data.rating=i%2===0 ? (i%10)+1 : null;
    rec.data.favorite=i%5===0;
    rec.data.note='Note '+i;
    legacyEntries[rec.key]=rec;
  }
  const customRec=newRecord(null,{title:'Indie Short',year:2024,genre:'Drama',now:baseTime+30000});
  legacyEntries[customRec.key]=customRec;

  const legacyWorkspace={
    entries:legacyEntries,
    cursor:42,
    archive:[{id:'11111111-1111-4111-8111-111111111111',record_key:'tmdb:101',local_json:'{}',remote_json:'{}',remote_revision:2,created_at:iso(baseTime)}],
    generation:7,
    clock_offset:150,
    clock_last:iso(baseTime+30000),
    enabled:true,
    sharing:{is_public:true,revision:3},
    share_outbox:null,
    profile_pending:null,
    people:{entries:{'actor:6384':{data:{person_id:6384,role:'actor',favorite:true,edited_at:iso(baseTime)},baseline:null,revision:0,outbox:null}},cursor:1},
    recommendations:{history:{balanced:[603]},dismissed:[999]},
  };
  await seedLegacyV1(idb,'myshelf-web','user-v1',legacyWorkspace);

  const store=createStorage(idb,'myshelf-web');
  const migrated=await store.read('user-v1');

  assert.equal(Object.keys(migrated.entries).length,21);
  assert.deepEqual(migrated.entries['tmdb:102'],legacyEntries['tmdb:102']);
  assert.deepEqual(migrated.entries[customRec.key],customRec);
  assert.equal(migrated.cursor,42);
  assert.equal(migrated.generation,7);
  assert.equal(migrated.clock_offset,150);
  assert.deepEqual(migrated.sharing,{is_public:true,revision:3});
  assert.equal(migrated.people.entries['actor:6384'].data.favorite,true);
  assert.deepEqual(migrated.recommendations.dismissed,[999]);
  assert.equal(migrated.archive.length,1);

  // Verify raw v2 stores: workspaces no longer stores entries, entries store holds all 21 rows.
  const dbState=idb.dbs.get('myshelf-web');
  assert.equal(dbState.version,2);
  assert(dbState.stores.has('entries'));
  const rawWs=dbState.stores.get('workspaces').data.get(encodeKey('user-v1'));
  assert.equal(Object.hasOwn(rawWs,'entries'),false);
  assert.equal(dbState.stores.get('entries').data.size,21);

  // Subsequent read must be purely readonly with 0 writes.
  idb.stats.reset();
  const secondRead=await store.read('user-v1');
  assert.equal(Object.keys(secondRead.entries).length,21);
  assert.equal(idb.stats.transactions.length,1);
  assert.equal(idb.stats.transactions[0].mode,'readonly');
  assert.equal(idb.stats.puts.length,0);
});

test('legacy v1 workspace migrates transparently when first access is a write (edit)',async()=>{
  const idb=createMockIDB();
  const t0=Date.parse('2026-10-10T00:00:00Z');
  const recA=newRecord(501,{now:t0}),recB=newRecord(502,{now:t0+1000});
  await seedLegacyV1(idb,'myshelf-web','user-write-first',{
    entries:{[recA.key]:recA,[recB.key]:recB},
    cursor:0,archive:[],generation:1,clock_offset:0,clock_last:'',enabled:true,sharing:null,share_outbox:null,profile_pending:null,
  });

  const store=createStorage(idb,'myshelf-web');
  await store.edit('user-write-first','tmdb:501',{status:'Watched',rating:9,note:'Classic'});

  const work=await store.read('user-write-first');
  assert.equal(work.entries['tmdb:501'].data.status,'Watched');
  assert.equal(work.entries['tmdb:501'].data.rating,9);
  assert.equal(work.entries['tmdb:501'].data.note,'Classic');
  assert.deepEqual(work.entries['tmdb:502'],recB);
  const rawWs=idb.dbs.get('myshelf-web').stores.get('workspaces').data.get(encodeKey('user-write-first'));
  assert.equal(Object.hasOwn(rawWs,'entries'),false);
});

test('single-entry mutations isolate writes to affected entry only without rewriting unrelated films',async()=>{
  const idb=createMockIDB();
  const store=createStorage(idb,'myshelf-web');

  // Seed 60 films for user-a and 5 films for user-b.
  for(let i=1;i<=60;i++)await store.add('user-a',1000+i);
  for(let i=1;i<=5;i++)await store.add('user-b',2000+i);

  // 1. Edit 1 film -> only 1 entry read and 1 entry put; workspaces row stays lightweight.
  idb.stats.reset();
  await store.edit('user-a','tmdb:1042',{status:'Watched',rating:10,favorite:true,note:'Masterpiece'});
  const editEntryGets=idb.stats.gets.filter(g=>g.store==='entries');
  const editEntryPuts=idb.stats.puts.filter(p=>p.store==='entries');
  const editWsPuts=idb.stats.puts.filter(p=>p.store==='workspaces');
  assert.equal(editEntryGets.length,1);
  assert.deepEqual(editEntryGets[0].key,['user-a','tmdb:1042']);
  assert.equal(editEntryPuts.length,1);
  assert.deepEqual(editEntryPuts[0].key,['user-a','tmdb:1042']);
  assert.equal(editWsPuts.length,1);
  assert.equal(Object.hasOwn(editWsPuts[0].value,'entries'),false);

  // 2. Soft delete + restore via add -> each touches only that 1 entry.
  idb.stats.reset();
  await store.edit('user-a','tmdb:1042',{deleted_at:iso()});
  assert.equal(idb.stats.puts.filter(p=>p.store==='entries').length,1);
  idb.stats.reset();
  const restoredKey=await store.add('user-a',1042);
  assert.equal(restoredKey,'tmdb:1042');
  assert.equal(idb.stats.puts.filter(p=>p.store==='entries').length,1);
  assert.equal((await store.read('user-a')).entries['tmdb:1042'].data.deleted_at,null);

  // 3. next() + acknowledge() -> each writes only 1 entry row.
  idb.stats.reset();
  const op=await store.next('user-a');
  assert(op && op.record_key);
  assert.equal(idb.stats.puts.filter(p=>p.store==='entries').length,1);

  idb.stats.reset();
  await store.acknowledge('user-a',op,1);
  const ackPuts=idb.stats.puts.filter(p=>p.store==='entries');
  assert.equal(ackPuts.length,1);
  assert.deepEqual(ackPuts[0].key,['user-a',op.record_key]);

  // 4. reject() + resolve() -> each touches only the single affected entry.
  await store.edit('user-a',op.record_key,{note:'local draft'});
  const op2=await store.next('user-a');
  idb.stats.reset();
  await store.reject('user-a',op2,{
    revision:2,
    data:{...op2.data,note:'remote note'},
    field_versions:null,
  });
  const rejPuts=idb.stats.puts.filter(p=>p.store==='entries');
  assert.equal(rejPuts.length,1);
  assert.deepEqual(rejPuts[0].key,['user-a',op2.record_key]);
  assert.equal((await store.read('user-a')).entries[op2.record_key].conflict.revision,2);

  idb.stats.reset();
  await store.resolve('user-a',op2.record_key,'local',2);
  const resPuts=idb.stats.puts.filter(p=>p.store==='entries');
  assert.equal(resPuts.length,1);
  assert.deepEqual(resPuts[0].key,['user-a',op2.record_key]);
  const resolvedEntry=(await store.read('user-a')).entries[op2.record_key];
  assert.equal(resolvedEntry.conflict,null);
  assert.equal(resolvedEntry.data.note,'local draft');

  // 5. page() pull with 2 remote changes -> touches only those 2 keys.
  const remote1=newRecord(9001,{now:Date.parse('2026-10-12T00:00:00Z')}).data;
  const remote2=newRecord(9002,{now:Date.parse('2026-10-12T00:01:00Z')}).data;
  idb.stats.reset();
  await store.page('user-a',{
    protocol:1,
    cursor:2,
    changes:[
      {record_key:'tmdb:9001',revision:1,data:remote1,field_versions:{status:'2026-10-12T00:00:00.000000+00:00'}},
      {record_key:'tmdb:9002',revision:2,data:remote2,field_versions:{status:'2026-10-12T00:01:00.000000+00:00'}},
    ],
  });
  const pagePuts=idb.stats.puts.filter(p=>p.store==='entries');
  assert.equal(pagePuts.length,2);
  assert.deepEqual(pagePuts.map(p=>p.key[1]).sort(),['tmdb:9001','tmdb:9002']);

  // 6. Metadata-only mutate() -> writes 0 rows to entries store!
  idb.stats.reset();
  await store.mutate('user-a',w=>{w.clock_offset=500;w.enabled=false;});
  assert.equal(idb.stats.puts.filter(p=>p.store==='entries').length,0);
  assert.equal(idb.stats.puts.filter(p=>p.store==='workspaces').length,1);
  const workA=await store.read('user-a'),workB=await store.read('user-b');
  assert.equal(workA.clock_offset,500);
  assert.equal(workA.enabled,false);
  assert.equal(Object.keys(workA.entries).length,62);
  assert.equal(Object.keys(workB.entries).length,5);
  assert.equal(pending(workB),5);
});

test('exportLibrary, importLibrary, copyGuest and aborted writes preserve full compatibility',async()=>{
  const idb=createMockIDB();
  const store=createStorage(idb,'myshelf-web');
  await store.add('guest',603);
  await store.edit('guest','tmdb:603',{status:'Watched',rating:9,favorite:true});
  await store.add('guest',null,{title:'My Film',year:2025,genre:'Sci-Fi'});

  const copied=await store.copyGuest('acct-1');
  assert.equal(copied,2);
  // Repeating copyGuest does not rewrite existing entries.
  idb.stats.reset();
  const copiedAgain=await store.copyGuest('acct-1');
  assert.equal(copiedAgain,0);
  assert.equal(idb.stats.puts.filter(p=>p.store==='entries').length,0);

  const exported=await store.exportLibrary('acct-1');
  assert.equal(exported.records.length,2);
  const importedCount=await store.importLibrary('acct-2',exported);
  assert.equal(importedCount,2);
  const acct2=await store.read('acct-2');
  assert.equal(acct2.entries['tmdb:603'].data.rating,9);

  // Invalid edits reject and do not corrupt state.
  await assert.rejects(()=>store.edit('acct-2','tmdb:999999',{rating:5}),/not_found/);
  await assert.rejects(()=>store.edit('acct-2','tmdb:603',{rating:99}),/invalid_record/);
  assert.equal((await store.read('acct-2')).entries['tmdb:603'].data.rating,9);
});

test('metadataBatch fetches many catalog keys in a single readonly IndexedDB transaction',async()=>{
  const idb=createMockIDB();
  const store=createStorage(idb,'myshelf-web');

  for(let i=1;i<=60;i++){
    await store.cacheMetadata('en:'+i,{id:i,title:'English Film '+i,poster_path:'/p'+i+'.jpg'});
    await store.cacheMetadata('tr:'+i,{id:i,title:'Türkçe Film '+i,poster_path:'/p'+i+'.jpg'});
  }

  // Empty batch opens zero transactions.
  idb.stats.reset();
  assert.deepEqual(await store.metadataBatch([]),{});
  assert.equal(idb.stats.transactions.length,0);

  // 120 keys + duplicates + missing keys -> exactly 1 readonly transaction on catalog!
  const keys=[];
  for(let i=1;i<=60;i++)keys.push('en:'+i,'tr:'+i);
  keys.push('en:1','tr:1','en:9999');

  idb.stats.reset();
  const batch=await store.metadataBatch(keys);

  assert.equal(idb.stats.transactions.length,1);
  assert.deepEqual(idb.stats.transactions[0],{stores:['catalog'],mode:'readonly'});
  // Duplicates are deduplicated before issuing .get() requests (120 + 1 missing = 121).
  assert.equal(idb.stats.gets.length,121);
  assert.equal(batch['en:1'].title,'English Film 1');
  assert.equal(batch['tr:60'].title,'Türkçe Film 60');
  assert.equal(batch['en:9999'],null);
});

test('large-library pagination slices 48 films per page with accurate progress and filter resets',()=>{
  assert.equal(LIBRARY_PAGE_SIZE,48);
  const base=Date.parse('2026-01-01T00:00:00Z');
  const entries={};

  // Create 240 active films + 15 soft-deleted films.
  for(let i=1;i<=240;i++){
    const isCustom=i%50===0;
    const rec=newRecord(isCustom ? null : 1000+i,{
      title:isCustom ? 'Custom '+i : '',
      year:isCustom ? 2020 : null,
      now:base+i*1000,
    });
    rec.data.status=i<=120 ? 'Watched' : 'Watchlist';
    rec.data.favorite=i%10===0;
    entries[rec.key]=rec;
  }
  for(let i=1;i<=15;i++){
    const rec=newRecord(5000+i,{now:base+500000+i*1000});
    rec.data.deleted_at=iso(base+600000+i*1000);
    entries[rec.key]=rec;
  }

  // Page 1: 48 / 240
  const p1=sliceLibrary(entries,{filter:'all',page:1});
  assert.equal(p1.shown,48);
  assert.equal(p1.total,240);
  assert.equal(p1.hasMore,true);
  assert.equal(p1.items.length,48);
  // Descending order_key (newest added first), deleted films excluded.
  assert(p1.items[0].data.order_key>p1.items[1].data.order_key);
  assert(p1.items.every(x=>!x.data.deleted_at));

  // Page 2: 96 / 240
  const p2=sliceLibrary(entries,{filter:'all',page:2});
  assert.equal(p2.shown,96);
  assert.equal(p2.total,240);
  assert.equal(p2.hasMore,true);
  assert.deepEqual(p2.items.slice(0,48).map(x=>x.key),p1.items.map(x=>x.key));

  // Page 5: 240 / 240 (last page)
  const p5=sliceLibrary(entries,{filter:'all',page:5});
  assert.equal(p5.shown,240);
  assert.equal(p5.total,240);
  assert.equal(p5.hasMore,false);

  // Overshooting page clamps cleanly to total.
  const p99=sliceLibrary(entries,{filter:'all',page:99});
  assert.equal(p99.shown,240);
  assert.equal(p99.hasMore,false);

  // Filter slices reset cleanly to page 1.
  const watchedP1=sliceLibrary(entries,{filter:'watched',page:1});
  assert.equal(watchedP1.shown,48);
  assert.equal(watchedP1.total,120);
  assert.equal(watchedP1.hasMore,true);
  assert(watchedP1.items.every(x=>x.data.status==='Watched'));

  const watchlistP1=sliceLibrary(entries,{filter:'watchlist',page:1});
  assert.equal(watchlistP1.shown,48);
  assert.equal(watchlistP1.total,120);
  assert.equal(watchlistP1.hasMore,true);

  const favP1=sliceLibrary(entries,{filter:'favorites',page:1});
  assert.equal(favP1.shown,24);
  assert.equal(favP1.total,24);
  assert.equal(favP1.hasMore,false);

  // Metadata keys collect primary + fallback for TMDB entries only (skipping custom films).
  const keys=libraryMetadataKeys(p1.items,'tr');
  const customInP1=p1.items.filter(x=>x.data.custom).length;
  assert.equal(keys.length,(48-customInP1)*2);
  assert(keys[0].startsWith('tr:'));
  assert(keys[1].startsWith('en:'));
});
