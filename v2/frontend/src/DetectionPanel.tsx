import {apiFetch} from './apiClient';
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

export default function DetectionPanel({ file, enabled }: { file: File | null; enabled: boolean }) {
  const { t,language } = useLanguage();
  const tx=(es:string,en:string)=>language==='en'?en:es;
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
      const response = await apiFetch('/api/images/analyze?threshold=' + threshold.toFixed(2), {
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

  return <section className="detector-panel panthera-photo-report">
    <div className="photo-report-head">
      <h3>{tx('Análisis de fotografía','Photograph analysis')}</h3>
      <span className={result?.animal_detection_performed?'photo-report-ai-on':'photo-report-ai-off'}>
        {result?.animal_detection_performed?'IA · MegaDetector':tx('IA de detección no activa','Wildlife AI inactive')}
      </span>
    </div>
    {processing&&<p className="sci-muted" role="status">{tx('Procesando fotografía…','Processing photograph…')}</p>}
    {error&&<p className="upload-error" role="alert">{error}</p>}
    {result?.animal_detection_performed? <div className="photo-report-ai-result">
      <div className="detection-metrics">
        <div><span>{tx('Animales','Animals')}</span><strong>{result.counts.animal}</strong></div>
        <div><span>{tx('Personas','People')}</span><strong>{result.counts.person}</strong></div>
        <div><span>{tx('Vehículos','Vehicles')}</span><strong>{result.counts.vehicle}</strong></div>
      </div>
      <p className="sci-muted">{tx('Detección genérica de animales; no confirma especie ni individuo.','Generic animal detection; does not establish species or individual.')}</p>
      <div className="annotated-viewer">
        {annotated?<img src={result.annotated_image} alt={tx('Fotografía con detecciones de fauna','Photograph with wildlife detection boxes')} />:file&&<OriginalPreview file={file}/>}
        <div className="preview-controls">
          <button type="button" onClick={()=>setAnnotated(true)} className={annotated?'active':''}>{tx('Detecciones','Detections')}</button>
          <button type="button" onClick={()=>setAnnotated(false)} className={!annotated?'active':''}>{tx('Original','Original')}</button>
        </div>
      </div>
      <details className="method-details method-details-compact">
        <summary>{tx('Parámetros de IA','AI parameters')}</summary>
        <label htmlFor="confidence-threshold">{tx('Umbral del detector','Detector threshold')} {Math.round(threshold*100)}%</label>
        <input id="confidence-threshold" type="range" min="0.1" max="0.9" step="0.05"
          value={threshold} onChange={event=>setThreshold(Number(event.target.value))} />
        <button type="button" onClick={()=>void detect()} disabled={!enabled||processing}>{tx('Repetir detección','Run detection again')}</button>
        <p>{result.model} · {result.inference_seconds.toFixed(2)} s</p>
      </details>
    </div>:<div className="photo-report-next">
      <p>{tx('La fotografía está lista para comparar su pelaje con individuos conocidos. La detección automática de jaguares aún requiere un modelo de IA habilitado.',
      'Your photograph is ready for comparison with known individuals. Automatic jaguar detection still requires an enabled AI model.')}</p>
      <a className="action-button" href="#panthera-individual-compare">
        {tx('Comparar patrones de individuos ↓','Compare individual patterns ↓')}
      </a>
    </div>}
    {result&&!result.animal_detection_performed&&<details className="method-details method-details-compact photo-experimental-details">
      <summary>{tx('Exploración técnica de contornos (opcional)','Technical contour exploration (optional)')}</summary>
      <p>{tx('Son formas oscuras en toda la imagen, incluidas plantas y suelo. No son rosetas identificadas por IA.',
      'These are dark shapes in the entire photograph, including vegetation and ground. They are not AI-identified rosettes.')}</p>
      {result.rosette_patterns?.samples.map((sample,index)=><figure key={index}>
        <img src={sample.annotated_crop} alt={tx('Contornos exploratorios, no rosetas verificadas','Exploratory contours, not verified rosettes')} loading="lazy"/>
        <figcaption>{sample.texture_regions_xyxy.length} {tx('regiones visuales sin validar','unvalidated visual regions')}</figcaption>
      </figure>)}
    </details>}
    {!result&&!processing&&!error&&!enabled&&<p className="sci-muted">{tx('Esperando conexión con Render…','Waiting for Render connection…')}</p>}
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
