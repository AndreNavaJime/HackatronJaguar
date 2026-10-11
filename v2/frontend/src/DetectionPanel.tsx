import React from 'react';

type Detection = {
  class_name: string;
  confidence: number;
  bbox_xyxy: number[];
};
type DetectionResult = {
  model: string;
  device: string;
  threshold: number;
  inference_seconds: number;
  counts: { animal: number; person: number; vehicle: number };
  detections: Detection[];
  annotated_image: string;
  note: string;
};

const labels: Record<string, string> = { animal: 'Animal', person: 'Persona', vehicle: 'Vehículo' };

export default function DetectionPanel({ file, enabled }: { file: File | null; enabled: boolean }) {
  const [result, setResult] = React.useState<DetectionResult | null>(null);
  const [threshold, setThreshold] = React.useState(0.25);
  const [processing, setProcessing] = React.useState(false);
  const [error, setError] = React.useState('');
  const [annotated, setAnnotated] = React.useState(true);

  React.useEffect(() => {
    setResult(null);
    setError('');
    setAnnotated(true);
  }, [file]);

  async function detect() {
    if (!file || processing || !enabled) return;
    if (file.size > 12 * 1024 * 1024) {
      setError('El tamaño máximo permitido es de 12 MB.');
      return;
    }
    setProcessing(true);
    setResult(null);
    setError('');
    try {
      const response = await fetch('/api/images/detect?threshold=' + threshold.toFixed(2), {
        method: 'POST',
        headers: { 'Content-Type': file.type || 'application/octet-stream' },
        body: file,
      });
      // A proxy may return an empty/HTML response when the Python worker exits.
      // Never assume that every HTTP response contains valid JSON.
      const raw = await response.text();
      let payload: unknown = null;
      if (raw.trim()) {
        try {
          payload = JSON.parse(raw) as unknown;
        } catch {
          const description = response.ok
            ? 'El servidor devolvió contenido no JSON. Reiniciá Vite y FastAPI si acabás de actualizar el código.'
            : 'El servidor devolvió un error sin JSON (HTTP ' + response.status + '). Comprobá la terminal de Python.';
          throw new Error(description);
        }
      }
      if (!response.ok) {
        const detail = typeof payload === 'object' && payload !== null
          && 'detail' in payload && typeof payload.detail === 'string'
          ? payload.detail : null;
        throw new Error(detail ?? ('Python no completó la solicitud (HTTP ' + response.status +
          '). Puede haberse interrumpido por falta de memoria; revisá la terminal de FastAPI.'));
      }
      if (typeof payload !== 'object' || payload === null
        || !('counts' in payload) || !('annotated_image' in payload)
        || typeof payload.annotated_image !== 'string'
        || !payload.annotated_image.startsWith('data:image/')) {
        throw new Error('El servidor respondió sin datos completos. Revisá la terminal de Python y su memoria disponible.');
      }
      setResult(payload as DetectionResult);
      setAnnotated(true);
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : 'No se pudo ejecutar MegaDetector.';
      setError(message === 'Failed to fetch'
        ? 'Se perdió la comunicación con Python. Puede haberse cerrado por falta de memoria. Revisá la terminal de FastAPI.'
        : message);
    } finally {
      setProcessing(false);
    }
  }

  return <section className="detector-panel">
    <h3>Detección de fauna · MegaDetector V6</h3>
    <p>Detecta animales, personas y vehículos. No identifica especies ni jaguares individuales.</p>
    <div className="detector-actions">
      <label htmlFor="confidence-threshold">Umbral de confianza: {Math.round(threshold * 100)}%</label>
      <input id="confidence-threshold" type="range" min="0.1" max="0.9" step="0.05"
        value={threshold} onChange={event => setThreshold(Number(event.target.value))} />
      <button className="action-button detection-button" type="button" disabled={!file || processing || !enabled} onClick={() => void detect()}>
        {processing ? 'Ejecutando MegaDetector…' : 'Detectar animales con IA'}
      </button>
      <small>La primera ejecución puede tardar porque se descargan los pesos del modelo.
        Es necesario instalar PytorchWildlife en Python.</small>
    </div>
    {error && <p className="upload-error" role="alert">{error}</p>}
    {result && <div className="detection-results" aria-live="polite">
      <h3>Resultados científicos preliminares</h3>
      <div className="detection-metrics">
        <div><span>Animales</span><strong>{result.counts.animal}</strong></div>
        <div><span>Personas</span><strong>{result.counts.person}</strong></div>
        <div><span>Vehículos</span><strong>{result.counts.vehicle}</strong></div>
        <div><span>Inferencia</span><strong>{result.inference_seconds.toFixed(2)} s</strong></div>
      </div>
      <p className="details-caption">{result.model} · {result.device.toUpperCase()} · Umbral {Math.round(result.threshold * 100)}%</p>
      <div className="annotated-viewer">
        {annotated
          ? <img src={result.annotated_image} alt="Fotografía con recuadros y confianza de las detecciones" />
          : file && <OriginalPreview file={file} />}
        <div className="preview-controls">
          <button type="button" className={annotated ? 'active' : ''} onClick={() => setAnnotated(true)}>Con recuadros</button>
          <button type="button" className={!annotated ? 'active' : ''} onClick={() => setAnnotated(false)}>Original</button>
          <a className="download-link" href={result.annotated_image} download="pantheraid_detecciones.jpg">Descargar anotada ↓</a>
        </div>
      </div>
      {result.detections.length ? <div className="detection-list">
        {result.detections.map((det, index) => <div key={index}>
          <strong>{labels[det.class_name] ?? det.class_name} {index + 1}</strong>
          <span>Confianza {(det.confidence * 100).toFixed(1)}%</span>
          <small>Recuadro: {det.bbox_xyxy.join(', ')}</small>
        </div>)}
      </div> : <p>No hubo detecciones por encima del umbral; esto no demuestra ausencia de fauna.</p>}
      <p className="scientific-note">{result.note} La confianza del modelo no equivale a una exactitud científica validada.</p>
    </div>}
  </section>;
}

function OriginalPreview({ file }: { file: File }) {
  const [src, setSrc] = React.useState('');
  React.useEffect(() => {
    const url = URL.createObjectURL(file);
    setSrc(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  return src ? <img src={src} alt="Fotografía original sin anotaciones" /> : null;
}
