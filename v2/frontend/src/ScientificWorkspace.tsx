import React from 'react';
import MonitoringWorkspace from './MonitoringWorkspace';
import EdgeWorkspace from './EdgeWorkspace';
import ResearchWorkspace from './ResearchWorkspace';
import {useLanguage} from './language';
import {Observation,EdgeEvent,newObservation,loadSession,saveSession} from './scienceShared';

type Props={section:string;onNavigate:(section:string)=>void};

export default function ScientificWorkspace({section,onNavigate}:Props){
  const {language}=useLanguage(),tx=(es:string,en:string)=>language==='en'?en:es;
  const [records,setRecords]=React.useState<Observation[]>(()=>{
    const value=loadSession<unknown>('pantheralab_session_observations_v1',[]);
    return Array.isArray(value)?value as Observation[]:[];
  });
  const [events,setEvents]=React.useState<EdgeEvent[]>(()=>{
    const value=loadSession<unknown>('pantheralab_session_edge_events_v1',[]);
    return Array.isArray(value)?value as EdgeEvent[]:[];
  });
  const [current,setCurrent]=React.useState<Observation>(()=>newObservation());

  React.useEffect(()=>saveSession('pantheralab_session_observations_v1',records),[records]);
  React.useEffect(()=>saveSession('pantheralab_session_edge_events_v1',events),[events]);

  const onSave=(record:Observation)=>setRecords(previous=>{
    const index=previous.findIndex(r=>r.observation_id===record.observation_id);
    if(index<0)return [record,...previous].slice(0,250);
    return previous.map(r=>r.observation_id===record.observation_id?record:r);
  });
  const onRemove=(id:string)=>setRecords(previous=>previous.filter(o=>o.observation_id!==id));
  const onEvent=(event:EdgeEvent)=>setEvents(previous=>[event,...previous].slice(0,100));

  if(section==='PantheraMONITORING'){
    return <MonitoringWorkspace records={records} current={current} setCurrent={setCurrent}
      onSave={onSave} onRemove={onRemove} events={events}/>;
  }
  if(section==='PantheraEDGE'){
    return <EdgeWorkspace events={events} onEvent={onEvent} current={current} setCurrent={setCurrent}/>;
  }
  if(section==='Investigación'){
    return <ResearchWorkspace records={records} current={current}/>;
  }
  if(section!=='Resumen')return null;

  const sites=new Set(records.map(r=>r.study_site.trim()).filter(Boolean));
  const validated=records.filter(r=>r.validation_status==='researcher_validated'||
    r.validation_status==='field_verified').length;
  return <div className="sci-screen">
    <div className="sci-heading"><div><span className="sci-kicker">PANTHERA LAB / COMMAND OVERVIEW</span>
      <h2>{tx('Centro de control científico','Scientific control center')}</h2>
      <p>{tx('De la cámara trampa a la evidencia: captura, filtrado, contexto ambiental y revisión.',
        'From camera traps to evidence: capture, filtering, environmental context and review.')}</p>
    </div><span className="sci-tag">{tx('PANEL DE INVESTIGACIÓN','RESEARCH WORKSPACE')}</span></div>
    <div className="sci-stats">
      <div><span>{tx('Observaciones en esta sesión','Observations in this session')}</span>
        <strong>{records.length}</strong></div>
      <div><span>{tx('Eventos Edge recibidos','Edge events received')}</span><strong>{events.length}</strong></div>
      <div><span>{tx('Registros con validación humana','Human-validated records')}</span><strong>{validated}</strong></div>
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
        <p>{tx('Fichas científicas, variables ambientales, mapa de cámara, historial temporal e informes PDF.',
          'Scientific records, environmental fields, camera maps, temporary history and PDF reports.')}</p>
        <small>{tx('Observaciones · PDF / GeoJSON','Observations · PDF / GeoJSON')}</small>
        <button type="button" onClick={()=>onNavigate('PantheraMONITORING')}>
          {tx('Abrir monitoreo ↗','Open monitoring ↗')}</button>
      </article>
      <article className="sci-launch sci-launch-c">
        <span className="sci-module-number">03 / FIELD EVENTS</span>
        <h3>PantheraEDGE</h3>
        <p>{tx('Simulación PantheraCAM, validación de eventos JSON y cálculos ilustrativos de transferencia 4G/5G.',
          'PantheraCAM simulation, JSON event validation and illustrative 4G/5G transfer calculations.')}</p>
        <small>{tx('Eventos de campo · HTTP / JSON','Field events · HTTP / JSON')}</small>
        <button type="button" onClick={()=>onNavigate('PantheraEDGE')}>
          {tx('Abrir Edge ↗','Open Edge ↗')}</button>
      </article>
      <article className="sci-launch sci-launch-d">
        <span className="sci-module-number">04 / EARTH OBSERVATION</span>
        <h3>{tx('Investigación','Research')}</h3>
        <p>{tx('Búsquedas reales en el catálogo Copernicus Sentinel-1/2, exportaciones CSV, JSON y GeoJSON.',
          'Real Copernicus Sentinel-1/2 catalogue queries and CSV, JSON and GeoJSON exports.')}</p>
        <small>{tx('Catálogo de adquisiciones · Sentinel-1/2','Acquisition catalogue · Sentinel-1/2')}</small>
        <button type="button" onClick={()=>onNavigate('Investigación')}>
          {tx('Abrir investigación ↗','Open research ↗')}</button>
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
  </div>;
}
