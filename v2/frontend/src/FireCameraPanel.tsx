import React from 'react';
import {useLanguage} from './language';
import type {CameraFireCandidate} from './cameraEvents';
import './FireCameraPanel.css';
import {connectWhep} from './whep';

type Props={onEvent:(event:CameraFireCandidate)=>void};
type Readiness='checking'|'ready'|'missing'|'offline';

export default function FireCameraPanel({onEvent}:Props){
  const {language}=useLanguage();
  const tx=(es:string,en:string)=>language==='en'?en:es;
  const [cameraActive,setCameraActive]=React.useState(false);
  const [permission,setPermission]=React.useState(false);
  const [cameraMode,setCameraMode]=React.useState<'device'|'remote'>('device');
  const [whepUrl,setWhepUrl]=React.useState('');
  const [readiness,setReadiness]=React.useState<Readiness>('checking');
  const [status,setStatus]=React.useState('');
  const [score,setScore]=React.useState<number|null>(null);
  const video=React.useRef<HTMLVideoElement|null>(null);
  const stream=React.useRef<MediaStream|null>(null);
  const peer=React.useRef<RTCPeerConnection|null>(null);
  const modeRef=React.useRef<'device'|'remote'>('device');
  const lastCandidate=React.useRef(0);
  const inFlight=React.useRef(false);
  const mounted=React.useRef(true);
  const fireCallback=React.useRef(onEvent);
  fireCallback.current=onEvent;

  const stop=React.useCallback(()=>{
    peer.current?.close();peer.current=null;
    stream.current?.getTracks().forEach(track=>track.stop());
    stream.current=null;
    if(video.current)video.current.srcObject=null;
    setCameraActive(false);setPermission(false);setScore(null);
  },[]);
  React.useEffect(()=>{
    mounted.current=true;
    return()=>{mounted.current=false;stop();};
  },[stop]);
  React.useEffect(()=>{
    const stopOnHide=()=>{if(document.hidden)stop();};
    document.addEventListener('visibilitychange',stopOnHide);
    return()=>document.removeEventListener('visibilitychange',stopOnHide);
  },[stop]);
  React.useEffect(()=>{
    const ctl=new AbortController();
    fetch('/api/live/capabilities',{cache:'no-store',signal:ctl.signal})
      .then(async r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json();})
      .then((c:{fire_detector?:string})=>{if(!ctl.signal.aborted)setReadiness(
        c.fire_detector==='configured'?'ready':'missing');})
      .catch(()=>{if(!ctl.signal.aborted)setReadiness('offline');});
    return()=>ctl.abort();
  },[]);

  async function start(){
    setStatus('');
    if(cameraMode==='device'&&(!navigator.mediaDevices?.getUserMedia||!window.isSecureContext)){
      setStatus(tx('Se requiere HTTPS y permiso de cámara.','HTTPS and camera access are required.'));return;
    }
    try{
      const remote=cameraMode==='remote'?await connectWhep(whepUrl.trim()):null;
      const current=remote?.stream||await navigator.mediaDevices.getUserMedia({audio:false,video:{
        width:{ideal:640},height:{ideal:360},facingMode:{ideal:'environment'}}});
      if(!mounted.current||document.hidden||modeRef.current!==cameraMode){
        remote?.peer.close();current.getTracks().forEach(t=>t.stop());return;
      }
      peer.current=remote?.peer||null;
      stream.current=current;
      if(video.current){
        video.current.srcObject=current;
        void video.current.play().catch(()=>{});
      }
      setCameraActive(true);
      setStatus(tx('Cámara conectada. Vista previa local.','Camera connected. Local preview.'));
      current.getVideoTracks().forEach(track=>track.addEventListener('ended',()=>{
        if(stream.current===current)stop();
      },{once:true}));
    }catch(err){
      setStatus(err instanceof Error?err.message:String(err));
    }
  }

  React.useEffect(()=>{
    if(!cameraActive||!permission||readiness!=='ready')return;
    let alive=true;
    const controller=new AbortController();
    const frame=document.createElement('canvas');
    frame.width=640;frame.height=360;
    async function inspect(){
      if(!alive||inFlight.current||!video.current||video.current.readyState<2)return;
      inFlight.current=true;
      try{
        const ctx=frame.getContext('2d');
        if(!ctx)throw Error('Canvas unavailable');
        ctx.drawImage(video.current,0,0,640,360);
        const blob=await new Promise<Blob|null>(done=>frame.toBlob(done,'image/jpeg',.7));
        if(!blob||!alive)return;
        const resp=await fetch('/api/fire/frame',{method:'POST',body:blob,
          headers:{'Content-Type':'image/jpeg'},signal:controller.signal});
        const data=await resp.json();
        if(!resp.ok)throw Error(typeof data?.detail==='string'?data.detail:'HTTP '+resp.status);
        if(!alive)return;
        if(typeof data.confidence!=='number')throw Error('Respuesta del modelo no válida');
        setScore(data.confidence);
        setStatus(tx('PyroEngine · lectura orientativa, sin alertas externas.',
          'PyroEngine · indicative reading, no external alerts.'));
        if(data.possible_fire&&Date.now()-lastCandidate.current>60000){
          lastCandidate.current=Date.now();
          fireCallback.current({
            id:'FIRE-IA-'+Date.now().toString(36).toUpperCase(),
            camera_id:'CAM-FIRE-LOCAL',recorded_at:new Date().toISOString(),
            signal:'fire',source:'pyroengine_browser_camera',
            confidence:data.confidence,simulation:false,verified:false
          });
        }
      }catch(err){
        if(!controller.signal.aborted&&alive){
          setStatus(tx('Se detuvo el análisis: ','Analysis stopped: ')+(err instanceof Error?err.message:String(err)));
          setPermission(false);
        }
      }finally{inFlight.current=false;}
    }
    void inspect();
    const timer=window.setInterval(()=>void inspect(),15000);
    return()=>{alive=false;controller.abort();window.clearInterval(timer);};
  },[cameraActive,permission,readiness,language]);

  function demo(){
    fireCallback.current({
      id:'FIRE-DEMO-'+Date.now().toString(36).toUpperCase(),
      camera_id:'CAM-FIRE-VIRTUAL',recorded_at:new Date().toISOString(),
      signal:'smoke',source:'virtual_fire_simulation',simulation:true,verified:false
    });
    setStatus(tx('Evento ficticio enviado a la bandeja.','Fictional event added to the queue.'));
  }
  return <section className="fire-card fire-camera-live">
    <div className="sci-panel-head">
      <h3>{tx('Cámara de incendios','Fire monitoring camera')}</h3>
      <span className="fire-pill">{tx('EXPERIMENTAL','EXPERIMENTAL')}</span>
    </div>
    <div className="fire-camera-layout">
      <div className="fire-camera-preview">
        <video playsInline muted autoPlay ref={video} aria-label={tx('Vista de cámara de incendios','Fire camera preview')}/>
        {!cameraActive&&<span>{tx('Cámara sin conectar','Camera disconnected')}</span>}
      </div>
      <div className="fire-camera-controls">
        <div className="camera-modes">
          <button type="button" className={cameraMode==='device'?'active':''}
            onClick={()=>{stop();modeRef.current='device';setCameraMode('device');}}>
            {tx('Dispositivo','Device')}</button>
          <button type="button" className={cameraMode==='remote'?'active':''}
            onClick={()=>{stop();modeRef.current='remote';setCameraMode('remote');}}>
            {tx('WebRTC · IP','WebRTC · IP')}</button>
        </div>
        {cameraMode==='remote'&&<label className="sci-field">
          <span>{tx('URL HTTPS · WHEP','HTTPS WHEP URL')}</span>
          <input type="url" value={whepUrl} disabled={cameraActive} autoComplete="off"
            placeholder="https://servidor.example/api/webrtc?src=cam"
            onChange={e=>setWhepUrl(e.target.value)}/></label>}
        <div className="fire-control">
          {!cameraActive?<button type="button" disabled={cameraMode==='remote'&&!whepUrl.trim()} onClick={()=>void start()}>
            {tx('Conectar cámara','Connect camera')}</button>
            :<button type="button" onClick={stop}>{tx('Desconectar','Disconnect')}</button>}
          <button type="button" onClick={demo}>{tx('Simular indicio','Simulate candidate')}</button>
        </div>
        <p className="sci-muted">{readiness==='ready'
          ?tx('PyroEngine configurado · activar análisis para enviar fotogramas.','PyroEngine configured · opt in to send frames.')
          :readiness==='checking'?tx('Comprobando detector…','Checking detector…')
          :tx('PyroEngine sin configurar: cámara local y simulación disponibles.',
            'PyroEngine not configured: local camera and simulation remain available.')}</p>
        <label className="camera-permission">
          <input type="checkbox" checked={permission} disabled={!cameraActive||readiness!=='ready'}
            onChange={e=>setPermission(e.target.checked)}/>
          <span>{tx('Analizar automáticamente con PyroEngine (fotogramas cada 15 s). Solo video autorizado.',
            'Analyze automatically with PyroEngine (frames every 15 s). Authorized video only.')}</span>
        </label>
        {score!==null&&<p className="sci-muted">{tx('Indicio del modelo','Model signal')}: {Math.round(score*100)}% · {tx('No verificado','Unverified')}</p>}
        {status&&<p className="sci-muted" role="status">{status}</p>}
      </div>
    </div>
  </section>;
}
