import React from 'react';
import {useLanguage} from './language';
import {apiJson,downloadFile} from './scienceShared';

type Scene={
  scene_id:string;
  acquired_at:string;
  cloud_cover_scene_pct:number|null;
  valid_pixel_fraction:number;
  sampled_valid_pixels:number;
  ndvi_mean:number;
  ndmi_mean:number;
  ndvi_greater_0_4_pct:number;
};
type VegetationResult={
  source:string;
  tree_cover_source:string;
  analysis_type:'real_pixel_sample_experimental';
  queried_at_utc:string;
  radius_km:number;
  grid_size:string;
  latest:Scene;
  previous:Scene|null;
  ndvi_mean_change_between_scenes:number|null;
  tree_cover_worldcover_2021_pct:number|null;
  warnings:string[];
  limitations:string;
};

type Props={latitude:string;longitude:string;maxCloudCover:number};

export default function VegetationPanel({latitude,longitude,maxCloudCover}:Props){
  const {language}=useLanguage();
  const tx=(es:string,en:string)=>language==='en'?en:es;
  const [radius,setRadius]=React.useState(0.5);
  const [days,setDays]=React.useState(90);
  const [busy,setBusy]=React.useState(false);
  const [error,setError]=React.useState('');
  const [result,setResult]=React.useState<VegetationResult|null>(null);

  // Results must not silently persist when the user changes sensitive coordinates.
  React.useEffect(()=>{setResult(null);setError('');},[latitude,longitude,radius,days,maxCloudCover]);

  async function analyze(){
    const lat=Number(latitude),lon=Number(longitude);
    if(!latitude.trim()||!longitude.trim()||!Number.isFinite(lat)||!Number.isFinite(lon)||
       lat < -85||lat > 85||lon < -180||lon > 180){
      setError(tx('Ingresá primero coordenadas WGS84 válidas en el panel Copernicus de arriba.',
        'Enter valid WGS84 coordinates in the Copernicus form above.'));
      return;
    }
    setBusy(true);setError('');setResult(null);
    try{
      const data=await apiJson<VegetationResult>(
        '/api/science/vegetation/analyze','POST',{
          latitude:lat,longitude:lon,radius_km:radius,days_back:days,
          max_cloud_cover:Math.min(80,maxCloudCover),
        }
      );
      if(data.analysis_type!=='real_pixel_sample_experimental'){
        throw new Error(tx('El servidor no devolvió un análisis real reconocido.',
          'Server did not return a recognized real-data analysis.'));
      }
      setResult(data);
    }catch(err){
      setError(err instanceof Error?err.message:String(err));
    }finally{setBusy(false);}
  }

  const display=(num:number|null|undefined,unit='')=>num===null||num===undefined?
    '—':num.toLocaleString(language==='en'?'en-US':'es-CR',{
      minimumFractionDigits:unit==='%'?1:3,
      maximumFractionDigits:unit==='%'?1:3,
    })+unit;

  return <section className="sci-panel vegetation-panel">
    <div className="sci-panel-head">
      <div>
        <span className="sci-kicker">SENTINEL-2 L2A · ESA WORLDCOVER 2021</span>
        <h3>{tx('Vegetación y hábitat · análisis de bandas reales',
           'Vegetation and habitat · real spectral band analysis')}</h3>
        <p className="sci-muted">{tx(
          'Analizá reflectancia satelital abierta con máscara de nubes para estimar NDVI y NDMI, más cobertura arbórea histórica de WorldCover.',
          'Analyze open satellite reflectance with cloud masking to estimate NDVI and NDMI, plus historic WorldCover tree-cover classification.')}</p>
      </div>
      <span className="sci-tag">{tx('DATOS REALES · EXPERIMENTAL','REAL DATA · EXPERIMENTAL')}</span>
    </div>
    <div className="sci-fields sci-fields-2">
      <label className="sci-field">
        <span>{tx('Radio de análisis','Analysis radius')} · {radius} km</span>
        <input type="range" min="0.2" max="2" step="0.1" value={radius}
          onChange={e=>setRadius(Number(e.target.value))}/>
      </label>
      <label className="sci-field">
        <span>{tx('Buscar escenas de los últimos','Look back')} {days} {tx('días','days')}</span>
        <input type="range" min="15" max="180" step="15" value={days}
          onChange={e=>setDays(Number(e.target.value))}/>
      </label>
    </div>
    <p className="sci-muted">{tx(
      'Toma las coordenadas y el límite de nubosidad del formulario de arriba. Estas coordenadas se envían a Earth Search y los servidores de imágenes de AWS. Evitá ubicaciones sensibles de fauna sin autorización.',
      'Uses the coordinates and cloud limit from the form above. Coordinates are shared with Earth Search and imagery hosts on AWS. Avoid sensitive wildlife locations without permission.')}</p>
    <div className="sci-actions">
      <button type="button" className="action-button" disabled={busy} onClick={()=>void analyze()}>
        {busy?tx('Procesando escenas reales…','Processing real imagery…'):
          tx('Calcular índices de vegetación ↗','Calculate vegetation indices ↗')}
      </button>
    </div>
    {error&&<p className="sci-notice" role="alert">{error}</p>}
    {busy&&<p className="sci-muted" role="status">{tx(
      'Descargando solamente ventanas pequeñas de bandas espectrales. Puede tardar por el servidor gratuito.',
      'Reading small windows of spectral bands. The free server may take a while.')}</p>}
    {result&&<div className="vegetation-result">
      <div className="sci-stats">
        <div><span>NDVI · {tx('promedio','mean')}</span><strong>{display(result.latest.ndvi_mean)}</strong></div>
        <div><span>NDMI · {tx('promedio','mean')}</span><strong>{display(result.latest.ndmi_mean)}</strong></div>
        <div><span>{tx('Píxeles válidos','Valid pixels')}</span>
          <strong>{display(result.latest.valid_pixel_fraction*100,'%')}</strong></div>
        <div><span>{tx('Área clasificada como árboles en 2021','Area classified as trees in 2021')}</span>
          <strong>{display(result.tree_cover_worldcover_2021_pct,'%')}</strong></div>
      </div>
      <p className="sci-muted">
        {tx('Escena','Scene')}: <code>{result.latest.scene_id}</code> · {tx('Adquirida','Acquired')}:
        {' '}{result.latest.acquired_at||'—'} ·
        {' '}{tx('Nubosidad de la escena','Scene cloud cover')}:
        {' '}{display(result.latest.cloud_cover_scene_pct,'%')}
      </p>
      <p className="sci-muted">
        {tx('Proporción de píxeles válidos con NDVI > 0,4','Valid-pixel share with NDVI > 0.4')}:
        {' '}<strong>{display(result.latest.ndvi_greater_0_4_pct,'%')}</strong>.
        {' '}{tx('Este umbral de verdor NO representa porcentaje de bosque.',
          'This greenness threshold is NOT a forest-cover percentage.')}
      </p>
      {result.previous&&<p className="sci-muted">
        {tx('Escena anterior','Previous scene')}: {result.previous.acquired_at} ·
        {' '}{tx('Diferencia de NDVI medio (reciente − anterior)','Mean NDVI difference (newer − older)')}:
        {' '}<strong>{display(result.ndvi_mean_change_between_scenes)}</strong>.
        {' '}{tx('No equivale a deforestación.','Not equivalent to deforestation.')}
      </p>}
      {result.warnings.length>0&&<div className="sci-warning" role="note">
        {result.warnings.map((note,i)=><p key={i}>{note}</p>)}
      </div>}
      <p className="sci-warning">{tx(
        'WorldCover 2021 clase 10 incluye cobertura arbórea clasificada (también plantaciones): NO es un mapa actual de bosque ni de pérdida forestal. La comparación de índices entre dos fechas no prueba deforestación. El análisis excluye píxeles de nubes/sombras con SCL y muestrea una cuadrícula limitada.',
        'WorldCover 2021 class 10 includes mapped tree cover (also plantations): NOT a current forest or forest-loss map. An index difference between two dates is not proof of deforestation. Cloud/shadow pixels are filtered with SCL and the area is sampled on a bounded grid.')}</p>
      <div className="sci-actions">
        <button className="sci-secondary" type="button" onClick={()=>downloadFile(
          'PantheraLAB_vegetacion_Sentinel2.json',JSON.stringify(result,null,2),'application/json')}>
          {tx('Exportar datos y método (JSON) ↓','Export data and method (JSON) ↓')}
        </button>
      </div>
      <p className="sci-muted">{tx('Fuentes: Element 84 Earth Search / Sentinel-2 L2A y ESA WorldCover 2021, bajo sus condiciones de uso y atribución.',
        'Sources: Element 84 Earth Search / Sentinel-2 L2A and ESA WorldCover 2021, subject to their licenses and attribution requirements.')}</p>
    </div>}
  </section>;
}
