import React from 'react';
import { useLanguage } from './language';

type LiteFrame = {sample:number; time_seconds:number; retained:boolean; motion_score:number; image:string};
type LiteRow = {sample:number; video_time_seconds:number; motion_score:number; edge_decision:string};
type LiteResult = {
  metadata:{mode:string; model:string; filename:string; duration_seconds:number;
    source_width:number; source_height:number; sample_seconds:number; threshold:number};
  totals:{sampled:number;retained:number;discarded:number;mean_motion:number;
    positive_frame_rate:number;estimated_payload_reduction:number};
  frames:LiteFrame[]; rows:LiteRow[]; note:string;
};
type Job = {state:'uploading'|'processing'|'completed'|'failed';stage:string;
  processed:number;total:number;error:string|null;result:LiteResult|null};
const CHUNK=5*1024*1024;
const LIMIT=60*1024*1024;

async function readResponse(response:Response) {
  let value:unknown;
  try { value=await response.json(); }
  catch { throw new Error('El servidor no devolvió datos JSON. / Server returned no JSON.'); }
  if (!response.ok) {
    const detail=typeof value==='object'&&value!==null&&'detail' in value&&typeof value.detail==='string'
      ? value.detail : 'HTTP '+response.status;
    throw new Error(detail);
  }
  return value;
}

export default function LiteVideoPanel({enabled}:{enabled:boolean}) {
  const {language}=useLanguage();
  const tx=(es:string,en:string)=>language==='en'?en:es;
  const [file,setFile]=React.useState<File|null>(null);
  const [preview,setPreview]=React.useState('');
  const [motionThreshold,setMotionThreshold]=React.useState(.04);
  const [seconds,setSeconds]=React.useState(1);
  const [samples,setSamples]=React.useState(8);
  const [uploaded,setUploaded]=React.useState(0);
  const [state,setState]=React.useState<'idle'|'uploading'|'processing'|'completed'|'failed'>('idle');
  const [jobId,setJobId]=React.useState('');
  const [job,setJob]=React.useState<Job|null>(null);
  const [result,setResult]=React.useState<LiteResult|null>(null);
  const [error,setError]=React.useState('');
  const busy=state==='uploading'||state==='processing';

  React.useEffect(()=>{
    if(!file){setPreview('');return;}
    const url=URL.createObjectURL(file);setPreview(url);
    return ()=>URL.revokeObjectURL(url);
  },[file]);
  React.useEffect(()=>{
    if(!jobId||state!=='processing')return;
    let active=true;
    const poll=async()=>{
      try{
        const next=await readResponse(await fetch('/api/videos/jobs/'+encodeURIComponent(jobId),{cache:'no-store'})) as Job;
        if(!active)return;
        setJob(next);
        if(next.state==='completed'){
          if(!next.result||next.result.metadata?.mode!=='lite')throw new Error('Resultado inesperado. / Unexpected result.');
          setResult(next.result);setState('completed');setError('');
        }else if(next.state==='failed'){setState('failed');setError(next.error||'Error del servidor / Server error');}
      }catch(cause){if(active)setError(cause instanceof Error?cause.message:String(cause));}
    };
    void poll();
    const interval=window.setInterval(()=>{void poll();},2500);
    return ()=>{active=false;window.clearInterval(interval);};
  },[jobId,state]);

  async function analyze(){
    if(!file||!enabled||busy)return;
    if(file.size>LIMIT){setError(tx('Máximo 60 MB en modo gratuito.','Free mode limit: 60 MB.'));return;}
    if(!/\.(mp4|mov|avi|mkv)$/i.test(file.name)){setError(tx('Elegí MP4, MOV, AVI o MKV.','Choose MP4, MOV, AVI or MKV.'));return;}
    setError('');setUploaded(0);setJob(null);setJobId('');setResult(null);setState('uploading');
    let uploadId='';
    try{
      const params=new URLSearchParams({
        mode:'lite',motion_threshold:motionThreshold.toFixed(3),sample_seconds:seconds.toFixed(1),
        max_samples:String(samples),
      });
      const started=await readResponse(await fetch('/api/videos/uploads?'+params.toString(),{
        method:'POST',headers:{'X-Video-Name':encodeURIComponent(file.name),'X-Video-Size':String(file.size)},
      })) as {upload_id:string;chunk_max_bytes:number};
      if(!started.upload_id)throw new Error('El servidor no creó la sesión. / No upload session.');
      uploadId=started.upload_id;
      const chunkSize=Math.min(CHUNK,started.chunk_max_bytes||CHUNK);
      for(let offset=0;offset<file.size;offset+=chunkSize){
        const end=Math.min(offset+chunkSize,file.size);
        const done=await readResponse(await fetch(
          '/api/videos/uploads/'+encodeURIComponent(uploadId)+'/chunks?offset='+offset,
          {method:'PUT',headers:{'Content-Type':'application/octet-stream'},body:file.slice(offset,end)},
        )) as {received_bytes:number};
        if(done.received_bytes!==end)throw new Error('Carga incompleta. / Incomplete upload.');
        setUploaded(end);
      }
      const begun=await readResponse(await fetch(
        '/api/videos/uploads/'+encodeURIComponent(uploadId)+'/complete',{method:'POST'},
      )) as {job_id:string};
      if(!begun.job_id)throw new Error('El servidor no inició el análisis. / Analysis did not start.');
      setJobId(begun.job_id);setState('processing');
    }catch(cause){
      setError(cause instanceof Error?cause.message:String(cause));setState('failed');
      if(uploadId)try{await fetch('/api/videos/uploads/'+encodeURIComponent(uploadId),{method:'DELETE'});}catch{/* best effort */}
    }
  }
  const reset=(next:File|null)=>{
    setFile(next);setJob(null);setJobId('');setResult(null);setError('');setState('idle');setUploaded(0);
  };
  const pct=(value:number)=>(value*100).toFixed(1)+'%';
  const base=jobId?'/api/videos/jobs/'+encodeURIComponent(jobId)+'/download?kind=':'';

  return <section className="video-panel lite-panel" aria-label={tx('Análisis gratuito de cambios visuales','Free visual-change screening')}>
    <div className="panel-heading">
      <div><span className="lite-kicker">{tx('MODO GRATUITO · SIN IA','FREE MODE · NO AI')}</span>
        <h3>{tx('Exploración visual de videos','Visual video screening')}</h3>
        <p>{tx('Extraé fotogramas, medí cambios entre muestras y descargá evidencias. No identifica animales, especies ni individuos.',
          'Extract frames, measure changes between samples and download evidence. Does not identify animals, species or individuals.')}</p>
      </div><span className="tag">OpenCV · CPU</span>
    </div>
    <div className="lite-science-notice" role="note">
      <strong>{tx('⚠ No es un detector de fauna','⚠ Not a wildlife detector')}</strong>
      <p>{tx('Lluvia, hojas, sombras o movimiento de cámara también pueden producir cambios. Una muestra estable no demuestra ausencia de animales. Revisá todas las imágenes.',
        'Rain, leaves, shadows and camera motion can cause changes. A stable sample does not prove wildlife absence. Review every image.')}</p>
    </div>
    <div className="video-config">
      <div className="video-input">
        <label htmlFor="lite-video">{tx('Video de cámara trampa (hasta 60 MB, máximo 3 min)','Camera-trap video (up to 60 MB, max 3 min)')}</label>
        <input id="lite-video" type="file" accept=".mp4,.mov,.avi,.mkv,video/mp4,video/quicktime,video/x-msvideo"
          disabled={busy} onChange={e=>reset(e.target.files?.[0]??null)}/>
        {file&&<small>{file.name} · {(file.size/1048576).toFixed(2)} MB</small>}
        {preview&&<video controls preload="metadata" src={preview} className="video-preview"
          aria-label={tx('Vista previa del video','Video preview')}/>}
        <small>{tx('La vista previa depende del códec del navegador. El video se analiza en el servidor.',
          'Preview depends on browser codec support. Video is processed on the server.')}</small>
      </div>
      <div className="video-options">
        <label htmlFor="lite-change">{tx('Umbral de píxeles cambiados','Changed-pixel threshold')}: {pct(motionThreshold)}</label>
        <input id="lite-change" type="range" min=".01" max=".15" step=".01"
          value={motionThreshold} disabled={busy} onChange={e=>setMotionThreshold(Number(e.target.value))}/>
        <label htmlFor="lite-interval">{tx('Muestreo cada','Sample every')} {seconds.toFixed(1)} s</label>
        <input id="lite-interval" type="range" min=".5" max="5" step=".5"
          value={seconds} disabled={busy} onChange={e=>setSeconds(Number(e.target.value))}/>
        <label htmlFor="lite-samples">{tx('Máximo de fotogramas','Maximum frames')}: {samples}</label>
        <input id="lite-samples" type="range" min="2" max="12" step="1"
          value={samples} disabled={busy} onChange={e=>setSamples(Number(e.target.value))}/>
        <button type="button" className="action-button" disabled={!file||!enabled||busy} onClick={()=>void analyze()}>
          {busy?tx('Procesando…','Processing…'):tx('Analizar cambios visuales gratis ↗','Screen visual changes for free ↗')}
        </button>
        {!enabled&&<small>{tx('Esperando el nuevo motor de video en Render. Comprobá que su último despliegue esté en Live.','Waiting for the updated video engine on Render. Check that its latest deployment is Live.')}</small>}
        <small>{tx('Se compara brillo entre muestras; el porcentaje NO es confianza de detección animal.',
          'Compares brightness between samples; the percentage is NOT animal detection confidence.')}</small>
      </div>
    </div>
    {state==='uploading'&&file&&<div className="video-progress" role="status">
      <strong>{tx('Subiendo video por bloques…','Uploading video in chunks…')}</strong>
      <p>{(uploaded/1048576).toFixed(1)} / {(file.size/1048576).toFixed(1)} MB</p>
      <progress max={file.size} value={uploaded}/>
    </div>}
    {state==='processing'&&<div className="video-progress" role="status">
      <strong>{job?.stage||tx('Analizando fotogramas…','Analyzing frames…')}</strong>
      <p>{job?.processed??0} / {job?.total||samples} {tx('muestras','samples')}</p>
      <progress max={job?.total||samples} value={job?.processed??0}/>
    </div>}
    {error&&<p role="alert" className="upload-error">{error}</p>}
    {result&&<div className="video-results lite-results">
      <h3>{tx('Resultados de exploración visual','Visual screening results')}</h3>
      <p className="details-caption">{result.metadata.filename} · {result.metadata.model}</p>
      <div className="video-metrics">
        <div><span>{tx('Fotogramas revisados','Frames reviewed')}</span><strong>{result.totals.sampled}</strong></div>
        <div><span>{tx('Con cambios visuales','With visual changes')}</span><strong>{result.totals.retained}</strong></div>
        <div><span>{tx('Referencia o sin cambios','Reference or unchanged')}</span><strong>{result.totals.discarded}</strong></div>
        <div><span>{tx('Cambio medio de píxeles','Mean pixel change')}</span><strong>{pct(result.totals.mean_motion)}</strong></div>
        <div><span>{tx('Muestras con cambios','Changed samples')}</span><strong>{result.totals.positive_frame_rate.toFixed(1)}%</strong></div>
        <div><span>{tx('Duración del video','Video duration')}</span><strong>{result.metadata.duration_seconds.toFixed(1)} s</strong></div>
      </div>
      <div className="video-chart-panel lite-motion-chart">
        <h4>{tx('Porcentaje de píxeles que cambiaron entre muestras','Percentage of pixels changed between samples')}</h4>
        <div className="lite-motion-bars">
          {result.rows.map(row=><div key={row.sample} className="lite-motion-row">
            <span>{row.sample} · {row.video_time_seconds.toFixed(1)} s</span>
            <div className="lite-motion-track"><div style={{width:Math.min(100,row.motion_score*100*5)+'%'}}/></div>
            <strong>{pct(row.motion_score)}</strong>
          </div>)}
        </div>
        <small>{tx('La primera muestra es una referencia (0%). Las barras visuales están ampliadas ×5 para facilitar la lectura.',
          'First sample is the reference (0%). Bar lengths are magnified ×5 for readability.')}</small>
      </div>
      <div className="video-downloads">
        <h4>{tx('Descargas para revisión científica','Downloads for scientific review')}</h4>
        <div className="preview-controls">
          <a className="download-link" href={base+'zip'}>{tx('Todas las imágenes · ZIP ↓','All frames · ZIP ↓')}</a>
          <a className="download-link" href={base+'csv'}>{tx('Cambios por fotograma · CSV ↓','Frame changes · CSV ↓')}</a>
          <a className="download-link" href={base+'pdf'}>{tx('Informe sin IA · PDF ↓','Non-AI report · PDF ↓')}</a>
        </div>
        <small>{tx('El ZIP contiene TODAS las muestras, no solo las marcadas. Los archivos caducan en aproximadamente una hora.',
          'The ZIP includes ALL frames, not only flagged ones. Files expire in approximately one hour.')}</small>
      </div>
      <h4>{tx('Galería de fotogramas','Frame gallery')}</h4>
      <p>{tx('Se muestran todas las muestras para evitar omitir posibles animales inmóviles.',
        'All samples are shown to avoid overlooking stationary wildlife.')}</p>
      <div className="video-gallery">
        {result.frames.map(frame=><article key={frame.sample} className="video-frame-card">
          <img src={frame.image} loading="lazy" alt={tx('Fotograma','Frame')+' '+frame.sample}/>
          <div className="video-frame-details">
            <strong>{tx('Muestra','Sample')} {frame.sample} · {frame.time_seconds.toFixed(1)} s</strong>
            <span>{frame.sample===1?tx('REFERENCIA INICIAL','INITIAL REFERENCE')
              :frame.retained?tx('CAMBIO VISUAL · revisar','VISUAL CHANGE · review')
              :tx('SIN CAMBIO DETECTADO','NO CHANGE DETECTED')}</span>
            <small>{tx('Píxeles cambiados','Changed pixels')}: {pct(frame.motion_score)}</small>
            <a className="download-link" download={'pantheraid_muestra_'+String(frame.sample).padStart(3,'0')+'.jpg'}
              href={frame.image}>{tx('Descargar fotograma ↓','Download frame ↓')}</a>
          </div>
        </article>)}
      </div>
      <p className="scientific-note">{tx(
        'Modo exploratorio sin IA. NO confirma ni descarta presencia de animales; las cifras no representan precisión ni confianza de un detector. Requiere revisión humana.',
        'Exploratory non-AI mode. Does NOT confirm or rule out wildlife presence; values are neither detector accuracy nor confidence. Human review is required.')}</p>
    </div>}
  </section>;
}
