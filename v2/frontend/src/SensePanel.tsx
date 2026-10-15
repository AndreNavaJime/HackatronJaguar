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
          'Lecturas recibidas del ESP32 virtual de Wokwi a través de la API de pruebas.',
          'Readings received from the virtual Wokwi ESP32 through the test API.'
        )}</p>
      </div>
      <span className="sci-tag">SIMULACIÓN · WOKWI</span>
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
    {last.length>0&&<div className="sense-history">
      <h4>{tx('Últimas lecturas (memoria temporal)','Recent readings (temporary memory)')}</h4>
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
    <p className="sci-muted sense-disclaimer">
      {tx(
        'DEMOSTRACIÓN: los valores provienen de un sensor virtual, no de una estación real ni de una red 5G. El servidor conserva únicamente lecturas recientes en memoria; si Render se reinicia, se pierden. No se almacenan fotos, coordenadas ni datos científicos.',
        'DEMO: values come from a virtual sensor, not a physical station or 5G network. The server keeps only recent readings in memory; a Render restart clears them. No photos, locations or scientific records are stored.'
      )}
    </p>
  </section>;
}
