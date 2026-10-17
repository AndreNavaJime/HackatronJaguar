/* Notification-only PantheraLIVE worker. It does NOT record background video.
 * Notification clicks focus an existing PantheraLAB tab, or open directly in LIVE.
 */
self.addEventListener('notificationclick',event=>{
  event.notification.close();
  event.waitUntil((async()=>{
    const windows=await clients.matchAll({type:'window',includeUncontrolled:true});
    const existing=windows.find(item=>new URL(item.url).origin===self.location.origin);
    if(existing){
      existing.postMessage({type:'PANTHERALIVE_REVIEW_CLIPS'});
      await existing.focus();
      return;
    }
    await clients.openWindow('/?tab=PantheraLIVE');
  })());
});
