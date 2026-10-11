const posterPath=/^\/[A-Za-z0-9_-]+\.(jpg|jpeg|png|webp)$/;
export const posterDay=(now=new Date())=>now.toISOString().slice(0,10);
export function posterPicks(results){
  const films=new Map();
  for(const movie of Array.isArray(results)?results:[]){
    if(movie && Number.isSafeInteger(movie.id) && movie.id>0 && movie.id<=9999999999 && !movie.adult && posterPath.test(movie.poster_path || '') && !films.has(movie.id))films.set(movie.id,movie);
    if(films.size===4)break;
  }
  return [...films.values()];
}
export async function dailyPosters(language,{pref,fetchCatalog,now=new Date()}){
  const day=posterDay(now),key='hero-posters:'+language;
  // Only public catalog data is cached here, separately for each language.
  const cached=await pref(key).catch(()=>null),previous=posterPicks(cached?.films);
  if(cached?.day===day && previous.length)return {day,films:previous};
  try{
    const response=await fetchCatalog(`catalog/trending/movie/day?language=${language==='tr'?'tr-TR':'en-US'}`);
    const films=posterPicks(response.results);
    if(!films.length)throw Error('catalog_unavailable');
    const result={day,films};
    await pref(key,result).catch(()=>{});
    return result;
  }catch(error){
    // An outage must not overwrite a usable selection or mark it up to date.
    if(previous.length)return {day:cached.day,films:previous};
    throw error;
  }
}
