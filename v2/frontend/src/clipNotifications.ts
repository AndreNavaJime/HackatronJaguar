/** Opt-in device notifications. The browser must grant permission once;
 * in-app clip alerts always work regardless of browser notification support.
 * No remote push notifications are installed or implied here.
 */
const WORKER_URL='/pantheralive-alert-sw.js';
const WORKER_SCOPE='/pantheralive-alerts/';

export async function requestClipAlertsOnCameraConnect():Promise<void>{
  if(!window.isSecureContext||typeof Notification==='undefined')return;
  if(Notification.permission!=='default')return;
  try{
    // Called synchronously from the user pressing Connect camera, not an effect.
    const permission=await Notification.requestPermission();
    if(permission==='granted'&&'serviceWorker' in navigator){
      await navigator.serviceWorker.register(WORKER_URL,{scope:WORKER_SCOPE});
    }
  }catch{
    // Device notification permissions should never block the camera.
  }
}

export async function notifyClipReady():Promise<void>{
  if(typeof Notification==='undefined'||Notification.permission!=='granted')return;
  const title='PantheraLIVE';
  const options={
    body:'Posible animal detectado. Video pendiente de revisión.',
    tag:'pantheralive-clip-ready',
    icon:'/favicon.ico'
  };
  try{
    if('serviceWorker' in navigator){
      const worker=await navigator.serviceWorker.register(WORKER_URL,{scope:WORKER_SCOPE});
      if(worker.active){
        await worker.showNotification(title,options);
        return;
      }
    }
    // Desktop fallback; some mobile browsers only support SW notifications.
    new Notification(title,options);
  }catch{
    // The automatic banner inside PantheraLIVE is the reliable fallback.
  }
}
