import type {Observation} from './scienceShared';

export type Study={study_id:string;title:string;organization:string;lead:string;objectives:string;
  methodology:string;start_date:string;end_date:string;created_at:string};
export type Deployment={deployment_id:string;study_id:string;camera_id:string;site:string;
  latitude:number|null;longitude:number|null;altitude_m:number|null;
  deployed_at:string;retrieved_at:string;operational_days:number|null;notes:string};
export type Individual={individual_id:string;study_id:string;species:string;sex:string;
  age_class:string;marks:string;status:'provisional'|'verified';validated_by:string;
  reference_image_url:string;notes:string};
export type Encounter={encounter_id:string;study_id:string;deployment_id:string;
  occurred_at:string;observer:string;temperature_c:number|null;humidity_percent:number|null;
  environment_source:'unprovided'|'sensor'|'manual'|'external';
  image_url:string;video_url:string;edge_event_id:string;notes:string};
export type Sighting={sighting_id:string;encounter_id:string;species:string;individual_id:string;
  identification_status:'unidentified'|'tentative'|'verified';
  sex:string;age_class:string;viewpoint:string;behavior:string;reviewer:string;notes:string};
export type ResearchData={version:1;studies:Study[];deployments:Deployment[];
  individuals:Individual[];encounters:Encounter[];sightings:Sighting[]};
export const STORE_KEY='pantheralab_research_v1';
export const emptyResearch=():ResearchData=>({
  version:1,studies:[],deployments:[],individuals:[],encounters:[],sightings:[],
});
export const uid=(prefix:string)=>prefix+'-'+(typeof crypto!=='undefined'&&'randomUUID' in crypto
  ?crypto.randomUUID().slice(0,10).toUpperCase()
  :Date.now().toString(36).toUpperCase()+Math.random().toString(36).slice(2,5).toUpperCase());
const limit=(v:unknown,n=250)=>String(v??'').slice(0,n);
const finite=(v:unknown,min:number,max:number):number|null=>{
  const num=Number(v);return v===null||v===undefined||v===''||!Number.isFinite(num)||num<min||num>max
    ?null:num;
};
export function migrateOldRecords(old:Observation[]):ResearchData{
  const data=emptyResearch();if(!old.length)return data;
  const projectId=uid('STUDY');
  data.studies.push({study_id:projectId,title:'Observaciones importadas',
    organization:'',lead:'',objectives:'',methodology:'Registros importados del formulario anterior.',
    start_date:'',end_date:'',created_at:new Date().toISOString()});
  const cameras=new Map<string,string>();
  const named=new Map<string,string>();
  for(const row of old.slice(0,250)){
    const key=limit(row.camera_id)+'|'+limit(row.study_site);
    let depId=cameras.get(key);
    if(!depId){
      depId=uid('DEP');cameras.set(key,depId);
      data.deployments.push({deployment_id:depId,study_id:projectId,
        camera_id:limit(row.camera_id)||'Sin cámara',
        site:limit(row.study_site),latitude:finite(row.camera_latitude,-90,90),
        longitude:finite(row.camera_longitude,-180,180),
        altitude_m:finite(row.altitude_m,-500,9000),
        deployed_at:'',retrieved_at:'',operational_days:null,
        notes:'Importado. Verificar datos de estación y fechas.'});
    }
    const encId=uid('EVT');
    data.encounters.push({encounter_id:encId,study_id:projectId,deployment_id:depId,
      occurred_at:limit(row.event_datetime_utc,80),observer:limit(row.observer),
      temperature_c:finite(row.temperature_c,-80,85),
      humidity_percent:finite(row.humidity_percent,0,100),
      environment_source:row.temperature_c!==null||row.humidity_percent!==null?'manual':'unprovided',
      image_url:limit(row.image_url,1024),video_url:limit(row.video_url,1024),
      edge_event_id:limit(row.edge_event_id),notes:limit(row.notes,1800)});
    let individualId='';
    if(row.individual_id&&row.individual_id.trim()){
      const external=limit(row.individual_id.trim(),90);
      if(named.has(external))individualId=named.get(external)!;
      else {
        individualId=uid('JAG');named.set(external,individualId);
        data.individuals.push({individual_id:individualId,study_id:projectId,
          species:limit(row.species)||'Panthera onca',sex:limit(row.sex)||'unknown',
          age_class:limit(row.age_class)||'unknown',marks:'',status:'provisional',
          validated_by:'',reference_image_url:'',notes:'ID anterior: '+external+
            '. Relación importada; identidad pendiente de revisión.'});
      }
    }
    data.sightings.push({sighting_id:uid('OBS'),encounter_id:encId,
      species:limit(row.species),individual_id:individualId,
      identification_status:individualId?'tentative':'unidentified',
      sex:limit(row.sex)||'unknown',age_class:limit(row.age_class)||'unknown',
      viewpoint:limit(row.viewpoint)||'unknown',behavior:limit(row.behavior),
      reviewer:limit(row.observer),notes:limit(row.habitat_notes,800)});
  }
  return data;
}
function isData(v:unknown):v is ResearchData {
  if(!v||typeof v!=='object')return false;
  const p=v as Record<string,unknown>;
  return p.version===1&&['studies','deployments','individuals','encounters','sightings']
    .every(k=>Array.isArray(p[k]));
}
export function loadResearch():ResearchData{
  try{
    const json=localStorage.getItem(STORE_KEY);
    if(json){const v:unknown=JSON.parse(json);if(isData(v))return v;}
  }catch{/* Storage restricted: fall back to local state. */}
  try{
    const legacy=sessionStorage.getItem('pantheralab_session_observations_v1');
    if(legacy){
      const old:unknown=JSON.parse(legacy);
      if(Array.isArray(old)&&old.length){
        const migrated=migrateOldRecords(old as Observation[]);
        try{localStorage.setItem(STORE_KEY,JSON.stringify(migrated));}catch{/* memory fallback */}
        return migrated;
      }
    }
  }catch{/* no legacy data */}
  return emptyResearch();
}
export function persistResearch(data:ResearchData):boolean{
  try{localStorage.setItem(STORE_KEY,JSON.stringify(data));return true;}
  catch{return false;}
}
export function flattenObservations(data:ResearchData):Observation[]{
  const deps=new Map(data.deployments.map(d=>[d.deployment_id,d]));
  const events=new Map(data.encounters.map(e=>[e.encounter_id,e]));
  const studies=new Map(data.studies.map(p=>[p.study_id,p]));
  return data.sightings.flatMap(s=>{
    const e=events.get(s.encounter_id);if(!e)return [];
    const dep=deps.get(e.deployment_id);if(!dep)return [];
    const p=studies.get(e.study_id);
    return [{
      observation_id:s.sighting_id,observation_name:p?.title||'',camera_id:dep.camera_id,
      study_site:dep.site,observer:e.observer,event_datetime_utc:e.occurred_at,
      camera_latitude:dep.latitude,camera_longitude:dep.longitude,altitude_m:dep.altitude_m,
      temperature_c:e.temperature_c,humidity_percent:e.humidity_percent,
      species:s.species,individual_id:s.individual_id,sex:s.sex,age_class:s.age_class,
      viewpoint:s.viewpoint,behavior:s.behavior,habitat_notes:s.notes,notes:e.notes,
      image_url:e.image_url,video_url:e.video_url,validation_status:s.identification_status,
      edge_event_id:e.edge_event_id,saved_at:'',source:'field_research_registry',
    } as Observation];
  });
}
export function projectPackage(data:ResearchData,study_id:string,redact:boolean,language:'es'|'en'){
  const studies=data.studies.find(p=>p.study_id===study_id);
  if(!studies)throw new Error('Study not found');
  const deployments=data.deployments.filter(x=>x.study_id===study_id);
  const individuals=data.individuals.filter(x=>x.study_id===study_id);
  const encounters=data.encounters.filter(x=>x.study_id===study_id);
  const encounterIds=new Set(encounters.map(e=>e.encounter_id));
  const sightings=data.sightings.filter(s=>encounterIds.has(s.encounter_id));
  return {study:studies,deployments,individuals,encounters,sightings,
    redact_coordinates:redact,language};
}
