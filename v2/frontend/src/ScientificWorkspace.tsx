import React from 'react';
import ResearchRegistry from './ResearchRegistry';
import EdgeWorkspace from './EdgeWorkspace';
import SensePanel from './SensePanel';
import FireWorkspace from './FireWorkspace';
import ResearchWorkspace from './ResearchWorkspace';
import ScientificRecordsPanel from './ScientificRecordsPanel';
import {useLanguage} from './language';
import {Observation,EdgeEvent,newObservation,loadSession,saveSession} from './scienceShared';
import {ResearchData,loadResearch,persistResearch,flattenObservations} from './researchData';
import {readStudyData,saveStudyData} from './researchDb';
import type {CameraFireCandidate} from './cameraEvents';

import type {VideoEvidenceBatch} from './videoWorkspaceDb';
type Props={section:string;onNavigate:(section:string)=>void;
  pendingEvidence?:VideoEvidenceBatch|null;onClearEvidence?:()=>void;
  monitoringNextRequest?:number;
  onRegistryTabChange?:(tab:'projects'|'stations'|'captures'|'individuals'|'reports')=>void;
  requestReport?:number;};

export default function ScientificWorkspace({section,onNavigate,pendingEvidence,onClearEvidence,
  monitoringNextRequest=0,onRegistryTabChange,requestReport=0}:Props){
  const {language}=useLanguage(),tx=(es:string,en:string)=>language==='en'?en:es;
  const [research,setResearch]=React.useState<ResearchData>(loadResearch);
  const [persistError,setPersistError]=React.useState(false);
  const [researchReady,setResearchReady]=React.useState(false);
  const [events,setEvents]=React.useState<EdgeEvent[]>(()=>{
    const value=loadSession<unknown>('pantheralab_session_edge_events_v1',[]);
    return Array.isArray(value)?value as EdgeEvent[]:[];
  });
  const [current,setCurrent]=React.useState<Observation>(()=>newObservation());
  const [incoming,setIncoming]=React.useState<EdgeEvent|null>(null);
  const [openReport,setOpenReport]=React.useState(false);
  const [cameraFireEvents,setCameraFireEvents]=React.useState<CameraFireCandidate[]>(()=>{
    const stored=loadSession<unknown>('pantheralab_camera_fire_events_v1',[]);
    return Array.isArray(stored)?stored.filter((v):v is CameraFireCandidate=>
      typeof v==='object'&&v!==null&&v.simulation===true&&
      (v.signal==='smoke'||v.signal==='flame')).slice(0,30):[];
  });
  React.useEffect(()=>{
    if(requestReport){setOpenReport(true);onNavigate('PantheraMONITORING');}
  },[requestReport]);
  const records=React.useMemo(()=>flattenObservations(research),[research]);

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
  const openFire=React.useCallback(()=>onNavigate('PantheraFIRE'),[onNavigate]);
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
  const sites=new Set(research.deployments.map(d=>d.site.trim()).filter(Boolean));
  const validated=new Set(research.sightings.filter(s=>s.identification_status==='verified'&&
    research.individuals.some(i=>i.individual_id===s.individual_id&&i.status==='verified'))
    .map(s=>s.individual_id)).size;
  return <>
    <div style={{display:section==='PantheraMONITORING'?'block':'none'}}>
      {persistError&&<p className="sci-warning" role="alert">{tx(
        'No fue posible guardar cambios en este navegador. Exportá un respaldo privado antes de salir.',
        'Could not save changes in this browser. Export a private backup before leaving.')}</p>}
      <ResearchRegistry data={research} setData={setResearch} pendingEdge={incoming}
        onClearEdge={()=>setIncoming(null)} pendingEvidence={pendingEvidence}
        onClearEvidence={onClearEvidence} reportRequested={openReport}
        onClearReportRequest={()=>setOpenReport(false)}
        nextRequest={monitoringNextRequest} onWorkflowTabChange={onRegistryTabChange}
        onNavigate={onNavigate}/>
    </div>
    <div style={{display:section==='PantheraMONITORING'?'block':'none'}}>
      <ScientificRecordsPanel records={records} onOpenReports={()=>setOpenReport(true)}/>
    </div>
    <div style={{display:section==='PantheraLIVE'?'block':'none'}}>
      <EdgeWorkspace events={events} onEvent={onEvent} current={current}
        setCurrent={setCurrent} onUseEvent={onUseEvent}
        enabled={section==='PantheraLIVE'} onFireEvent={onFireEvent} onOpenFire={openFire}/>
    </div>
    <div style={{display:section==='PantheraSENSE'?'block':'none'}}><SensePanel /></div>
    {section==='PantheraFIRE'&&<FireWorkspace cameraEvents={cameraFireEvents} onOpenLive={()=>onNavigate('PantheraLIVE')}/>}
    <div style={{display:section==='PantheraSAT'?'block':'none'}}>
      <ResearchWorkspace current={records[0]||current}/>
    </div>
    {section==='Resumen'&&<div className="sci-screen">
    <div className="sci-heading"><div><span className="sci-kicker">PANTHERA LAB / COMMAND OVERVIEW</span>
      <h2>{tx('Centro de control científico','Scientific control center')}</h2>
      <p>{tx('De la cámara trampa a la evidencia: captura, filtrado, contexto ambiental y revisión.',
        'From camera traps to evidence: capture, filtering, environmental context and review.')}</p>
    </div><span className="sci-tag">{tx('PANEL DE INVESTIGACIÓN','RESEARCH WORKSPACE')}</span></div>
    <div className="sci-stats">
      <div><span>{tx('Observaciones de animales','Animal sightings')}</span>
        <strong>{research.sightings.length}</strong></div>
      <div><span>{tx('Eventos de captura','Capture events')}</span><strong>{research.encounters.length}</strong></div>
      <div><span>{tx('Individuos validados','Verified individuals')}</span><strong>{validated}</strong></div>
      <div><span>{tx('Sitios anotados','Annotated study sites')}</span><strong>{sites.size}</strong></div>
    </div>
    <div className="sci-launch-grid">
      <article className="sci-launch sci-launch-a">
        <span className="sci-module-number">01 / MULTIMEDIA</span>
        <h3>PantheraID</h3>
        <p>{tx('Carga de fotografías y videos, preselección de fotogramas con OpenCV y exportación de evidencia.',
          'Photo/video uploads, OpenCV frame screening and evidence exports.')}</p>
        <small>{tx('Análisis de secuencias · OpenCV','Sequence analysis · OpenCV')}</small>
        <button type="button" onClick={()=>onNavigate('PantheraID')}>{tx('Abrir identificación ↗','Open identification ↗')}</button>
      </article>
      <article className="sci-launch sci-launch-b">
        <span className="sci-module-number">02 / SCIENTIFIC RECORDS</span>
        <h3>PantheraMONITORING</h3>
        <p>{tx('Estudios, estaciones, catálogo de jaguares, encuentros y reportes científicos integrales.',
          'Studies, deployments, jaguar catalogue, encounters and consolidated reports.')}</p>
        <small>{tx('Catálogo de individuos · PDF / ZIP','Individual catalogue · PDF / ZIP')}</small>
        <button type="button" onClick={()=>onNavigate('PantheraMONITORING')}>
          {tx('Abrir monitoreo ↗','Open monitoring ↗')}</button>
      </article>
      <article className="sci-launch sci-launch-c">
        <span className="sci-module-number">03 / FIELD EVENTS</span>
        <h3>PantheraLIVE</h3>
        <p>{tx('Cámara virtual automática, conexión de webcam autorizada, eventos JSON y comparación ilustrativa de redes.',
          'Automatic virtual camera, opt-in device preview, JSON event intake and illustrative network models.')}</p>
        <small>{tx('Eventos de campo · HTTP / JSON','Field events · HTTP / JSON')}</small>
        <button type="button" onClick={()=>onNavigate('PantheraLIVE')}>
          {tx('Abrir Live ↗','Open Live ↗')}</button>
      </article>
      <article className="sci-launch sci-launch-d">
        <span className="sci-module-number">04 / EARTH OBSERVATION</span>
        <h3>PantheraSAT</h3>
        <p>{tx('Búsquedas reales en el catálogo Copernicus Sentinel-1/2, vegetación y Starlink.',
          'Real Copernicus Sentinel-1/2 catalogue queries, vegetation and Starlink.')}</p>
        <small>{tx('Catálogo de adquisiciones · Sentinel-1/2','Acquisition catalogue · Sentinel-1/2')}</small>
        <button type="button" onClick={()=>onNavigate('PantheraSAT')}>
          {tx('Abrir satélites ↗','Open satellites ↗')}</button>
      </article>
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
