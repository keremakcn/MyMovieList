// Mirrors name_policy.py; private movie notes are never filtered.
const roots=["hitler", "motherfucker", "orospu", "siktir", "sikeyim", "sikim", "yarrak", "yarak", "amcik", "gotveren", "nigger", "faggot"], tokens=new Set(["amk", "aq", "asshole", "bastard", "bitch", "bitchboy", "cunt", "dick", "dickhead", "fuck", "fucker", "fuckhead", "fucking", "fuckoff", "fuckyou", "nazi", "nazifan", "nazis", "nazism", "pussy", "shit", "shithead", "shitty", "sik"]);
const leet={'0':'o','1':'i','3':'e','4':'a','5':'s','7':'t','8':'b'};
export function nameAllowed(value) {
  if(typeof value!=='string')return false;
  const normalized=value.normalize('NFKD').toLowerCase().replaceAll('ı','i').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,'_');
  for(const candidate of [normalized,normalized.replace(/[0134578]/g,c=>leet[c])]){
    const compact=candidate.replaceAll('_','');
    if(roots.some(root=>compact.includes(root)) || tokens.has(compact) || candidate.replace(/[0-9]+/g,'_').split('_').some(token=>tokens.has(token)))return false;
  }
  return true;
}
