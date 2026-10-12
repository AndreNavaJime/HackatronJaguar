export type Observation = {
  observation_id:string; observation_name:string; camera_id:string; study_site:string;
  observer:string; event_datetime_utc:string; camera_latitude:number|null; camera_longitude:number|null;
  altitude_m:number|null;temperature_c:number|null;humidity_percent:number|null;
  species:string;individual_id:string; sex:string;age_class:string;viewpoint:string;
  behavior:string;habitat_notes:string;notes:string;image_url:string;video_url:string;
  validation_status:string; edge_event_id:string; saved_at:string;source:string;
};
export type EdgeEvent={
  event_id:string; camera_id:string; timestamp:string; event:string; contract_version:string;
  latitude:number|null;longitude:number|null;altitude:number|null;
  temperature:number|null;humidity:number|null;class:string;confidence:number|null;
  image_url:string;clip_url:string;transport:string;hmac_status:string;
  source:string;status:string;
};
export type SatelliteItem={id:string;datetime:string;platform:string;orbit_state:string;
  cloud_cover:number|null;sensor:string};
export type SatelliteData={source:string;queried_at:string;bbox:number[];
  sentinel_1:SatelliteItem[];sentinel_2:SatelliteItem[];disclaimer:string};

export const EMPTY_OBSERVATION: Observation = {
  observation_id:'',observation_name:'',camera_id:'',study_site:'',observer:'',
  event_datetime_utc:'',camera_latitude:null,camera_longitude:null,altitude_m:null,
  temperature_c:null,humidity_percent:null,species:'',individual_id:'',
  sex:'unknown',age_class:'unknown',viewpoint:'unknown',behavior:'',habitat_notes:'',
  notes:'',image_url:'',video_url:'',validation_status:'researcher_review_pending',
  edge_event_id:'',saved_at:'',source:'manual_researcher_entry',
};
export function newObservation():Observation{
  const date=new Date().toISOString().slice(0,10).replace(/-/g,'');
  return {...EMPTY_OBSERVATION,
    observation_id:'OBS-'+date+'-'+Math.random().toString(36).slice(2,8).toUpperCase()};
}
export function numberOrNull(input:string):number|null {
  if(input.trim()==='')return null;
  const number=Number(input);
  return Number.isFinite(number)?number:null;
}
export function loadSession<T>(key:string, fallback:T):T {
  try { const raw=sessionStorage.getItem(key);return raw?JSON.parse(raw) as T:fallback; }
  catch {return fallback;}
}
export function saveSession(key:string,value:unknown){
  try {sessionStorage.setItem(key,JSON.stringify(value));}
  catch { /* Protected private browsing: app still works in memory. */ }
}
export function downloadFile(name:string,data:string|Blob,mime='text/plain;charset=utf-8'){
  const blob=typeof data==='string'?new Blob([data],{type:mime}):data;
  const url=URL.createObjectURL(blob);
  const anchor=document.createElement('a');anchor.href=url;anchor.download=name;
  document.body.append(anchor);anchor.click();anchor.remove();
  window.setTimeout(()=>URL.revokeObjectURL(url),2000);
}
function escapeCell(input:unknown):string {
  let value=input===null||input===undefined?'':String(input);
  if(typeof input==='string'&&/^[=+@\-\t\r]/.test(value))value="'"+value;
  return '"'+value.replace(/"/g,'""')+'"';
}
export function toCsv(rows:Record<string,unknown>[]):string{
  if(!rows.length)return '';
  const keys=Object.keys(rows[0]);
  return '\uFEFF'+keys.map(escapeCell).join(',')+'\n'+
    rows.map(row=>keys.map(key=>escapeCell(row[key])).join(',')).join('\n');
}
export function toGeoJSON(records:Observation[]){
  return {type:'FeatureCollection',features:records.map(record=>({
    type:'Feature',
    geometry:record.camera_latitude!==null&&record.camera_longitude!==null
      ?{type:'Point',coordinates:[record.camera_longitude,record.camera_latitude]}:null,
    properties:Object.fromEntries(Object.entries(record).filter(([key])=>
      !['camera_latitude','camera_longitude'].includes(key))),
  }))};
}
export async function apiJson<T>(url:string,method='GET',body?:unknown):Promise<T>{
  const response=await fetch(url,{method,cache:'no-store',
    headers:body===undefined?undefined:{'Content-Type':'application/json'},
    body:body===undefined?undefined:JSON.stringify(body)});
  let parsed:unknown;
  try{parsed=await response.json();}catch{throw new Error('El servidor devolvió una respuesta no JSON.');}
  if(!response.ok){
    let detail='HTTP '+response.status;
    if(typeof parsed==='object'&&parsed!==null&&'detail' in parsed){
      const v=parsed.detail;detail=typeof v==='string'?v:JSON.stringify(v);
    }
    throw new Error(detail);
  }
  return parsed as T;
}
