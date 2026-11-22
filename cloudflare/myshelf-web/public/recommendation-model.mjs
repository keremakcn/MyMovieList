// Browser port of recommendation_model.py v3. No network, notes or display-language scoring.
export const ALGORITHM_VERSION='3';
export const GENRES={28:'Action',12:'Adventure',16:'Animation',35:'Comedy',80:'Crime',99:'Documentary',18:'Drama',10751:'Family',14:'Fantasy',36:'History',27:'Horror',10402:'Music',9648:'Mystery',10749:'Romance',878:'Science Fiction',10770:'TV Movie',53:'Thriller',10752:'War',37:'Western'};
const WEIGHTS={genres:.34,keywords:.30,directors:.19,cast:.11,decades:.04,languages:.02};
const PRIORS={genres:4,keywords:5,directors:3,cast:5,decades:8,languages:8};
const POLICIES={familiar:{fit:2,novelty:.08,familiar_slots:8,diversity:.2},balanced:{fit:1.35,novelty:.32,familiar_slots:5,diversity:.4},explore:{fit:.8,novelty:.58,familiar_slots:2,diversity:.6}};
const groups=Object.keys(WEIGHTS), sum=values=>[...values].reduce((a,b)=>a+b,0);
const positiveIds=values=>new Set(Array.isArray(values)?values.filter(v=>Number.isInteger(v)&&v>0):[]);
const intersection=(a,b)=>new Set([...a].filter(x=>b.has(x)));
const increment=(map,key,value=1)=>map.set(key,(map.get(key)||0)+value);
const lex=(a,b)=>String(a)<String(b)?-1:String(a)>String(b)?1:0;
const fold=value=>value.toLowerCase().replaceAll('ß','ss').replaceAll('ς','σ');
export const todayUTC=()=>new Date().toISOString().slice(0,10);
export function validDate(value){
  return typeof value==='string' && /^\d{4}-\d{2}-\d{2}$/.test(value) && Number(value.slice(0,4))>0 && !Number.isNaN(Date.parse(value+'T00:00:00Z')) && new Date(value+'T00:00:00Z').toISOString().slice(0,10)===value;
}
export function validCandidate(raw){
  const id=raw?.id ?? raw?.tmdb_id, votes=raw?.vote_count ?? 0, average=raw?.vote_average ?? 0, released=raw?.release_date || '';
  return !!raw && typeof raw==='object' && !Array.isArray(raw) && Number.isInteger(id)&&id>0 && typeof raw.title==='string' && !raw.adult && Array.isArray(raw.genre_ids ?? []) && Number.isInteger(votes)&&votes>=0 && typeof average==='number'&&Number.isFinite(average)&&average>=0&&average<=10 && (!released || validDate(released));
}
export function movieFeatures(movie,today=todayUTC()){
  let entities=movie.entities;
  if(!entities || typeof entities!=='object' || Array.isArray(entities)){
    try{entities=JSON.parse(movie.entities_json || '{}');}catch{entities={};}
  }
  if(!entities || typeof entities!=='object' || Array.isArray(entities))entities={};
  const people=(group,limit=Infinity)=>new Set((Array.isArray(entities[group])?entities[group]:[]).filter(p=>Number.isInteger(p?.id)&&p.id>0).map(p=>p.id).filter((id,i,all)=>all.indexOf(id)===i).slice(0,limit));
  let genres=new Set([...positiveIds(movie.genre_ids)].filter(id=>Object.hasOwn(GENRES,id)));
  if(!genres.size)genres=new Set((movie.genre || '').split(',').map(name=>Object.keys(GENRES).find(id=>GENRES[id].toLowerCase()===name.trim().toLowerCase())).filter(Boolean).map(Number));
  let directors=people('directors');
  if(!directors.size)directors=new Set((movie.director || '').split(',').filter(n=>n.trim()).map(n=>'legacy:'+fold(n.trim())));
  const year=movie.year || (/^\d{4}/.test(movie.release_date || '')?Number(movie.release_date.slice(0,4)):null);
  return {genres,keywords:positiveIds(movie.keyword_ids),directors,cast:people('cast',6),
    decades:new Set(Number.isInteger(year)&&year>=1880&&year<=Number(today.slice(0,4))?[Math.floor(year/10)*10]:[]),
    languages:new Set(typeof movie.original_language==='string'&&movie.original_language.length===2?[movie.original_language]:[]),
    collection:Number.isInteger(movie.collection_id)&&movie.collection_id>0?movie.collection_id:null};
}
function preferenceSignal(movie,baseline){
  if(movie.rating!=null){
    const signal=Math.max(-1,Math.min(1,.7*(movie.rating-6)/4+.3*(movie.rating-baseline)/3));
    if(movie.rating<=4)return Math.min(signal,-.5);
    return movie.favorite?Math.max(signal,.8):signal;
  }
  return movie.favorite?.valueOf()? .85:movie.survey_liked?.valueOf()? .6:0;
}
export function buildProfile(movies,today=todayUTC()){
  const ratings=movies.filter(m=>m.rating!=null).map(m=>m.rating), baseline=ratings.length?sum(ratings)/ratings.length:6;
  const signals=[],related=new Map();
  for(const movie of movies){
    const signal=preferenceSignal(movie,baseline);if(Math.abs(signal)<.1)continue;
    const features=movieFeatures(movie,today),group=JSON.stringify(features.collection?['collection',features.collection]:features.directors.size?['directors',[...features.directors].sort(lex)]:['film',movie.tmdb_id || movie.id]);
    increment(related,group);signals.push({movie,signal,features,genres:features.genres,group});
  }
  const sums=Object.fromEntries(groups.map(g=>[g,new Map()])),supports=Object.fromEntries(groups.map(g=>[g,new Map()])),magnitudes=Object.fromEntries(groups.map(g=>[g,new Map()])),hits=Object.fromEntries(groups.map(g=>[g,new Map()]));
  const interests=new Map(),themes=new Map();let positiveMass=0,effective=0;
  for(const entry of signals){
    const weight=1/Math.sqrt(related.get(entry.group));entry.weight=weight;
    if(groups.some(g=>entry.features[g].size))effective+=weight;
    for(const group of groups){
      const tokens=entry.features[group],tokenWeight=weight/Math.sqrt(Math.max(1,tokens.size));
      for(const token of tokens){increment(sums[group],token,entry.signal*tokenWeight);increment(supports[group],token,tokenWeight);increment(magnitudes[group],token,Math.abs(entry.signal)*tokenWeight);increment(hits[group],token);}
    }
    if(entry.signal>0){
      const mass=entry.signal*weight;positiveMass+=mass;
      for(const genre of entry.genres)increment(interests,genre,mass/Math.max(1,entry.genres.size));
      for(const keyword of entry.features.keywords)increment(themes,keyword,mass);
    }
  }
  const features=Object.fromEntries(groups.map(g=>[g,new Map([...sums[g]].map(([token,value])=>[token,value/(supports[g].get(token)+PRIORS[g])]))]));
  let agreement=sum(groups.map(g=>WEIGHTS[g]*sum([...sums[g].values()].map(Math.abs)))), magnitude=sum(groups.map(g=>WEIGHTS[g]*sum(magnitudes[g].values())));
  agreement=magnitude?agreement/magnitude:0;
  const confidence=effective/(effective+8)*(.4+.6*agreement),total=sum(interests.values());
  return {affinities:features.genres,features,supports,hits,signals,confidence,count:signals.length,ready:confidence>=.45,
    interests:new Map([...interests].map(([g,v])=>[g,total?v/total:0])),themes:new Map([...themes].map(([k,v])=>[k,positiveMass?v/positiveMass:0])),baseline,algorithm_version:ALGORITHM_VERSION};
}
export function profileFingerprint(profile){
  const values=profile.signals.map(entry=>[entry.movie.tmdb_id || entry.movie.id,Math.round(entry.signal*1e8)/1e8,groups.map(g=>[g,[...entry.features[g]].sort(lex)]),entry.features.collection]);
  return JSON.stringify(values.sort((a,b)=>a[0]-b[0]));
}
export function scoreFeatures(features,profile){
  const affinities=profile.features,active=sum(groups.filter(g=>affinities[g].size).map(g=>WEIGHTS[g])) || 1;
  let fit=0,negative=0,familiarity=0,matchedWeight=0;
  for(const group of groups){
    const tokens=features[group],weight=WEIGHTS[group];if(!tokens.size || !affinities[group].size)continue;
    const values=[...tokens].map(t=>affinities[group].get(t)||0);
    const positive=['directors','cast'].includes(group)?Math.max(0,...values):sum(values.map(v=>Math.max(0,v)))/values.length;
    fit+=weight*positive;negative+=weight*sum(values.map(v=>Math.min(0,v)))/values.length;
    familiarity+=weight*values.filter(v=>v>.05).length/values.length;matchedWeight+=weight;
  }
  return {fit:fit/active,negative:negative/active,familiarity:matchedWeight?familiarity/matchedWeight:0};
}
function featureSimilarity(left,right){
  let total=0,weight=0;
  for(const group of ['genres','keywords','directors','cast']){
    const a=left[group],b=right[group];if(!a.size || !b.size)continue;
    total+=WEIGHTS[group]*intersection(a,b).size/new Set([...a,...b]).size;weight+=WEIGHTS[group];
  }
  return weight?total/weight:0;
}
export function recognitionSignals(movie,quality,today=todayUTC()){
  const votes=movie.vote_count || 0, recognition=Math.min(1,Math.log10(1+votes/100)/2), reception=Math.min(1,Math.max(0,(quality-.64)/.16));
  const age=movie.release_date?(Date.parse(today+'T00:00:00Z')-Date.parse(movie.release_date+'T00:00:00Z'))/86400000/365.2425:null;
  const classic=age!=null&&age>=10&&votes>=1000&&(movie.vote_average || 0)>=7.4;
  let prominence=0;
  for(const person of (Array.isArray(movie.entities?.cast)?movie.entities.cast:[]).slice(0,3)){
    const popularity=person?.popularity || 0;
    if(typeof popularity==='number'&&Number.isFinite(popularity))prominence=Math.max(prominence,Math.min(1,Math.max(0,(Math.log1p(Math.max(0,popularity))-Math.log(11))/(Math.log(101)-Math.log(11)))));
  }
  const recentCast=age!=null&&age>=0&&age<=4&&votes>=50?prominence*(1-age/5):0;
  return {bonus:reception*(.18*recognition+.22*Number(classic)*recognition+.14*recentCast),classic};
}
export async function rankCandidates(candidates,profile,{excluded=[],mode='balanced',limit=10,previous=[],seed='',today=todayUTC()}={}){
  const policy=POLICIES[mode] || POLICIES.balanced, familiarSlots=!profile.ready&&mode==='familiar'?6:policy.familiar_slots;
  const pool=[],seen=new Set(excluded),recent=new Set(previous),positiveGenres=new Set([...profile.affinities].filter(([,v])=>v>.05).map(([g])=>g));
  const richEvidence=['keywords','directors','cast'].some(g=>[...profile.features[g].values()].some(v=>v>=.15));
  const strongest=new Map(),random=new Map();
  if(seed)await Promise.all(candidates.filter(validCandidate).map(async raw=>{
    const id=raw.id ?? raw.tmdb_id,bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(`${seed}:${mode}:${id}`));random.set(id,new DataView(bytes).getUint32(0)/2**32*.035);
  }));
  for(const entry of profile.signals)if(entry.signal>0)for(const genre of entry.genres)if(!strongest.has(genre)||entry.signal>strongest.get(genre).signal)strongest.set(genre,entry);
  for(const raw of candidates){
    if(!validCandidate(raw))continue;
    const id=raw.id ?? raw.tmdb_id;
    if(seen.has(id)||(raw.release_date || '')>today)continue;seen.add(id);
    const features=movieFeatures(raw,today),scored=scoreFeatures(features,profile);
    const stronglyNegative=['genres','keywords'].some(g=>[...features[g]].some(t=>(profile.features[g].get(t)||0)<-.35&&(profile.hits[g].get(t)||0)>=3));
    if(stronglyNegative&&scored.fit<.05)continue;
    const votes=Math.max(0,raw.vote_count || 0),quality=((raw.vote_average || 0)*votes+600)/(votes+100)/10;
    let score=.45*quality+policy.fit*scored.fit+1.8*scored.negative+policy.novelty*(1-scored.familiarity);
    const recognition=recognitionSignals(raw,quality,today),gate=profile.ready?.25+.75*Math.min(1,Math.max(0,scored.fit)/.2):1;
    score+=recognition.bonus*gate*({familiar:1.15,balanced:1,explore:.55}[mode] || 1)+(random.get(id)||0);
    const genreFamiliarity=intersection(features.genres,positiveGenres).size/Math.max(1,features.genres.size),richMatch=['keywords','directors','cast'].some(g=>[...features[g]].some(t=>(profile.features[g].get(t)||0)>=.15));
    const familiar=genreFamiliarity>=.5&&(!richEvidence||scored.familiarity>=.65)||richMatch&&scored.fit>=.10&&scored.familiarity>=.35;
    const evidence=[...features.genres].filter(g=>strongest.has(g)).map(g=>strongest.get(g));
    const liked=evidence.length?evidence.reduce((a,b)=>a.signal>=b.signal?a:b).movie.title || 'a film you liked':null;
    pool.push({raw:{...raw,id},score,features,familiar,recent:recent.has(id),overlap:0,liked,classic:recognition.classic});
  }
  const selected=[],directors=new Map(),collections=new Map(),keywords=new Map(),interests=new Map();let familiarCount=0;
  while(pool.length&&selected.length<limit){
    let eligible=pool.filter(p=>!p.recent);if(!eligible.length)eligible=pool;
    const unconcentrated=eligible.filter(p=>{
      const f=p.features;
      return !(f.collection&&(collections.get(f.collection)||0)>=1 || [...f.directors].some(d=>(directors.get(d)||0)>=2) || [...f.keywords].some(k=>(keywords.get(k)||0)>=Math.max(2,Math.ceil(10*(profile.themes.get(k)||0)+1))));
    });
    if(unconcentrated.length)eligible=unconcentrated;
    const slot=selected.length%10,offset=10-familiarSlots,wantFamiliar=Math.floor(((slot+1)*familiarSlots+offset)/10)>Math.floor((slot*familiarSlots+offset)/10);
    const lane=eligible.filter(p=>p.familiar===wantFamiliar);if(positiveGenres.size&&lane.length)eligible=lane;
    if(wantFamiliar&&positiveGenres.size){
      const available=new Set(eligible.filter(p=>p.familiar).flatMap(p=>[...intersection(p.features.genres,positiveGenres)]));
      if(available.size){
        const target=[...available].sort((a,b)=>((profile.interests.get(b)||0)*(familiarCount+1)-(interests.get(b)||0))-((profile.interests.get(a)||0)*(familiarCount+1)-(interests.get(a)||0)) || a-b)[0];
        const matching=eligible.filter(p=>p.familiar&&p.features.genres.has(target));if(matching.length)eligible=matching;
      }
    }
    const best=eligible.reduce((a,b)=>a.score-policy.diversity*a.overlap>b.score-policy.diversity*b.overlap || a.score-policy.diversity*a.overlap===b.score-policy.diversity*b.overlap&&a.raw.id<b.raw.id?a:b);
    pool.splice(pool.indexOf(best),1);selected.push(best);
    for(const d of best.features.directors)increment(directors,d);
    for(const k of best.features.keywords)increment(keywords,k);
    if(best.features.collection)increment(collections,best.features.collection);
    if(best.familiar){familiarCount++;const genres=intersection(best.features.genres,positiveGenres);for(const g of genres)increment(interests,g,1/Math.max(1,genres.size));}
    for(const p of pool)p.overlap=Math.max(p.overlap,featureSimilarity(p.features,best.features));
  }
  return selected.map(p=>({...p.raw,tmdb_id:p.raw.id,reason:p.liked?`Shares an interest with ${p.liked}.`:'A discovery pick to broaden your selection.',liked_title:p.liked,recommendation_highlight:p.classic?'Acclaimed classic':''}));
}
