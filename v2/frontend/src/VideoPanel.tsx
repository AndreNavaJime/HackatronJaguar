import React from 'react';

type Counts = { animal: number; person: number; vehicle: number };
type Frame = {
  sample: number;
  time_seconds: number;
  retained: boolean;
  counts: Counts;
  max_animal_confidence: number;
  inference_seconds: number;
  image: string;
};
type Candidate = {
  sample: number;
  time_seconds: number;
  confidence: number;
  bbox_xyxy: number[];
  image: string;
  filename: string;
};
type SampleRow = {
  sample: number;
  video_time_seconds: number;
  animals: number;
  persons: number;
  vehicles: number;
  max_animal_confidence: number;
  edge_decision: 'RETAIN' | 'DISCARD';
  input_jpeg_bytes: number;
  candidate_jpeg_bytes: number;
  inference_seconds: number;
};
type VideoAnalysis = {
  metadata: {
    filename: string;
    source_width: number;
    source_height: number;
    analysis_width: number;
    analysis_height: number;
    fps: number;
    duration_seconds: number;
    total_video_frames: number;
    sample_seconds: number;
    threshold: number;
    model: string;
    device: string;
  };
  totals: {
    sampled: number;
    retained: number;
    discarded: number;
    animals: number;
    persons: number;
    vehicles: number;
    mean_confidence: number;
    max_confidence: number;
    positive_frame_rate: number;
    estimated_payload_reduction: number;
    input_jpeg_bytes: number;
    retained_jpeg_bytes: number;
    mean_inference_seconds: number;
  };
  rows: SampleRow[];
  frames: Frame[];
  candidates: Candidate[];
  note: string;
};
type JobSnapshot = {
  job_id: string;
  state: 'uploading' | 'processing' | 'completed' | 'failed';
  stage: string;
  processed: number;
  total: number;
  error: string | null;
  result: VideoAnalysis | null;
};
type LocalStatus = 'idle' | 'uploading' | 'processing' | 'completed' | 'failed';

const MAX_VIDEO_BYTES = 250 * 1024 * 1024;
const UPLOAD_CHUNK_BYTES = 5 * 1024 * 1024;
const percentage = (value: number) => (value * 100).toFixed(1) + '%';
const megabytes = (bytes: number) => (bytes / 1024 / 1024).toFixed(2) + ' MB';

async function fetchJson(response: Response) {
  let raw: string;
  try {
    raw = await response.text();
  } catch {
    throw new Error('La conexión se interrumpió mientras recibíamos una respuesta de Python.');
  }
  let value: unknown = null;
  if (raw.trim()) {
    try {
      value = JSON.parse(raw);
    } catch {
      const status = 'HTTP ' + response.status;
      if (response.status === 413) {
        throw new Error('El servidor intermediario rechazó el tamaño de la petición (' + status + ').');
      }
      throw new Error('Se recibió una respuesta no JSON (' + status +
        '). Revisá la terminal de FastAPI y la de Vite; podría ser un error del proxy de Codespaces.');
    }
  }
  if (!response.ok) {
    const detail = typeof value === 'object' && value !== null && 'detail' in value &&
      typeof value.detail === 'string' ? value.detail : 'HTTP ' + response.status;
    throw new Error(detail);
  }
  if (typeof value !== 'object' || value === null) {
    throw new Error('El servidor devolvió una respuesta vacía.');
  }
  return value;
}

function Timeline({ rows, threshold }: { rows: SampleRow[]; threshold: number }) {
  if (!rows.length) return null;
  const left = 43;
  const right = 680;
  const top = 14;
  const bottom = 158;
  const startTime = rows[0].video_time_seconds;
  const endTime = rows[rows.length - 1].video_time_seconds;
  const x = (time: number) => left + (endTime > startTime
    ? ((time - startTime) / (endTime - startTime)) * (right - left)
    : (right - left) / 2);
  const y = (value: number) => bottom - Math.min(1, Math.max(0, value)) * (bottom - top);
  const line = rows.map((row, index) =>
    (index === 0 ? 'M' : 'L') + x(row.video_time_seconds).toFixed(1) +
    ',' + y(row.max_animal_confidence).toFixed(1)).join(' ');

  return <div className="video-graph">
    <h4>Confianza animal a lo largo del video</h4>
    <svg role="img" aria-label="Gráfico de confianza máxima de detección animal por fotograma muestreado" viewBox="0 0 710 193">
      {[0, 0.25, 0.5, 0.75, 1].map(t => <g key={t}>
        <line x1={left} y1={y(t)} x2={right} y2={y(t)} stroke="#315741" strokeDasharray="3 4" />
        <text x={35} y={y(t) + 4} textAnchor="end" fill="#b3c9b9" fontSize="11">{Math.round(t * 100)}%</text>
      </g>)}
      <line x1={left} y1={y(threshold)} x2={right} y2={y(threshold)} stroke="#f0c56e" strokeWidth="1.6" strokeDasharray="8 5" />
      <path d={line} fill="none" stroke="#70daa0" strokeWidth="2.3" strokeLinejoin="round" />
      {rows.map(row => <circle key={row.sample} cx={x(row.video_time_seconds)}
        cy={y(row.max_animal_confidence)} r={4.5}
        fill={row.edge_decision === 'RETAIN' ? '#80e6a5' : '#849b8a'}>
        <title>{'Muestra ' + row.sample + ' · ' + row.video_time_seconds + ' s · ' + percentage(row.max_animal_confidence)}</title>
      </circle>)}
      <text x={left} y={183} fill="#b3c9b9" fontSize="12">{startTime.toFixed(1)} s</text>
      <text x={right} y={183} fill="#b3c9b9" textAnchor="end" fontSize="12">{endTime.toFixed(1)} s</text>
    </svg>
    <small>Línea amarilla: umbral configurado. Los ceros indican ausencia de detección animal en ese fotograma, no ausencia de fauna.</small>
  </div>;
}

function Download({ href, children, filename }: { href: string; children: React.ReactNode; filename?: string }) {
  return <a className="download-link" href={href} download={filename}>{children}</a>;
}

export default function VideoPanel({ enabled }: { enabled: boolean }) {
  const [file, setFile] = React.useState<File | null>(null);
  const [videoUrl, setVideoUrl] = React.useState<string | null>(null);
  const [threshold, setThreshold] = React.useState(0.25);
  const [sampleSeconds, setSampleSeconds] = React.useState(1);
  const [maxSamples, setMaxSamples] = React.useState(8);
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [status, setStatus] = React.useState<LocalStatus>('idle');
  const [job, setJob] = React.useState<JobSnapshot | null>(null);
  const [result, setResult] = React.useState<VideoAnalysis | null>(null);
  const [error, setError] = React.useState('');
  const [uploadedBytes, setUploadedBytes] = React.useState(0);

  React.useEffect(() => {
    if (!file) {
      setVideoUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setVideoUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  React.useEffect(() => {
    if (!jobId || status !== 'processing') return;
    let active = true;
    async function poll() {
      try {
        const response = await fetch('/api/videos/jobs/' + jobId, { cache: 'no-store' });
        const data = await fetchJson(response) as JobSnapshot;
        if (!active) return;
        setJob(data);
        if (data.state === 'completed') {
          if (!data.result) throw new Error('El análisis terminó sin resultados.');
          setResult(data.result);
          setStatus('completed');
        } else if (data.state === 'failed') {
          setError(data.error || 'Falló el análisis. Revisá la terminal de Python.');
          setStatus('failed');
        }
      } catch (cause) {
        if (!active) return;
        // One lost poll should not falsely mark an inference job as failed.
        setError(cause instanceof Error ? cause.message : 'No se pudo consultar el avance.');
      }
    }
    void poll();
    const timer = window.setInterval(() => { void poll(); }, 2000);
    return () => { active = false; window.clearInterval(timer); };
  }, [jobId, status]);

  const busy = status === 'uploading' || status === 'processing';

  function onFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
    setStatus('idle');
    setJob(null);
    setJobId(null);
    setResult(null);
    setError('');
    setUploadedBytes(0);
  }

  async function analyze() {
    if (!file || !enabled || busy) return;
    if (file.size > MAX_VIDEO_BYTES) {
      setError('El video supera el límite de 250 MB.');
      return;
    }
    const extension = file.name.split('.').pop()?.toLowerCase();
    if (!extension || !['mp4', 'mov', 'avi', 'mkv'].includes(extension)) {
      setError('Formato no admitido. Usá MP4, MOV, AVI o MKV.');
      return;
    }
    setStatus('uploading');
    setUploadedBytes(0);
    setError('');
    setResult(null);
    setJob(null);
    let uploadId: string | null = null;
    try {
      const params = new URLSearchParams({
        threshold: threshold.toFixed(2),
        sample_seconds: sampleSeconds.toFixed(1),
        max_samples: String(maxSamples),
      });
      // Each network request is <= 5 MiB; large single POSTs may be rejected
      // by Codespaces or development proxies before reaching Python.
      const start = await fetchJson(await fetch('/api/videos/uploads?' + params.toString(), {
        method: 'POST',
        headers: {
          'X-Video-Name': encodeURIComponent(file.name),
          'X-Video-Size': String(file.size),
        },
      })) as { upload_id?: string; chunk_max_bytes?: number };
      if (!start.upload_id) throw new Error('Python no devolvió una sesión de carga.');
      uploadId = start.upload_id;
      const chunkSize = Math.min(UPLOAD_CHUNK_BYTES, start.chunk_max_bytes || UPLOAD_CHUNK_BYTES);
      let offset = 0;
      while (offset < file.size) {
        const next = Math.min(offset + chunkSize, file.size);
        const reply = await fetchJson(await fetch(
          '/api/videos/uploads/' + uploadId + '/chunks?offset=' + offset,
          { method: 'PUT', headers: { 'Content-Type': 'application/octet-stream' },
            body: file.slice(offset, next) }
        )) as { received_bytes?: number };
        if (reply.received_bytes !== next) {
          throw new Error('La cantidad de datos recibidos no coincide con el bloque enviado.');
        }
        offset = next;
        setUploadedBytes(offset);
      }
      const completed = await fetchJson(await fetch(
        '/api/videos/uploads/' + uploadId + '/complete', { method: 'POST' }
      )) as { job_id?: string };
      if (!completed.job_id) throw new Error('Python no confirmó el inicio del análisis.');
      setJobId(completed.job_id);
      setStatus('processing');
    } catch (cause) {
      if (uploadId) {
        // Best-effort cleanup; never hide the original upload error.
        try { await fetch('/api/videos/uploads/' + uploadId, { method: 'DELETE' }); } catch { /* ignored */ }
      }
      setStatus('failed');
      setError(cause instanceof Error ? cause.message : 'No se pudo enviar el video.');
    }
  }

  const downloadBase = jobId ? '/api/videos/jobs/' + jobId + '/download?kind=' : '';

  return <section className="video-panel" aria-label="Análisis de video">
    <div className="panel-heading">
      <div>
        <h3>Análisis de videos · PantheraEDGE + MegaDetector V6</h3>
        <p>Procesamiento local de muestras de videos de cámaras trampa, con fotogramas, recortes y exportaciones científicas.</p>
      </div>
      <span className="tag">VIDEO · BETA</span>
    </div>

    <div className="video-config">
      <div className="video-input">
        <label htmlFor="panthera-video">Video de cámara trampa (MP4, MOV, AVI o MKV · máximo 250 MB)</label>
        <input id="panthera-video" type="file" accept=".mp4,.mov,.avi,.mkv,video/mp4,video/quicktime,video/x-msvideo"
          disabled={busy} onChange={onFileChange} />
        {file && <small>{file.name} · {megabytes(file.size)}</small>}
        {videoUrl && <video className="video-preview" src={videoUrl} controls preload="metadata"
          aria-label="Vista previa del video seleccionado">
          Tu navegador no puede reproducir este formato; Python podría procesarlo.
        </video>}
        <small>La reproducción previa depende del navegador; OpenCV podría leer formatos que el navegador no reproduce.</small>
      </div>
      <div className="video-options">
        <label htmlFor="video-threshold">Umbral de confianza: {Math.round(threshold * 100)}%</label>
        <input id="video-threshold" type="range" min={0.1} max={0.9} step={0.05} value={threshold}
          disabled={busy} onChange={e => setThreshold(Number(e.target.value))} />
        <label htmlFor="video-interval">Muestreo cada {sampleSeconds.toFixed(1)} segundos</label>
        <input id="video-interval" type="range" min={0.5} max={5} step={0.5} value={sampleSeconds}
          disabled={busy} onChange={e => setSampleSeconds(Number(e.target.value))} />
        <label htmlFor="video-samples">Máximo de fotogramas: {maxSamples}</label>
        <input id="video-samples" type="range" min={1} max={24} step={1} value={maxSamples}
          disabled={busy} onChange={e => setMaxSamples(Number(e.target.value))} />
        <button className="action-button" type="button" disabled={!file || !enabled || busy}
          onClick={() => void analyze()}>
          {status === 'uploading' ? 'Enviando video…' : busy ? 'Analizando video…' : 'Analizar video con IA'}
        </button>
        <small>Los archivos grandes se transfieren en bloques de 5 MB para evitar límites de la conexión. Después se analizan los fotogramas muestreados.</small>
      </div>
    </div>

    {status === 'uploading' && file && <div className="video-progress" role="status" aria-live="polite">
      <strong>Subiendo video en bloques de 5 MB…</strong>
      <p>{megabytes(uploadedBytes)} de {megabytes(file.size)} · {Math.round(100 * uploadedBytes / file.size)}%</p>
      <progress max={file.size} value={uploadedBytes} />
      <small>No cerrés la pestaña hasta terminar la carga.</small>
    </div>}
    {status === 'processing' && <div className="video-progress" role="status" aria-live="polite">
      <strong>{job?.stage || 'Preparando MegaDetector…'}</strong>
      <p>{job?.processed ?? 0} de {job?.total || maxSamples} fotogramas completados</p>
      <progress max={job?.total || maxSamples} value={job?.processed ?? 0} />
      <small>Podés dejar esta pestaña abierta mientras Python procesa el video.</small>
    </div>}
    {error && <p role="alert" className="upload-error">{error}</p>}

    {result && <div className="video-results">
      <h3>Resultados científicos preliminares</h3>
      <p className="details-caption">{result.metadata.model} · {result.metadata.device} · Video: {result.metadata.filename}</p>
      <div className="video-metrics">
        <div><span>Fotogramas muestreados</span><strong>{result.totals.sampled}</strong></div>
        <div><span>Con animales</span><strong>{result.totals.retained}</strong></div>
        <div><span>Sin animales</span><strong>{result.totals.discarded}</strong></div>
        <div><span>Detecciones animales</span><strong>{result.totals.animals}</strong></div>
        <div><span>Confianza media animal</span><strong>{percentage(result.totals.mean_confidence)}</strong></div>
        <div><span>Frecuencia de muestras positivas</span><strong>{result.totals.positive_frame_rate.toFixed(1)}%</strong></div>
      </div>
      <div className="video-metadata">
        <span>Duración: {result.metadata.duration_seconds.toFixed(1)} s</span>
        <span>FPS: {result.metadata.fps.toFixed(1)}</span>
        <span>Original: {result.metadata.source_width} × {result.metadata.source_height} px</span>
        <span>Análisis: {result.metadata.analysis_width} × {result.metadata.analysis_height} px</span>
        <span>Inferencia media: {result.totals.mean_inference_seconds.toFixed(2)} s/muestra</span>
      </div>
      <div className="video-analytics">
        <div className="video-chart-panel">
          <h4>Filtrado simulado de PantheraEDGE</h4>
          <div className="filter-meter" aria-label={'Retenidos ' + result.totals.retained + '; descartados ' + result.totals.discarded}>
            <div style={{ width: result.totals.positive_frame_rate + '%' }} />
          </div>
          <div className="filter-legend">
            <span>● Con animales: {result.totals.retained}</span>
            <span>○ Sin animales: {result.totals.discarded}</span>
          </div>
          <p>Carga JPEG de fotogramas muestreados: {megabytes(result.totals.input_jpeg_bytes)}.</p>
          <p>Carga JPEG de fotogramas retenidos: {megabytes(result.totals.retained_jpeg_bytes)}.</p>
          <strong>Reducción estimada: {result.totals.estimated_payload_reduction.toFixed(1)}%</strong>
          <small>Estimación de archivos JPEG de muestras, NO ahorro de tráfico 5G medido.</small>
        </div>
        <Timeline rows={result.rows} threshold={result.metadata.threshold} />
      </div>

      <div className="video-downloads">
        <h4>Descargas para revisión</h4>
        <div className="preview-controls">
          <Download href={downloadBase + 'zip'}>Descargar fotogramas y candidatos · ZIP ↓</Download>
          <Download href={downloadBase + 'csv'}>Tabla por fotograma · CSV ↓</Download>
          <Download href={downloadBase + 'pdf'}>Informe preliminar · PDF ↓</Download>
        </div>
        <small>Los archivos se conservan temporalmente en Codespaces hasta una hora. Descargalos antes de cerrar el servidor.</small>
      </div>

      <h4>Galería de fotogramas anotados</h4>
      <p>Cada recuadro marca una detección, no una identidad confirmada. Se muestran todos los fotogramas muestreados.</p>
      <div className="video-gallery">
        {result.frames.map(frame => <article key={frame.sample} className="video-frame-card">
          <img src={frame.image} loading="lazy" alt={'Fotograma ' + frame.sample + ' con anotaciones de MegaDetector'} />
          <div className="video-frame-details">
            <strong>Muestra {frame.sample} · {frame.time_seconds.toFixed(1)} s</strong>
            <span>{frame.retained ? 'RETENER · animal detectado' : 'DESCARTAR · sin detección animal'}</span>
            <small>Animales: {frame.counts.animal} · Personas: {frame.counts.person} · Vehículos: {frame.counts.vehicle}</small>
            <small>Confianza animal máxima: {percentage(frame.max_animal_confidence)}</small>
            <Download href={frame.image} filename={'pantheraid_muestra_' + String(frame.sample).padStart(3, '0') + '.jpg'}>Descargar fotograma ↓</Download>
          </div>
        </article>)}
      </div>

      <h4>Recortes candidatos para revisión de fauna ({result.candidates.length})</h4>
      <p>Estas imágenes requieren validación visual por personal científico; MegaDetector no puede confirmar que sean jaguares.</p>
      {result.candidates.length
        ? <div className="video-gallery video-candidates">
          {result.candidates.map((candidate, index) => <article key={index} className="video-frame-card">
            <img src={candidate.image} loading="lazy" alt={'Recorte candidato ' + (index + 1) + ' detectado en video'} />
            <div className="video-frame-details">
              <strong>Candidato {index + 1} · {candidate.time_seconds.toFixed(1)} s</strong>
              <small>Confianza: {percentage(candidate.confidence)} · Muestra {candidate.sample}</small>
              <small>Coordenadas del recuadro: {candidate.bbox_xyxy.join(', ')}</small>
              <Download href={candidate.image} filename={candidate.filename}>Descargar candidato ↓</Download>
            </div>
          </article>)}
        </div>
        : <p>No hubo recortes animales por encima del umbral elegido.</p>}

      <details className="video-table-details">
        <summary>Ver tabla de resultados por fotograma ({result.rows.length})</summary>
        <div className="video-table-scroll">
          <table>
            <thead><tr><th>Muestra</th><th>Tiempo (s)</th><th>Animales</th><th>Personas</th><th>Vehículos</th><th>Confianza animal máx.</th><th>Decisión</th></tr></thead>
            <tbody>{result.rows.map(row => <tr key={row.sample}>
              <td>{row.sample}</td><td>{row.video_time_seconds.toFixed(2)}</td>
              <td>{row.animals}</td><td>{row.persons}</td><td>{row.vehicles}</td>
              <td>{percentage(row.max_animal_confidence)}</td>
              <td>{row.edge_decision}</td>
            </tr>)}</tbody>
          </table>
        </div>
      </details>
      <p className="scientific-note">{result.note} La ausencia de detección entre muestras no puede inferirse. Las confianzas del modelo no equivalen a sensibilidad, especificidad ni exactitud validada.</p>
    </div>}
  </section>;
}
