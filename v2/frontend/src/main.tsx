import React from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import DetectionPanel from './DetectionPanel';
import VideoPanel from './VideoPanel';
import InstallControl from './InstallControl';
import { registerPantheraPwa } from './registerPwa';

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
  const [section, setSection] = React.useState('Resumen');
  const [apiState, setApiState] = React.useState<ApiState>('checking');
  const [apiMessage, setApiMessage] = React.useState('Comprobando conexión con Python…');
  const [selectedImage, setSelectedImage] = React.useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = React.useState<string | null>(null);
  const [imageResult, setImageResult] = React.useState<ImageResult | null>(null);
  const [imageError, setImageError] = React.useState('');
  const [uploading, setUploading] = React.useState(false);

  const checkApi = React.useCallback(async () => {
    setApiState('checking');
    setApiMessage('Comprobando conexión con Python…');
    try {
      const response = await fetch('/api/health', { cache: 'no-store' });
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const data: unknown = await response.json();
      if (typeof data !== 'object' || data === null || !('status' in data) || data.status !== 'ok') {
        throw new Error('Respuesta inesperada del servidor');
      }
      setApiState('connected');
      setApiMessage('Python conectado · PantheraID API responde correctamente');
    } catch {
      setApiState('disconnected');
      setApiMessage('No se pudo conectar con Python. Verificá que FastAPI siga ejecutándose en el puerto 8000.');
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
      setImageError('El tamaño máximo permitido es de 12 MB.');
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
        throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Error al leer la imagen.');
      }
      setImageResult(payload as ImageResult);
    } catch (err) {
      setImageError(err instanceof Error ? err.message : 'No se pudo enviar la imagen.');
    } finally {
      setUploading(false);
    }
  }

  return <div className="shell">
    <aside>
      <div className="brand">
        <img className="brand-symbol" src="/icons/pantheraid.svg" alt="" />
        <span className="brand-copy"><strong>PANTHERA<span>LAB</span></strong><small>WILDLIFE INTELLIGENCE</small></span>
      </div>
      <p className="sub">Conservación inteligente</p>
      <p className="sidebar-label">CENTRO DE CONTROL</p>
      <nav aria-label="Navegación principal">
        {sections.map(s => <button type="button" key={s} className={section===s?'active':''} aria-current={section===s?'page':undefined}
          onClick={() => setSection(s)}>
          <span className="nav-symbol" aria-hidden="true">{sectionSymbols[s]}</span><span className="nav-text">{s}</span>
          <span className="nav-arrow" aria-hidden="true">↗</span>
        </button>)}
      </nav>
      <div className={'sidebar-connection '+apiState}>
        <span className="sidebar-connection-dot" aria-hidden="true" />
        <div><strong>Panthera API</strong><small>{apiState==='connected'?'En línea':apiState==='checking'?'Verificando…':'Sin conexión'}</small></div>
      </div>
      <small className="sidebar-footer">PANTHERAID / V2.0<br />PLATAFORMA EN DESARROLLO</small>
    </aside>
    <main>
      <header className="app-header">
        <span className="header-location"><span className="header-location-mark" aria-hidden="true">◉</span> PANTHERALAB <span className="header-divider">/</span> {section.toUpperCase()}</span>
        <div className="app-header-actions"><span className="top-status">● SISTEMA CIENTÍFICO</span><InstallControl /></div>
      </header>
      <section className="hero-stage" aria-label="Introducción a PantheraID">
        <div className="hero-copy">
          <p className="hero-eyebrow"><span className="hero-eyebrow-line" /> OBSERVAR · ANALIZAR · CONSERVAR</p>
          <h1>{section==='Resumen'?'Inteligencia para la vida silvestre':section}</h1>
          <p className="lead">Tecnología aplicada a cámaras trampa, evidencia científica y monitoreo de fauna.</p>
          <div className="hero-chips"><span>◆ PANTHERAID 2.0</span><span>◈ INVESTIGACIÓN</span><span>◉ COSTA RICA</span></div>
        </div>
        <div className="hero-orbit" aria-hidden="true">
          <div className="hero-orbit-outer" />
          <div className="hero-orbit-inner"><img src="/icons/pantheraid.svg" alt="" /></div>
          <span className="orbit-code orbit-code-top">SPECIES · 01</span>
          <span className="orbit-code orbit-code-bottom">WILDLIFE / INTELLIGENCE</span>
        </div>
      </section>
      <section className={'api-status ' + apiState} aria-live="polite" aria-label="Estado de la API">
        <div><span className="status-dot" aria-hidden="true"></span><strong>Conexión con backend</strong><p>{apiMessage}</p></div>
        <button type="button" onClick={() => void checkApi()} disabled={apiState === 'checking'}>Comprobar conexión</button>
      </section>
      {section === 'PantheraID' ? <section className="panel upload-panel">
        <div className="panel-heading">
          <div><h2>PantheraID · Multimedia de cámaras trampa</h2><p>Fotografías, detección animal y análisis de videos con revisión científica.</p></div>
          <span className="tag">IMAGEN + VIDEO</span>
        </div>
        <div className="upload-layout">
          <div className="upload-controls">
            <label htmlFor="panthera-image">Seleccionar fotografía (JPEG, PNG o WebP; máximo 12 MB)</label>
            <input id="panthera-image" type="file" accept="image/jpeg,image/png,image/webp" onChange={handleFileChange} />
            <button className="action-button" disabled={!selectedImage || uploading || apiState !== 'connected'} onClick={() => void inspectImage()}>
              {uploading ? 'Enviando…' : 'Enviar a Python'}
            </button>
            {imageError && <p role="alert" className="upload-error">{imageError}</p>}
            {imageResult && <div className="image-result" role="status">
              <strong>✓ Fotografía recibida por Python</strong>
              <dl><dt>Formato</dt><dd>{imageResult.format}</dd><dt>Dimensiones</dt><dd>{imageResult.width} × {imageResult.height} px</dd><dt>Tamaño</dt><dd>{(imageResult.size_bytes / 1024 / 1024).toFixed(2)} MB</dd><dt>Almacenada</dt><dd>No</dd></dl>
              <p>{imageResult.note}</p>
            </div>}
          </div>
          <div className="image-frame">
            {previewUrl ? <img src={previewUrl} alt="Vista previa de la fotografía seleccionada" /> : <div className="empty-preview">Aquí aparecerá la fotografía seleccionada</div>}
            {selectedImage && <small>{selectedImage.name}</small>}
          </div>
        </div>
        <DetectionPanel file={selectedImage} enabled={apiState === 'connected' && !uploading} />
        <VideoPanel enabled={apiState === 'connected'} />
        <p className="scientific-note">La recepción por sí sola no ejecuta MegaDetector. Las fotografías no se guardan en Supabase. Los análisis de video utilizan archivos temporales en el servidor Python y se eliminan después de su vencimiento; la identificación de especie o individuo requiere revisión científica.</p>
      </section> : <>
        <div className="section-heading"><div><span className="section-kicker">PANEL DE CONTROL</span><h2>Estado de la plataforma</h2></div><span className="section-counter">03 MÓDULOS EN SEGUIMIENTO</span></div>
        <div className="cards">
          <article className="metric-card metric-card-a"><div className="metric-top"><span>01 / IDENTIFICACIÓN</span><b aria-hidden="true">◎</b></div><strong>En migración</strong><p>Modelos de identificación individual pendientes de integración y validación.</p><div className="metric-footer"><i /> PENDIENTE DE VALIDACIÓN</div></article>
          <article className="metric-card metric-card-b"><div className="metric-top"><span>02 / EVENTOS DE CAMPO</span><b aria-hidden="true">⌁</b></div><strong>Sin datos conectados</strong><p>Preparado para integrar PantheraEDGE y el nodo VIGÍA.</p><div className="metric-footer"><i /> INTEGRACIÓN EN DESARROLLO</div></article>
          <article className="metric-card metric-card-c"><div className="metric-top"><span>03 / REVISIÓN CIENTÍFICA</span><b aria-hidden="true">✦</b></div><strong>Pendiente</strong><p>Espacio preparado para evidencias, métricas y exportaciones.</p><div className="metric-footer"><i /> PRÓXIMA ETAPA</div></article>
        </div>
        <section className="panel workspace-panel">
          <div className="workspace-copy"><span className="section-kicker">WORKSPACE / PANTHERAID</span><h2>De la cámara trampa a la evidencia</h2>
          <p>El módulo PantheraID permite recibir fotografías y consultar el servidor Python. La detección con IA y las integraciones de campo dependen de las capacidades habilitadas en el backend.</p>
          <button type="button" className="action-button workspace-button" onClick={() => setSection('PantheraID')}>Explorar módulo PantheraID <span aria-hidden="true">↗</span></button></div>
          <div className="workspace-visual" aria-hidden="true"><span>CAPTURA</span><i>→</i><span>ANÁLISIS</span><i>→</i><span>REVISIÓN</span></div>
        </section>
      </>}
    </main>
  </div>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
registerPantheraPwa();
