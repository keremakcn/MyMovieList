import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFile} from 'node:fs/promises';
import {ALGORITHM_VERSION,buildProfile,profileFingerprint,rankCandidates} from '../public/recommendation-model.mjs';
const fixtures=JSON.parse(await readFile(new URL('./recommendation-parity.json',import.meta.url),'utf8'));
test('browser ranking and preference evidence agree with the native algorithm across 42 cases',async()=>{
  assert.equal(ALGORITHM_VERSION,fixtures.native_algorithm);
  for(const c of fixtures.cases){
    const p=buildProfile(c.library,c.options.today),native=c.profile;
    for(const k of ['count','ready','baseline'])assert.equal(p[k],native[k],c.name+' '+k);
    assert(Math.abs(p.confidence-native.confidence)<1e-12,c.name+' confidence');
    for(const [group,values] of Object.entries(native.features)){
      assert.equal(p.features[group].size,Object.keys(values).length,c.name+' '+group);
      for(const [key,value] of p.features[group])assert(Math.abs(value-values[String(key)])<1e-12,c.name+' '+group+' '+key);
    }
    const ranked=await rankCandidates(c.candidates,p,c.options);
    assert.deepEqual(ranked.map(m=>({id:m.tmdb_id,highlight:m.recommendation_highlight})),c.ranked,c.name);
  }
});
test('private notes and localized titles do not affect preference identity or ranking',async()=>{
  const c=fixtures.cases.find(c=>c.name==='mixed-balanced-stable');
  const altered=c.library.map(m=>({...m,title:'Yerelleştirilmiş ad',note:'PRIVATE NOTE',overview:'Translated synopsis'}));
  const one=buildProfile(c.library,c.options.today),two=buildProfile(altered,c.options.today);
  assert.equal(profileFingerprint(one),profileFingerprint(two));
  assert.deepEqual((await rankCandidates(c.candidates,one,c.options)).map(m=>m.id),(await rankCandidates(c.candidates,two,c.options)).map(m=>m.id));
});
