import React from 'react';
import {useLanguage} from './language';

type Sample={
  device_id:string;
  temperature_c:number;
  humidity_pct:number;
  received_at_utc:string;
  reading_number:number;
  simulation:true;
};
type Result={
  status:'waiting'|'live'|'stale';
  simulation:true;
  storage:'ephemeral_process_memory';
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
  const active=data?.status==='live'&&!!sample;
  const last=(data?.history??[]).slice(-6).reverse();

  return <section className="sci-panel sense-panel" aria-label="PantheraSENSE">
    <div className="sci-panel-head">
      <div>
        <h3>PantheraSENSE · {tx('Nodo ambiental','Environmental node')}</h3>
        <p className="sci-muted">{tx(
          'Monitoreo ambiental · Temperatura y humedad',
          'Environmental monitoring · Temperature and humidity'
        )}</p>
      </div>
      <span className="sci-tag">{tx('SIMULACIÓN','SIMULATION')}</span>
    </div>
    <div className="sense-status-line" role="status">
      <span className={active?'sense-status-live':'sense-status-wait'}>
        {loading?tx('Consultando servidor…','Checking server…')
          :problem?tx('API no disponible','API unavailable')
          :active?tx('RECIBIENDO DATOS','RECEIVING DATA')
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
        <span>{tx('Última recepción','Last received')}</span>
        <strong className="sense-date">{sample?clock(sample.received_at_utc,language):'—'}</strong>
      </div>
    </div>
    <p className="sense-source-line">{tx('Fuente: ESP32 virtual · Wokwi','Source: Virtual ESP32 · Wokwi')}</p>
    {last.length>0&&<div className="sense-history">
      <h4>{tx('Últimas lecturas','Recent readings')}</h4>
      <div className="sense-table-wrap">
        <table><thead><tr>
          <th>{tx('Hora recibida','Received')}</th>
          <th>{tx('Temperatura','Temperature')}</th>
          <th>{tx('Humedad','Humidity')}</th>
          <th>#</th>
        </tr></thead>
          <tbody>{last.map((entry,i)=><tr key={entry.received_at_utc+'-'+i}>
            <td>{clock(entry.received_at_utc,language)}</td>
            <td>{entry.temperature_c.toFixed(1)} °C</td>
            <td>{entry.humidity_pct.toFixed(1)} %</td>
            <td>{entry.reading_number}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </div>}
    <details className="sense-methodology">
      <summary>{tx('Información técnica y metodología','Technical information and methodology')}</summary>
      <div className="sense-methodology-content">
        <p>{tx(
          'Los valores proceden de un ESP32 virtual en Wokwi. Permiten verificar el flujo de telemetría, pero no representan mediciones de campo ni demuestran conectividad 5G real.',
          'Values originate from a virtual ESP32 in Wokwi. They verify the telemetry workflow but are not field measurements and do not demonstrate real 5G connectivity.'
        )}</p>
        <p>{tx(
          'El servidor conserva hasta 30 lecturas en memoria temporal; un reinicio de Render elimina ese historial. Este módulo no recibe fotos, coordenadas ni registros científicos.',
          'The server stores up to 30 readings in temporary memory; restarting Render clears that history. This module does not receive photos, coordinates, or scientific records.'
        )}</p>
      </div>
    </details>
  </section>;
}
