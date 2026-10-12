import React from 'react';
import {useLanguage} from './language';
import {Observation,SatelliteData,SatelliteItem,apiJson,downloadFile,toCsv,toGeoJSON} from './scienceShared';

type Props={records:Observation[];current:Observation};

export default function ResearchWorkspace({records,current}:Props){
  const {language}=useLanguage(),tx=(es:string,en:string)=>language==='en'?en:es;
  const [latitude,setLatitude]=React.useState(String(current.camera_latitude??''));
  const [longitude,setLongitude]=React.useState(String(current.camera_longitude??''));
  const [radius,setRadius]=React.useState(5);
  const [days,setDays]=React.useState(30);
  const [cloud,setCloud]=React.useState(40);
  const [busy,setBusy]=React.useState(false);
  const [error,setError]=React.useState('');
  const [satellite,setSatellite]=React.useState<SatelliteData|null>(null);
  const [selected,setSelected]=React.useState('all');
  const available=records.filter(x=>x.validation_status==='researcher_validated'||x.validation_status==='field_verified');
  const rows=selected==='validated'?available:records;
  const items=[...(satellite?.sentinel_1??[]),...(satellite?.sentinel_2??[])];
  const convertItem=(item:SatelliteItem):Record<string,unknown>=>({
    sensor:item.sensor,product_id:item.id,acquisition:item.datetime,
    cloud_cover:item.cloud_cover,platform:item.platform,orbit_state:item.orbit_state,
  });

  const lookup=async()=>{
    const lat=Number(latitude),lon=Number(longitude);
    if(latitude.trim()===''||longitude.trim()===''||!Number.isFinite(lat)||!Number.isFinite(lon)||
      lat < -90||lat > 90||lon < -180||lon > 180){
      setError(tx('Ingresá coordenadas WGS84 válidas de una estación.','Enter valid WGS84 station coordinates.'));
      return;
    }
    setError('');setBusy(true);setSatellite(null);
    try{
      const response=await apiJson<SatelliteData>('/api/science/sentinel/search','POST',{
        latitude:lat,longitude:lon,radius_km:radius,days_back:days,max_cloud_cover:cloud,
      });
      setSatellite(response);
    }catch(cause){setError(cause instanceof Error?cause.message:String(cause));}
    finally{setBusy(false);}
  };

  return <div className="sci-screen">
    <div className="sci-heading"><div><span className="sci-kicker">RESEARCH / COPERNICUS / ESA SENTINEL</span>
      <h2>{tx('Investigación · Evidencia y contexto satelital','Research · Evidence and satellite context')}</h2>
      <p>{tx('Catálogo de adquisiciones de Sentinel-1 y Sentinel-2, historial de anotaciones y exportaciones institucionales.',
        'Sentinel-1 and Sentinel-2 acquisition catalogue, annotation history, and institutional exports.')}</p></div>
      <span className="sci-tag">{tx('DATOS + MÉTODOS','DATA + METHODS')}</span></div>
    <div className="sci-2col">
      <section className="sci-panel">
        <div className="sci-panel-head"><h3>{tx('Consultar Copernicus Data Space','Query Copernicus Data Space')}</h3>
          <span className="sci-tag">STAC API</span></div>
        <p className="sci-muted">{tx('Búsqueda del catálogo real alrededor de una cámara. No descarga ni analiza bandas espectrales.',
          'Real catalogue search around a camera. Does not download or analyze spectral bands.')}</p>
        <div className="sci-fields sci-fields-2">
          <label className="sci-field"><span>{tx('Latitud de cámara','Camera latitude')}</span>
            <input type="number" step="any" min="-90" max="90" value={latitude}
              onChange={e=>setLatitude(e.target.value)} placeholder="9.7489"/></label>
          <label className="sci-field"><span>{tx('Longitud de cámara','Camera longitude')}</span>
            <input type="number" step="any" min="-180" max="180" value={longitude}
              onChange={e=>setLongitude(e.target.value)} placeholder="-83.7534"/></label>
          <label className="sci-field"><span>{tx('Radio de búsqueda','Search radius')} · {radius} km</span>
            <input type="range" min="1" max="50" step="1" value={radius}
              onChange={e=>setRadius(Number(e.target.value))}/></label>
          <label className="sci-field"><span>{tx('Periodo anterior','Lookback period')} · {days} {tx('días','days')}</span>
            <input type="range" min="5" max="90" step="5" value={days}
              onChange={e=>setDays(Number(e.target.value))}/></label>
          <label className="sci-field"><span>{tx('Cobertura nubosa máxima S2','S2 maximum cloud cover')} · {cloud}%</span>
            <input type="range" min="0" max="100" step="5" value={cloud}
              onChange={e=>setCloud(Number(e.target.value))}/></label>
        </div>
        <div className="sci-actions">
          <button type="button" className="action-button" disabled={busy} onClick={()=>void lookup()}>
            {busy?tx('Consultando catálogo…','Searching catalogue…'):
              tx('Consultar Sentinel-1 y Sentinel-2 ↗','Query Sentinel-1 and Sentinel-2 ↗')}</button>
          {current.camera_latitude!==null&&current.camera_longitude!==null&&
            <button className="sci-secondary" type="button" onClick={()=>{
              setLatitude(String(current.camera_latitude));setLongitude(String(current.camera_longitude));
            }}>{tx('Usar coordenadas de la observación','Use observation coordinates')}</button>}
        </div>
        {error&&<p className="sci-notice" role="alert">{error}</p>}
        <p className="sci-muted">{tx('Al consultar, las coordenadas indicadas se envían a Copernicus. No introduzcás localizaciones sensibles sin autorización.',
          'When querying, these coordinates are sent to Copernicus. Do not submit sensitive locations without authorization.')}</p>
      </section>
      <section className="sci-panel">
        <h3>{tx('Qué aporta cada satélite','What each satellite contributes')}</h3>
        <div className="sci-satellite-box"><span>SENTINEL-1 · SAR</span>
          <p>{tx('Fecha de adquisición, plataforma y órbita. El radar puede adquirir escenas independientemente de la nubosidad.',
            'Acquisition date, platform, and orbit. Radar can acquire scenes regardless of cloud cover.')}</p></div>
        <div className="sci-satellite-box"><span>SENTINEL-2 · L2A</span>
          <p>{tx('Adquisiciones ópticas multiespectrales y nubosidad reportada. El catálogo no equivale a un índice NDVI calculado.',
            'Multispectral optical acquisitions and reported cloud cover. Catalogue metadata is not calculated NDVI.')}</p></div>
        <p className="sci-warning">{tx('El catálogo por sí solo NO demuestra deforestación, inundaciones, cambios de hábitat ni presencia de jaguares.',
          'Catalogue metadata alone does NOT establish forest loss, flooding, habitat change or jaguar presence.')}</p>
      </section>
    </div>

    {satellite&&<section className="sci-panel">
      <div className="sci-panel-head"><h3>{tx('Resultados del catálogo satelital','Satellite catalogue results')}</h3>
        <span className="sci-tag">{new Date(satellite.queried_at).toLocaleString(language==='en'?'en-US':'es-CR')}</span></div>
      <div className="sci-stats">
        <div><span>{tx('Adquisiciones Sentinel-1','Sentinel-1 acquisitions')}</span>
          <strong>{satellite.sentinel_1.length}</strong></div>
        <div><span>{tx('Adquisiciones Sentinel-2','Sentinel-2 acquisitions')}</span>
          <strong>{satellite.sentinel_2.length}</strong></div>
        <div><span>{tx('Máximo nubosidad solicitada S2','Requested S2 cloud threshold')}</span>
          <strong>{cloud}%</strong></div>
        <div><span>{tx('Productos en respuesta','Products returned')}</span>
          <strong>{items.length}</strong></div>
      </div>
      <div className="sci-table-wrap"><table className="sci-table">
        <thead><tr><th>{tx('Sensor','Sensor')}</th><th>{tx('Adquisición UTC','UTC acquisition')}</th>
          <th>{tx('Plataforma','Platform')}</th><th>{tx('Nubes','Clouds')}</th><th>{tx('Producto','Product')}</th></tr></thead>
        <tbody>{items.map((item,i)=><tr key={item.id+'-'+i}>
          <td>{item.sensor}</td><td>{item.datetime}</td><td>{item.platform||'—'}</td>
          <td>{item.cloud_cover===null?'N/A':item.cloud_cover+'%'}</td><td>{item.id}</td>
        </tr>)}</tbody>
      </table></div>
      {!items.length&&<p className="sci-muted">{tx('No hubo adquisiciones en el periodo o con estos filtros.',
        'No acquisitions matched this period and filters.')}</p>}
      <div className="sci-actions">
        <button className="sci-secondary" type="button" onClick={()=>downloadFile('PantheraLAB_Sentinel_catalogo.json',
          JSON.stringify(satellite,null,2),'application/json')}>JSON ↓</button>
        <button className="sci-secondary" type="button" disabled={!items.length} onClick={()=>
          downloadFile('PantheraLAB_Sentinel_catalogo.csv',toCsv(items.map(convertItem)),'text/csv;charset=utf-8')}>
          CSV ↓</button>
      </div>
      <p className="sci-muted">{satellite.disclaimer}</p>
    </section>}

    <section className="sci-panel">
      <div className="sci-panel-head"><h3>{tx('Datos científicos y exportaciones','Scientific data and exports')}</h3>
        <span className="sci-tag">JSON · CSV · GeoJSON</span></div>
      <p className="sci-muted">{tx('Exportá los registros de esta pestaña para revisión externa. Las especies e IDs son anotaciones humanas.',
        'Export this tab’s records for external review. Species and IDs are human annotations.')}</p>
      <div className="sci-switch" role="group" aria-label={tx('Filtro de validación','Validation filter')}>
        <button type="button" className={selected==='all'?'selected':''} onClick={()=>setSelected('all')}>
          {tx('Todos los registros','All records')} ({records.length})</button>
        <button type="button" className={selected==='validated'?'selected':''} onClick={()=>setSelected('validated')}>
          {tx('Validados','Validated')} ({available.length})</button>
      </div>
      <div className="sci-stats">
        <div><span>{tx('Registros seleccionados','Selected records')}</span><strong>{rows.length}</strong></div>
        <div><span>{tx('Con coordenadas','With coordinates')}</span><strong>{
          rows.filter(r=>r.camera_latitude!==null&&r.camera_longitude!==null).length}</strong></div>
        <div><span>{tx('Especies anotadas distintas','Distinct annotated species')}</span><strong>{
          new Set(rows.map(r=>r.species.trim()).filter(Boolean)).size}</strong></div>
        <div><span>{tx('IDs individuales asignados','Assigned individual IDs')}</span><strong>{
          new Set(rows.map(r=>r.individual_id.trim()).filter(Boolean)).size}</strong></div>
      </div>
      <div className="sci-actions">
        <button type="button" className="sci-secondary" disabled={!rows.length} onClick={()=>
          downloadFile('PantheraLAB_investigacion.json',JSON.stringify(rows,null,2),'application/json')}>JSON ↓</button>
        <button type="button" className="sci-secondary" disabled={!rows.length} onClick={()=>
          downloadFile('PantheraLAB_investigacion.csv',
            toCsv(rows as unknown as Record<string,unknown>[]),'text/csv;charset=utf-8')}>CSV ↓</button>
        <button type="button" className="sci-secondary" disabled={!rows.length} onClick={()=>
          downloadFile('PantheraLAB_investigacion.geojson',
            JSON.stringify(toGeoJSON(rows),null,2),'application/geo+json')}>GeoJSON ↓</button>
      </div>
      <p className="sci-warning">{tx('GeoJSON conserva coordenadas exactas. Antes de compartir con terceros, generalizá u ocultá puntos de especies vulnerables.',
        'GeoJSON includes exact coordinates. Generalize or remove sensitive wildlife locations before sharing with third parties.')}</p>
      <h3>{tx('Formatos institucionales','Institutional outputs')}</h3>
      <div className="sci-stats">
        <div><span>SINAC / GIS</span><strong>GeoJSON</strong></div>
        <div><span>{tx('Investigadores','Researchers')}</span><strong>CSV / JSON</strong></div>
        <div><span>CNE / Bomberos</span><strong>{tx('CAP pendiente','CAP planned')}</strong></div>
        <div><span>{tx('Guardaparques','Rangers')}</span><strong>{tx('API pendiente','API planned')}</strong></div>
      </div>
      <p className="sci-muted">{tx('Son formatos de exportación disponibles, no conexiones automáticas con instituciones.',
        'These are available export formats, not automatic institutional connections.')}</p>
    </section>

    <section className="sci-panel">
      <h3>{tx('Alcance y límites metodológicos','Scope and methodological limits')}</h3>
      <p className="sci-muted">{tx(
        'Los gráficos de confianza, precisión y presencia animal requieren un modelo de detección real y validación independiente. En Render Free solo hay filtrado visual de OpenCV. El seguimiento de individuos depende de revisión humana; las métricas 5G son estimaciones con entradas configurables.',
        'Detection confidence, accuracy and animal-presence charts require actual AI inference and independent validation. Render Free only runs OpenCV visual screening. Individual tracking needs human review; 5G metrics are estimates from configurable inputs.')}</p>
    </section>
  </div>;
}
