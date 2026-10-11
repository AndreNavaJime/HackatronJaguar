import React from 'react';

interface BrowserInstallPrompt extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform: string }>;
}

function alreadyInstalled(): boolean {
  return window.matchMedia('(display-mode: standalone)').matches
    || Boolean((navigator as Navigator & { standalone?: boolean }).standalone);
}

/** A real browser-install prompt on supported browsers; otherwise guided steps. */
export default function InstallControl() {
  const [prompt, setPrompt] = React.useState<BrowserInstallPrompt | null>(null);
  const [installed, setInstalled] = React.useState(false);
  const [instructions, setInstructions] = React.useState(false);
  const [ios, setIos] = React.useState(false);

  React.useEffect(() => {
    const media = window.matchMedia('(display-mode: standalone)');
    const refresh = () => setInstalled(alreadyInstalled());
    const onPrompt = (event: Event) => {
      event.preventDefault();
      setPrompt(event as BrowserInstallPrompt);
    };
    const onInstalled = () => {
      setInstalled(true);
      setPrompt(null);
      setInstructions(false);
    };
    refresh();
    setIos(/iPad|iPhone|iPod/i.test(navigator.userAgent) ||
      (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1));
    window.addEventListener('beforeinstallprompt', onPrompt);
    window.addEventListener('appinstalled', onInstalled);
    media.addEventListener?.('change', refresh);
    return () => {
      window.removeEventListener('beforeinstallprompt', onPrompt);
      window.removeEventListener('appinstalled', onInstalled);
      media.removeEventListener?.('change', refresh);
    };
  }, []);

  async function install() {
    if (prompt) {
      try {
        await prompt.prompt();
        const choice = await prompt.userChoice;
        setPrompt(null);
        if (choice.outcome === 'dismissed') setInstructions(true);
      } catch {
        setInstructions(true);
      }
    } else {
      setInstructions(value => !value);
    }
  }

  if (installed) return <span className="installed-indicator" role="status">✓ App instalada</span>;

  return <div className="pwa-install">
    <button type="button" className="install-button" onClick={() => void install()}
      aria-expanded={instructions} aria-controls="install-help">
      <span aria-hidden="true">↧</span> Instalar app
    </button>
    {instructions && <div className="install-help" id="install-help" role="region"
      aria-label="Instrucciones para instalar PantheraID">
      <strong>Agregar PantheraID al celular</strong>
      {ios ? <p>En <b>Safari</b>, tocá <b>Compartir</b> y seleccioná <b>Agregar a pantalla de inicio</b>.</p>
        : <p>En <b>Chrome para Android</b>, abrí el menú <b>⋮</b> y elegí
          <b> Instalar aplicación</b> o <b>Agregar a pantalla de inicio</b>.</p>}
      <p>Necesitás abrir PantheraID mediante HTTPS. Los análisis con MegaDetector requieren
        conexión al servidor Python, aunque la aplicación esté instalada.</p>
      <button type="button" onClick={() => setInstructions(false)}
        className="install-dismiss">Cerrar</button>
    </div>}
  </div>;
}
