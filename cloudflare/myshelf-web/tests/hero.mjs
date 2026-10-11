import assert from 'node:assert/strict';
import {test} from 'node:test';
import {dailyPosters,posterPicks} from '../public/hero.mjs';

const film=(id,title='Film')=>({id,title,poster_path:'/poster.jpg',adult:false});
function fixture(){
  const records=new Map(),calls=[];
  return {records,calls,pref:async(key,value)=>value===undefined?records.get(key):records.set(key,value),fetchCatalog:async path=>{calls.push(path);return {results:[film(calls.length)]};}};
}
test('daily posters refresh on the UTC date change, with independent translated caches',async()=>{
  const f=fixture(),day=new Date('2026-10-11T20:00:00Z');
  const first=await dailyPosters('tr',{...f,now:day});
  assert.deepEqual(await dailyPosters('tr',{...f,now:new Date('2026-10-11T23:59:59Z')}),first);
  assert.equal(f.calls.length,1);
  await dailyPosters('en',{...f,now:day});
  assert.equal(f.calls[1],'catalog/trending/movie/day?language=en-US');
  const next=await dailyPosters('tr',{...f,now:new Date('2026-10-12T00:00:00Z')});
  assert.equal(next.day,'2026-10-12');assert.notEqual(next.films[0].id,first.films[0].id);
});
test('an unavailable or empty daily catalog preserves the old selection and retries later',async()=>{
  const f=fixture();await dailyPosters('tr',{...f,now:new Date('2026-10-11')});
  for(const fetchCatalog of [async()=>{throw Error('offline');},async()=>({results:[]})]){
    const old=await dailyPosters('tr',{...f,fetchCatalog,now:new Date('2026-10-12')});
    assert.equal(old.day,'2026-10-11');assert.equal(f.records.get('hero-posters:tr').day,'2026-10-11');
  }
  assert.equal((await dailyPosters('tr',{...f,now:new Date('2026-10-12')})).day,'2026-10-12');
});
test('poster picks keep numeric film identity, exclude adult/missing posters and remove duplicates',()=>{
  assert.deepEqual(posterPicks([null,{...film(1),adult:true},{...film(2),poster_path:null},film(3),film(3),film(4),film(5),film(6),film(7)]).map(m=>m.id),[3,4,5,6]);
});
test('a browser cache write failure does not hide a valid public catalog response',async()=>{
  const result=await dailyPosters('en',{pref:async()=>{throw Error('storage unavailable');},fetchCatalog:async()=>({results:[film(603)]})});
  assert.equal(result.films[0].id,603);
});
