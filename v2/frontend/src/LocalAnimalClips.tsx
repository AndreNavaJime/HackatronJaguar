import React from 'react';
import {useLanguage} from './language';
import {addAnimalClip,deleteAnimalClip,listAnimalClips,localStudyId,setAnimalClipState,
  MAX_CLIPS,type AnimalClip} from './animalClipStore';
import './LocalAnimalClips.css';

type Prediction={class:string;score:number};
type Detector={detect:(video:HTMLVideoElement)=>Promise<Prediction[]>;backend:string};
type Capture={recorder:MediaRecorder;parts:Blob[];discard:boolean;started:number;
  animalClass:string;confidence:number;studyId:string;mime:string};
type Props={stream:MediaStream|null;video:HTMLVideoElement|null};
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
export default function LocalAnimalClips({stream,video}:Props){
  const {language}=useLanguage();
  const tx=React.useCallback((es:string,en:string)=>language==='en'?en:es,[language]);
  const [loading,setLoading]=React.useState(false);
  const [running,setRunning]=React.useState(false);
  const [status,setStatus]=React.useState('');
  const [error,setError]=React.useState('');
  const [clips,setClips]=React.useState<AnimalClip[]>([]);
  const [objects,setObjects]=React.useState<Record<string,string>>({});
  const [detectorBackend,setDetectorBackend]=React.useState('');
  const detectorRef=React.useRef<Detector|null>(null);
  const captureRef=React.useRef<Capture|null>(null);
  const readyRef=React.useRef(true);
  const lastAnimalRef=React.useRef(0);
  const lastClipRef=React.useRef(0);
  const mountedRef=React.useRef(true);
  const loadToken=React.useRef(0);
  const busyRef=React.useRef(false);

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
          state:'pending',mimeType:blob.type,video:blob};
        void addAnimalClip(item).then(()=>{
          if(!mountedRef.current)return;
          setStatus(tx('Nuevo video con posible animal. Revisalo en la bandeja local.',
            'New possible-animal clip. Review it in your local inbox.'));
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
          }else if(readyRef.current&&now-lastClipRef.current>REST_MS&&clips.length<MAX_CLIPS){
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
  },[running,stream,video,finish,language,clips.length,refresh,tx]);

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
    loadToken.current++;setRunning(false);setLoading(false);finish();
    setStatus(tx('Detección pausada. Los videos existentes siguen disponibles.',
      'Detection paused. Existing clips remain available.'));
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
      <strong>{tx('Detección y videos de animales · Prueba en celular',
        'Animal detection and clips · Phone trial')}</strong>
      <span className="sci-tag">{tx('EN EL DISPOSITIVO','ON DEVICE')}</span>
    </div>
    <p className="sci-muted">{tx(
      'Detecta perro, gato, aves y algunas otras categorías comunes. No reconoce jaguares, sus rosetas ni especies silvestres individualmente. El modelo se descarga la primera vez; después analiza fotogramas en este dispositivo.',
      'Detects dogs, cats, birds and other common categories. It cannot identify jaguars, rosettes, or wild species. Model weights download on first use; frames are then analyzed on this device.'
    )}</p>
    <div className="local-animal-actions">
      {!running?<button type="button" className="action-button" disabled={!stream?.active||loading}
        onClick={()=>void activate()}>{loading?tx('Cargando detector…','Loading detector…'):
          tx('Activar detección y grabación selectiva','Start selective animal recording')}</button>:
        <button type="button" className="sci-secondary" onClick={stop}>
          {tx('Detener detección','Stop detection')}</button>}
      {running&&<span className="local-animal-active">{tx('Buscando animales…','Searching for animals…')}
        {detectorBackend?' · '+detectorBackend:''}</span>}
    </div>
    <p className="sci-muted">{tx(
      'Graba únicamente después de una posible detección (máximo 19 s por clip). No sube fotos ni videos al servidor; detiene la captura si el detector ve personas. No es vigilancia permanente: mantené la pantalla activa.',
      'Records only after possible animal detection (up to 19 s per clip). No photos or videos are uploaded; recording stops if people are detected. Keep this screen active.'
    )}</p>
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
            <button type="button" className="registry-delete-button" onClick={()=>{
              if(window.confirm(tx('¿Descartar este video del dispositivo?','Delete this clip from this device?')))
                void update(clip.id,'delete');
            }}>{tx('Descartar','Discard')}</button>
          </div>
        </article>)}</div>}
    <p className="sci-muted">{tx(
      'Avisos solo dentro de la app. Los videos se guardan temporalmente en este navegador (IndexedDB), no en Supabase ni Render. Para conservarlos con seguridad, descargalos: el navegador puede borrar archivos locales. Las decisiones no crean automáticamente observaciones científicas.',
      'In-app alerts only. Clips are saved to this browser (IndexedDB), not Supabase or Render. Download important clips: browsers may erase local files. Review decisions do not automatically create scientific records.'
    )}</p>
  </section>;
}
