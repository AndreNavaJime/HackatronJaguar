import React from 'react';
import {useLanguage} from './language';
import {downloadFile} from './scienceShared';
import {ResearchData,Study,Deployment,Individual,Encounter,Sighting,uid,projectPackage} from './researchData';
import type {VideoEvidenceBatch} from './videoWorkspaceDb';

type Tab='projects'|'stations'|'captures'|'individuals'|'reports';
type Props={data:ResearchData;setData:React.Dispatch<React.SetStateAction<ResearchData>>;
  pendingEdge?:{camera_id:string;timestamp:string;event_id:string;latitude:number|null;
    longitude:number|null;temperature:number|null;humidity:number|null;image_url:string;
    clip_url:string;hmac_status?:string;source?:string}|null;onClearEdge?:()=>void;
  pendingEvidence?:VideoEvidenceBatch|null;onClearEvidence?:()=>void;
  reportRequested?:boolean;onClearReportRequest?:()=>void;
  onNavigate?:(section:string)=>void};
const localTime=()=>new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,16);
async function makeEvidencePreview(file:File):Promise<string>{
  if(!file.type.startsWith('image/')||file.size>8*1024*1024){
    throw new Error('Seleccioná una fotografía JPG, PNG o WebP de hasta 8 MB.');
  }
  return new Promise((resolve,reject)=>{
    const url=URL.createObjectURL(file);
    const img=new window.Image();
    img.onerror=()=>{URL.revokeObjectURL(url);reject(new Error('No se pudo abrir la fotografía.'));};
    img.onload=()=>{
      URL.revokeObjectURL(url);
      try{
        const scale=Math.min(1,480/Math.max(img.naturalWidth,img.naturalHeight));
        const canvas=document.createElement('canvas');
        canvas.width=Math.max(1,Math.round(img.naturalWidth*scale));
        canvas.height=Math.max(1,Math.round(img.naturalHeight*scale));
        const context=canvas.getContext('2d');
        if(!context)throw new Error('Imagen no compatible.');
        context.drawImage(img,0,0,canvas.width,canvas.height);
        let result='';
        for(const quality of [.7,.55,.42,.30]){
          result=canvas.toDataURL('image/jpeg',quality);
          if(result.length<=72000)break;
        }
        if(result.length>72000)throw new Error('Imagen demasiado compleja para guardar como miniatura.');
        resolve(result);
      }catch(error){reject(error);}
    };
    img.src=url;
  });
}
const inputTime=(iso:string)=>{
  if(!iso)return '';
  const date=new Date(iso);
  return Number.isFinite(date.getTime())
    ?new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16)
    :'';
};
const nval=(v:string,min=-Infinity,max=Infinity):number|null=>{
  if(!v.trim())return null;const n=Number(v);return Number.isFinite(n)&&n>=min&&n<=max?n:null;
};
const selectValues=(tx:(es:string,en:string)=>string)=>({
  sex:[['unknown',tx('Desconocido','Unknown')],['female',tx('Hembra','Female')],['male',tx('Macho','Male')]],
  age:[['unknown',tx('Desconocida','Unknown')],['juvenile',tx('Juvenil','Juvenile')],
    ['subadult',tx('Subadulto','Subadult')],['adult',tx('Adulto','Adult')]],
});
const initialStudy=():Study=>({study_id:uid('STUDY'),title:'',organization:'',lead:'',
  objectives:'',methodology:'',start_date:'',end_date:'',created_at:new Date().toISOString()});
const initialStation=(study_id:string):Deployment=>({
  deployment_id:uid('DEP'),study_id,camera_id:'',site:'',latitude:null,
  longitude:null,altitude_m:null,deployed_at:'',retrieved_at:'',operational_days:null,notes:''});
const initialIndividual=(study_id:string):Individual=>({
  individual_id:uid('JAG'),study_id,species:'Panthera onca',sex:'unknown',age_class:'unknown',
  marks:'',status:'provisional',validated_by:'',reference_image_url:'',notes:''});
const initialEvent=(study_id:string,deployment_id:string):Encounter=>({
  encounter_id:uid('EVT'),study_id,deployment_id,occurred_at:'',observer:'',
  temperature_c:null,humidity_percent:null,environment_source:'unprovided',
  image_url:'',video_url:'',edge_event_id:'',notes:''});
const initialSighting=(encounter_id:string):Sighting=>({
  sighting_id:uid('OBS'),encounter_id,species:'Panthera onca',individual_id:'',
  identification_status:'unidentified',sex:'unknown',age_class:'unknown',viewpoint:'unknown',
  behavior:'',reviewer:'',notes:''});

export default function ResearchRegistry({data,setData,pendingEdge,onClearEdge,pendingEvidence,onClearEvidence,
  reportRequested,onClearReportRequest,onNavigate}:Props){
  const {language}=useLanguage();const tx=(es:string,en:string)=>language==='en'?en:es;
  const [tab,setTab]=React.useState<Tab>('projects');
  React.useEffect(()=>{
    if(reportRequested){setTab('reports');onClearReportRequest?.();}
  },[reportRequested]);
  const [selectedStudy,setSelectedStudy]=React.useState('');
  const activeId=data.studies.some(s=>s.study_id===selectedStudy)?selectedStudy:data.studies[0]?.study_id||'';
  const study=data.studies.find(s=>s.study_id===activeId);
  const stations=data.deployments.filter(d=>d.study_id===activeId);
  const people=data.individuals.filter(i=>i.study_id===activeId);
  const encounters=data.encounters.filter(e=>e.study_id===activeId);
  const eventIds=new Set(encounters.map(e=>e.encounter_id));
  const sightings=data.sightings.filter(s=>eventIds.has(s.encounter_id));
  const [studyDraft,setStudyDraft]=React.useState<Study>(initialStudy);
  const [stationDraft,setStationDraft]=React.useState<Deployment>(()=>initialStation(''));
  const [individualDraft,setIndividualDraft]=React.useState<Individual>(()=>initialIndividual(''));
  const [eventDraft,setEventDraft]=React.useState<Encounter>(()=>initialEvent('',''));
  const [sightingDraft,setSightingDraft]=React.useState<Sighting>(()=>initialSighting(''));
  const [selectedEvent,setSelectedEvent]=React.useState('');
  const [notice,setNotice]=React.useState('');
  const [pdfBusy,setPdfBusy]=React.useState(false);
  const [mapDeployment,setMapDeployment]=React.useState('');
  const [includePrecise,setIncludePrecise]=React.useState(false);
  const [filterStatus,setFilterStatus]=React.useState<'all'|'verified'>('all');
  const [startDate,setStartDate]=React.useState('');
  const [endDate,setEndDate]=React.useState('');
  const fileRef=React.useRef<HTMLInputElement|null>(null);
  const opts=selectValues(tx);

  React.useEffect(()=>{
    setStationDraft(initialStation(activeId));setIndividualDraft(initialIndividual(activeId));
    setEventDraft(initialEvent(activeId,''));setSightingDraft(initialSighting(''));
    setSelectedEvent('');setNotice('');
  },[activeId]);
  React.useEffect(()=>{
    if(!pendingEvidence)return;
    if(!activeId){
      setTab('projects');
      setNotice(tx('Creá o seleccioná un estudio para asociar los fotogramas del análisis.',
        'Create or choose a study to link the selected analysis frames.'));
      return;
    }
    if(!stations.length){
      setTab('stations');
      setNotice(tx('Registrá una estación antes de asociar el video. La selección se conserva.',
        'Register a camera deployment before linking the video. Your selection is retained.'));
      return;
    }
    let canceled=false;
    void (async()=>{
      try{
        if(!pendingEvidence.frames.length||pendingEvidence.frames.length>6)
          throw new Error(tx('Seleccioná entre uno y seis fotogramas.','Select between one and six frames.'));
        const prepared:{sample:number;time_seconds:number;motion_score:number;data_url:string}[]=[];
        for(const frame of pendingEvidence.frames){
          if(!frame.frameDataUrl.startsWith('data:image/jpeg;base64,')||
             frame.frameDataUrl.length>2500000)throw new Error('Invalid frame image format');
          const imageBlob=await (await fetch(frame.frameDataUrl)).blob();
          const thumb=await makeEvidencePreview(new File([imageBlob],
            'frame_'+frame.sample+'.jpg',{type:'image/jpeg'}));
          prepared.push({sample:frame.sample,time_seconds:frame.timeSeconds,
            motion_score:frame.motionScore,data_url:thumb});
        }
        if(canceled)return;
        const previous=encounters.find(e=>e.source_analysis_id===pendingEvidence.analysisId);
        const draft=previous?{...previous}:initialEvent(activeId,stations[0].deployment_id);
        const first=prepared[0];
        setTab('captures');setSelectedEvent(previous?.encounter_id||'');
        setEventDraft({...draft,thumbnail_data_url:first.data_url,
          thumbnail_filename:'pantheraid_frame_'+first.sample+'.jpg',
          evidence_frames:prepared.slice(1),
          source_analysis_id:pendingEvidence.analysisId,
          source_job_id:pendingEvidence.jobId,
          source_video_name:pendingEvidence.fileName.slice(0,150),
          analysis_method:'OpenCV visual-change screening (no animal identification)',
          analysis_sample_seconds:pendingEvidence.sampleSeconds,
          analysis_threshold:pendingEvidence.motionThreshold,
          analysis_samples:pendingEvidence.totalSamples,
          video_duration_seconds:pendingEvidence.durationSeconds,
          notes:previous?.notes||('PantheraID | '+pendingEvidence.fileName.slice(0,140)+
            ' | segundos del video: '+prepared.map(v=>v.time_seconds.toFixed(2)).join(', ')+
            ' | fotogramas: '+prepared.map(v=>v.sample).join(', ')+
            '. Fecha original e identificación de fauna requieren revisión humana.')});
        setNotice(tx('Se prepararon '+prepared.length+' fotogramas en una sola captura. Revisá estación y fecha; después guardá el evento.',
          prepared.length+' frames prepared under one capture. Check camera and date, then save the event.'));
        onClearEvidence?.();
      }catch(error){
        if(!canceled)setNotice(error instanceof Error?error.message:String(error));
      }
    })();
    return ()=>{canceled=true;};
  },[pendingEvidence,activeId,stations.length]);
  const setStudy=(key:keyof Study,v:string)=>setStudyDraft(p=>({...p,[key]:v}));
  const setStation=(key:keyof Deployment,v:string|number|null)=>setStationDraft(p=>({...p,[key]:v}));
  const setPerson=(key:keyof Individual,v:string)=>setIndividualDraft(p=>({...p,[key]:v}));
  const setEvent=(key:keyof Encounter,v:string|number|null)=>setEventDraft(p=>({...p,[key]:v}));
  const setSighting=(key:keyof Sighting,v:string)=>setSightingDraft(p=>({...p,[key]:v}));

  // Pre-fill an encounter from an explicitly selected PantheraEDGE event; nothing is auto-validated.
  React.useEffect(()=>{
    if(!pendingEdge||!activeId)return;
    const station=stations.find(s=>s.camera_id===pendingEdge.camera_id);
    if(!station){
      setTab('stations');
      setNotice(tx('Registrá primero el despliegue de la cámara '+pendingEdge.camera_id+
        ' para vincular el evento de campo.', 'Register camera deployment '+pendingEdge.camera_id+
        ' before linking its field event.'));
      return;
    }
    setTab('captures');setSelectedEvent('');
    setEventDraft({...initialEvent(activeId,station.deployment_id),
      occurred_at:pendingEdge.timestamp,edge_event_id:pendingEdge.event_id,
      temperature_c:pendingEdge.temperature,humidity_percent:pendingEdge.humidity,
      environment_source:pendingEdge.temperature===null&&pendingEdge.humidity===null?'unprovided':
        pendingEdge.hmac_status==='VALID'?'sensor':'manual',
      image_url:pendingEdge.image_url||'',video_url:pendingEdge.clip_url||'',
      notes:pendingEdge.hmac_status==='VALID'?'Origen EDGE con firma HMAC válida.':
        'Datos EDGE no autenticados; confirmar procedencia antes de usarlos científicamente.'});
    setNotice(tx('Evento EDGE preparado para revisión. Guardalo para incorporarlo al estudio.',
      'EDGE event prepared for review. Save it to add it to this study.'));
    onClearEdge?.();
  },[pendingEdge,activeId,stations.length]);

  function textField(label:string,value:string,change:(value:string)=>void,placeholder='',type='text'){
    return <label className="sci-field"><span>{label}</span>
      <input type={type} maxLength={type==='text'?300:undefined} value={value} placeholder={placeholder}
        onChange={e=>change(e.target.value)}/></label>;
  }
  function decimalField(label:string,value:number|null,change:(value:number|null)=>void,
    min=-100000,max=100000,step='any'){
    return <label className="sci-field"><span>{label}</span>
      <input type="number" min={min} max={max} step={step} value={value??''}
        onChange={e=>change(nval(e.target.value,min,max))}/></label>;
  }
  function choices(label:string,value:string,change:(value:string)=>void,options:string[][]){
    return <label className="sci-field"><span>{label}</span><select value={value}
      onChange={e=>change(e.target.value)}>{options.map(([key,name])=>
        <option key={key} value={key}>{name}</option>)}</select></label>;
  }
  function notesField(label:string,value:string,change:(value:string)=>void){
    return <label className="sci-field sci-wide"><span>{label}</span>
      <textarea rows={3} maxLength={1800} value={value} onChange={e=>change(e.target.value)}/></label>;
  }
  function saved(es:string,en:string){setNotice(tx(es,en));}
  function saveStudy(){
    if(!studyDraft.title.trim()){saved('Ingresá el nombre del estudio.','Enter a study title.');return;}
    setData(prev=>({...prev,studies:prev.studies.some(s=>s.study_id===studyDraft.study_id)
      ?prev.studies.map(s=>s.study_id===studyDraft.study_id?studyDraft:s)
      :[...prev.studies,studyDraft]}));
    setSelectedStudy(studyDraft.study_id);setStudyDraft(initialStudy());
    setTab('stations');saved('Proyecto registrado. Configurá su primera estación.',
      'Study saved. Configure its first camera deployment.');
  }
  function saveStation(){
    const coords=stationDraft.latitude!==null||stationDraft.longitude!==null;
    if(!stationDraft.camera_id.trim()||!stationDraft.site.trim()){
      saved('Indicá cámara y sitio de estudio.','Camera ID and site are required.');return;}
    if(coords&&(stationDraft.latitude===null||stationDraft.longitude===null)){
      saved('Completá ambas coordenadas o dejá ambas vacías.','Enter both coordinates or leave both blank.');return;}
    if(stationDraft.deployed_at&&stationDraft.retrieved_at&&stationDraft.retrieved_at<stationDraft.deployed_at){
      saved('El retiro no puede anteceder a la instalación.','Retrieval cannot precede deployment.');return;}
    setData(prev=>({...prev,deployments:prev.deployments.some(d=>d.deployment_id===stationDraft.deployment_id)
      ?prev.deployments.map(d=>d.deployment_id===stationDraft.deployment_id?stationDraft:d)
      :[...prev.deployments,stationDraft]}));
    setStationDraft(initialStation(activeId));
    saved('Estación incorporada al estudio.','Camera deployment added to the study.');
  }
  function saveIndividual(){
    const key=individualDraft.individual_id.trim();
    if(!key||!/^[\w.-]{1,90}$/.test(key)||!individualDraft.species.trim()){
      saved('Ingresá un ID alfanumérico y la especie.','Enter an alphanumeric ID and species.');return;}
    if(data.individuals.some(i=>i.individual_id===key&&i.study_id!==activeId)){
      // Globally unique IDs keep exports and lookups unambiguous across projects.
      saved('Este ID ya existe en otro proyecto. Usá un código distinto.',
        'This ID belongs to another study. Use a different code.');return;}
    if(individualDraft.status==='verified'&&!individualDraft.validated_by.trim()){
      saved('Una identidad validada requiere el nombre del investigador responsable.',
        'Verified identity requires a reviewer name.');return;}
    setData(prev=>({...prev,individuals:prev.individuals.some(i=>i.individual_id===key)
      ?prev.individuals.map(i=>i.individual_id===key?individualDraft:i)
      :[...prev.individuals,individualDraft]}));
    setIndividualDraft(initialIndividual(activeId));
    saved('Ficha individual guardada.','Individual profile saved.');
  }
  async function attachThumbnail(file:File){
    try{
      const data=await makeEvidencePreview(file);
      setEventDraft(p=>({...p,thumbnail_data_url:data,thumbnail_filename:file.name.slice(0,160)}));
      saved('Miniatura preparada para el informe. Guardá el evento para conservarla.',
        'Thumbnail ready for the report. Save the capture to keep it.');
    }catch(error){setNotice(error instanceof Error?error.message:String(error));}
  }
  function saveEvent(){
    if(!stations.some(d=>d.deployment_id===eventDraft.deployment_id)||!eventDraft.occurred_at){
      saved('Seleccioná una estación y la fecha/hora de la captura.',
        'Select a camera deployment and capture date/time.');return;}
    if(!Number.isFinite(new Date(eventDraft.occurred_at).getTime())){
      saved('Fecha de captura inválida.','Invalid capture date.');return;}
    setData(prev=>({...prev,encounters:prev.encounters.some(e=>e.encounter_id===eventDraft.encounter_id)
      ?prev.encounters.map(e=>e.encounter_id===eventDraft.encounter_id?eventDraft:e)
      :[...prev.encounters,eventDraft]}));
    setSelectedEvent(eventDraft.encounter_id);setTab('captures');
    setSightingDraft(initialSighting(eventDraft.encounter_id));
    saved('Captura guardada. Registrá ahora cada animal observado.',
      'Capture saved. Now record each observed animal.');
  }
  function saveSighting(){
    if(!selectedEvent||!encounters.some(e=>e.encounter_id===selectedEvent)){
      saved('Seleccioná primero una captura guardada.','Select a saved capture first.');return;}
    if(!sightingDraft.species.trim()){
      saved('Indicá la especie o una categoría taxonómica por revisar.',
        'Enter the species or an unresolved taxonomic category.');return;}
    if(sightingDraft.individual_id&&!people.some(p=>p.individual_id===sightingDraft.individual_id)){
      saved('El individuo debe pertenecer al proyecto actual.',
        'Individual must belong to the selected study.');return;}
    if(sightingDraft.individual_id){
      const linked=people.find(p=>p.individual_id===sightingDraft.individual_id);
      if(linked&&linked.species.trim().toLowerCase()!==sightingDraft.species.trim().toLowerCase()){
        saved('La especie debe coincidir con la ficha del individuo.',
          'Species must match the linked individual profile.');return;
      }
    }
    if(sightingDraft.identification_status==='verified'&&!sightingDraft.individual_id){
      saved('Una identificación validada necesita una ficha individual asociada.',
        'Verified identification needs a linked individual profile.');return;}
    if(sightingDraft.identification_status==='verified'&&(!sightingDraft.reviewer.trim()||
       people.find(p=>p.individual_id===sightingDraft.individual_id)?.status!=='verified')){
      saved('La identidad debe estar validada en el catálogo y contar con investigador revisor.',
        'Identity must be verified in the catalogue and include a reviewer.');return;}
    const ready={...sightingDraft,encounter_id:selectedEvent};
    setData(prev=>({...prev,sightings:prev.sightings.some(s=>s.sighting_id===ready.sighting_id)
      ?prev.sightings.map(s=>s.sighting_id===ready.sighting_id?ready:s)
      :[...prev.sightings,ready]}));
    setSightingDraft(initialSighting(selectedEvent));
    saved('Animal asociado al evento. Podés añadir más observaciones a esta captura.',
      'Animal linked to the event. You can add more observations to this capture.');
  }
  function chooseEvent(e:Encounter){
    setSelectedEvent(e.encounter_id);setEventDraft({...e});setSightingDraft(initialSighting(e.encounter_id));
    setNotice('');
  }
  function removeEncounter(e:Encounter){
    if(!window.confirm(tx('¿Eliminar esta captura y sus observaciones asociadas?',
      'Delete this capture and all its linked animal observations?')))return;
    setData(p=>({...p,encounters:p.encounters.filter(v=>v.encounter_id!==e.encounter_id),
      sightings:p.sightings.filter(s=>s.encounter_id!==e.encounter_id)}));
    if(selectedEvent===e.encounter_id)setSelectedEvent('');
  }
  async function report(kind:'pdf'|'zip',individualId='',encounterId=''){
    if(!study)return;
    if(includePrecise&&!window.confirm(tx(
      'Este archivo incluirá coordenadas precisas de cámaras. ¿Confirmás que su uso está autorizado?',
      'This file will include precise camera coordinates. Confirm you are authorized to export them?')))return;
    setPdfBusy(true);setNotice('');
    try{
      const body=projectPackage(data,activeId,!includePrecise,language);
      const query=new URLSearchParams({kind});
      if(individualId)query.set('individual_id',individualId);
      if(encounterId)query.set('encounter_id',encounterId);
      const response=await fetch('/api/science/studies/report?'+query.toString(),{
        method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),cache:'no-store'});
      if(!response.ok){let detail='HTTP '+response.status;
        try{const v=await response.json();if(v.detail)detail=String(v.detail);}catch{/* content */}throw new Error(detail);}
      const bytes=await response.blob();
      const suffix=individualId?'_individuo_'+individualId:
        encounterId?'_captura_'+encounterId:'_'+study.study_id;
      downloadFile('PantheraLAB'+suffix+(kind==='pdf'?'_informe.pdf':'_dataset.zip'),bytes);
      saved('Informe generado. Revisá los archivos antes de distribuirlos.',
        'Report generated. Review files before distributing them.');
    }catch(err){setNotice(err instanceof Error?err.message:String(err));}
    finally{setPdfBusy(false);}
  }
  async function restoreBackup(file:File){
    if(file.size>4000000){saved('El archivo de respaldo supera 4 MB.','Backup exceeds 4 MB.');return;}
    try{
      const value:unknown=JSON.parse(await file.text());
      if(!value||typeof value!=='object')throw new Error('Invalid format');
      const src=value as Record<string,unknown>;
      if(src.version!==1||!['studies','deployments','individuals','encounters','sightings']
        .every(k=>Array.isArray(src[k])))throw new Error('Invalid version');
      for(const key of ['studies','deployments','individuals','encounters','sightings']){
        const items=src[key] as unknown[];
        if(items.length>1500||items.some(item=>item===null||typeof item!=='object'||Array.isArray(item)))
          throw new Error('Malformed records');
      }
      const studies=src.studies as Study[],deployments=src.deployments as Deployment[],
        individuals=src.individuals as Individual[],encounters=src.encounters as Encounter[],
        sightings=src.sightings as Sighting[];
      const studyIds=new Set(studies.map(p=>p.study_id));
      const cameraIds=new Set(deployments.map(d=>d.deployment_id));
      const encounterIds=new Set(encounters.map(e=>e.encounter_id));
      const individualIds=new Set(individuals.map(i=>i.individual_id));
      if(studies.some(p=>typeof p.study_id!=='string'||typeof p.title!=='string')||
         deployments.some(d=>!studyIds.has(d.study_id))||
         individuals.some(i=>!studyIds.has(i.study_id))||
         encounters.some(e=>!studyIds.has(e.study_id)||!cameraIds.has(e.deployment_id))||
         sightings.some(o=>!encounterIds.has(o.encounter_id)||
           (o.individual_id&&!individualIds.has(o.individual_id))))
        throw new Error('Inconsistent relationships');
      if(!window.confirm(tx('Esto reemplazará los datos locales de TODOS los proyectos. ¿Continuar?',
        'This will replace local data for ALL projects. Continue?')))return;
      setData(src as ResearchData);setSelectedStudy('');
      saved('Respaldo restaurado en este navegador.','Backup restored to this browser.');
    }catch{saved('No se pudo restaurar: respaldo incompatible.','Unable to restore: incompatible backup.');}
  }

  const activeSightings=sightings.filter(s=>s.encounter_id===selectedEvent);
  const verifiedPeople=new Set(sightings.filter(s=>s.individual_id&&
    s.identification_status==='verified'&&people.find(i=>i.individual_id===s.individual_id)?.status==='verified')
    .map(s=>s.individual_id));
  const eventMap=new Map(encounters.map(e=>[e.encounter_id,e]));
  const stationMap=new Map(stations.map(d=>[d.deployment_id,d]));
  const perIndividual=(id:string)=>sightings.filter(s=>s.individual_id===id);
  const filteredSightings=sightings.filter(s=>{
    if(filterStatus==='verified'&&s.identification_status!=='verified')return false;
    const time=eventMap.get(s.encounter_id)?.occurred_at.slice(0,10)||'';
    return (!startDate||time>=startDate)&&(!endDate||time<=endDate);
  });

  return <div className="sci-screen research-registry">
    <div className="sci-heading"><div><span className="sci-kicker">PANTHERAMONITORING / SCIENTIFIC RECORDS</span>
      <h2>{tx('Centro de investigación de fauna','Wildlife research workspace')}</h2>
      <p>{tx('Organizá estudios, cámaras, capturas e individuos en un registro vinculado y trazable.',
        'Organize studies, cameras, capture events and individuals in a linked, traceable registry.')}</p>
    </div><span className="sci-tag">{tx('REGISTRO DE CAMPO','FIELD REGISTRY')}</span></div>
    <div className="sci-inline-info"><span className="sci-info-dot" aria-hidden="true"/>
      <p>{tx('Los registros se conservan localmente en este navegador (no sincronizados). Exportá un respaldo y no usés equipos compartidos para coordenadas sensibles. Los videos y fotografías no se almacenan aquí; solo sus referencias.',
        'Records are stored locally in this browser (not synchronized). Export a backup and avoid shared devices for sensitive coordinates. Videos and photos are not saved here, only their references.')}</p></div>

    <div className="registry-topline">
      <label className="sci-field"><span>{tx('Estudio activo','Active study')}</span>
        <select value={activeId} onChange={e=>{setSelectedStudy(e.target.value);setTab('projects');}}>
          {data.studies.length===0&&<option value="">{tx('Crear primer estudio','Create your first study')}</option>}
          {data.studies.map(s=><option key={s.study_id} value={s.study_id}>{s.title}</option>)}
        </select></label>
      {study&&<span className="sci-tag">{study.study_id}</span>}
    </div>

    <div className="sci-stats">
      <div><span>{tx('Estaciones registradas','Camera deployments')}</span><strong>{stations.length}</strong></div>
      <div><span>{tx('Eventos de captura','Capture events')}</span><strong>{encounters.length}</strong></div>
      <div><span>{tx('Observaciones de animales','Animal observations')}</span><strong>{sightings.length}</strong></div>
      <div><span>{tx('Identidades verificadas','Verified identities')}</span><strong>{verifiedPeople.size}</strong></div>
    </div>

    <div className="registry-tabs" role="group" aria-label={tx('Secciones del registro','Registry sections')}>
      {([
        ['projects',tx('01 · Estudios','01 · Studies')],
        ['stations',tx('02 · Estaciones','02 · Stations')],
        ['captures',tx('03 · Capturas','03 · Captures')],
        ['individuals',tx('04 · Individuos','04 · Individuals')],
        ['reports',tx('05 · Informes','05 · Reports')],
      ] as [Tab,string][]).map(([key,title])=>
      <button key={key} type="button" className={tab===key?'selected':''}
        onClick={()=>{setTab(key);setNotice('');}}>{title}</button>)}
    </div>
    {notice&&<p className="sci-notice" role="status">{notice}</p>}

    {tab==='projects'&&<section className="sci-panel">
      <div className="sci-panel-head"><h3>{tx('Proyecto de investigación','Research study')}</h3>
        <button type="button" className="sci-secondary" onClick={()=>setStudyDraft(initialStudy())}>
          + {tx('Nuevo estudio','New study')}</button></div>
      <p className="sci-muted">{tx('Definí el objetivo y el protocolo una vez. Podés actualizar la ficha antes de emitir el informe.',
        'Define the objective and protocol once. You can update the study profile before reporting.')}</p>
      {study&&<div className="registry-study-card"><strong>{study.title}</strong>
        <span>{study.organization||tx('Sin institución declarada','No organization provided')}</span>
        <button type="button" className="sci-inline" onClick={()=>setStudyDraft({...study})}>
          {tx('Editar ficha del estudio','Edit study profile')}</button></div>}
      <div className="sci-fields">
        {textField(tx('Título del estudio *','Study title *'),studyDraft.title,v=>setStudy('title',v),
          tx('Monitoreo de jaguares · Península de Osa','Jaguar monitoring · Osa Peninsula'))}
        {textField(tx('Institución','Institution'),studyDraft.organization,v=>setStudy('organization',v))}
        {textField(tx('Responsable científico','Principal investigator'),studyDraft.lead,v=>setStudy('lead',v))}
        {textField(tx('Inicio','Start date'),studyDraft.start_date,v=>setStudy('start_date',v),'','date')}
        {textField(tx('Fin','End date'),studyDraft.end_date,v=>setStudy('end_date',v),'','date')}
        <label className="sci-field sci-wide"><span>{tx('Código de proyecto','Study ID')}</span>
          <input value={studyDraft.study_id} readOnly /></label>
        {notesField(tx('Objetivos e hipótesis','Objectives and hypotheses'),studyDraft.objectives,v=>setStudy('objectives',v))}
        {notesField(tx('Método / protocolo de cámaras trampa','Sampling protocol'),studyDraft.methodology,v=>setStudy('methodology',v))}
      </div>
      <button className="action-button" type="button" onClick={saveStudy}>
        {tx('Guardar ficha del estudio','Save study profile')}</button>
      {data.studies.length>1&&<div className="registry-list">{data.studies.map(p=>
        <button type="button" key={p.study_id} className="registry-record-button"
          onClick={()=>{setSelectedStudy(p.study_id);setStudyDraft({...p});}}>
          <strong>{p.title}</strong><small>{p.study_id}</small></button>)}</div>}
    </section>}

    {tab==='stations'&&<section className="sci-panel">
      <div className="sci-panel-head"><h3>{tx('Estaciones y despliegues','Camera deployments')}</h3>
        <button className="sci-secondary" type="button" onClick={()=>setStationDraft(initialStation(activeId))}>
          + {tx('Nueva estación','New deployment')}</button></div>
      {!study?<p className="sci-warning">{tx('Creá un estudio antes de registrar estaciones.',
        'Create a study before registering deployments.')}</p>:<>
        <p className="sci-muted">{tx('Las coordenadas y la altitud se registran aquí una sola vez. Cada captura hereda la estación.',
          'Coordinates and altitude are entered here once. Each capture references its deployment.')}</p>
        <div className="sci-fields">
          {textField(tx('ID de cámara *','Camera ID *'),stationDraft.camera_id,v=>setStation('camera_id',v),'CT-07')}
          {textField(tx('Sitio / hábitat *','Site / habitat *'),stationDraft.site,v=>setStation('site',v),
            tx('Bosque húmedo','Humid forest'))}
          {decimalField('Latitud WGS84',stationDraft.latitude,v=>setStation('latitude',v),-90,90)}
          {decimalField('Longitud WGS84',stationDraft.longitude,v=>setStation('longitude',v),-180,180)}
          {decimalField(tx('Altitud (m)','Altitude (m)'),stationDraft.altitude_m,v=>setStation('altitude_m',v),-500,9000)}
          {textField(tx('Instalación','Deployed'),stationDraft.deployed_at,v=>setStation('deployed_at',v),'','date')}
          {textField(tx('Retiro','Retrieved'),stationDraft.retrieved_at,v=>setStation('retrieved_at',v),'','date')}
          {decimalField(tx('Días-cámara operativos reportados','Reported operational camera-days'),
            stationDraft.operational_days,v=>setStation('operational_days',v),0,100000,'1')}
          {notesField(tx('Condiciones, fallas y protocolo','Conditions, downtime and protocol'),
            stationDraft.notes,v=>setStation('notes',v))}
        </div>
        <p className="sci-muted">{tx('Los días-cámara se declaran manualmente; la aplicación no presume actividad continua entre instalación y retiro.',
          'Camera-days are manually reported; continuous operation is not assumed between deployment and retrieval.')}</p>
        <button className="action-button" type="button" onClick={saveStation}>
          {tx('Guardar estación','Save deployment')}</button>
        {stations.length>0&&<div className="sci-table-wrap"><table className="sci-table">
          <thead><tr><th>{tx('Cámara','Camera')}</th><th>{tx('Sitio','Site')}</th><th>{tx('Días operativos','Operational days')}</th><th></th></tr></thead>
          <tbody>{stations.map(d=><tr key={d.deployment_id}><td>{d.camera_id}</td><td>{d.site}</td>
            <td>{d.operational_days??'—'}</td><td><button type="button" className="sci-inline"
              onClick={()=>setStationDraft({...d})}>{tx('Editar','Edit')}</button>
              {d.latitude!==null&&d.longitude!==null&&<button type="button" className="sci-inline"
                onClick={()=>setMapDeployment(d.deployment_id===mapDeployment?'':d.deployment_id)}>
                {tx('Ver mapa','Show map')}</button>}</td></tr>)}</tbody>
        </table></div>}
        {mapDeployment&&(()=>{
          const location=stations.find(d=>d.deployment_id===mapDeployment);
          if(!location||location.latitude===null||location.longitude===null)return null;
          const {latitude:lat,longitude:lon}=location;
          const bbox=[lon-.06,lat-.04,lon+.06,lat+.04].map(v=>v.toFixed(5)).join('%2C');
          const src='https://www.openstreetmap.org/export/embed.html?bbox='+bbox+
            '&layer=mapnik&marker='+lat.toFixed(6)+'%2C'+lon.toFixed(6);
          return <div className="sci-map-toggle">
            <p className="sci-muted">{tx('Al abrir este mapa, las coordenadas de la estación se comparten con OpenStreetMap.',
              'Opening this map shares the camera location with OpenStreetMap.')}</p>
            <iframe className="sci-map" title={tx('Mapa de estación','Camera deployment map')}
              loading="lazy" referrerPolicy="no-referrer" src={src}/>
          </div>;
        })()}
      </>}
    </section>}

    {tab==='individuals'&&<section className="sci-panel">
      <div className="sci-panel-head"><h3>{tx('Catálogo de individuos','Individual catalogue')}</h3>
        <button type="button" className="sci-secondary" onClick={()=>setIndividualDraft(initialIndividual(activeId))}>
          + {tx('Nueva ficha','New profile')}</button></div>
      {!study?<p className="sci-warning">{tx('Primero creá un estudio.','Create a study first.')}</p>:<>
        <p className="sci-muted">{tx('Un individuo puede asociarse con múltiples capturas. La identidad solo se marca verificada después de revisión humana.',
          'An individual can be linked to many captures. Mark identity verified only after human evidence review.')}</p>
        <div className="sci-fields">
          <label className="sci-field"><span>{tx('Código de individuo *','Individual code *')}</span>
            <input type="text" maxLength={90} value={individualDraft.individual_id}
              readOnly={people.some(p=>p.individual_id===individualDraft.individual_id)}
              onChange={e=>setPerson('individual_id',e.target.value)}/>
          </label>
          {textField(tx('Especie *','Species *'),individualDraft.species,v=>setPerson('species',v),'Panthera onca')}
          {choices(tx('Sexo anotado','Annotated sex'),individualDraft.sex,v=>setPerson('sex',v),opts.sex)}
          {choices(tx('Edad estimada','Estimated age'),individualDraft.age_class,v=>setPerson('age_class',v),opts.age)}
          {choices(tx('Estado de identificación','Identity review status'),individualDraft.status,
            v=>setPerson('status',v),[['provisional',tx('Provisional','Provisional')],['verified',tx('Validada','Verified')]])}
          {textField(tx('Revisor responsable','Reviewer'),individualDraft.validated_by,v=>setPerson('validated_by',v))}
          {textField(tx('URL de fotografía de referencia','Reference photo URL'),individualDraft.reference_image_url,
            v=>setPerson('reference_image_url',v),'https://...','url')}
          {notesField(tx('Patrón de rosetas / marcas distintivas','Rosettes / distinctive markings'),
            individualDraft.marks,v=>setPerson('marks',v))}
          {notesField(tx('Observaciones de identificación','Identification notes'),
            individualDraft.notes,v=>setPerson('notes',v))}
        </div>
        <button type="button" className="action-button" onClick={saveIndividual}>
          {tx('Guardar ficha individual','Save individual profile')}</button>
        <div className="registry-person-grid">{people.map(ind=>{
          const linked=perIndividual(ind.individual_id);
          const nEvents=new Set(linked.map(s=>s.encounter_id)).size;
          return <article key={ind.individual_id} className="registry-person">
            {ind.reference_image_url.startsWith('https://')&&
              <a href={ind.reference_image_url} target="_blank" rel="noreferrer noopener"
                className="registry-photo-ref">{tx('Ver referencia fotográfica ↗','View photo reference ↗')}</a>}
            <span className="sci-kicker">{ind.status==='verified'?tx('IDENTIDAD VALIDADA','VERIFIED IDENTITY'):
              tx('IDENTIDAD PROVISIONAL','PROVISIONAL IDENTITY')}</span>
            <h4>{ind.individual_id}</h4><em>{ind.species}</em>
            <p>{ind.marks||tx('Sin rasgos distintivos descritos.','No distinguishing marks described.')}</p>
            <span className="registry-count">{nEvents} {tx('encuentros asociados','linked encounters')}</span>
            <details className="method-details"><summary>{tx('Historial de encuentros','Encounter history')}</summary>
              {linked.length===0?<p>{tx('Sin observaciones vinculadas.','No linked sightings.')}</p>:
              <div className="registry-history">{linked.map(s=>{
                const e=eventMap.get(s.encounter_id),dep=e?stationMap.get(e.deployment_id):undefined;
                return <p key={s.sighting_id}><strong>{e?.occurred_at.slice(0,16)||'—'}</strong>
                  {' · '+(dep?.camera_id||'—')+' · '+(s.behavior||'—')+' · '+s.identification_status}</p>;
              })}</div>}</details>
            <div className="sci-actions">
              <button type="button" className="sci-secondary" onClick={()=>setIndividualDraft({...ind})}>
                {tx('Editar ficha','Edit profile')}</button>
              <button type="button" className="sci-secondary" disabled={pdfBusy}
                onClick={()=>void report('pdf',ind.individual_id)}>
                {tx('Informe individual · PDF ↓','Individual report · PDF ↓')}</button>
            </div>
          </article>;
        })}</div>
      </>}
    </section>}

    {tab==='captures'&&<>
      <section className="sci-panel">
        <div className="sci-panel-head"><h3>{tx('Evento de captura','Capture event')}</h3>
          <button type="button" className="sci-secondary" onClick={()=>{
            setSelectedEvent('');setEventDraft(initialEvent(activeId,stations[0]?.deployment_id||''));
            setSightingDraft(initialSighting(''));
          }}>+ {tx('Nueva captura','New capture')}</button></div>
        {!stations.length?<p className="sci-warning">{tx('Registrá una estación antes de documentar capturas.',
          'Register a camera deployment before documenting captures.')}</p>:<>
          <p className="sci-muted">{tx('Un video o ráfaga fotográfica representa un evento de captura; agregá una observación por cada animal visible.',
            'A video or image burst represents one capture event; add one sighting per visible animal.')}</p>
          <div className="sci-fields">
            {choices(tx('Estación *','Camera deployment *'),eventDraft.deployment_id,
              v=>setEvent('deployment_id',v),[['',tx('Seleccionar…','Choose…')],
                ...stations.map(d=>[d.deployment_id,d.camera_id+' · '+d.site])])}
            {textField(tx('Fecha y hora de captura *','Capture date and time *'),
              inputTime(eventDraft.occurred_at),v=>{
                setEvent('occurred_at',v?new Date(v).toISOString():'');
              },'','datetime-local')}
            {textField(tx('Investigador / anotador','Observer / annotator'),
              eventDraft.observer,v=>setEvent('observer',v))}
            {decimalField(tx('Temperatura de evento (°C)','Event temperature (°C)'),
              eventDraft.temperature_c,v=>setEvent('temperature_c',v),-80,85)}
            {decimalField(tx('Humedad relativa (%)','Relative humidity (%)'),
              eventDraft.humidity_percent,v=>setEvent('humidity_percent',v),0,100)}
            {choices(tx('Fuente ambiental','Environmental data source'),eventDraft.environment_source,
              v=>setEvent('environment_source',v),[
                ['unprovided',tx('No proporcionada','Not provided')],
                ['sensor',tx('Sensor de campo','Field sensor')],
                ['manual',tx('Medición o anotación manual','Manual reading or annotation')],
                ['external',tx('Fuente externa','External source')]])}
            {textField(tx('Referencia URL de imagen','Image reference URL'),eventDraft.image_url,
              v=>setEvent('image_url',v),'https://...','url')}
            {textField(tx('Referencia URL de video','Video reference URL'),eventDraft.video_url,
              v=>setEvent('video_url',v),'https://...','url')}
          <label className="sci-field sci-wide"><span>{tx('Fotografía de referencia para el informe',
              'Reference photo for report')}</span>
            <input type="file" accept="image/jpeg,image/png,image/webp" onChange={e=>{
              const file=e.target.files?.[0];if(file)void attachThumbnail(file);e.target.value='';
            }}/>
            <small>{tx('Se guarda una miniatura comprimida en este navegador; conservá el original por separado.',
              'A compressed thumbnail is saved in this browser; keep the original separately.')}</small>
          </label>
          {eventDraft.thumbnail_data_url&&
            <div className="registry-thumb-wrap">
              <img src={eventDraft.thumbnail_data_url} alt={tx('Miniatura de la captura','Capture thumbnail')}/>
              <button type="button" className="sci-secondary" onClick={()=>
                setEventDraft(p=>({...p,thumbnail_data_url:'',thumbnail_filename:''}))}>
                {tx('Quitar miniatura','Remove thumbnail')}</button>
            </div>}
          {textField('PantheraEDGE event ID',eventDraft.edge_event_id,v=>setEvent('edge_event_id',v))}
            {notesField(tx('Notas del evento','Capture notes'),eventDraft.notes,v=>setEvent('notes',v))}
          </div>
          <button type="button" className="action-button" onClick={saveEvent}>
            {tx('Guardar evento de captura','Save capture event')}</button>
          <p className="sci-muted">{tx('Las miniaturas aparecen en los informes, pero no sustituyen la fotografía original. Las referencias URL no adjuntan archivos externos automáticamente.',
            'Thumbnails appear in reports but do not replace original photographs. URL references do not automatically attach external files.')}</p>
          {encounters.length>0&&<div className="sci-table-wrap"><table className="sci-table">
            <thead><tr><th>{tx('Fecha UTC','Date UTC')}</th><th>{tx('Cámara','Camera')}</th>
              <th>{tx('Animales registrados','Sightings')}</th><th>{tx('Acciones','Actions')}</th></tr></thead>
            <tbody>{[...encounters].sort((a,b)=>b.occurred_at.localeCompare(a.occurred_at)).map(e=>
              <tr key={e.encounter_id}><td>{e.occurred_at.slice(0,16)}</td>
                <td>{stationMap.get(e.deployment_id)?.camera_id||'—'}</td>
                <td>{sightings.filter(s=>s.encounter_id===e.encounter_id).length}</td>
                <td><button type="button" className="sci-inline" onClick={()=>chooseEvent(e)}>
                    {tx('Abrir / editar','Open / edit')}</button>
                  <button type="button" className="sci-inline" disabled={pdfBusy}
                    onClick={()=>void report('pdf','',e.encounter_id)}>{tx('Informe PDF ↓','PDF report ↓')}</button>
                  <button type="button" className="sci-inline sci-danger" onClick={()=>removeEncounter(e)}>
                    {tx('Eliminar','Delete')}</button></td></tr>)}</tbody></table></div>}
        </>}
      </section>
      {selectedEvent&&<section className="sci-panel" id="registry-sightings">
        <div className="sci-panel-head"><h3>{tx('Animales observados en esta captura','Animals observed in this capture')}</h3>
          <span className="sci-tag">{activeSightings.length} {tx('observaciones','sightings')}</span></div>
        <p className="sci-muted">{tx('Podés registrar dos o más jaguares en la misma captura sin duplicar el evento ni los datos de la cámara.',
          'You can register two or more jaguars in one capture without duplicating the event or camera metadata.')}</p>
        <div className="sci-fields">
          {textField(tx('Especie / taxón *','Species / taxon *'),sightingDraft.species,v=>setSighting('species',v))}
          {choices(tx('Individuo (opcional)','Individual (optional)'),sightingDraft.individual_id,
            v=>setSighting('individual_id',v),[['',tx('Sin identificar','Unidentified')],
              ...people.map(p=>[p.individual_id,p.individual_id+' · '+p.status])])}
          {choices(tx('Confianza de identidad (revisión humana)','Human identity review'),
            sightingDraft.identification_status,v=>setSighting('identification_status',v),[
              ['unidentified',tx('No identificado','Unidentified')],
              ['tentative',tx('Asignación provisional','Tentative match')],
              ['verified',tx('Identidad validada','Verified identity')]])}
          {choices(tx('Sexo observado','Observed sex'),sightingDraft.sex,v=>setSighting('sex',v),opts.sex)}
          {choices(tx('Clase de edad','Age class'),sightingDraft.age_class,
            v=>setSighting('age_class',v),opts.age)}
          {choices(tx('Orientación de cámara','Viewpoint'),sightingDraft.viewpoint,
            v=>setSighting('viewpoint',v),[
              ['unknown',tx('Desconocido','Unknown')],['left',tx('Perfil izquierdo','Left flank')],
              ['right',tx('Perfil derecho','Right flank')],['front',tx('Frontal','Frontal')],
              ['back',tx('Posterior','Rear')]])}
          {textField(tx('Comportamiento observado','Observed behavior'),
            sightingDraft.behavior,v=>setSighting('behavior',v),
            tx('Caminando, marcaje, reposo…','Walking, marking, resting…'))}
          {textField(tx('Investigador que revisó la identidad','Identity reviewer'),
            sightingDraft.reviewer,v=>setSighting('reviewer',v))}
          {notesField(tx('Evidencia distintiva y observaciones','Distinctive evidence and notes'),
            sightingDraft.notes,v=>setSighting('notes',v))}
        </div>
        <div className="sci-actions"><button type="button" className="action-button" onClick={saveSighting}>
          {tx('Guardar observación de animal','Save animal sighting')}</button>
          <button type="button" className="sci-secondary"
            onClick={()=>{setSightingDraft(initialSighting(selectedEvent));setTab('individuals');}}>
            {tx('Crear individuo en catálogo','Create individual profile')}</button></div>
        {activeSightings.length>0&&<div className="sci-table-wrap"><table className="sci-table">
          <thead><tr><th>{tx('Especie','Species')}</th><th>{tx('Individuo','Individual')}</th>
            <th>{tx('Identidad','Identity')}</th><th>{tx('Conducta','Behavior')}</th><th></th></tr></thead>
          <tbody>{activeSightings.map(s=><tr key={s.sighting_id}>
            <td>{s.species}</td><td>{s.individual_id||'—'}</td><td>{s.identification_status}</td>
            <td>{s.behavior||'—'}</td><td>
              <button type="button" className="sci-inline" onClick={()=>setSightingDraft({...s})}>
                {tx('Editar','Edit')}</button>
              <button type="button" className="sci-inline sci-danger" onClick={()=>{
                if(window.confirm(tx('¿Eliminar esta observación?','Delete this sighting?')))
                  setData(p=>({...p,sightings:p.sightings.filter(v=>v.sighting_id!==s.sighting_id)}));
              }}>{tx('Eliminar','Delete')}</button></td></tr>)}</tbody>
        </table></div>}
      </section>}
    </>}

    {tab==='reports'&&<section className="sci-panel">
      <div className="sci-panel-head"><h3>{tx('Informe integral de investigación','Consolidated study report')}</h3>
        <span className="sci-tag">PDF + DATASET</span></div>
      {!study?<p className="sci-warning">{tx('Creá un proyecto antes de generar informes.',
        'Create a study before generating reports.')}</p>:<>
        <p className="sci-muted">{tx('Un solo documento reúne proyecto, estaciones, esfuerzo declarado, catálogo de individuos, historial de encuentros, observaciones y variables ambientales.',
          'One document combines study metadata, camera deployments, reported effort, individual catalogue, encounter history, sightings and environment.')}</p>
        <div className="sci-stats">
          <div><span>{tx('Capturas','Capture events')}</span><strong>{encounters.length}</strong></div>
          <div><span>{tx('Animales observados','Animal sightings')}</span><strong>{sightings.length}</strong></div>
          <div><span>{tx('Perfiles individuales','Individual profiles')}</span><strong>{people.length}</strong></div>
          <div><span>{tx('Estaciones','Deployments')}</span><strong>{stations.length}</strong></div>
        </div>
        <label className="registry-checkbox"><input type="checkbox" checked={includePrecise}
          onChange={e=>setIncludePrecise(e.target.checked)}/>
          <span>{tx('Incluir coordenadas exactas en PDF y ZIP (requiere autorización)',
            'Include precise coordinates in PDF and ZIP (authorization required)')}</span></label>
        <p className="sci-muted">{tx('Por defecto se ocultan las coordenadas. El servidor genera el informe sin guardar los registros. El PDF y ZIP incluyen las miniaturas cargadas; las fotos y videos originales permanecen fuera del paquete y se citan mediante URL.',
          'Coordinates are hidden by default. Reports are generated without server-side storage. PDF and ZIP include uploaded thumbnails; original photos and videos remain outside the package and are referenced by URL.')}</p>
        <div className="sci-actions">
          <button type="button" className="action-button" disabled={pdfBusy} onClick={()=>void report('pdf')}>
            {pdfBusy?tx('Generando informe…','Generating report…'):
              tx('Descargar informe científico · PDF ↓','Download scientific report · PDF ↓')}</button>
          <button type="button" className="sci-secondary" disabled={pdfBusy} onClick={()=>void report('zip')}>
            {tx('Paquete de investigación · ZIP ↓','Research dataset · ZIP ↓')}</button>
        </div>
        <h3 className="registry-subtitle">{tx('Explorar observaciones','Explore observations')}</h3>
        <div className="sci-fields">
          {textField(tx('Desde','From'),startDate,setStartDate,'','date')}
          {textField(tx('Hasta','To'),endDate,setEndDate,'','date')}
          {choices(tx('Identificación','Identification'),filterStatus,setFilterStatus as (v:string)=>void,
            [['all',tx('Todas','All')],['verified',tx('Solo identidades verificadas','Verified only')]])}
        </div>
        <div className="sci-table-wrap"><table className="sci-table">
          <thead><tr><th>UTC</th><th>{tx('Cámara','Camera')}</th><th>{tx('Especie','Species')}</th>
            <th>{tx('Individuo','Individual')}</th><th>{tx('Conducta','Behavior')}</th><th>{tx('Estado','Review')}</th></tr></thead>
          <tbody>{filteredSightings.map(s=>{
            const e=eventMap.get(s.encounter_id);
            return <tr key={s.sighting_id}><td>{e?.occurred_at.slice(0,16)||'—'}</td>
              <td>{stationMap.get(e?.deployment_id||'')?.camera_id||'—'}</td>
              <td>{s.species}</td><td>{s.individual_id||tx('Sin identificar','Unidentified')}</td>
              <td>{s.behavior||'—'}</td><td>{s.identification_status}</td></tr>;
          })}</tbody>
        </table></div>
        <p className="sci-muted">{tx('Los filtros de esta tabla son exploratorios. PDF y ZIP exportan el estudio completo, incluyendo anotaciones provisionales, para no perder la trazabilidad.',
          'Table filters are for exploration. PDF and ZIP export the full study, including provisional annotations, to preserve traceability.')}</p>
      </>}
    </section>}

    <section className="sci-panel">
      <div className="sci-panel-head"><h3>{tx('Respaldo y recuperación','Backup and recovery')}</h3>
        <span className="sci-tag">{tx('SOLO EN ESTE DISPOSITIVO','ON THIS DEVICE ONLY')}</span></div>
      <p className="sci-muted">{tx('Guardá una copia de todos los estudios en JSON para recuperarlos o moverlos a otro dispositivo. Este respaldo privado incluye coordenadas exactas y referencias de evidencia.',
        'Download a JSON backup of all studies for recovery or transfer. This private backup includes precise coordinates and evidence references.')}</p>
      <div className="sci-actions">
        <button type="button" className="sci-secondary" onClick={()=>{
          if(window.confirm(tx('El respaldo contendrá coordenadas exactas y todas las observaciones. ¿Generarlo?',
            'The backup will include precise locations and all observations. Generate it?')))
            downloadFile('PantheraLAB_respaldo_privado.json',JSON.stringify(data,null,2),'application/json');
        }}>{tx('Descargar respaldo privado · JSON','Download private JSON backup')}</button>
        <button type="button" className="sci-secondary" onClick={()=>fileRef.current?.click()}>
          {tx('Restaurar respaldo JSON','Restore JSON backup')}</button>
        <input className="registry-hidden" ref={fileRef} type="file" accept=".json,application/json"
          onChange={e=>{const f=e.target.files?.[0];if(f)void restoreBackup(f);e.target.value='';}}/>
      </div>
    </section>
  </div>;
}
