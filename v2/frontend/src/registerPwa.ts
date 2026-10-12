/** PWA registration, including Codespaces HTTPS development preview.
 * API calls, videos and model results are never cached by the service worker.
 */
export function registerPantheraPwa(): void {
  if (!('serviceWorker' in navigator) || !window.isSecureContext) return;
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(error => {
      console.warn('PantheraID: no se pudo registrar el modo PWA:', error);
    });
  });
}
