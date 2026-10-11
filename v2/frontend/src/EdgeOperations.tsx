import React from 'react';
import type { EdgeSummary, ScientificObservation } from './ScientificWorkspace';

type EdgeEvent = {
  contract_version?: string; event_id?: string; timestamp?: string | null;
  camera_id?: string; event?: string; transport?: string; status?: string;
  latitude?: number | null; longitude?: number | null;
  temperature?: number | null; humidity?: number | null;
  class?: string | null; confidence?: number | null;
  hmac_status?: string; source?: string;
};

type Props = {
  latestEdge: EdgeSummary | null;
  draft: ScientificObservation;
  setDraft: React.Dispatch<React.SetStateAction<ScientificObservation>>;
  enabled: boolean;
};

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return <div className="edge-metric"><span>{label}</span><strong>{value}</strong>
    {detail && <small>{detail}</small>}</div>;
}
const percent = (number: number) => (number * 100).toFixed(1) + '%';
const mb = (bytes: number) => (bytes / 1024 / 1024).toFixed(3) + ' MB';

function ConfidenceGraph({ rows, threshold = 0.25 }: { rows: NonNullable<EdgeSummary['rows']>; threshold?: number }) {
  if (!rows.length) return null;
  const values = rows.map(point => Math.max(0, Math.min(1, point.confidence)));
  const W = 680, H = 180, L = 38, R = 660, T = 12, B = 147;
  const line = values.map((value, i) =>
    (i === 0 ? 'M' : 'L') + (L + i / Math.max(1, values.length - 1) * (R - L)).toFixed(1)
    + ',' + (B - value * (B - T)).toFixed(1)).join(' ');
  return <div className="edge-chart">
    <h4>Confianza de detección animal por muestra</h4>
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Perfil de confianza de MegaDetector de cero a cien por ciento">
      {[0, 0.25, 0.5, 0.75, 1].map(value => <g key={value}>
        <line x1={L} x2={R} y1={B - value * (B - T)} y2={B - value * (B - T)}
          stroke="#315b45" strokeDasharray="4 5" />
        <text x={L - 5} y={B - value * (B - T) + 4} fontSize="11" textAnchor="end" fill="#b9cfbf">{Math.round(value * 100)}%</text>
      </g>)}
      <line x1={L} x2={R} y1={B - threshold * (B - T)} y2={B - threshold * (B - T)}
        stroke="#f2c675" strokeDasharray="7 5" strokeWidth="2" />
      <path d={line} stroke="#78db99" fill="none" strokeWidth="2.5" />
      {values.map((value, index) => <circle key={index}
        cx={L + index / Math.max(1, values.length - 1) * (R - L)}
        cy={B - value * (B - T)} r={4} fill={rows[index].retained ? '#86eab0' : '#abb7ae'} />)}
      <text x={L} y={H - 7} fill="#b9cfbf" fontSize="11">Muestra 1</text>
      <text x={R} y={H - 7} textAnchor="end" fill="#b9cfbf" fontSize="11">Muestra {rows.length}</text>
    </svg>
    <small>La línea amarilla representa el umbral del análisis. Los ceros no demuestran ausencia de fauna.</small>
  </div>;
}

function Distribution({ rows }: { rows: NonNullable<EdgeSummary['rows']> }) {
  const detected = rows.map(row => row.confidence).filter(value => value > 0);
  if (!detected.length) return <p>No hay valores positivos para calcular una distribución.</p>;
  const bins = Array.from({ length: 5 }, (_, index) =>
    detected.filter(value => value >= index / 5 && (index === 4 ? value <= 1 : value < (index + 1) / 5)).length);
  const largest = Math.max(...bins, 1);
  return <div className="edge-chart"><h4>Distribución de confianza entre muestras positivas</h4>
    <div className="edge-bars">{bins.map((count, index) => <div key={index} className="edge-bar-item">
      <span>{Math.round(index * 20)}–{Math.round((index + 1) * 20)}%</span>
      <div className="edge-bar-track"><div style={{ width: (count / largest * 100) + '%' }} /></div>
      <strong>{count}</strong>
    </div>)}</div>
    <small>Se agrupa la confianza máxima por muestra, no cada detección individual. Este histograma no mide exactitud del modelo.</small>
  </div>;
}

export default function EdgeOperations({ latestEdge, draft, setDraft, enabled }: Props) {
  const [event, setEvent] = React.useState<EdgeEvent | null>(null);
  const [eventSource, setEventSource] = React.useState<'none' | 'demo' | 'remote'>('none');
  const [eventError, setEventError] = React.useState('');
  const [polling, setPolling] = React.useState(false);
  const [notice, setNotice] = React.useState('');
  const [measured, setMeasured] = React.useState(false);
  const [fiveGUp, setFiveGUp] = React.useState(20);
  const [fiveGLatency, setFiveGLatency] = React.useState(25);
  const [fourGUp, setFourGUp] = React.useState(8);
  const [fourGLatency, setFourGLatency] = React.useState(60);
  const [mapVisible, setMapVisible] = React.useState(false);

  const rawBytes = latestEdge?.input_jpeg_bytes ?? null;
  const keptBytes = latestEdge?.retained_jpeg_bytes ?? null;
  const comparable = rawBytes !== null && keptBytes !== null && rawBytes > 0;
  const raw = comparable ? rawBytes : 0;
  const filtered = comparable ? keptBytes : 0;
  const reduction = comparable ? (raw - filtered) / raw * 100 : null;
  const seconds = (bytes: number, throughput: number, latency: number) =>
    bytes * 8 / 1000000 / Math.max(throughput, 0.001) + latency / 1000;
  function simulate() {
    setEvent({
      contract_version: 'panthera-v1.0',
      event_id: 'EDGE-DEMO-' + Math.floor(Date.now() / 1000),
      timestamp: new Date().toISOString(),
      camera_id: draft.camera_id || 'CAMARA-SIN-ASIGNAR',
      event: 'new_capture', transport: 'Wi-Fi / LoRa (demo)',
      status: 'SIMULATED', hmac_status: 'NOT_CHECKED', source: 'demo_local',
      latitude: draft.latitude, longitude: draft.longitude,
    });
    setEventSource('demo'); setEventError(''); setNotice('');
  }
  async function pollRemote() {
    if (!enabled) { setEventError('Se requiere conexión con FastAPI.'); return; }
    setPolling(true); setEventError(''); setNotice('');
    try {
      const response = await fetch('/api/edge/bridge', { cache: 'no-store' });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Error de puente HTTP.');
      if (!data.configured || !data.event) {
        setEventError(data.message || 'Puente sin configurar en el servidor.');
        return;
      }
      setEvent(data.event as EdgeEvent); setEventSource('remote');
    } catch (cause) {
      setEventError(cause instanceof Error ? cause.message : 'No se pudo consultar el nodo.');
    } finally { setPolling(false); }
  }
  function linkEvent() {
    if (!event) return;
    setDraft(previous => ({
      ...previous,
      edge_event_id: event.event_id || '',
      edge_event_timestamp: event.timestamp || '',
      edge_transport: event.transport || '',
      edge_hmac_status: event.hmac_status || 'NOT_CHECKED',
      camera_id: previous.camera_id || event.camera_id || '',
    }));
    setNotice('Identificador del evento asociado al formulario. Las coordenadas y las mediciones del nodo NO se copian automáticamente: necesitan validación de procedencia.');
  }

  const mapCoordsPresent = draft.latitude !== null && draft.longitude !== null;
  const latitude = draft.latitude ?? 0, longitude = draft.longitude ?? 0;
  const bbox = [
    (longitude - 0.015).toFixed(6), (latitude - 0.015).toFixed(6),
    (longitude + 0.015).toFixed(6), (latitude + 0.015).toFixed(6),
  ].join(',');
  const osmMap = 'https://www.openstreetmap.org/export/embed.html?bbox=' + encodeURIComponent(bbox)
    + '&layer=mapnik&marker=' + encodeURIComponent(latitude + ',' + longitude);

  return <div className="edge-operations">
    <section className="panel edge-module">
      <h2>PantheraEDGE · Flujo de monitoreo</h2>
      <div className="edge-flow" aria-label="Arquitectura conceptual">
        {['PantheraCAM / Sensores', 'PantheraEDGE · IA local', 'Troncal 5G / 4G', 'Panthera LAB · Nube', 'Investigadores / Instituciones'].map((step, index) =>
          <React.Fragment key={step}>{index > 0 && <span aria-hidden="true" className="edge-flow-arrow">→</span>}
            <div><small>ETAPA {index + 1}</small><strong>{step}</strong></div></React.Fragment>)}
      </div>
      <p className="scientific-note">Arquitectura de referencia: esta PWA es la interfaz de investigación. La ingesta real y la transmisión 5G dependen de infraestructura externa; no se infieren conexiones físicas.</p>
    </section>

    <section className="panel edge-module">
      <h2>Resultados y analítica de MegaDetector</h2>
      {latestEdge ? <>
        <p>Último archivo: <strong>{latestEdge.filename}</strong> · {latestEdge.model}</p>
        <div className="edge-metrics-grid">
          <Metric label="Muestras analizadas" value={String(latestEdge.sampled)} />
          <Metric label="Frames retenidos" value={String(latestEdge.retained)} />
          <Metric label="Animales detectados" value={String(latestEdge.animals)} />
          <Metric label="Personas / vehículos" value={latestEdge.persons + ' / ' + latestEdge.vehicles} />
          <Metric label="Confianza máxima" value={percent(latestEdge.max_confidence)} />
          <Metric label="Reducción JPEG estimada" value={reduction === null ? 'Sin datos' : reduction.toFixed(1) + '%'} />
        </div>
        {(latestEdge.rows?.length ?? 0) > 0 && <div className="edge-graphs">
          <ConfidenceGraph rows={latestEdge.rows!} threshold={latestEdge.threshold} />
          <Distribution rows={latestEdge.rows!} />
        </div>}
        <p className="scientific-note">La detección animal no identifica especies, ni jaguares individuales. La confianza no mide precisión, y las muestras positivas no representan individuos únicos.</p>
      </> : <p>Analizá una imagen o video en PantheraID o en el bloque multimedia de esta pestaña. Los resultados científicos aparecerán aquí.</p>}
    </section>

    <section className="panel edge-module">
      <h2>Ubicación de cámara · Contexto espacial</h2>
      <p>{mapCoordsPresent ? 'Latitud: ' + latitude.toFixed(6) + ' · Longitud: ' + longitude.toFixed(6) : 'Aún no se registran coordenadas.'}</p>
      <small>La ubicación es de la estación, no del animal. Indicá coordenadas reales y procedencia en el formulario científico.</small>
      {mapCoordsPresent && <>
        <div className="science-actions"><button type="button" onClick={() => setMapVisible(value => !value)}>
          {mapVisible ? 'Ocultar mapa' : 'Mostrar mapa OpenStreetMap'}
        </button></div>
        {mapVisible && <div className="edge-map">
          <p>Al mostrar el mapa, las coordenadas se comparten con OpenStreetMap. No uses ubicaciones sensibles sin autorización.</p>
          <iframe src={osmMap} title="Mapa de la cámara trampa" loading="lazy" referrerPolicy="no-referrer"
            sandbox="allow-scripts allow-same-origin" />
        </div>}
      </>}
    </section>

    <section className="panel edge-module">
      <h2>Eventos PantheraCAM / PantheraEDGE</h2>
      <p>Podés simular una captura o consultar un puente HTTP real configurado previamente por el responsable del servidor.</p>
      <div className="science-actions">
        <button type="button" onClick={simulate}>Simular captura PantheraCAM</button>
        <button type="button" disabled={!enabled || polling} onClick={() => void pollRemote()}>
          {polling ? 'Consultando…' : 'Consultar puente HTTP configurado'}</button>
      </div>
      {eventError && <p role="alert" className="upload-error">{eventError}</p>}
      {event && <div className="edge-event-detail">
        <div className="edge-metrics-grid">
          <Metric label="Origen" value={eventSource === 'demo' ? 'DEMOSTRACIÓN' : 'PUENTE HTTP'} />
          <Metric label="Estado" value={event.status || 'RECEIVED'} />
          <Metric label="Contrato" value={event.contract_version || 'No indicado'} />
          <Metric label="HMAC" value={event.hmac_status || 'NOT_CHECKED'} />
        </div>
        <dl>
          <dt>ID de evento</dt><dd>{event.event_id || 'No indicado'}</dd>
          <dt>Cámara/nodo</dt><dd>{event.camera_id || 'No indicado'}</dd>
          <dt>Hora UTC</dt><dd>{event.timestamp || 'No indicada'}</dd>
          <dt>Transporte</dt><dd>{event.transport || 'No indicado'}</dd>
          <dt>Clase / confianza</dt><dd>{event.class || 'Sin detectar'} · {typeof event.confidence === 'number' ? percent(event.confidence) : 'N/D'}</dd>
        </dl>
        <div className="science-actions">
          <button type="button" onClick={linkEvent}>Vincular identificador al registro científico</button>
          <button type="button" onClick={() => {
            const anchor = document.createElement('a');
            const url = URL.createObjectURL(new Blob([JSON.stringify(event, null, 2)], { type: 'application/json' }));
            anchor.href = url; anchor.download = 'PantheraEDGE_evento.json'; anchor.click();
            window.setTimeout(() => URL.revokeObjectURL(url), 5000);
          }}>Descargar evento JSON</button>
        </div>
        {notice && <p className="science-success" role="status">{notice}</p>}
      </div>}
      <p className="scientific-note">Los eventos simulados no provienen de sensores ni de redes 5G reales. La consulta remota es opcional y requiere la variable PANTHERA_EDGE_BRIDGE_URL en FastAPI.</p>
    </section>

    <section className="panel edge-module">
      <h2>Conectividad y estimación de transferencia · 5G / 4G</h2>
      <div className="science-check"><input type="checkbox" checked={measured} onChange={event => setMeasured(event.target.checked)} />
        <span>Los valores de throughput y latencia fueron medidos externamente (testbed)</span></div>
      <p className="science-hint">Los valores iniciales son supuestos de referencia. Activar la casilla no mide la red: solo etiqueta valores aportados por el usuario.</p>
      <div className="science-grid">
        <label className="science-field"><span>5G subida (Mbps)</span><input type="number" min="0.1" max="1000" step="0.1" value={fiveGUp}
          onChange={e => setFiveGUp(Number(e.target.value))}/></label>
        <label className="science-field"><span>5G latencia / RTT (ms)</span><input type="number" min="0" max="1000" step="1" value={fiveGLatency}
          onChange={e => setFiveGLatency(Number(e.target.value))}/></label>
        <label className="science-field"><span>4G subida de respaldo (Mbps)</span><input type="number" min="0.1" max="500" step="0.1" value={fourGUp}
          onChange={e => setFourGUp(Number(e.target.value))}/></label>
        <label className="science-field"><span>4G latencia / RTT (ms)</span><input type="number" min="0" max="1000" step="1" value={fourGLatency}
          onChange={e => setFourGLatency(Number(e.target.value))}/></label>
      </div>
      {comparable ? <>
        <div className="edge-metrics-grid">
          <Metric label="JPEG muestreados" value={mb(raw)} />
          <Metric label="Frames retenidos" value={mb(filtered)} />
          <Metric label="5G entrada (estimada)" value={seconds(raw, fiveGUp, fiveGLatency).toFixed(3) + ' s'} />
          <Metric label="5G filtrado (estimado)" value={seconds(filtered, fiveGUp, fiveGLatency).toFixed(3) + ' s'} />
          <Metric label="4G filtrado (estimado)" value={seconds(filtered, fourGUp, fourGLatency).toFixed(3) + ' s'} />
          <Metric label="Tráfico evitado estimado" value={mb(Math.max(0, raw - filtered))} />
        </div>
        <p className="science-hint">Fuente: {measured ? 'valores de red declarados medidos por investigador' : 'supuestos de referencia'} · Comparación determinista de carga JPEG. No son métricas de tráfico real ni una medición de rendimiento 5G.</p>
      </> : <p>Cuando haya un análisis de video o imagen con tamaños JPEG comparables, se calcularán los tiempos estimados de transmisión.</p>}
    </section>
  </div>;
}
