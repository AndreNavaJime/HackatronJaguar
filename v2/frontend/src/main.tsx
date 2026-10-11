import React from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import DetectionPanel from './DetectionPanel';
import VideoPanel from './VideoPanel';

const sections = ['Resumen', 'PantheraID', 'PantheraMONITORING', 'PantheraEDGE', 'Investigación'];
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
      <div className="brand">🐆 PANTHERA<span>LAB</span></div>
      <p className="sub">Conservación inteligente</p>
      <nav aria-label="Navegación principal">
        {sections.map(s => <button key={s} className={section===s?'active':''} onClick={() => setSection(s)}>{s}</button>)}
      </nav>
      <small>PantheraID 2.0 · Vista preliminar</small>
    </aside>
    <main>
      <header><span>Plataforma científica de monitoreo</span><span className="tag">PROTOTIPO UI</span></header>
      <h1>{section}</h1>
      <p className="lead">Sistema de apoyo para monitoreo de fauna y revisión científica de evidencia.</p>
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
        <p className="scientific-note">La recepción por sí sola no ejecuta MegaDetector. Las fotografías no se guardan en Supabase. Los análisis de video utilizan archivos temporales en Codespaces y se eliminan después de su vencimiento; la identificación de especie o individuo requiere revisión científica.</p>
      </section> : <>
        <div className="cards">
          <article><span>Identificación individual</span><strong>En migración</strong><p>Los modelos y la validación se integrarán desde el backend Python.</p></article>
          <article><span>Eventos de campo</span><strong>Sin datos conectados</strong><p>Preparado para integrar PantheraEDGE y el nodo VIGÍA.</p></article>
          <article><span>Revisión científica</span><strong>Pendiente</strong><p>Conservaremos cuadros de imágenes, métricas y exportaciones.</p></article>
        </div>
        <section className="panel"><h2>{section} · Espacio de trabajo</h2><p>Esta pantalla es una primera base responsive. El módulo PantheraID ya permite comprobar la recepción de fotografías, pero la detección, la identificación individual y las integraciones de campo continúan en migración.</p></section>
      </>}
    </main>
  </div>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
