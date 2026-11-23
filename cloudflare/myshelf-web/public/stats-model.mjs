// Pure local Cinema Statistics engine for MyShelf Web.
import {entryTitle,entryYear,foldTitle,tmdbIdOf} from './library-model.mjs';
import {GENRES} from './recommendation-model.mjs';

const TR_GENRES={
  28:'Aksiyon',12:'Macera',16:'Animasyon',35:'Komedi',80:'Suç',99:'Belgesel',18:'Dram',
  10751:'Aile',14:'Fantastik',36:'Tarih',27:'Korku',10402:'Müzik',9648:'Gizem',
  10749:'Romantik',878:'Bilim-Kurgu',10770:'TV Filmi',53:'Gerilim',10752:'Savaş',37:'Western',
};

const round1=value=>Math.round(value*10)/10;
const validRating=r=>Number.isInteger(r) && r>=1 && r<=10;
const orderKey=x=>String(x?.data?.order_key || '');
const RING_CIRCUMFERENCE=251;
const MAX_RUNTIME=1000;
const DATE_RE=/^(\d{4})-(\d{2})(?:-(\d{2}))?(?:$|[T ])/;

function medianOf(values){
  if(!values.length)return null;
  const ordered=[...values].sort((a,b)=>a-b);
  const mid=Math.floor(ordered.length/2);
  return ordered.length%2===1 ? ordered[mid] : round1((ordered[mid-1]+ordered[mid])/2);
}

function longestStreakOf(dayEpochSet){
  if(!dayEpochSet.size)return 0;
  const ordered=[...dayEpochSet].sort((a,b)=>a-b);
  let best=1,current=1;
  for(let i=1;i<ordered.length;i++){
    if(ordered[i]-ordered[i-1]===1){
      current++;
      if(current>best)best=current;
    }else{
      current=1;
    }
  }
  return best;
}

function lookup(map,key){
  if(!map || typeof map!=='object' || !Object.hasOwn(map,key))return null;
  const v=map[key];
  return v && typeof v==='object' ? v : null;
}

// Merge localized + fallback metadata so localized titles pair with cached runtime/credits/genres from either key.
function resolvedMetadata(entry,metadataMap,lang='en'){
  const id=tmdbIdOf(entry);
  if(id===null)return null;
  const fallback=lang==='tr' ? 'en' : 'tr';
  const primary=lookup(metadataMap,lang+':'+id);
  const secondary=lookup(metadataMap,fallback+':'+id);
  const generic=lookup(metadataMap,'tmdb:'+id) || lookup(metadataMap,String(id));
  const features=lookup(metadataMap,'recommendation-features:'+id);
  if(!primary && !secondary && !generic && !features)return null;
  return {...features,...generic,...secondary,...primary,
    runtime:primary?.runtime ?? secondary?.runtime ?? generic?.runtime ?? null,
    genres:primary?.genres?.length ? primary.genres : secondary?.genres?.length ? secondary.genres : generic?.genres || null,
    genre_ids:primary?.genre_ids?.length ? primary.genre_ids : secondary?.genre_ids?.length ? secondary.genre_ids : generic?.genre_ids ?? features?.genre_ids ?? null,
    credits:primary?.credits?.cast || primary?.credits?.crew ? primary.credits : secondary?.credits?.cast || secondary?.credits?.crew ? secondary.credits : generic?.credits || null,
    production_companies:primary?.production_companies?.length ? primary.production_companies : secondary?.production_companies?.length ? secondary.production_companies : generic?.production_companies || null,
    vote_average:primary?.vote_average ?? secondary?.vote_average ?? generic?.vote_average ?? features?.vote_average ?? null,
    poster_path:primary?.poster_path ?? secondary?.poster_path ?? generic?.poster_path ?? null,
  };
}

function extractGenres(entry,meta,lang='en'){
  const custom=entry?.data?.custom;
  const raw=[];
  if(custom){
    if(typeof custom.genre==='string')raw.push(...custom.genre.split(','));
  }else if(meta){
    const dict=lang==='tr' ? TR_GENRES : GENRES;
    if(Array.isArray(meta.genres) && meta.genres.length){
      for(const g of meta.genres){
        if(typeof g==='string')raw.push(g);
        else if(g && typeof g==='object'){
          if(typeof g.name==='string' && g.name.trim())raw.push(g.name);
          else if(Number.isInteger(g.id) && dict[g.id])raw.push(dict[g.id]);
        }
      }
    }else if(Array.isArray(meta.genre_ids) && meta.genre_ids.length){
      for(const id of meta.genre_ids)if(dict[id])raw.push(dict[id]);
    }else if(typeof meta.genre==='string'){
      raw.push(...meta.genre.split(','));
    }
  }
  const seen=new Set(),out=[];
  for(const item of raw){
    const name=String(item || '').trim();
    const key=foldTitle(name);
    if(!name || !key || seen.has(key))continue;
    seen.add(key);
    out.push({key,name});
  }
  return out;
}

function rankPeople(entries,metaByKey,extractor,lang){
  const byPerson=new Map();
  const collator=new Intl.Collator(lang==='tr' ? 'tr' : 'en',{sensitivity:'base'});
  for(const entry of entries){
    const meta=metaByKey.get(entry.key);
    const list=extractor(meta);
    if(!list.length)continue;
    const rating=validRating(entry.data.rating) ? entry.data.rating : null;
    const seenInFilm=new Set();
    for(const person of list){
      const name=String(person?.name || '').trim();
      if(!name)continue;
      const id=Number.isSafeInteger(person?.id) && person.id>0 ? person.id : null;
      const pKey=id!==null ? 'id:'+id : 'name:'+foldTitle(name);
      if(seenInFilm.has(pKey))continue;
      seenInFilm.add(pKey);
      let bucket=byPerson.get(pKey);
      if(!bucket){
        bucket={id,name,profile_path:person?.profile_path || null,count:0,ratingSum:0,ratingCount:0};
        byPerson.set(pKey,bucket);
      }else if(!bucket.profile_path && person?.profile_path){
        bucket.profile_path=person.profile_path;
      }
      bucket.count++;
      if(rating!==null){bucket.ratingSum+=rating;bucket.ratingCount++;}
    }
  }
  return [...byPerson.values()]
    .map(b=>({
      id:b.id,
      name:b.name,
      profile_path:b.profile_path,
      count:b.count,
      avgRating:b.ratingCount ? round1(b.ratingSum/b.ratingCount) : null,
    }))
    .sort((a,b)=>b.count-a.count || (b.avgRating ?? -1)-(a.avgRating ?? -1) || collator.compare(a.name,b.name))
    .slice(0,6);
}

function rankStudios(entries,metaByKey,lang){
  const byStudio=new Map();
  const collator=new Intl.Collator(lang==='tr' ? 'tr' : 'en',{sensitivity:'base'});
  for(const entry of entries){
    const meta=metaByKey.get(entry.key);
    const list=Array.isArray(meta?.production_companies) ? meta.production_companies : Array.isArray(meta?.entities?.companies) ? meta.entities.companies : [];
    if(!list.length)continue;
    const rating=validRating(entry.data.rating) ? entry.data.rating : null;
    const seenInFilm=new Set();
    for(const company of list){
      const name=String(company?.name || '').trim();
      if(!name)continue;
      const id=Number.isSafeInteger(company?.id) && company.id>0 ? company.id : null;
      const sKey=id!==null ? 'id:'+id : 'name:'+foldTitle(name);
      if(seenInFilm.has(sKey))continue;
      seenInFilm.add(sKey);
      let bucket=byStudio.get(sKey);
      if(!bucket){
        bucket={id,name,count:0,ratingSum:0,ratingCount:0};
        byStudio.set(sKey,bucket);
      }
      bucket.count++;
      if(rating!==null){bucket.ratingSum+=rating;bucket.ratingCount++;}
    }
  }
  return [...byStudio.values()]
    .map(b=>({
      id:b.id,
      name:b.name,
      count:b.count,
      avgRating:b.ratingCount ? round1(b.ratingSum/b.ratingCount) : null,
    }))
    .sort((a,b)=>b.count-a.count || (b.avgRating ?? -1)-(a.avgRating ?? -1) || collator.compare(a.name,b.name))
    .slice(0,6);
}

function makeRecordRef(entry,metadataMap,meta,lang,runtimeOverride=null){
  const tmdbId=tmdbIdOf(entry);
  const rawRt=runtimeOverride!==null ? runtimeOverride : Number(meta?.runtime);
  const runtime=Number.isFinite(rawRt) && rawRt>0 && rawRt<=MAX_RUNTIME ? Math.round(rawRt) : null;
  const y=entryYear(entry,metadataMap,lang);
  return {
    key:entry.key,
    tmdbId,
    title:entryTitle(entry,metadataMap,lang) || (tmdbId ? 'TMDB #'+tmdbId : ''),
    year:Number.isInteger(y) && y>=1800 && y<=2200 ? y : null,
    runtime,
    rating:validRating(entry.data?.rating) ? entry.data.rating : null,
  };
}

export function computeCinemaStats(entries,metadataMap={},{lang='en',year=new Date().getFullYear()}={}){
  const currentYear=new Date().getFullYear();
  const targetYear=Number.isInteger(year) && year>=1800 && year<=2200 ? year : currentYear;
  const rawList=Array.isArray(entries) ? entries : Object.values(entries || {});
  const active=rawList.filter(x=>x && x.data && !x.data.deleted_at);
  const metaByKey=new Map(active.map(e=>[e.key,resolvedMetadata(e,metadataMap,lang)]));

  let watched=0,watchlist=0,favorites=0,rated=0,ratingSum=0,withNotes=0,watchedThisYear=0,totalMinutes=0,runtimeCount=0;
  const ratingCounts=new Array(11).fill(0);
  const ratingValues=[];
  const monthCounts=new Array(12).fill(0);
  const weekdayCounts=new Array(7).fill(0);
  const runtimeBucketCounts={short:0,feature:0,extended:0,epic:0};
  const seenYears=new Set([currentYear,targetYear]);
  const exactDayEpochs=new Set();
  const tmdbPairs=[];
  const watchedEntries=[];
  let longestRecord=null,shortestRecord=null,oldestRecord=null,newestRecord=null;

  for(const entry of active){
    const d=entry.data;
    const meta=metaByKey.get(entry.key);
    const isWatched=d.status==='Watched';
    if(isWatched){
      watched++;
      watchedEntries.push(entry);
    }else if(d.status==='Watchlist'){
      watchlist++;
    }
    if(d.favorite)favorites++;
    if(typeof d.note==='string' && d.note.trim())withNotes++;
    if(validRating(d.rating)){
      rated++;
      ratingSum+=d.rating;
      ratingCounts[d.rating]++;
      ratingValues.push(d.rating);
      const voteAvg=Number(meta?.vote_average);
      const scorePct=Number(meta?.score_percent);
      const tmdbScore=Number.isFinite(voteAvg) && voteAvg>0 && voteAvg<=10
        ? voteAvg
        : (Number.isFinite(scorePct) && scorePct>0 && scorePct<=100 ? scorePct/10 : null);
      if(tmdbScore!==null)tmdbPairs.push([d.rating,tmdbScore]);
    }
    if(isWatched && typeof d.watched_date==='string'){
      const match=DATE_RE.exec(d.watched_date);
      if(match){
        const wYear=Number(match[1]),wMonth=Number(match[2]);
        if(wYear>=1800 && wYear<=2200)seenYears.add(wYear);
        if(wYear===targetYear && wMonth>=1 && wMonth<=12){
          watchedThisYear++;
          monthCounts[wMonth-1]++;
        }
        if(match[3] && wYear>=1800 && wYear<=2200 && wMonth>=1 && wMonth<=12){
          const wDay=Number(match[3]);
          const dt=new Date(Date.UTC(wYear,wMonth-1,wDay));
          if(dt.getUTCFullYear()===wYear && dt.getUTCMonth()===wMonth-1 && dt.getUTCDate()===wDay){
            exactDayEpochs.add(Math.floor(dt.getTime()/86400000));
            weekdayCounts[(dt.getUTCDay()+6)%7]++;
          }
        }
      }
    }
    if(isWatched){
      const runtime=Number(meta?.runtime);
      if(Number.isFinite(runtime) && runtime>0 && runtime<=MAX_RUNTIME){
        const rt=Math.round(runtime);
        totalMinutes+=rt;
        runtimeCount++;
        if(rt<90)runtimeBucketCounts.short++;
        else if(rt<120)runtimeBucketCounts.feature++;
        else if(rt<150)runtimeBucketCounts.extended++;
        else runtimeBucketCounts.epic++;
        if(!longestRecord || rt>longestRecord.runtime)longestRecord=makeRecordRef(entry,metadataMap,meta,lang,rt);
        if(!shortestRecord || rt<shortestRecord.runtime)shortestRecord=makeRecordRef(entry,metadataMap,meta,lang,rt);
      }
    }
    const relYear=entryYear(entry,metadataMap,lang);
    if(Number.isInteger(relYear) && relYear>=1800 && relYear<=2200){
      if(!oldestRecord || relYear<oldestRecord.year)oldestRecord=makeRecordRef(entry,metadataMap,meta,lang);
      if(!newestRecord || relYear>newestRecord.year)newestRecord=makeRecordRef(entry,metadataMap,meta,lang);
    }
  }

  const maxRatingCount=Math.max(0,...ratingCounts.slice(1));
  const ratingDistribution=[];
  for(let r=1;r<=10;r++){
    const count=ratingCounts[r];
    ratingDistribution.push({rating:r,count,share:maxRatingCount>0 ? count/maxRatingCount : 0});
  }

  const maxMonthCount=Math.max(0,...monthCounts);
  const monthlyActivity=monthCounts.map((count,idx)=>({
    month:idx+1,
    count,
    share:maxMonthCount>0 ? count/maxMonthCount : 0,
  }));

  const maxWeekdayCount=Math.max(0,...weekdayCounts);
  const weekdays=weekdayCounts.map((count,day)=>({
    day,
    count,
    share:maxWeekdayCount>0 ? count/maxWeekdayCount : 0,
  }));

  const maxRuntimeBucket=Math.max(0,...Object.values(runtimeBucketCounts));
  const runtimeBuckets=['short','feature','extended','epic'].map(key=>({
    key,
    count:runtimeBucketCounts[key],
    share:maxRuntimeBucket>0 ? runtimeBucketCounts[key]/maxRuntimeBucket : 0,
  }));

  // Top genres from watched films, falling back to all active films if watched films have no genres.
  const collator=new Intl.Collator(lang==='tr' ? 'tr' : 'en',{sensitivity:'base'});
  const collectGenres=source=>{
    const map=new Map();
    for(const entry of source){
      const genres=extractGenres(entry,metaByKey.get(entry.key),lang);
      if(!genres.length)continue;
      const r=validRating(entry.data.rating) ? entry.data.rating : null;
      for(const g of genres){
        let b=map.get(g.key);
        if(!b){b={name:g.name,count:0,ratingSum:0,ratingCount:0};map.set(g.key,b);}
        b.count++;
        if(r!==null){b.ratingSum+=r;b.ratingCount++;}
      }
    }
    return map;
  };
  let genreMap=collectGenres(watchedEntries);
  if(!genreMap.size && active.length>watchedEntries.length)genreMap=collectGenres(active);
  const sortedGenres=[...genreMap.values()]
    .map(g=>({name:g.name,count:g.count,avgRating:g.ratingCount ? round1(g.ratingSum/g.ratingCount) : null}))
    .sort((a,b)=>b.count-a.count || (b.avgRating ?? -1)-(a.avgRating ?? -1) || collator.compare(a.name,b.name))
    .slice(0,8);
  const maxGenreCount=Math.max(0,...sortedGenres.map(g=>g.count));
  const topGenres=sortedGenres.map(g=>({...g,share:maxGenreCount>0 ? g.count/maxGenreCount : 0}));

  // Chronological decade breakdown from release years (or custom year).
  const decadeMap=new Map();
  for(const entry of active){
    const y=entryYear(entry,metadataMap,lang);
    if(!Number.isInteger(y) || y<1800 || y>2200)continue;
    const startYear=Math.floor(y/10)*10;
    decadeMap.set(startYear,(decadeMap.get(startYear) || 0)+1);
  }
  const maxDecadeCount=Math.max(0,...decadeMap.values());
  const decades=[...decadeMap.entries()]
    .sort((a,b)=>a[0]-b[0])
    .map(([startYear,count])=>({
      decade:`${startYear}s`,
      startYear,
      count,
      share:maxDecadeCount>0 ? count/maxDecadeCount : 0,
    }));

  const topDirectors=rankPeople(watchedEntries,metaByKey,meta=>{
    if(Array.isArray(meta?.credits?.crew))return meta.credits.crew.filter(p=>p && p.job==='Director');
    if(Array.isArray(meta?.entities?.directors))return meta.entities.directors;
    return [];
  },lang);

  const topActors=rankPeople(watchedEntries,metaByKey,meta=>{
    if(Array.isArray(meta?.credits?.cast))return meta.credits.cast.slice(0,6);
    if(Array.isArray(meta?.entities?.cast))return meta.entities.cast.slice(0,6);
    return [];
  },lang);

  const topStudios=rankStudios(watchedEntries,metaByKey,lang);

  const highestRated=watchedEntries
    .filter(e=>validRating(e.data.rating))
    .sort((a,b)=>{
      if(b.data.rating!==a.data.rating)return b.data.rating-a.data.rating;
      if(Boolean(b.data.favorite)!==Boolean(a.data.favorite))return b.data.favorite ? 1 : -1;
      const x=orderKey(a),y=orderKey(b);
      return x<y ? 1 : x>y ? -1 : 0;
    })
    .slice(0,6)
    .map(entry=>{
      const tmdbId=tmdbIdOf(entry);
      const meta=metaByKey.get(entry.key);
      return {
        key:entry.key,
        tmdbId,
        title:entryTitle(entry,metadataMap,lang) || (tmdbId ? 'TMDB #'+tmdbId : ''),
        year:entryYear(entry,metadataMap,lang),
        poster_path:meta?.poster_path || null,
        rating:entry.data.rating,
        favorite:Boolean(entry.data.favorite),
      };
    });

  const completionPct=active.length>0 ? Math.round((watched*100)/active.length) : 0;
  const completionRingDash=Math.round((RING_CIRCUMFERENCE*completionPct)/100);
  const favoriteRate=watched>0 ? Math.round((favorites*100)/watched) : 0;
  const avgRuntime=runtimeCount>0 ? Math.round(totalMinutes/runtimeCount) : null;
  const totalDays=totalMinutes>0 ? round1(totalMinutes/1440) : 0;
  const peakMonth=maxMonthCount>0 ? monthCounts.indexOf(maxMonthCount)+1 : null;
  let tmdbAvg=null,criticDelta=null;
  if(tmdbPairs.length>0){
    const userPairedAvg=tmdbPairs.reduce((s,p)=>s+p[0],0)/tmdbPairs.length;
    const tmdbPairedAvg=tmdbPairs.reduce((s,p)=>s+p[1],0)/tmdbPairs.length;
    tmdbAvg=round1(tmdbPairedAvg);
    criticDelta=round1(userPairedAvg-tmdbPairedAvg);
  }
  const topDecadeEntry=decades.length
    ? [...decades].sort((a,b)=>b.count-a.count || b.startYear-a.startYear)[0]
    : null;

  return {
    year:targetYear,
    availableYears:[...seenYears].sort((a,b)=>b-a),
    totals:{
      total:active.length,
      watched,
      watchlist,
      favorites,
      rated,
      withNotes,
      watchedThisYear,
      avgRating:rated ? round1(ratingSum/rated) : null,
      totalMinutes,
      runtimeCount,
    },
    overview:{
      completionPct,
      completionRingDash,
      ringCircumference:RING_CIRCUMFERENCE,
      favoriteRate,
      avgRuntime,
      totalDays,
      medianRating:medianOf(ratingValues),
      tenCount:ratingCounts[10],
      peakMonth,
      peakMonthCount:maxMonthCount,
      longestStreak:longestStreakOf(exactDayEpochs),
      tmdbAvg,
      criticDelta,
      topGenreName:topGenres.length ? topGenres[0].name : null,
      topDecade:topDecadeEntry ? topDecadeEntry.decade : null,
    },
    records:{
      longest:longestRecord,
      shortest:shortestRecord,
      oldest:oldestRecord,
      newest:newestRecord,
    },
    ratingDistribution,
    topGenres,
    decades,
    monthlyActivity,
    weekdays,
    runtimeBuckets,
    topDirectors,
    topActors,
    topStudios,
    highestRated,
  };
}
