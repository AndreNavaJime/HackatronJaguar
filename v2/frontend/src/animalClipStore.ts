/** Local-only provisional animal video evidence. Nothing is sent to the PantheraLAB API.
 * Kept videos in IndexedDB can be evicted by the browser: export important files.
 */
export type AnimalClip={
  id:string;
  capturedAt:string;
  studyId:string;
  animalClass:string;
  confidence:number;
  model:string;
  state:'pending'|'kept';
  mimeType:string;
  video:Blob;
  /** Video source and measurements are recorded locally for EDGE / 5G comparisons. */
  sourceMode?:'device'|'remote';
  cameraId?:string;
  durationMs?:number;
};
const DB_NAME='pantheralab_live_review_clips_v1';
const STORE='clips';
export const MAX_CLIPS=20;
export const LIVE_CLIPS_CHANGED='pantheralive:clips-changed';
function clipsChanged(){window.dispatchEvent(new Event(LIVE_CLIPS_CHANGED));}
export const MAX_CLIP_BYTES=25*1024*1024;
function database():Promise<IDBDatabase>{
  return new Promise((resolve,reject)=>{
    if(!('indexedDB' in window))return reject(new Error('Este navegador no permite guardar videos localmente.'));
    const req=indexedDB.open(DB_NAME,1);
    req.onupgradeneeded=()=>{
      if(!req.result.objectStoreNames.contains(STORE))
        req.result.createObjectStore(STORE,{keyPath:'id'});
    };
    req.onsuccess=()=>resolve(req.result);
    req.onerror=()=>reject(req.error||new Error('No se puede abrir la biblioteca local.'));
    req.onblocked=()=>reject(new Error('Cerrá las otras pestañas de PantheraLAB e intentá nuevamente.'));
  });
}
async function transact<T>(mode:IDBTransactionMode,task:(store:IDBObjectStore,resolve:(result:T)=>void,reject:(error:unknown)=>void)=>void):Promise<T>{
  const db=await database();
  return new Promise<T>((resolve,reject)=>{
    let result:T,done=false;
    const tx=db.transaction(STORE,mode);
    tx.oncomplete=()=>{db.close();if(done)resolve(result);};
    tx.onerror=()=>{db.close();reject(tx.error||new Error('Error del almacenamiento local.'));};
    tx.onabort=()=>{db.close();reject(tx.error||new Error('Almacenamiento interrumpido.'));};
    task(tx.objectStore(STORE),value=>{result=value;done=true;},reject);
  });
}
export function countPendingAnimalClips():Promise<number>{
  // Iterate only stored status; no video should be read into a React sidebar.
  return transact('readonly',(store,ok,fail)=>{
    let pending=0;
    const cursor=store.openCursor();
    cursor.onsuccess=()=>{
      const current=cursor.result;
      if(!current){ok(pending);return;}
      if((current.value as AnimalClip).state==='pending')pending++;
      current.continue();
    };
    cursor.onerror=()=>fail(cursor.error);
  });
}
export function listAnimalClips():Promise<AnimalClip[]>{
  return transact('readonly',(store,ok,fail)=>{
    const req=store.getAll();
    req.onsuccess=()=>ok((req.result as AnimalClip[]).sort((a,b)=>b.capturedAt.localeCompare(a.capturedAt)));
    req.onerror=()=>fail(req.error);
  });
}
export async function addAnimalClip(clip:AnimalClip):Promise<void>{
  if(clip.video.size<1024||clip.video.size>MAX_CLIP_BYTES)
    throw new Error('Video vacío o demasiado grande (máximo 25 MB).');
  const existing=await listAnimalClips();
  if(existing.length>=MAX_CLIPS)throw new Error('La bandeja local alcanzó 20 videos; conservá o descartá algunos.');
  await transact('readwrite', (store,ok,fail)=>{
    const req=store.add(clip);req.onsuccess=()=>ok(undefined);req.onerror=()=>fail(req.error);
  });
  clipsChanged();
}
export async function setAnimalClipState(id:string,state:'kept'):Promise<void>{
  await transact('readwrite',(store,ok,fail)=>{
    const get=store.get(id);
    get.onsuccess=()=>{
      const value=get.result as AnimalClip|undefined;
      if(!value)return fail(new Error('El video ya no está disponible.'));
      value.state=state;
      const put=store.put(value);put.onsuccess=()=>ok(undefined);put.onerror=()=>fail(put.error);
    };
    get.onerror=()=>fail(get.error);
  });
  clipsChanged();
}
export async function deleteAnimalClip(id:string):Promise<void>{
  await transact('readwrite',(store,ok,fail)=>{
    const req=store.delete(id);req.onsuccess=()=>ok(undefined);req.onerror=()=>fail(req.error);
  });
  clipsChanged();
}
export function localStudyId():string{
  try{return localStorage.getItem('pantheralab_selected_study_v1')||'';}catch{return '';}
}
