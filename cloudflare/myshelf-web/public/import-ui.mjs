// Modal UI for browser-side Letterboxd (ZIP/CSV) and IMDb (CSV) import.
import {MAX_UPLOAD_BYTES,parseExternalFile,importExternalItems} from './external-import.mjs';

export function createImportUI({state,store,api,t,e,queueSync,render,toast,navigate}){
  let source='auto',selectedFile=null,running=false,lastSummary=null,lastError='';

  const dialog=()=>document.querySelector('#external-import-dialog');
  const content=()=>document.querySelector('#external-import-content');

  function formatImportError(error){
    const key=error?.message;
    if(key && t(key)!==key)return t(key);
    return t('import_generic');
  }

  function draw(){
    const box=content();
    if(!box)return;
    const sources=[
      ['auto',t('importSourceAuto')],
      ['letterboxd',t('importSourceLetterboxd')],
      ['imdb',t('importSourceImdb')],
    ];
    const fileLabel=selectedFile ? `${selectedFile.name} (${Math.max(1,Math.round(selectedFile.size/1024))} KB)` : t('importDropHint');
    box.innerHTML=
      `<div class="auth-body import-body">`+
        `<h1 id="external-import-title">${t('importExternalTitle')}</h1>`+
        `<p>${t('importExternalP')}</p>`+
        `<div class="tabs import-sources" role="radiogroup" aria-label="${e(t('importExternalTitle'))}">${sources.map(([id,label])=>`<button type="button" class="tab ${source===id?'selected':''}" data-import-source="${id}" aria-pressed="${source===id}" ${running?'disabled':''}>${e(label)}</button>`).join('')}</div>`+
        `<label class="import-dropzone ${selectedFile?'has-file':''}" id="external-import-drop">`+
          `<input type="file" id="external-import-file" accept=".zip,.csv,application/zip,text/csv" hidden ${running?'disabled':''}>`+
          `<strong>${e(selectedFile ? t('importChangeFile') : t('importChooseFile'))}</strong>`+
          `<span>${e(fileLabel)}</span>`+
        `</label>`+
        `<p class="form-hint">${t('importExternalHint')}</p>`+
        `<div id="external-import-progress" class="import-progress" hidden>`+
          `<div class="import-progress-meta"><span id="external-import-stage"></span><span id="external-import-counter"></span></div>`+
          `<progress id="external-import-bar" max="100" value="0"></progress>`+
        `</div>`+
        `<div class="form-error" id="external-import-error" role="alert">${e(lastError)}</div>`+
        (lastSummary ?
          `<div class="import-summary">`+
            `<strong>${t('importDoneTitle')}</strong>`+
            `<div class="import-summary-grid">`+
              `<div><span>${t('importStatImported')}</span><strong>${lastSummary.imported}</strong></div>`+
              `<div><span>${t('importStatMatched')}</span><strong>${lastSummary.matchedTmdb}</strong></div>`+
              `<div><span>${t('importStatCustom')}</span><strong>${lastSummary.addedCustom}</strong></div>`+
              `<div><span>${t('importStatSkipped')}</span><strong>${lastSummary.skippedExisting}</strong></div>`+
              (lastSummary.skippedNonFilms ? `<div><span>${t('importStatNonFilms')}</span><strong>${lastSummary.skippedNonFilms}</strong></div>` : '')+
            `</div>`+
            (lastSummary.catalogOffline ? `<p class="form-hint">${t('importOfflineNote')}</p>` : '')+
            `<div class="actions"><button type="button" class="button small" data-import-open-library>${t('openLibrary')} →</button></div>`+
          `</div>` : '')+
        `<div class="actions import-actions"><button type="button" class="button full" id="external-import-run" ${!selectedFile || running ? 'disabled' : ''}>${running ? t('importRunning') : t('importStart')+' →'}</button></div>`+
      `</div>`;
  }

  function open(){
    if(!running){selectedFile=null;lastSummary=null;lastError='';}
    draw();
    const d=dialog();
    if(d && !d.open)d.showModal();
  }

  async function runImport(){
    if(running || !selectedFile)return;
    const owner=state.owner,lang=state.lang;
    lastError='';lastSummary=null;
    if(selectedFile.size>MAX_UPLOAD_BYTES){lastError=t('import_too_large');draw();return;}
    running=true;draw();
    const prog=document.querySelector('#external-import-progress');
    const stage=document.querySelector('#external-import-stage');
    const counter=document.querySelector('#external-import-counter');
    const bar=document.querySelector('#external-import-bar');
    if(prog)prog.hidden=false;
    if(stage)stage.textContent=t('importReading');
    try{
      const buffer=await selectedFile.arrayBuffer();
      const parsed=await parseExternalFile(buffer,selectedFile.name,source);
      if(!parsed.items.length)throw Object.assign(Error('import_empty_items'),{code:'empty_items'});
      if(bar){bar.max=parsed.items.length;bar.value=0;}
      const searchCatalog=async query=>{
        const path=`catalog/search/movie?query=${encodeURIComponent(query)}&language=${lang==='tr'?'tr-TR':'en-US'}&page=1`;
        return api(path,undefined,owner);
      };
      const result=await importExternalItems(parsed,{
        owner,store,searchCatalog,lang,concurrency:3,
        onProgress:({done,total,currentTitle})=>{
          if(bar){bar.max=total;bar.value=done;}
          if(stage)stage.textContent=currentTitle ? `${t('importMatching')} · ${currentTitle}` : t('importMatching');
          if(counter)counter.textContent=`${done} / ${total}`;
        },
      });
      lastSummary=result;
      selectedFile=null;
      queueSync();
      await render();
      toast(t('imported'));
    }catch(error){
      lastError=formatImportError(error);
    }finally{
      running=false;
      draw();
    }
  }

  function handleClick(button){
    if(button.dataset.action==='external-import'){open();return true;}
    if(button.dataset.importSource && !running){source=button.dataset.importSource;lastError='';draw();return true;}
    if(button.id==='external-import-run'){runImport();return true;}
    if(button.dataset.importOpenLibrary!==undefined){dialog()?.close();navigate('/library');return true;}
    return false;
  }

  function handleChange(target){
    if(target.id!=='external-import-file')return false;
    const file=target.files?.[0];
    if(file){selectedFile=file;lastError='';lastSummary=null;draw();}
    return true;
  }

  function bindDragDrop(){
    document.addEventListener('dragover',event=>{
      const zone=event.target.closest?.('#external-import-drop');
      if(!zone || running)return;
      event.preventDefault();
      zone.classList.add('drag-over');
    });
    document.addEventListener('dragleave',event=>{
      const zone=event.target.closest?.('#external-import-drop');
      if(zone)zone.classList.remove('drag-over');
    });
    document.addEventListener('drop',event=>{
      const zone=event.target.closest?.('#external-import-drop');
      if(!zone || running)return;
      event.preventDefault();
      zone.classList.remove('drag-over');
      const file=event.dataTransfer?.files?.[0];
      if(file){selectedFile=file;lastError='';lastSummary=null;draw();}
    });
  }

  bindDragDrop();
  return {open,handleClick,handleChange};
}
