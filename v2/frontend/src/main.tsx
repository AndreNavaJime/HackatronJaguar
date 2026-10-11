import React from 'react';
import MobileNavigation from './MobileNavigation';
import { Button } from './components/ui/button';
import { createRoot } from 'react-dom/client';
import './style.css';
import DetectionPanel from './DetectionPanel';
import VideoPanel from './VideoPanel';
import InstallControl from './InstallControl';
import ScientificWorkspace, { emptyObservation, type EdgeSummary, type ScientificObservation } from './ScientificWorkspace';
import EdgeOperations from './EdgeOperations';
import MonitoringPanel from './MonitoringPanel';
import { registerPantheraPwa } from './registerPwa';

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
  const [aiDependencyState, setAiDependencyState] = React.useState<'checking' | 'available' | 'missing'>('checking');
  const [selectedImage, setSelectedImage] = React.useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = React.useState<string | null>(null);
  const [imageResult, setImageResult] = React.useState<ImageResult | null>(null);
  const [imageError, setImageError] = React.useState('');
  const [uploading, setUploading] = React.useState(false);
  const [scientificDraft, setScientificDraft] = React.useState<ScientificObservation>(emptyObservation);
  const [scientificRecords, setScientificRecords] = React.useState<ScientificObservation[]>([]);
  const [latestEdge, setLatestEdge] = React.useState<EdgeSummary | null>(null);

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
      setApiMessage('Python conectado · PantheraLAB API responde correctamente');
      try {
        const capResponse = await fetch('/api/capabilities', { cache: 'no-store' });
        if (capResponse.ok) {
          const capabilities = await capResponse.json() as { animal_detection?: string };
          setAiDependencyState(capabilities.animal_detection === 'requires_pytorchwildlife' ? 'missing' : 'available');
        }
      } catch { setAiDependencyState('checking'); }
    } catch {
      setApiState('disconnected');
      setAiDependencyState('checking');
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
      <header className="app-header">
        <div className="mobile-brand" aria-label="PantheraLAB, conservación inteligente">
          <span className="mobile-brand-icon" aria-hidden="true">🐆</span>
          <span className="mobile-brand-name">PANTHERA<strong>LAB</strong><small>Conservación inteligente</small></span>
        </div>
        <span className="desktop-header-label">Plataforma científica de monitoreo</span>
        <div className="app-header-actions"><InstallControl /><span className="tag">PROTOTIPO UI</span></div>
      </header>
      <h1>{section}</h1>
      <p className="lead">Sistema de apoyo para monitoreo de fauna y revisión científica de evidencia.</p>
      <section className={'api-status ' + apiState} aria-live="polite" aria-label="Estado de la API">
        <div><span className="status-dot" aria-hidden="true"></span><strong>Conexión con backend</strong><p>{apiMessage}</p></div>
        <button type="button" onClick={() => void checkApi()} disabled={apiState === 'checking'}>Comprobar conexión</button>
      </section>
      <div hidden={section !== 'PantheraID' && section !== 'PantheraEDGE'}>
      <section className="panel upload-panel">
        <div className="panel-heading">
          <div><h2>{section === 'PantheraEDGE' ? 'PantheraEDGE · Multimedia científica' : 'PantheraID · Multimedia de cámaras trampa'}</h2>
          <p>Fotografías y videos, detecciones de animales, recortes candidatos, tablas por frame, gráficos y descargas para revisión científica.</p></div>
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
        <DetectionPanel file={selectedImage} enabled={apiState === 'connected' && !uploading}
          onAnalysisComplete={setLatestEdge} />
        <VideoPanel enabled={apiState === 'connected'} onAnalysisComplete={setLatestEdge} />
        <p className="scientific-note">La recepción por sí sola no ejecuta MegaDetector. Las fotografías no se guardan en Supabase. Los análisis de video utilizan archivos temporales en Codespaces y se eliminan después de su vencimiento; la identificación de especie o individuo requiere revisión científica.</p>
      </section>
      </div>
      {section === 'PantheraEDGE' && <>
        <EdgeOperations latestEdge={latestEdge} draft={scientificDraft} setDraft={setScientificDraft}
          enabled={apiState === 'connected'} />
        <ScientificWorkspace view="PantheraEDGE" enabled={apiState === 'connected'}
          draft={scientificDraft} setDraft={setScientificDraft}
          records={scientificRecords} setRecords={setScientificRecords} latestEdge={latestEdge} />
      </>}
      {section === 'Investigación' && <ScientificWorkspace view="Investigación" enabled={apiState === 'connected'}
        draft={scientificDraft} setDraft={setScientificDraft}
        records={scientificRecords} setRecords={setScientificRecords} latestEdge={latestEdge} />}
      {section === 'PantheraMONITORING' && <MonitoringPanel records={scientificRecords}
        latestEdge={latestEdge} onOpenEdge={() => setSection('PantheraEDGE')}
        onOpenResearch={() => setSection('Investigación')} />}
      {apiState === 'connected' && aiDependencyState === 'missing' &&
        (section === 'PantheraID' || section === 'PantheraEDGE') && <p className="science-hint" role="status">
          La API científica funciona, pero MegaDetector todavía necesita PyTorchWildlife y sus pesos en el entorno de FastAPI.
          Los formularios y exportaciones no dependen de ese modelo.
        </p>}
      {section === 'Resumen' && <>
        <div className="cards">
          <article><span>PantheraID · Imágenes y videos</span><strong>MegaDetector V6</strong><p>Detección de animales, personas y vehículos con API Python. La identificación individual continúa pendiente.</p>
            <Button type="button" onClick={() => setSection('PantheraID')}>Abrir análisis multimedia</Button></article>
          <article><span>PantheraEDGE · Ciencia</span ><strong>Módulos científicos</strong><p>Captura científica, IA, gráficos, ubicación, eventos, Sentinel, simulación 5G y reportes.</p>
            <Button type="button" onClick={() => setSection('PantheraEDGE')}>Abrir PantheraEDGE</Button></article>
          <article><span>PantheraMONITORING</span><strong>{scientificRecords.length} registros locales</strong><p>Dashboard de observaciones de esta sesión. Sin conexión automática a Supabase.</p>
            <Button type="button" onClick={() => setSection('PantheraMONITORING')}>Abrir monitoreo</Button></article>
        </div>
        <section className="panel"><h2>PantheraLAB · Flujo de investigación</h2><p>Ingresá una cámara o video, procesá los fotogramas con MegaDetector, documentá su procedencia científica en PantheraEDGE y exportá el registro desde Investigación. Una PWA instalada sigue necesitando conexión con el servidor Python para inferencia, informes PDF y Sentinel.</p>
        <p className="scientific-note">Estado del prototipo: la detección exige bibliotecas y pesos de IA instalados en FastAPI; el nodo VIGÍA y la persistencia real en Supabase requieren configuración e integración adicionales.</p></section>
      </>}
    </main>
    <MobileNavigation currentSection={section} onSelect={setSection} />
  </div>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
registerPantheraPwa();
