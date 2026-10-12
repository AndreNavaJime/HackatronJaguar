import React from 'react';
import { useLanguage } from './language';

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
  const { t } = useLanguage();
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

  if (installed) return <span className="installed-indicator" role="status">✓ {t('App instalada')}</span>;

  return <div className="pwa-install">
    <button type="button" className="install-button" onClick={() => void install()}
      aria-expanded={instructions} aria-controls="install-help">
      <span aria-hidden="true">↧</span> {t('Instalar app')}
    </button>
    {instructions && <div className="install-help" id="install-help" role="region"
      aria-label="Instrucciones para instalar PantheraID">
      <strong>{t('Agregar PantheraID al celular')}</strong>
      {ios
        ? <p>{t('Para iPhone, abrí Safari, tocá Compartir y seleccioná Agregar a pantalla de inicio.')}</p>
        : <p>{t('En Chrome para Android, abrí el menú ⋮ y elegí Instalar aplicación o Agregar a pantalla de inicio.')}</p>}
      <p>{t('El análisis de videos y las consultas satelitales requieren conexión a Internet, incluso con la aplicación instalada.')}</p>
      <button type="button" onClick={() => setInstructions(false)}
        className="install-dismiss">{t('Cerrar')}</button>
    </div>}
  </div>;
}
