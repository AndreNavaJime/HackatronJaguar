import React from 'react';
import VegetationPanel from './VegetationPanel';
import StarlinkSimulator from './StarlinkSimulator';
import {useLanguage} from './language';
import {Observation,SatelliteData,SatelliteItem,apiJson,downloadFile,toCsv} from './scienceShared';

type Props={current:Observation};

export default function ResearchWorkspace({current}:Props){
  const {language}=useLanguage(),tx=(es:string,en:string)=>language==='en'?en:es;
  const [latitude,setLatitude]=React.useState(String(current.camera_latitude??''));
  const [longitude,setLongitude]=React.useState(String(current.camera_longitude??''));
  const [radius,setRadius]=React.useState(5);
  const [days,setDays]=React.useState(30);
  const [cloud,setCloud]=React.useState(40);
  const [busy,setBusy]=React.useState(false);
  const [error,setError]=React.useState('');
  const [satellite,setSatellite]=React.useState<SatelliteData|null>(null);
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
    <div className="sci-heading"><div><span className="sci-kicker">PANTHERASAT / COPERNICUS / ESA SENTINEL</span>
      <h2>{tx('PantheraSAT · Observación y conectividad satelital','PantheraSAT · Earth observation and satellite connectivity')}</h2>
      <p>{tx('Adquisiciones Sentinel-1 y Sentinel-2, análisis de vegetación y simulación de conectividad Starlink.',
        'Sentinel-1 and Sentinel-2 acquisitions, vegetation analysis and Starlink connectivity simulation.')}</p></div>
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
        <p className="sci-warning">{tx('El catálogo aporta fechas y características de adquisición. La interpretación de cambios ecológicos requiere procesamiento y verificación independientes.',
          'The catalogue provides acquisition dates and metadata. Ecological change assessment requires separate processing and validation.')}</p>
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

    <VegetationPanel latitude={latitude} longitude={longitude} maxCloudCover={cloud}/>

    <StarlinkSimulator />

    <details className="method-details research-method-details">
      <summary>{tx('Alcance y criterios metodológicos','Scope and methodological guidance')}</summary>
      <p>{tx(
        'La consulta Sentinel devuelve metadatos del catálogo, no índices ambientales calculados. La evaluación de presencia animal y las estadísticas de confianza requieren modelos de detección validados; el análisis visual disponible utiliza OpenCV. Los identificadores individuales provienen de anotaciones de investigadores. Los indicadores 4G/5G son estimaciones a partir de valores proporcionados.',
        'Sentinel queries return catalogue metadata, not derived environmental indices. Wildlife presence and detection-confidence statistics require validated models; the available visual analysis uses OpenCV. Individual identifiers are researcher annotations. 4G/5G values are estimates based on supplied inputs.')}</p>
    </details>
  </div>;
}
