import assert from 'node:assert/strict';
import {test} from 'node:test';
import {createRecommender,publicMovie} from '../public/recommendation-catalog.mjs';
const movie=id=>({id,title:'Film '+id,genre_ids:[id%2?28:35],original_language:'en',release_date:'2000-01-01',vote_count:5000,vote_average:8,poster_path:'/poster.jpg'});
function fixture(){
  const works=new Map(),catalog=new Map(),prefs=new Map(),calls=[];
  const store={read:async owner=>structuredClone(works.get(owner)||{entries:{}}),mutate:async(owner,fn)=>{const copy=structuredClone(works.get(owner)||{entries:{}});const result=fn(copy);works.set(owner,copy);return result;},metadata:async key=>catalog.get(key)||null,cacheMetadata:async(key,data)=>catalog.set(key,{...catalog.get(key),...data}),pref:async(key,value)=>value===undefined?prefs.get(key):prefs.set(key,value)};
  const fetchCatalog=async path=>{
    calls.push(path);
    if(path.startsWith('catalog/discover/'))return {results:Array.from({length:20},(_,i)=>movie(1000+i))};
    const id=Number(/movie\/(\d+)/.exec(path)[1]);return {...movie(id),genres:[{id:28}],credits:{cast:[{id:6384,name:'Actor'}],crew:[{id:9340,job:'Director'}]},keywords:{keywords:[{id:100}]}};
  };
  return {works,catalog,prefs,calls,store,fetchCatalog};
}
test('public feature projection strips personal fields and validates identity',()=>{
  const data=publicMovie({...movie(1),note:'PRIVATE',rating:10,favorite:true,access_token:'SECRET'});
  for(const key of ['note','rating','favorite','access_token'])assert(!Object.hasOwn(data,key));
  assert.equal(publicMovie({...movie(1),adult:true}),null);
});
test('discovery requests are fixed public queries, cached and independent of private preferences',async()=>{
  const f=fixture();f.works.set('A',{entries:{'tmdb:5':{key:'tmdb:5',data:{rating:9,favorite:true,note:'DO NOT UPLOAD',deleted_at:null,custom:null}}}});
  const service=createRecommender(f.store,f.fetchCatalog,{online:()=>true});
  const first=await service.recommend('A',{isCurrent:()=>true});assert.equal(first.movies.length,10);assert.equal(first.profile.count,1);
  assert(f.calls.filter(p=>p.startsWith('catalog/discover')).length===10);
  assert(f.calls.every(p=>!p.includes('DO NOT UPLOAD')&&!p.includes('rating=')&&!p.includes('with_cast')&&!p.includes('with_people')&&!p.includes('with_keywords')));
  assert([...f.catalog.values()].every(v=>!Object.hasOwn(v,'note')));
  const firstIDs=first.movies.map(m=>m.id),count=f.calls.length;
  const again=await service.recommend('A');assert.deepEqual(again.movies.map(m=>m.id),firstIDs);assert.equal(f.calls.length,count);
  await service.dismiss('A',firstIDs[0]);const changed=await service.recommend('A');assert(!changed.movies.some(m=>m.id===firstIDs[0]));
  const other=await service.recommend('B');assert.equal(other.profile.count,0);assert(!f.works.get('B').recommendations.dismissed.length);
});
test('offline cached discovery remains usable and stale views stop before preference writes',async()=>{
  const f=fixture();f.prefs.set('recommendation-public-catalog-v3',{version:'3',movies:Array.from({length:15},(_,i)=>movie(1000+i)),next_page:2,fetched_at:0});
  const offline=createRecommender(f.store,()=>{throw Error('must stay offline');},{online:()=>false});
  assert.equal((await offline.recommend('guest')).movies.length,10);
  const before=structuredClone(f.works.get('guest'));
  await assert.rejects(()=>offline.recommend('guest',{refresh:true,isCurrent:()=>false}),/stale_view/);
  assert.deepEqual(f.works.get('guest'),before);
});

test('translated presentation preserves film identity and never changes the frozen ranking',async()=>{
  const f=fixture(),original=f.fetchCatalog;
  const service=createRecommender(f.store,async path=>{
    const raw=await original(path);
    return path.includes('language=tr-TR')?{...raw,title:'Türkçe '+raw.id}:raw;
  },{online:()=>true});
  const english=await service.recommend('guest',{lang:'en'}),before=f.calls.length;
  const turkish=await service.recommend('guest',{lang:'tr'});
  assert.deepEqual(turkish.movies.map(m=>m.id),english.movies.map(m=>m.id));
  assert(turkish.movies.every(m=>m.title==='Türkçe '+m.id));
  assert.equal(f.calls.length-before,10);
  const translatedCalls=f.calls.length;
  await service.recommend('guest',{lang:'tr'});
  assert.equal(f.calls.length,translatedCalls,'translated public metadata is reused');
  assert([...f.catalog.values()].every(v=>!Object.hasOwn(v,'rating')&&!Object.hasOwn(v,'note')));
});

test('learning can hydrate an incomplete library card without losing the personal signal',async()=>{
  const f=fixture();
  f.works.set('guest',{entries:{'tmdb:5':{key:'tmdb:5',data:{rating:9,favorite:true,note:'PRIVATE',deleted_at:null,custom:null}}}});
  f.catalog.set('tr:5',{...movie(5),genre_ids:[],title:'Kütüphanedeki ad'});
  const result=await createRecommender(f.store,f.fetchCatalog,{online:()=>true}).recommend('guest');
  assert.equal(result.profile.count,1);
  assert(result.profile.features.genres.has(28));
  assert(!result.profile.features.genres.has(35));
  assert.equal(f.works.get('guest').entries['tmdb:5'].data.note,'PRIVATE');
});

test('a failed refresh retains the usable selection and public cache',async()=>{
  const f=fixture();let available=true;
  const service=createRecommender(f.store,path=>available?f.fetchCatalog(path):Promise.reject(Error('upstream unavailable')),{online:()=>true});
  const first=await service.recommend('guest');
  const cached=structuredClone(f.prefs.get('recommendation-public-catalog-v3'));
  available=false;
  const next=await service.recommend('guest',{refresh:true});
  assert.deepEqual(next.movies.map(m=>m.id),first.movies.map(m=>m.id));
  assert(next.unavailable);
  assert.deepEqual(f.prefs.get('recommendation-public-catalog-v3'),cached);
});

test('a library restored while discovery loads supplies evidence and excludes the restored film',async()=>{
  const f=fixture();let restored=false;
  const service=createRecommender(f.store,async path=>{
    if(!restored && path.startsWith('catalog/discover/')){
      restored=true;
      f.works.set('account',{entries:{'tmdb:1000':{key:'tmdb:1000',data:{rating:9,favorite:true,note:'PRIVATE CLOUD NOTE',deleted_at:null,custom:null}}}});
    }
    return f.fetchCatalog(path);
  },{online:()=>true});
  const result=await service.recommend('account');
  assert.equal(result.profile.count,1);
  assert(!result.movies.some(m=>m.id===1000));
  assert.equal(f.works.get('account').entries['tmdb:1000'].data.note,'PRIVATE CLOUD NOTE');
  assert(f.calls.every(path=>!path.includes('PRIVATE CLOUD NOTE')));
});
