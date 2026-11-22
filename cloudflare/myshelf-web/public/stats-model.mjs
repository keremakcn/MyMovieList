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

export function computeCinemaStats(entries,metadataMap={},{lang='en',year=new Date().getFullYear()}={}){
  const targetYear=Number.isInteger(year) ? year : new Date().getFullYear();
  const yearPrefix=String(targetYear).padStart(4,'0')+'-';
  const rawList=Array.isArray(entries) ? entries : Object.values(entries || {});
  const active=rawList.filter(x=>x && x.data && !x.data.deleted_at);
  const metaByKey=new Map(active.map(e=>[e.key,resolvedMetadata(e,metadataMap,lang)]));

  let watched=0,watchlist=0,favorites=0,rated=0,ratingSum=0,withNotes=0,watchedThisYear=0,totalMinutes=0,runtimeCount=0;
  const ratingCounts=new Array(11).fill(0);
  const monthCounts=new Array(12).fill(0);
  const watchedEntries=[];

  for(const entry of active){
    const d=entry.data;
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
    }
    if(isWatched && typeof d.watched_date==='string' && d.watched_date.startsWith(yearPrefix)){
      const m=Number(d.watched_date.slice(5,7));
      if(m>=1 && m<=12){
        watchedThisYear++;
        monthCounts[m-1]++;
      }
    }
    if(isWatched){
      const runtime=Number(metaByKey.get(entry.key)?.runtime);
      if(Number.isFinite(runtime) && runtime>0){
        totalMinutes+=Math.round(runtime);
        runtimeCount++;
      }
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

  return {
    year:targetYear,
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
    ratingDistribution,
    topGenres,
    decades,
    monthlyActivity,
    topDirectors,
    topActors,
    highestRated,
  };
}
