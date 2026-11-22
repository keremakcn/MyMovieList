import {nameAllowed} from './name-policy.mjs';
import {validDate} from './recommendation-model.mjs';
const avatars=new Set(['luna','cocoa','sunshine','sage','coral','cloud','midnight','peach','sky','mocha','lilac','mint','cherry','gold','ocean','silver'].map(s=>'cat-'+s));
const username=value=>typeof value==='string'&&/^[a-z][a-z0-9_]{2,23}$/.test(value)&&nameAllowed(value);
const fields=(value,keys)=>value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).sort().join(',')===keys.sort().join(',');
export function socialQuery(value=''){
  if(typeof value!=='string')throw Error('invalid_request');
  value=value.trim().replace(/^@/,'');if([...value].length>60 || /[\x00-\x1f\x7f]/.test(value))throw Error('invalid_request');return value;
}
export function socialPosition(view,value){
  if(value==null)return null;
  const keys=view==='people'?['username']:['username','tmdb_id','watched_date','week_start'];
  if(!['people','week'].includes(view)||!fields(value,keys)||!username(value.username))throw Error('invalid_request');
  if(view==='week'&&(!Number.isInteger(value.tmdb_id)||value.tmdb_id<1||value.tmdb_id>9999999999||!validDate(value.watched_date)||!validDate(value.week_start)))throw Error('invalid_request');
  return {...value};
}
export function socialCursor(view,query,position){
  const bytes=new TextEncoder().encode(JSON.stringify({view,query,position}));
  return btoa(String.fromCharCode(...bytes)).replaceAll('+','-').replaceAll('/','_').replaceAll('=','');
}
export function decodeSocialCursor(token,view,query){
  if(!token)return null;
  if(typeof token!=='string'||token.length>1024||!/^[A-Za-z0-9_-]+$/.test(token))throw Error('invalid_request');
  try{
    const raw=Uint8Array.from(atob(token.replaceAll('-','+').replaceAll('_','/')),c=>c.charCodeAt(0));
    const value=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(raw));
    if(!fields(value,['view','query','position'])||value.view!==view||value.query!==query)throw Error();
    return socialPosition(view,value.position);
  }catch{throw Error('invalid_request');}
}
function member(raw){
  if(!fields(raw,['username','display_name','avatar_id'])||!username(raw.username)||typeof raw.display_name!=='string'||[...raw.display_name].length>40||/[\x00-\x1f]/.test(raw.display_name)||!nameAllowed(raw.display_name)||!avatars.has(raw.avatar_id))throw Error('invalid_response');
  return {...raw};
}
export function socialPage(value,view){
  if(!['people','week'].includes(view)||!fields(value,['protocol','view','rows','next_cursor','week_start','week_end'])||value.protocol!==1||value.view!==view||!validDate(value.week_start)||!validDate(value.week_end))throw Error('invalid_response');
  const start=Date.parse(value.week_start+'T00:00:00Z'),end=Date.parse(value.week_end+'T00:00:00Z');
  if(new Date(start).getUTCDay()!==1 || end-start!==6*86400000 || !Array.isArray(value.rows)||value.rows.length>(view==='people'?16:12))throw Error('invalid_response');
  const identities=new Set();let last=null;
  const rows=value.rows.map(raw=>{
    let row;
    if(view==='people')row=member(raw);
    else{
      const base=['username','display_name','avatar_id','tmdb_id','watched_date'];
      if(!fields(raw,base)&&!fields(raw,[...base,'rating']))throw Error('invalid_response');
      member({username:raw.username,display_name:raw.display_name,avatar_id:raw.avatar_id});
      if(!Number.isInteger(raw.tmdb_id)||raw.tmdb_id<1||raw.tmdb_id>9999999999||!validDate(raw.watched_date)||raw.watched_date<value.week_start||raw.watched_date>value.week_end||'rating' in raw&&(!Number.isInteger(raw.rating)||raw.rating<1||raw.rating>10))throw Error('invalid_response');
      row={...raw};const id=row.username+':'+row.tmdb_id;if(identities.has(id))throw Error('invalid_response');identities.add(id);
    }
    if(last && (view==='people'?row.username<=last.username:row.watched_date>last.watched_date || row.watched_date===last.watched_date&&(row.username<last.username || row.username===last.username&&row.tmdb_id<=last.tmdb_id)))throw Error('invalid_response');
    last=row;return row;
  });
  let next;
  try{next=socialPosition(view,value.next_cursor);}catch{throw Error('invalid_response');}
  if(next){
    if(!last||rows.length!==(view==='people'?16:12))throw Error('invalid_response');
    const expected=view==='people'?{username:last.username}:{username:last.username,tmdb_id:last.tmdb_id,watched_date:last.watched_date,week_start:value.week_start};
    if(Object.keys(expected).some(k=>next[k]!==expected[k]))throw Error('invalid_response');
  }
  return {...value,rows,next_cursor:next};
}
