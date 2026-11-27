// Obsidian Screening Room UX Engine for MyShelf Web PWA (100% CSP-safe, zero inline HTML style attributes).
import {entryTitle,entryYear,foldTitle,tmdbIdOf} from './library-model.mjs';

export const NOIR_SILHOUETTE_SVG=
  `<svg class="noir-silhouette-svg" viewBox="0 0 64 80" fill="none" aria-hidden="true">`+
    `<polygon points="0,0 44,0 64,80 14,80" fill="currentColor" opacity="0.07"/>`+
    `<path d="M12 29c5-2.5 14-4 25-3.2 8.8.6 15.2 2.4 18 4.4-5.2.9-14.6 1.5-24.5 1.2C21.4 31.1 15 30.3 12 29Z" fill="currentColor" opacity="0.36"/>`+
    `<path d="M21 27.5c1.4-7.2 5.2-11.5 11.4-11.5 5.8 0 9.4 4.1 10.6 11.5" fill="currentColor" opacity="0.26" stroke="currentColor" stroke-width="1.3"/>`+
    `<path d="M24 31c.6 6.8 4.2 11.2 8.8 11.2 4.5 0 8-4.4 8.6-11.2" fill="currentColor" opacity="0.22"/>`+
    `<path d="M8 78c2.2-15.6 9.8-24.8 24.4-25.8 14.4 1 22.2 10.2 24.6 25.8" fill="currentColor" opacity="0.2" stroke="currentColor" stroke-width="1.35"/>`+
    `<path d="M24 53l8.4 13.5L40.8 53" stroke="currentColor" stroke-width="1.3" opacity="0.5"/>`+
  `</svg>`;

export function withTransition(fn){
  if(typeof document!=='undefined' && document.startViewTransition && !matchMedia('(prefers-reduced-motion: reduce)').matches){
    document.startViewTransition(()=>fn());
  }else{
    fn();
  }
}

export function initCinemaUX({state,store,api,t,e,image,navigate,render,queueSync,toast,openMovie,switchLanguage,setLibraryView,openImport}){
  const mq=window.matchMedia('(prefers-reduced-motion: reduce)');
  let reduceMotion=mq.matches;
  mq.addEventListener?.('change',ev=>{reduceMotion=ev.matches;});

  // 1. Real-Time Ambient Backdrop Bleed Projector (<canvas>)
  const ambientCanvas=document.getElementById('ambient-canvas');
  const amb={r1:196,g1:177,b1:255,r2:229,g2:199,b2:135,tr1:196,tg1:177,tb1:255,tr2:229,tg2:199,tb2:135,raf:0};
  const palettes=[
    [[196,177,255],[229,199,135]],
    [[118,184,248],[214,166,255]],
    [[241,135,153],[235,204,142]],
    [[122,214,180],[196,177,255]],
    [[236,176,120],[176,142,248]],
  ];
  function seedPalette(seed){
    let h=2166136261;
    const s=String(seed || 'MyShelf');
    for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619);}
    return palettes[Math.abs(h)%palettes.length];
  }
  function drawAmbient(){
    amb.raf=0;
    const k=0.08;
    amb.r1+=(amb.tr1-amb.r1)*k;amb.g1+=(amb.tg1-amb.g1)*k;amb.b1+=(amb.tb1-amb.b1)*k;
    amb.r2+=(amb.tr2-amb.r2)*k;amb.g2+=(amb.tg2-amb.g2)*k;amb.b2+=(amb.tb2-amb.b2)*k;
    if(ambientCanvas){
      const ctx=ambientCanvas.getContext('2d');
      if(ctx){
        const w=ambientCanvas.width=Math.min(window.innerWidth,960);
        const h=ambientCanvas.height=Math.min(window.innerHeight,640);
        ctx.clearRect(0,0,w,h);
        const g1=ctx.createRadialGradient(w*0.52,h*0.14,12,w*0.52,h*0.14,w*0.58);
        g1.addColorStop(0,`rgba(${Math.round(amb.r1)},${Math.round(amb.g1)},${Math.round(amb.b1)},0.19)`);
        g1.addColorStop(1,'rgba(0,0,0,0)');
        ctx.fillStyle=g1;ctx.fillRect(0,0,w,h);
        const g2=ctx.createRadialGradient(w*0.86,h*0.42,12,w*0.86,h*0.42,w*0.46);
        g2.addColorStop(0,`rgba(${Math.round(amb.r2)},${Math.round(amb.g2)},${Math.round(amb.b2)},0.12)`);
        g2.addColorStop(1,'rgba(0,0,0,0)');
        ctx.fillStyle=g2;ctx.fillRect(0,0,w,h);
      }
    }
    const diff=Math.abs(amb.tr1-amb.r1)+Math.abs(amb.tg1-amb.g1)+Math.abs(amb.tb1-amb.b1);
    if(diff>0.8 && !reduceMotion)amb.raf=requestAnimationFrame(drawAmbient);
  }
  function setAmbientSeed(seed){
    const [p1,p2]=seedPalette(seed);
    amb.tr1=p1[0];amb.tg1=p1[1];amb.tb1=p1[2];
    amb.tr2=p2[0];amb.tg2=p2[1];amb.tb2=p2[2];
    if(!amb.raf)amb.raf=requestAnimationFrame(drawAmbient);
  }
  drawAmbient();

  // 2. 3D Perspective Tilt + Specular Glare
  let tiltEl=null;
  document.addEventListener('pointermove',ev=>{
    if(reduceMotion || ev.pointerType==='touch')return;
    const card=ev.target.closest('.poster-button, .member-card, .showcase-pick');
    if(!card || card.closest('.view-shelf')){
      if(tiltEl){tiltEl.classList.remove('is-tilting');tiltEl.style.setProperty('--glare-opacity','0');tiltEl=null;}
      return;
    }
    if(tiltEl && tiltEl!==card){tiltEl.classList.remove('is-tilting');tiltEl.style.setProperty('--glare-opacity','0');}
    if(tiltEl!==card){
      tiltEl=card;
      const label=card.querySelector('img')?.alt || card.textContent || '';
      setAmbientSeed(label);
    }
    const rect=card.getBoundingClientRect();
    if(!rect.width || !rect.height)return;
    const px=(ev.clientX-rect.left)/rect.width;
    const py=(ev.clientY-rect.top)/rect.height;
    card.classList.add('is-tilting');
    card.style.setProperty('--rx',((0.5-py)*9).toFixed(2)+'deg');
    card.style.setProperty('--ry',((px-0.5)*9).toFixed(2)+'deg');
    card.style.setProperty('--gx',Math.round(px*100)+'%');
    card.style.setProperty('--gy',Math.round(py*100)+'%');
    card.style.setProperty('--glare-opacity','1');
  },{passive:true});

  // 3D Spatial Shelf tap-to-expand spine support
  document.addEventListener('click',ev=>{
    const spine=ev.target.closest('.shelf-spine-face');
    if(!spine)return;
    const card=spine.closest('.movie-card');
    const grid=card?.closest('.view-shelf');
    if(!card || !grid)return;
    const open=card.classList.contains('is-shelf-open');
    grid.querySelectorAll('.movie-card.is-shelf-open').forEach(c=>c.classList.remove('is-shelf-open'));
    if(!open)card.classList.add('is-shelf-open');
  });

  // 3. Micro-Particle Heart Burst (<canvas>)
  const pCanvas=document.getElementById('particle-canvas');
  const particles=[];
  let pRaf=0;
  function tickParticles(){
    if(!pCanvas){pRaf=0;return;}
    const ctx=pCanvas.getContext('2d');
    pCanvas.width=window.innerWidth;pCanvas.height=window.innerHeight;
    ctx.clearRect(0,0,pCanvas.width,pCanvas.height);
    for(let i=particles.length-1;i>=0;i--){
      const p=particles[i];
      p.x+=p.vx;p.y+=p.vy;p.vy+=0.14;p.life-=0.028;
      if(p.life<=0){particles.splice(i,1);continue;}
      ctx.globalAlpha=Math.max(0,p.life);
      ctx.fillStyle=p.color;
      ctx.beginPath();ctx.arc(p.x,p.y,p.size,0,Math.PI*2);ctx.fill();
    }
    pRaf=particles.length ? requestAnimationFrame(tickParticles) : 0;
  }
  function burstHeart(origin){
    if(reduceMotion || !pCanvas || !origin)return;
    const r=origin.getBoundingClientRect();
    const cx=r.left+r.width/2,cy=r.top+r.height/2;
    const cols=['#f18799','#e5c787','#c4b1ff','#ff9eb5'];
    for(let i=0;i<14;i++){
      const a=(Math.PI*2*i)/14+(Math.random()-0.5)*0.3;
      const sp=1.8+Math.random()*3;
      particles.push({x:cx,y:cy,vx:Math.cos(a)*sp,vy:Math.sin(a)*sp-1.2,size:2+Math.random()*2.4,color:cols[i%cols.length],life:1});
    }
    if(!pRaf)pRaf=requestAnimationFrame(tickParticles);
  }
  document.addEventListener('click',ev=>{
    const hb=ev.target.closest('[data-person-favorite]');
    if(hb && hb.getAttribute('aria-pressed')!=='true')burstHeart(hb);
  });

  // 4. Universal Ctrl+K / ⌘K Spotlight Command Center
  const dialog=document.getElementById('command-dialog');
  const input=document.getElementById('command-input');
  const body=document.getElementById('command-body');
  let cmdRows=[],cmdIdx=0,cmdTimer=0,lastRemote={q:'',items:[]};

  function setActiveCmd(idx){
    if(!cmdRows.length)return;
    cmdIdx=(idx+cmdRows.length)%cmdRows.length;
    cmdRows.forEach((r,i)=>{
      r.el.setAttribute('aria-selected',String(i===cmdIdx));
      if(i===cmdIdx)r.el.scrollIntoView({block:'nearest'});
    });
  }

  async function renderPalette(){
    if(!body)return;
    const q=(input?.value || '').trim();
    const qFold=foldTitle(q);
    const work=await store.read(state.owner);
    const active=Object.values(work.entries || {}).filter(x=>x?.data && !x.data.deleted_at);
    body.replaceChildren();
    cmdRows=[];

    const addGroup=(label,items)=>{
      if(!items.length)return;
      const h=document.createElement('div');
      h.className='cmd-group-title';h.textContent=label;
      const ul=document.createElement('ul');
      ul.className='cmd-list';ul.setAttribute('role','listbox');
      for(const item of items){
        const li=document.createElement('li');
        li.className='cmd-row';li.setAttribute('role','option');li.setAttribute('aria-selected','false');
        const main=document.createElement('div');main.className='cmd-row-main';
        if(item.thumb){
          const im=document.createElement('img');im.className='cmd-thumb';im.src=item.thumb;im.alt='';main.append(im);
        }else{
          const ic=document.createElement('span');ic.className='cmd-chip';ic.textContent=item.symbol || '✦';main.append(ic);
        }
        const tx=document.createElement('div');tx.className='cmd-text';
        const st=document.createElement('strong');st.textContent=item.title;
        const sm=document.createElement('small');sm.textContent=item.sub || '';
        tx.append(st,sm);main.append(tx);li.append(main);

        const acts=document.createElement('div');acts.className='cmd-actions';
        if(item.catalogMovieId){
          const key='tmdb:'+item.catalogMovieId;
          const existing=work.entries[key];
          if(existing && !existing.data.deleted_at){
            const b=document.createElement('span');b.className='cmd-mini is-saved';
            b.textContent='✓ '+(existing.data.status==='Watched'?t('watched'):t('saved'));
            acts.append(b);
          }else{
            const bWant=document.createElement('button');bWant.type='button';bWant.className='cmd-mini';
            bWant.textContent='+ '+t('watchlist');
            bWant.addEventListener('click',async ev=>{
              ev.stopPropagation();bWant.disabled=true;
              await store.add(state.owner,item.catalogMovieId);
              queueSync();toast(t('added'));await renderPalette();render();
            });
            const bWatched=document.createElement('button');bWatched.type='button';bWatched.className='cmd-mini';
            bWatched.textContent='✓ '+t('cmdMarkWatched');
            bWatched.addEventListener('click',async ev=>{
              ev.stopPropagation();bWatched.disabled=true;
              await store.add(state.owner,item.catalogMovieId);
              await store.edit(state.owner,'tmdb:'+item.catalogMovieId,{status:'Watched'});
              queueSync();toast(t('added'));await renderPalette();render();
            });
            acts.append(bWant,bWatched);
          }
        }else if(item.kbd){
          const kb=document.createElement('kbd');kb.textContent=item.kbd;acts.append(kb);
        }
        li.append(acts);
        const idx=cmdRows.length;
        li.addEventListener('pointermove',()=>setActiveCmd(idx));
        li.addEventListener('click',()=>{dialog.close();item.run();});
        cmdRows.push({el:li,run:item.run});
        ul.append(li);
      }
      body.append(h,ul);
    };

    if(q.length>=2){
      const metaKeys=active.slice(0,120).flatMap(x=>{const id=tmdbIdOf(x);return id?[state.lang+':'+id]:[];});
      const meta=metaKeys.length ? await store.metadataBatch(metaKeys) : {};
      const libMatches=[];
      for(const entry of active){
        const title=entryTitle(entry,meta,state.lang);
        if(title && foldTitle(title).includes(qFold)){
          const id=tmdbIdOf(entry);
          const m=id ? meta[state.lang+':'+id] : null;
          libMatches.push({
            thumb:m ? image(m.poster_path,'w185') : '',
            symbol:'◈',
            title,
            sub:[entryYear(entry,meta,state.lang),entry.data.status==='Watched'?t('watched'):t('watchlist'),entry.data.rating?'★ '+entry.data.rating:''].filter(Boolean).join(' · '),
            kbd:'↵',
            run:()=>openMovie(id,entry.key),
          });
          if(libMatches.length>=6)break;
        }
      }
      addGroup(t('cmdLibrary'),libMatches);

      if(lastRemote.q===q && lastRemote.items.length){
        addGroup(t('cmdCatalog'),lastRemote.items.map(r=>r.media_type==='person' ? ({
          thumb:image(r.profile_path,'w185'),
          symbol:'◎',
          title:r.name,
          sub:r.known_for_department || '',
          kbd:'→',
          run:()=>navigate('/person/'+r.id),
        }) : ({
          thumb:image(r.poster_path,'w185'),
          symbol:'◈',
          title:r.title || r.original_title || 'TMDB #'+r.id,
          sub:[r.release_date?.slice(0,4),r.vote_average?'★ '+Number(r.vote_average).toFixed(1):''].filter(Boolean).join(' · '),
          catalogMovieId:r.id,
          run:()=>openMovie(r.id),
        })));
      }
    }

    const staticCmds=[
      {group:'quick',title:t('cmdShelfView'),sub:t('viewShelf'),kbd:'1',run:()=>{setLibraryView('shelf');if(location.pathname!=='/library')navigate('/library');else render();}},
      {group:'quick',title:t('cmdPosterView'),sub:t('viewPosters'),kbd:'2',run:()=>{setLibraryView('posters');if(location.pathname!=='/library')navigate('/library');else render();}},
      {group:'quick',title:t('cmdEditorialView'),sub:t('viewEditorial'),kbd:'3',run:()=>{setLibraryView('editorial');if(location.pathname!=='/library')navigate('/library');else render();}},
      {group:'quick',title:t('cmdSwitchLang')+' → '+(state.lang==='tr'?'English (EN)':'Türkçe (TR)'),sub:'TR / EN',kbd:state.lang==='tr'?'EN':'TR',run:()=>switchLanguage()},
      {group:'quick',title:t('importExternal'),sub:'.zip / .csv',kbd:'↗',run:()=>openImport()},
      {group:'nav',title:t('library'),sub:'/library',kbd:'G L',run:()=>navigate('/library')},
      {group:'nav',title:t('discover'),sub:'/discover',kbd:'G E',run:()=>navigate('/discover')},
      {group:'nav',title:t('forYou'),sub:'/recommendations',kbd:'G R',run:()=>navigate('/recommendations')},
      {group:'nav',title:t('stats'),sub:'/stats',kbd:'G S',run:()=>navigate('/stats')},
      {group:'nav',title:t('social'),sub:'/social',kbd:'G C',run:()=>navigate('/social')},
      {group:'nav',title:t('favoritePeople'),sub:'/people',kbd:'G P',run:()=>navigate('/people')},
    ].filter(c=>!qFold || foldTitle(c.title).includes(qFold) || foldTitle(c.sub).includes(qFold));

    addGroup(t('cmdQuick'),staticCmds.filter(c=>c.group==='quick'));
    addGroup(t('cmdNav'),staticCmds.filter(c=>c.group==='nav'));
    if(cmdRows.length)setActiveCmd(0);
  }

  function openSpotlight(){
    if(!dialog)return;
    renderPalette();
    if(!dialog.open)dialog.showModal();
    input?.focus();input?.select();
  }

  document.getElementById('open-command')?.addEventListener('click',()=>openSpotlight());
  input?.addEventListener('input',()=>{
    clearTimeout(cmdTimer);
    const q=(input.value || '').trim();
    renderPalette();
    if(q.length<2 || !navigator.onLine)return;
    cmdTimer=setTimeout(async()=>{
      try{
        const res=await api(`catalog/search/multi?query=${encodeURIComponent(q)}&language=${state.lang==='tr'?'tr-TR':'en-US'}&page=1`);
        const items=(res.results || []).filter(x=>(x.media_type==='movie' || x.media_type==='person') && !x.adult && Number.isSafeInteger(x.id)).slice(0,7);
        lastRemote={q,items};
        if(dialog?.open)renderPalette();
      }catch{}
    },220);
  });

  input?.addEventListener('keydown',ev=>{
    if(ev.key==='ArrowDown'){ev.preventDefault();setActiveCmd(cmdIdx+1);}
    else if(ev.key==='ArrowUp'){ev.preventDefault();setActiveCmd(cmdIdx-1);}
    else if(ev.key==='Enter' && cmdRows[cmdIdx]){ev.preventDefault();const fn=cmdRows[cmdIdx].run;dialog.close();fn();}
  });

  document.addEventListener('keydown',ev=>{
    if((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase()==='k'){
      ev.preventDefault();
      if(dialog?.open)dialog.close();
      else openSpotlight();
    }
  },true);

  return {openSpotlight,setAmbientSeed};
}
