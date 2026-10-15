import React from 'react';
import {useLanguage} from './language';

type Sample={
  device_id:string;
  temperature_c:number;
  humidity_pct:number;
  received_at_utc:string;
  reading_number:number;
  simulation:true;
  gas_alert?:boolean;
};
type Result={
  status:'waiting'|'live'|'stale';
  simulation:true;
  storage:'ephemeral_process_memory'|'computed_on_demand';
  source?:'wokwi_virtual'|'cloud_simulation';
  generated_on_request?:boolean;
  latest:Sample|null;
  history:Sample[];
};
function clock(value:string, lang:string){
  const date=new Date(value);
  return Number.isNaN(date.getTime())?'—':date.toLocaleString(lang==='en'?'en-US':'es-CR');
}

/** Read-only view: never presents simulated DHT22 readings as field measurements. */
export default function SensePanel(){
  const {language}=useLanguage();
  const tx=(es:string,en:string)=>language==='en'?en:es;
  const [data,setData]=React.useState<Result|null>(null);
  const [problem,setProblem]=React.useState('');
  const [loading,setLoading]=React.useState(true);
  // Manual local drill; it never creates a server-side emergency.
  const [manualDrill,setManualDrill]=React.useState(false);
  const refresh=React.useCallback(async(signal?:AbortSignal)=>{
    try{
      const response=await fetch('/api/sense/latest',{cache:'no-store',signal});
      if(!response.ok)throw new Error('HTTP '+response.status);
      const result=await response.json() as Result;
      if(result.simulation!==true||!Array.isArray(result.history)){
        throw new Error('Formato de datos inesperado');
      }
      setData(result);
      setProblem('');
    }catch(err){
      if(signal?.aborted)return;
      setProblem(err instanceof Error?err.message:String(err));
    }finally{
      if(!signal?.aborted)setLoading(false);
    }
  },[]);
  React.useEffect(()=>{
    const controller=new AbortController();
    void refresh(controller.signal);
    const timer=window.setInterval(()=>void refresh(controller.signal),15000);
    return ()=>{window.clearInterval(timer);controller.abort();};
  },[refresh]);

  const sample=data?.latest??null;
  const cloud=data?.source==='cloud_simulation';
  const active=data?.status==='live'&&!!sample;
  const last=(data?.history??[]).slice(-6).reverse();
  const wokwiGasSignal=active&&!cloud&&sample?.gas_alert===true;
  const alertActive=manualDrill||wokwiGasSignal;
  const gasAvailable=active&&!cloud&&typeof sample?.gas_alert==='boolean';

  return <section className="sci-panel sense-panel" aria-label="PantheraSENSE">
    <div className="sci-panel-head">
      <div>
        <h3>PantheraSENSE · {tx('Nodo ambiental','Environmental node')}</h3>
        <p className="sci-muted">{tx(
          'Monitoreo ambiental · Telemetría y alertas',
          'Environmental monitoring · Telemetry and alerts'
        )}</p>
      </div>
      <span className="sci-tag">{tx('SIMULACIÓN','SIMULATION')}</span>
    </div>
    <div className="sense-status-line" role="status">
      <span className={active?'sense-status-live':'sense-status-wait'}>
        {loading?tx('Consultando servidor…','Checking server…')
          :problem?tx('API no disponible','API unavailable')
          :active?(cloud?tx('SIMULACIÓN EN NUBE ACTIVA','CLOUD SIMULATION ACTIVE')
            :tx('RECIBIENDO DATOS','RECEIVING DATA'))
          :data?.status==='stale'?tx('SIN DATOS RECIENTES','NO RECENT DATA')
          :tx('ESPERANDO PRIMER ENVÍO','AWAITING FIRST READING')}
      </span>
      <button className="sci-secondary" type="button" onClick={()=>void refresh()}
        disabled={loading}>
        {tx('Actualizar ahora','Refresh now')}
      </button>
    </div>
    {problem&&<p className="sci-notice" role="alert">{tx(
      'No se puede consultar la API PantheraSENSE: ',
      'Cannot reach PantheraSENSE API: '
    )}{problem}. {tx(
      'Esto no afecta los demás módulos.',
      'Other modules remain available.'
    )}</p>}
    <div className="sense-grid">
      <div className="sense-stat">
        <span>{tx('Temperatura','Temperature')}</span>
        <strong>{sample?sample.temperature_c.toFixed(1)+' °C':'—'}</strong>
      </div>
      <div className="sense-stat">
        <span>{tx('Humedad relativa','Relative humidity')}</span>
        <strong>{sample?sample.humidity_pct.toFixed(1)+' %':'—'}</strong>
      </div>
      <div className="sense-stat">
        <span>{cloud?tx('Última simulación','Last simulated')
          :tx('Última recepción','Last received')}</span>
        <strong className="sense-date">{sample?clock(sample.received_at_utc,language):'—'}</strong>
      </div>
    </div>
    <div className="sense-gas-header">
      <div>
        <h4>{tx('Detección experimental de gases','Experimental gas detection')}</h4>
        <p className="sci-muted">{tx(
          'Señales de prueba; no constituye un sistema validado de detección de incendios.',
          'Test signals; not a validated wildfire detection system.'
        )}</p>
      </div>
      <span className={alertActive?'sense-gas-state sense-gas-active':'sense-gas-state'}>
        {alertActive?tx('ALERTA DE PRUEBA','TEST ALERT')
          :gasAvailable?tx('SIN SEÑAL ANÓMALA','NO ABNORMAL SIGNAL')
          :tx('SIN SENSOR DE GAS ACTIVO','NO ACTIVE GAS SENSOR')}
      </span>
    </div>
    {alertActive&&<div className="sense-fire-alert" role="alert">
      <div className="sense-fire-alert-title">
        <span aria-hidden="true">⚠</span>
        <strong>{tx('SEÑAL ANÓMALA DE GASES · SIMULACIÓN',
          'ABNORMAL GAS SIGNAL · SIMULATION')}</strong>
      </div>
      <p>{manualDrill?tx(
        'Simulacro activado desde este navegador. No se ha detectado humo ni un incendio real.',
        'Drill activated in this browser. No actual smoke or fire has been detected.'
      ):tx(
        'El MQ-2 virtual de Wokwi superó el umbral digital. Requiere verificación; no confirma humo ni incendio.',
        'The virtual Wokwi MQ-2 exceeded the digital threshold. Verification is required; this does not confirm smoke or fire.'
      )}</p>
      <small>{wokwiGasSignal?tx(
        'Nodo emisor: '+(sample?.device_id??'—')+' · ubicación no verificada',
        'Origin node: '+(sample?.device_id??'—')+' · location not verified'
      ):tx('Evento local de demostración · sin ubicación asociada',
        'Local demo event · no location assigned')}</small>
    </div>}
    <div className="sense-drill-actions">
      <button type="button" className="sci-secondary" aria-pressed={manualDrill}
        onClick={()=>setManualDrill(value=>!value)}>
        {manualDrill?tx('Finalizar simulacro','End drill')
          :tx('Simular alerta de gases','Simulate gas alert')}
      </button>
      <span>{tx('El simulacro solo aparece en este navegador.',
        'The drill only appears in this browser.')}</span>
    </div>
    <p className="sense-source-line">{cloud?
      tx('Fuente: generador virtual en la nube · Render','Source: Cloud virtual generator · Render'):
      tx('Fuente: ESP32 virtual · Wokwi','Source: Virtual ESP32 · Wokwi')}</p>
    {last.length>0&&<div className="sense-history">
      <h4>{cloud?tx('Últimos valores simulados','Recent simulated values')
        :tx('Últimas lecturas','Recent readings')}</h4>
      <div className="sense-table-wrap">
        <table><thead><tr>
          <th>{cloud?tx('Hora simulada','Simulated time')
            :tx('Hora recibida','Received')}</th>
          <th>{tx('Temperatura','Temperature')}</th>
          <th>{tx('Humedad','Humidity')}</th>
          <th>{tx('Señal MQ-2','MQ-2 signal')}</th>
          <th>#</th>
        </tr></thead>
          <tbody>{last.map((entry,i)=><tr key={entry.received_at_utc+'-'+i}>
            <td>{clock(entry.received_at_utc,language)}</td>
            <td>{entry.temperature_c.toFixed(1)} °C</td>
            <td>{entry.humidity_pct.toFixed(1)} %</td>
            <td>{entry.gas_alert===true?tx('Alerta de prueba','Test alert'):
              entry.gas_alert===false?tx('Normal','Normal'):'—'}</td>
            <td>{entry.reading_number}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </div>}
    <details className="sense-methodology">
      <summary>{tx('Información técnica y metodología','Technical information and methodology')}</summary>
      <div className="sense-methodology-content">
        <p>{cloud?tx(
          'Modo nube: el servidor calcula valores sintéticos cada vez que se consulta el panel. No necesita Wokwi abierto, sensores físicos ni claves. Estos valores no son mediciones de campo y no demuestran conectividad 5G.',
          'Cloud mode: the server computes synthetic values when the dashboard is queried. No Wokwi session, physical sensor or key is required. These values are not field measurements and do not demonstrate 5G connectivity.'
        ):tx(
          'Modo Wokwi: las lecturas proceden del ESP32 virtual y llegan por HTTPS. No son mediciones de campo ni demuestran conectividad 5G real.',
          'Wokwi mode: readings originate from a virtual ESP32 and arrive over HTTPS. They are not field measurements and do not demonstrate real 5G connectivity.'
        )}</p>
        <p>{tx(
          'El MQ-2 indica ciertos gases combustibles, no confirma humo ni incendios. La señal es experimental y no tiene localización verificada de cámara ni calibración para campo. El simulacro se mantiene solo en este navegador; no envía notificaciones externas.',
          'The MQ-2 indicates some combustible gases, not confirmed smoke or wildfires. Signals are experimental, with no verified camera location or field calibration. The drill stays in this browser and sends no external notifications.'
        )}</p>
        <p>{tx(
          'En modo nube, los valores se generan bajo demanda: no se registra un historial permanente ni se ejecuta una tarea continua con la aplicación cerrada. Si Wokwi envía datos nuevos, se muestran primero. Las lecturas de Wokwi se guardan temporalmente en memoria y se pierden al reiniciar Render.',
          'In cloud mode, values are generated on demand: no permanent history is recorded and no continuous job runs when the app is closed. Fresh Wokwi data takes priority. Wokwi readings are stored temporarily in memory and lost when Render restarts.'
        )}</p>
      </div>
    </details>
  </section>;
}
