import React from 'react';
import {useLanguage} from './language';

type Sample = {
  device_id:string;
  received_at_utc:string;
  reading_number:number;
  simulation:true;
  gas_alert?:boolean|null;
};
type Telemetry = {
  status:'waiting'|'live'|'stale';
  simulation:true;
  source?:'wokwi_virtual'|'cloud_simulation';
  latest:Sample|null;
  history:Sample[];
};

function localDate(raw:string, language:string) {
  const date=new Date(raw);
  return Number.isNaN(date.getTime())?'—':
    date.toLocaleString(language==='en'?'en-US':'es-CR');
}

export default function FireWorkspace() {
  const {language}=useLanguage();
  const tx=(es:string,en:string)=>language==='en'?en:es;
  const [data,setData]=React.useState<Telemetry|null>(null);
  const [loading,setLoading]=React.useState(true);
  const [problem,setProblem]=React.useState('');
  const [drill,setDrill]=React.useState(false);
  const refresh=React.useCallback(async (signal?:AbortSignal)=>{
    try {
      const response=await fetch('/api/sense/latest',{cache:'no-store',signal});
      if(!response.ok)throw new Error('HTTP '+response.status);
      const payload=await response.json() as Telemetry;
      if(payload.simulation!==true||!Array.isArray(payload.history)){
        throw new Error('Unexpected telemetry format');
      }
      setData(payload);
      setProblem('');
    }catch(error){
      if(signal?.aborted)return;
      setProblem(error instanceof Error?error.message:String(error));
    }finally{
      if(!signal?.aborted)setLoading(false);
    }
  },[]);
  React.useEffect(()=>{
    const controller=new AbortController();
    void refresh(controller.signal);
    const timer=window.setInterval(()=>void refresh(controller.signal),15000);
    return ()=>{controller.abort();window.clearInterval(timer);};
  },[refresh]);

  const virtualWokwi=data?.source==='wokwi_virtual'&&data.status==='live';
  const mq2Present=virtualWokwi&&typeof data?.latest?.gas_alert==='boolean';
  const mq2Alert=mq2Present&&data?.latest?.gas_alert===true;
  const alarm=drill||mq2Alert;
  const recent=(virtualWokwi?data?.history??[]:[])
    .filter(item=>item.gas_alert===true).slice(-8).reverse();

  return <div className="sci-screen fire-screen">
    <div className="fire-heading">
      <div>
        <span className="fire-kicker">PANTHERAFIRE / ENVIRONMENTAL ALERTS</span>
        <h2>PantheraFIRE · {tx('Alertas ambientales','Environmental alerts')}</h2>
        <p>{tx('Centro experimental de señales de gases y simulacros de respuesta. Sin verificación de incendios reales ni notificaciones automáticas a emergencias.',
          'Experimental gas-signal and response-drill center. No real wildfire verification or automatic emergency dispatch.')}</p>
      </div>
      <span className="fire-pill">{tx('ENTORNO DE SIMULACIÓN','SIMULATION ENVIRONMENT')}</span>
    </div>

    <section className="fire-status" aria-label={tx('Estado de vigilancia','Monitoring status')}>
      <h3>{tx('Estado de señales ambientales','Environmental signal status')}</h3>
      <p>{loading?tx('Consultando el servidor…','Checking server…')
        :problem?tx('No se pudo consultar la API: ','Cannot reach the API: ')+problem
        :mq2Present?tx('Entrada digital del MQ-2 virtual conectada en Wokwi.',
            'Virtual Wokwi MQ-2 digital input reporting.')
        :tx('Sin sensor MQ-2 conectado actualmente. El simulacro local permanece disponible.',
            'No MQ-2 sensor currently reporting. Local drills remain available.')}</p>
      <span className={'fire-state'+(alarm?' alert':'')}>
        {alarm?tx('ALERTA SIMULADA · REQUIERE REVISIÓN','SIMULATED ALERT · REVIEW REQUIRED')
          :mq2Present?tx('SIN SEÑAL ANÓMALA','NO ABNORMAL SIGNAL')
          :tx('MONITOREO NO ACTIVO','MONITORING INACTIVE')}
      </span>
      <div className="fire-control">
        <button type="button" onClick={()=>setDrill(v=>!v)} aria-pressed={drill}>
          {drill?tx('Finalizar simulacro','End drill'):tx('Simular alerta de gases','Simulate gas alert')}
        </button>
        <button type="button" onClick={()=>void refresh()} disabled={loading}>
          {tx('Actualizar estado','Refresh status')}
        </button>
        <span>{tx('El simulacro solo afecta este navegador.','This drill affects only this browser.')}</span>
      </div>
      {alarm&&<div className="fire-alert" role="alert">
        <strong>⚠ {tx('SEÑAL ANÓMALA · EVENTO SIMULADO','ABNORMAL SIGNAL · SIMULATED EVENT')}</strong>
        <p>{drill?tx('Aviso generado manualmente para ensayar la interfaz. No corresponde a un incendio ni a una medición real.',
          'Manually generated alert to test the interface. Not a fire or a real measurement.')
          :tx('El MQ-2 virtual de Wokwi marcó su umbral digital. No confirma humo, llamas o incendio; requiere verificación.',
            'The Wokwi virtual MQ-2 crossed its digital threshold. Not confirmation of smoke, flame or fire; verification is needed.')}</p>
        <small>{mq2Alert?tx('Origen: '+(data?.latest?.device_id??'—')+' · estación y ubicación no verificadas',
            'Origin: '+(data?.latest?.device_id??'—')+' · station and location unverified')
          :tx('Simulacro local · ubicación no disponible','Local drill · no location available')}</small>
      </div>}
    </section>

    <div className="fire-columns">
      <section className="fire-card">
        <h3>{tx('Atención de emergencias · Costa Rica','Emergency response · Costa Rica')}</h3>
        <p>{tx('Para reportar un incendio real o una emergencia, utilice el número nacional de emergencias. No llame por simulacros de esta aplicación.',
          'To report an actual fire or emergency, use the national emergency number. Do not call for drills in this app.')}</p>
        <a className="fire-number" href="tel:911" aria-label={tx('Llamar al 911','Call 911')}>9-1-1 ↗</a>
        <p><strong>{tx('Benemérito Cuerpo de Bomberos de Costa Rica','Costa Rica Fire Department')}</strong></p>
        <p>{tx('Oficinas centrales · contacto administrativo:','Headquarters · administrative contact:')}
          {' '}<a href="tel:+50625473700">+506 2547-3700</a>
        </p>
        <p><a href="mailto:info@bomberos.go.cr">info@bomberos.go.cr</a></p>
        <p>{tx('Estación Central, San José · contacto de estación:','Central Fire Station, San José · station contact:')}
          {' '}<a href="tel:+50622569320">2256-9320</a>
        </p>
        <p><a href="https://www.bomberos.go.cr/central/" target="_blank" rel="noreferrer">
          {tx('Directorio oficial de Estación Central ↗','Official Central Station directory ↗')}</a></p>
        <p><a href="https://www.bomberos.go.cr/" target="_blank" rel="noreferrer">
          {tx('Sitio oficial de Bomberos ↗','Official fire department website ↗')}</a></p>
      </section>
      <section className="fire-card">
        <h3>{tx('Verificación y respuesta','Verification and response')}</h3>
        <details className="fire-detail"><summary>{tx('Consultar protocolo orientativo','View suggested protocol')}</summary>
        <ol>
          <li>{tx('Identificar el origen y hora de la señal anómala.','Identify the source and time of the abnormal signal.')}</li>
          <li>{tx('Contrastar con personal autorizado o fuentes independientes, sin aproximarse a áreas peligrosas.','Cross-check through authorized personnel or independent sources without approaching dangerous areas.')}</li>
          <li>{tx('No inferir ubicación o presencia de incendios solo por el MQ-2.','Do not infer a fire or its location from an MQ-2 alone.')}</li>
          <li>{tx('Si se observa una emergencia real, dar aviso al 9-1-1 por medios habituales.','If a real emergency is observed, report it using normal 9-1-1 channels.')}</li>
        </ol></details>
        <div className="fire-note">{tx('La app no está conectada al despacho de Bomberos. Ninguna alerta o simulacro llama, envía mensajes o notifica automáticamente al 9-1-1.',
          'The app is not connected to fire dispatch. No alert or drill automatically calls, sends messages, or notifies 9-1-1.')}</div>
      </section>
    </div>
    <section className="fire-card" style={{marginTop:14}}>
      <h3>{tx('Registro reciente de señales de prueba · Wokwi','Recent simulated signal log · Wokwi')}</h3>
      {recent.length===0?<p>{tx('No hay señales MQ-2 recientes en las lecturas disponibles. Los simulacros manuales no se almacenan como incidentes.',
        'No recent MQ-2 signals in available readings. Manual drills are not stored as incidents.')}</p>:
        <div style={{overflowX:'auto'}}>
          <table className="fire-events"><thead><tr>
            <th>{tx('Hora recibida','Received')}</th><th>{tx('Nodo','Node')}</th><th>{tx('Tipo','Type')}</th>
          </tr></thead><tbody>{recent.map((event,i)=><tr key={event.received_at_utc+'-'+i}>
            <td>{localDate(event.received_at_utc,language)}</td>
            <td>{event.device_id}</td>
            <td>{tx('Gas · simulación','Gas · simulation')}</td>
          </tr>)}</tbody></table>
        </div>}
      <details className="fire-detail"><summary>{tx('Metodología y limitaciones','Methodology and limitations')}</summary>
        <p>{tx('PantheraFIRE es una interfaz experimental de simulación. Los valores y señales proceden de Wokwi, y no hay ubicaciones de cámaras vinculadas o verificadas. El MQ-2 responde a ciertos gases combustibles, no verifica un incendio. La API conserva pocas lecturas en RAM, no un historial persistente. El botón de simulacro es exclusivamente local.',
          'PantheraFIRE is an experimental simulation interface. Values and signals come from Wokwi, with no linked or verified camera locations. An MQ-2 responds to certain combustible gases, not confirmed fires. The API stores only a few readings in RAM, not a persistent history. The drill button is local only.')}</p>
      </details>
    </section>
  </div>;
}
