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

export async function notifyClipReady(pending=1):Promise<void>{
  if(typeof Notification==='undefined'||Notification.permission!=='granted')return;
  const title='PantheraLIVE';
  const options={
    body:pending===1?'1 video de posible animal pendiente de revisión.':
      pending+' videos de posibles animales pendientes de revisión.',
    tag:'pantheralive-clip-ready',
    icon:'/icons/jaguar-modern-192.png'
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

/** Clear Android's notification dot when no unreviewed local video remains.
 * Does not create a new notification or request permissions.
 */
export async function clearClipReadyNotification():Promise<void>{
  if(!('serviceWorker' in navigator))return;
  try{
    const worker=await navigator.serviceWorker.getRegistration(WORKER_SCOPE);
    const notifications=await worker?.getNotifications({tag:'pantheralive-clip-ready'});
    notifications?.forEach(note=>note.close());
  }catch{/* Closing a notification must never block clip review. */}
}
