/** Best-effort installed-PWA badge + visible browser-tab fallback.
 * This reflects unresolved clips stored ON THIS DEVICE. It is not remote push.
 * Different Android launchers may choose a dot, count, or no icon badge.
 */
import {countPendingAnimalClips,LIVE_CLIPS_CHANGED} from './animalClipStore';
import {clearClipReadyNotification} from './clipNotifications';

type BadgeNavigator=Navigator&{
  setAppBadge?:(count?:number)=>Promise<void>;
  clearAppBadge?:()=>Promise<void>;
};
const ORIGINAL_TITLE='PantheraLAB · Plataforma científica';
const DEFAULT_FAVICON='/icons/jaguar-modern-192.png';
let lastFaviconUrl:string|null=null;
let iconPromise:Promise<HTMLImageElement>|null=null;
function icon():Promise<HTMLImageElement>{
  if(!iconPromise)iconPromise=new Promise((resolve,reject)=>{
    const image=new Image();
    image.onload=()=>resolve(image);
    image.onerror=()=>reject(new Error('No app icon'));
    image.src=DEFAULT_FAVICON;
  });
  return iconPromise;
}
async function iconDot(pending:number):Promise<void>{
  const link=document.querySelector<HTMLLinkElement>('link[rel="icon"]');
  if(!link)return;
  if(!pending){
    link.href=DEFAULT_FAVICON;
    lastFaviconUrl=null;
    return;
  }
  const image=await icon();
  const canvas=document.createElement('canvas');
  canvas.width=64;canvas.height=64;
  const ctx=canvas.getContext('2d');
  if(!ctx)return;
  ctx.drawImage(image,0,0,64,64);
  ctx.beginPath();ctx.arc(50,14,12,0,Math.PI*2);
  ctx.fillStyle='#e83945';ctx.fill();
  ctx.lineWidth=3;ctx.strokeStyle='#f9fafb';ctx.stroke();
  const url=canvas.toDataURL('image/png');
  // Keep only the latest calculation when a clip was reviewed in the meantime.
  if(lastFaviconUrl===null&&Number(document.title.match(/^\((\d+)\)/)?.[1]||0)===0)return;
  lastFaviconUrl=url;
  link.href=url;
}

export async function applyPendingLiveBadge(count:number):Promise<void>{
  const pending=Math.max(0,Math.floor(count));
  document.title=pending?('('+pending+') '+ORIGINAL_TITLE):ORIGINAL_TITLE;
  const nav=navigator as BadgeNavigator;
  try{
    if(pending>0)await nav.setAppBadge?.(pending);
    else await nav.clearAppBadge?.();
  }catch{
    // Unsupported, denied or launcher-controlled badging: title/nav fallback.
  }
  if(pending===0){
    const link=document.querySelector<HTMLLinkElement>('link[rel="icon"]');
    if(link)link.href=DEFAULT_FAVICON;
    lastFaviconUrl=null;
    void clearClipReadyNotification();
  }else{
    await iconDot(pending).catch(()=>{});
  }
}

/** Keep global pending count current without reading clip video bytes into App. */
export function watchPendingLiveClips(onCount:(pending:number)=>void):()=>void{
  let alive=true;
  let version=0;
  async function refresh(){
    const seq=++version;
    try{
      const pending=await countPendingAnimalClips();
      if(alive&&seq===version)onCount(pending);
    }catch{
      // IndexedDB might be blocked or unavailable; never invent a count.
    }
  }
  const checkVisibility=()=>{if(!document.hidden)void refresh();};
  const check=()=>void refresh();
  window.addEventListener(LIVE_CLIPS_CHANGED,check);
  window.addEventListener('pageshow',check);
  document.addEventListener('visibilitychange',checkVisibility);
  void refresh();
  return ()=>{
    alive=false;
    window.removeEventListener(LIVE_CLIPS_CHANGED,check);
    window.removeEventListener('pageshow',check);
    document.removeEventListener('visibilitychange',checkVisibility);
  };
}
