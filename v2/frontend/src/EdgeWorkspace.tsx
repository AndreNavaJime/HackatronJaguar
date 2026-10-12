import React from 'react';
import {useLanguage} from './language';
import {EdgeEvent,Observation,apiJson,downloadFile,toCsv} from './scienceShared';

type Props={events:EdgeEvent[];onEvent:(event:EdgeEvent)=>void;
  current:Observation;setCurrent:(record:Observation)=>void};

export default function EdgeWorkspace({events,onEvent,current,setCurrent}:Props){
  const {language}=useLanguage();const tx=(es:string,en:string)=>language==='en'?en:es;
  const [camera,setCamera]=React.useState('CAM-DEMO-01');
  const [latitude,setLatitude]=React.useState('');
  const [longitude,setLongitude]=React.useState('');
  const [temperature,setTemperature]=React.useState('');
  const [humidity,setHumidity]=React.useState('');
  const [rawJson,setRawJson]=React.useState('');
  const [remoteUrl,setRemoteUrl]=React.useState('');
  const [notice,setNotice]=React.useState('');
  const [busy,setBusy]=React.useState(false);
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
  const demo=()=>({
    contract_version:'panthera-v1.0',
    event_id:'EDGE-DEMO-'+Date.now().toString(36).toUpperCase(),
    timestamp:new Date().toISOString(),camera_id:camera||'CAM-DEMO-01',
    event:'new_capture',status:'RECEIVED',
    source:'PantheraCAM local simulator',transport:'Wi-Fi 2.4 / LoRa demo',
    latitude:latitude.trim()===''?null:Number(latitude),
    longitude:longitude.trim()===''?null:Number(longitude),
    environment:{temperature:temperature.trim()===''?null:Number(temperature),
      humidity:humidity.trim()===''?null:Number(humidity)},
  });
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

  const numberInput=(label:string,value:number,setter:(n:number)=>void,min:number,max:number,unit:string)=>
    <label className="sci-field"><span>{label} ({unit})</span>
      <input type="number" step="any" min={min} max={max} value={value}
        onChange={e=>{const v=Number(e.target.value);if(Number.isFinite(v)&&v>=min&&v<=max)setter(v);}}/>
    </label>;

  return <div className="sci-screen">
    <div className="sci-heading"><div><span className="sci-kicker">PANTHERAEDGE / LOCAL REFLEX / 5G</span>
      <h2>{tx('PantheraEDGE · Eventos y conectividad','PantheraEDGE · Events and connectivity')}</h2>
      <p>{tx('Simulación de cámaras, lectura de JSON del nodo y comparación de tiempos de transferencia.',
        'Camera simulation, node JSON reading and transfer-time comparison.')}</p></div>
      <span className="sci-tag">{tx('EVENTOS DE CAMPO','FIELD EVENTS')}</span></div>
    <div className="sci-inline-info" role="note"><span className="sci-info-dot" aria-hidden="true" />
      <p><strong>{tx('Entorno de integración','Integration environment')}</strong> · {tx(
        'Los eventos de prueba y los recibidos por JSON se conservan en esta sesión. La conexión automática a dispositivos físicos y la sincronización en nube aún no están habilitadas.',
        'Test events and imported JSON events are retained in this session. Automatic field-device connections and cloud synchronization are not enabled.')}</p>
    </div>

    <div className="sci-2col">
      <section className="sci-panel">
        <div className="sci-panel-head"><h3>{tx('Generador de eventos PantheraCAM','PantheraCAM event generator')}</h3>
          <span className="sci-tag">{tx('SIMULACIÓN','SIMULATION')}</span></div>
        <p className="sci-muted">{tx('Creá un evento de prueba con datos de estación configurables para verificar el flujo de captura.',
          'Create a test event using configurable station data to verify the capture workflow.')}</p>
        <div className="sci-fields sci-fields-2">
          <label className="sci-field"><span>{tx('ID de cámara','Camera ID')}</span>
            <input value={camera} onChange={e=>setCamera(e.target.value)}/></label>
          <label className="sci-field"><span>{tx('Latitud (opcional)','Latitude (optional)')}</span>
            <input value={latitude} placeholder="9.7489" type="number" step="any" onChange={e=>setLatitude(e.target.value)}/></label>
          <label className="sci-field"><span>{tx('Longitud (opcional)','Longitude (optional)')}</span>
            <input value={longitude} placeholder="-83.7534" type="number" step="any" onChange={e=>setLongitude(e.target.value)}/></label>
          <label className="sci-field"><span>{tx('Temperatura °C (opcional)','Temperature °C (optional)')}</span>
            <input value={temperature} type="number" step="any" onChange={e=>setTemperature(e.target.value)}/></label>
          <label className="sci-field"><span>{tx('Humedad % (opcional)','Humidity % (optional)')}</span>
            <input value={humidity} type="number" step="any" onChange={e=>setHumidity(e.target.value)}/></label>
        </div>
        <button type="button" className="action-button" disabled={busy} onClick={()=>void ingest(demo())}>
          {tx('Simular captura PantheraCAM','Simulate PantheraCAM capture')}</button>
      </section>
      <section className="sci-panel">
        <div className="sci-panel-head"><h3>{tx('Puente HTTP / Wokwi / nodo de campo','HTTP bridge / Wokwi / field node')}</h3>
          <span className="sci-tag">JSON · HTTP</span></div>
        <p className="sci-muted">{tx('Pegá el JSON del emulador de Manuel o recuperalo de un endpoint HTTPS público con CORS.',
          'Paste JSON from Manuel’s emulator or retrieve it from a public CORS-enabled HTTPS endpoint.')}</p>
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
      </section>
    </div>
    {notice&&<p className="sci-notice" role="status">{notice}</p>}

    <section className="sci-panel">
      <div className="sci-panel-head"><h3>{tx('Eventos de la sesión','Session events')}</h3>
        <span className="sci-tag">{events.length} {tx('eventos','events')}</span></div>
      {events.length===0?<p className="sci-muted">{tx('Todavía no hay eventos. Podés simular una captura o validar un JSON.',
        'No events yet. Simulate a capture or validate JSON.')}</p>:
      <><div className="sci-table-wrap"><table className="sci-table">
        <thead><tr><th>ID</th><th>{tx('Cámara','Camera')}</th><th>{tx('Fecha','Time')}</th>
          <th>HMAC</th><th>{tx('Origen','Source')}</th><th>{tx('Acción','Action')}</th></tr></thead>
        <tbody>{events.map((event,i)=><tr key={event.event_id+'-'+i}>
          <td>{event.event_id}</td><td>{event.camera_id}</td><td>{event.timestamp}</td>
          <td>{event.hmac_status}</td><td>{event.source}</td>
          <td><button className="sci-inline" type="button" onClick={()=>{
            setCurrent({...current,camera_id:event.camera_id,
              camera_latitude:event.latitude,camera_longitude:event.longitude,
              altitude_m:event.altitude,temperature_c:event.temperature,
              humidity_percent:event.humidity,edge_event_id:event.event_id});
            setNotice(tx('Metadatos copiados al formulario de PantheraMONITORING. Revisá y guardá la observación allí.',
              'Metadata copied to PantheraMONITORING form. Review and save the observation there.'));
          }}>{tx('Usar en MONITORING','Send to MONITORING')}</button></td></tr>)}</tbody>
      </table></div>
      <div className="sci-actions">
        <button type="button" className="sci-secondary" onClick={()=>downloadFile('PantheraEDGE_eventos.json',
          JSON.stringify(events,null,2),'application/json')}>JSON ↓</button>
        <button type="button" className="sci-secondary" onClick={()=>downloadFile('PantheraEDGE_eventos.csv',
          toCsv(events as unknown as Record<string,unknown>[]),'text/csv')}>CSV ↓</button>
      </div></>}
    </section>

    <section className="sci-panel">
      <div className="sci-panel-head"><h3>{tx('Modelo de transmisión · 5G / 4G','Transmission model · 5G / 4G')}</h3>
        <span className="sci-tag">{tx('ESCENARIO DE REFERENCIA','REFERENCE SCENARIO')}</span></div>
      <p className="sci-muted">{tx('Compará escenarios de transmisión a partir de tamaños de archivo, velocidades y latencias configurables. Los tiempos son proyecciones, no mediciones de red en tiempo real.',
        'Compare transmission scenarios using configurable payload sizes, speeds and latency. Results are projections, not live network measurements.')}</p>
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
      <div className="sci-fields">
        {numberInput(tx('Entrada sin filtrar','Unfiltered input'),rawMB,setRawMB,0,1000,'MB')}
        {numberInput(tx('Payload filtrado','Filtered payload'),filteredMB,setFilteredMB,0,1000,'MB')}
        {numberInput('5G uplink',throughput,setThroughput,.1,1000,'Mbps')}
        {numberInput(tx('Latencia de referencia 5G','5G reference latency'),latency,setLatency,0,1000,'ms')}
        {numberInput('4G uplink',fallbackThroughput,setFallbackThroughput,.1,500,'Mbps')}
        {numberInput(tx('Latencia de referencia 4G','4G reference latency'),fallbackLatency,setFallbackLatency,0,1000,'ms')}
      </div>
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
      <button type="button" className="sci-secondary" onClick={()=>downloadFile('PantheraEDGE_estimacion_5G.json',
        JSON.stringify({source:networkSource,rawMB,filteredMB,throughput_mbps:throughput,latency_ms:latency,
          fallback4g_mbps:fallbackThroughput,fallback4g_latency_ms:fallbackLatency,
          estimated_raw_seconds:rawSec,estimated_filtered_5g_seconds:edgeSec,
          estimated_filtered_4g_seconds:fourGSec,estimated_payload_reduction:reduction,
          measured_network_kpis:false},null,2),'application/json')}>JSON ↓</button>
    </section>
  </div>;
}
