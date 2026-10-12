/** Browser-local, recoverable PantheraID analysis history.
 * IndexedDB is used rather than localStorage to avoid storing frame JPEGs in
 * the small synchronous Web Storage quota. No cloud synchronization occurs.
 * Original videos are NOT archived. Users must preserve source media separately.
 */
export type VideoFrameEvidence={
  sample:number;time_seconds:number;retained:boolean;motion_score:number;image:string
};
export type VideoResult={
  metadata:{mode:string;model:string;filename:string;duration_seconds:number;
    source_width:number;source_height:number;sample_seconds:number;threshold:number};
  totals:{sampled:number;retained:number;discarded:number;mean_motion:number;
    positive_frame_rate:number;estimated_payload_reduction:number};
  frames:VideoFrameEvidence[];
  rows:{sample:number;video_time_seconds:number;motion_score:number;edge_decision:string}[];
  note:string;
};
export type VideoSession={
  id:string;jobId:string;filename:string;createdAt:string;updatedAt:string;
  stage:'processing'|'completed'|'failed';
  motionThreshold:number;sampleSeconds:number;maxSamples:number;
  selectedSamples:number[];result:VideoResult|null;error?:string;
};
export type VideoEvidenceBatch={
  analysisId:string;jobId:string;fileName:string;sampleSeconds:number;
  motionThreshold:number;totalSamples:number;durationSeconds:number;
  frames:{sample:number;timeSeconds:number;motionScore:number;frameDataUrl:string}[];
};
const DB_NAME='pantheralab_media_sessions_v1';
const STORE_NAME='analyses';
const ACTIVE_KEY='pantheralab_active_video_v1';

function open():Promise<IDBDatabase>{
  return new Promise((resolve,reject)=>{
    if(!('indexedDB' in window)){reject(new Error('IndexedDB unavailable'));return;}
    const request=indexedDB.open(DB_NAME,1);
    request.onupgradeneeded=()=>{
      const db=request.result;
      if(!db.objectStoreNames.contains(STORE_NAME)){
        const store=db.createObjectStore(STORE_NAME,{keyPath:'id'});
        store.createIndex('updatedAt','updatedAt',{unique:false});
      }
    };
    request.onsuccess=()=>resolve(request.result);
    request.onerror=()=>reject(request.error||new Error('No se pudo abrir IndexedDB'));
  });
}
async function transaction<T>(mode:IDBTransactionMode,action:(store:IDBObjectStore)=>IDBRequest<T>):Promise<T>{
  const db=await open();
  return new Promise<T>((resolve,reject)=>{
    const tx=db.transaction(STORE_NAME,mode);
    const req=action(tx.objectStore(STORE_NAME));
    let value:T;
    req.onsuccess=()=>{value=req.result;};
    req.onerror=()=>{/* The transaction failure reports the underlying error. */};
    tx.oncomplete=()=>{db.close();resolve(value);};
    tx.onerror=()=>{db.close();reject(tx.error||new Error('Fallo de almacenamiento local'));};
    tx.onabort=()=>{db.close();reject(tx.error||new Error('Almacenamiento local interrumpido'));};
  });
}
export async function saveVideoSession(value:VideoSession):Promise<void>{
  await transaction('readwrite',store=>store.put(value));
}
export async function getVideoSession(id:string):Promise<VideoSession|undefined>{
  if(!id)return undefined;
  return transaction('readonly',store=>store.get(id)) as Promise<VideoSession|undefined>;
}
export async function listVideoSessions():Promise<VideoSession[]>{
  const values=await transaction('readonly',store=>store.getAll()) as VideoSession[];
  return values.sort((a,b)=>b.updatedAt.localeCompare(a.updatedAt));
}
export async function deleteVideoSession(id:string):Promise<void>{
  await transaction('readwrite',store=>store.delete(id));
  if(getActiveVideoId()===id)setActiveVideoId('');
}
export function getActiveVideoId():string{
  try{return localStorage.getItem(ACTIVE_KEY)||'';}catch{return '';}
}
export function setActiveVideoId(id:string):void{
  try{if(id)localStorage.setItem(ACTIVE_KEY,id);else localStorage.removeItem(ACTIVE_KEY);}
  catch{/* Private browsing may block localStorage. */}
}
export function createAnalysisId():string{
  return 'ANL-'+(typeof crypto!=='undefined'&&'randomUUID' in crypto?
    crypto.randomUUID().slice(0,13).toUpperCase():
    Date.now().toString(36).toUpperCase()+Math.random().toString(36).slice(2,7).toUpperCase());
}
export function selectionBatch(value:VideoSession):VideoEvidenceBatch{
  if(!value.result)throw new Error('Análisis incompleto');
  const wanted=new Set(value.selectedSamples);
  const frames=value.result.frames.filter(f=>wanted.has(f.sample)).slice(0,6).map(f=>({
    sample:f.sample,timeSeconds:f.time_seconds,motionScore:f.motion_score,frameDataUrl:f.image,
  }));
  return {analysisId:value.id,jobId:value.jobId,fileName:value.filename,
    sampleSeconds:value.sampleSeconds,motionThreshold:value.motionThreshold,
    totalSamples:value.result.totals.sampled,
    durationSeconds:value.result.metadata.duration_seconds,frames};
}
