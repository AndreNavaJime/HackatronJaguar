import React from 'react';
import {useLanguage} from './language';
import {EdgeEvent,Observation,apiJson,downloadFile,toCsv,loadSession,saveSession} from './scienceShared';
import CameraSourcesPanel from './CameraSourcesPanel';

type Props={events:EdgeEvent[];onEvent:(event:EdgeEvent)=>void;
  current:Observation;setCurrent:(record:Observation)=>void;
  onUseEvent?:(event:EdgeEvent)=>void;
  enabled:boolean;};

export default function EdgeWorkspace({events,onEvent,current,setCurrent,onUseEvent,enabled}:Props){
  const {language}=useLanguage();const tx=(es:string,en:string)=>language==='en'?en:es;
  const [rawJson,setRawJson]=React.useState('');
  const [remoteUrl,setRemoteUrl]=React.useState('');
  const [notice,setNotice]=React.useState('');
  const [reviewDecisions,setReviewDecisions]=React.useState<Record<string,'review'|'discard'>>(()=>{
    const stored=loadSession<unknown>('pantheralab_live_review_decisions_v1',{});
    if(!stored||typeof stored!=='object'||Array.isArray(stored))return {};
    return Object.fromEntries(Object.entries(stored).filter(([id,value])=>
      id.length<150&&(value==='review'||value==='discard'))) as Record<string,'review'|'discard'>;
  });
  React.useEffect(()=>{
    saveSession('pantheralab_live_review_decisions_v1',reviewDecisions);
  },[reviewDecisions]);
  const [busy,setBusy]=React.useState(false);
  const [showDiscarded,setShowDiscarded]=React.useState(false);
  const [networkSource,setNetworkSource]=React.useState<'reference'|'measured'>('reference');
  const [rawMB,setRawMB]=React.useState(8);
  const [filteredMB,setFilteredMB]=React.useState(1.2);
  const [throughput,setThroughput]=React.useState(20);
  const [latency,setLatency]=React.useState(25);
  const [fallbackThroughput,setFallbackThroughput]=React.useState(8);
  const [fallbackLatency,setFallbackLatency]=React.useState(60);

  async function ingest(body:unknown){
    setBusy(true);setNotice('');
    try{
      const data=await apiJson<{accepted:boolean;verification:string;event:EdgeEvent;saved:boolean}>(
        '/api/edge/validate','POST',body);
      onEvent(data.event);
      setNotice(tx('Evento incorporado a la sesión. HMAC: ','Event added to the session. HMAC: ')+data.verification+
        (data.verification==='NOT_CONFIGURED'?tx(' (no autenticado).',' (not authenticated).'):''));
    }catch(err){setNotice(err instanceof Error?err.message:String(err));}
    finally{setBusy(false);}
  }
  async function remote(){
    let url:URL;
    try{url=new URL(remoteUrl);if(url.protocol!=='https:')throw new Error(
      tx('Utilizá un endpoint HTTPS.','Use an HTTPS endpoint.'));}
    catch{setNotice(tx('Ingresá una URL HTTPS válida.','Enter a valid HTTPS URL.'));return;}
    setBusy(true);setNotice('');
    try{
      // Client-side only: prevents turning public FastAPI into an open URL proxy.
      const response=await fetch(url.toString(),{method:'GET',mode:'cors',credentials:'omit',
        headers:{'Accept':'application/json'}});
      if(!response.ok)throw new Error('HTTP '+response.status);
      const body=await response.text();
      if(body.length>7500)throw new Error(tx('Evento demasiado grande.','Event too large.'));
      setRawJson(JSON.stringify(JSON.parse(body),null,2));
      setNotice(tx('JSON recibido. Revisá su contenido y seleccioná «Validar JSON».',
        'JSON received. Review it and select “Validate JSON”.'));
    }catch(err){setNotice(tx('No se pudo consultar el endpoint desde el navegador (puede requerir CORS). ',
      'Browser request failed (endpoint may require CORS). ')+(err instanceof Error?err.message:String(err)));}
    finally{setBusy(false);}
  }
  const transfer=(mb:number,mbps:number,rtt:number)=>(Math.max(0,mb)*8/Math.max(.1,mbps)+Math.max(0,rtt)/1000);
  const rawSec=transfer(rawMB,throughput,latency);
  const edgeSec=transfer(filteredMB,throughput,latency);
  const fourGSec=transfer(filteredMB,fallbackThroughput,fallbackLatency);
  const avoided=Math.max(0,rawMB-filteredMB);
  const reduction=rawMB>0?Math.max(0,100*avoided/rawMB):0;

  const cameraCandidate=(event:EdgeEvent)=>
    event.source==='camera_virtual_simulation'||event.source==='browser_camera_megadetector_opt_in'
    ||event.class==='person';
  const visibleEvents=events.filter(event=>showDiscarded||reviewDecisions[event.event_id]!=='discard');
  const discardedCount=events.filter(event=>reviewDecisions[event.event_id]==='discard').length;
  const pendingCount=events.filter(event=>cameraCandidate(event)&&!reviewDecisions[event.event_id]).length;
  const displayedTime=(iso:string)=>{
    const parsed=new Date(iso);
    return Number.isNaN(parsed.getTime())?iso:parsed.toLocaleString(language==='en'?'en-US':'es-CR',
      {dateStyle:'short',timeStyle:'short'});
  };
  const numberInput=(label:string,value:number,setter:(n:number)=>void,min:number,max:number,unit:string)=>
    <label className="sci-field"><span>{label} ({unit})</span>
      <input type="number" step="any" min={min} max={max} value={value}
        onChange={e=>{const v=Number(e.target.value);if(Number.isFinite(v)&&v>=min&&v<=max)setter(v);}}/>
    </label>;

  return <div className="sci-screen">
    <div className="sci-heading"><div><span className="sci-kicker">PANTHERALIVE / PANTHERAEDGE ENGINE / 5G</span>
      <h2>{tx('PantheraLIVE · Cámaras y conectividad','PantheraLIVE · Camera events and connectivity')}</h2>
      <p>{tx('Conectá una cámara y revisá detecciones de fauna o personas.',
        'Connect a camera and review wildlife or person detections.')}</p></div>
      <span className="sci-tag">{tx('EVENTOS DE CAMPO','FIELD EVENTS')}</span></div>
    <CameraSourcesPanel enabled={enabled} onEvent={onEvent}/>

    {notice&&<p className="sci-notice" role="status">{notice}</p>}

    <section className="sci-panel live-events">
      <div className="sci-panel-head">
        <h3>{tx('Eventos por revisar','Events for review')}</h3>
        <span className="sci-tag">{pendingCount} {tx('pendientes','pending')}</span>
      </div>
      {discardedCount>0&&<label className="live-show-discarded">
        <input type="checkbox" checked={showDiscarded} onChange={e=>setShowDiscarded(e.target.checked)}/>
        {tx('Mostrar descartados','Show dismissed')} ({discardedCount})
      </label>}
      {visibleEvents.length===0?<p className="sci-muted">
        {events.length===0
          ?tx('Los eventos aparecerán aquí al conectar una cámara o iniciar la demostración.',
            'Events appear here after connecting a camera or starting the demo.')
          :tx('No hay eventos pendientes en pantalla. Podés mostrar los descartados.',
            'No pending events on screen. You can show dismissed ones.')}</p>
      :<div className="live-event-list">
        {visibleEvents.map((event,i)=>{
          const candidate=cameraCandidate(event);
          const simulated=event.source==='camera_virtual_simulation';
          const label=event.class==='person'?tx('Persona','Person'):
            event.class==='animal'?tx('Posible animal','Possible animal'):
            tx('Evento recibido','Incoming event');
          const decision=reviewDecisions[event.event_id];
          return <article className="live-event-card" key={event.event_id+'-'+i}>
            <div className="live-event-main">
              <div className="live-event-heading">
                <strong>{label}</strong>
                <span className={'live-event-badge'+(simulated?' simulation':'')}>
                  {simulated?tx('SIMULACIÓN','SIMULATION'):candidate?tx('SIN VALIDAR','UNVERIFIED'):tx('IMPORTADO','IMPORTED')}
                </span>
              </div>
              <div className="live-event-meta">
                <span>{event.camera_id}</span>
                <span>{displayedTime(event.timestamp)}</span>
                {typeof event.confidence==='number'&&event.confidence>0&&
                  <span>{Math.round(event.confidence*100)}% {tx('del detector','detector score')}</span>}
              </div>
              {decision&&<span className="live-event-decision">
                {decision==='review'?tx('Marcado para revisión científica','Flagged for scientific review'):
                  tx('Descartado de la bandeja','Dismissed from queue')}
              </span>}
            </div>
            <div className="live-event-actions">
              {candidate?<>
                <button type="button" className="sci-secondary" disabled={decision==='review'}
                  onClick={()=>setReviewDecisions(v=>({...v,[event.event_id]:'review'}))}>
                  {tx('Marcar para revisión','Flag for review')}</button>
                <button type="button" className="sci-secondary" disabled={decision==='discard'}
                  onClick={()=>setReviewDecisions(v=>({...v,[event.event_id]:'discard'}))}>
                  {tx('Descartar','Dismiss')}</button>
                {decision&&<button type="button" className="sci-inline"
                  onClick={()=>setReviewDecisions(v=>{
                    const next={...v};delete next[event.event_id];return next;
                  })}>{tx('Restablecer','Reset')}</button>}
              </>:<button type="button" className="sci-secondary" onClick={()=>{
                setCurrent({...current,camera_id:event.camera_id,
                  camera_latitude:event.latitude,camera_longitude:event.longitude,
                  altitude_m:event.altitude,temperature_c:event.temperature,
                  humidity_percent:event.humidity,edge_event_id:event.event_id});
                onUseEvent?.(event);
                setNotice(tx('Metadatos enviados a MONITORING para revisión.',
                  'Metadata sent to MONITORING for review.'));
              }}>{tx('Revisar en MONITORING','Review in MONITORING')}</button>}
            </div>
          </article>;
        })}
      </div>}
      {events.length>0&&<details className="method-details edge-exports">
        <summary>{tx('Exportar eventos · JSON / CSV','Export events · JSON / CSV')}</summary>
        <div className="sci-actions">
          <button type="button" className="sci-secondary" onClick={()=>downloadFile('PantheraEDGE_eventos.json',
            JSON.stringify(events.map(event=>({...event,
              manual_review:reviewDecisions[event.event_id]||'not_reviewed',
              species_verified:false})),null,2),'application/json')}>JSON ↓</button>
          <button type="button" className="sci-secondary" onClick={()=>downloadFile('PantheraEDGE_eventos.csv',
            toCsv(events.map(event=>({...event,
              manual_review:reviewDecisions[event.event_id]||'not_reviewed'})) as Record<string,unknown>[]),'text/csv')}>CSV ↓</button>
        </div>
      </details>}
      <p className="sci-muted live-event-note">{tx(
        'Los eventos virtuales son ficticios; los de IA requieren validación. No se guardan clips ni se acusa a personas automáticamente.',
        'Virtual events are fictional; AI events need validation. No clips are stored or people automatically accused.')}</p>
    </section>

      <details className="sci-panel edge-advanced"><summary>{tx('Integración técnica · JSON / nodos','Technical integration · JSON / nodes')}</summary>
      <section>
        <div className="sci-panel-head"><h3>{tx('Puente HTTP / Wokwi / nodo de campo','HTTP bridge / Wokwi / field node')}</h3>
          <span className="sci-tag">JSON · HTTP</span></div>
        <label className="sci-field"><span>{tx('Endpoint HTTPS del nodo (opcional)','Node HTTPS endpoint (optional)')}</span>
          <input type="url" value={remoteUrl} onChange={e=>setRemoteUrl(e.target.value)}
            placeholder="https://example.org/api/latest-event"/></label>
        <button type="button" className="sci-secondary" disabled={busy||!remoteUrl.trim()}
          onClick={()=>void remote()}>{tx('Consultar endpoint desde navegador','Fetch endpoint in browser')}</button>
        <label className="sci-field"><span>{tx('JSON del evento','Event JSON')}</span>
          <textarea rows={7} value={rawJson} onChange={e=>setRawJson(e.target.value)}
            placeholder='{"event_id":"EDGE-01","camera_id":"CT-07","temperature":24.5}'/></label>
        <button type="button" className="action-button" disabled={busy||!rawJson.trim()} onClick={()=>{
          try{const obj=JSON.parse(rawJson);void ingest(obj);}
          catch{setNotice(tx('JSON inválido; corregí su sintaxis.','Invalid JSON; correct its syntax.'));}
        }}>{tx('Validar JSON e incorporar evento','Validate JSON and add event')}</button>
      </section></details>

    <details className="sci-panel edge-network-details">
      <summary>{tx('Comparación técnica · 5G / 4G','Technical comparison · 5G / 4G')}</summary>
      <div className="edge-network-body">
        <p className="sci-muted">{tx('Escenarios de referencia, no velocidades medidas.',
          'Reference scenarios, not measured speeds.')}</p>
      <div className="sci-switch" role="group" aria-label={tx('Fuente de datos','Data source')}>
        <button type="button" className={networkSource==='reference'?'selected':''}
          onClick={()=>setNetworkSource('reference')}>{tx('Supuestos de referencia','Reference assumptions')}</button>
        <button type="button" className={networkSource==='measured'?'selected':''}
          onClick={()=>setNetworkSource('measured')}>{tx('Ingresar valores medidos','Enter measured inputs')}</button>
      </div>
      <p className="sci-warning">{networkSource==='reference'
        ?tx('Escenario calculado con parámetros de referencia; no corresponde a telemetría de red.',
          'Scenario calculated from reference inputs, not network telemetry.')
        :tx('Valores aportados por el usuario; su procedencia debe verificarse antes de utilizarlos en informes.',
          'User-provided values; verify their source before using them in reports.')}</p>
      <details className="method-details edge-advanced"><summary>{tx('Parámetros avanzados · velocidades y latencias','Advanced parameters · speeds and latency')}</summary><div className="sci-fields">
        {numberInput(tx('Entrada sin filtrar','Unfiltered input'),rawMB,setRawMB,0,1000,'MB')}
        {numberInput(tx('Payload filtrado','Filtered payload'),filteredMB,setFilteredMB,0,1000,'MB')}
        {numberInput('5G uplink',throughput,setThroughput,.1,1000,'Mbps')}
        {numberInput(tx('Latencia de referencia 5G','5G reference latency'),latency,setLatency,0,1000,'ms')}
        {numberInput('4G uplink',fallbackThroughput,setFallbackThroughput,.1,500,'Mbps')}
        {numberInput(tx('Latencia de referencia 4G','4G reference latency'),fallbackLatency,setFallbackLatency,0,1000,'ms')}
      </div></details>
      <div className="sci-stats">
        <div><span>{tx('Transferencia original (5G)','Original transfer (5G)')}</span><strong>{rawSec.toFixed(3)} s</strong></div>
        <div><span>{tx('Filtrado (5G)','Filtered (5G)')}</span><strong>{edgeSec.toFixed(3)} s</strong></div>
        <div><span>{tx('Filtrado (4G)','Filtered (4G)')}</span><strong>{fourGSec.toFixed(3)} s</strong></div>
        <div><span>{tx('Reducción de bytes estimada','Estimated payload reduction')}</span><strong>{reduction.toFixed(1)}%</strong></div>
      </div>
      <p className="sci-muted">{tx('Tráfico evitado en el escenario: ','Traffic avoided in scenario: ')}
        <strong>{avoided.toFixed(3)} MB</strong>. {tx(
          'Estos resultados NO miden tráfico real de la red ni prueban ahorro efectivo 5G.',
          'These results do NOT measure actual network traffic or prove realized 5G savings.')}</p>
      <details className="method-details edge-exports"><summary>{tx('Exportar modelo técnico · JSON','Export technical model · JSON')}</summary><button type="button" className="sci-secondary" onClick={()=>downloadFile('PantheraEDGE_estimacion_5G.json',
        JSON.stringify({source:networkSource,rawMB,filteredMB,throughput_mbps:throughput,latency_ms:latency,
          fallback4g_mbps:fallbackThroughput,fallback4g_latency_ms:fallbackLatency,
          estimated_raw_seconds:rawSec,estimated_filtered_5g_seconds:edgeSec,
          estimated_filtered_4g_seconds:fourGSec,estimated_payload_reduction:reduction,
          measured_network_kpis:false},null,2),'application/json')}>JSON ↓</button></details>
      </div>
    </details>
  </div>;
}
