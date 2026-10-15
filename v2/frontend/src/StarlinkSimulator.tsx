import React from 'react';
import {useLanguage} from './language';

type LinkMode='available'|'obstructed'|'offline';
type Route='satellite'|'cellular';
type DemoEvent={id:number;kind:'camera'|'fire';route:Route;created:string;result:'delivered'|'queued';estimatedSeconds:number|null};
const LIMIT=8;
function transferSeconds(kb:number,mbps:number,rtt:number){
  return kb*8/1000/mbps+rtt/1000;
}
export default function StarlinkSimulator(){
  const {language}=useLanguage();
  const tx=(es:string,en:string)=>language==='en'?en:es;
  const [mode,setMode]=React.useState<LinkMode>('available');
  const [cellular,setCellular]=React.useState(true);
  const [satUpload,setSatUpload]=React.useState(5);
  const [satLatency,setSatLatency]=React.useState(65);
  const [cellUpload,setCellUpload]=React.useState(2);
  const [cellLatency,setCellLatency]=React.useState(90);
  const [payloadKb,setPayloadKb]=React.useState(250);
  const [entries,setEntries]=React.useState<DemoEvent[]>([]);
  const [pending,setPending]=React.useState<{id:number;kind:'camera'|'fire';created:string}[]>([]);
  const seq=React.useRef(0);

  // User-controlled link scenarios only: nothing is transmitted to any external service.
  const satOk=mode==='available';
  const fallback:Route|null=satOk?'satellite':cellular?'cellular':null;
  const chosenMbps=fallback==='satellite'?satUpload:cellUpload;
  const chosenRtt=fallback==='satellite'?satLatency:cellLatency;
  const duration=fallback?transferSeconds(payloadKb,chosenMbps,chosenRtt):null;
  const satDuration=transferSeconds(payloadKb,satUpload,satLatency);
  const cellDuration=transferSeconds(payloadKb,cellUpload,cellLatency);
  const modeText=mode==='available'?tx('Enlace satelital disponible (simulado)','Satellite link available (simulated)')
    :mode==='obstructed'?tx('Enlace satelital obstruido (simulado)','Satellite link obstructed (simulated)')
    :tx('Enlace satelital desconectado (simulado)','Satellite link disconnected (simulated)');

  function send(kind:'camera'|'fire'){
    const id=++seq.current;
    const created=new Date().toISOString();
    if(!fallback){
      setPending(prev=>[...prev,{id,kind,created}].slice(-LIMIT));
      setEntries(prev=>[{id,kind,route:'satellite',created,result:'queued',estimatedSeconds:null},...prev].slice(0,LIMIT));
      return;
    }
    setEntries(prev=>[{id,kind,route:fallback,created,result:'delivered',estimatedSeconds:duration},...prev].slice(0,LIMIT));
  }
  function flush(){
    if(!fallback||!pending.length)return;
    const delivered=pending.map(event=>({...event,route:fallback,result:'delivered' as const,estimatedSeconds:duration}));
    const ids=new Set(delivered.map(event=>event.id));
    setEntries(prev=>[...delivered,...prev.filter(event=>!ids.has(event.id))].slice(0,LIMIT));
    setPending([]);
  }
  function reset(){setEntries([]);setPending([]);}
  const numberControl=(title:string,value:number,setter:(x:number)=>void,min:number,max:number,step:number,unit:string)=>
    <label className="sci-field"><span>{title} ({unit})</span><input type="number" value={value}
      min={min} max={max} step={step} onChange={e=>{const n=Number(e.target.value);
        if(e.target.value.trim()!==''&&Number.isFinite(n)&&n>=min&&n<=max)setter(n);}}/></label>;
  return <section className="sci-panel starlink-panel" aria-label={tx('Simulador de conexión Starlink','Starlink connection simulator')}>
    <div className="sci-panel-head">
      <div><h3>{tx('Conectividad satelital · Escenario Starlink','Satellite connectivity · Starlink scenario')}</h3>
        <p className="sci-muted">{tx('Evaluación didáctica de enlaces de campo, respaldo celular y recuperación de eventos.',
          'Educational model of field links, cellular fallback and event recovery.')}</p></div>
      <span className="sci-tag">{tx('SIMULACIÓN','SIMULATION')}</span>
    </div>
    <div className="starlink-status" role="status"><strong>{modeText}</strong><span>{fallback==='satellite'?
      tx('Ruta hipotética: Starlink','Hypothetical route: Starlink'):fallback==='cellular'?
      tx('Respaldo celular disponible (simulado)','Cellular fallback available (simulated)'):
      tx('Sin salida simulada; eventos en cola local','No simulated route; events queued locally')}</span></div>
    <p className="sci-muted">{tx(
      'Starlink es un servicio de acceso a Internet, no un satélite de observación como Sentinel-2. Este módulo NO consulta la red de Starlink, ni mide cobertura, disponibilidad o latencia reales.',
      'Starlink provides Internet connectivity, not Earth observation like Sentinel-2. This module does NOT query the Starlink network or measure actual coverage, availability or latency.'
    )}</p>
    <div className="starlink-controls">
      <label className="sci-field"><span>{tx('Estado del enlace satelital','Satellite link scenario')}</span>
        <select value={mode} onChange={e=>setMode(e.target.value as LinkMode)}>
          <option value="available">{tx('Disponible','Available')}</option>
          <option value="obstructed">{tx('Obstruido por vegetación','Obstructed by vegetation')}</option>
          <option value="offline">{tx('Desconectado','Disconnected')}</option>
        </select></label>
      <label className="starlink-toggle"><input type="checkbox" checked={cellular}
        onChange={e=>setCellular(e.target.checked)}/>{tx('Respaldo celular hipotético habilitado',
          'Hypothetical cellular fallback enabled')}</label>
    </div>
    <div className="sci-fields">
      {numberControl(tx('Velocidad de subida Starlink (supuesto)','Starlink assumed upload speed'),satUpload,setSatUpload,.1,100,.1,'Mbps')}
      {numberControl(tx('Latencia Starlink (supuesto)','Starlink assumed latency'),satLatency,setSatLatency,1,2000,1,'ms')}
      {numberControl(tx('Velocidad de subida celular (supuesto)','Cellular assumed upload speed'),cellUpload,setCellUpload,.1,100,.1,'Mbps')}
      {numberControl(tx('Latencia celular (supuesto)','Cellular assumed latency'),cellLatency,setCellLatency,1,2000,1,'ms')}
      {numberControl(tx('Tamaño del mensaje de prueba','Test message size'),payloadKb,setPayloadKb,1,10000,1,'kB')}
    </div>
    <div className="sci-stats">
      <div><span>{tx('Starlink (si disponible)','Starlink (if available)')}</span><strong>{satDuration.toFixed(2)} s</strong></div>
      <div><span>{tx('Celular (si disponible)','Cellular (if available)')}</span><strong>{cellDuration.toFixed(2)} s</strong></div>
      <div><span>{tx('Ruta seleccionada','Selected route')}</span><strong>{fallback??'—'}</strong></div>
      <div><span>{tx('Eventos pendientes','Queued events')}</span><strong>{pending.length}</strong></div>
    </div>
    <p className="sci-muted">{tx('Modelo ilustrativo = tamaño / velocidad + latencia. No incluye protocolos, congestión, pérdidas, energía, instalación, obstrucciones variables ni variabilidad de Starlink; no es una predicción de rendimiento.',
      'Illustrative model = size / throughput + latency. Protocol overhead, congestion, packet loss, power, installation, changing obstructions and Starlink variability are excluded; this is not a performance prediction.')}</p>
    <div className="starlink-actions">
      <button type="button" className="sci-secondary" onClick={()=>send('camera')}>{tx('Simular evento de cámara','Simulate camera event')}</button>
      <button type="button" className="sci-secondary" onClick={()=>send('fire')}>{tx('Simular mensaje PantheraFIRE','Simulate PantheraFIRE message')}</button>
      <button type="button" className="sci-secondary" disabled={!fallback||!pending.length} onClick={flush}>{tx('Reenviar cola simulada','Retry simulated queue')}</button>
      <button type="button" className="sci-secondary" disabled={!entries.length&&!pending.length} onClick={reset}>{tx('Limpiar pruebas','Clear tests')}</button>
    </div>
    <p className="sci-muted">{tx('Los mensajes PantheraFIRE de esta sección son ejercicios locales; NO generan alertas reales, no se envían a PantheraFIRE ni se notifican a Bomberos.',
      'PantheraFIRE messages here are local drills: no real alarms, no data sent to PantheraFIRE and no emergency dispatch notifications.')}</p>
    {entries.length>0&&<div className="sense-table-wrap"><table className="fire-events"><thead><tr>
      <th>{tx('Evento','Event')}</th><th>{tx('Estado','Status')}</th><th>{tx('Ruta','Route')}</th><th>{tx('Tiempo estimado','Estimated time')}</th>
    </tr></thead><tbody>{entries.map(event=><tr key={event.id}>
      <td>{event.kind==='fire'?'PantheraFIRE':'PantheraCAM'} #{event.id}</td>
      <td>{event.result==='queued'?tx('En cola','Queued'):tx('Entrega hipotética','Hypothetical delivery')}</td>
      <td>{event.result==='queued'?'—':event.route==='satellite'?'Starlink':tx('Celular','Cellular')}</td>
      <td>{event.estimatedSeconds===null?'—':event.estimatedSeconds.toFixed(2)+' s'}</td>
    </tr>)}</tbody></table></div>}
  </section>;
}
