import React from 'react';
import {useLanguage} from './language';
import {addAnimalClip,deleteAnimalClip,listAnimalClips,localStudyId,setAnimalClipState,
  MAX_CLIPS,type AnimalClip} from './animalClipStore';
import './LocalAnimalClips.css';

type Prediction={class:string;score:number};
type Detector={detect:(video:HTMLVideoElement)=>Promise<Prediction[]>;backend:string};
type Capture={recorder:MediaRecorder;parts:Blob[];discard:boolean;started:number;
  animalClass:string;confidence:number;studyId:string;mime:string};
type Props={stream:MediaStream|null;video:HTMLVideoElement|null;
  sourceMode:'device'|'remote';cameraId:string};
const ANIMALS=new Set(['bird','cat','dog','horse','sheep','cow','elephant','bear','zebra','giraffe']);
const LABELS:Record<string,[string,string]>={
  dog:['Perro','Dog'],cat:['Gato','Cat'],bird:['Ave','Bird'],horse:['Caballo','Horse'],
  cow:['Vaca','Cow'],sheep:['Oveja','Sheep'],bear:['Oso','Bear'],
  elephant:['Elefante','Elephant'],zebra:['Cebra','Zebra'],giraffe:['Jirafa','Giraffe'],
};
const THRESHOLD=.56;
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
  const [notificationPermission,setNotificationPermission]=React.useState(
    typeof Notification==='undefined'?'unavailable':Notification.permission);
  const [dismissedStart,setDismissedStart]=React.useState(false);
  const detectorRef=React.useRef<Detector|null>(null);
  const captureRef=React.useRef<Capture|null>(null);
  const readyRef=React.useRef(true);
  const lastAnimalRef=React.useRef(0);
  const lastClipRef=React.useRef(0);
  const mountedRef=React.useRef(true);
  const loadToken=React.useRef(0);
  const busyRef=React.useRef(false);
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
    const startClip=(prediction:Prediction)=>{
      const mime=recordingMime();
      if(!mime)throw new Error(tx('La grabación de video no está disponible en este navegador.',
        'Video recording is not available in this browser.'));
      const rec=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:850_000});
      const cap:Capture={recorder:rec,parts:[],discard:false,started:Date.now(),
        animalClass:prediction.class,confidence:prediction.score,
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
          if(typeof Notification!=='undefined'&&Notification.permission==='granted'){
            try{new Notification('PantheraLIVE', {body:tx(
              'Posible animal detectado. Video listo para revisión en este dispositivo.',
              'Possible animal detected. Clip ready for review on this device.')});}catch{/* Browser may not support page notifications. */}
          }
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
      if(!active||busyRef.current||!video||video.readyState<2||!stream?.active)return;
      busyRef.current=true;
      try{
        const results=await detector.detect(video);
        if(!active)return;
        const now=Date.now();
        const person=results.some(p=>p.class==='person'&&p.score>=.5);
        const winner=results[0];
        if(winner)setLastObservation((LABELS[winner.class]?.[language==='en'?1:0]||winner.class)+
          ' · '+Math.round(winner.score*100)+'% '+tx('puntuación','score'));
        else setLastObservation(tx('Sin objetos reconocidos','No recognizable objects'));
        const animal=results.filter(p=>ANIMALS.has(p.class)&&p.score>=THRESHOLD)
          .sort((a,b)=>b.score-a.score)[0];
        if(person){
          if(captureRef.current)finish(true);
          setStatus(tx('Persona visible: grabación descartada por privacidad.',
            'Person visible: recording discarded for privacy.'));
          lastClipRef.current=now;
        }else if(animal){
          lastAnimalRef.current=now;
          if(captureRef.current){
            setStatus(tx('Grabando posible ','Recording possible ')+
              (LABELS[animal.class]?.[language==='en'?1:0]||animal.class)+'…');
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
    setError('');setLoading(true);
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
  async function requestAlerts(){
    if(typeof Notification==='undefined')return;
    try{
      const permission=await Notification.requestPermission();
      setNotificationPermission(permission);
    }catch{setNotificationPermission('unavailable');}
  }
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
      'Al conectar la cámara empieza automáticamente a buscar animales y grabar eventos. Detecta categorías comunes como perro, gato y ave; no identifica jaguares ni sus rosetas.',
      'Animal detection and event recording start when the camera connects. Recognizes common categories such as dog, cat and bird; not jaguars or rosettes.'
    )}</p>
    <div className="local-animal-actions">
      {!running?<button type="button" className="action-button" disabled={!stream?.active||loading}
        onClick={()=>void activate()}>{loading?tx('Cargando detector…','Loading detector…'):
          tx('Activar detección y grabación selectiva','Start selective animal recording')}</button>:
        <button type="button" className="sci-secondary" onClick={stop}>
          {tx('Detener detección','Stop detection')}</button>}
      {running&&<span className="local-animal-active">{tx('Buscando animales…','Searching for animals…')}
        {detectorBackend?' · '+detectorBackend:''}</span>}
      {running&&lastObservation&&<p className="sci-muted" role="status">{tx('Última detección: ',
        'Latest detection: ')}{lastObservation}</p>}
    </div>
    <p className="sci-muted">{tx(
      'Graba únicamente después de una posible detección (máximo 19 s por clip). No sube fotos ni videos al servidor; detiene la captura si el detector ve personas. No es vigilancia permanente: mantené la pantalla activa.',
      'Records only after possible animal detection (up to 19 s per clip). No photos or videos are uploaded; recording stops if people are detected. Keep this screen active.'
    )}</p>
    {typeof Notification!=='undefined'&&notificationPermission==='default'&&
      <button type="button" className="sci-secondary" onClick={()=>void requestAlerts()}>
        {tx('Permitir aviso al terminar un clip (app abierta)',
          'Enable clip-ready alerts (app open)')}</button>}
    {status&&<p role="status" className="sci-notice">{status}</p>}
    {error&&<p role="alert" className="sci-warning">{error}</p>}
    <div className="local-animal-inbox-head"><strong>{tx('Bandeja de videos locales','Local video inbox')}</strong>
      <span>{pending} {tx('pendientes','pending')} · {clips.length}/{MAX_CLIPS}</span></div>
    {!clips.length?<p className="sci-muted">{tx('Aún no hay videos. Enfocá a Josefina con la cámara local y activá la detección.',
      'No videos yet. Point the local camera at your pet and start detection.')}</p>:
      <div className="local-animal-inbox">{clips.map(clip=>
        <article key={clip.id} className="local-animal-clip">
          {objects[clip.id]&&<video src={objects[clip.id]} controls playsInline preload="metadata"/>}
          <div className="local-animal-clip-info">
            <strong>{LABELS[clip.animalClass]?.[language==='en'?1:0]||clip.animalClass}
              {' · '+Math.round(clip.confidence*100)+'% '+tx('puntuación del detector','detector score')}</strong>
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
      'Avisos en pantalla y aviso opcional del navegador, solo mientras la aplicación permanezca abierta. Los videos se guardan en este dispositivo, no en Supabase ni Render. Descargá los importantes; no se agregan automáticamente al estudio.',
      'In-app alerts and optional browser notifications only while this page is open. Videos stay on this device, not Supabase or Render. Download important clips; they are not automatically added to your study.'
    )}</p>
  </section>;
}
