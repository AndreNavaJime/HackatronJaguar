import {apiFetch} from './apiClient';
/** Receive a video stream from a WHEP-compatible WebRTC gateway (e.g. go2rtc).
 * Browser-side signaling only. No RTSP, credentials or uploads are proxied.
 */
export async function connectWhep(endpoint:string):Promise<{
  peer:RTCPeerConnection;stream:MediaStream;
}>{
  if(!('RTCPeerConnection' in window))throw new Error('WebRTC no está disponible en este navegador.');
  let url:URL;
  try{url=new URL(endpoint);}catch{throw new Error('Ingresá una URL WHEP válida.');}
  if(url.protocol!=='https:'&&!(url.protocol==='http:'&&['localhost','127.0.0.1'].includes(url.hostname)))
    throw new Error('La cámara remota necesita un endpoint WHEP HTTPS.');
  if(url.username||url.password)throw new Error('No incluyás claves en la dirección de la cámara.');
  const peer=new RTCPeerConnection();
  try{
    const stream=new MediaStream();
    const trackReceived=new Promise<void>((resolve,reject)=>{
      const timeout=window.setTimeout(()=>reject(new Error('No llegó video del gateway WebRTC.')),16000);
      peer.ontrack=e=>{
        for(const track of e.streams[0]?.getVideoTracks()||[e.track]){
          if(track.kind==='video'&&!stream.getTracks().some(t=>t.id===track.id))stream.addTrack(track);
        }
        if(stream.getVideoTracks().length){window.clearTimeout(timeout);resolve();}
      };
    });
    peer.addTransceiver('video',{direction:'recvonly'});
    const offer=await peer.createOffer();
    await peer.setLocalDescription(offer);
    if(peer.iceGatheringState!=='complete'){
      await new Promise<void>(done=>{
        const timer=window.setTimeout(()=>{peer.removeEventListener('icegatheringstatechange',check);done();},7000);
        const check=()=>{
          if(peer.iceGatheringState==='complete'){
            window.clearTimeout(timer);
            peer.removeEventListener('icegatheringstatechange',check);
            done();
          }
        };
        peer.addEventListener('icegatheringstatechange',check);
      });
    }
    const response=await apiFetch(url.toString(),{
      method:'POST',mode:'cors',credentials:'omit',
      headers:{'Content-Type':'application/sdp','Accept':'application/sdp'},
      body:peer.localDescription?.sdp||offer.sdp
    });
    if(!response.ok)throw new Error('Gateway WebRTC: HTTP '+response.status);
    const answer=await response.text();
    if(!answer.startsWith('v=0'))throw new Error('El gateway no respondió con SDP.');
    await peer.setRemoteDescription({type:'answer',sdp:answer});
    await trackReceived;
    return {peer,stream};
  }catch(error){
    peer.close();
    throw error;
  }
}
