import React from 'react';
import {useLanguage} from './language';
import type {EdgeEvent} from './scienceShared';
import type {CameraFireCandidate} from './cameraEvents';
import './CameraSourcesPanel.css';

type Props={
  enabled:boolean;
  onEvent:(event:EdgeEvent)=>void;
  onFireEvent:(event:CameraFireCandidate)=>void;
  onOpenFire:()=>void;
};
type Capability='checking'|'ready'|'missing'|'unreachable';
type Recognition={animals:number;persons:number;vehicles:number;at:string};

function newEvent(camera:string,kind:'animal'|'person',source:string,confidence:number|null,simulation:boolean):EdgeEvent{
  const at=new Date().toISOString();
  return {
    event_id:'LIVE-'+Date.now().toString(36).toUpperCase()+'-'+Math.random().toString(36).slice(2,7).toUpperCase(),
    camera_id:camera,timestamp:at,event:'camera_detection_candidate',
    contract_version:'panthera-v1.0',latitude:null,longitude:null,altitude:null,
    temperature:null,humidity:null,class:kind,confidence,
    image_url:'',clip_url:'',transport:simulation?'virtual_event_engine':'browser_frame_review',
    hmac_status:'NOT_CONFIGURED',source,status:simulation?'SIMULATED':'PENDING_REVIEW',
  };
}

function parseError(e:unknown){return e instanceof Error?e.message:String(e);}

export default function CameraSourcesPanel({enabled,onEvent,onFireEvent,onOpenFire}:Props){
  const {language}=useLanguage();
  const tx=(es:string,en:string)=>language==='en'?en:es;
  const [virtualRunning,setVirtualRunning]=React.useState(false);
  const [virtualLast,setVirtualLast]=React.useState('');
  const [virtualCount,setVirtualCount]=React.useState(0);
  const [cameraId,setCameraId]=React.useState('CAM-VIRTUAL-01');
  const [webcamRunning,setWebcamRunning]=React.useState(false);
  const [cameraProblem,setCameraProblem]=React.useState('');
  const [capability,setCapability]=React.useState<Capability>('checking');
  const [permission,setPermission]=React.useState(false);
  const [analyzeEnabled,setAnalyzeEnabled]=React.useState(false);
  const [recognition,setRecognition]=React.useState<Recognition|null>(null);
  const [analysisStatus,setAnalysisStatus]=React.useState('');
  const videoRef=React.useRef<HTMLVideoElement>(null);
  const streamRef=React.useRef<MediaStream|null>(null);
  const tick=React.useRef(0);
  const mounted=React.useRef(true);
  const enabledRef=React.useRef(enabled);
  enabledRef.current=enabled;
  const lock=React.useRef(false);
  const lastClassTime=React.useRef<Record<string,number>>({});
  const demoRef=React.useRef<ReturnType<typeof window.setInterval>|null>(null);
  const [mode,setMode]=React.useState<'virtual'|'device'>('virtual');

  const stopCamera=React.useCallback(()=>{
    for(const track of streamRef.current?.getTracks()||[])track.stop();
    streamRef.current=null;
    if(videoRef.current)videoRef.current.srcObject=null;
    setWebcamRunning(false);setAnalyzeEnabled(false);setAnalysisStatus('');
    setPermission(false);setRecognition(null);
  },[]);
  const stopDemo=React.useCallback(()=>{
    if(demoRef.current!==null){window.clearInterval(demoRef.current);demoRef.current=null;}
    setVirtualRunning(false);
  },[]);

  React.useEffect(()=>{
    mounted.current=true;
    return ()=>{mounted.current=false;stopDemo();stopCamera();};
  },[stopDemo,stopCamera]);
  React.useEffect(()=>{
    if(!enabled){stopDemo();stopCamera();}
  },[enabled,stopDemo,stopCamera]);

  React.useEffect(()=>{
    const controller=new AbortController();
    async function check(){
      try{
        const response=await fetch('/api/capabilities',{cache:'no-store',signal:controller.signal});
        if(!response.ok)throw new Error('HTTP '+response.status);
        const data=await response.json() as {video_ai?:string;animal_detection?:string};
        if(!controller.signal.aborted)setCapability(
          data.animal_detection==='optional_dependencies_installed'?'ready':'missing');
      }catch{
        if(!controller.signal.aborted)setCapability('unreachable');
      }
    }
    void check();
    return ()=>controller.abort();
  },[]);

  function startDemo(){
    stopCamera();stopDemo();
    tick.current=0;setVirtualCount(0);setVirtualLast(tx('Esperando eventos…','Waiting for events…'));
    setMode('virtual');setVirtualRunning(true);
    // Deliberate demonstration sequence: no imagery and NO ML inference.
    const sequence:('empty'|'animal'|'empty'|'person'|'empty'|'smoke'|'empty'|'flame')[]=
      ['empty','animal','empty','person','empty','smoke','empty','flame'];
    function step(){
      const kind=sequence[tick.current%sequence.length];
      tick.current++;
      if(kind==='empty'){
        setVirtualLast(tx('Escena sin evento · no se guarda video','No event · no footage stored'));
        return;
      }
      setVirtualCount(v=>v+1);
      const camera=cameraId.trim().slice(0,80)||'CAM-VIRTUAL-01';
      if(kind==='animal'||kind==='person'){
        onEvent(newEvent(camera,kind,'camera_virtual_simulation',null,true));
        setVirtualLast(kind==='animal'?tx('Evento DEMO: animal · enviado a LIVE','DEMO event: animal · sent to LIVE'):
          tx('Evento DEMO: persona · revisión reservada','DEMO event: person · review only'));
      }else{
        const fire:CameraFireCandidate={
          id:'FIRE-DEMO-'+Date.now().toString(36).toUpperCase()+'-'+tick.current,
          camera_id:camera,recorded_at:new Date().toISOString(),
          signal:kind,source:'virtual_camera_simulation',simulation:true,verified:false,
        };
        onFireEvent(fire);
        setVirtualLast(kind==='smoke'?tx('Evento DEMO: posible humo → PantheraFIRE','DEMO event: possible smoke → PantheraFIRE'):
          tx('Evento DEMO: posible llama → PantheraFIRE','DEMO event: possible flame → PantheraFIRE'));
      }
    }
    step();demoRef.current=window.setInterval(step,4500);
  }

  async function startCamera(){
    stopDemo();stopCamera();setCameraProblem('');
    if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia){
      setCameraProblem(tx('El acceso a cámara requiere HTTPS o localhost y un navegador compatible.',
        'Camera access requires HTTPS or localhost and a supported browser.'));
      return;
    }
    try{
      const stream=await navigator.mediaDevices.getUserMedia({
        audio:false,video:{width:{ideal:640},height:{ideal:360},facingMode:{ideal:'environment'}}
      });
      if(!mounted.current||!enabledRef.current){stream.getTracks().forEach(t=>t.stop());return;}
      streamRef.current=stream;
      setMode('device');setWebcamRunning(true);
      if(videoRef.current){
        videoRef.current.srcObject=stream;
        void videoRef.current.play().catch(()=>{});
      }
      for(const track of stream.getVideoTracks()){
        track.addEventListener('ended',()=>{if(streamRef.current===stream)stopCamera();},{once:true});
      }
    }catch(e){setCameraProblem(tx('No se pudo abrir la cámara: ','Cannot open device camera: ')+parseError(e));}
  }

  React.useEffect(()=>{
    if(!webcamRunning||!enabled||!analyzeEnabled||!permission||capability!=='ready')return;
    let active=true;
    const controller=new AbortController();
    const canvas=document.createElement('canvas');canvas.width=640;canvas.height=360;
    async function inspect(){
      if(!active||lock.current||!videoRef.current||videoRef.current.readyState<2)return;
      lock.current=true;
      try{
        const video=videoRef.current;
        const context=canvas.getContext('2d');
        if(!context||!video)throw new Error('No se puede analizar esta cámara.');
        context.drawImage(video,0,0,640,360);
        const frame=await new Promise<Blob|null>(resolve=>canvas.toBlob(resolve,'image/jpeg',.68));
        if(!frame||!active)return;
        const response=await fetch('/api/images/detect?threshold=0.30',{
          method:'POST',body:frame,headers:{'Content-Type':'image/jpeg'},signal:controller.signal,
        });
        let payload:any=null;
        try{payload=await response.json();}catch{/* leave null */}
        if(!response.ok)throw new Error(typeof payload?.detail==='string'?payload.detail:'HTTP '+response.status);
        if(!active)return;
        const counts=payload?.counts;
        if(!counts||typeof counts.animal!=='number'||typeof counts.person!=='number')
          throw new Error('El servidor devolvió un formato de detecciones inesperado.');
        const snapshot={animals:counts.animal,persons:counts.person,vehicles:counts.vehicle||0,at:new Date().toISOString()};
        setRecognition(snapshot);
        setAnalysisStatus(tx('Último fotograma analizado · no se guarda imagen ni clip en la sesión.',
          'Latest frame processed · no image or clip stored in the session.'));
        const camera='CAM-DISPOSITIVO-LOCAL';
        for(const kind of ['animal','person'] as const){
          if(counts[kind]>0){
            const last=lastClassTime.current[kind]||0;
            if(Date.now()-last<30000)continue;
            lastClassTime.current[kind]=Date.now();
            const best=Array.isArray(payload.detections)
              ?Math.max(0,...payload.detections.filter((d:any)=>d.class_name===kind)
                .map((d:any)=>typeof d.confidence==='number'?d.confidence:0)):0;
            onEvent(newEvent(camera,kind,'browser_camera_megadetector_opt_in',best||null,false));
          }
        }
      }catch(e){
        if(active&&!controller.signal.aborted){
          setAnalysisStatus(tx('Análisis detenido por error: ','Analysis stopped after error: ')+parseError(e));
          setAnalyzeEnabled(false);
        }
      }finally{lock.current=false;}
    }
    void inspect();
    const interval=window.setInterval(()=>void inspect(),12000);
    return ()=>{active=false;controller.abort();window.clearInterval(interval);};
  },[webcamRunning,analyzeEnabled,permission,capability,enabled,language,onEvent]);

  const capabilityMessage=capability==='checking'?tx('Consultando disponibilidad…','Checking availability…')
    :capability==='missing'?tx('MegaDetector no está instalado en este servidor. La vista previa funciona, pero la detección IA está deshabilitada.',
      'MegaDetector is not installed on this server. Preview works; AI detection is disabled.')
    :capability==='unreachable'?tx('No hay conexión con la API de análisis. La cámara puede mostrarse localmente.',
      'Analysis API is unreachable. Device camera preview still works locally.')
    :tx('Dependencias de MegaDetector detectadas; la inferencia requiere que los pesos y recursos funcionen.',
      'MegaDetector dependencies detected; successful inference still requires model weights and compute.');
  return <section className="sci-panel camera-sources" aria-label={tx('Centro de cámaras','Camera center')}>
    <div className="sci-panel-head">
      <h3>{tx('Fuentes de cámara · eventos automáticos','Camera sources · automatic events')}</h3>
      <span className="sci-tag">{tx('INTEGRACIÓN EXPERIMENTAL','EXPERIMENTAL INTEGRATION')}</span>
    </div>
    <p className="sci-muted">{tx(
      'PantheraLIVE es el punto de entrada de las cámaras. Los archivos manuales se analizan únicamente en PantheraID. Aquí probamos eventos desde una fuente virtual o una cámara del dispositivo.',
      'PantheraLIVE is the camera entry point. Manual file analysis belongs only in PantheraID. Here we test events with a virtual source or a device camera.')}</p>
    <div className="camera-modes">
      <button type="button" aria-pressed={mode==='virtual'} className={mode==='virtual'?'active':''}
        onClick={()=>{stopCamera();setMode('virtual');}}>{tx('Cámara virtual','Virtual camera')}</button>
      <button type="button" aria-pressed={mode==='device'} className={mode==='device'?'active':''}
        onClick={()=>{stopDemo();setMode('device');}}>{tx('Cámara del dispositivo','Device camera')}</button>
    </div>
    {mode==='virtual'?<div className="camera-source-body">
      <div className="camera-virtual-scene">
        <div className="camera-live-light"><i className={virtualRunning?'on':''}/>{virtualRunning?tx('EMULANDO EVENTOS','SIMULATING EVENTS'):tx('EN ESPERA','STANDBY')}</div>
        <strong>CAM · PantheraLAB</strong>
        <span>{virtualRunning?virtualLast:tx('Fuente de eventos virtuales · no contiene imágenes reales',
          'Virtual event source · no real imagery')}</span>
        <small>{tx('Fauna · personas → LIVE   |   humo · llamas → FIRE',
          'Wildlife · people → LIVE   |   smoke · flames → FIRE')}</small>
      </div>
      <div className="camera-source-controls">
        <label className="sci-field"><span>{tx('ID de cámara virtual','Virtual camera ID')}</span>
          <input value={cameraId} maxLength={80} disabled={virtualRunning}
            onChange={e=>setCameraId(e.target.value)}/></label>
        <div className="camera-action-row">
          {!virtualRunning?<button type="button" className="action-button" onClick={startDemo} disabled={!enabled}>
            {tx('Iniciar cámara virtual','Start virtual camera')}</button>
            :<button type="button" className="sci-secondary" onClick={stopDemo}>
              {tx('Detener simulación','Stop simulation')}</button>}
          <button type="button" className="sci-secondary" onClick={onOpenFire}>
            {tx('Ver avisos en PantheraFIRE ↗','View PantheraFIRE events ↗')}</button>
        </div>
        <p className="sci-muted">{tx(
          'La simulación produce eventos cada pocos segundos, incluidos momentos sin evento. No ejecuta IA, no simula imágenes de jaguares, no avisa a emergencias y no genera evidencias científicas.',
          'The simulation emits periodic events, including no-event intervals. It runs no AI, creates no jaguar imagery, sends no emergency notifications and produces no scientific evidence.')}</p>
        {virtualCount>0&&<p className="sci-notice">{virtualCount} {tx('eventos de demostración emitidos','demonstration events emitted')}</p>}
      </div>
    </div>:<div className="camera-source-body">
      <div className="camera-device-scene">
        <video ref={videoRef} playsInline autoPlay muted aria-label={tx('Vista previa de cámara','Camera preview')}/>
        {!webcamRunning&&<div className="camera-device-idle"><strong>{tx('Cámara desconectada','Camera disconnected')}</strong>
          <small>{tx('Abrí la webcam o cámara del teléfono con el permiso del navegador.',
            'Open your computer or phone camera with browser permission.')}</small></div>}
        <div className="camera-live-light"><i className={webcamRunning?'on':''}/>
          {webcamRunning?tx('VISTA PREVIA LOCAL','LOCAL PREVIEW'):tx('NO CONECTADA','NOT CONNECTED')}</div>
      </div>
      <div className="camera-source-controls">
        <div className="camera-action-row">
          {!webcamRunning?<button type="button" className="action-button" disabled={!enabled}
            onClick={()=>void startCamera()}>{tx('Conectar cámara de este dispositivo','Connect this device camera')}</button>
            :<button type="button" className="sci-secondary" onClick={stopCamera}>
              {tx('Desconectar cámara','Disconnect camera')}</button>}
        </div>
        {cameraProblem&&<p className="sci-warning" role="alert">{cameraProblem}</p>}
        <p className="sci-muted">{tx(
          'Abrir la cámara solo muestra una vista previa local. No se graba ni envía video por defecto. Un stream RTSP de cámara trampa requerirá un adaptador/gateway compatible.',
          'Opening the camera only shows a local preview. No recording or uploads occur by default. Camera-trap RTSP streams require a compatible gateway/adapter.')}</p>
        <div className="camera-ai">
          <strong>{tx('Filtro opcional de animales y personas · MegaDetector',
            'Optional wildlife/person screening · MegaDetector')}</strong>
          <p className="sci-muted">{capabilityMessage}</p>
          <label className="camera-permission"><input type="checkbox" checked={permission}
            disabled={!webcamRunning||capability!=='ready'||analyzeEnabled}
            onChange={e=>setPermission(e.target.checked)}/>
            <span>{tx(
              'Autorizo transmitir fotogramas individuales al backend para inferencia. No usar con personas identificables ni escenas sensibles: el servidor experimental no tiene autenticación.',
              'I authorize sending individual frames to the backend for inference. Do not use with identifiable people or sensitive scenes: the experimental server has no authentication.')}</span></label>
          <div className="camera-action-row">
            {!analyzeEnabled?<button type="button" className="sci-secondary"
              disabled={!webcamRunning||!permission||capability!=='ready'}
              onClick={()=>{lastClassTime.current={};setAnalysisStatus('');setAnalyzeEnabled(true);}}>
              {tx('Activar análisis IA (cada 12 s)','Enable AI screening (every 12 s)')}</button>
              :<button type="button" className="sci-secondary" onClick={()=>setAnalyzeEnabled(false)}>
                {tx('Detener análisis IA','Stop AI screening')}</button>}
          </div>
          {analysisStatus&&<p className="sci-notice" role="status">{analysisStatus}</p>}
          {recognition&&<div className="camera-counts">
            <span>{tx('Animales','Animals')}: <b>{recognition.animals}</b></span>
            <span>{tx('Personas','People')}: <b>{recognition.persons}</b></span>
            <span>{tx('Vehículos','Vehicles')}: <b>{recognition.vehicles}</b></span>
          </div>}
          <p className="sci-muted">{tx(
            'Solo se generan metadatos preliminares en la sesión; no se graban clips, no se confirma ninguna especie y no se detectan incendios con MegaDetector. No usar como vigilancia de seguridad.',
            'Only preliminary session metadata is generated: no clips recorded, no species identification and no fire recognition by MegaDetector. Not for security surveillance.')}</p>
        </div>
      </div>
    </div>}
  </section>;
}
