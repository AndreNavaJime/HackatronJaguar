import React from 'react';
import {useLanguage} from './language';
import type {EdgeEvent} from './scienceShared';
import './CameraSourcesPanel.css';
import {connectWhep} from './whep';

type Props={
  enabled:boolean;
  onEvent:(event:EdgeEvent)=>void;
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

export default function CameraSourcesPanel({enabled,onEvent}:Props){
  const {language}=useLanguage();
  const tx=(es:string,en:string)=>language==='en'?en:es;
  const [virtualRunning,setVirtualRunning]=React.useState(false);
  const [virtualLast,setVirtualLast]=React.useState('');
  const [virtualCount,setVirtualCount]=React.useState(0);
  const [cameraId,setCameraId]=React.useState('CAM-VIRTUAL-01');
  const [whepUrl,setWhepUrl]=React.useState('');
  const [webcamRunning,setWebcamRunning]=React.useState(false);
  const [cameraProblem,setCameraProblem]=React.useState('');
  const [capability,setCapability]=React.useState<Capability>('checking');
  const [permission,setPermission]=React.useState(false);
  const [analyzeEnabled,setAnalyzeEnabled]=React.useState(false);
  const [recognition,setRecognition]=React.useState<Recognition|null>(null);
  const [species,setSpecies]=React.useState<{label:string;score:number}[]>([]);
  const [analysisStatus,setAnalysisStatus]=React.useState('');
  const videoRef=React.useRef<HTMLVideoElement>(null);
  const streamRef=React.useRef<MediaStream|null>(null);
  const peerRef=React.useRef<RTCPeerConnection|null>(null);
  const tick=React.useRef(0);
  const mounted=React.useRef(true);
  const enabledRef=React.useRef(enabled);
  enabledRef.current=enabled;
  const modeRef=React.useRef<'virtual'|'device'|'remote'>('device');
  const lock=React.useRef(false);
  const lastClassTime=React.useRef<Record<string,number>>({});
  const demoRef=React.useRef<ReturnType<typeof window.setInterval>|null>(null);
  const [mode,setMode]=React.useState<'virtual'|'device'|'remote'>('device');

  const stopCamera=React.useCallback(()=>{
    peerRef.current?.close();peerRef.current=null;
    for(const track of streamRef.current?.getTracks()||[])track.stop();
    streamRef.current=null;
    if(videoRef.current)videoRef.current.srcObject=null;
    setWebcamRunning(false);setAnalyzeEnabled(false);setAnalysisStatus('');
    setPermission(false);setRecognition(null);setSpecies([]);
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
    const onVisibility=()=>{if(document.hidden){stopDemo();stopCamera();}};
    document.addEventListener('visibilitychange',onVisibility);
    return ()=>document.removeEventListener('visibilitychange',onVisibility);
  },[stopDemo,stopCamera]);

  React.useEffect(()=>{
    const controller=new AbortController();
    async function check(){
      try{
        const response=await fetch('/api/live/capabilities',{cache:'no-store',signal:controller.signal});
        if(!response.ok)throw new Error('HTTP '+response.status);
        const data=await response.json() as {wildlife_detector?:string};
        if(!controller.signal.aborted)setCapability(
          data.wildlife_detector==='available'?'ready':'missing');
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
    modeRef.current='virtual';
    setMode('virtual');setVirtualRunning(true);
    // Deliberate demonstration sequence: no imagery and NO ML inference.
    // Synthetic wildlife/person events for the review workflow; no fire here.
    const sequence:('empty'|'animal'|'person')[]=['animal','empty','person','empty'];
    function step(){
      const kind=sequence[tick.current%sequence.length];
      tick.current++;
      if(kind==='empty'){
        setVirtualLast(tx('Sin evento · no se conserva video','No event · no footage stored'));
        return;
      }
      setVirtualCount(v=>v+1);
      const camera=cameraId.trim().slice(0,80)||'CAM-VIRTUAL-01';
      onEvent(newEvent(camera,kind,'camera_virtual_simulation',null,true));
      setVirtualLast(kind==='animal'?tx('DEMO · Animal · evento en LIVE','DEMO · Animal · LIVE event')
        :tx('DEMO · Persona · revisión restringida','DEMO · Person · private review'));
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
      if(!mounted.current||!enabledRef.current||modeRef.current!=='device'){
        stream.getTracks().forEach(track=>track.stop());
        return;
      }
      streamRef.current=stream;
      setWebcamRunning(true);
      if(videoRef.current){
        videoRef.current.srcObject=stream;
        void videoRef.current.play().catch(()=>{});
      }
      for(const track of stream.getVideoTracks()){
        track.addEventListener('ended',()=>{if(streamRef.current===stream)stopCamera();},{once:true});
      }
    }catch(e){setCameraProblem(tx('No se pudo abrir la cámara: ','Cannot open device camera: ')+parseError(e));}
  }

  async function startRemote(){
    stopDemo();stopCamera();setCameraProblem('');
    try{
      const remote=await connectWhep(whepUrl.trim());
      if(!mounted.current||!enabledRef.current||modeRef.current!=='remote'){
        remote.peer.close();remote.stream.getTracks().forEach(t=>t.stop());
        return;
      }
      peerRef.current=remote.peer;streamRef.current=remote.stream;
      setWebcamRunning(true);
      if(videoRef.current){
        videoRef.current.srcObject=remote.stream;
        void videoRef.current.play().catch(()=>{});
      }
    }catch(error){
      setCameraProblem(tx('No fue posible conectar WebRTC (revisá HTTPS, CORS y el gateway). ',
        'WebRTC connection failed (check HTTPS, CORS and gateway). ')+parseError(error));
    }
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
        const response=await fetch('/api/live/wildlife-frame?threshold=0.30',{
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
        setSpecies(Array.isArray(payload.speciesnet?.suggestions)?payload.speciesnet.suggestions:[]);
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
    :tx('Detección de fauna disponible. SpeciesNet sugerirá especies si el modelo está configurado.',
      'Wildlife detection available. SpeciesNet suggests species if its model is configured.');
  return <section className="sci-panel camera-sources" aria-label={tx('Centro de cámaras','Camera center')}>
    <div className="sci-panel-head">
      <h3>{tx('Cámara de fauna','Wildlife camera')}</h3>
      <span className="sci-tag">{tx('EN PRUEBAS','IN TESTING')}</span>
    </div>
    <div className="camera-modes">
      <button type="button" aria-pressed={mode==='device'} className={mode==='device'?'active':''}
        onClick={()=>{modeRef.current='device';stopDemo();stopCamera();setMode('device');}}>{tx('Este dispositivo','This device')}</button>
      <button type="button" aria-pressed={mode==='remote'} className={mode==='remote'?'active':''}
        onClick={()=>{modeRef.current='remote';stopDemo();stopCamera();setMode('remote');}}>{tx('WebRTC · IP','WebRTC · IP')}</button>
      <button type="button" aria-pressed={mode==='virtual'} className={mode==='virtual'?'active':''}
        onClick={()=>{modeRef.current='virtual';stopCamera();stopDemo();setMode('virtual');}}>{tx('Simulación','Simulation')}</button>
    </div>
    {mode==='virtual'?<div className="camera-source-body">
      <div className="camera-virtual-scene">
        <div className="camera-live-light"><i className={virtualRunning?'on':''}/>{virtualRunning?tx('EMULANDO EVENTOS','SIMULATING EVENTS'):tx('EN ESPERA','STANDBY')}</div>
        <strong>CAM · PantheraLAB</strong>
        <span>{virtualRunning?virtualLast:tx('Fuente de eventos virtuales · no contiene imágenes reales',
          'Virtual event source · no real imagery')}</span>
        <small>{tx('Fauna y personas → PantheraLIVE','Wildlife and people → PantheraLIVE')}</small>
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
        </div>
        <p className="sci-muted">{tx(
          'Solo eventos ficticios de fauna y personas. No se genera evidencia científica.',
          'Fictional wildlife/person events only. No scientific evidence is generated.')}</p>
        {virtualCount>0&&<p className="sci-notice">{virtualCount} {tx('eventos de demostración emitidos','demonstration events emitted')}</p>}
      </div>
    </div>:<div className="camera-source-body">
      <div className="camera-device-scene">
        <video ref={videoRef} playsInline autoPlay muted aria-label={tx('Vista previa de cámara','Camera preview')}/>
        {!webcamRunning&&<div className="camera-device-idle"><strong>{tx('Cámara desconectada','Camera disconnected')}</strong>
          <small>{tx('Conectá para ver el video en vivo.',
            'Connect to see live video.')}</small></div>}
        <div className="camera-live-light"><i className={webcamRunning?'on':''}/>
          {webcamRunning?tx('VISTA PREVIA LOCAL','LOCAL PREVIEW'):tx('NO CONECTADA','NOT CONNECTED')}</div>
      </div>
      <div className="camera-source-controls">
        {mode==='remote'&&<label className="sci-field"><span>{tx('URL HTTPS · WHEP / go2rtc','HTTPS URL · WHEP / go2rtc')}</span>
          <input type="url" value={whepUrl} disabled={webcamRunning}
            placeholder="https://servidor.example/api/webrtc?src=camera1"
            onChange={e=>setWhepUrl(e.target.value)} autoComplete="off" spellCheck={false}/></label>}
        <div className="camera-action-row">
          {!webcamRunning?<button type="button" className="action-button" disabled={!enabled||(mode==='remote'&&!whepUrl.trim())}
            onClick={()=>void (mode==='remote'?startRemote():startCamera())}>{mode==='remote'
              ?tx('Conectar WebRTC','Connect WebRTC')
              :tx('Conectar cámara','Connect camera')}</button>
            :<button type="button" className="sci-secondary" onClick={stopCamera}>
              {tx('Desconectar','Disconnect')}</button>}
        </div>
        {cameraProblem&&<p className="sci-warning" role="alert">{cameraProblem}</p>}
        {mode==='remote'&&<p className="sci-muted">{tx(
          'Se requiere un gateway WHEP compatible, HTTPS y CORS.',
          'Requires a WHEP-compatible gateway, HTTPS and CORS.')}</p>
        <div className="camera-ai">
          <strong>{tx('Detección automática · MegaDetector / SpeciesNet',
            'Automatic detection · MegaDetector / SpeciesNet')}</strong>
          <p className="sci-muted">{capabilityMessage}</p>
          <label className="camera-permission"><input type="checkbox" checked={permission}
            disabled={!webcamRunning||capability!=='ready'}
            onChange={e=>{setPermission(e.target.checked);setAnalyzeEnabled(e.target.checked);}}/>
            <span>{tx(
              'Activar análisis: enviará fotogramas al servidor cada 12 s. No usar con personas identificables; el servidor no tiene acceso protegido.',
              'Enable analysis: sends frames every 12 s. Do not use with identifiable people; the server is not access-protected.')}</span></label>
          {analyzeEnabled&&<p className="sci-notice" role="status">{tx('Análisis automático activo · cada 12 segundos','Automatic screening active · every 12 seconds')}</p>}
          {analysisStatus&&<p className="sci-notice" role="status">{analysisStatus}</p>}
          {species.length>0&&<p className="sci-muted">{tx('SpeciesNet · sugerencia sin validar: ','SpeciesNet · unverified suggestion: ')}
            {species[0].label} ({Math.round(species[0].score*100)}%)</p>}
          {recognition&&<div className="camera-counts">
            <span>{tx('Animales','Animals')}: <b>{recognition.animals}</b></span>
            <span>{tx('Personas','People')}: <b>{recognition.persons}</b></span>
            <span>{tx('Vehículos','Vehicles')}: <b>{recognition.vehicles}</b></span>
          </div>}
          <p className="sci-muted">{tx(
            'Solo genera eventos preliminares; aún no guarda clips.',
            'Preliminary events only; clips are not yet saved.')}</p>
        </div>
      </div>
    </div>}
  </section>;
}
