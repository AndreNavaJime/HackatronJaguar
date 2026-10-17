import React from 'react';
import ResearchRegistry from './ResearchRegistry';
import EdgeWorkspace from './EdgeWorkspace';
import SensePanel from './SensePanel';
import FireWorkspace from './FireWorkspace';
import ResearchWorkspace from './ResearchWorkspace';
import AIResultsPanel from './AIResultsPanel';
import {useLanguage} from './language';
import {Observation,EdgeEvent,newObservation,loadSession,saveSession} from './scienceShared';
import {ResearchData,loadResearch,persistResearch,flattenObservations} from './researchData';
import {readStudyData,saveStudyData} from './researchDb';
import type {CameraFireCandidate} from './cameraEvents';

import type {VideoEvidenceBatch} from './videoWorkspaceDb';
type Props={section:string;onNavigate:(section:string)=>void;
  pendingEvidence?:VideoEvidenceBatch|null;onClearEvidence?:()=>void;
  monitoringNextRequest?:number;
  onRegistryTabChange?:(tab:'projects'|'stations'|'captures'|'individuals')=>void;
  onActiveStudyInfo?:(title:string)=>void;
};

export default function ScientificWorkspace({section,onNavigate,pendingEvidence,onClearEvidence,
  monitoringNextRequest=0,onRegistryTabChange,onActiveStudyInfo}:Props){
  const {language}=useLanguage(),tx=(es:string,en:string)=>language==='en'?en:es;
  const [research,setResearch]=React.useState<ResearchData>(loadResearch);
  const [activeStudyId,setActiveStudyId]=React.useState(()=>{
    try{return localStorage.getItem('pantheralab_selected_study_v1')||'';}catch{return '';}
  });
  const [persistError,setPersistError]=React.useState(false);
  const [researchReady,setResearchReady]=React.useState(false);
  const [events,setEvents]=React.useState<EdgeEvent[]>(()=>{
    const value=loadSession<unknown>('pantheralab_session_edge_events_v1',[]);
    return Array.isArray(value)?value as EdgeEvent[]:[];
  });
  const [current,setCurrent]=React.useState<Observation>(()=>newObservation());
  const [incoming,setIncoming]=React.useState<EdgeEvent|null>(null);
  const [cameraFireEvents,setCameraFireEvents]=React.useState<CameraFireCandidate[]>(()=>{
    const stored=loadSession<unknown>('pantheralab_camera_fire_events_v1',[]);
    return Array.isArray(stored)?stored.filter((v):v is CameraFireCandidate=>
      typeof v==='object'&&v!==null&&
      (v.source==='virtual_fire_simulation'||v.source==='pyroengine_browser_camera')&&
      (v.signal==='smoke'||v.signal==='flame'||v.signal==='fire')).slice(0,30):[];
  });
  const activeStudy=research.studies.find(p=>p.study_id===activeStudyId)||research.studies[0];
  React.useEffect(()=>{onActiveStudyInfo?.(activeStudy?.title||'');},
    [activeStudy?.title,onActiveStudyInfo]);
  const studyRecords=React.useMemo(()=>{
    const id=activeStudy?.study_id;
    if(!id)return {...research,studies:[],deployments:[],individuals:[],encounters:[],sightings:[]};
    const encounters=research.encounters.filter(e=>e.study_id===id);
    const eventIds=new Set(encounters.map(e=>e.encounter_id));
    return {...research,studies:research.studies.filter(p=>p.study_id===id),
      deployments:research.deployments.filter(d=>d.study_id===id),
      individuals:research.individuals.filter(p=>p.study_id===id),
      encounters,sightings:research.sightings.filter(s=>eventIds.has(s.encounter_id))};
  },[research,activeStudy?.study_id]);
  const records=React.useMemo(()=>flattenObservations(studyRecords),[studyRecords]);

  React.useEffect(()=>{
    let cancelled=false;
    void readStudyData().then(stored=>{
      if(!cancelled&&stored)setResearch(stored);
    }).catch(()=>{
      if(!cancelled)setPersistError(true);
    }).finally(()=>{if(!cancelled)setResearchReady(true);});
    return ()=>{cancelled=true;};
  },[]);
  React.useEffect(()=>{
    if(!researchReady)return;
    const metadataSaved=persistResearch(research);
    void saveStudyData(research).then(()=>{
      setPersistError(!metadataSaved);
    }).catch(()=>setPersistError(true));
  },[research,researchReady]);
  React.useEffect(()=>saveSession('pantheralab_session_edge_events_v1',events),[events]);
  React.useEffect(()=>saveSession('pantheralab_camera_fire_events_v1',cameraFireEvents),[cameraFireEvents]);
  const onEvent=React.useCallback((event:EdgeEvent)=>
    setEvents(previous=>[event,...previous].slice(0,100)),[]);
  const onFireEvent=React.useCallback((event:CameraFireCandidate)=>
    setCameraFireEvents(previous=>[event,...previous].slice(0,30)),[]);
  const onUseEvent=(event:EdgeEvent)=>{
    setIncoming(event);
    onNavigate('PantheraMONITORING');
  };

  if(!researchReady){
    return section==='PantheraID'?null:<div className="sci-screen" role="status">
      <p className="sci-muted">{tx('Restaurando el archivo científico local…',
        'Restoring local scientific records…')}</p>
    </div>;
  }
  const sites=new Set(studyRecords.deployments.map(d=>d.site.trim()).filter(Boolean));
  const validated=new Set(studyRecords.sightings.filter(s=>s.identification_status==='verified'&&
    studyRecords.individuals.some(i=>i.individual_id===s.individual_id&&i.status==='verified'))
    .map(s=>s.individual_id)).size;
  return <>
    <div style={{display:section==='PantheraMONITORING'||section==='Informes'?'block':'none'}}>
      {persistError&&<p className="sci-warning" role="alert">{tx(
        'No fue posible guardar cambios en este navegador. Exportá un respaldo privado antes de salir.',
        'Could not save changes in this browser. Export a private backup before leaving.')}</p>}
      <ResearchRegistry data={research} setData={setResearch} pendingEdge={incoming}
        onClearEdge={()=>setIncoming(null)} pendingEvidence={pendingEvidence}
        onClearEvidence={onClearEvidence} reportsOnly={section==='Informes'}
        nextRequest={section==='PantheraMONITORING'?monitoringNextRequest:0}
        onWorkflowTabChange={onRegistryTabChange} onActiveStudyChange={setActiveStudyId}
        onNavigate={onNavigate}/>
      {section==='Informes'&&<details className="method-details method-details-compact scientific-advanced-tools">
        <summary>{tx('Laboratorio avanzado · informes de modelos externos',
          'Advanced laboratory · external model reports')}</summary>
        <AIResultsPanel />
      </details>}
    </div>
    <div style={{display:section==='PantheraLIVE'?'block':'none'}}>
      <EdgeWorkspace events={events} onEvent={onEvent} current={current}
        setCurrent={setCurrent} onUseEvent={onUseEvent}
        enabled={section==='PantheraLIVE'}/>
    </div>
    <div style={{display:section==='PantheraSENSE'?'block':'none'}}><SensePanel /></div>
    {section==='PantheraFIRE'&&<FireWorkspace cameraEvents={cameraFireEvents} onFireEvent={onFireEvent}/>}
    <div style={{display:section==='PantheraSAT'?'block':'none'}}>
      <ResearchWorkspace current={records[0]||current}/>
    </div>
    {section==='Resumen'&&<div className="sci-screen">
    <div className="sci-heading"><div><span className="sci-kicker">PANTHERA LAB / COMMAND OVERVIEW</span>
      <h2>{tx('Centro de control científico','Scientific control center')}</h2>
      <p>{tx('De la cámara trampa a la evidencia: captura, filtrado, contexto ambiental y revisión.',
        'From camera traps to evidence: capture, filtering, environmental context and review.')}</p>
    </div><span className="sci-tag">{tx('PANEL DE INVESTIGACIÓN','RESEARCH WORKSPACE')}</span></div>
    {activeStudy&&<p className="sci-muted">{tx('Estudio local activo: ','Active local study: ')}
      <strong>{activeStudy.title}</strong></p>}
    <div className="sci-stats">
      <div><span>{tx('Observaciones de animales','Animal sightings')}</span>
        <strong>{studyRecords.sightings.length}</strong></div>
      <div><span>{tx('Eventos de captura','Capture events')}</span><strong>{studyRecords.encounters.length}</strong></div>
      <div><span>{tx('Individuos validados','Verified individuals')}</span><strong>{validated}</strong></div>
      <div><span>{tx('Sitios anotados','Annotated study sites')}</span><strong>{sites.size}</strong></div>
    </div>
    <div className="sci-launch-grid">
      {([
        ['01','PantheraMONITORING',tx('Creá el estudio, cargá su biblioteca de individuos y prepará las estaciones.',
          'Create a study, prepare the individual reference library and register stations.')],
        ['02','PantheraLIVE',tx('Cámaras conectadas y eventos preliminares de campo.',
          'Connected cameras and preliminary field events.')],
        ['03','PantheraID',tx('Fotos y videos: comparar patrones y revisar evidencia.',
          'Photographs and video: compare patterns and review evidence.')],
        ['04','PantheraSENSE',tx('Sensores ambientales; simulaciones indicadas como tales.',
          'Environmental sensors, with simulations clearly identified.')],
        ['05','PantheraSAT',tx('Consultas satelitales y contexto territorial disponible.',
          'Satellite catalogues and available territorial context.')],
        ['06','Informes',tx('Informe científico PDF y tablas de datos del estudio.',
          'Scientific PDF report and study data tables.')],
      ] as [string,string,string][]).map(([number,module,description],index)=>
        <article className={'sci-launch sci-launch-'+['a','b','c','d'][index%4]} key={module}>
          <span className="sci-module-number">{number} / {tx('FLUJO CIENTÍFICO','SCIENTIFIC WORKFLOW')}</span>
          <h3>{module==='PantheraID'?'PantheraSCAN':module==='Informes'?
            tx('Informes científicos','Scientific reports'):module}</h3>
          <p>{description}</p>
          <button type="button" onClick={()=>onNavigate(module)}>
            {tx('Abrir módulo ↗','Open module ↗')}</button>
        </article>)}
    </div>
    <section className="sci-panel">
      <h3>{tx('Arquitectura de PantheraLAB','PantheraLAB architecture')}</h3>
      <div className="sci-pipeline">
        <div><span>01</span><strong>PantheraCAM</strong><small>{tx('Cámaras y sensores','Cameras and sensors')}</small></div>
        <b>→</b><div><span>02</span><strong>PantheraEDGE</strong><small>{tx('Filtro + eventos','Screening + events')}</small></div>
        <b>→</b><div><span>03</span><strong>5G / 4G</strong><small>{tx('Troncal estimada','Estimated trunk')}</small></div>
        <b>→</b><div><span>04</span><strong>PantheraLAB</strong><small>{tx('Datos y monitoreo','Data and monitoring')}</small></div>
        <b>→</b><div><span>05</span><strong>{tx('Instituciones','Institutions')}</strong>
          <small>{tx('Formatos exportables','Export formats')}</small></div>
      </div>
      <p className="sci-muted">{tx(
        'Arquitectura de referencia. La conexión a dispositivos físicos, la telemetría 5G y la persistencia en nube requieren habilitar sus respectivas integraciones.',
        'Reference architecture. Physical devices, 5G telemetry and cloud persistence require their respective integrations to be enabled.')}</p>
    </section>
  </div>}
  </>;
}
