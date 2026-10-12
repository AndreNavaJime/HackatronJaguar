import React from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import DetectionPanel from './DetectionPanel';
import VideoPanel from './VideoPanel';
import LiteVideoPanel from './LiteVideoPanel';
import ScientificWorkspace from './ScientificWorkspace';
import InstallControl from './InstallControl';
import { registerPantheraPwa } from './registerPwa';
import { LanguageProvider, useLanguage } from './language';

const sections = ['Resumen', 'PantheraID', 'PantheraMONITORING', 'PantheraEDGE', 'Investigación'];
const sectionSymbols: Record<string, string> = {
  Resumen: '◈', PantheraID: '◎', PantheraMONITORING: '▦', PantheraEDGE: '⌁', Investigación: '✦',
};
type ApiState = 'checking' | 'connected' | 'disconnected';
type ImageResult = {
  status: string;
  format: string;
  width: number;
  height: number;
  color_mode: string;
  size_bytes: number;
  sha256: string;
  saved: boolean;
  animal_detection: boolean;
  note: string;
};

function App() {
  const { language, setLanguage, t } = useLanguage();
  const [section, setSection] = React.useState('Resumen');
  const [apiState, setApiState] = React.useState<ApiState>('checking');
  const [aiAvailable, setAiAvailable] = React.useState(false);
  const [liteAvailable, setLiteAvailable] = React.useState(false);
  const [apiMessage, setApiMessage] = React.useState('Verificando disponibilidad del servicio…');
  const [selectedImage, setSelectedImage] = React.useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = React.useState<string | null>(null);
  const [imageResult, setImageResult] = React.useState<ImageResult | null>(null);
  const [imageError, setImageError] = React.useState('');
  const [uploading, setUploading] = React.useState(false);

  const checkApi = React.useCallback(async () => {
    setApiState('checking');
    setApiMessage('Verificando disponibilidad del servicio…');
    try {
      const response = await fetch('/api/health', { cache: 'no-store' });
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const data: unknown = await response.json();
      if (typeof data !== 'object' || data === null || !('status' in data) || data.status !== 'ok') {
        throw new Error('Respuesta inesperada del servidor');
      }
      setApiState('connected');
      setApiMessage('Servicio de análisis operativo');
      try {
        const caps=await fetch('/api/capabilities',{cache:'no-store'});
        const data:unknown=await caps.json();
        setAiAvailable(caps.ok && typeof data==='object' && data!==null
          && 'animal_detection' in data && data.animal_detection==='optional_dependencies_installed');
        setLiteAvailable(caps.ok && typeof data==='object' && data!==null
          && 'video_lightweight' in data && data.video_lightweight==='available');
      } catch { setAiAvailable(false); setLiteAvailable(false); }
    } catch {
      setLiteAvailable(false);
      setAiAvailable(false);
      setApiState('disconnected');
      setApiMessage('No se pudo establecer conexión con el servicio. Volvé a intentar en unos minutos.');
    }
  }, []);

  React.useEffect(() => { void checkApi(); }, [checkApi]);
  React.useEffect(() => {
    if (!selectedImage) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(selectedImage);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [selectedImage]);

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    setSelectedImage(file);
    setImageResult(null);
    setImageError('');
  }

  async function inspectImage() {
    if (!selectedImage) return;
    if (selectedImage.size > 12 * 1024 * 1024) {
      setImageError(t('El tamaño máximo permitido es de 12 MB.'));
      return;
    }
    setUploading(true);
    setImageError('');
    setImageResult(null);
    try {
      const response = await fetch('/api/images/inspect', {
        method: 'POST',
        headers: { 'Content-Type': selectedImage.type || 'application/octet-stream' },
        body: selectedImage,
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(typeof payload.detail === 'string' ? payload.detail : t('Error al leer la imagen.'));
      }
      setImageResult(payload as ImageResult);
    } catch (err) {
      setImageError(err instanceof Error ? err.message : t('No se pudo enviar la imagen.'));
    } finally {
      setUploading(false);
    }
  }

  return <div className="shell">
    <aside>
      <div className="brand">
        <img className="brand-symbol" src="/icons/jaguar-modern-512.png" alt="" />
        <span className="brand-copy"><strong>PANTHERA<span>LAB</span></strong><small>WILDLIFE INTELLIGENCE</small></span>
      </div>
      <p className="sub">{t('Conservación inteligente')}</p>
      <p className="sidebar-label">{t('CENTRO DE CONTROL')}</p>
      <nav aria-label="Navegación principal">
        {sections.map(s => <button type="button" key={s} className={section===s?'active':''} aria-current={section===s?'page':undefined}
          onClick={() => setSection(s)}>
          <span className="nav-symbol" aria-hidden="true">{sectionSymbols[s]}</span><span className="nav-text">{t(s)}</span>
          <span className="nav-arrow" aria-hidden="true">↗</span>
        </button>)}
      </nav>
      <div className={'sidebar-connection '+apiState}>
        <span className="sidebar-connection-dot" aria-hidden="true" />
        <div><strong>Panthera API</strong><small>{t(apiState==='connected'?'En línea':apiState==='checking'?'Verificando…':'Sin conexión')}</small></div>
      </div>
      <small className="sidebar-footer">PANTHERALAB / V2.0<br />{language==='en'?'SCIENTIFIC MONITORING':'MONITOREO CIENTÍFICO'}</small>
    </aside>
    <main>
      <header className="app-header">
        <span className="header-location"><span className="header-location-mark" aria-hidden="true">◉</span> PANTHERALAB <span className="header-divider">/</span> {t(section).toUpperCase()}</span>
        <div className="app-header-actions"><span className="top-status">● {t('SISTEMA CIENTÍFICO')}</span>
          <div className="language-switch" role="group" aria-label="Idioma / Language">
            <button type="button" onClick={() => setLanguage('es')} aria-pressed={language==='es'} className={language==='es'?'selected':''}>ES</button>
            <button type="button" onClick={() => setLanguage('en')} aria-pressed={language==='en'} className={language==='en'?'selected':''}>EN</button>
          </div>
          <InstallControl /></div>
      </header>
      <section className="hero-stage" aria-label="Introducción a PantheraID">
        <div className="hero-copy">
          <p className="hero-eyebrow"><span className="hero-eyebrow-line" /> {t('OBSERVAR · ANALIZAR · CONSERVAR')}</p>
          <h1>{t(section==='Resumen'?'Inteligencia para la vida silvestre':section)}</h1>
          <p className="lead">{t('Tecnología aplicada a cámaras trampa, evidencia científica y monitoreo de fauna.')}</p>
          <div className="hero-chips"><span>◆ PANTHERAID 2.0</span><span>◈ {t('INVESTIGACIÓN')}</span><span>◉ COSTA RICA</span></div>
        </div>
        <div className="hero-orbit" aria-hidden="true">
          <div className="hero-orbit-outer" />
          <div className="hero-orbit-inner"><img src="/icons/jaguar-modern-512.png" alt="" /></div>
          <span className="orbit-code orbit-code-top">FIELD DATA · 01</span>
          <span className="orbit-code orbit-code-bottom">WILDLIFE / INTELLIGENCE</span>
        </div>
      </section>
      <section className={'api-status ' + apiState} aria-live="polite" aria-label="Estado de la API">
        <div><span className="status-dot" aria-hidden="true"></span><strong>{t("Estado del servicio")}</strong><p>{t(apiMessage)}</p></div>
        <button type="button" onClick={() => void checkApi()} disabled={apiState === 'checking'}>{t("Actualizar estado")}</button>
      </section>
      {section === 'PantheraID' ? <section className="panel upload-panel">
        <div className="panel-heading">
          <div><h2>{t("PantheraID · Multimedia de cámaras trampa")}</h2><p>{t("Organización de evidencia multimedia y análisis exploratorio de cámaras trampa.")}</p></div>
          <span className="tag">{t("IMAGEN + VIDEO")}</span>
        </div>
        <div className="upload-layout">
          <div className="upload-controls">
            <label htmlFor="panthera-image">{t("Seleccionar fotografía (JPEG, PNG o WebP; máximo 12 MB)")}</label>
            <input id="panthera-image" type="file" accept="image/jpeg,image/png,image/webp" onChange={handleFileChange} />
            <button className="action-button" disabled={!selectedImage || uploading || apiState !== 'connected'} onClick={() => void inspectImage()}>
              {t(uploading ? 'Enviando…' : 'Inspeccionar fotografía')}
            </button>
            {imageError && <p role="alert" className="upload-error">{imageError}</p>}
            {imageResult && <div className="image-result" role="status">
              <strong>✓ {t('Fotografía verificada')}</strong>
              <dl><dt>{t("Formato")}</dt><dd>{imageResult.format}</dd><dt>{t("Dimensiones")}</dt><dd>{imageResult.width} × {imageResult.height} px</dd><dt>{t("Tamaño")}</dt><dd>{(imageResult.size_bytes / 1024 / 1024).toFixed(2)} MB</dd><dt>{t("Almacenada")}</dt><dd>{t("No")}</dd></dl>
              <p>{language==='en'?'File validation completed. Species identification was not performed.':'Validación del archivo completada. No se ha realizado identificación de especies.'}</p>
            </div>}
          </div>
          <div className="image-frame">
            {previewUrl ? <img src={previewUrl} alt={t('Vista previa de la fotografía seleccionada')} /> : <div className="empty-preview">{t("Aquí aparecerá la fotografía seleccionada")}</div>}
            {selectedImage && <small>{selectedImage.name}</small>}
          </div>
        </div>
        <LiteVideoPanel enabled={apiState === 'connected' && liteAvailable} />
        <details className="method-details ai-method-details">
          <summary>{language==='en'?'Automatic detection · MegaDetector V6':'Detección automática · MegaDetector V6'}
            <span className="method-status">{aiAvailable
              ? (language==='en'?'Available for testing':'Disponible para pruebas')
              : (language==='en'?'Not enabled':'No habilitado')}</span>
          </summary>
          <p>{aiAvailable
            ? (language==='en'?'The model dependencies are present. Its inference capacity must still be validated in this environment.':'Las dependencias del modelo están presentes. Su capacidad de inferencia aún requiere verificación en este entorno.')
            : (language==='en'?'Automated detection requires additional model dependencies and processing resources. The sequence analysis above remains available using OpenCV.':'La detección automática requiere dependencias y capacidad de procesamiento adicionales. El análisis de secuencias anterior está disponible con OpenCV.')}</p>
        </details>
        {aiAvailable && <VideoPanel enabled={apiState === 'connected'} />}
        {aiAvailable && <DetectionPanel file={selectedImage} enabled={apiState === 'connected' && !uploading} />}
        <details className="method-details method-details-compact">
          <summary>{language==='en'?'Evidence management and data retention':'Gestión de evidencia y conservación de datos'}</summary>
          <p>{language==='en'?'Image inspection does not perform species recognition or save images to Supabase. Video analysis uses temporary files that expire on the processing server. Biological identification requires independent scientific review.':'La inspección de fotografías no reconoce especies ni guarda imágenes en Supabase. El análisis de video utiliza archivos temporales que caducan en el servidor de procesamiento. La identificación biológica exige revisión científica independiente.'}</p>
        </details>
      </section> : <ScientificWorkspace section={section} onNavigate={setSection} />}
    </main>
  </div>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><LanguageProvider><App /></LanguageProvider></React.StrictMode>);
registerPantheraPwa();
