import React from 'react';
import {useLanguage} from './language';
import {Observation,EdgeEvent,newObservation,numberOrNull,downloadFile,toCsv,toGeoJSON} from './scienceShared';

type Props={records:Observation[];current:Observation;setCurrent:(o:Observation)=>void;
  onSave:(o:Observation)=>void;onRemove:(id:string)=>void;events:EdgeEvent[]};

export default function MonitoringWorkspace({records,current,setCurrent,onSave,onRemove,events}:Props){
  const {language}=useLanguage();
  const tx=(es:string,en:string)=>language==='en'?en:es;
  const [notice,setNotice]=React.useState('');
  const [pdfBusy,setPdfBusy]=React.useState(false);
  const [showMap,setShowMap]=React.useState(false);
  const [removeId,setRemoveId]=React.useState('');
  const set=(key:keyof Observation,value:string|number|null)=>
    setCurrent({...current,[key]:value});
  const field=(key:keyof Observation,es:string,en:string,placeholder='',type='text')=>
    <label className="sci-field" key={key}>
      <span>{tx(es,en)}</span>
      <input type={type} value={String(current[key]??'')} maxLength={type==='text'?240:undefined}
        placeholder={placeholder} onChange={e=>{
          const v=e.target.value;
          set(key,['camera_latitude','camera_longitude','altitude_m','temperature_c','humidity_percent']
            .includes(key)?numberOrNull(v):v);
        }}/>
    </label>;
  const choose=(key:keyof Observation,es:string,en:string,options:{value:string;es:string;en:string}[])=>
    <label className="sci-field" key={key}><span>{tx(es,en)}</span>
      <select value={String(current[key]??'')} onChange={e=>set(key,e.target.value)}>
        {options.map(o=><option key={o.value} value={o.value}>{tx(o.es,o.en)}</option>)}
      </select></label>;
  const enumOptions=(items:[string,string,string][])=>items.map(([value,es,en])=>({value,es,en}));
  const validCoords=current.camera_latitude!==null&&current.camera_longitude!==null
    &&Math.abs(current.camera_latitude)<=90&&Math.abs(current.camera_longitude)<=180;
  const lat=current.camera_latitude??0,lon=current.camera_longitude??0;
  const bbox=[lon-.07,lat-.05,lon+.07,lat+.05].map(n=>n.toFixed(5)).join('%2C');
  const mapUrl='https://www.openstreetmap.org/export/embed.html?bbox='+bbox+
    '&layer=mapnik&marker='+lat.toFixed(6)+'%2C'+lon.toFixed(6);

  function save(){
    if(!current.observation_name.trim()||!current.camera_id.trim()){
      setNotice(tx('Indicá un nombre de observación y un ID de cámara.','Enter an observation name and camera ID.'));return;
    }
    if((current.camera_latitude!==null||current.camera_longitude!==null)&&!validCoords){
      setNotice(tx('Las coordenadas deben ser válidas o quedar ambas vacías.',
        'Coordinates must be valid or both left blank.'));return;
    }
    const complete={...current,source:'manual_researcher_entry',saved_at:new Date().toISOString()};
    onSave(complete);setCurrent(complete);
    setNotice(tx('Observación incorporada al registro de sesión.',
      'Observation added to the session registry.'));
  }

  async function generatePdf(){
    setPdfBusy(true);setNotice('');
    try{
      const response=await fetch('/api/science/reports/observation',{
        method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(current),
      });
      if(!response.ok){let text='HTTP '+response.status;
        try{const data=await response.json();text=data.detail||text;}catch{/* */}throw new Error(text);}
      const blob=await response.blob();
      downloadFile('PantheraMONITORING_'+current.observation_id+'.pdf',blob);
    }catch(err){setNotice(err instanceof Error?err.message:String(err));}
    finally{setPdfBusy(false);}
  }

  const individuals=new Set(records.map(r=>r.individual_id.trim()).filter(x=>x&&!['Unassigned','Unknown','unknown'].includes(x)));
  const knownCoords=records.filter(r=>r.camera_latitude!==null&&r.camera_longitude!==null).length;
  const annotations=new Map<string,number>();
  records.forEach(r=>{const key=r.species.trim()||tx('Sin anotación','Unannotated');annotations.set(key,(annotations.get(key)||0)+1);});

  return <div className="sci-screen">
    <div className="sci-heading"><div><span className="sci-kicker">PANTHERA LAB / SCIENTIFIC MONITORING</span>
      <h2>{tx('PantheraMONITORING · Registros científicos','PantheraMONITORING · Scientific records')}</h2>
      <p>{tx('Documentación de observaciones de cámaras trampa, variables de campo y revisión por investigadores.',
        'Camera-trap observation documentation, field variables and researcher review.')}</p></div>
      <span className="sci-tag">{tx('REGISTRO CIENTÍFICO','SCIENTIFIC REGISTRY')}</span></div>
    <div className="sci-inline-info" role="note">
      <span className="sci-info-dot" aria-hidden="true" />
      <p><strong>{tx('Almacenamiento de sesión','Session storage')}</strong> · {tx(
        'Las observaciones permanecen en esta pestaña. Exportá tus registros antes de cerrarla; todavía no hay sincronización con Supabase.',
        'Observations remain in this tab. Export records before closing it; Supabase synchronization is not enabled.')}</p>
    </div>

    <div className="sci-stats">
      <div><span>{tx('Observaciones guardadas','Saved observations')}</span><strong>{records.length}</strong></div>
      <div><span>{tx('Individuos anotados manualmente','Manually assigned individuals')}</span><strong>{individuals.size}</strong></div>
      <div><span>{tx('Registros georreferenciados','Georeferenced records')}</span><strong>{knownCoords}</strong></div>
      <div><span>{tx('Eventos Edge en sesión','Edge events in session')}</span><strong>{events.length}</strong></div>
    </div>

    <section className="sci-panel">
      <div className="sci-panel-head"><h3>{tx('Ficha de observación','Observation form')}</h3>
        <button type="button" className="sci-secondary" onClick={()=>{setCurrent(newObservation());setNotice('');}}>
          + {tx('Nueva observación','New observation')}</button></div>
      <p className="sci-muted">{tx('La especie e identidad individual son anotaciones humanas, no resultados automáticos de OpenCV.',
        'Species and individual identity are human annotations, not OpenCV classifications.')}</p>
      <div className="sci-fields">
        {field('observation_id','ID de observación','Observation ID')}
        {field('observation_name','Nombre de observación *','Observation name *','Ej. Encuentro de jaguar')}
        {field('camera_id','Cámara / estación *','Camera / station *','Ej. CT-07')}
        {field('study_site','Sitio de estudio','Study site','Ej. Península de Osa')}
        {field('observer','Observador / investigador','Observer / researcher')}
        {field('event_datetime_utc','Fecha/hora UTC (ISO 8601)','Event date/time UTC (ISO 8601)','2026-10-12T12:45:00Z')}
        {field('camera_latitude','Latitud WGS84','Latitude WGS84','9.7489','number')}
        {field('camera_longitude','Longitud WGS84','Longitude WGS84','-83.7534','number')}
        {field('altitude_m','Altitud (m)','Altitude (m)','—','number')}
        {field('temperature_c','Temperatura (°C)','Temperature (°C)','—','number')}
        {field('humidity_percent','Humedad relativa (%)','Relative humidity (%)','—','number')}
        {field('species','Especie (anotación)','Species (annotation)','Panthera onca')}
        {field('individual_id','ID individual asignado','Manually assigned individual ID','JAG-003')}
        {choose('sex','Sexo','Sex',enumOptions([['unknown','Desconocido','Unknown'],['female','Hembra','Female'],['male','Macho','Male'],['undetermined','Indeterminado','Undetermined']]))}
        {choose('age_class','Clase de edad','Age class',enumOptions([['unknown','Desconocida','Unknown'],['juvenile','Juvenil','Juvenile'],['subadult','Subadulto','Subadult'],['adult','Adulto','Adult'],['undetermined','Indeterminada','Undetermined']]))}
        {choose('viewpoint','Ángulo de observación','Viewpoint',enumOptions([['unknown','Desconocido','Unknown'],['left','Izquierdo','Left'],['right','Derecho','Right'],['frontal','Frontal','Frontal'],['rear','Posterior','Rear'],['other','Otro','Other']]))}
        {field('behavior','Comportamiento','Behavior','Ej. caminando, descansando')}
        {choose('validation_status','Estado de validación','Validation status',enumOptions([
          ['researcher_review_pending','Pendiente de revisión','Pending researcher review'],
          ['researcher_validated','Validado por investigador','Researcher validated'],
          ['field_verified','Verificado en campo','Field verified'],
          ['rejected','Rechazado','Rejected']]))}
        {field('edge_event_id','ID de evento PantheraEDGE','PantheraEDGE event ID')}
        {field('image_url','URL de evidencia fotográfica','Photo evidence URL','https://...')}
        {field('video_url','URL de video','Video URL','https://...')}
      </div>
      <div className="sci-fields sci-fields-2">
        <label className="sci-field"><span>{tx('Hábitat / microhábitat','Habitat / microhabitat')}</span>
          <textarea rows={3} value={current.habitat_notes} onChange={e=>set('habitat_notes',e.target.value)}
            placeholder={tx('Tipo de bosque, sendero, río, alteraciones…','Forest type, trail, river, disturbances…')}/></label>
        <label className="sci-field"><span>{tx('Notas de campo','Field notes')}</span>
          <textarea rows={3} value={current.notes} onChange={e=>set('notes',e.target.value)}
            placeholder={tx('Observaciones, condiciones e incertidumbre','Observations, conditions, uncertainty')}/></label>
      </div>
      {validCoords&&<div className="sci-map-toggle">
        <button type="button" className="sci-secondary" onClick={()=>setShowMap(!showMap)}>
          {showMap?tx('Ocultar mapa','Hide map'):tx('Ver estación en OpenStreetMap','Show station on OpenStreetMap')}</button>
        <small>{tx('El mapa envía coordenadas a OpenStreetMap al abrirlo. No compartás ubicaciones protegidas.',
          'Opening this map sends coordinates to OpenStreetMap. Do not share protected locations.')}</small>
        {showMap&&<iframe title={tx('Mapa de cámara','Camera map')} className="sci-map"
          loading="lazy" referrerPolicy="no-referrer" src={mapUrl}/>}
      </div>}
      {notice&&<p className="sci-notice" role="status">{notice}</p>}
      <div className="sci-actions">
        <button type="button" className="action-button" onClick={save}>{tx('Guardar observación','Save observation')}</button>
        <button type="button" className="sci-secondary" disabled={pdfBusy} onClick={()=>void generatePdf()}>
          {pdfBusy?tx('Creando PDF…','Generating PDF…'):tx('Descargar informe PDF','Download PDF report')}</button>
        <button type="button" className="sci-secondary" onClick={()=>downloadFile(current.observation_id+'.json',
          JSON.stringify(current,null,2),'application/json')}>JSON ↓</button>
        <button type="button" className="sci-secondary" onClick={()=>downloadFile(current.observation_id+'.geojson',
          JSON.stringify(toGeoJSON([current]),null,2),'application/geo+json')}>GeoJSON ↓</button>
      </div>
    </section>

    <section className="sci-panel">
      <div className="sci-panel-head"><h3>{tx('Registro de observaciones','Observation registry')}</h3>
        <span className="sci-tag">{records.length} {tx('registros','records')}</span></div>
      {records.length===0?<p className="sci-muted">{tx('Todavía no hay observaciones guardadas en esta pestaña.',
        'No observations saved in this tab yet.')}</p>:
      <><div className="sci-table-wrap"><table className="sci-table">
        <thead><tr><th>ID</th><th>{tx('Cámara','Camera')}</th><th>{tx('Sitio','Site')}</th>
          <th>{tx('Especie anotada','Annotated species')}</th><th>{tx('Estado','Status')}</th><th>{tx('Acción','Action')}</th></tr></thead>
        <tbody>{records.map(record=><tr key={record.observation_id}>
          <td>{record.observation_id}</td><td>{record.camera_id}</td><td>{record.study_site||'—'}</td>
          <td><i>{record.species||'—'}</i></td><td>{record.validation_status}</td>
          <td><button type="button" className="sci-inline" onClick={()=>{setCurrent({...record});window.scrollTo({top:0,behavior:'smooth'});}}>
            {tx('Editar','Edit')}</button></td></tr>)}</tbody>
      </table></div>
      <div className="sci-actions">
        <button type="button" className="sci-secondary" onClick={()=>downloadFile('PantheraMONITORING_observaciones.json',
          JSON.stringify(records,null,2),'application/json')}>JSON ↓</button>
        <button type="button" className="sci-secondary" onClick={()=>downloadFile('PantheraMONITORING_observaciones.csv',
          toCsv(records as unknown as Record<string,unknown>[]),'text/csv;charset=utf-8')}>CSV ↓</button>
        <button type="button" className="sci-secondary" onClick={()=>downloadFile('PantheraMONITORING_observaciones.geojson',
          JSON.stringify(toGeoJSON(records),null,2),'application/geo+json')}>GeoJSON ↓</button>
      </div>
      <div className="sci-delete"><label className="sci-field"><span>{tx('Seleccionar observación para eliminar','Select observation to delete')}</span>
        <select value={removeId} onChange={e=>setRemoveId(e.target.value)}>
          <option value="">{tx('Seleccionar…','Select…')}</option>
          {records.map(r=><option key={r.observation_id} value={r.observation_id}>{r.observation_id}</option>)}
        </select></label><button type="button" className="sci-secondary sci-danger" disabled={!removeId}
          onClick={()=>{if(window.confirm(tx('¿Eliminar esta observación de la sesión?','Delete this observation from this session?'))){
            onRemove(removeId);setRemoveId('');}}}>{tx('Eliminar registro','Delete record')}</button></div></>}
    </section>
    <details className="method-details method-details-compact">
      <summary>{tx('Protección de coordenadas y trazabilidad','Coordinate protection and traceability')}</summary>
      <p>{tx('Las coordenadas de fauna sensible pueden requerir restricción o generalización antes de compartir archivos JSON, CSV y GeoJSON. La especie, el ID individual y la validación de registros son anotaciones de investigación, no identificaciones automáticas.',
        'Sensitive wildlife coordinates may require restricted access or generalization before sharing JSON, CSV and GeoJSON files. Species, individual IDs and validation are researcher annotations, not automatic identifications.')}</p>
    </details>
    {records.length>0&&<section className="sci-panel">
      <h3>{tx('Resumen de especies anotadas','Annotated species summary')}</h3>
      <p className="sci-muted">{tx('Frecuencias de anotaciones manuales, no conteos automatizados de individuos ni abundancia poblacional.',
        'Counts of manual annotations, not automated individual counts or population abundance.')}</p>
      {[...annotations.entries()].sort((a,b)=>b[1]-a[1]).map(([name,count])=>
        <div className="sci-bar-row" key={name}><span>{name}</span>
          <div className="sci-bar-track"><div style={{width:(100*count/records.length)+'%'}}/></div>
          <strong>{count}</strong></div>)}
    </section>}
  </div>;
}
