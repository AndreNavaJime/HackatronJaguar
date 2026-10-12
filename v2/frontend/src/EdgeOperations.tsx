import React from 'react';
import type { EdgeSummary, ScientificObservation } from './ScientificWorkspace';

type EdgeEvent = {
  contract_version?: string; event_id?: string; timestamp?: string | null;
  camera_id?: string; event?: string; transport?: string; status?: string;
  latitude?: number | null; longitude?: number | null;
  temperature?: number | null; humidity?: number | null;
  class?: string | null; confidence?: number | null;
  hmac_status?: string; source?: string;
  auth_status?: string; trigger?: string; filename?: string;
  size_bytes?: number; saved?: boolean; analyzed?: boolean;
  received_at?: string;
};
type VigiaStatus = { configured: boolean; dashboard_configured: boolean; received_count: number; message: string };

type Props = {
  latestEdge: EdgeSummary | null;
  draft: ScientificObservation;
  setDraft: React.Dispatch<React.SetStateAction<ScientificObservation>>;
  enabled: boolean;
  onOpenPantheraId: () => void;
  onOpenResearch: () => void;
};

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return <div className="edge-metric"><span>{label}</span><strong>{value}</strong>
    {detail && <small>{detail}</small>}</div>;
}
const percent = (number: number) => (number * 100).toFixed(1) + '%';
const mb = (bytes: number) => (bytes / 1024 / 1024).toFixed(3) + ' MB';

export default function EdgeOperations({ latestEdge, draft, setDraft, enabled, onOpenPantheraId, onOpenResearch }: Props) {
  const [event, setEvent] = React.useState<EdgeEvent | null>(null);
  const [eventSource, setEventSource] = React.useState<'none' | 'demo' | 'remote' | 'vigia'>('none');
  const [vigiaStatus, setVigiaStatus] = React.useState<VigiaStatus | null>(null);
  const [dashboardToken, setDashboardToken] = React.useState('');
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
  async function pollVigia() {
    if (!enabled) { setEventError('Se requiere conexión con FastAPI.'); return; }
    setPolling(true); setEventError(''); setNotice('');
    try {
      const statusResponse = await fetch('/api/edge/vigia/status', { cache: 'no-store' });
      if (!statusResponse.ok) throw new Error('No se pudo consultar el receptor VIGÍA.');
      const status = await statusResponse.json() as VigiaStatus;
      setVigiaStatus(status);
      if (!status.configured) { setEventError(status.message); return; }
      if (!status.received_count) { setEventError('Receptor activo, pero todavía no recibió fotografías de VIGÍA.'); return; }
      if (!dashboardToken.trim()) {
        setEventError('Ingresá la clave de consulta proporcionada por el operador para ver el evento.');
        return;
      }
      const response = await fetch('/api/edge/vigia/latest', {
        cache: 'no-store', headers: { 'X-Panthera-Dashboard-Token': dashboardToken },
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'No se autorizó la consulta del nodo.');
      if (!payload.event) { setEventError(payload.message || 'No hay eventos de VIGÍA.'); return; }
      setEvent(payload.event as EdgeEvent);
      setEventSource('vigia');
    } catch (cause) {
      setEventError(cause instanceof Error ? cause.message : 'Falló la consulta a VIGÍA.');
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
    setNotice('Identificador vinculado al borrador de Investigación. Las coordenadas y mediciones del nodo NO se copian automáticamente: verificá su procedencia.');
    onOpenResearch();
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
      <h2>PantheraEDGE · Conexión con VIGÍA</h2>
      <div className="edge-flow" aria-label="Arquitectura conceptual">
        {['VIGÍA · SD / ESP32', 'Wi-Fi / futura pasarela 5G', 'PantheraEDGE · Recepción', 'PantheraID · Detección', 'Monitoreo / Investigación'].map((step, index) =>
          <React.Fragment key={step}>{index > 0 && <span aria-hidden="true" className="edge-flow-arrow">→</span>}
            <div><small>ETAPA {index + 1}</small><strong>{step}</strong></div></React.Fragment>)}
      </div>
      <p className="scientific-note">VIGÍA en Wokwi simula cámara, PIR, microSD y subida Wi-Fi. No es una conexión 5G real. La recepción autenticada de fotografías requiere configurar el endpoint HTTPS y modificar el sketch o su pasarela; aún no hay integración física.</p>
    </section>

    <section className="panel edge-module edge-id-link">
      <h2>Análisis de imágenes: PantheraID</h2>
      <p>La detección de animales, sus gráficos y fotogramas se realizan únicamente en PantheraID. PantheraEDGE se ocupa de la conexión del nodo VIGÍA y de los eventos recibidos.</p>
      <div className="science-actions"><button type="button" onClick={onOpenPantheraId}>Abrir PantheraID</button></div>
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
      <h2>VIGÍA · Eventos del nodo de Manuel</h2>
      <p>PantheraEDGE recibe metadatos de capturas enviadas por VIGÍA. El sketch original usa Wi-Fi y todavía debe configurarse para utilizar un endpoint HTTPS autenticado. Los eventos no se guardan en Supabase ni ejecutan MegaDetector.</p>
      <div className="edge-vigia-connect">
        <p><strong>Estado del receptor:</strong> {vigiaStatus ? vigiaStatus.message : 'Sin comprobar'}</p>
        {vigiaStatus && <p className="science-hint">Configuración: {vigiaStatus.configured ? 'Receptor habilitado' : 'Pendiente'} · Eventos en memoria: {vigiaStatus.received_count} · No implica conexión 5G real.</p>}
        <label className="science-field" htmlFor="vigia-dashboard-token">
          <span>Clave de consulta del operador (no se guarda en el navegador)</span>
          <input id="vigia-dashboard-token" type="password" autoComplete="off"
            value={dashboardToken} onChange={event => setDashboardToken(event.target.value)}
            placeholder="Solo para eventos reales" />
        </label>
        <div className="science-actions">
          <button type="button" disabled={!enabled || polling} onClick={() => void pollVigia()}>
            {polling ? 'Consultando…' : 'Consultar receptor VIGÍA'}
          </button>
          <button type="button" onClick={simulate}>Simular evento (solo demo)</button>
          <button type="button" disabled={!enabled || polling} onClick={() => void pollRemote()}>
            Consultar puente JSON opcional
          </button>
        </div>
      </div>
      {eventError && <p role="alert" className="upload-error">{eventError}</p>}
      {event && <div className="edge-event-detail">
        <div className="edge-metrics-grid">
          <Metric label="Origen" value={eventSource === 'demo' ? 'DEMOSTRACIÓN' : eventSource === 'vigia' ? 'VIGÍA / MULTIPART' : 'PUENTE JSON'} />
          <Metric label="Estado" value={event.status || 'RECEIVED'} />
          <Metric label="Contrato" value={event.contract_version || 'No indicado'} />
          <Metric label="HMAC" value={event.hmac_status || 'NOT_CHECKED'} />
        </div>
        <dl>
          <dt>ID de evento</dt><dd>{event.event_id || 'No indicado'}</dd>
          <dt>Cámara/nodo</dt><dd>{event.camera_id || 'No indicado'}</dd>
          <dt>Hora UTC</dt><dd>{event.timestamp || 'No indicada'}</dd>
          <dt>Transporte</dt><dd>{event.transport || 'No indicado'}</dd>
          {event.filename && <><dt>Fotografía recibida</dt><dd>{event.filename} · {typeof event.size_bytes === 'number' ? mb(event.size_bytes) : 'Tamaño desconocido'}</dd></>}
          {eventSource === 'vigia' && <><dt>Autenticación del nodo</dt><dd>{event.auth_status || 'Sin especificar'}</dd>
            <dt>Inferencia automática</dt><dd>No; fotografía no guardada ni analizada</dd></>}
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
      <p className="scientific-note">El receptor VIGÍA requiere credenciales configuradas en FastAPI y cambios coordinados con Manuel. Los eventos simulados no provienen de sensores reales. El puente JSON previo sigue siendo opcional. No se realiza inferencia ni se almacena la fotografía al recibir el evento.</p>
    </section>

    <section className="panel edge-module">
      <h2>Pasarela 5G / 4G · Escenario de conectividad</h2>
      <div className="science-check"><input type="checkbox" checked={measured} onChange={event => setMeasured(event.target.checked)} />
        <span>Los valores de throughput y latencia fueron medidos externamente (testbed)</span></div>
      <p className="science-hint">Wokwi se conecta mediante Wi-Fi, no 5G. Los valores iniciales son supuestos; marcar la casilla no mide la red. Para 5G real se necesita un router/gateway y mediciones verificadas.</p>
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
      </> : <p>Analizá un video desde PantheraID para obtener tamaños JPEG comparables. Aquí se calculan tiempos estimados para una futura pasarela 5G/4G, no tráfico real del nodo.</p>}
    </section>
  </div>;
}
