import assert from 'node:assert/strict';
import {test} from 'node:test';
import {deflateRawSync} from 'node:zlib';

import {
  LIBRARY_PAGE_SIZE,
  LIBRARY_SORTS,
  foldTitle,
  libraryMetadataKeys,
  selectLibraryEntries,
  sliceLibrary,
} from '../public/library-model.mjs';
import {
  MAX_NOTE_LENGTH,
  MAX_ZIP_UNCOMPRESSED_BYTES,
  extractZipCSVs,
  importExternalItems,
  matchTmdbMovie,
  parseCSV,
  parseExternalFile,
  parseImdbCSV,
  parseLetterboxdCSV,
  parseLetterboxdZip,
} from '../public/external-import.mjs';
import {computeCinemaStats} from '../public/stats-model.mjs';
import {formatDecadeLabel,renderStatsCardCanvas} from '../public/stats-card.mjs';
import {iso,newRecord} from '../public/sync-model.mjs';

// ---------- minimal ZIP builder for stored (0) and deflate-raw (8) archives ----------

const CRC_TABLE=(()=>{
  const table=new Uint32Array(256);
  for(let n=0;n<256;n++){
    let c=n;
    for(let k=0;k<8;k++)c=c&1 ? 0xedb88320^(c>>>1) : c>>>1;
    table[n]=c>>>0;
  }
  return table;
})();

function crc32(buf){
  let c=0xffffffff;
  for(let i=0;i<buf.length;i++)c=CRC_TABLE[(c^buf[i])&0xff]^(c>>>8);
  return (c^0xffffffff)>>>0;
}

function buildZip(entries){
  const localParts=[],centralParts=[];
  let offset=0;
  for(const item of entries){
    const nameBuf=Buffer.from(item.name,'utf8');
    const rawBuf=Buffer.isBuffer(item.data) ? item.data : Buffer.from(item.data ?? '','utf8');
    const method=item.method ?? 8;
    const compBuf=method===8 ? deflateRawSync(rawBuf) : rawBuf;
    const crc=item.crc ?? crc32(rawBuf);
    const declaredSize=item.declaredSize ?? rawBuf.length;
    const externalAttr=item.externalAttr ?? 0;

    const local=Buffer.alloc(30+nameBuf.length);
    local.writeUInt32LE(0x04034b50,0);
    local.writeUInt16LE(20,4);
    local.writeUInt16LE(0,6);
    local.writeUInt16LE(method,8);
    local.writeUInt32LE(0,10);
    local.writeUInt32LE(crc,14);
    local.writeUInt32LE(compBuf.length,18);
    local.writeUInt32LE(declaredSize,22);
    local.writeUInt16LE(nameBuf.length,26);
    local.writeUInt16LE(0,28);
    nameBuf.copy(local,30);
    localParts.push(local,compBuf);

    const central=Buffer.alloc(46+nameBuf.length);
    central.writeUInt32LE(0x02014b50,0);
    central.writeUInt16LE(20,4);
    central.writeUInt16LE(20,6);
    central.writeUInt16LE(0,8);
    central.writeUInt16LE(method,10);
    central.writeUInt32LE(0,12);
    central.writeUInt32LE(crc,16);
    central.writeUInt32LE(compBuf.length,20);
    central.writeUInt32LE(declaredSize,24);
    central.writeUInt16LE(nameBuf.length,28);
    central.writeUInt16LE(0,30);
    central.writeUInt16LE(0,32);
    central.writeUInt16LE(0,34);
    central.writeUInt16LE(0,36);
    central.writeUInt32LE(externalAttr,38);
    central.writeUInt32LE(offset,42);
    nameBuf.copy(central,46);
    centralParts.push(central);

    offset+=local.length+compBuf.length;
  }
  const cdBuf=Buffer.concat(centralParts);
  const eocd=Buffer.alloc(22);
  eocd.writeUInt32LE(0x06054b50,0);
  eocd.writeUInt16LE(0,4);
  eocd.writeUInt16LE(0,6);
  eocd.writeUInt16LE(entries.length,8);
  eocd.writeUInt16LE(entries.length,10);
  eocd.writeUInt32LE(cdBuf.length,12);
  eocd.writeUInt32LE(offset,16);
  eocd.writeUInt16LE(0,20);
  const full=Buffer.concat([...localParts,cdBuf,eocd]);
  return full.buffer.slice(full.byteOffset,full.byteOffset+full.byteLength);
}

function createMemoryStore(){
  const workspaces=new Map();
  const catalog=new Map();
  let tick=Date.parse('2026-06-01T00:00:00Z');
  const getWs=owner=>{
    if(!workspaces.has(owner))workspaces.set(owner,{entries:{}});
    return workspaces.get(owner);
  };
  return {
    catalog,
    async read(owner){
      return structuredClone(getWs(owner));
    },
    async add(owner,id,details={}){
      const ws=getWs(owner);
      tick+=1000;
      if(id){
        const key='tmdb:'+id;
        if(ws.entries[key]){
          if(ws.entries[key].data.deleted_at)ws.entries[key].data.deleted_at=null;
          return key;
        }
        ws.entries[key]=newRecord(id,{...details,now:tick});
        return key;
      }
      const entry=newRecord(null,{...details,now:tick});
      ws.entries[entry.key]=entry;
      return entry.key;
    },
    async edit(owner,key,changes){
      const ws=getWs(owner);
      const entry=ws.entries[key];
      if(!entry)throw Error('not_found');
      entry.data={...entry.data,...changes};
    },
    async cacheMetadata(key,value){
      catalog.set(key,{...(catalog.get(key) || {}),...value});
    },
    async metadataBatch(keys){
      const out={};
      for(const k of keys || [])out[k]=catalog.get(k) || null;
      return out;
    },
  };
}

// ---------- 1. library-model.mjs tests ----------

test('foldTitle handles Turkish ı/İ/ş/ğ/ç/ö/ü, diacritics, and whitespace normalization',()=>{
  assert.equal(LIBRARY_PAGE_SIZE,48);
  assert.deepEqual(LIBRARY_SORTS,[
    'default','added_desc','added_asc','rating_desc','rating_asc',
    'year_desc','year_asc','watched_desc','watched_asc','title_asc',
  ]);
  assert.equal(foldTitle('Kış Uykusu'),'kis uykusu');
  assert.equal(foldTitle('İSTANBUL   Kanatlarımın  Altında'),'istanbul kanatlarimin altinda');
  assert.equal(foldTitle('Işık ve Gölge'),'isik ve golge');
  assert.equal(foldTitle('Çağrı & Şaban: Ölümlü Dünya'),'cagri & saban: olumlu dunya');
  assert.equal(foldTitle('Le Fabuleux Destin d’Amélie Poulain'),'le fabuleux destin d’amelie poulain');
});

test('selectLibraryEntries and sliceLibrary support Turkish search, all 10 sort modes, and backwards compatibility',()=>{
  const t0=Date.parse('2026-01-01T00:00:00Z');
  const entries={};

  const e1=newRecord(101,{now:t0+1000});
  e1.data.status='Watched';
  e1.data.rating=8;
  e1.data.favorite=false;
  e1.data.watched_date='2025-11-10';
  entries[e1.key]=e1;

  const e2=newRecord(102,{now:t0+2000});
  e2.data.status='Watched';
  e2.data.rating=10;
  e2.data.favorite=true;
  e2.data.watched_date='2026-02-14';
  entries[e2.key]=e2;

  const e3=newRecord(103,{now:t0+3000});
  e3.data.status='Watchlist';
  e3.data.rating=null;
  e3.data.favorite=true;
  e3.data.watched_date=null;
  entries[e3.key]=e3;

  const e4=newRecord(null,{title:'Ahlat Ağacı',year:2018,genre:'Dram',now:t0+4000});
  e4.data.status='Watched';
  e4.data.rating=8;
  e4.data.favorite=false;
  e4.data.watched_date='2024-05-01';
  entries[e4.key]=e4;

  const deleted=newRecord(999,{now:t0+5000});
  deleted.data.deleted_at=iso(t0+6000);
  entries[deleted.key]=deleted;

  const meta={
    'en:101':{id:101,title:'Winter Sleep',original_title:'Kış Uykusu',release_date:'2014-06-13'},
    'tr:101':{id:101,title:'Kış Uykusu',original_title:'Kış Uykusu',release_date:'2014-06-13'},
    'en:102':{id:102,title:'The Matrix',original_title:'The Matrix',release_date:'1999-03-31'},
    'en:103':{id:103,title:'Amélie',original_title:'Le Fabuleux Destin d\'Amélie Poulain',release_date:''},
  };

  // Backwards compatibility: string second argument.
  assert.deepEqual(selectLibraryEntries(entries).map(x=>x.key),[e4.key,e3.key,e2.key,e1.key]);
  assert.deepEqual(selectLibraryEntries(entries,'watched').map(x=>x.key),[e4.key,e2.key,e1.key]);
  assert.deepEqual(selectLibraryEntries(entries,'watchlist').map(x=>x.key),[e3.key]);
  assert.deepEqual(selectLibraryEntries(entries,'favorites').map(x=>x.key),[e3.key,e2.key]);

  // Search query matches localized title, original_title, and custom title with Turkish folding.
  assert.deepEqual(selectLibraryEntries(entries,{query:'kıs uykusu',meta,lang:'en'}).map(x=>x.key),[e1.key]);
  assert.deepEqual(selectLibraryEntries(entries,{query:'İSTANBUL',meta,lang:'tr'}).map(x=>x.key),[]);
  assert.deepEqual(selectLibraryEntries(entries,{query:'agaci',meta,lang:'tr'}).map(x=>x.key),[e4.key]);
  assert.deepEqual(selectLibraryEntries(entries,{query:'AMELIE',meta,lang:'en'}).map(x=>x.key),[e3.key]);

  // All 10 sort modes + null-last + order_key DESC tie-breaking.
  assert.deepEqual(selectLibraryEntries(entries,{sort:'default',meta}).map(x=>x.key),[e4.key,e3.key,e2.key,e1.key]);
  assert.deepEqual(selectLibraryEntries(entries,{sort:'added_desc',meta}).map(x=>x.key),[e4.key,e3.key,e2.key,e1.key]);
  assert.deepEqual(selectLibraryEntries(entries,{sort:'added_asc',meta}).map(x=>x.key),[e1.key,e2.key,e3.key,e4.key]);
  // Rating tie on 8 (e4 added after e1 -> e4 before e1); null rating (e3) sorts last in both desc and asc.
  assert.deepEqual(selectLibraryEntries(entries,{sort:'rating_desc',meta}).map(x=>x.key),[e2.key,e4.key,e1.key,e3.key]);
  assert.deepEqual(selectLibraryEntries(entries,{sort:'rating_asc',meta}).map(x=>x.key),[e4.key,e1.key,e2.key,e3.key]);
  // Year sort: e4=2018, e1=2014, e2=1999, e3=null (last).
  assert.deepEqual(selectLibraryEntries(entries,{sort:'year_desc',meta}).map(x=>x.key),[e4.key,e1.key,e2.key,e3.key]);
  assert.deepEqual(selectLibraryEntries(entries,{sort:'year_asc',meta}).map(x=>x.key),[e2.key,e1.key,e4.key,e3.key]);
  // Watched date sort: e2=2026-02-14, e1=2025-11-10, e4=2024-05-01, e3=null (last).
  assert.deepEqual(selectLibraryEntries(entries,{sort:'watched_desc',meta}).map(x=>x.key),[e2.key,e1.key,e4.key,e3.key]);
  assert.deepEqual(selectLibraryEntries(entries,{sort:'watched_asc',meta}).map(x=>x.key),[e4.key,e1.key,e2.key,e3.key]);
  // Title ascending (EN: Ahlat Ağacı, Amélie, The Matrix, Winter Sleep).
  assert.deepEqual(selectLibraryEntries(entries,{sort:'title_asc',meta,lang:'en'}).map(x=>x.key),[e4.key,e3.key,e2.key,e1.key]);

  // sliceLibrary passes query/sort/meta/lang and paginates accurately.
  const sliced=sliceLibrary(entries,{filter:'watched',sort:'rating_desc',meta,page:1,pageSize:2});
  assert.equal(sliced.total,3);
  assert.equal(sliced.shown,2);
  assert.equal(sliced.hasMore,true);
  assert.deepEqual(sliced.items.map(x=>x.key),[e2.key,e4.key]);

  assert.deepEqual(libraryMetadataKeys([e1,e4],'tr'),['tr:101','en:101']);
});

// ---------- 2. external-import.mjs tests ----------

test('parseCSV handles BOM, quoted commas, escaped double quotes, multiline fields, and rejects unclosed quotes',()=>{
  const raw='\uFEFFName,Year,Review\r\n"Dune: Part Two",2024,"Line 1\r\n""Epic"" Line 2"\nArrival,2016,Simple\r\n';
  const rows=parseCSV(raw);
  assert.deepEqual(rows,[
    ['Name','Year','Review'],
    ['Dune: Part Two','2024','Line 1\r\n"Epic" Line 2'],
    ['Arrival','2016','Simple'],
  ]);
  assert.throws(()=>parseCSV('Name,Year\n"Unclosed,2024'),/import_malformed/);
});

test('extractZipCSVs and parseLetterboxdZip merge stored & deflated CSVs, ignore deleted/lists, and enforce security limits',async()=>{
  const watchedCsv='\uFEFFDate,Name,Year,Letterboxd URI\n2026-01-05,Anatomy of a Fall,2023,https://boxd.it/abcd\n2026-01-06,Past Lives,2023,https://boxd.it/efgh\n';
  const ratingsCsv='Date,Name,Year,Letterboxd URI,Rating\n2026-01-07,Anatomy of a Fall,2023,https://boxd.it/abcd,4.5\n2026-01-06,Past Lives,2023,https://boxd.it/efgh,3.5\n';
  const diaryCsv='Date,Name,Year,Letterboxd URI,Rating,Rewatch,Tags,Watched Date\n2026-02-01,Anatomy of a Fall,2023,https://boxd.it/diaryentry1,4.0,No,,2026-01-20\n';
  const reviewsCsv='Date,Name,Year,Letterboxd URI,Rating,Rewatch,Review,Tags,Watched Date\n2026-02-01,Anatomy of a Fall,2023,https://boxd.it/diaryentry1,4.0,No,"Gripping courtroom drama.\n\nA+".repeat(1),' +
    ',2026-01-20\n2026-02-02,Long Review Film,2022,https://boxd.it/long,0.5,No,'+'X'.repeat(MAX_NOTE_LENGTH+500)+',,2026-02-02\n';
  const watchlistCsv='Date,Name,Year,Letterboxd URI\n2026-01-01,Anatomy of a Fall,2023,https://boxd.it/abcd\n2026-01-10,Nosferatu,2024,https://boxd.it/nosf\n';

  const zipBuf=buildZip([
    {name:'export/watched.csv',data:watchedCsv,method:8},
    {name:'export/ratings.csv',data:ratingsCsv,method:0},
    {name:'export/diary.csv',data:diaryCsv,method:8},
    {name:'export/reviews.csv',data:reviewsCsv,method:8},
    {name:'export/watchlist.csv',data:watchlistCsv,method:0},
    {name:'export/deleted/watched.csv',data:'Date,Name,Year,Letterboxd URI\n2020-01-01,Deleted Film,2020,https://boxd.it/del\n',method:8},
    {name:'export/lists/favorites.csv',data:'Date,Name,Year,Letterboxd URI\n2020-01-01,List Film,2020,https://boxd.it/lst\n',method:8},
  ]);

  const extracted=await extractZipCSVs(zipBuf);
  assert.deepEqual(Object.keys(extracted).sort(),['diary.csv','ratings.csv','reviews.csv','watched.csv','watchlist.csv']);

  const parsed=await parseLetterboxdZip(zipBuf);
  assert.equal(parsed.source,'letterboxd');
  assert.equal(parsed.skippedNonFilms,0);
  assert.equal(parsed.items.length,4);

  const anatomy=parsed.items.find(x=>x.title==='Anatomy of a Fall');
  assert.equal(anatomy.year,2023);
  assert.equal(anatomy.status,'Watched'); // Watchlist + Watched merges to Watched
  assert.equal(anatomy.rating,9); // 4.5 stars from ratings.csv overrides 4.0 diary rating
  assert.equal(anatomy.watched_date,'2026-01-20'); // Explicit diary Watched Date wins
  assert(anatomy.note.includes('Gripping courtroom drama.'));

  const pastLives=parsed.items.find(x=>x.title==='Past Lives');
  assert.equal(pastLives.status,'Watched');
  assert.equal(pastLives.rating,7); // 3.5 * 2 = 7
  assert.equal(pastLives.watched_date,'2026-01-06');

  const longFilm=parsed.items.find(x=>x.title==='Long Review Film');
  assert.equal(longFilm.rating,1); // 0.5 * 2 = 1
  assert.equal(longFilm.note.length,MAX_NOTE_LENGTH);

  const nosferatu=parsed.items.find(x=>x.title==='Nosferatu');
  assert.equal(nosferatu.status,'Watchlist');
  assert.equal(nosferatu.watched_date,null);
  assert.equal(nosferatu.rating,null);

  // Security rejections: path traversal, drive letter, symlink, too many files, zip-bomb.
  for(const badName of ['../watched.csv','/watched.csv','\\watched.csv','C:watched.csv','sub/../../watched.csv','bad\0.csv']){
    const badZip=buildZip([{name:badName,data:watchedCsv}]);
    await assert.rejects(()=>extractZipCSVs(badZip),/import_zip_unsafe_path/);
  }
  const symlinkZip=buildZip([{name:'watched.csv',data:watchedCsv,externalAttr:(0o120777<<16)>>>0}]);
  await assert.rejects(()=>extractZipCSVs(symlinkZip),/import_zip_unsafe_path/);

  const tooManyZip=buildZip(Array.from({length:51},(_,i)=>({name:`file-${i}.txt`,data:'hi'})));
  await assert.rejects(()=>extractZipCSVs(tooManyZip),/import_zip_too_many_files/);

  const declaredBombZip=buildZip([{name:'watched.csv',data:watchedCsv,declaredSize:MAX_ZIP_UNCOMPRESSED_BYTES+10}]);
  await assert.rejects(()=>extractZipCSVs(declaredBombZip),/import_zip_too_large/);

  // Streaming deflate zip-bomb where central directory lies about uncompressed size (declaredSize=64, actual >25 MB).
  const streamingBombPayload=Buffer.alloc(MAX_ZIP_UNCOMPRESSED_BYTES+4096,0x41);
  const streamingBombZip=buildZip([{name:'watched.csv',data:streamingBombPayload,method:8,declaredSize:64}]);
  await assert.rejects(()=>extractZipCSVs(streamingBombZip),/import_zip_too_large/);

  // Standalone single-CSV Letterboxd parse.
  const singleLb=parseLetterboxdCSV(ratingsCsv,'ratings.csv');
  assert.equal(singleLb.source,'letterboxd');
  assert.equal(singleLb.items.length,2);
  assert.equal(singleLb.items[0].rating,9);
});

test('parseImdbCSV and parseExternalFile filter non-film TV/game rows and map ratings, dates, and watchlist status',async()=>{
  const imdbCsv=[
    'Const,Your Rating,Date Rated,Title,URL,Title Type,IMDb Rating,Runtime (mins),Year,Genres,Num Votes,Release Date,Directors',
    'tt15239678,9,2026-03-10,Dune: Part Two,https://www.imdb.com/title/tt15239678/,movie,8.5,166,2024,"Action, Adventure, Drama",500000,2024-03-01,Denis Villeneuve',
    'tt0903747,10,2025-01-01,Breaking Bad,https://www.imdb.com/title/tt0903747/,tvSeries,9.5,49,2008,"Crime, Drama",2000000,2008-01-20,',
    'tt9999991,,,The Lighthouse,https://www.imdb.com/title/tt9999991/,movie,7.4,109,2019,"Drama, Fantasy",200000,2019-10-18,Robert Eggers',
    'tt9999992,8,2026-01-12,La Jetée,https://www.imdb.com/title/tt9999992/,short,8.2,28,1962,Sci-Fi,40000,1962-02-16,Chris Marker',
    'tt9999993,10,2026-01-12,Elden Ring,https://www.imdb.com/title/tt9999993/,videoGame,9.6,,2022,Action,10000,2022-02-25,',
  ].join('\n');

  const parsed=parseImdbCSV(imdbCsv,'WATCHLIST.csv');
  assert.equal(parsed.source,'imdb');
  assert.equal(parsed.skippedNonFilms,2);
  assert.equal(parsed.items.length,3);

  const dune=parsed.items.find(x=>x.title==='Dune: Part Two');
  assert.equal(dune.status,'Watched');
  assert.equal(dune.rating,9);
  assert.equal(dune.watched_date,'2026-03-10');
  assert.equal(dune.year,2024);
  assert.equal(dune.genre,'Action, Adventure, Drama');

  const lighthouse=parsed.items.find(x=>x.title==='The Lighthouse');
  assert.equal(lighthouse.status,'Watchlist');
  assert.equal(lighthouse.rating,null);
  assert.equal(lighthouse.watched_date,null);

  const autoDetected=await parseExternalFile(imdbCsv,'imdb-export.csv','auto');
  assert.equal(autoDetected.source,'imdb');
  assert.equal(autoDetected.items.length,3);

  const lbSingle=await parseExternalFile('Date,Name,Year,Letterboxd URI\n2026-02-01,Cure,1997,https://boxd.it/cure\n','watchlist.csv','auto');
  assert.equal(lbSingle.source,'letterboxd');
  assert.equal(lbSingle.items[0].status,'Watchlist');
  assert.equal(lbSingle.items[0].title,'Cure');
});

test('matchTmdbMovie and importExternalItems match TMDB, preserve existing records, and trip circuit breaker on 429',async()=>{
  // Direct matcher test: exact title + closest year wins over wrong year.
  const match=matchTmdbMovie({title:'Dune: Part Two',year:2024},[
    {id:438631,title:'Dune',original_title:'Dune',release_date:'2021-09-15'},
    {id:693134,title:'Dune: Part Two',original_title:'Dune: Part Two',release_date:'2024-02-27'},
  ]);
  assert.equal(match.tmdb_id,693134);

  const store=createMemoryStore();
  // Seed existing TMDB film (tmdb:603 The Matrix) with user rating 10 & personal note, plus existing custom film.
  await store.add('user-1',603);
  await store.edit('user-1','tmdb:603',{status:'Watched',rating:10,favorite:true,note:'My original Matrix note'});
  await store.cacheMetadata('en:603',{id:603,title:'The Matrix',original_title:'The Matrix',release_date:'1999-03-31'});
  await store.add('user-1',null,{title:'Kış Uykusu',year:2014,genre:'Dram'});

  const items=[
    {title:'The Matrix',year:1999,status:'Watched',rating:4,note:'Should NOT overwrite',watched_date:'2026-01-01'},
    {title:'Kis Uykusu',year:2014,status:'Watched',rating:9,note:'Should NOT overwrite folded custom duplicate'},
    {title:'Dune: Part Two',year:2024,status:'Watched',rating:9,note:'Imax watch',watched_date:'2026-03-10'},
    {title:'Rate Limited Film 1',year:2023,status:'Watched',rating:8,note:'Saved as custom on 429',watched_date:'2026-03-11',genre:'Drama'},
    {title:'Post Breaker Film 2',year:2025,status:'Watchlist',rating:null,note:null,watched_date:null,genre:'Sci-Fi'},
  ];

  let searchCalls=0;
  const progressEvents=[];
  const summary=await importExternalItems(items,{
    owner:'user-1',
    store,
    concurrency:1,
    onProgress:p=>progressEvents.push(p),
    async searchCatalog(query){
      searchCalls++;
      if(query==='Dune: Part Two'){
        return {results:[{id:693134,title:'Dune: Part Two',original_title:'Dune: Part Two',release_date:'2024-02-27',poster_path:'/dune2.jpg'}]};
      }
      const err=Error('HTTP 429 Too Many Requests');
      err.status=429;
      throw err;
    },
  });

  assert.equal(summary.imported,3);
  assert.equal(summary.matchedTmdb,1);
  assert.equal(summary.addedCustom,2);
  assert.equal(summary.skippedExisting,2);
  assert.equal(summary.catalogOffline,true);
  // Circuit breaker tripped on 'Rate Limited Film 1' (429), so 'Post Breaker Film 2' did not invoke searchCatalog.
  assert.equal(searchCalls,2);
  assert.equal(progressEvents.length,5);
  assert.equal(progressEvents.at(-1).done,5);

  const work=await store.read('user-1');
  // Existing Matrix record untouched.
  assert.equal(work.entries['tmdb:603'].data.rating,10);
  assert.equal(work.entries['tmdb:603'].data.favorite,true);
  assert.equal(work.entries['tmdb:603'].data.note,'My original Matrix note');
  // Matched TMDB film created and metadata cached.
  assert.equal(work.entries['tmdb:693134'].data.status,'Watched');
  assert.equal(work.entries['tmdb:693134'].data.rating,9);
  assert.equal(work.entries['tmdb:693134'].data.note,'Imax watch');
  assert.equal(work.entries['tmdb:693134'].data.watched_date,'2026-03-10');
  assert.equal(store.catalog.get('en:693134').poster_path,'/dune2.jpg');
  // 429 fallback custom films preserved with all ratings/notes/genres.
  const customEntries=Object.values(work.entries).filter(e=>e.data.custom);
  assert.equal(customEntries.length,3);
  const fallback1=customEntries.find(e=>e.data.custom.title==='Rate Limited Film 1');
  assert.equal(fallback1.data.status,'Watched');
  assert.equal(fallback1.data.rating,8);
  assert.equal(fallback1.data.note,'Saved as custom on 429');
  assert.equal(fallback1.data.custom.genre,'Drama');
});

// ---------- 3. stats-model.mjs tests ----------

test('computeCinemaStats handles empty libraries and computes ratings, minutes, genres, decades, cadence, and people accurately',()=>{
  const empty=computeCinemaStats({},{},{lang:'en',year:2026});
  assert.equal(empty.totals.total,0);
  assert.equal(empty.totals.watched,0);
  assert.equal(empty.totals.avgRating,null);
  assert.equal(empty.totals.totalMinutes,0);
  assert.equal(empty.ratingDistribution.length,10);
  assert.equal(empty.monthlyActivity.length,12);
  assert.deepEqual(empty.topGenres,[]);
  assert.deepEqual(empty.decades,[]);
  assert.deepEqual(empty.topDirectors,[]);
  assert.deepEqual(empty.topActors,[]);
  assert.deepEqual(empty.highestRated,[]);

  const t0=Date.parse('2026-01-01T00:00:00Z');
  const entries={};

  const m1=newRecord(603,{now:t0+1000});
  m1.data.status='Watched';
  m1.data.rating=10;
  m1.data.favorite=true;
  m1.data.note='All-time sci-fi favorite';
  m1.data.watched_date='2026-03-05';
  entries[m1.key]=m1;

  const m2=newRecord(27205,{now:t0+2000});
  m2.data.status='Watched';
  m2.data.rating=9;
  m2.data.favorite=false;
  m2.data.note='Dream layers';
  m2.data.watched_date='2026-03-19';
  entries[m2.key]=m2;

  const m3=newRecord(157336,{now:t0+3000});
  m3.data.status='Watched';
  m3.data.rating=9;
  m3.data.favorite=true;
  m3.data.note='';
  m3.data.watched_date='2025-12-20';
  entries[m3.key]=m3;

  const m4=newRecord(9991,{now:t0+4000});
  m4.data.status='Watchlist';
  m4.data.rating=null;
  m4.data.favorite=false;
  entries[m4.key]=m4;

  const custom=newRecord(null,{title:'Festival Short',year:1995,genre:'Sci-Fi, Drama',now:t0+5000});
  custom.data.status='Watched';
  custom.data.rating=8;
  custom.data.watched_date='2026-01-12';
  entries[custom.key]=custom;

  const deleted=newRecord(8888,{now:t0+6000});
  deleted.data.status='Watched';
  deleted.data.rating=1;
  deleted.data.deleted_at=iso(t0+7000);
  entries[deleted.key]=deleted;

  const metadataMap={
    'en:603':{
      id:603,title:'The Matrix',release_date:'1999-03-31',runtime:136,poster_path:'/matrix.jpg',
      genres:[{id:28,name:'Action'},{id:878,name:'Sci-Fi'}],
      credits:{
        cast:[{id:6384,name:'Keanu Reeves',profile_path:'/keanu.jpg'},{id:2975,name:'Laurence Fishburne',profile_path:'/laurence.jpg'}],
        crew:[{id:905,name:'Lana Wachowski',job:'Director',profile_path:'/lana.jpg'}],
      },
    },
    'en:27205':{
      id:27205,title:'Inception',release_date:'2010-07-16',runtime:148,poster_path:'/inception.jpg',
      genres:[{id:28,name:'Action'},{id:878,name:'Sci-Fi'}],
      credits:{
        cast:[{id:6193,name:'Leonardo DiCaprio',profile_path:'/leo.jpg'},{id:24045,name:'Joseph Gordon-Levitt',profile_path:'/jgl.jpg'}],
        crew:[{id:525,name:'Christopher Nolan',job:'Director',profile_path:'/nolan.jpg'}],
      },
    },
    'en:157336':{
      id:157336,title:'Interstellar',release_date:'2014-11-05',runtime:169,poster_path:'/interstellar.jpg',
      genres:[{id:18,name:'Drama'},{id:878,name:'Sci-Fi'}],
      credits:{
        cast:[{id:10297,name:'Matthew McConaughey',profile_path:'/matt.jpg'},{id:1813,name:'Anne Hathaway',profile_path:'/anne.jpg'}],
        crew:[{id:525,name:'Christopher Nolan',job:'Director',profile_path:'/nolan.jpg'}],
      },
    },
    'en:9991':{
      id:9991,title:'Future Watchlist Film',release_date:'1979-05-25',runtime:117,
      genres:[{id:27,name:'Horror'}],
    },
  };

  const stats=computeCinemaStats(entries,metadataMap,{lang:'en',year:2026});

  // Totals (deleted entry excluded; watchlist runtime excluded from watched totalMinutes).
  assert.deepEqual(stats.totals,{
    total:5,
    watched:4,
    watchlist:1,
    favorites:2,
    rated:4,
    withNotes:2,
    watchedThisYear:3,
    avgRating:9, // (10 + 9 + 9 + 8) / 4 = 9.0
    totalMinutes:136+148+169,
    runtimeCount:3,
  });

  // Rating distribution 1..10
  const r8=stats.ratingDistribution.find(x=>x.rating===8);
  const r9=stats.ratingDistribution.find(x=>x.rating===9);
  const r10=stats.ratingDistribution.find(x=>x.rating===10);
  assert.equal(r8.count,1);
  assert.equal(r8.share,0.5);
  assert.equal(r9.count,2);
  assert.equal(r9.share,1);
  assert.equal(r10.count,1);
  assert.equal(r10.share,0.5);

  // Top genres from watched films: Sci-Fi (4), Action (2), Drama (2); Horror on watchlist excluded.
  assert.equal(stats.topGenres[0].name,'Sci-Fi');
  assert.equal(stats.topGenres[0].count,4);
  assert.equal(stats.topGenres[0].avgRating,9);
  assert.equal(stats.topGenres[0].share,1);
  assert.equal(stats.topGenres.some(g=>g.name==='Horror'),false);

  // Chronological decades across active films: 1970s (1), 1990s (2), 2010s (2).
  assert.deepEqual(stats.decades.map(d=>({decade:d.decade,count:d.count})),[
    {decade:'1970s',count:1},
    {decade:'1990s',count:2},
    {decade:'2010s',count:2},
  ]);

  // Monthly activity for 2026: Jan=1, Mar=2.
  assert.equal(stats.monthlyActivity[0].month,1);
  assert.equal(stats.monthlyActivity[0].count,1);
  assert.equal(stats.monthlyActivity[0].share,0.5);
  assert.equal(stats.monthlyActivity[2].month,3);
  assert.equal(stats.monthlyActivity[2].count,2);
  assert.equal(stats.monthlyActivity[2].share,1);

  // Top directors: Christopher Nolan (2 films, avgRating 9.0) ahead of Lana Wachowski (1 film, 10.0).
  assert.equal(stats.topDirectors[0].id,525);
  assert.equal(stats.topDirectors[0].name,'Christopher Nolan');
  assert.equal(stats.topDirectors[0].count,2);
  assert.equal(stats.topDirectors[0].avgRating,9);
  assert.equal(stats.topDirectors[1].name,'Lana Wachowski');

  // Top actors from top-6 billed cast on watched films.
  assert.equal(stats.topActors.length,6);
  assert.equal(stats.topActors[0].name,'Keanu Reeves');
  assert.equal(stats.topActors[0].avgRating,10);

  // Highest rated: Matrix (10, fav), Interstellar (9, fav=true beats Inception fav=false), Inception (9), Festival Short (8).
  assert.deepEqual(stats.highestRated.map(x=>x.title),['The Matrix','Interstellar','Inception','Festival Short']);

  // Fallback to all active films when watched films have no genres.
  const watchlistOnly=computeCinemaStats({[m4.key]:m4},metadataMap,{lang:'en',year:2026});
  assert.equal(watchlistOnly.topGenres.length,1);
  assert.equal(watchlistOnly.topGenres[0].name,'Horror');
});

test('computeCinemaStats computes availableYears, overview ring/criticDelta/streak/median, records, weekdays, runtimeBuckets, topStudios, and Cinema Passport canvas',()=>{
  const empty=computeCinemaStats({},{},{lang:'en',year:2026});
  assert.ok(empty.availableYears.includes(2026));
  assert.equal(empty.overview.completionPct,0);
  assert.equal(empty.overview.completionRingDash,0);
  assert.equal(empty.overview.ringCircumference,251);
  assert.equal(empty.overview.medianRating,null);
  assert.equal(empty.overview.tmdbAvg,null);
  assert.equal(empty.overview.criticDelta,null);
  assert.equal(empty.overview.longestStreak,0);
  assert.deepEqual(empty.records,{longest:null,shortest:null,oldest:null,newest:null});
  assert.equal(empty.weekdays.length,7);
  assert.deepEqual(empty.runtimeBuckets.map(b=>b.key),['short','feature','extended','epic']);
  assert.deepEqual(empty.topStudios,[]);

  const t0=Date.parse('2026-01-01T00:00:00Z');
  const entries={};

  // 3 consecutive watch days in March 2026: 2026-03-02 (Mon), 2026-03-03 (Tue), 2026-03-04 (Wed), plus 2024-07-14 (Sun)
  const f1=newRecord(603,{now:t0+1000});
  f1.data.status='Watched';
  f1.data.rating=10;
  f1.data.favorite=true;
  f1.data.watched_date='2026-03-02'; // Monday (day=0)
  entries[f1.key]=f1;

  const f2=newRecord(27205,{now:t0+2000});
  f2.data.status='Watched';
  f2.data.rating=9;
  f2.data.favorite=false;
  f2.data.watched_date='2026-03-03'; // Tuesday (day=1)
  entries[f2.key]=f2;

  const f3=newRecord(157336,{now:t0+3000});
  f3.data.status='Watched';
  f3.data.rating=8;
  f3.data.favorite=true;
  f3.data.watched_date='2026-03-04'; // Wednesday (day=2)
  entries[f3.key]=f3;

  const f4=newRecord(777,{now:t0+4000});
  f4.data.status='Watched';
  f4.data.rating=7;
  f4.data.favorite=false;
  f4.data.watched_date='2024-07-14'; // Sunday (day=6)
  entries[f4.key]=f4;

  const f5=newRecord(999,{now:t0+5000});
  f5.data.status='Watchlist';
  f5.data.rating=null;
  entries[f5.key]=f5;

  const meta={
    'en:603':{
      id:603,title:'The Matrix',release_date:'1999-03-31',runtime:136,vote_average:8.2,
      genres:[{id:878,name:'Sci-Fi'}],
      production_companies:[{id:79,name:'Village Roadshow Pictures'},{id:174,name:'Warner Bros. Pictures'}],
    },
    'en:27205':{
      id:27205,title:'Inception',release_date:'2010-07-16',runtime:148,vote_average:8.4,
      genres:[{id:878,name:'Sci-Fi'}],
      production_companies:[{id:174,name:'Warner Bros. Pictures'},{id:9996,name:'Syncopy'}],
    },
    'en:157336':{
      id:157336,title:'Interstellar',release_date:'2014-11-05',runtime:169,vote_average:8.4,
      genres:[{id:878,name:'Sci-Fi'}],
      production_companies:[{id:174,name:'Warner Bros. Pictures'},{id:9996,name:'Syncopy'}],
    },
    'en:777':{
      id:777,title:'Sherlock Jr.',release_date:'1924-04-21',runtime:45,vote_average:8.0,
      genres:[{id:35,name:'Comedy'}],
      production_companies:[{id:55,name:'Buster Keaton Productions'}],
    },
    'en:999':{
      id:999,title:'Upcoming Odyssey',release_date:'2026-10-01',runtime:112,
      genres:[{id:18,name:'Drama'}],
    },
  };

  const stats=computeCinemaStats(entries,meta,{lang:'en',year:2026});

  // availableYears descending includes 2026 and 2024
  assert.equal(stats.availableYears[0],Math.max(2026,new Date().getFullYear()));
  assert.ok(stats.availableYears.includes(2026));
  assert.ok(stats.availableYears.includes(2024));

  // overview metrics: 4 watched of 5 total = 80%, ring dash = round(251 * 0.8) = 201
  assert.equal(stats.overview.completionPct,80);
  assert.equal(stats.overview.completionRingDash,201);
  assert.equal(stats.overview.ringCircumference,251);
  assert.equal(stats.overview.favoriteRate,50); // 2 favorites / 4 watched = 50%
  assert.equal(stats.overview.avgRuntime,Math.round((136+148+169+45)/4)); // 125
  assert.equal(stats.overview.totalDays,0.3); // 498 / 1440 = 0.345 -> 0.3
  assert.equal(stats.overview.medianRating,8.5); // [7, 8, 9, 10] -> 8.5
  assert.equal(stats.overview.tenCount,1);
  assert.equal(stats.overview.peakMonth,3);
  assert.equal(stats.overview.peakMonthCount,3);
  assert.equal(stats.overview.longestStreak,3); // Mar 2, 3, 4
  // Paired ratings: user avg = (10+9+8+7)/4 = 8.5, tmdb avg = (8.2+8.4+8.4+8.0)/4 = 8.25 -> 8.3, delta = +0.3
  assert.equal(stats.overview.tmdbAvg,8.3);
  assert.equal(stats.overview.criticDelta,0.3);
  assert.equal(stats.overview.topGenreName,'Sci-Fi');
  assert.equal(stats.overview.topDecade,'2010s');

  // records: longest=Interstellar(169m), shortest=Sherlock Jr.(45m), oldest=Sherlock Jr.(1924), newest=Upcoming Odyssey(2026)
  assert.equal(stats.records.longest.title,'Interstellar');
  assert.equal(stats.records.longest.runtime,169);
  assert.equal(stats.records.shortest.title,'Sherlock Jr.');
  assert.equal(stats.records.shortest.runtime,45);
  assert.equal(stats.records.oldest.title,'Sherlock Jr.');
  assert.equal(stats.records.oldest.year,1924);
  assert.equal(stats.records.newest.title,'Upcoming Odyssey');
  assert.equal(stats.records.newest.year,2026);

  // weekdays: Mon(0)=1, Tue(1)=1, Wed(2)=1, Sun(6)=1, others=0
  assert.deepEqual(stats.weekdays.map(w=>w.count),[1,1,1,0,0,0,1]);
  assert.equal(stats.weekdays[0].share,1);
  assert.equal(stats.weekdays[3].share,0);

  // runtimeBuckets: short(<90)=1 (45m), feature(90-119)=0, extended(120-149)=2 (136m, 148m), epic(150+)=1 (169m)
  assert.deepEqual(stats.runtimeBuckets,[
    {key:'short',count:1,share:0.5},
    {key:'feature',count:0,share:0},
    {key:'extended',count:2,share:1},
    {key:'epic',count:1,share:0.5},
  ]);

  // topStudios: Warner Bros. Pictures (3 films, avgRating 9.0), Syncopy (2 films, avgRating 8.5)
  assert.equal(stats.topStudios[0].id,174);
  assert.equal(stats.topStudios[0].name,'Warner Bros. Pictures');
  assert.equal(stats.topStudios[0].count,3);
  assert.equal(stats.topStudios[0].avgRating,9);
  assert.equal(stats.topStudios[1].name,'Syncopy');
  assert.equal(stats.topStudios[1].count,2);
  assert.equal(stats.topStudios[1].avgRating,8.5);

  // Turkish decade formatting & Canvas rendering smoke test
  assert.equal(formatDecadeLabel('1990s','tr'),"1990'lar");
  assert.equal(formatDecadeLabel('2020s','tr'),"2020'ler");
  assert.equal(formatDecadeLabel('2010s','en'),'2010s');

  const drawOps=[];
  const mockCtx={
    fillStyle:'',strokeStyle:'',lineWidth:1,lineCap:'',font:'',textAlign:'',textBaseline:'',
    createLinearGradient:()=>({addColorStop:()=>{}}),
    createRadialGradient:()=>({addColorStop:()=>{}}),
    fillRect:(...a)=>drawOps.push(['fillRect',...a]),
    beginPath:()=>{},moveTo:()=>{},lineTo:()=>{},arc:()=>{},arcTo:()=>{},closePath:()=>{},
    fill:()=>{},stroke:()=>{},save:()=>{},restore:()=>{},setLineDash:()=>{},
    measureText:s=>({width:String(s).length*9}),
    fillText:(text,x,y)=>drawOps.push(['fillText',String(text),x,y]),
  };
  const mockCanvas={width:0,height:0,getContext:type=>type==='2d'?mockCtx:null};
  renderStatsCardCanvas(mockCanvas,stats,{t:k=>k,lang:'en',user:{username:'cinephile',profile:{display_name:'Deniz'}}});
  assert.equal(mockCanvas.width,1080);
  assert.equal(mockCanvas.height,1350);
  assert.ok(drawOps.some(op=>op[0]==='fillText' && op[1].includes('myshelf.cloud')));
  assert.ok(drawOps.some(op=>op[0]==='fillText' && op[1].includes('@cinephile')));
});
