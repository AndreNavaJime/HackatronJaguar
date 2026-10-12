/** Primary on-device study store.
 * Keeps linked observations and compressed reference imagery together in
 * IndexedDB, independently from the temporary backend and video jobs.
 */
import type {ResearchData} from './researchData';

const NAME='pantheralab_studies_indexeddb_v1';
const STORE='research';
const PRIMARY='current';
let writeQueue:Promise<void>=Promise.resolve();

function openDb():Promise<IDBDatabase>{
  return new Promise((resolve,reject)=>{
    if(typeof indexedDB==='undefined'){reject(new Error('IndexedDB unavailable'));return;}
    const request=indexedDB.open(NAME,1);
    request.onupgradeneeded=()=>{
      if(!request.result.objectStoreNames.contains(STORE))
        request.result.createObjectStore(STORE);
    };
    request.onsuccess=()=>resolve(request.result);
    request.onerror=()=>reject(request.error||new Error('Study storage unavailable'));
  });
}

export async function readStudyData():Promise<ResearchData|null>{
  const db=await openDb();
  return new Promise((resolve,reject)=>{
    const tx=db.transaction(STORE,'readonly');
    let data:ResearchData|null=null;
    const req=tx.objectStore(STORE).get(PRIMARY);
    req.onsuccess=()=>{data=(req.result as ResearchData|undefined)||null;};
    tx.oncomplete=()=>{db.close();resolve(data);};
    tx.onerror=()=>{db.close();reject(tx.error||new Error('Unable to read study'));};
    tx.onabort=()=>{db.close();reject(tx.error||new Error('Study read aborted'));};
  });
}

async function writeData(data:ResearchData):Promise<void>{
  const db=await openDb();
  return new Promise((resolve,reject)=>{
    const tx=db.transaction(STORE,'readwrite');
    tx.objectStore(STORE).put(data,PRIMARY);
    tx.oncomplete=()=>{db.close();resolve();};
    tx.onerror=()=>{db.close();reject(tx.error||new Error('Unable to save study'));};
    tx.onabort=()=>{db.close();reject(tx.error||new Error('Study save aborted'));};
  });
}
export function saveStudyData(data:ResearchData):Promise<void>{
  // Preserve write order if several research records are saved in quick succession.
  writeQueue=writeQueue.catch(()=>undefined).then(()=>writeData(data));
  return writeQueue;
}
