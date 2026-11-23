// Pure HTML5 Canvas 1080x1350 Shareable Cinema Passport PNG generator for MyShelf Web.
// Zero external image assets, zero CORS taint, strict CSP-compliant (no inline styles).

const CARD_W=1080;
const CARD_H=1350;
const SANS='Inter, "Segoe UI", system-ui, -apple-system, sans-serif';
const SERIF='Georgia, "Iowan Old Style", "Times New Roman", serif';

function roundRectPath(ctx,x,y,w,h,r){
  const radius=Math.max(0,Math.min(r,w/2,h/2));
  ctx.beginPath();
  ctx.moveTo(x+radius,y);
  ctx.arcTo(x+w,y,x+w,y+h,radius);
  ctx.arcTo(x+w,y+h,x,y+h,radius);
  ctx.arcTo(x,y+h,x,y,radius);
  ctx.arcTo(x,y,x+w,y,radius);
  ctx.closePath();
}

function fillPanel(ctx,x,y,w,h,r,{fill='#161720',stroke='rgba(255,255,255,0.08)',lineWidth=1.5}={}){
  roundRectPath(ctx,x,y,w,h,r);
  if(fill){
    ctx.fillStyle=fill;
    ctx.fill();
  }
  if(stroke){
    ctx.strokeStyle=stroke;
    ctx.lineWidth=lineWidth;
    ctx.stroke();
  }
}

function fitText(ctx,text,maxWidth){
  const str=String(text ?? '');
  if(!str || ctx.measureText(str).width<=maxWidth)return str;
  const ellipsis='…';
  let lo=0,hi=str.length;
  while(lo<hi){
    const mid=Math.ceil((lo+hi)/2);
    if(ctx.measureText(str.slice(0,mid)+ellipsis).width<=maxWidth)lo=mid;
    else hi=mid-1;
  }
  return str.slice(0,Math.max(1,lo))+ellipsis;
}

function formatDuration(totalMinutes,t){
  if(!totalMinutes || totalMinutes<=0)return `0 ${t('statsHours')}`;
  const hours=Math.floor(totalMinutes/60),mins=totalMinutes%60;
  return mins>0 ? `${hours}${t('statsHours')} ${mins}${t('statsMinutesShort')}` : `${hours}${t('statsHours')}`;
}

export function formatDecadeLabel(decade,lang='en'){
  if(!decade)return '';
  if(lang!=='tr')return String(decade);
  const start=Number(String(decade).replace(/\D/g,''));
  if(!Number.isInteger(start))return String(decade);
  const suffixes={0:'ler',1:'lar',2:'ler',3:'lar',4:'lar',5:'ler',6:'lar',7:'ler',8:'ler',9:'lar'};
  return `${start}'${suffixes[Math.floor(start/10)%10] || 'ler'}`;
}

export function renderStatsCardCanvas(canvas,stats,{t,lang='en',user=null}={}){
  if(!canvas)return;
  canvas.width=CARD_W;
  canvas.height=CARD_H;
  const ctx=canvas.getContext('2d');
  if(!ctx)return;

  const {totals,overview,records}=stats;
  const tr=key=>typeof t==='function' ? t(key) : key;

  // 1. Obsidian velvet background + projector lavender + warm gold glows
  const bgGrad=ctx.createLinearGradient(0,0,0,CARD_H);
  bgGrad.addColorStop(0,'#11121a');
  bgGrad.addColorStop(0.5,'#0d0e14');
  bgGrad.addColorStop(1,'#090a0f');
  ctx.fillStyle=bgGrad;
  ctx.fillRect(0,0,CARD_W,CARD_H);

  const lavGlow=ctx.createRadialGradient(220,120,20,220,120,640);
  lavGlow.addColorStop(0,'rgba(196, 177, 255, 0.18)');
  lavGlow.addColorStop(0.55,'rgba(196, 177, 255, 0.05)');
  lavGlow.addColorStop(1,'rgba(196, 177, 255, 0)');
  ctx.fillStyle=lavGlow;
  ctx.fillRect(0,0,CARD_W,CARD_H);

  const goldGlow=ctx.createRadialGradient(880,1150,20,880,1150,620);
  goldGlow.addColorStop(0,'rgba(229, 199, 135, 0.14)');
  goldGlow.addColorStop(0.6,'rgba(229, 199, 135, 0.03)');
  goldGlow.addColorStop(1,'rgba(229, 199, 135, 0)');
  ctx.fillStyle=goldGlow;
  ctx.fillRect(0,0,CARD_W,CARD_H);

  const roseGlow=ctx.createRadialGradient(860,260,10,860,260,420);
  roseGlow.addColorStop(0,'rgba(241, 135, 153, 0.08)');
  roseGlow.addColorStop(1,'rgba(241, 135, 153, 0)');
  ctx.fillStyle=roseGlow;
  ctx.fillRect(0,0,CARD_W,CARD_H);

  // Subtle screening-room dot matrix texture at top
  ctx.fillStyle='rgba(255,255,255,0.025)';
  for(let gx=72;gx<=1008;gx+=36){
    for(let gy=68;gy<=240;gy+=36){
      ctx.beginPath();
      ctx.arc(gx,gy,1.1,0,Math.PI*2);
      ctx.fill();
    }
  }

  // Double hairline festival poster border
  fillPanel(ctx,32,32,1016,1286,28,{fill:null,stroke:'rgba(255, 255, 255, 0.12)',lineWidth:1.5});
  fillPanel(ctx,44,44,992,1262,22,{fill:null,stroke:'rgba(196, 177, 255, 0.18)',lineWidth:1});

  // 2. Header section: Eyebrow + Year badge + Georgia Serif headline + Curator handle
  ctx.beginPath();
  ctx.arc(82,88,5,0,Math.PI*2);
  ctx.fillStyle='#c4b1ff';
  ctx.fill();

  ctx.font=`650 16px ${SANS}`;
  ctx.fillStyle='#c4b1ff';
  ctx.textAlign='left';
  ctx.textBaseline='middle';
  ctx.fillText(String(tr('statsCardEyebrow')).toUpperCase(),98,88);

  // Year badge pill
  const yearBadgeText=`${stats.year} · ${String(tr('statsCardEdition')).toUpperCase()}`;
  ctx.font=`650 15px ${SANS}`;
  const yearBadgeW=Math.ceil(ctx.measureText(yearBadgeText).width)+34;
  fillPanel(ctx,1008-yearBadgeW,69,yearBadgeW,38,19,{fill:'rgba(229, 199, 135, 0.12)',stroke:'rgba(229, 199, 135, 0.38)',lineWidth:1.2});
  ctx.fillStyle='#e5c787';
  ctx.textAlign='center';
  ctx.fillText(yearBadgeText,1008-yearBadgeW/2,88);

  // Main Georgia serif headline
  const headline=overview.topGenreName
    ? tr('statsDrawnTo').replace('{genre}',overview.topGenreName)
    : tr('statsTitle');
  ctx.font=`400 48px ${SERIF}`;
  ctx.fillStyle='#f4f1ec';
  ctx.textAlign='left';
  ctx.textBaseline='alphabetic';
  ctx.fillText(fitText(ctx,headline,920),72,152);

  // Optional user display name / @username subtitle
  const displayName=user?.profile?.display_name?.trim() || '';
  const username=user?.username?.trim() ? '@'+user.username.trim() : '';
  const identityLine=[displayName,username].filter(Boolean).join(' · ') || tr('statsCardSubtitle');
  ctx.font=`500 20px ${SANS}`;
  ctx.fillStyle='#a1a0b2';
  ctx.fillText(fitText(ctx,identityLine,920),72,188);

  // 3. Completion Donut Ring + 4 KPI Tiles (y=218..418)
  fillPanel(ctx,72,218,248,200,20,{fill:'rgba(22, 23, 32, 0.92)',stroke:'rgba(196, 177, 255, 0.18)'});
  const ringCx=196,ringCy=306,ringR=54;
  ctx.beginPath();
  ctx.arc(ringCx,ringCy,ringR,0,Math.PI*2);
  ctx.strokeStyle='rgba(255, 255, 255, 0.09)';
  ctx.lineWidth=11;
  ctx.stroke();

  if(overview.completionPct>0){
    const startAngle=-Math.PI/2;
    const endAngle=startAngle+(Math.PI*2*Math.min(100,overview.completionPct))/100;
    const ringGrad=ctx.createLinearGradient(ringCx-ringR,ringCy-ringR,ringCx+ringR,ringCy+ringR);
    ringGrad.addColorStop(0,'#c4b1ff');
    ringGrad.addColorStop(1,'#e5c787');
    ctx.beginPath();
    ctx.arc(ringCx,ringCy,ringR,startAngle,endAngle);
    ctx.strokeStyle=ringGrad;
    ctx.lineWidth=11;
    ctx.lineCap='round';
    ctx.stroke();
  }
  ctx.font=`700 28px ${SANS}`;
  ctx.fillStyle='#f4f1ec';
  ctx.textAlign='center';
  ctx.textBaseline='middle';
  ctx.fillText(`${overview.completionPct}%`,ringCx,ringCy-6);
  ctx.font=`500 13px ${SANS}`;
  ctx.fillStyle='#a1a0b2';
  ctx.fillText(tr('statsWatched'),ringCx,ringCy+18);
  ctx.fillText(`${totals.watched}/${totals.total} ${tr('filmCount')}`,ringCx,392);

  // 4 KPI tiles in a 2x2 grid on the right
  const kpiTiles=[
    {
      label:tr('statsWatched'),
      value:totals.watched.toLocaleString(),
      sub:`${stats.year}: ${totals.watchedThisYear} ${tr('statsThisYear')}`,
      color:'#f4f1ec',
    },
    {
      label:tr('statsWatchTime'),
      value:formatDuration(totals.totalMinutes,tr),
      sub:overview.totalDays>0 ? `${overview.totalDays} ${tr('statsDays')}` : `${totals.runtimeCount} ${tr('filmCount')}`,
      color:'#c4b1ff',
    },
    {
      label:tr('statsAvgRating'),
      value:totals.avgRating!==null ? `★ ${totals.avgRating}` : '—',
      sub:overview.medianRating!==null
        ? `${totals.rated} ${tr('statsRatedCount')} · ${tr('statsMedianShort')} ${overview.medianRating}`
        : `${totals.rated} ${tr('statsRatedCount')}`,
      color:'#e5c787',
    },
    {
      label:tr('statsFavorites'),
      value:`♥ ${totals.favorites.toLocaleString()}`,
      sub:`${overview.favoriteRate}% · ${totals.watchlist} ${tr('statsWatchlist')}`,
      color:'#f18799',
    },
  ];

  const tileW=324,tileH=93,tileGapX=20,tileGapY=14,tileStartX=340,tileStartY=218;
  kpiTiles.forEach((tile,idx)=>{
    const col=idx%2,row=Math.floor(idx/2);
    const tx=tileStartX+col*(tileW+tileGapX);
    const ty=tileStartY+row*(tileH+tileGapY);
    fillPanel(ctx,tx,ty,tileW,tileH,18,{fill:'rgba(22, 23, 32, 0.92)',stroke:'rgba(255, 255, 255, 0.08)'});
    ctx.textAlign='left';
    ctx.textBaseline='alphabetic';
    ctx.font=`600 13px ${SANS}`;
    ctx.fillStyle='#a1a0b2';
    ctx.fillText(fitText(ctx,tile.label.toUpperCase(),tileW-32),tx+18,ty+26);
    ctx.font=`700 28px ${SANS}`;
    ctx.fillStyle=tile.color;
    ctx.fillText(fitText(ctx,tile.value,tileW-32),tx+18,ty+58);
    ctx.font=`500 13px ${SANS}`;
    ctx.fillStyle='#a1a0b2';
    ctx.fillText(fitText(ctx,tile.sub,tileW-32),tx+18,ty+79);
  });

  // 4. Insight chips row (Critic delta, Peak era, Streak, 10/10 count, Avg runtime)
  const chips=[];
  if(overview.topDecade){
    chips.push({text:tr('statsPeakEra').replace('{era}',formatDecadeLabel(overview.topDecade,lang)),gold:false});
  }
  if(overview.criticDelta!==null){
    const deltaText=overview.criticDelta>0
      ? tr('statsCriticAbove').replace('{delta}',`+${overview.criticDelta}`)
      : overview.criticDelta<0
        ? tr('statsCriticBelow').replace('{delta}',String(overview.criticDelta))
        : tr('statsCriticMatch').replace('{avg}',String(overview.tmdbAvg));
    chips.push({text:deltaText,gold:true});
  }
  if(overview.longestStreak>1){
    chips.push({text:tr('statsBestStreak').replace('{days}',String(overview.longestStreak)),gold:false});
  }
  if(overview.tenCount>0){
    chips.push({text:tr('statsMasterpieces').replace('{count}',String(overview.tenCount)),gold:true});
  }
  if(overview.avgRuntime){
    chips.push({text:tr('statsAvgRuntimeChip').replace('{min}',String(overview.avgRuntime)),gold:false});
  }

  let chipX=72;
  const chipY=434,chipH=38;
  ctx.font=`600 14px ${SANS}`;
  for(const chip of chips){
    const cw=Math.ceil(ctx.measureText(chip.text).width)+30;
    if(chipX+cw>1008)break;
    fillPanel(ctx,chipX,chipY,cw,chipH,19,{
      fill:chip.gold ? 'rgba(229, 199, 135, 0.12)' : 'rgba(196, 177, 255, 0.10)',
      stroke:chip.gold ? 'rgba(229, 199, 135, 0.34)' : 'rgba(196, 177, 255, 0.26)',
      lineWidth:1,
    });
    ctx.fillStyle=chip.gold ? '#e5c787' : '#d7c9ff';
    ctx.textAlign='center';
    ctx.textBaseline='middle';
    ctx.fillText(chip.text,chipX+cw/2,chipY+chipH/2);
    chipX+=cw+12;
  }

  // 5. Painted 1-10 Rating Histogram Panel (y=490..722)
  const histY=490,histH=232;
  fillPanel(ctx,72,histY,936,histH,20,{fill:'rgba(22, 23, 32, 0.92)',stroke:'rgba(255, 255, 255, 0.08)'});
  ctx.textAlign='left';
  ctx.textBaseline='alphabetic';
  ctx.font=`400 24px ${SERIF}`;
  ctx.fillStyle='#f4f1ec';
  ctx.fillText(tr('statsRatingsTitle'),98,histY+38);

  ctx.textAlign='right';
  ctx.font=`500 14px ${SANS}`;
  ctx.fillStyle='#a1a0b2';
  const histBadge=totals.avgRating!==null
    ? `★ ${totals.avgRating} · ${totals.rated} ${tr('statsRatedCount')}`
    : tr('statsNoRatings');
  ctx.fillText(histBadge,982,histY+36);

  const barAreaX=102,barAreaY=histY+66,barAreaW=876,barAreaH=118;
  const binGap=18;
  const binW=Math.floor((barAreaW-binGap*9)/10);
  stats.ratingDistribution.forEach((bin,i)=>{
    const bx=barAreaX+i*(binW+binGap);
    // Track
    fillPanel(ctx,bx,barAreaY,binW,barAreaH,8,{fill:'rgba(255, 255, 255, 0.05)',stroke:null});
    // Fill
    if(bin.count>0){
      const bh=Math.max(10,Math.round(bin.share*barAreaH));
      const by=barAreaY+barAreaH-bh;
      const fillCol=bin.rating>=8 ? '#e5c787' : '#c4b1ff';
      fillPanel(ctx,bx,by,binW,bh,8,{fill:fillCol,stroke:null});
      ctx.font=`650 13px ${SANS}`;
      ctx.fillStyle='#f4f1ec';
      ctx.textAlign='center';
      ctx.fillText(String(bin.count),bx+binW/2,by-7);
    }
    ctx.font=`600 13px ${SANS}`;
    ctx.fillStyle=bin.rating>=8 ? '#e5c787' : '#a1a0b2';
    ctx.textAlign='center';
    ctx.fillText(`★${bin.rating}`,bx+binW/2,barAreaY+barAreaH+24);
  });

  // 6. Two-Column Editorial Split (y=742..1194)
  const colY=742,colH=452,colW=456;
  // Left Column: Top Genres + Top Director & Studio
  fillPanel(ctx,72,colY,colW,colH,20,{fill:'rgba(22, 23, 32, 0.92)',stroke:'rgba(255, 255, 255, 0.08)'});
  ctx.textAlign='left';
  ctx.textBaseline='alphabetic';
  ctx.font=`400 24px ${SERIF}`;
  ctx.fillStyle='#f4f1ec';
  ctx.fillText(tr('statsGenresTitle'),96,colY+38);

  const genres=stats.topGenres.slice(0,4);
  if(genres.length){
    genres.forEach((g,idx)=>{
      const gy=colY+74+idx*54;
      ctx.font=`600 16px ${SANS}`;
      ctx.fillStyle='#f4f1ec';
      ctx.textAlign='left';
      ctx.fillText(fitText(ctx,g.name,240),96,gy);

      ctx.font=`500 14px ${SANS}`;
      ctx.fillStyle='#a1a0b2';
      ctx.textAlign='right';
      const gMeta=`${g.count} ${tr('filmCount')}${g.avgRating!==null ? ` · ★ ${g.avgRating}` : ''}`;
      ctx.fillText(gMeta,72+colW-24,gy);

      const trackY=gy+10,trackW=colW-48;
      fillPanel(ctx,96,trackY,trackW,8,4,{fill:'rgba(255, 255, 255, 0.07)',stroke:null});
      const fillW=Math.max(12,Math.round((g.share || 0)*trackW));
      fillPanel(ctx,96,trackY,fillW,8,4,{fill:idx===0 ? '#e5c787' : '#c4b1ff',stroke:null});
    });
  }else{
    ctx.font=`500 15px ${SANS}`;
    ctx.fillStyle='#a1a0b2';
    ctx.fillText(fitText(ctx,tr('statsNoGenres'),colW-48),96,colY+90);
  }

  // Divider inside left column
  ctx.strokeStyle='rgba(255, 255, 255, 0.08)';
  ctx.lineWidth=1;
  ctx.beginPath();
  ctx.moveTo(96,colY+296);
  ctx.lineTo(72+colW-24,colY+296);
  ctx.stroke();

  // Director & Studio / Actor spotlights
  const topDir=stats.topDirectors[0] || null;
  const topStudioOrActor=stats.topStudios[0] || stats.topActors[0] || null;
  const secondLabel=stats.topStudios[0] ? tr('statsTopStudioLabel') : tr('statsTopActorLabel');

  const drawSpotlight=(label,entity,sy)=>{
    ctx.textAlign='left';
    ctx.font=`650 12px ${SANS}`;
    ctx.fillStyle='#c4b1ff';
    ctx.fillText(String(label).toUpperCase(),96,sy);
    ctx.font=`650 18px ${SANS}`;
    ctx.fillStyle='#f4f1ec';
    const nameText=entity ? entity.name : '—';
    ctx.fillText(fitText(ctx,nameText,275),96,sy+26);
    if(entity){
      ctx.textAlign='right';
      ctx.font=`600 14px ${SANS}`;
      ctx.fillStyle='#e5c787';
      const metaText=`${entity.count} ${tr('filmCount')}${entity.avgRating!==null ? ` · ★ ${entity.avgRating}` : ''}`;
      ctx.fillText(metaText,72+colW-24,sy+26);
    }
  };
  drawSpotlight(tr('statsTopDirectorLabel'),topDir,colY+324);
  drawSpotlight(secondLabel,topStudioOrActor,colY+386);

  // Right Column: Top 3 Highest-Rated Films + Archive Milestone Record
  const rightX=552;
  fillPanel(ctx,rightX,colY,colW,colH,20,{fill:'rgba(22, 23, 32, 0.92)',stroke:'rgba(255, 255, 255, 0.08)'});
  ctx.textAlign='left';
  ctx.textBaseline='alphabetic';
  ctx.font=`400 24px ${SERIF}`;
  ctx.fillStyle='#f4f1ec';
  ctx.fillText(tr('statsHighestRatedTitle'),rightX+24,colY+38);

  const topFilms=stats.highestRated.slice(0,3);
  if(topFilms.length){
    topFilms.forEach((film,idx)=>{
      const fy=colY+64+idx*72;
      fillPanel(ctx,rightX+24,fy,colW-48,58,14,{fill:'rgba(31, 32, 44, 0.85)',stroke:'rgba(255, 255, 255, 0.06)'});
      // Rank badge
      fillPanel(ctx,rightX+36,fy+13,32,32,9,{fill:'rgba(229, 199, 135, 0.15)',stroke:'rgba(229, 199, 135, 0.35)'});
      ctx.font=`700 14px ${SANS}`;
      ctx.fillStyle='#e5c787';
      ctx.textAlign='center';
      ctx.textBaseline='middle';
      ctx.fillText(`0${idx+1}`,rightX+52,fy+29);

      // Title + year
      ctx.textAlign='left';
      ctx.textBaseline='alphabetic';
      ctx.font=`650 16px ${SANS}`;
      ctx.fillStyle='#f4f1ec';
      ctx.fillText(fitText(ctx,film.title,240),rightX+80,fy+26);

      ctx.font=`500 13px ${SANS}`;
      ctx.fillStyle='#a1a0b2';
      const subParts=[film.year || '',film.favorite ? '♥' : ''].filter(Boolean).join(' · ');
      ctx.fillText(subParts,rightX+80,fy+45);

      // Rating badge
      ctx.textAlign='right';
      ctx.font=`700 16px ${SANS}`;
      ctx.fillStyle='#e5c787';
      ctx.fillText(`★ ${film.rating}/10`,rightX+colW-38,fy+35);
    });
  }else{
    ctx.font=`500 15px ${SANS}`;
    ctx.fillStyle='#a1a0b2';
    ctx.fillText(fitText(ctx,tr('statsNoRatings'),colW-48),rightX+24,colY+90);
  }

  // Divider inside right column
  ctx.strokeStyle='rgba(255, 255, 255, 0.08)';
  ctx.lineWidth=1;
  ctx.beginPath();
  ctx.moveTo(rightX+24,colY+296);
  ctx.lineTo(rightX+colW-24,colY+296);
  ctx.stroke();

  // Archive Milestone Record (Longest + Oldest)
  const rec1=records?.longest ? {label:tr('statsRecordLongest'),film:records.longest,meta:`${records.longest.runtime} ${tr('minutes')}`} : null;
  const rec2=records?.oldest ? {label:tr('statsRecordOldest'),film:records.oldest,meta:String(records.oldest.year || '')} : null;

  const drawMilestone=(rec,my)=>{
    ctx.textAlign='left';
    ctx.font=`650 12px ${SANS}`;
    ctx.fillStyle='#e5c787';
    ctx.fillText(String(rec ? rec.label : tr('statsMilestonesTitle')).toUpperCase(),rightX+24,my);
    ctx.font=`650 18px ${SANS}`;
    ctx.fillStyle='#f4f1ec';
    ctx.fillText(fitText(ctx,rec ? rec.film.title : '—',285),rightX+24,my+26);
    if(rec){
      ctx.textAlign='right';
      ctx.font=`600 14px ${SANS}`;
      ctx.fillStyle='#a1a0b2';
      ctx.fillText(rec.meta,rightX+colW-24,my+26);
    }
  };
  drawMilestone(rec1,colY+324);
  drawMilestone(rec2,colY+386);

  // 7. Cinema Ticket Perforation Footer (y=1222..1290)
  ctx.save();
  ctx.setLineDash([8,8]);
  ctx.strokeStyle='rgba(196, 177, 255, 0.24)';
  ctx.lineWidth=1.5;
  ctx.beginPath();
  ctx.moveTo(72,1222);
  ctx.lineTo(1008,1222);
  ctx.stroke();
  ctx.restore();

  // Ticket notch punch-outs
  for(const nx of [44,1036]){
    ctx.beginPath();
    ctx.arc(nx,1222,12,0,Math.PI*2);
    ctx.fillStyle='#090a0f';
    ctx.fill();
    ctx.strokeStyle='rgba(196, 177, 255, 0.25)';
    ctx.lineWidth=1;
    ctx.stroke();
  }

  ctx.textAlign='left';
  ctx.textBaseline='middle';
  ctx.font=`600 16px ${SANS}`;
  ctx.fillStyle='#a1a0b2';
  ctx.fillText(`MyMovieList · ${tr('statsCardFooter')}`,72,1262);

  ctx.textAlign='right';
  ctx.font=`700 20px ${SANS}`;
  ctx.fillStyle='#e5c787';
  ctx.fillText('myshelf.cloud',1008,1262);
}

function canvasToBlob(canvas){
  return new Promise(resolve=>{
    if(typeof canvas.toBlob==='function'){
      canvas.toBlob(blob=>resolve(blob),'image/png');
    }else{
      resolve(null);
    }
  });
}

export function openStatsCardDialog(stats,{t,lang='en',user=null,toast}={}){
  const dialog=document.querySelector('#stats-card-dialog');
  const content=document.querySelector('#stats-card-content');
  if(!dialog || !content)return;
  const tr=key=>typeof t==='function' ? t(key) : key;
  const canCopy=typeof ClipboardItem!=='undefined' && Boolean(navigator.clipboard?.write);

  content.innerHTML=
    `<div class="auth-body stats-card-modal-body">`+
      `<div class="eyebrow"><span class="dot"></span>${tr('statsCardEyebrow')}</div>`+
      `<h1 id="stats-card-title">${tr('statsCardTitle')}</h1>`+
      `<p>${tr('statsCardP')}</p>`+
      `<div class="stats-card-preview-wrap">`+
        `<canvas id="stats-card-canvas" class="stats-card-canvas" width="${CARD_W}" height="${CARD_H}" aria-label="${tr('statsCardTitle')}"></canvas>`+
      `</div>`+
      `<div class="actions stats-card-actions">`+
        `<button type="button" class="button" id="stats-card-download">${tr('statsCardDownload')} ↓</button>`+
        (canCopy ? `<button type="button" class="button secondary" id="stats-card-copy">${tr('statsCardCopy')}</button>` : '')+
      `</div>`+
    `</div>`;

  const canvas=content.querySelector('#stats-card-canvas');
  renderStatsCardCanvas(canvas,stats,{t:tr,lang,user});

  const downloadBtn=content.querySelector('#stats-card-download');
  downloadBtn?.addEventListener('click',async()=>{
    downloadBtn.disabled=true;
    try{
      const filename=`MyMovieList-Cinema-Passport-${stats.year}.png`;
      const blob=await canvasToBlob(canvas);
      const url=blob ? URL.createObjectURL(blob) : canvas.toDataURL('image/png');
      const link=document.createElement('a');
      link.href=url;
      link.download=filename;
      link.click();
      if(blob)setTimeout(()=>URL.revokeObjectURL(url),1500);
      toast?.(tr('statsCardDownloaded'));
    }finally{
      if(downloadBtn.isConnected)downloadBtn.disabled=false;
    }
  });

  const copyBtn=content.querySelector('#stats-card-copy');
  copyBtn?.addEventListener('click',async()=>{
    copyBtn.disabled=true;
    try{
      const blob=await canvasToBlob(canvas);
      if(!blob)throw Error('copy_failed');
      await navigator.clipboard.write([new ClipboardItem({'image/png':blob})]);
      toast?.(tr('statsCardCopied'));
    }catch{
      toast?.(tr('genericError'));
    }finally{
      if(copyBtn.isConnected)copyBtn.disabled=false;
    }
  });

  if(!dialog.open)dialog.showModal();
}
