import React from 'react';
import {useLanguage} from './language';
import {Observation,downloadFile,toCsv,toGeoJSON} from './scienceShared';

type Props={records:Observation[];onOpenReports:()=>void};
export default function ScientificRecordsPanel({records,onOpenReports}:Props){
 const {language}=useLanguage();const tx=(es:string,en:string)=>language==='en'?en:es;
 const [selected,setSelected]=React.useState('all');
 const available=records.filter(x=>['researcher_validated','field_verified','verified'].includes(x.validation_status));
 const rows=selected==='validated'?available:records;
 return <div className="sci-screen scientific-records-panel">
 <div className="sci-heading"><div><span className="sci-kicker">SCIENTIFIC RECORDS / MONITORING</span>
 <h2>{tx('Investigación y exportaciones científicas','Research records and scientific exports')}</h2>
 <p>{tx('Registros, revisión de evidencia y formatos reproducibles de los estudios.','Study records, evidence review and reproducible outputs.')}</p></div></div>
     <section className="sci-panel">
      <div className="sci-panel-head"><h3>{tx('Informes y revisión científica','Scientific reporting and review')}</h3>
        <span className="sci-tag">PDF · ZIP</span></div>
      <p className="sci-muted">{tx('Generá un informe integral con el catálogo de jaguares, historial de encuentros, cámaras, notas y evidencias visuales; o descargá las tablas relacionadas para reproducibilidad.',
        'Generate a consolidated report with jaguar profiles, encounter history, camera deployments, notes and visual evidence; or download linked datasets for reproducibility.')}</p>
      {onOpenReports&&<button type="button" className="action-button" onClick={onOpenReports}>
        {tx('Abrir informes del estudio ↗','Open study reports ↗')}</button>}
    </section>
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
      <p className="sci-warning">{tx('Protección de datos: GeoJSON incluye coordenadas exactas. Generalizá u ocultá ubicaciones de especies sensibles antes de compartir resultados.',
        'Data protection: GeoJSON contains exact coordinates. Generalize or remove locations of sensitive species before sharing results.')}</p>
      <h3>{tx('Formatos institucionales','Institutional outputs')}</h3>
      <div className="sci-stats">
        <div><span>SINAC / GIS</span><strong>GeoJSON</strong></div>
        <div><span>{tx('Investigadores','Researchers')}</span><strong>CSV / JSON</strong></div>
        <div><span>CNE / Bomberos</span><strong>{tx('Integración futura','Future integration')}</strong></div>
        <div><span>{tx('Guardaparques','Rangers')}</span><strong>{tx('Integración futura','Future integration')}</strong></div>
      </div>
      <p className="sci-muted">{tx('Son formatos de exportación disponibles, no conexiones automáticas con instituciones.',
        'These are available export formats, not automatic institutional connections.')}</p>
    </section>


 </div>;
}
