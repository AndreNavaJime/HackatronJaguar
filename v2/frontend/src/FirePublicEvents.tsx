import React from 'react';
import {apiFetch} from './apiClient';
import {useLanguage} from './language';
import './FirePublicEvents.css';

type Region='world'|'africa'|'asia'|'europe'|'north_america'|'central_america'|'south_america'|'oceania'|'costa_rica';
type NasaFireEvent={
  id:string;
  title:string;
  reported_at:string|null;
  open_in_catalogue:boolean;
  sources:string[];
  reference_url:string;
};
type FireEventsResponse={
  source:'NASA EONET API v3';
  type:'reported_wildfire_events_not_active_fire_detections';
  region:Region;
  days:number;
  queried_at_utc:string;
  count_returned:number;
  events:NasaFireEvent[];
  limitations:string;
};
const NAMES:Record<Region,[string,string]>={
  world:['Mundo','World'],
  africa:['África','Africa'],
  asia:['Asia','Asia'],
  europe:['Europa','Europe'],
  north_america:['América del Norte','North America'],
  south_america:['América del Sur','South America'],
  oceania:['Oceanía','Oceania'],
  central_america:['Centroamérica','Central America'],
  costa_rica:['Costa Rica','Costa Rica'],
};

export default function FirePublicEvents(){
  const {language}=useLanguage();
  const tx=(es:string,en:string)=>language==='en'?en:es;
  const [region,setRegion]=React.useState<Region>('world');
  const [days,setDays]=React.useState(30);
  const [loading,setLoading]=React.useState(false);
  const [data,setData]=React.useState<FireEventsResponse|null>(null);
  const [error,setError]=React.useState('');
  const [reload,setReload]=React.useState(0);
  React.useEffect(()=>{
    const controller=new AbortController();
    let active=true;
    setLoading(true);setError('');setData(null);
    async function query(){
      try{
        const response=await apiFetch('/api/fire/nasa-events?region='+region+'&days='+days,
          {signal:controller.signal,cache:'no-store'});
        if(!response.ok){
          let explanation='';
          try{
            const body=await response.json();
            if(typeof body?.detail==='string')explanation=body.detail;
          }catch{/* Non-JSON error responses are reported with status. */}
          throw Error(explanation||'NASA EONET HTTP '+response.status);
        }
        const result=await response.json() as FireEventsResponse;
        if(result.source!=='NASA EONET API v3'||
          result.type!=='reported_wildfire_events_not_active_fire_detections'||
          !Array.isArray(result.events))throw Error('Unexpected external data format');
        if(active)setData(result);
      }catch(e){
        if(active&&!controller.signal.aborted)setError(e instanceof Error?e.message:String(e));
      }finally{if(active)setLoading(false);}
    }
    void query();
    return ()=>{active=false;controller.abort();};
  },[region,days,reload]);

  return <section className="fire-card nasa-fire-events" aria-label={tx(
    'Eventos de incendios reportados por NASA','Wildfire events reported by NASA')}>
    <div className="sci-panel-head">
      <div><span className="fire-kicker">NASA EONET / {tx('FUENTE PÚBLICA','PUBLIC DATA')}</span>
        <h3>{tx('Incendios forestales reportados','Reported wildfire events')}</h3></div>
      <span className="fire-pill">{tx('DATOS EXTERNOS REALES','REAL EXTERNAL REPORTS')}</span>
    </div>
    <p>{tx(
      'Consultá reportes de incendios del catálogo público NASA EONET por continente o región. Las regiones utilizan áreas geográficas aproximadas, no fronteras políticas. Son eventos publicados por fuentes externas, no detecciones de una cámara PantheraFIRE ni píxeles térmicos de NASA FIRMS.',
      'Browse public wildfire event reports catalogued by NASA EONET by continent or region. Geographic areas are approximate, not political boundaries. These are externally reported events, not PantheraFIRE camera detections or NASA FIRMS thermal hotspots.'
    )}</p>
    <div className="nasa-fire-controls">
      <label className="sci-field"><span>{tx('Región del catálogo','Catalogue region')}</span>
        <select value={region} onChange={e=>setRegion(e.target.value as Region)}>
          {(Object.keys(NAMES) as Region[]).map(key=>
            <option key={key} value={key}>{NAMES[key][language==='en'?1:0]}</option>)}
        </select>
      </label>
      <label className="sci-field"><span>{tx('Periodo','Lookback')}</span>
        <select value={days} onChange={e=>setDays(Number(e.target.value))}>
          <option value={7}>{tx('Últimos 7 días','Last 7 days')}</option>
          <option value={30}>{tx('Últimos 30 días','Last 30 days')}</option>
          <option value={90}>{tx('Últimos 90 días','Last 90 days')}</option>
        </select>
      </label>
      <button type="button" className="sci-secondary" disabled={loading}
        onClick={()=>setReload(v=>v+1)}>{loading?tx('Consultando…','Loading…'):
          tx('Actualizar catálogo','Refresh catalogue')}</button>
    </div>
    {error&&<p role="alert" className="sci-warning">
      {tx('No se pudo consultar NASA EONET: ','Could not retrieve NASA EONET: ')}{error}
      {' '}{tx('No significa que no existan incendios.','This does not mean no fires exist.')}</p>}
    {loading&&<p role="status" className="sci-muted">{tx(
      'Consultando eventos reales publicados por NASA…','Fetching real events published by NASA…')}</p>}
    {data&&!loading&&<>
      <div className="nasa-fire-meta">
        <strong>{data.count_returned} {tx('eventos devueltos por la consulta','catalogued events returned')}</strong>
        <small>{tx('Consulta','Query')} · {new Date(data.queried_at_utc).toLocaleString(
          language==='en'?'en-US':'es-CR')}</small>
      </div>
      {data.events.length===0?<p className="sci-muted">{tx(
        'No aparecen eventos para esta selección. Esto NO significa que la región esté libre de incendios: EONET no es un catálogo exhaustivo de detecciones.',
        'No events returned for these filters. This does NOT mean the area is fire-free: EONET is not an exhaustive fire detection catalogue.'
      )}</p>:
        <div className="nasa-fire-list">{data.events.slice(0,40).map(event=>
          <article className="nasa-fire-entry" key={event.id}>
            <div className="nasa-fire-entry-head">
              <strong>{event.title}</strong>
              <span className="fire-pill">{event.open_in_catalogue
                ?tx('ABIERTO EN CATÁLOGO','OPEN IN CATALOGUE')
                :tx('CERRADO EN CATÁLOGO','CLOSED IN CATALOGUE')}</span>
            </div>
            <small>{event.reported_at?new Date(event.reported_at).toLocaleDateString(
              language==='en'?'en-US':'es-CR'):tx('Fecha no disponible','Date unavailable')}
              {event.sources.length?' · '+event.sources.join(', '):''}</small>
            <a href={event.reference_url} target="_blank" rel="noopener noreferrer">
              {tx('Ver ficha de NASA EONET ↗','Open NASA EONET event ↗')}</a>
          </article>)}</div>}
      {data.events.length>40&&<p className="sci-muted">{tx(
        'Se muestran los primeros 40 eventos de la consulta. Para el catálogo completo, consultá NASA EONET.',
        'Showing the first 40 results. See NASA EONET for the full catalogue.')}</p>}
    </>}
    <div className="fire-note">{tx(
      'No es un sistema de alerta temprana ni confirma incendios cerca de tu cámara. Los reportes pueden estar incompletos o retrasados y el estado «abierto» es administrativo. No se envían notificaciones de emergencias.',
      'Not an early-warning system and does not confirm fires near your camera. Reports may be incomplete or delayed, and “open” is a catalogue status. No emergency alerts are dispatched.'
    )}</div>
    <div className="nasa-fire-links">
      <a href="https://eonet.gsfc.nasa.gov/" target="_blank" rel="noopener noreferrer">
        NASA EONET ↗</a>
      <a href="https://firms.modaps.eosdis.nasa.gov/map/" target="_blank" rel="noopener noreferrer">
        {tx('NASA FIRMS · mapa de focos térmicos ↗','NASA FIRMS · thermal hotspot map ↗')}</a>
    </div>
  </section>;
}
