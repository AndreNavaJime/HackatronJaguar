import React from 'react';
import {useLanguage} from './language';
import {apiJson, downloadFile, EdgeEvent} from './scienceShared';
import './AutoCapturesPanel.css';

type Counts={animal:number;person:number;vehicle:number};
type Frame={
  sample:number;time_seconds:number;retained:boolean;counts:Counts;
  max_animal_confidence:number;image:string;
  detections:{class_name:string;confidence:number}[];
};
type VideoResult={
  metadata:{filename:string;model:string;duration_seconds:number;sampling_strategy?:string;threshold:number};
  totals:{sampled:number;animals:number;persons:number;vehicles:number};
  frames:Frame[];note:string;
};
type Job={
  state:'uploading'|'processing'|'completed'|'failed';
  stage:string;processed:number;total:number;error:string|null;result:VideoResult|null;
};
type ReviewState='accepted'|'discarded'|'human_review';
type Props={onEvent:(event:EdgeEvent)=>void};

const MAX_SIZE=250*1024*1024;
const CHUNK_SIZE=5*1024*1024;
async function readJson(response:Response):Promise<any>{
  let body:any;
  try{body=await response.json();}catch{throw new Error('El servidor no devolvió JSON válido.');}
  if(!response.ok)throw new Error(typeof body?.detail==='string'?body.detail:'HTTP '+response.status);
  return body;
}
function clock(seconds:number){const min=Math.floor(seconds/60);return String(min).padStart(2,'0')+':'+String(Math.floor(seconds%60)).padStart(2,'0');}
function highest(frame:Frame,cls:string){return Math.max(0,...frame.detections.filter(d=>d.class_name===cls).map(d=>d.confidence));}

export default function AutoCapturesPanel({onEvent}:Props){
  const {language}=useLanguage();
  const tx=(es:string,en:string)=>language==='en'?en:es;
  const [file,setFile]=React.useState<File|null>(null);
  const [fileKey,setFileKey]=React.useState(0);
  const [previewUrl,setPreviewUrl]=React.useState('');
  const [camera,setCamera]=React.useState('CAM-PRUEBA-01');
  const [permission,setPermission]=React.useState(false);
  const [threshold,setThreshold]=React.useState(.25);
  const [sampleCount,setSampleCount]=React.useState(12);
  const [jobId,setJobId]=React.useState('');
  const [state,setState]=React.useState<'idle'|'uploading'|'processing'|'completed'|'failed'>('idle');
  const [job,setJob]=React.useState<Job|null>(null);
  const [result,setResult]=React.useState<VideoResult|null>(null);
  const [reviews,setReviews]=React.useState<Record<number,ReviewState>>({});
  const [revealed,setRevealed]=React.useState<Record<number,boolean>>({});
  const [showEmpty,setShowEmpty]=React.useState(false);
  const [showPlayer,setShowPlayer]=React.useState(false);
  const [bytes,setBytes]=React.useState(0);
  const [message,setMessage]=React.useState('');
  const [action,setAction]=React.useState(0);
  const [busyReview,setBusyReview]=React.useState<number|null>(null);
  const player=React.useRef<HTMLVideoElement>(null);
  const busy=state==='uploading'||state==='processing';

  React.useEffect(()=>{
    if(!file){setPreviewUrl('');return;}
    const url=URL.createObjectURL(file);
    setPreviewUrl(url);
    return ()=>URL.revokeObjectURL(url);
  },[file]);

  React.useEffect(()=>{
    if(state!=='processing'||!jobId)return;
    let active=true;
    let failedPolls=0;
    async function poll(){
      try{
        const next=await readJson(await fetch('/api/videos/jobs/'+encodeURIComponent(jobId),{cache:'no-store'})) as Job;
        if(!active)return;
        failedPolls=0;setJob(next);
        if(next.state==='completed'){
          if(!next.result)throw new Error(tx('El análisis terminó sin resultados.','Analysis returned no result.'));
          setResult(next.result);setMessage('');setState('completed');
        }else if(next.state==='failed'){
          setState('failed');setMessage(next.error||tx('No se pudo analizar el video.','Video analysis failed.'));
        }
      }catch(error){
        if(!active)return;
        failedPolls++;
        if(failedPolls>=4)setMessage(tx(
          'No se ha podido consultar el servidor. El trabajo podría seguir procesándose. No iniciés otro análisis todavía.',
          'The server cannot be reached. Processing may still be running. Do not start another analysis yet.'));
      }
    }
    void poll();const timer=window.setInterval(()=>void poll(),2500);
    return ()=>{active=false;window.clearInterval(timer);};
  },[state,jobId,language]);

  function choose(next:File|null){
    if(state!=='idle'&&jobId){
      setMessage(tx('Eliminá primero el análisis anterior del servidor para seleccionar otro video.',
        'Delete the previous server analysis before selecting another video.'));
      return;
    }
    setFile(next);setPermission(false);setResult(null);setReviews({});
    setRevealed({});setShowPlayer(false);setMessage('');setBytes(0);
  }

  async function upload(){
    if(!file||busy||!permission)return;
    if(file.size>MAX_SIZE){setMessage(tx('Máximo 250 MB.','Maximum 250 MB.'));return;}
    if(!/\.(mp4|mov|avi|mkv)$/i.test(file.name)){
      setMessage(tx('Usá un archivo MP4, MOV, AVI o MKV.','Use an MP4, MOV, AVI or MKV file.'));return;
    }
    setState('uploading');setMessage('');setBytes(0);
    let uploadId='';
    try{
      const params=new URLSearchParams({mode:'megadetector',sampling_strategy:'spread',
        threshold:threshold.toFixed(2),sample_seconds:'1',max_samples:String(sampleCount)});
      const start=await readJson(await fetch('/api/videos/uploads?'+params.toString(),{
        method:'POST',headers:{'X-Video-Name':encodeURIComponent(file.name),'X-Video-Size':String(file.size)},
      })) as {upload_id:string;chunk_max_bytes?:number};
      uploadId=start.upload_id;
      if(!uploadId)throw new Error(tx('El servidor no creó la carga.','No upload session was created.'));
      let offset=0;const limit=Math.min(CHUNK_SIZE,start.chunk_max_bytes||CHUNK_SIZE);
      while(offset<file.size){
        const end=Math.min(file.size,offset+limit);
        const reply=await readJson(await fetch(
          '/api/videos/uploads/'+encodeURIComponent(uploadId)+'/chunks?offset='+offset,
          {method:'PUT',headers:{'Content-Type':'application/octet-stream'},body:file.slice(offset,end)}
        )) as {received_bytes:number};
        if(reply.received_bytes!==end)throw new Error(tx('Un bloque llegó incompleto.','A chunk was incomplete.'));
        offset=end;setBytes(offset);
      }
      const ready=await readJson(await fetch(
        '/api/videos/uploads/'+encodeURIComponent(uploadId)+'/complete',{method:'POST'}
      )) as {job_id:string};
      if(!ready.job_id)throw new Error(tx('El análisis no comenzó.','Analysis was not started.'));
      setJobId(ready.job_id);setState('processing');
    }catch(error){
      if(uploadId)try{await fetch('/api/videos/uploads/'+encodeURIComponent(uploadId),{method:'DELETE'});}catch{/* expires */}
      setState('failed');setMessage(error instanceof Error?error.message:String(error));
    }
  }

  async function erase(){
    if(!jobId){
      setFile(null);setState('idle');setMessage('');setFileKey(k=>k+1);return;
    }
    if(busy){setMessage(tx('Esperá a que termine la carga o el procesamiento para borrar.',
      'Wait for the upload or processing to finish before deleting.'));return;}
    setAction(x=>x+1);setMessage('');
    try{
      const response=await fetch('/api/videos/jobs/'+encodeURIComponent(jobId),{method:'DELETE'});
      if(!response.ok&&response.status!==404)await readJson(response);
      setJobId('');setFile(null);setResult(null);setJob(null);setReviews({});
      setRevealed({});setShowPlayer(false);setPermission(false);setState('idle');
      setFileKey(k=>k+1);
      setMessage(tx('Archivo y resultados temporales eliminados del servidor; las anotaciones que ya enviaste a Eventos siguen en esa sesión.',
        'Temporary footage and analysis deleted; metadata already sent to Session events remains there.'));
    }catch(error){
      setMessage(tx('No se pudo confirmar el borrado en el servidor: ',
        'Server deletion could not be confirmed: ')+(error instanceof Error?error.message:String(error)));
    }finally{setAction(x=>Math.max(0,x-1));}
  }

  async function accept(frame:Frame){
    if(!frame.counts.animal||frame.counts.person){
      setMessage(tx('No se permite transferir automáticamente imágenes con personas al registro científico.',
        'Frames with people cannot be sent automatically to scientific records.'));return;
    }
    if(busyReview!==null||reviews[frame.sample])return;
    setBusyReview(frame.sample);setMessage('');
    try{
      const raw={
        contract_version:'panthera-v1.0',
        event_id:'VIDEO-'+Date.now().toString(36).toUpperCase()+'-'+frame.sample,
        timestamp:new Date().toISOString(), camera_id:camera.trim()||'CAM-PRUEBA-01',
        event_type:'animal_candidate_reviewed',status:'REVIEWED_ANIMAL',
        class:'animal',confidence:frame.max_animal_confidence,
        transport:'manual_video_upload',source:'reviewed_megadetector_sample',
      };
      const reply=await apiJson<{event:EdgeEvent;verification:string}>('/api/edge/validate','POST',raw);
      onEvent(reply.event);
      setReviews(previous=>({...previous,[frame.sample]:'accepted'}));
      setMessage(tx('Metadatos enviados a Eventos de la sesión. No se ha guardado el clip en MONITORING ni se ha identificado la especie.',
        'Metadata added to Session events. No clip was stored in MONITORING and no species was identified.'));
    }catch(error){
      setMessage(error instanceof Error?error.message:String(error));
    }finally{setBusyReview(null);}
  }

  function playAt(seconds:number){
    if(!previewUrl)return;
    setShowPlayer(true);
    window.setTimeout(()=>{
      if(!player.current)return;
      player.current.currentTime=Math.max(0,seconds-2);
      void player.current.play().catch(()=>{});
    },100);
  }

  const frames=result?.frames??[];
  const positives=frames.filter(f=>f.counts.animal>0||f.counts.person>0);
  const shown=showEmpty?frames:positives;
  const pending=positives.filter(f=>!reviews[f.sample]).length;
  const exportRows=frames.map(f=>({
    camera_id:camera,source_filename:result?.metadata.filename,
    sample:f.sample,time_seconds:f.time_seconds,animals:f.counts.animal,
    persons:f.counts.person,vehicles:f.counts.vehicle,
    max_animal_confidence:f.max_animal_confidence,
    review:reviews[f.sample]||'pending',
    method:'MegaDetector V6 - sampled frames',species_verified:false,
  }));

  return <section className="sci-panel auto-captures" aria-label={tx('Capturas automáticas','Automatic captures')}>
    <div className="sci-panel-head">
      <h3>{tx('Capturas automáticas · Revisión de eventos','Automatic captures · Event review')}</h3>
      <span className="sci-tag">{tx('PRUEBA CON VIDEO','VIDEO FILE TEST')}</span>
    </div>
    <p className="sci-muted">{tx(
      'Ensayá el flujo de una cámara con un video grabado: MegaDetector examina fotogramas distribuidos en el clip, separa posibles animales/personas y permite que una persona científica revise cada muestra.',
      'Test a camera workflow with a recorded video: MegaDetector examines distributed frames, flags possible animals/people and lets a researcher review each sample.')}</p>
    <div className="sci-inline-info" role="note"><span className="sci-info-dot" aria-hidden="true"/>
      <p><strong>{tx('Alcance real','Current scope')}</strong> · {tx(
        'No hay cámara en directo ni guardado automático de clips individuales. Los fotogramas se procesan en el servidor temporal; el video original se reproduce localmente. Requiere MegaDetector instalado en el backend, sin resultados simulados.',
        'No live camera or automatic saving of individual clips. Sampled frames are processed on a temporary server; the original video plays locally. MegaDetector must be installed on the backend; no simulated detections.')}</p>
    </div>
    <div className="sci-fields sci-fields-2 auto-config">
      <label className="sci-field"><span>{tx('Video de prueba (MP4, MOV, AVI, MKV)','Test video (MP4, MOV, AVI, MKV)')}</span>
        <input key={fileKey} type="file" accept=".mp4,.mov,.avi,.mkv,video/*" disabled={busy||!!jobId}
          onChange={e=>choose(e.target.files?.[0]??null)}/></label>
      <label className="sci-field"><span>{tx('Cámara / referencia','Camera / reference')}</span>
        <input value={camera} disabled={busy} maxLength={80} onChange={e=>setCamera(e.target.value)}/></label>
      <label className="sci-field"><span>{tx('Umbral de detección','Detection threshold')}: {Math.round(threshold*100)}%</span>
        <input type="range" min=".1" max=".9" step=".05" value={threshold} disabled={busy||!!jobId}
          onChange={e=>setThreshold(Number(e.target.value))}/></label>
      <label className="sci-field"><span>{tx('Fotogramas distribuidos por el video','Frames spread across video')}</span>
        <select value={sampleCount} disabled={busy||!!jobId} onChange={e=>setSampleCount(Number(e.target.value))}>
          <option value={8}>8</option><option value={12}>12</option><option value={24}>24</option>
        </select></label>
    </div>
    <p className="sci-muted">{tx(
      'Recomendación inicial: videos de 10–30 segundos. En videos largos solo se muestrean hasta 24 fotogramas; una detección negativa NO demuestra ausencia de animales. Una persona y un animal pueden aparecer en una misma muestra.',
      'Recommended first test: 10–30-second videos. In long videos only up to 24 frames are sampled; negative results do NOT prove the absence of wildlife. People and animals may appear in the same frame.')}</p>
    <label className="auto-consent"><input type="checkbox" checked={permission} disabled={busy||!!jobId}
      onChange={e=>setPermission(e.target.checked)}/>
      <span>{tx(
        'Confirmo que tengo autorización para enviar este video al servidor temporal de prueba. No utilizar grabaciones privadas de personas ni material sensible en el servidor público.',
        'I confirm I am authorized to upload this footage to the temporary test server. Do not upload private recordings of people or sensitive material to the public server.')}</span>
    </label>
    <div className="sci-actions auto-actions">
      <button className="action-button" type="button" disabled={!file||!permission||busy||!!jobId}
        onClick={()=>void upload()}>{tx('Analizar y preparar revisión','Analyze and prepare review')}</button>
      {(!!jobId||state==='failed')&&<button className="sci-secondary" type="button" disabled={busy||action>0}
        onClick={()=>void erase()}>{tx('Eliminar video y análisis del servidor','Delete video and analysis from server')}</button>}
    </div>
    {busy&&<p className="sci-notice" role="status">{state==='uploading'
      ?tx('Enviando video en bloques: ','Uploading in chunks: ')+
        (file?Math.round(100*bytes/Math.max(1,file.size)):0)+'%'
      :job?.stage||tx('Procesando con MegaDetector…','Processing with MegaDetector…')}
      {job?.total?' · '+job.processed+'/'+job.total:''}</p>}
    {message&&<p className={state==='failed'?'sci-warning':'sci-notice'} role="status">{message}</p>}
    {result&&<div className="auto-review">
      <div className="sci-panel-head">
        <h3>{tx('Bandeja de revisión','Review queue')}</h3>
        <span className="sci-tag">{pending} {tx('por revisar','to review')}</span>
      </div>
      <div className="sci-stats">
        <div><span>{tx('Fotogramas analizados','Sampled frames')}</span><strong>{result.totals.sampled}</strong></div>
        <div><span>{tx('Muestras con animales','Frames with animals')}</span><strong>{frames.filter(f=>f.counts.animal>0).length}</strong></div>
        <div><span>{tx('Muestras con personas','Frames with people')}</span><strong>{frames.filter(f=>f.counts.person>0).length}</strong></div>
        <div><span>{tx('Pendientes de revisión','Pending reviews')}</span><strong>{pending}</strong></div>
      </div>
      <div className="auto-review-toolbar">
        <label><input type="checkbox" checked={showEmpty} onChange={e=>setShowEmpty(e.target.checked)}/>
          {' '}{tx('Mostrar también muestras sin detecciones','Also show samples with no detections')}</label>
        <button type="button" className="sci-secondary" onClick={()=>downloadFile(
          'PantheraLIVE_revision_eventos.json',
          JSON.stringify({model:result.metadata.model,camera_id:camera,
            source_filename:result.metadata.filename,sampling_strategy:'spread',
            note:'Muestras dispersas, no vigilancia continua ni identificación de especies',
            rows:exportRows},null,2),'application/json')}>
          {tx('Exportar decisiones JSON','Export review decisions JSON')}</button>
      </div>
      {positives.length===0&&<p className="sci-warning">{tx(
        'Ninguna muestra seleccionada obtuvo una detección. Esto NO demuestra que el video completo esté vacío. Revisá el original antes de descartarlo.',
        'No sampled frame produced a detection. This does NOT mean the entire video is empty. Review the original before discarding it.')}</p>}
      {previewUrl&&<div className="auto-local-player">
        <button type="button" className="sci-secondary" onClick={()=>setShowPlayer(x=>!x)}>
          {showPlayer?tx('Ocultar video original','Hide original video'):tx('Mostrar video original local','Show local original video')}</button>
        {showPlayer&&<><p className="sci-muted">{tx(
          'El video puede contener personas: acceso de revisión local. No se ha guardado un clip recortado.',
          'The video may contain people: local review only. No cropped clip has been saved.')}</p>
          <video ref={player} controls playsInline preload="metadata" src={previewUrl}/></>}
      </div>}
      <div className="auto-event-list">
        {shown.map(frame=>{
          const hasPerson=frame.counts.person>0;
          const hasAnimal=frame.counts.animal>0;
          const status=reviews[frame.sample];
          return <article key={frame.sample} className="auto-event">
            <div className={'auto-frame '+(hasPerson&&!revealed[frame.sample]?'auto-sensitive':'')}>
              {hasPerson&&!revealed[frame.sample]
                ?<div className="auto-protected"><strong>{tx('Vista previa oculta','Preview hidden')}</strong>
                  <small>{tx('Posible persona detectada','Possible person detected')}</small>
                  <button type="button" className="sci-secondary" onClick={()=>setRevealed(previous=>({...previous,[frame.sample]:true}))}>
                    {tx('Mostrar para revisión','Reveal for review')}</button></div>
                :<img alt={tx('Fotograma analizado','Analyzed frame')+' '+frame.sample} src={frame.image}/>}
            </div>
            <div className="auto-event-info">
              <div className="auto-event-title"><strong>{tx('Muestra','Sample')} {frame.sample} · {clock(frame.time_seconds)}</strong>
                <span className="sci-tag">{status==='accepted'?tx('ACEPTADA','ACCEPTED'):status==='discarded'?tx('DESCARTADA','DISCARDED'):status==='human_review'?tx('REVISIÓN HUMANA','HUMAN REVIEW'):tx('PENDIENTE','PENDING')}</span></div>
              <p className="sci-muted">{hasAnimal?tx('Animal posible','Possible animal')+' · '+frame.counts.animal+' · '+
                Math.round(highest(frame,'animal')*100)+'%':''}
                {hasAnimal&&hasPerson?' · ':''}{hasPerson?tx('Persona posible · privacidad','Possible person · privacy')+' · '+frame.counts.person:''}
                {!hasAnimal&&!hasPerson?tx('Sin detección en esta muestra','No detection in this sample'):''}</p>
              <p className="sci-muted">{tx('El modelo no identifica jaguares, especies ni individuos. La confianza no equivale a certeza científica.',
                'The model does not identify jaguars, species or individuals. Confidence is not scientific certainty.')}</p>
              <div className="sci-actions">
                <button type="button" className="sci-secondary" disabled={!previewUrl}
                  onClick={()=>playAt(frame.time_seconds)}>{tx('Ver momento del video','Play video at this moment')}</button>
                {hasAnimal&&!hasPerson&&<button type="button" className="action-button"
                  disabled={!!status||busyReview!==null} onClick={()=>void accept(frame)}>
                  {tx('Confirmar animal · enviar evento','Confirm animal · add event')}</button>}
                {hasPerson&&!status&&<button type="button" className="sci-secondary"
                  onClick={()=>setReviews(prev=>({...prev,[frame.sample]:'human_review'}))}>
                  {tx('Marcar presencia humana para revisión','Flag human presence for review')}</button>}
                {!status&&<button type="button" className="sci-secondary"
                  onClick={()=>setReviews(prev=>({...prev,[frame.sample]:'discarded'}))}>
                  {tx('Descartar muestra','Discard sample')}</button>}
                {status&&status!=='accepted'&&<button type="button" className="sci-inline"
                  onClick={()=>setReviews(prev=>{const next={...prev};delete next[frame.sample];return next;})}>
                  {tx('Reabrir decisión','Reopen decision')}</button>}
              </div>
              {hasPerson&&<p className="sci-warning">{tx(
                'La detección de una persona no demuestra caza furtiva. Registrá solamente presencia humana, sin acusaciones automáticas. Esta vista oculta la imagen visualmente, pero NO establece seguridad ni permisos de acceso: no subás evidencia sensible al servidor de prueba.',
                'A person detection does not establish poaching. Flag human presence only, without automatic accusations. The preview is merely visually hidden and is NOT access control: do not upload sensitive evidence to this test server.')}</p>}
            </div>
          </article>;
        })}
      </div>
      <p className="sci-muted">{tx(
        '«Descartar muestra» solo cambia una anotación y no borra el video. «Marcar presencia humana» tampoco envía denuncias ni preserva pruebas. Conservá evidencia sensible únicamente en un sistema autorizado y seguro. El servidor experimental no tiene autenticación: usá solo videos de prueba autorizados y borrá el análisis temporal al terminar.',
        'Discard sample changes only a review annotation and does not delete the video. Flag human presence neither sends reports nor preserves evidence. Sensitive footage requires an authorized secure system. This experimental server has no authentication: use authorized test videos only and delete temporary analysis when finished.')}</p>
    </div>}
  </section>;
}
