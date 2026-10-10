// The personal-record contract matches personal_data.py. Titles never identify films.
export const FIELDS = ['status','rating','note','favorite','watched_date','added_at','order_key','deleted_at','custom'];
export const EDITABLE = FIELDS.filter(k => !['added_at','order_key'].includes(k));
export const equal = (a,b) => stable(a) === stable(b);
function stable(v) {
  if (Array.isArray(v)) return '['+v.map(stable).join(',')+']';
  if (v && typeof v==='object') return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+stable(v[k])).join(',')+'}';
  return JSON.stringify(v);
}
export function iso(time=Date.now()) { return new Date(time).toISOString().replace(/\.([0-9]{3})Z$/,'.$1000+00:00'); }
export function timestamp(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(value) || !Number.isFinite(Date.parse(value))) throw Error('invalid_time');
  const [year,month,day,hour,minute,second]=value.match(/^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})/).slice(1).map(Number);
  const days=new Date(Date.UTC(year,month,0)).getUTCDate();
  if(year<1 || month<1 || month>12 || day<1 || day>days || hour>23 || minute>59 || second>59)throw Error('invalid_time');
  const match=value.match(/\.(\d{1,6})/);
  const micros=match ? match[1].padEnd(6,'0') : '000000';
  return new Date(Date.parse(value)).toISOString().slice(0,19)+'.'+micros+'+00:00';
}
export function versions(value={}) {
  if (!value || typeof value!=='object' || Array.isArray(value) || Object.keys(value).some(k=>!EDITABLE.includes(k))) throw Error('invalid_versions');
  return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,timestamp(v)]));
}
export function validateRecord(key,data) {
  if (!/^(tmdb:[1-9][0-9]{0,9}|custom:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/.test(key) || !data || typeof data!=='object' || Array.isArray(data) || !equal(Object.keys(data).sort(),[...FIELDS].sort())) throw Error('invalid_record');
  const d=structuredClone(data);
  if (!['Watchlist','Watched'].includes(d.status) || typeof d.favorite!=='boolean' || (d.rating!==null && (!Number.isInteger(d.rating) || d.rating<1 || d.rating>10)) || (d.note!==null && (typeof d.note!=='string' || d.note.length>20000))) throw Error('invalid_record');
  if (d.watched_date!==null && (!/^\d{4}-\d{2}-\d{2}$/.test(d.watched_date) || iso(Date.parse(d.watched_date)).slice(0,10)!==d.watched_date)) throw Error('invalid_record');
  d.added_at=timestamp(d.added_at); d.deleted_at=d.deleted_at===null ? null : timestamp(d.deleted_at);
  if (!/^[0-9]{20}:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(d.order_key)) throw Error('invalid_record');
  if (key.startsWith('tmdb:')) { if (d.custom!==null) throw Error('invalid_record'); }
  else if (!d.custom || !equal(Object.keys(d.custom).sort(),['genre','title','year']) || typeof d.custom.title!=='string' || !d.custom.title.trim() || d.custom.title.length>300 || (d.custom.year!==null && (!Number.isInteger(d.custom.year) || d.custom.year<1800 || d.custom.year>2200)) || (d.custom.genre!==null && (typeof d.custom.genre!=='string' || d.custom.genre.length>300))) throw Error('invalid_record');
  return d;
}
export function merge(base,local,remote,localVersions={},remoteVersions=null,now=Date.now()) {
  const ours=versions(localVersions), theirs=versions(remoteVersions || {});
  const changedLocal=new Set(EDITABLE.filter(k=>!base || !equal(local[k],base[k])));
  const changedRemote=new Set(EDITABLE.filter(k=>!base || !equal(remote[k],base[k])));
  const result=structuredClone(remote), times={...theirs};
  const newer=k=>{
    const a=ours[k],b=theirs[k];
    if (remoteVersions===null || !a || !b || a===b || Date.parse(a)>now+300000 || Date.parse(b)>now+300000) return null;
    return a>b;
  };
  for (const k of EDITABLE) {
    if (changedLocal.has(k)) {
      let keep=true;
      if (changedRemote.has(k) && !equal(local[k],remote[k])) {
        keep=newer(k); if (keep===null) return {conflict:true};
      }
      if (keep) {result[k]=structuredClone(local[k]); if (ours[k]) times[k]=ours[k]; else delete times[k];}
    }
    if (equal(local[k],remote[k]) && ours[k] && theirs[k]) times[k]=ours[k]>theirs[k] ? ours[k] : theirs[k];
  }
  for (const [deleted,edited,deletedTimes,editedTimes,changes] of [[local,remote,ours,theirs,changedRemote],[remote,local,theirs,ours,changedLocal]]) {
    if (deleted.deleted_at===null || edited.deleted_at!==null || (base && equal(deleted.deleted_at,base.deleted_at))) continue;
    const edits=[...changes].filter(k=>k!=='deleted_at'); if (!edits.length) continue;
    const a=deletedTimes.deleted_at,b=edits.map(k=>editedTimes[k]);
    if (remoteVersions===null || !a || b.some(t=>!t) || [a,...b].some(t=>Date.parse(t)>now+300000)) return {conflict:true};
    const latest=b.sort().at(-1); if (a===latest) return {conflict:true};
    result.deleted_at=latest>a ? null : deleted.deleted_at; times.deleted_at=latest>a ? latest : a;
  }
  result.added_at=remote.added_at; result.order_key=remote.order_key;
  return {conflict:false,data:result,versions:times};
}
export function newRecord(id,{title='',year=null,genre=null,now=Date.now()}={}) {
  const key=id ? 'tmdb:'+id : 'custom:'+crypto.randomUUID();
  const data={status:'Watchlist',rating:null,note:null,favorite:false,watched_date:null,added_at:iso(now),order_key:String(Math.round(now*1000)).padStart(20,'0')+':'+crypto.randomUUID(),deleted_at:null,custom:id ? null : {title,year,genre}};
  return {key,data:validateRecord(key,data),versions:Object.fromEntries(EDITABLE.map(k=>[k,iso(now)])),baseline:null,baseVersions:{},revision:0,outbox:null,conflict:null};
}
