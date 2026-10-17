import React from 'react';
import {useLanguage} from './language';
import type {Deployment,Encounter,Individual,Sighting} from './researchData';
import './StudyStatistics.css';

type Props={deployments:Deployment[];encounters:Encounter[];individuals:Individual[];sightings:Sighting[]};
type Count={label:string;count:number};
function countValues(rows:string[]):Count[]{
  const totals=new Map<string,number>();
  rows.forEach(label=>{const k=label.trim()||'—';totals.set(k,(totals.get(k)||0)+1);});
  return Array.from(totals,([label,count])=>({label,count}))
    .sort((a,b)=>b.count-a.count||a.label.localeCompare(b.label));
}
function DataBars({items,empty}:{items:Count[];empty:string}){
  const top=items.slice(0,9),max=Math.max(1,...top.map(x=>x.count));
  if(!top.length)return <p className="sci-muted">{empty}</p>;
  return <div className="study-stat-bars">{top.map(row=>
    <div className="study-stat-line" key={row.label}>
      <span title={row.label}>{row.label}</span>
      <div className="study-stat-track" aria-hidden="true">
        <span style={{width:(100*row.count/max)+'%'}}/>
      </div>
      <strong>{row.count}</strong>
    </div>)}</div>;
}
export default function StudyStatistics({deployments,encounters,individuals,sightings}:Props){
  const {language}=useLanguage(),tx=(es:string,en:string)=>language==='en'?en:es;
  const cameras=new Map(deployments.map(d=>[d.deployment_id,d.camera_id||d.deployment_id]));
  const perCamera=countValues(encounters.map(e=>cameras.get(e.deployment_id)||tx('Sin cámara','No camera')));
  const perSpecies=countValues(sightings.map(s=>s.species||tx('Sin identificar','Unidentified')));
  const perMonth=countValues(encounters.map(e=>
    /^\d{4}-\d{2}/.test(e.occurred_at)?e.occurred_at.slice(0,7):tx('Fecha desconocida','Unknown date')))
    .sort((a,b)=>a.label.localeCompare(b.label));
  const statuses=countValues(sightings.map(s=>s.identification_status==='verified'
    ?tx('Verificada','Verified'):s.identification_status==='tentative'
      ?tx('Provisional','Tentative'):tx('Sin identificar','Unidentified')));
  const verified=new Set(sightings.filter(s=>s.identification_status==='verified'&&
    individuals.some(p=>p.individual_id===s.individual_id&&p.status==='verified')).map(s=>s.individual_id)).size;
  const effortComplete=deployments.length>0&&deployments.every(d=>
    typeof d.operational_days==='number'&&Number.isFinite(d.operational_days)&&d.operational_days>=0);
  const cameraDays=effortComplete?deployments.reduce((sum,d)=>sum+(d.operational_days||0),0):null;
  const rate=cameraDays!==null&&cameraDays>0?(100*encounters.length/cameraDays):null;
  return <section className="sci-panel study-statistics">
    <div className="sci-panel-head"><h3>{tx('Resultados descriptivos del estudio','Study descriptive results')}</h3></div>
    <div className="sci-stats">
      <div><span>{tx('Capturas','Capture events')}</span><strong>{encounters.length}</strong></div>
      <div><span>{tx('Observaciones','Sightings')}</span><strong>{sightings.length}</strong></div>
      <div><span>{tx('Individuos verificados','Verified individuals')}</span><strong>{verified}</strong></div>
      <div><span>{tx('Días-cámara declarados','Reported camera-days')}</span>
        <strong>{cameraDays===null?'—':cameraDays}</strong></div>
    </div>
    <div className="study-stat-grid">
      <div><h4>{tx('Observaciones anotadas por especie','Annotated sightings by species')}</h4>
        <DataBars items={perSpecies} empty={tx('Sin observaciones.','No sightings.')}/></div>
      <div><h4>{tx('Capturas por cámara','Capture events by camera')}</h4>
        <DataBars items={perCamera} empty={tx('Sin capturas.','No capture events.')}/></div>
      <div><h4>{tx('Capturas por mes (UTC)','Capture events by month (UTC)')}</h4>
        <DataBars items={perMonth} empty={tx('Sin fechas de captura.','No capture dates.')}/></div>
      <div><h4>{tx('Estado de las identificaciones','Identification review status')}</h4>
        <DataBars items={statuses} empty={tx('Sin identificaciones.','No identifications.')}/></div>
    </div>
    {rate!==null&&<p className="sci-muted">{tx(
      'Índice descriptivo: '+rate.toFixed(2)+' eventos registrados por 100 días-cámara declarados. No representa abundancia ni detección independiente.',
      'Descriptive index: '+rate.toFixed(2)+' recorded events per 100 reported camera-days. Not an estimate of abundance or independent detections.'
    )}</p>}
    <p className="sci-muted">{tx(
      'Estas gráficas usan solamente capturas, observaciones y estaciones del estudio local seleccionado. Los datos simulados de PantheraSENSE, consultas temporales de PantheraSAT y bibliotecas Supabase no se incorporan automáticamente.',
      'These charts use only local capture events, sightings, and deployments from the selected study. Simulated PantheraSENSE readings, temporary PantheraSAT queries, and Supabase libraries are not automatically included.'
    )}</p>
  </section>;
}
