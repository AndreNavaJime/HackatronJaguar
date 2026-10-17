/* PantheraLIVE notification-only worker.
 * This narrow-scope worker does not intercept fetches or cache project data.
 * Browser permission is mandatory; no background camera capture is attempted.
 */
self.addEventListener('notificationclick',event=>{
  event.notification.close();
  event.waitUntil((async()=>{
    const windows=await clients.matchAll({type:'window',includeUncontrolled:true});
    const existing=windows.find(item=>new URL(item.url).origin===self.location.origin);
    if(existing){await existing.focus();return;}
    await clients.openWindow('/');
  })());
});
