import React from 'react';
import {useLanguage} from './language';
import {addAnimalClip,deleteAnimalClip,listAnimalClips,localStudyId,setAnimalClipState,
  MAX_CLIPS,type AnimalClip} from './animalClipStore';
import './LocalAnimalClips.css';
import {notifyClipReady} from './clipNotifications';
import {AdaptiveLightFrame,type LightCondition} from './adaptiveLightFrame';

type Prediction={class:string;score:number};
type Detector={detect:(frame:HTMLVideoElement|HTMLCanvasElement)=>Promise<Prediction[]>;backend:string};
type Capture={recorder:MediaRecorder;parts:Blob[];discard:boolean;started:number;
  animalClass:string;confidence:number;studyId:string;mime:string};
type Props={stream:MediaStream|null;video:HTMLVideoElement|null;
  sourceMode:'device'|'remote';cameraId:string};
const ANIMALS=new Set(['bird','cat','dog','horse','sheep','cow','elephant','bear','zebra','giraffe']);
// COCO object classes are not verified species. We group the animal labels
// into a provisional animal/no-animal trigger for event recording.
const WEAK_ANIMAL_SCORE=.28;
const MEDIUM_ANIMAL_SCORE=.38;
const STRONG_ANIMAL_SCORE=.78;
const CONFIRM_WITHIN_MS=6000;
const SILENCE_MS=4500;
const MAX_DURATION_MS=19000;
const REARM_MS=6000;
const REST_MS=6500;

function recordingMime():string{
  if(typeof MediaRecorder==='undefined')return '';
  for(const candidate of ['video/webm;codecs=vp8','video/webm','video/mp4']){
    if(MediaRecorder.isTypeSupported(candidate))return candidate;
  }
  return '';
}
export default function LocalAnimalClips({stream,video,sourceMode,cameraId}:Props){
  const {language}=useLanguage();
  const tx=React.useCallback((es:string,en:string)=>language==='en'?en:es,[language]);
  const [loading,setLoading]=React.useState(false);
  const [running,setRunning]=React.useState(false);
  const [status,setStatus]=React.useState('');
  const [error,setError]=React.useState('');
  const [clips,setClips]=React.useState<AnimalClip[]>([]);
  const [objects,setObjects]=React.useState<Record<string,string>>({});
  const [detectorBackend,setDetectorBackend]=React.useState('');
  const [lastObservation,setLastObservation]=React.useState('');
  const [lightCondition,setLightCondition]=React.useState<LightCondition>('normal');
  const [lightBrightness,setLightBrightness]=React.useState<number|null>(null);
  const [framesInspected,setFramesInspected]=React.useState(0);
  const [clipAlert,setClipAlert]=React.useState('');
  const [dismissedStart,setDismissedStart]=React.useState(false);
  const detectorRef=React.useRef<Detector|null>(null);
  const captureRef=React.useRef<Capture|null>(null);
  const readyRef=React.useRef(true);
  const lastAnimalRef=React.useRef(0);
  const lastClipRef=React.useRef(0);
  const mountedRef=React.useRef(true);
  const loadToken=React.useRef(0);
  const busyRef=React.useRef(false);
  const animalHistory=React.useRef<{at:number;score:number}[]>([]);
  const adaptiveFrame=React.useRef<AdaptiveLightFrame|null>(null);
  const clipCountRef=React.useRef(0);
  clipCountRef.current=clips.length;

  const refresh=React.useCallback(async()=>{
    const all=await listAnimalClips();
    if(mountedRef.current)setClips(all);
  },[]);
  React.useEffect(()=>{
    mountedRef.current=true;
    void refresh().catch(e=>setError(String(e instanceof Error?e.message:e)));
    return ()=>{mountedRef.current=false;loadToken.current++;};
  },[refresh]);
  React.useEffect(()=>{
    const urls:Record<string,string>={};
    clips.forEach(clip=>{urls[clip.id]=URL.createObjectURL(clip.video);});
    setObjects(urls);
    return ()=>Object.values(urls).forEach(url=>URL.revokeObjectURL(url));
  },[clips]);

  const finish=React.useCallback((discard=false)=>{
    const cap=captureRef.current;
    if(!cap)return;
    if(discard)cap.discard=true;
    if(cap.recorder.state!=='inactive'){
      try{cap.recorder.stop();}catch{/* Tracks may have ended. */}
    }
  },[]);
  // Foreground-only experiment. Backgrounding stops the camera and finalizes a partial clip.
  React.useEffect(()=>{
    if(stream&&stream.active)return;
    loadToken.current++;
    setRunning(false);setLoading(false);
    finish();
  },[stream,finish]);

  React.useEffect(()=>{
    if(!running||!stream?.active||!video||!detectorRef.current)return;
    let active=true,timer:number|undefined;
    const detector=detectorRef.current;
    readyRef.current=true;lastAnimalRef.current=0;
    animalHistory.current=[];
    setFramesInspected(0);setLastObservation('');setLightCondition('normal');setLightBrightness(null);
    const startClip=(prediction:Prediction)=>{
      const mime=recordingMime();
      if(!mime)throw new Error(tx('La grabación de video no está disponible en este navegador.',
        'Video recording is not available in this browser.'));
      const rec=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:850_000});
      const cap:Capture={recorder:rec,parts:[],discard:false,started:Date.now(),
        animalClass:'animal',confidence:prediction.score,
        studyId:localStudyId(),mime};
      captureRef.current=cap;readyRef.current=false;
      rec.ondataavailable=e=>{if(e.data.size>0)cap.parts.push(e.data);};
      rec.onerror=()=>{cap.discard=true;setError(tx('La grabación de este evento falló.',
        'Recording failed for this event.'));};
      rec.onstop=()=>{
        if(captureRef.current===cap)captureRef.current=null;
        if(cap.discard)return;
        const blob=new Blob(cap.parts,{type:rec.mimeType||cap.mime});
        if(blob.size<1024||Date.now()-cap.started<700)return;
        const item:AnimalClip={id:crypto.randomUUID(),studyId:cap.studyId,capturedAt:new Date(cap.started).toISOString(),
          animalClass:cap.animalClass,confidence:cap.confidence,model:'COCO-SSD Lite (navegador)',
          state:'pending',mimeType:blob.type,video:blob,sourceMode,cameraId,
          durationMs:Date.now()-cap.started};
        void addAnimalClip(item).then(()=>{
          if(!mountedRef.current)return;
          setStatus(tx('Nuevo video con posible animal. Revisalo en la bandeja local.',
            'New possible-animal clip. Review it in your local inbox.'));
          setClipAlert(tx('Nuevo video de posible animal pendiente de revisión.',
            'New possible-animal video awaiting review.'));
          void notifyClipReady();
          return refresh();
        }).catch(e=>{
          if(mountedRef.current)setError(tx('No se pudo guardar el video en este dispositivo: ',
            'Video could not be saved on this device: ')+(e instanceof Error?e.message:String(e)));
        });
      };
      rec.start(1000);
      setStatus(tx('Posible animal detectado: grabando clip temporal…',
        'Possible animal detected: recording temporary clip…'));
    };
    async function scan(){
      if(!active)return;
      // WebRTC/phone preview often has no decoded frame immediately after play().
      // Always reschedule rather than silently stopping the detection loop.
      if(busyRef.current||!video||video.readyState<2||!stream?.active){
        timer=window.setTimeout(()=>void scan(),600);
        return;
      }
      busyRef.current=true;
      try{
        if(!adaptiveFrame.current)adaptiveFrame.current=new AdaptiveLightFrame();
        const frame=adaptiveFrame.current.prepare(video);
        setLightCondition(frame.condition);
        setLightBrightness(frame.brightness>=0?Math.round(frame.brightness):null);
        if(frame.condition==='too_dark'){
          setLastObservation(tx(
            'Imagen casi negra: no hay luz suficiente para detectar animales con fiabilidad. Se necesita iluminación o cámara infrarroja.',
            'Nearly black image: not enough light to detect animals reliably. Use lighting or an infrared camera.'
          ));
          if(captureRef.current&&Date.now()-lastAnimalRef.current>SILENCE_MS){
            lastClipRef.current=Date.now();finish();
          }
          return;
        }
        const results=await detector.detect(frame.source);
        if(!active)return;
        setFramesInspected(n=>n+1);
        const now=Date.now();
        const person=results.some(p=>p.class==='person'&&p.score>=.50);
        const candidate=results.filter(p=>ANIMALS.has(p.class))
          .sort((a,b)=>b.score-a.score)[0];
        let animal:Prediction|undefined;
        // Aggregate animal evidence regardless of fluctuating cat/dog labels.
        // "car", "truck" and all non-animal classes cannot start clips.
        animalHistory.current=animalHistory.current.filter(x=>
          now-x.at>=0&&now-x.at<=CONFIRM_WITHIN_MS);
        if(person){
          animalHistory.current=[];
          setLastObservation(tx('Posible persona: se evita grabar por privacidad.',
            'Possible person: recording suppressed for privacy.'));
        }else if(candidate){
          if(candidate.score>=WEAK_ANIMAL_SCORE){
            animalHistory.current.push({at:now,score:candidate.score});
            animalHistory.current=animalHistory.current.slice(-5);
          }
          const medium=animalHistory.current.filter(x=>x.score>=MEDIUM_ANIMAL_SCORE).length;
          const weak=animalHistory.current.filter(x=>x.score>=WEAK_ANIMAL_SCORE).length;
          const confirmed=candidate.score>=STRONG_ANIMAL_SCORE||medium>=2||weak>=3;
          if(confirmed){
            animal={class:'animal',score:Math.max(candidate.score,...animalHistory.current.map(x=>x.score))};
            setLastObservation(tx('Posible animal · señal suficiente para grabar',
              'Possible animal · enough evidence to record'));
          }else{
            setLastObservation(candidate.score<WEAK_ANIMAL_SCORE
              ?tx('Señal de animal demasiado débil; mejorá el encuadre',
                'Animal signal too weak; adjust framing')
              :tx('Posible animal · verificando varios fotogramas ('+weak+'/3)',
                'Possible animal · checking several frames ('+weak+'/3)'));
          }
          // Avoid cutting clips because the class fluctuates during recording.
          if(captureRef.current&&candidate.score>=WEAK_ANIMAL_SCORE)
            lastAnimalRef.current=now;
        }else{
          setLastObservation(tx(
            'Sin evidencia de animal. Probá otro ángulo o iluminación.',
            'No animal evidence. Try a different angle or lighting.'
          ));
        }
        if(person){
          if(captureRef.current)finish(true);
          setStatus(tx('Persona visible: grabación descartada por privacidad.',
            'Person visible: recording discarded for privacy.'));
          lastClipRef.current=now;
        }else if(animal){
          lastAnimalRef.current=now;
          if(captureRef.current){
            setStatus(tx('Grabando posible animal…','Recording possible animal…'));
          }else if(readyRef.current&&now-lastClipRef.current>REST_MS&&clipCountRef.current<MAX_CLIPS){
            startClip(animal);
          }
        }else{
          const cap=captureRef.current;
          if(cap&&now-lastAnimalRef.current>SILENCE_MS){
            lastClipRef.current=now;finish();
          }else if(!cap&&lastAnimalRef.current&&now-lastAnimalRef.current>REARM_MS){
            readyRef.current=true;
          }
        }
        const cap=captureRef.current;
        if(cap&&now-cap.started>MAX_DURATION_MS){lastClipRef.current=now;finish();}
      }catch(e){
        if(active){
          setError(tx('Detección detenida: ','Detection stopped: ')+(e instanceof Error?e.message:String(e)));
          setRunning(false);finish();
          return;
        }
      }finally{
        busyRef.current=false;
        if(active)timer=window.setTimeout(()=>void scan(),950);
      }
    }
    void scan();
    return ()=>{active=false;if(timer!==undefined)window.clearTimeout(timer);finish();};
  },[running,stream,video,finish,language,refresh,tx,sourceMode,cameraId]);

  async function activate(){
    if(!stream?.active||!video)return;
    setError('');setClipAlert('');setLoading(true);
    const token=++loadToken.current;
    try{
      if(!window.isSecureContext||!('MediaRecorder' in window)||!recordingMime())
        throw new Error(tx('Este navegador necesita HTTPS y compatibilidad con MediaRecorder.',
          'This browser needs HTTPS and MediaRecorder support.'));
      if(clips.length>=MAX_CLIPS)throw new Error(tx('La bandeja tiene 20 videos: descartá algunos primero.',
        'Inbox contains 20 clips: discard some first.'));
      const detector=await import('./onDeviceAnimalDetector');
      const loaded=await detector.loadLocalAnimalModel();
      if(token!==loadToken.current||!stream.active||!mountedRef.current)return;
      detectorRef.current=loaded;setDetectorBackend(loaded.backend);
      setRunning(true);setStatus(tx('Analizando en el celular. Apuntá la cámara a Josefina.',
        'Scanning on this device. Point the camera at your pet.'));
    }catch(e){if(token===loadToken.current)setError(tx('No se pudo cargar el detector: ',
      'Could not load detector: ')+(e instanceof Error?e.message:String(e)));}
    finally{if(token===loadToken.current)setLoading(false);}
  }
  function stop(){
    setDismissedStart(true);
    loadToken.current++;setRunning(false);setLoading(false);finish();
    setStatus(tx('Detección pausada. Los videos existentes siguen disponibles.',
      'Detection paused. Existing clips remain available.'));
  }
  React.useEffect(()=>{
    if(!stream?.active||!video||dismissedStart)return;
    void activate();
    // A fresh camera stream is started only by a user action. No background surveillance.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[stream,video,dismissedStart]);
  React.useEffect(()=>{
    if(!stream?.active)setDismissedStart(false);
  },[stream]);
  function exportClipEvent(clip:AnimalClip){
    // No coordinates, URLs or identifiable images are included in metadata exports.
    const payload={contract_version:'panthera-live-clip-v1',event_id:clip.id,
      captured_at:clip.capturedAt,study_id:clip.studyId||null,
      camera_id:clip.cameraId||null,source:clip.sourceMode||'device',
      candidate_class:clip.animalClass,detector_score:clip.confidence,
      model:clip.model,review_state:clip.state,clip_bytes:clip.video.size,
      duration_ms:clip.durationMs||null,
      storage:'this_browser_only',species_verified:false,
      inference_location:'researcher_browser',network_measurement:false};
    const objectUrl=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],
      {type:'application/json'}));
    const link=document.createElement('a');link.href=objectUrl;
    link.download='PantheraEDGE_'+clip.id+'.json';
    link.click();window.setTimeout(()=>URL.revokeObjectURL(objectUrl),1000);
  }
  async function update(id:string,action:'keep'|'delete'){
    setError('');
    try{
      if(action==='keep')await setAnimalClipState(id,'kept');
      else await deleteAnimalClip(id);
      await refresh();
      setStatus(action==='keep'?tx('Video conservado localmente. Descargalo para un respaldo seguro.',
        'Clip kept locally. Download it for a safer backup.'):tx('Video descartado del dispositivo.',
        'Clip deleted from this device.'));
    }catch(e){setError(e instanceof Error?e.message:String(e));}
  }
  function download(clip:AnimalClip){
    const url=objects[clip.id];if(!url)return;
    const link=document.createElement('a');
    link.href=url;
    link.download='PantheraLIVE_'+clip.capturedAt.replace(/[^0-9]/g,'').slice(0,14)+
      (clip.mimeType.includes('mp4')?'.mp4':'.webm');
    document.body.appendChild(link);link.click();link.remove();
  }
  const pending=clips.filter(c=>c.state==='pending').length;
  return <section className="local-animal-clips" aria-label={tx('Clips de fauna en el celular','Animal video clips on this device')}>
    <div className="local-animal-head">
      <strong>{sourceMode==='remote'
        ?tx('LIVE · Eventos en transmisión de campo','LIVE · Remote camera event clips')
        :tx('EDGE · Detección local en celular','EDGE · On-device animal detection')}</strong>
      <span className="sci-tag">{tx('EN EL DISPOSITIVO','ON DEVICE')}</span>
    </div>
    <p className="sci-muted">{tx(
      'Busca señales de posible animal y graba automáticamente eventos para revisión. No intenta determinar la especie ni la identidad; pueden ocurrir falsas alarmas.',
      'Looks for possible animal presence and records events for review. It does not determine species or identity; false alarms remain possible.'
    )}</p>
    <div className="local-animal-actions">
      {!running?<button type="button" className="action-button" disabled={!stream?.active||loading}
        onClick={()=>void activate()}>{loading?tx('Cargando detector…','Loading detector…'):
          tx('Activar detección y grabación selectiva','Start selective animal recording')}</button>:
        <button type="button" className="sci-secondary" onClick={stop}>
          {tx('Detener detección','Stop detection')}</button>}
      {running&&<span className="local-animal-active">{tx('Buscando animales…','Searching for animals…')}
        {detectorBackend?' · '+detectorBackend:''}</span>}
      {running&&<div className="local-animal-diagnostics" role="status">
        <span>{tx('Fotogramas analizados: ','Frames analyzed: ')}{framesInspected}</span>
        <span>{lastObservation||tx('Esperando primeros resultados del modelo…',
          'Waiting for initial model output…')}</span>
        {lightBrightness!==null&&<span>{tx('Brillo del fotograma','Frame brightness')}: {lightBrightness}/255 · {
          lightCondition==='too_dark'?tx('Luz insuficiente','Insufficient light'):
          lightCondition==='dim'?tx('Mejora automática para detección','Automatic detection enhancement'):
          tx('Iluminación normal','Normal lighting')
        }</span>}
      </div>}
    </div>
    <p className="sci-muted">{tx(
      'El modo de baja luz mejora únicamente la imagen temporal que analiza la IA; el video guardado permanece original. No es visión nocturna: en oscuridad total se necesita una cámara infrarroja. No se envían imágenes al servidor.',
      'Low-light mode only adjusts a temporary frame for AI analysis; saved videos remain original. This is not night vision: full darkness requires an infrared camera. Images are not sent to the server.'
    )}</p>
    {clipAlert&&<p role="alert" className="sci-notice local-animal-alert">
      {clipAlert}</p>}
    {status&&<p role="status" className="sci-notice">{status}</p>}
    {error&&<p role="alert" className="sci-warning">{error}</p>}
    <div className="local-animal-inbox-head"><strong>{tx('Bandeja de videos locales','Local video inbox')}</strong>
      <span>{pending} {tx('pendientes','pending')} · {clips.length}/{MAX_CLIPS}</span></div>
    {!clips.length?<p className="sci-muted">{tx(
      'No hay clips. Conectá la cámara para comenzar la detección y grabación selectiva.',
      'No clips yet. Connect the camera to begin selective detection and recording.')}</p>:
      <div className="local-animal-inbox">{clips.map(clip=>
        <article key={clip.id} className="local-animal-clip">
          {objects[clip.id]&&<video src={objects[clip.id]} controls playsInline preload="metadata"/>}
          <div className="local-animal-clip-info">
            <strong>{tx('Posible animal · pendiente de revisión',
              'Possible animal · awaiting review')}</strong>
            <small>{tx('Puntuación de detección (no especie): ',
              'Detection score (not species identification): ')}{Math.round(clip.confidence*100)}%</small>
            <small>{new Date(clip.capturedAt).toLocaleString(language==='en'?'en-US':'es-CR')}</small>
            <small>{clip.studyId?tx('Estudio local: ','Local study: ')+clip.studyId:
              tx('Sin estudio asignado','No study assigned')}</small>
            <span className="sci-tag">{clip.state==='kept'?tx('CONSERVADO LOCALMENTE','KEPT LOCALLY'):
              tx('PENDIENTE DE REVISIÓN','PENDING REVIEW')}</span>
          </div>
          <div className="local-animal-clip-actions">
            {clip.state!=='kept'&&<button type="button" className="sci-secondary" onClick={()=>void update(clip.id,'keep')}>
              {tx('Conservar','Keep')}</button>}
            <button type="button" className="sci-secondary" onClick={()=>download(clip)}>
              {tx('Descargar','Download')}</button>
            <button type="button" className="sci-secondary" onClick={()=>exportClipEvent(clip)}>
              {tx('Evento JSON','Event JSON')}</button>
            <button type="button" className="registry-delete-button" onClick={()=>{
              if(window.confirm(tx('¿Descartar este video del dispositivo?','Delete this clip from this device?')))
                void update(clip.id,'delete');
            }}>{tx('Descartar','Discard')}</button>
          </div>
        </article>)}</div>}
    <p className="sci-muted">{tx(
      'Los avisos de clips aparecen automáticamente en la app; Chrome puede solicitar permiso una sola vez para avisos del sistema al conectar la cámara. La página debe permanecer abierta. Los videos siguen en este dispositivo, no en Render ni Supabase.',
      'Clip alerts appear automatically inside the app. Chrome may request one-time permission for device alerts on camera connection. Keep this page open. Videos remain on this device, not Render or Supabase.'
    )}</p>
  </section>;
}
