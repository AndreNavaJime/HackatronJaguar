import {apiFetch} from './apiClient';
import React from 'react';
import {useLanguage} from './language';
import type {EdgeEvent} from './scienceShared';
import './CameraSourcesPanel.css';
import {connectWhep} from './whep';
import LocalAnimalClips from './LocalAnimalClips';
import {requestClipAlertsOnCameraConnect} from './clipNotifications';

type Props={
  enabled:boolean;
  onEvent:(event:EdgeEvent)=>void;
};
type Capability='checking'|'ready'|'missing'|'unreachable';
type Recognition={animals:number;persons:number;vehicles:number;at:string};

function newEvent(camera:string,kind:'animal'|'person',source:string,confidence:number|null):EdgeEvent{
  const at=new Date().toISOString();
  return {
    event_id:'LIVE-'+Date.now().toString(36).toUpperCase()+'-'+Math.random().toString(36).slice(2,7).toUpperCase(),
    camera_id:camera,timestamp:at,event:'camera_detection_candidate',
    contract_version:'panthera-v1.0',latitude:null,longitude:null,altitude:null,
    temperature:null,humidity:null,class:kind,confidence,
    image_url:'',clip_url:'',transport:'browser_frame_review',
    hmac_status:'NOT_CONFIGURED',source,status:'PENDING_REVIEW',
  };
}

function parseError(e:unknown){return e instanceof Error?e.message:String(e);}

export default function CameraSourcesPanel({enabled,onEvent}:Props){
  const {language}=useLanguage();
  const tx=(es:string,en:string)=>language==='en'?en:es;
  const [whepUrl,setWhepUrl]=React.useState('');
  const [webcamRunning,setWebcamRunning]=React.useState(false);
  const [cameraProblem,setCameraProblem]=React.useState('');
  const [torchSupported,setTorchSupported]=React.useState(false);
  const [torchEnabled,setTorchEnabled]=React.useState(false);
  const [capability,setCapability]=React.useState<Capability>('checking');
  const [permission,setPermission]=React.useState(false);
  const [analyzeEnabled,setAnalyzeEnabled]=React.useState(false);
  const [recognition,setRecognition]=React.useState<Recognition|null>(null);
  const [species,setSpecies]=React.useState<{label:string;score:number}[]>([]);
  const [analysisStatus,setAnalysisStatus]=React.useState('');
  const videoRef=React.useRef<HTMLVideoElement>(null);
  const streamRef=React.useRef<MediaStream|null>(null);
  const peerRef=React.useRef<RTCPeerConnection|null>(null);
  const mounted=React.useRef(true);
  const enabledRef=React.useRef(enabled);
  enabledRef.current=enabled;
  const modeRef=React.useRef<'device'|'remote'>('device');
  const lock=React.useRef(false);
  const lastClassTime=React.useRef<Record<string,number>>({});
  const [mode,setMode]=React.useState<'device'|'remote'>('device');

  const stopCamera=React.useCallback(()=>{
    peerRef.current?.close();peerRef.current=null;
    for(const track of streamRef.current?.getTracks()||[])track.stop();
    streamRef.current=null;
    if(videoRef.current)videoRef.current.srcObject=null;
    setWebcamRunning(false);setAnalyzeEnabled(false);setAnalysisStatus('');
    setTorchSupported(false);setTorchEnabled(false);
    setPermission(false);setRecognition(null);setSpecies([]);
  },[]);
  React.useEffect(()=>{
    mounted.current=true;
    return ()=>{mounted.current=false;stopCamera();};
  },[stopCamera]);
  React.useEffect(()=>{
    if(!enabled)stopCamera();
  },[enabled,stopCamera]);

  React.useEffect(()=>{
    const onVisibility=()=>{if(document.hidden)stopCamera();};
    document.addEventListener('visibilitychange',onVisibility);
    return ()=>document.removeEventListener('visibilitychange',onVisibility);
  },[stopCamera]);

  React.useEffect(()=>{
    if(mode!=='remote')return;
    const controller=new AbortController();
    async function check(){
      try{
        const response=await apiFetch('/api/live/capabilities',{cache:'no-store',signal:controller.signal});
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
  },[mode]);

  async function startCamera(){
    // The camera button is the user's activation gesture. Browser notification
    // permission may be requested once here, not with an extra UI toggle.
    void requestClipAlertsOnCameraConnect();
    stopCamera();setCameraProblem('');
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
      try{
        const caps=stream.getVideoTracks()[0]?.getCapabilities() as
          (MediaTrackCapabilities&{torch?:boolean|boolean[]})|undefined;
        setTorchSupported(caps?.torch===true||
          (Array.isArray(caps?.torch)&&caps.torch.includes(true)));
      }catch{setTorchSupported(false);}
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

  async function toggleTorch(){
    const track=streamRef.current?.getVideoTracks()[0];
    if(mode!=='device'||!torchSupported||!track)return;
    const next=!torchEnabled;
    try{
      await track.applyConstraints({advanced:[
        {torch:next} as unknown as MediaTrackConstraintSet
      ]});
      setTorchEnabled(next);
      setCameraProblem('');
    }catch{
      setCameraProblem(tx('Este dispositivo no permite controlar la linterna desde Chrome.',
        'This device cannot control the flashlight through Chrome.'));
      setTorchSupported(false);
    }
  }

  async function startRemote(){
    void requestClipAlertsOnCameraConnect();
    stopCamera();setCameraProblem('');
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
        const response=await apiFetch('/api/live/wildlife-frame?threshold=0.30',{
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
            onEvent(newEvent(camera,kind,'browser_camera_megadetector_opt_in',best||null));
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
      <h3>{tx('PantheraLIVE · EDGE + Transmisión en vivo','PantheraLIVE · EDGE + Live streaming')}</h3>
      <span className="sci-tag">{tx('EN PRUEBAS','IN TESTING')}</span>
    </div>
    <div className="camera-modes" role="group" aria-label={tx('Tipo de cámara','Camera type')}>
      <button type="button" aria-pressed={mode==='remote'} className={mode==='remote'?'active':''}
        onClick={()=>{modeRef.current='remote';stopCamera();setMode('remote');}}>
        {tx('LIVE · Cámara remota','LIVE · Remote camera')}</button>
      <button type="button" aria-pressed={mode==='device'} className={mode==='device'?'active':''}
        onClick={()=>{modeRef.current='device';stopCamera();setMode('device');}}>
        {tx('EDGE · Cámara de este dispositivo','EDGE · On-device camera')}</button>
    </div>
    <div className="camera-source-body">
      <div className="camera-device-scene">
        <video ref={videoRef} playsInline autoPlay muted aria-label={tx('Vista previa de cámara','Camera preview')}/>
        {!webcamRunning&&<div className="camera-device-idle"><strong>{tx('Cámara desconectada','Camera disconnected')}</strong>
          <small>{mode==='remote'
            ?tx('Conectá una cámara remota para iniciar la transmisión.',
              'Connect a remote camera to start streaming.')
            :tx('Activá la cámara del celular o computadora.',
              'Turn on your phone or computer camera.')}</small></div>}
        <div className="camera-live-light"><i className={webcamRunning?'on':''}/>
          {webcamRunning?tx('CONECTADA','CONNECTED'):tx('NO CONECTADA','NOT CONNECTED')}</div>
      </div>
      <div className="camera-source-controls">
        {mode==='remote'&&<label className="sci-field"><span>{tx('Dirección de la cámara (WHEP HTTPS)','Camera address (WHEP HTTPS)')}</span>
          <input type="url" value={whepUrl} disabled={webcamRunning}
            placeholder="https://servidor.example/api/webrtc?src=camera1"
            onChange={e=>setWhepUrl(e.target.value)} autoComplete="off" spellCheck={false}/></label>}
        <div className="camera-action-row">
          {!webcamRunning?<button type="button" className="action-button" disabled={!enabled||(mode==='remote'&&!whepUrl.trim())}
            onClick={()=>void (mode==='remote'?startRemote():startCamera())}>{mode==='remote'
              ?tx('Conectar cámara de campo','Connect field camera')
              :tx('Activar cámara local','Start local camera')}</button>
            :<button type="button" className="sci-secondary" onClick={stopCamera}>
              {tx('Desconectar','Disconnect')}</button>}
        </div>
        {mode==='device'&&webcamRunning&&torchSupported&&
          <div className="camera-torch-control">
            <button type="button" className="sci-secondary" aria-pressed={torchEnabled}
              onClick={()=>void toggleTorch()}>
              {torchEnabled?tx('Apagar luz auxiliar','Turn off flashlight'):
                tx('Encender luz auxiliar (prueba doméstica)','Turn on flashlight (home test)')}
            </button>
            <small>{tx('Solo para probar con mascotas. No apuntar iluminación visible a fauna silvestre.',
              'For home pet testing only. Avoid shining visible light directly at wildlife.')}</small>
          </div>}
        {cameraProblem&&<p className="sci-warning" role="alert">{cameraProblem}</p>}
        {mode==='remote'&&<p className="sci-muted">{tx(
          'Requiere un gateway WHEP/WebRTC con HTTPS y CORS. La detección automática se ejecuta en este navegador mientras la pantalla permanezca abierta; todavía no funciona como servidor autónomo 24/7.',
          'Requires a WHEP/WebRTC gateway with HTTPS and CORS. Automatic detection runs in this browser while the page stays open; this is not yet a 24/7 autonomous server.'
        )}</p>}
        {mode==='remote'&&<details className="method-details method-details-compact camera-advanced-server">
          <summary>{tx('Análisis de servidor (opcional, pendiente de modelo)',
            'Server analysis (optional, model not yet installed)')}</summary>
        <div className="camera-ai">
          <strong>{tx('Detección automática · MegaDetector / SpeciesNet',
            'Automatic detection · MegaDetector / SpeciesNet')}</strong>
          <p className="sci-muted">{capabilityMessage}</p>
          <label className="camera-permission"><input type="checkbox" checked={permission}
            disabled={!webcamRunning||capability!=='ready'}
            onChange={e=>{setPermission(e.target.checked);setAnalyzeEnabled(e.target.checked);}}/>
            <span>{tx(
              'Análisis experimental: examina un fotograma cada 12 s; NO graba videos. No activar con personas identificables.',
              'Experimental screening: examines one frame every 12 s; it does NOT record video. Do not enable with identifiable people.')}</span></label>
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
        </details>}
      </div>
    </div>
    <LocalAnimalClips key={mode} sourceMode={mode}
      cameraId={mode==='remote'?'WHEP-CAMARA-REMOTA':'CAM-DISPOSITIVO-LOCAL'}
      stream={webcamRunning?streamRef.current:null} video={videoRef.current}/>
  </section>;
}
