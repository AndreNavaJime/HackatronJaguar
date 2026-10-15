import React from 'react';
import {useLanguage} from './language';
import {downloadFile} from './scienceShared';
import './FireVisionPanel.css';

type Scene={
  index:number;time:number;image:string;flameFraction:number;smokeChangeFraction:number;
  flame:boolean;smoke:boolean;
};
type Review='needs_review'|'discarded';
const VIDEO_MAX_BYTES=180*1024*1024;

function videoTime(s:number){
  return Math.floor(s/60).toString().padStart(2,'0')+':'+Math.floor(s%60).toString().padStart(2,'0');
}
function errMessage(err:unknown){return err instanceof Error?err.message:String(err);}
function waitVideo(video:HTMLVideoElement,eventName:'loadedmetadata'|'seeked',timeout=14000):Promise<void>{
  return new Promise((resolve,reject)=>{
    const cleanup=()=>{video.removeEventListener(eventName,done);video.removeEventListener('error',fail);window.clearTimeout(timer);};
    const done=()=>{cleanup();resolve();};
    const fail=()=>{cleanup();reject(new Error('El navegador no pudo decodificar el video o su códec.'));};
    const timer=window.setTimeout(()=>{cleanup();reject(new Error('El navegador tardó demasiado en leer el video.'));},timeout);
    video.addEventListener(eventName,done,{once:true});
    video.addEventListener('error',fail,{once:true});
  });
}
function screen(image:ImageData,previous:Uint8ClampedArray|null){
  const data=image.data;
  const total=data.length/4;
  let flamePixels=0;
  let neutral=0;
  let changedNeutral=0;
  for(let offset=0;offset<data.length;offset+=4){
    const r=data[offset],g=data[offset+1],b=data[offset+2];
    const max=Math.max(r,g,b),min=Math.min(r,g,b);
    // A deliberately simple color-candidate rule, NOT an AI fire model.
    const brightWarm=r>166&&g>68&&r>g*1.18&&g>b*1.24&&(max-min)>70;
    if(brightWarm)flamePixels++;
    const brightness=(r+g+b)/3;
    const grayish=max-min<35&&brightness>105&&brightness<245;
    if(grayish){
      neutral++;
      if(previous){
        const difference=(Math.abs(r-previous[offset])+Math.abs(g-previous[offset+1])+
          Math.abs(b-previous[offset+2]))/3;
        if(difference>24)changedNeutral++;
      }
    }
  }
  const flameFraction=flamePixels/total;
  const smokeChangeFraction=changedNeutral/total;
  const neutralFraction=neutral/total;
  return {
    flameFraction,smokeChangeFraction,
    flame:flameFraction>=.006,
    smoke:!!previous&&smokeChangeFraction>=.025&&neutralFraction>=.14,
  };
}

export default function FireVisionPanel(){
  const {language}=useLanguage();
  const tx=(es:string,en:string)=>language==='en'?en:es;
  const [file,setFile]=React.useState<File|null>(null);
  const [url,setUrl]=React.useState('');
  const [busy,setBusy]=React.useState(false);
  const [error,setError]=React.useState('');
  const [progress,setProgress]=React.useState('');
  const [scenes,setScenes]=React.useState<Scene[]>([]);
  const [reviews,setReviews]=React.useState<Record<number,Review>>({});
  const [showAll,setShowAll]=React.useState(false);
  const [sampleCount,setSampleCount]=React.useState(12);
  const [showPlayer,setShowPlayer]=React.useState(false);
  const [runStamp,setRunStamp]=React.useState('');
  const video=React.useRef<HTMLVideoElement|null>(null);
  const canvas=React.useRef<HTMLCanvasElement|null>(null);
  const alive=React.useRef(true);
  React.useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
  React.useEffect(()=>{
    if(!file){setUrl('');return;}
    const objectUrl=URL.createObjectURL(file);setUrl(objectUrl);
    return()=>URL.revokeObjectURL(objectUrl);
  },[file]);

  function selectFile(next:File|null){
    if(busy)return;
    setFile(next);setScenes([]);setReviews({});setError('');setProgress('');setShowPlayer(false);setRunStamp('');
  }

  async function analyze(){
    if(!file||!url||busy)return;
    if(!/^(video\/|application\/octet-stream)/.test(file.type)&&!/\.(mp4|webm|mov|m4v)$/i.test(file.name)){
      setError(tx('Seleccioná un video compatible (MP4, WebM o MOV).',
        'Select a compatible video (MP4, WebM or MOV).'));return;
    }
    if(file.size>VIDEO_MAX_BYTES){
      setError(tx('Para esta prueba local el límite es de 180 MB.','This local test is limited to 180 MB.'));return;
    }
    setBusy(true);setError('');setScenes([]);setReviews({});setRunStamp('');
    try{
      const element=video.current,buffer=canvas.current;
      if(!element||!buffer)throw new Error('No se pudo preparar el reproductor.');
      element.pause();
      element.preload='auto';element.muted=true;
      if(element.readyState<1||!Number.isFinite(element.duration)){
        const ready=waitVideo(element,'loadedmetadata');
        element.load();
        await ready;
      }
      if(!Number.isFinite(element.duration)||element.duration<=0){
        throw new Error(tx('El video no tiene una duración válida.','Video duration is invalid.'));
      }
      const ctx=buffer.getContext('2d',{willReadFrequently:true});
      if(!ctx)throw new Error('Canvas 2D no está disponible.');
      buffer.width=320;buffer.height=180;
      const duration=element.duration;
      const n=Math.min(sampleCount,Math.max(1,Math.floor(duration*2)));
      const snapshots:Scene[]=[];
      let previous:Uint8ClampedArray|null=null;
      for(let i=0;i<n;i++){
        if(!alive.current)return;
        const point=Math.min(Math.max(0,duration-.06),Math.max(0,((i+.5)/n)*duration));
        setProgress(tx('Revisando muestra ','Processing sample ')+(i+1)+' / '+n);
        if(Math.abs(element.currentTime-point)>.035||element.readyState<2){
          const done=waitVideo(element,'seeked');
          element.currentTime=point;
          await done;
        }
        ctx.drawImage(element,0,0,buffer.width,buffer.height);
        const data=ctx.getImageData(0,0,buffer.width,buffer.height);
        const measurement=screen(data,previous);
        previous=new Uint8ClampedArray(data.data);
        snapshots.push({index:i+1,time:point,image:buffer.toDataURL('image/jpeg',.7),...measurement});
        // Yield to the UI between frames to allow progress reporting.
        await new Promise<void>(resolve=>window.setTimeout(resolve,0));
      }
      if(alive.current){
        setScenes(snapshots);setRunStamp(new Date().toISOString());
        setProgress('');
      }
    }catch(err){if(alive.current){setError(errMessage(err));setProgress('');}}
    finally{if(alive.current)setBusy(false);}
  }

  const flagged=scenes.filter(s=>s.flame||s.smoke);
  const shown=showAll?scenes:flagged;
  const pending=flagged.filter(s=>!reviews[s.index]).length;
  const report=()=>{
    const payload={project:'PantheraLAB',module:'PantheraFIRE',analyzed_at:runStamp,
      filename:file?.name||'',method:'exploratory_browser_pixel_rules_no_AI',
      validated_wildfire_detector:false,camera_live:false,automatic_emergency_alert:false,
      limitations:'Color and frame-change heuristics are unvalidated; foliage, sunlight, clouds, fog and lighting may trigger false positives. Sampled frames cannot rule out a fire.',
      samples:scenes.map(s=>({sample:s.index,second:Math.round(s.time*100)/100,
        possible_flame_color:s.flame,possible_smoke_change:s.smoke,
        flame_color_fraction:Number(s.flameFraction.toFixed(4)),
        gray_change_fraction:Number(s.smokeChangeFraction.toFixed(4)),
        human_decision:reviews[s.index]||'not_reviewed'}))};
    downloadFile('PantheraFIRE_revision_visual.json',JSON.stringify(payload,null,2),'application/json');
  };

  return <section className="fire-card fire-vision" aria-label={tx('Revisión visual experimental','Experimental visual review')}>
    <div className="fire-vision-head"><div>
      <span className="fire-kicker">PANTHERAFIRE / CAMERA VISION</span>
      <h3>{tx('Humo y llamas · Análisis visual experimental',
        'Smoke and flames · Experimental visual screening')}</h3>
    </div><span className="fire-pill">{tx('PRUEBA LOCAL','LOCAL TEST')}</span></div>
    <p>{tx(
      'Seleccioná un video autorizado para buscar señales visuales preliminares de colores compatibles con llama y cambios grisáceos compatibles con humo. Se examinan fotogramas del video sin enviarlo a ningún servidor.',
      'Select an authorized video to screen for preliminary flame-like colors and changing gray regions that might resemble smoke. Sampled frames stay in this browser and are not uploaded.')}</p>
    <div className="fire-vision-warning" role="note">
      <strong>{tx('Importante: todavía NO es un detector de incendios con IA.',
        'Important: this is NOT an AI wildfire detector yet.')}</strong>
      <span>{tx(
        'Es un cribado por reglas de color y cambios entre fotogramas. La niebla, el sol, tierra roja, nubes, hojas o sombras pueden producir falsos positivos y un incendio real puede pasar inadvertido. No se conecta con Bomberos, cámaras ni PyroEngine.',
        'It screens colors and changes between frames. Fog, sunlight, reddish soil, clouds, foliage and shadows can cause false positives, and real fires can be missed. It is not connected to emergency services, cameras or PyroEngine.')}</span>
    </div>
    <div className="fire-vision-form">
      <label className="sci-field"><span>{tx('Video de prueba (MP4, WebM o MOV)','Test video (MP4, WebM or MOV)')}</span>
        <input type="file" accept="video/mp4,video/webm,video/quicktime,.mp4,.webm,.mov,.m4v"
          disabled={busy} onChange={e=>selectFile(e.target.files?.[0]||null)}/></label>
      <label className="sci-field"><span>{tx('Fotogramas a examinar','Frames to examine')}</span>
        <select value={sampleCount} onChange={e=>setSampleCount(Number(e.target.value))} disabled={busy}>
          <option value="8">8</option><option value="12">12</option><option value="16">16</option>
        </select></label>
      <button type="button" className="action-button" disabled={!file||busy||!url}
        onClick={()=>void analyze()}>{busy?tx('Analizando…','Analyzing…'):tx('Examinar video local','Screen local video')}</button>
    </div>
    <video ref={video} src={url||undefined} muted playsInline preload="metadata"
      className={showPlayer?'fire-vision-player':'fire-vision-hidden'} controls={showPlayer}
      aria-label={tx('Video original local','Local original video')}/>
    <canvas ref={canvas} className="fire-vision-hidden" aria-hidden="true"/>
    {file&&<p className="sci-muted">{file.name} · {(file.size/1048576).toFixed(1)} MB · {tx('permanece en este navegador','stays in this browser')}</p>}
    {busy&&<p className="sci-notice" role="status">{progress}</p>}
    {error&&<p className="sci-warning" role="alert">{error}</p>}
    {scenes.length>0&&<div className="fire-vision-results">
      <div className="sci-stats">
        <div><span>{tx('Muestras examinadas','Frames screened')}</span><strong>{scenes.length}</strong></div>
        <div><span>{tx('Color compatible con llama','Flame-like color')}</span><strong>{scenes.filter(s=>s.flame).length}</strong></div>
        <div><span>{tx('Cambio grisáceo','Gray change')}</span><strong>{scenes.filter(s=>s.smoke).length}</strong></div>
        <div><span>{tx('Indicios por revisar','Candidates to review')}</span><strong>{pending}</strong></div>
      </div>
      <div className="fire-vision-toolbar">
        <label><input type="checkbox" checked={showAll} onChange={e=>setShowAll(e.target.checked)}/>
          {tx('Mostrar también muestras sin indicios','Show samples without indicators')}</label>
        <button type="button" className="sci-secondary" onClick={()=>setShowPlayer(v=>!v)}>
          {showPlayer?tx('Ocultar video original','Hide original video'):tx('Revisar video completo','Review full video')}</button>
        <button type="button" className="sci-secondary" onClick={report}>{tx('Exportar revisión JSON','Export review JSON')}</button>
      </div>
      {flagged.length===0&&<p className="fire-vision-warning">{tx(
        'No aparecieron indicios con estas reglas en las muestras examinadas. NO significa que el video esté libre de humo o incendio: revisá el original.',
        'No candidates were flagged by these rules in sampled frames. This does NOT mean the video is smoke- or fire-free: review the original.')}</p>}
      <div className="fire-vision-list">
        {shown.map(scene=><article className="fire-vision-event" key={scene.index}>
          <img src={scene.image} loading="lazy" alt={tx('Muestra del video','Video frame')+' '+scene.index}/>
          <div className="fire-vision-event-body">
            <strong>{tx('Muestra','Sample')} {scene.index} · {videoTime(scene.time)}</strong>
            <span>{scene.flame?tx('Color compatible con llama · NO confirmado','Flame-like color · UNCONFIRMED'):''}
              {scene.flame&&scene.smoke?' · ':''}
              {scene.smoke?tx('Cambio compatible con humo · NO confirmado','Smoke-like change · UNCONFIRMED'):''}
              {!scene.flame&&!scene.smoke?tx('Sin indicios bajo estas reglas','No indicators under these rules'):''}</span>
            <div className="fire-vision-buttons">
              <button type="button" className="sci-secondary"
                onClick={()=>setReviews(v=>({...v,[scene.index]:'needs_review'}))}>
                {tx('Marcar para revisión','Mark for review')}</button>
              <button type="button" className="sci-secondary"
                onClick={()=>setReviews(v=>({...v,[scene.index]:'discarded'}))}>
                {tx('Descartar indicio','Dismiss candidate')}</button>
              <a className="sci-secondary" href={scene.image} download={'PantheraFIRE_muestra_'+scene.index+'.jpg'}>
                {tx('Guardar fotograma','Save frame')}</a>
            </div>
            <small>{reviews[scene.index]==='needs_review'
              ?tx('Revisión solicitada (solo en este navegador)','Marked for review (in this browser only)')
              :reviews[scene.index]==='discarded'
              ?tx('Indicio descartado; no se elimina el archivo original','Candidate dismissed; original video is unaffected')
              :tx('Sin decisión científica','Awaiting review')}</small>
          </div>
        </article>)}
      </div>
      <p className="sci-muted">{tx(
        'Este experimento no envía alertas ni guarda expedientes: si necesitás conservar evidencia, descargá el informe y los fotogramas. Una implementación posterior de PyroEngine/ONNX y pruebas de campo podrían sustituir estas reglas por un modelo especializado.',
        'This experiment sends no alerts and stores no case files: download the report and frames if you need evidence. A later PyroEngine/ONNX integration and field validation could replace these rules with a specialized model.')}</p>
    </div>}
  </section>;
}
