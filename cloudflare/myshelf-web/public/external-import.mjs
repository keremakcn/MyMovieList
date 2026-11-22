// Zero-dependency Letterboxd (ZIP/CSV) and IMDb (CSV) importer for the browser and Node 20+.
// Parsing rules mirror external_import.py so desktop and web imports behave identically.
import {foldTitle} from './library-model.mjs';

export const MAX_UPLOAD_BYTES=25*1024*1024;
export const MAX_ZIP_UNCOMPRESSED_BYTES=25*1024*1024;
export const MAX_ZIP_FILES=50;
export const MAX_IMPORT_ITEMS=10000;
export const MAX_NOTE_LENGTH=20000;
export const MAX_TITLE_LENGTH=300;
export const MAX_GENRE_LENGTH=300;

const LETTERBOXD_FILES=[['watched.csv','watched'],['ratings.csv','ratings'],['diary.csv','diary'],['reviews.csv','reviews'],['watchlist.csv','watchlist']];
const LETTERBOXD_FILE_MAP=new Map(LETTERBOXD_FILES);
const LETTERBOXD_KINDS=new Set(LETTERBOXD_FILE_MAP.values());
const LETTERBOXD_FILM_URI_KINDS=new Set(['watched','ratings','watchlist']);
const LETTERBOXD_IGNORED_DIRS=new Set(['deleted','orphaned','likes','lists','comments','__macosx']);
const IMDB_FILM_TYPES=new Set(['','movie','tvmovie','short','video']);

// Stable error codes: err.message === 'import_'+err.code.
export function importError(code){
  const error=Error('import_'+code);
  error.code=code;
  return error;
}

// ---------- text helpers ----------

function truncate(text,max){
  if(text.length<=max)return text;
  let out=text.slice(0,max);
  const last=out.charCodeAt(out.length-1);
  if(last>=0xd800 && last<=0xdbff)out=out.slice(0,-1);
  return out;
}

export const normalizeTitle=value=>foldTitle(value || '');
export const titleSlug=value=>foldTitle(value || '').replace(/[^a-z0-9]+/g,' ').trim();

export function cleanTitle(value){
  const text=String(value ?? '').replace(/[\r\n\t]+/g,' ').trim();
  return truncate(text,MAX_TITLE_LENGTH).trim();
}

export function cleanGenre(value){
  const text=String(value ?? '').replace(/[\r\n\t]+/g,' ').trim();
  if(!text)return null;
  return truncate(text,MAX_GENRE_LENGTH).trim() || null;
}

export function cleanNote(value){
  if(value===null || value===undefined)return null;
  const text=String(value).replace(/\r\n/g,'\n').replace(/\r/g,'\n').trim();
  if(!text)return null;
  return truncate(text,MAX_NOTE_LENGTH);
}

export function parseYear(value){
  if(Number.isInteger(value))return value>=1800 && value<=2200 ? value : null;
  const match=String(value ?? '').trim().match(/^(\d{4})(?:\D|$)/);
  if(!match)return null;
  const year=Number(match[1]);
  return year>=1800 && year<=2200 ? year : null;
}

export function parseIsoDate(value){
  const candidate=String(value ?? '').trim().slice(0,10);
  if(!/^\d{4}-\d{2}-\d{2}$/.test(candidate))return null;
  const [y,m,d]=candidate.split('-').map(Number);
  if(y<1 || m<1 || m>12 || d<1)return null;
  const days=new Date(Date.UTC(2000,m,0)).getUTCDate();
  const leap=y%4===0 && (y%100!==0 || y%400===0);
  if(d>(m===2 ? (leap ? 29 : 28) : days))return null;
  return candidate;
}

function parseNumber(value){
  const text=String(value ?? '').trim();
  if(!text || !/^[+-]?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$/i.test(text))return null;
  const n=Number(text);
  return Number.isFinite(n) ? n : null;
}

export function convertLetterboxdRating(value){
  const stars=parseNumber(value);
  if(stars===null || stars<=0)return null;
  return Math.max(1,Math.min(10,Math.round(stars*2)));
}

export function parseImdbRating(value){
  const score=parseNumber(value);
  if(score===null || score<1 || score>10)return null;
  return Math.max(1,Math.min(10,Math.round(score)));
}

const normalizeUri=value=>String(value ?? '').trim().replace(/\/+$/,'').toLowerCase();
const baseName=name=>String(name || '').replace(/\\/g,'/').split('/').pop().toLowerCase();

// ---------- CSV ----------

// RFC-4180 parser: quoted fields, "" escapes, multiline values, BOM strip, CRLF/LF/CR. Returns string[][].
export function parseCSV(text){
  let s=String(text ?? '');
  if(s.charCodeAt(0)===0xfeff)s=s.slice(1);
  const rows=[];
  let row=[],field='',inQuotes=false,quoted=false,started=false;
  for(let i=0;i<s.length;i++){
    const c=s[i];
    if(inQuotes){
      if(c==='"'){
        if(s[i+1]==='"'){field+='"';i++;}
        else inQuotes=false;
      }else field+=c;
      continue;
    }
    if(c==='"' && field==='' && !quoted){inQuotes=true;quoted=true;started=true;continue;}
    if(c===','){row.push(field);field='';quoted=false;started=true;continue;}
    if(c==='\r' || c==='\n'){
      if(c==='\r' && s[i+1]==='\n')i++;
      if(started || field!==''){row.push(field);rows.push(row);}
      row=[];field='';quoted=false;started=false;
      continue;
    }
    field+=c;started=true;
  }
  if(inQuotes)throw importError('malformed');
  if(started || field!==''){row.push(field);rows.push(row);}
  return rows;
}

function readCsvRecords(text){
  const rows=parseCSV(text);
  if(!rows.length)throw importError('no_header');
  const headers=rows[0].map(h=>String(h).trim().toLowerCase());
  if(!headers.some(Boolean))throw importError('no_header');
  const records=[];
  for(const raw of rows.slice(1)){
    const record=Object.create(null);
    headers.forEach((key,i)=>{if(key)record[key]=raw[i] ?? '';});
    records.push(record);
  }
  return {headers:new Set(headers.filter(Boolean)),rows:records};
}

const get=(row,key)=>row[key] ?? '';
const isLetterboxdHeaders=h=>h.has('name') && ['letterboxd uri','year','watched date','review','rating','date'].some(k=>h.has(k));
const isImdbHeaders=h=>h.has('title') && ['const','your rating','title type','imdb rating','date rated','position'].some(k=>h.has(k));

function detectLetterboxdKind(headers,filename=''){
  if(headers.has('review'))return 'reviews';
  if(headers.has('watched date') || headers.has('rewatch'))return 'diary';
  if(headers.has('rating'))return 'ratings';
  return baseName(filename).includes('watchlist') ? 'watchlist' : 'watched';
}

function decodeCsvBytes(bytes){
  if(!bytes || !bytes.byteLength)throw importError('empty');
  if(bytes.byteLength>MAX_UPLOAD_BYTES)throw importError('too_large');
  if(bytes.includes(0))throw importError('malformed');
  try{return new TextDecoder('utf-8',{fatal:true}).decode(bytes);}
  catch{throw importError('encoding');}
}

async function toBytes(input){
  if(input instanceof Uint8Array)return input;
  if(input instanceof ArrayBuffer)return new Uint8Array(input);
  if(ArrayBuffer.isView(input))return new Uint8Array(input.buffer,input.byteOffset,input.byteLength);
  if(input && typeof input.arrayBuffer==='function'){
    if(Number.isFinite(input.size) && input.size>MAX_UPLOAD_BYTES)throw importError('too_large');
    return new Uint8Array(await input.arrayBuffer());
  }
  throw importError('empty');
}

function textInput(input){
  if(typeof input==='string'){
    if(!input)throw importError('empty');
    if(input.length>MAX_UPLOAD_BYTES)throw importError('too_large');
    if(input.includes('\0'))throw importError('malformed');
    return input.charCodeAt(0)===0xfeff ? input.slice(1) : input;
  }
  if(input instanceof ArrayBuffer || ArrayBuffer.isView(input)){
    const bytes=input instanceof ArrayBuffer ? new Uint8Array(input) : new Uint8Array(input.buffer,input.byteOffset,input.byteLength);
    return decodeCsvBytes(bytes);
  }
  throw importError('empty');
}

// ---------- Letterboxd ----------

function mergeLetterboxdTables(tables){
  const entries=[],uriIndex=new Map(),titleYearIndex=new Map();
  const tyKey=(t,y)=>t+'\u0000'+(y ?? '');
  const find=(norm,year,uri,kind)=>{
    if(uri && uriIndex.has(uri))return uriIndex.get(uri);
    const existing=titleYearIndex.get(tyKey(norm,year));
    if(existing){
      // Diary/review rows carry entry URIs, not film URIs: only split on conflicting film-level URIs.
      if(LETTERBOXD_FILM_URI_KINDS.has(kind) && existing._film_uri && uri && existing._film_uri!==uri)return null;
      return existing;
    }
    return null;
  };
  for(const [kind,rows] of tables){
    for(const row of rows){
      const title=cleanTitle(get(row,'name'));
      if(!title)continue;
      const year=parseYear(get(row,'year'));
      const norm=normalizeTitle(title);
      if(!norm)continue;
      const uri=normalizeUri(get(row,'letterboxd uri'));
      let entry=find(norm,year,uri,kind);
      if(!entry){
        if(entries.length>=MAX_IMPORT_ITEMS)throw importError('too_many_items');
        entry={title,year,status:kind==='watchlist' ? 'Watchlist' : 'Watched',rating:null,watched_date:null,note:null,genre:null,external_id:uri || null,
          _film_uri:LETTERBOXD_FILM_URI_KINDS.has(kind) ? uri : '',_rating_from_ratings:false,_rating_date:'',_watched_date_priority:0,_notes:[]};
        entries.push(entry);
        const k=tyKey(norm,year);
        if(!titleYearIndex.has(k))titleYearIndex.set(k,entry);
        if(uri)uriIndex.set(uri,entry);
      }else if(uri){
        if(!uriIndex.has(uri))uriIndex.set(uri,entry);
        if(LETTERBOXD_FILM_URI_KINDS.has(kind) && !entry._film_uri)entry._film_uri=uri;
        if(!entry.external_id)entry.external_id=uri;
      }
      if(kind!=='watchlist')entry.status='Watched';

      const rowDate=parseIsoDate(get(row,'watched date')) || parseIsoDate(get(row,'date')) || '';
      const rating=convertLetterboxdRating(get(row,'rating'));
      if(rating!==null){
        if(kind==='ratings'){entry.rating=rating;entry._rating_from_ratings=true;}
        else if(!entry._rating_from_ratings && (entry.rating===null || rowDate>=entry._rating_date)){entry.rating=rating;entry._rating_date=rowDate;}
      }

      if(kind==='diary' || kind==='reviews'){
        const explicit=parseIsoDate(get(row,'watched date'));
        const fallback=parseIsoDate(get(row,'date'));
        if(explicit){
          if(entry._watched_date_priority<3 || !entry.watched_date || explicit>entry.watched_date){entry.watched_date=explicit;entry._watched_date_priority=3;}
        }else if(fallback && entry._watched_date_priority<=2){
          if(entry._watched_date_priority<2 || !entry.watched_date || fallback>entry.watched_date){entry.watched_date=fallback;entry._watched_date_priority=2;}
        }
      }else if(kind==='watched' || kind==='ratings'){
        const fallback=parseIsoDate(get(row,'date'));
        if(fallback && entry._watched_date_priority<=1){
          if(entry._watched_date_priority<1 || !entry.watched_date || fallback>entry.watched_date){entry.watched_date=fallback;entry._watched_date_priority=1;}
        }
      }

      if(kind==='reviews'){
        const review=cleanNote(get(row,'review'));
        if(review && !entry._notes.includes(review))entry._notes.push(review);
      }
    }
  }
  const items=entries.map(e=>({
    title:e.title,
    year:e.year,
    status:e.status,
    rating:e.rating,
    watched_date:e.status==='Watched' ? e.watched_date : null,
    note:e._notes.length ? cleanNote(e._notes.join('\n\n')) : null,
    genre:null,
    external_id:e.external_id,
  }));
  return {source:'letterboxd',items,skippedNonFilms:0};
}

export function parseLetterboxdCSV(text,filename='',kind=null){
  const {headers,rows}=readCsvRecords(textInput(text));
  if(!isLetterboxdHeaders(headers))throw importError('not_letterboxd');
  const detected=kind || detectLetterboxdKind(headers,filename);
  if(!LETTERBOXD_KINDS.has(detected))throw importError('unsupported_csv');
  return mergeLetterboxdTables([[detected,rows]]);
}

// ---------- ZIP ----------

const CRC_TABLE=(()=>{
  const table=new Uint32Array(256);
  for(let n=0;n<256;n++){
    let c=n;
    for(let k=0;k<8;k++)c=c&1 ? 0xedb88320^(c>>>1) : c>>>1;
    table[n]=c>>>0;
  }
  return table;
})();

function crc32(bytes){
  let c=0xffffffff;
  for(let i=0;i<bytes.length;i++)c=CRC_TABLE[(c^bytes[i])&0xff]^(c>>>8);
  return (c^0xffffffff)>>>0;
}

function zipMemberParts(name,externalAttr){
  if(!name || name.includes('\0') || name.startsWith('/') || name.startsWith('\\') || name.includes('\\') || name.includes(':'))throw importError('zip_unsafe_path');
  const parts=name.split('/').filter(p=>p!=='' && p!=='.');
  if(parts.includes('..'))throw importError('zip_unsafe_path');
  if((((externalAttr>>>16)&0o170000)>>>0)===0o120000)throw importError('zip_unsafe_path');
  return parts;
}

async function inflateRaw(data,limit){
  if(typeof DecompressionStream!=='function')throw importError('bad_zip');
  let stream;
  try{stream=new DecompressionStream('deflate-raw');}
  catch{throw importError('bad_zip');}
  const writer=stream.writable.getWriter();
  const writing=writer.write(data).then(()=>writer.close()).catch(()=>{});
  const reader=stream.readable.getReader();
  const chunks=[];
  let total=0;
  try{
    for(;;){
      const {done,value}=await reader.read();
      if(done)break;
      total+=value.byteLength;
      if(total>limit){
        reader.cancel().catch(()=>{});
        writer.abort().catch(()=>{});
        throw importError('zip_too_large');
      }
      chunks.push(value);
    }
  }catch(error){
    if(error?.code)throw error;
    throw importError('bad_zip');
  }
  await writing;
  const out=new Uint8Array(total);
  let offset=0;
  for(const chunk of chunks){out.set(chunk,offset);offset+=chunk.byteLength;}
  return out;
}

// Safely reads supported Letterboxd CSVs from a ZIP. Returns {'watched.csv': text, ...}.
export async function extractZipCSVs(arrayBuffer){
  const bytes=await toBytes(arrayBuffer);
  if(!bytes.byteLength)throw importError('empty');
  if(bytes.byteLength>MAX_UPLOAD_BYTES)throw importError('too_large');
  const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
  const len=bytes.byteLength;
  let eocd=-1;
  for(let i=len-22;i>=Math.max(0,len-22-65535);i--){
    if(view.getUint32(i,true)===0x06054b50){eocd=i;break;}
  }
  if(eocd<0)throw importError('bad_zip');
  const totalEntries=view.getUint16(eocd+10,true);
  const cdSize=view.getUint32(eocd+12,true);
  const cdOffset=view.getUint32(eocd+16,true);
  if(totalEntries===0xffff || cdSize===0xffffffff || cdOffset===0xffffffff)throw importError('bad_zip');
  if(cdOffset+cdSize>eocd)throw importError('bad_zip');
  if(totalEntries>MAX_ZIP_FILES)throw importError('zip_too_many_files');

  const nameDecoder=new TextDecoder('utf-8');
  const members=[];
  let p=cdOffset;
  const cdEnd=cdOffset+cdSize;
  while(p<cdEnd){
    if(p+46>cdEnd || view.getUint32(p,true)!==0x02014b50)throw importError('bad_zip');
    if(members.length>=MAX_ZIP_FILES)throw importError('zip_too_many_files');
    const nameLen=view.getUint16(p+28,true),extraLen=view.getUint16(p+30,true),commentLen=view.getUint16(p+32,true);
    if(p+46+nameLen>cdEnd)throw importError('bad_zip');
    members.push({
      flags:view.getUint16(p+8,true),
      method:view.getUint16(p+10,true),
      crc:view.getUint32(p+16,true),
      compressedSize:view.getUint32(p+20,true),
      size:view.getUint32(p+24,true),
      externalAttr:view.getUint32(p+38,true),
      localOffset:view.getUint32(p+42,true),
      name:nameDecoder.decode(bytes.subarray(p+46,p+46+nameLen)),
    });
    p+=46+nameLen+extraLen+commentLen;
  }
  if(members.length!==totalEntries)throw importError('bad_zip');

  let declared=0;
  const selected=new Map();
  for(const m of members){
    const parts=zipMemberParts(m.name,m.externalAttr);
    if(m.size>MAX_ZIP_UNCOMPRESSED_BYTES)throw importError('zip_too_large');
    declared+=m.size;
    if(declared>MAX_ZIP_UNCOMPRESSED_BYTES)throw importError('zip_too_large');
    if(m.name.endsWith('/') || !parts.length)continue;
    const lower=parts.map(x=>x.toLowerCase());
    if(lower.slice(0,-1).some(x=>LETTERBOXD_IGNORED_DIRS.has(x)))continue;
    if(parts.length>2)continue;
    const base=lower.at(-1);
    if(LETTERBOXD_FILE_MAP.has(base)){
      const existing=selected.get(base);
      if(!existing || parts.length<existing.depth)selected.set(base,{depth:parts.length,member:m});
    }
  }
  if(!selected.size)throw importError('zip_no_csv');

  let actual=0;
  const files={};
  for(const [csvName] of LETTERBOXD_FILES){
    const picked=selected.get(csvName);
    if(!picked)continue;
    const m=picked.member;
    if(m.flags&1)throw importError('bad_zip');
    const o=m.localOffset;
    if(o+30>len || view.getUint32(o,true)!==0x04034b50)throw importError('bad_zip');
    const start=o+30+view.getUint16(o+26,true)+view.getUint16(o+28,true);
    const end=start+m.compressedSize;
    if(end>len)throw importError('bad_zip');
    const data=bytes.subarray(start,end);
    let content;
    if(m.method===0){
      if(m.compressedSize!==m.size)throw importError('bad_zip');
      if(actual+data.byteLength>MAX_ZIP_UNCOMPRESSED_BYTES)throw importError('zip_too_large');
      content=data;
    }else if(m.method===8){
      content=await inflateRaw(data.slice(),MAX_ZIP_UNCOMPRESSED_BYTES-actual);
    }else throw importError('bad_zip');
    actual+=content.byteLength;
    if(actual>MAX_ZIP_UNCOMPRESSED_BYTES)throw importError('zip_too_large');
    if(content.byteLength!==m.size || crc32(content)!==m.crc)throw importError('bad_zip');
    if(!new TextDecoder('latin1').decode(content).trim())continue;
    files[csvName]=decodeCsvBytes(content);
  }
  return files;
}

export async function parseLetterboxdZip(arrayBuffer){
  const files=await extractZipCSVs(arrayBuffer);
  const tables=[];
  for(const [csvName,kind] of LETTERBOXD_FILES){
    if(!Object.hasOwn(files,csvName))continue;
    const {headers,rows}=readCsvRecords(files[csvName]);
    if(!isLetterboxdHeaders(headers))throw importError('not_letterboxd');
    tables.push([kind,rows]);
  }
  if(!tables.length)throw importError('zip_no_csv');
  return mergeLetterboxdTables(tables);
}

// ---------- IMDb ----------

export function parseImdbCSV(text,filename=''){
  const {headers,rows}=readCsvRecords(textInput(text));
  if(!isImdbHeaders(headers))throw importError('not_imdb');
  const base=baseName(filename);
  const watchedList=['watched','ratings','checkins','check-ins'].some(t=>base.includes(t));
  const items=[],byConst=new Map(),byTitleYear=new Map();
  let skippedNonFilms=0;
  for(const row of rows){
    const type=get(row,'title type').trim().toLowerCase().replace(/[\s_-]+/g,'');
    if(!IMDB_FILM_TYPES.has(type)){skippedNonFilms++;continue;}
    const title=cleanTitle(get(row,'title'));
    if(!title)continue;
    const norm=normalizeTitle(title);
    if(!norm)continue;
    const year=parseYear(get(row,'year')) ?? parseYear(get(row,'release date'));
    const constId=String(get(row,'const')).trim().toLowerCase();
    const rating=parseImdbRating(get(row,'your rating'));
    let watchedDate=parseIsoDate(get(row,'date rated'));
    const genre=cleanGenre(get(row,'genres'));
    const status=rating!==null || watchedDate!==null || watchedList ? 'Watched' : 'Watchlist';
    if(status!=='Watched')watchedDate=null;
    const tyKey=norm+'\u0000'+(year ?? '');
    const existing=(constId ? byConst.get(constId) : null) || byTitleYear.get(tyKey);
    if(existing){
      if(status==='Watched')existing.status='Watched';
      if(rating!==null)existing.rating=rating;
      if(watchedDate && (!existing.watched_date || watchedDate>existing.watched_date))existing.watched_date=watchedDate;
      if(genre && !existing.genre)existing.genre=genre;
      continue;
    }
    if(items.length>=MAX_IMPORT_ITEMS)throw importError('too_many_items');
    const entry={title,year,status,rating,watched_date:watchedDate,note:null,genre,external_id:constId || null};
    items.push(entry);
    if(constId)byConst.set(constId,entry);
    byTitleYear.set(tyKey,entry);
  }
  return {source:'imdb',items,skippedNonFilms};
}

// ---------- auto-detect ----------

export async function parseExternalFile(input,filename='',source='auto'){
  const name=String(filename || input?.name || '').trim();
  const last=name.toLowerCase().replace(/\\/g,'/').split('/').pop();
  const ext=last.includes('.') ? '.'+last.split('.').pop() : '';
  if(ext && ext!=='.zip' && ext!=='.csv')throw importError('unsupported_file');
  let text;
  if(typeof input==='string'){
    if(ext==='.zip')throw importError('bad_zip');
    text=textInput(input);
  }else{
    const bytes=await toBytes(input);
    if(!bytes.byteLength)throw importError('empty');
    if(bytes.byteLength>MAX_UPLOAD_BYTES)throw importError('too_large');
    const sig=bytes.byteLength>=4 && bytes[0]===0x50 && bytes[1]===0x4b && ((bytes[2]===3 && bytes[3]===4) || (bytes[2]===5 && bytes[3]===6) || (bytes[2]===7 && bytes[3]===8));
    if(ext==='.zip' || sig){
      if(source==='imdb')throw importError('imdb_zip');
      return parseLetterboxdZip(bytes);
    }
    text=decodeCsvBytes(bytes);
  }
  if(source==='letterboxd')return parseLetterboxdCSV(text,name);
  if(source==='imdb')return parseImdbCSV(text,name);
  const {headers}=readCsvRecords(text);
  if(isImdbHeaders(headers))return parseImdbCSV(text,name);
  if(isLetterboxdHeaders(headers))return parseLetterboxdCSV(text,name);
  throw importError('unsupported_csv');
}

// ---------- TMDB matching ----------

function normalizeCandidate(item){
  if(!item || typeof item!=='object')return null;
  if(Number.isSafeInteger(item.tmdb_id) && item.tmdb_id>=1 && item.tmdb_id<=9999999999){
    return {tmdb_id:item.tmdb_id,title:cleanTitle(item.title || ''),original_title:cleanTitle(item.original_title || ''),year:parseYear(item.year ?? item.release_date),raw:item};
  }
  if(Number.isSafeInteger(item.id) && item.id>=1 && item.id<=9999999999){
    return {tmdb_id:item.id,title:cleanTitle(item.title || ''),original_title:cleanTitle(item.original_title || ''),year:parseYear(item.release_date ?? item.year),raw:item};
  }
  return null;
}

// Python parity (pick_best_tmdb_match): exact slug within ±2 years ranks by year distance,
// partial (>=60% overlap) slugs require the exact year, unknown years accept exact titles only.
export function matchTmdbMovie(item,candidates){
  const target=titleSlug(item?.title);
  if(!target)return null;
  const year=parseYear(item?.year);
  let bestRank=null,best=null;
  (Array.isArray(candidates) ? candidates : []).forEach((raw,index)=>{
    const c=normalizeCandidate(raw);
    if(!c)return;
    const slugs=[titleSlug(c.title),titleSlug(c.original_title)].filter(Boolean);
    if(!slugs.length)return;
    const exact=slugs.includes(target);
    let partial=false;
    if(!exact){
      for(const slug of slugs){
        if(target.includes(slug) || slug.includes(target)){
          const shorter=Math.min(target.length,slug.length),longer=Math.max(target.length,slug.length);
          if(longer>0 && shorter/longer>=0.6){partial=true;break;}
        }
      }
    }
    let yearTier;
    if(year!==null && c.year!==null){
      const diff=Math.abs(c.year-year);
      if(exact && diff<=2)yearTier=diff;
      else if(partial && diff===0)yearTier=0;
      else return;
    }else if(exact)yearTier=3;
    else return;
    const rank=[yearTier,exact ? 0 : 1,index];
    if(!bestRank || rank[0]<bestRank[0] || (rank[0]===bestRank[0] && (rank[1]<bestRank[1] || (rank[1]===bestRank[1] && rank[2]<bestRank[2])))){
      bestRank=rank;best=c;
    }
  });
  return best;
}

// ---------- import executor ----------

const tyKey=(title,year)=>normalizeTitle(title)+'\u0000'+(year ?? '');

export async function importExternalItems(items,{owner,store,searchCatalog=null,onProgress=null,concurrency=3,lang='en'}={}){
  const list=Array.isArray(items) ? items : Array.isArray(items?.items) ? items.items : [];
  if(list.length>MAX_IMPORT_ITEMS)throw importError('too_many_items');
  if(!store || typeof store.read!=='function' || typeof store.add!=='function' || typeof store.edit!=='function')throw Error('invalid_store');

  const work=await store.read(owner);
  const active=Object.values(work?.entries || {}).filter(e=>e?.data && !e.data.deleted_at);
  const existingTmdb=new Set(),existingTitleYears=new Set();
  const metaKeys=[];
  for(const e of active){
    if(e.data.custom){existingTitleYears.add(tyKey(e.data.custom.title,e.data.custom.year));continue;}
    const id=Number(String(e.key).split(':')[1]);
    if(Number.isSafeInteger(id) && id>0){existingTmdb.add(id);metaKeys.push('en:'+id,'tr:'+id);}
  }
  if(metaKeys.length && typeof store.metadataBatch==='function'){
    let meta={};
    try{meta=await store.metadataBatch(metaKeys) || {};}catch{meta={};}
    for(const value of Object.values(meta)){
      if(!value || typeof value!=='object')continue;
      const year=parseYear(value.release_date ?? value.year);
      for(const t of [value.title,value.original_title])if(typeof t==='string' && t.trim())existingTitleYears.add(tyKey(t,year));
    }
  }

  const prepared=list.map(item=>{
    const title=cleanTitle(item?.title);
    const year=parseYear(item?.year);
    if(!title || !normalizeTitle(title))return null;
    const status=item.status==='Watched' || item.status==='Watchlist' ? item.status : 'Watchlist';
    const rating=Number.isInteger(item.rating) && item.rating>=1 && item.rating<=10 ? item.rating : null;
    return {title,year,status,rating,watched_date:status==='Watched' ? parseIsoDate(item.watched_date) : null,note:cleanNote(item.note),genre:cleanGenre(item.genre)};
  });

  // Bounded-concurrency catalog search with a circuit breaker; commits stay in input order.
  let catalogAvailable=typeof searchCatalog==='function';
  let consecutiveErrors=0;
  const limit=Math.max(1,Math.min(8,Number.isInteger(concurrency) ? concurrency : 3));
  const searches=new Array(prepared.length);
  const startSearch=i=>{
    if(searches[i])return;
    const item=prepared[i];
    if(!item || existingTitleYears.has(tyKey(item.title,item.year))){searches[i]=Promise.resolve(null);return;}
    searches[i]=(async()=>{
      if(!catalogAvailable)return null;
      try{
        const result=await searchCatalog(item.title,item);
        consecutiveErrors=0;
        const candidates=Array.isArray(result) ? result : Array.isArray(result?.results) ? result.results : [];
        return matchTmdbMovie(item,candidates);
      }catch(error){
        consecutiveErrors++;
        if(error?.status===429 || /429|rate/i.test(String(error?.message || '')) || consecutiveErrors>=3)catalogAvailable=false;
        return null;
      }
    })();
  };

  let imported=0,matchedTmdb=0,addedCustom=0,skippedExisting=0;
  const total=prepared.length;
  for(let i=0;i<total;i++){
    for(let j=i;j<Math.min(total,i+limit);j++)startSearch(j);
    const match=await searches[i];
    searches[i]=null;
    const item=prepared[i];
    if(item){
      if(existingTitleYears.has(tyKey(item.title,item.year))){
        skippedExisting++;
      }else if(match){
        const id=match.tmdb_id;
        const matchTitle=cleanTitle(match.title || item.title) || item.title;
        const matchYear=match.year ?? item.year;
        if(existingTmdb.has(id) || existingTitleYears.has(tyKey(matchTitle,matchYear))){
          skippedExisting++;
        }else{
          const key=await store.add(owner,id);
          await store.edit(owner,key,{status:item.status,rating:item.rating,note:item.note,watched_date:item.watched_date});
          if(typeof store.cacheMetadata==='function' && Number.isSafeInteger(match.raw?.id)){
            try{await store.cacheMetadata(lang+':'+id,match.raw);}catch{}
          }
          existingTmdb.add(id);
          existingTitleYears.add(tyKey(item.title,item.year));
          existingTitleYears.add(tyKey(matchTitle,matchYear));
          imported++;matchedTmdb++;
        }
      }else{
        const key=await store.add(owner,null,{title:item.title,year:item.year,genre:item.genre});
        if(item.status!=='Watchlist' || item.rating!==null || item.note!==null || item.watched_date!==null){
          await store.edit(owner,key,{status:item.status,rating:item.rating,note:item.note,watched_date:item.watched_date});
        }
        existingTitleYears.add(tyKey(item.title,item.year));
        imported++;addedCustom++;
      }
    }
    onProgress?.({done:i+1,total,currentTitle:item?.title || ''});
  }
  return {imported,matchedTmdb,addedCustom,skippedExisting,skippedNonFilms:Number(items?.skippedNonFilms) || 0,catalogOffline:typeof searchCatalog==='function' && !catalogAvailable};
}
