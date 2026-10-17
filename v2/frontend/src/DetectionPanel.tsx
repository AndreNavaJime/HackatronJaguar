import React from 'react';
import { useLanguage } from './language';

type Detection = {
  class_name: string;
  confidence: number;
  bbox_xyxy: number[];
};
type RosetteSample = {
  animal_bbox_xyxy: number[];
  texture_regions_xyxy: number[][];
  annotated_crop: string;
};
type PatternResult = {
  status: string;
  method?: string;
  samples: RosetteSample[];
  identity_verified: boolean;
  scientifically_validated: boolean;
  note: string;
};
type DetectionResult = {
  animal_detection_performed?: boolean;
  model: string;
  device: string;
  threshold: number;
  inference_seconds: number;
  counts: { animal: number; person: number; vehicle: number };
  detections: Detection[];
  annotated_image: string;
  rosette_patterns?: PatternResult;
  note: string;
};

const labels: Record<string, string> = { animal: 'Animal', person: 'Persona', vehicle: 'Vehículo' };

export default function DetectionPanel({ file, enabled }: { file: File | null; enabled: boolean }) {
  const { t } = useLanguage();
  const [result, setResult] = React.useState<DetectionResult | null>(null);
  const [threshold, setThreshold] = React.useState(0.25);
  const [processing, setProcessing] = React.useState(false);
  const [error, setError] = React.useState('');
  const [annotated, setAnnotated] = React.useState(true);
  const activeRequest = React.useRef<AbortController | null>(null);

  React.useEffect(() => {
    activeRequest.current?.abort();
    setResult(null);
    setError('');
    setAnnotated(true);
    // Analyze a photo automatically as soon as it is selected and Python is connected.
    if (file && enabled) void detect(file);
    return () => activeRequest.current?.abort();
  }, [file, enabled]);

  async function detect(photo: File | null = file) {
    if (!photo || !enabled) return;
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    if (photo.size > 12 * 1024 * 1024) {
      setError(t('El tamaño máximo permitido es de 12 MB.'));
      activeRequest.current = null;
      return;
    }
    setProcessing(true);
    setResult(null);
    setError('');
    try {
      const response = await fetch('/api/images/analyze?threshold=' + threshold.toFixed(2), {
        method: 'POST',
        headers: { 'Content-Type': photo.type || 'application/octet-stream' },
        body: photo,
        signal: controller.signal,
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
      if (controller.signal.aborted) return;
      setResult(payload as DetectionResult);
      setAnnotated(true);
    } catch (cause) {
      if (controller.signal.aborted) return;
      const message = cause instanceof Error ? cause.message : t('No se pudo ejecutar MegaDetector.');
      setError(message === 'Failed to fetch'
        ? 'Se perdió la comunicación con Python. Puede haberse cerrado por falta de memoria. Revisá la terminal de FastAPI.'
        : message);
    } finally {
      if (activeRequest.current === controller) {
        activeRequest.current = null;
        setProcessing(false);
      }
    }
  }

  return <section className="detector-panel">
    <h3>{t('Fotografía · análisis automático de pelaje')}</h3>
    <p>{t("Al seleccionar una fotografía comienza automáticamente el análisis en el servidor, si el modelo está disponible.")}</p>
    <p>{t('Con MegaDetector activado detecta fauna; en el plan gratuito explora únicamente patrones de textura. Ninguna opción identifica especies ni individuos.')}</p>
    <div className="detector-actions">
      <label htmlFor="confidence-threshold">{t("Umbral de confianza:")} {Math.round(threshold * 100)}%</label>
      <input id="confidence-threshold" type="range" min="0.1" max="0.9" step="0.05"
        value={threshold} onChange={event => setThreshold(Number(event.target.value))} />
      <button className="action-button detection-button" type="button" disabled={!file || processing || !enabled} onClick={() => void detect()}>
        {t(processing ? 'Analizando fotografía…' : result ? 'Repetir análisis con este umbral' : 'Explorar fotografía automáticamente')}
      </button>
      <small>{t('El escaneo ligero funciona en Render sin PyTorch; MegaDetector requiere un servidor con recursos adicionales.')}
        </small>
    </div>
    {error && <p className="upload-error" role="alert">{error}</p>}
    {result && <div className="detection-results" aria-live="polite">
      <h3>{t("Resultados científicos preliminares")}</h3>
      <p className="scientific-note">{result.animal_detection_performed ? t('Detección animal IA ejecutada.') : t('Exploración ligera de textura: no se ejecutó un detector de animales. Los conteos siguientes no son observaciones.')}</p>
      <div className="detection-metrics">
        <div><span>{t("Animales")}</span><strong>{result.animal_detection_performed ? result.counts.animal : '—'}</strong></div>
        <div><span>{t("Personas")}</span><strong>{result.animal_detection_performed ? result.counts.person : '—'}</strong></div>
        <div><span>{t("Vehículos")}</span><strong>{result.animal_detection_performed ? result.counts.vehicle : '—'}</strong></div>
        <div><span>{t("Inferencia")}</span><strong>{result.inference_seconds.toFixed(2)} s</strong></div>
      </div>
      <p className="details-caption">{result.model} · {result.device.toUpperCase()} · {t('Umbral')} {Math.round(result.threshold * 100)}%</p>
      <div className="annotated-viewer">
        {annotated
          ? <img src={result.annotated_image} alt={t("Fotografía con recuadros y confianza de las detecciones")} />
          : file && <OriginalPreview file={file} />}
        <div className="preview-controls">
          <button type="button" className={annotated ? 'active' : ''} onClick={() => setAnnotated(true)}>{t("Con recuadros")}</button>
          <button type="button" className={!annotated ? 'active' : ''} onClick={() => setAnnotated(false)}>{t("Original")}</button>
          <a className="download-link" href={result.annotated_image} download="pantherascan_detecciones.jpg">{t("Descargar anotada ↓")}</a>
        </div>
      </div>
      {result.detections.length ? <div className="detection-list">
        {result.detections.map((det, index) => <div key={index}>
          <strong>{t(labels[det.class_name] ?? det.class_name)} {index + 1}</strong>
          <span>{t("Confianza")} {(det.confidence * 100).toFixed(1)}%</span>
          <small>{t("Recuadro:")} {det.bbox_xyxy.join(', ')}</small>
        </div>)}
      </div> : <p>{t(result.animal_detection_performed ? 'No hubo detecciones por encima del umbral; esto no demuestra ausencia de fauna.' : 'No se ejecutó un detector de animales. La exploración de textura no permite afirmar presencia o ausencia de fauna.')}</p>}
      {result.rosette_patterns && <div className="rosette-automatic-preview">
        <h4>{t('Patrones de pelaje · exploración automática')}</h4>
        <p>{t('Zonas anulares candidatas dentro de los animales detectados. No es una identificación por rosetas.')}</p>
        {result.rosette_patterns.samples.map((sample, index) => <figure key={index}>
          <img src={sample.annotated_crop} alt={t('Recorte de animal con regiones de textura candidatas')} loading="lazy" />
          <figcaption>{t(result.animal_detection_performed ? 'Animal' : 'Fotografía')} {index + 1} · {sample.texture_regions_xyxy.length} {t('regiones candidatas (no rosetas confirmadas)')}</figcaption>
        </figure>)}
        {!result.rosette_patterns.samples.length && <p>{t('No se obtuvieron recortes de pelaje analizables.')}</p>}
        <p className="scientific-note">{result.rosette_patterns.note}</p>
      </div>}
      <p className="scientific-note">{result.note} {t('La confianza del modelo no equivale a una exactitud científica validada.')}</p>
    </div>}
  </section>;
}

function OriginalPreview({ file }: { file: File }) {
  const { t } = useLanguage();
  const [src, setSrc] = React.useState('');
  React.useEffect(() => {
    const url = URL.createObjectURL(file);
    setSrc(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  return src ? <img src={src} alt={t("Fotografía original sin anotaciones")} /> : null;
}
