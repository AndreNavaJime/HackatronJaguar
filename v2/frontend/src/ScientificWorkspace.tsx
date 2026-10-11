import React from 'react';

export type EdgeSummary = {
  source: 'video' | 'image';
  filename: string;
  model: string;
  sampled: number;
  retained: number;
  animals: number;
  persons: number;
  vehicles: number;
  max_confidence: number;
  note: string;
};
export type ScientificObservation = {
  observation_id: string; observation_name: string; observer: string;
  institution: string; project_code: string; protocol: string;
  camera_id: string; camera_model: string; study_site: string;
  deployed_at: string; retrieved_at: string; camera_trap_nights: number | null;
  event_datetime_utc: string; latitude: number | null; longitude: number | null;
  coordinate_provenance: string; altitude_m: number | null;
  temperature_c: number | null; humidity_percent: number | null;
  environmental_source: string; species: string; individual_id: string;
  identification_method: string; evidence_quality: string; validation_status: string;
  sex: string; age_class: string; viewpoint: string; behavior: string;
  habitat_type: string; notes: string; limitations: string;
  media_reference: string; edge_analysis: EdgeSummary | null;
};

export function emptyObservation(): ScientificObservation {
  return {
    observation_id: 'OBS-' + Date.now().toString(36).toUpperCase(),
    observation_name: '', observer: '', institution: '', project_code: '', protocol: '',
    camera_id: '', camera_model: '', study_site: '', deployed_at: '', retrieved_at: '',
    camera_trap_nights: null, event_datetime_utc: '', latitude: null, longitude: null,
    coordinate_provenance: 'sin_verificar', altitude_m: null,
    temperature_c: null, humidity_percent: null, environmental_source: '',
    species: '', individual_id: '', identification_method: 'pendiente',
    evidence_quality: 'sin_evaluar', validation_status: 'pendiente',
    sex: 'desconocido', age_class: 'desconocida', viewpoint: 'desconocido',
    behavior: '', habitat_type: '', notes: '', limitations: '', media_reference: '',
    edge_analysis: null,
  };
}
const textColumns: (keyof ScientificObservation)[] = [
  'observation_id', 'observation_name', 'observer', 'institution', 'project_code',
  'camera_id', 'study_site', 'species', 'individual_id', 'event_datetime_utc',
  'latitude', 'longitude', 'coordinate_provenance', 'camera_trap_nights',
  'temperature_c', 'humidity_percent', 'altitude_m', 'validation_status',
];
function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 5000);
}
function downloadJson(value: unknown, name: string) {
  saveBlob(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }), name);
}
function cell(value: unknown): string {
  if (value === null || value === undefined) return '';
  return typeof value === 'object' ? JSON.stringify(value) : String(value);
}
function csvText(records: ScientificObservation[]): string {
  const quote = (v: unknown) => '"' + cell(v).replace(/"/g, '""') + '"';
  return '\uFEFF' + [textColumns.join(','), ...records.map(record => textColumns.map(key => quote(record[key])).join(','))].join('\r\n');
}
function geoFeature(record: ScientificObservation) {
  const { latitude, longitude, ...properties } = record;
  const geometry = latitude === null || longitude === null
    ? null : { type: 'Point', coordinates: [longitude, latitude] };
  return { type: 'Feature', geometry, properties };
}
async function readError(response: Response): Promise<string> {
  try {
    const data: unknown = await response.json();
    if (typeof data === 'object' && data !== null && 'detail' in data) {
      const detail = data.detail;
      if (typeof detail === 'string') return detail;
      if (Array.isArray(detail)) return detail.map((part: { msg?: string }) => part.msg ?? 'Campo inválido').join(' · ');
    }
  } catch { /* An upstream proxy can return HTML. */ }
  return 'No se pudo completar la solicitud (HTTP ' + response.status + ').';
}
type Props = {
  view: 'PantheraEDGE' | 'Investigación';
  enabled: boolean;
  draft: ScientificObservation;
  setDraft: React.Dispatch<React.SetStateAction<ScientificObservation>>;
  records: ScientificObservation[];
  setRecords: React.Dispatch<React.SetStateAction<ScientificObservation[]>>;
  latestEdge: EdgeSummary | null;
};

export default function ScientificWorkspace({ view, enabled, draft, setDraft, records, setRecords, latestEdge }: Props) {
  const [saving, setSaving] = React.useState(false);
  const [feedback, setFeedback] = React.useState('');
  const [error, setError] = React.useState('');
  const [pdfBusy, setPdfBusy] = React.useState('');
  const [catalogue, setCatalogue] = React.useState<{
    sentinel_1: { count: number; items: { id: string; datetime: string; cloud_cover: number | null }[] };
    sentinel_2: { count: number; items: { id: string; datetime: string; cloud_cover: number | null }[] };
    note: string;
  } | null>(null);
  const [searching, setSearching] = React.useState(false);
  const [radius, setRadius] = React.useState(5);
  const [days, setDays] = React.useState(30);
  const [cloudCover, setCloudCover] = React.useState(40);

  function update<K extends keyof ScientificObservation>(name: K, value: ScientificObservation[K]) {
    setDraft(previous => ({ ...previous, [name]: value }));
    setFeedback('');
  }

  function field(label: string, name: keyof ScientificObservation, placeholder = '') {
    return <label className="science-field" key={name}>
      <span>{label}</span>
      <input value={String(draft[name] ?? '')} placeholder={placeholder} maxLength={300}
        onChange={event => update(name, event.target.value)} />
    </label>;
  }
  function numeric(label: string, name: 'latitude' | 'longitude' | 'altitude_m' |
    'temperature_c' | 'humidity_percent' | 'camera_trap_nights', min: number, max: number) {
    return <label className="science-field" key={name}>
      <span>{label}</span>
      <input type="number" step="any" min={min} max={max} value={draft[name] ?? ''}
        placeholder="Sin dato" onChange={event => update(name, event.target.value === '' ? null : Number(event.target.value))} />
    </label>;
  }
  function select(label: string, name: keyof ScientificObservation, values: [string, string][]) {
    return <label className="science-field" key={name}>
      <span>{label}</span>
      <select value={String(draft[name] ?? '')} onChange={event => update(name, event.target.value)}>
        {values.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
      </select>
    </label>;
  }
  function area(label: string, name: keyof ScientificObservation, hint: string) {
    return <label className="science-field science-field-wide" key={name}>
      <span>{label}</span>
      <textarea value={String(draft[name] ?? '')} maxLength={name === 'notes' ? 3000 : 1500}
        rows={3} placeholder={hint} onChange={event => update(name, event.target.value)} />
    </label>;
  }
  async function register(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFeedback('');
    setError('');
    if (!enabled) { setError('Para validar y registrar, iniciá FastAPI en el puerto 8000.'); return; }
    setSaving(true);
    try {
      const response = await fetch('/api/research/validate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(draft),
      });
      if (!response.ok) throw new Error(await readError(response));
      const payload = await response.json() as { observation: ScientificObservation };
      setRecords(previous => [...previous, payload.observation]);
      setDraft(emptyObservation());
      setFeedback('Observación validada en formato y agregada al registro temporal. Exportá una copia antes de cerrar.');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'No se pudo registrar la observación.');
    } finally { setSaving(false); }
  }
  async function pdf(record: ScientificObservation) {
    if (!enabled) { setError('El PDF requiere FastAPI conectado.'); return; }
    setError('');
    setPdfBusy(record.observation_id);
    try {
      const response = await fetch('/api/research/pdf', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(record),
      });
      if (!response.ok) throw new Error(await readError(response));
      saveBlob(await response.blob(), record.observation_id + '_PantheraEDGE.pdf');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'No se pudo generar el PDF.');
    } finally { setPdfBusy(''); }
  }
  async function queryCopernicus() {
    if (!enabled || draft.latitude === null || draft.longitude === null) {
      setError('Para consultar Sentinel, conectá FastAPI e indicá coordenadas reales de una estación.');
      return;
    }
    setSearching(true);
    setCatalogue(null);
    setError('');
    try {
      const params = new URLSearchParams({
        latitude: String(draft.latitude), longitude: String(draft.longitude),
        radius_km: String(radius), days_back: String(days), max_cloud_cover: String(cloudCover),
      });
      const response = await fetch('/api/research/copernicus?' + params, { cache: 'no-store' });
      if (!response.ok) throw new Error(await readError(response));
      setCatalogue(await response.json());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'No se pudo consultar Copernicus.');
    } finally { setSearching(false); }
  }

  const registry = <section className="science-registry" aria-label="Registro de observaciones científicas">
    <div className="panel-heading"><div><h3>Registro temporal de observaciones</h3>
      <p>Los registros se mantienen en memoria mientras la aplicación esté abierta. No se envían a Supabase.</p></div>
      <span className="tag">{records.length} REGISTROS</span></div>
    {!!records.length && <div className="science-actions">
      <button type="button" onClick={() => downloadJson(records, 'PantheraEDGE_registro.json')}>Descargar JSON</button>
      <button type="button" onClick={() => saveBlob(new Blob([csvText(records)], { type: 'text/csv;charset=utf-8' }), 'PantheraEDGE_registro.csv')}>Descargar CSV</button>
      <button type="button" onClick={() => downloadJson({
        type: 'FeatureCollection', features: records.map(geoFeature),
      }, 'PantheraEDGE_registro.geojson')}>Descargar GeoJSON</button>
    </div>}
    {!records.length ? <p>Aún no hay observaciones. Guardá una desde PantheraEDGE.</p> :
      <div className="science-records">{records.map((record, index) => <div className="science-record" key={record.observation_id + '-' + index}>
        <div><strong>{record.observation_name || record.observation_id}</strong>
          <small>{record.study_site || 'Sitio no indicado'} · {record.camera_id || 'Sin cámara'} · {record.species || 'Especie sin validar'}</small>
          <small>{record.validation_status} · {record.coordinate_provenance}</small></div>
        <div className="science-actions">
          <button type="button" onClick={() => void pdf(record)} disabled={pdfBusy !== ''}>
            {pdfBusy === record.observation_id ? 'Generando PDF…' : 'Informe PDF'}
          </button>
          <button type="button" onClick={() => downloadJson(geoFeature(record), record.observation_id + '.geojson')}>GeoJSON</button>
          <button type="button" onClick={() => setRecords(previous => previous.filter((_, i) => i !== index))}>Quitar</button>
        </div>
      </div>)}</div>}
  </section>;

  return <section className="panel science-workspace">
    <div className="panel-heading"><div>
      <h2>{view === 'Investigación' ? 'Investigación · Registro científico' : 'PantheraEDGE · Trabajo científico'}</h2>
      <p>Metadatos de campo, contexto satelital, trazabilidad científica e informes para cámaras trampa.</p>
    </div><span className="tag">CIENCIA · BETA</span></div>
    {view === 'PantheraEDGE' && <>
      <p className="scientific-note">Las especies y los individuos son anotaciones del investigador, no predicciones de MegaDetector.
        Dejá vacíos los valores ambientales que no se midieron; no se emplean coordenadas inventadas.</p>
      <form onSubmit={event => void register(event)}>
        <h3>1. Campaña y estación</h3>
        <div className="science-grid">
          {field('Nombre de observación', 'observation_name', 'Ej. Jaguar en sendero CT-07')}
          {field('Investigador / observador', 'observer')}
          {field('Institución / ONG', 'institution')}
          {field('Código del proyecto', 'project_code')}
          {field('ID de cámara', 'camera_id')}
          {field('Modelo de cámara', 'camera_model')}
          {field('Sitio de estudio', 'study_site')}
          {field('Instalación (AAAA-MM-DD)', 'deployed_at')}
          {field('Retiro (AAAA-MM-DD)', 'retrieved_at')}
          {numeric('Esfuerzo de muestreo (noches-cámara)', 'camera_trap_nights', 0, 100000)}
          {area('Protocolo de muestreo', 'protocol', 'Método, diseño, esfuerzo, frecuencia...')}
        </div>
        <h3>2. Observación y evidencia</h3>
        <div className="science-grid">
          {field('Fecha/hora del evento (UTC, ISO 8601)', 'event_datetime_utc', '2026-10-11T15:00:00Z')}
          {field('Especie anotada por investigador', 'species', 'Ej. Panthera onca')}
          {field('Individuo anotado', 'individual_id', 'Ej. JAG-003 / desconocido')}
          {select('Método de identificación', 'identification_method', [
            ['pendiente', 'Pendiente'], ['anotacion_visual', 'Anotación visual'],
            ['modelo_validado', 'Modelo externo validado'], ['otro', 'Otro']])}
          {select('Calidad de evidencia', 'evidence_quality', [
            ['sin_evaluar', 'Sin evaluar'], ['baja', 'Baja'], ['media', 'Media'], ['alta', 'Alta']])}
          {select('Validación científica', 'validation_status', [
            ['pendiente', 'Revisión pendiente'], ['validada_investigador', 'Validada por investigador'],
            ['verificada_campo', 'Verificada en campo'], ['rechazada', 'Rechazada']])}
          {select('Sexo', 'sex', [['desconocido', 'Desconocido'], ['hembra', 'Hembra'], ['macho', 'Macho'], ['indeterminado', 'Indeterminado']])}
          {select('Clase de edad', 'age_class', [['desconocida', 'Desconocida'], ['juvenil', 'Juvenil'], ['subadulto', 'Subadulto'], ['adulto', 'Adulto'], ['indeterminada', 'Indeterminada']])}
          {select('Ángulo de observación', 'viewpoint', [['desconocido', 'Desconocido'], ['izquierdo', 'Izquierdo'], ['derecho', 'Derecho'], ['frontal', 'Frontal'], ['posterior', 'Posterior'], ['otro', 'Otro']])}
          {field('Comportamiento', 'behavior')}
          {field('Tipo de hábitat', 'habitat_type')}
          {field('Referencia de foto/video', 'media_reference', 'Nombre de archivo o URL')}
          {area('Notas de campo', 'notes', 'Contexto, condiciones, observaciones...')}
          {area('Sesgos y limitaciones', 'limitations', 'Visibilidad, muestreo, identificación incierta...')}
        </div>
        <h3>3. Ubicación y ambiente</h3>
        <div className="science-grid">
          {numeric('Latitud WGS84', 'latitude', -90, 90)}
          {numeric('Longitud WGS84', 'longitude', -180, 180)}
          {select('Procedencia de coordenadas', 'coordinate_provenance', [
            ['sin_verificar', 'No verificadas'], ['gps', 'GPS'],
            ['estacion', 'Estación registrada'], ['investigador', 'Aportadas por investigador']])}
          {numeric('Altitud (m)', 'altitude_m', -500, 9000)}
          {numeric('Temperatura (°C)', 'temperature_c', -60, 70)}
          {numeric('Humedad relativa (%)', 'humidity_percent', 0, 100)}
          {field('Fuente de mediciones ambientales', 'environmental_source', 'Sensor, estación, ficha de campo...')}
        </div>
        <p className="science-hint">Sin fuente ambiental, dejá temperatura, humedad y altitud vacías. La ubicación corresponde a la cámara, no al animal.</p>
        <h3>4. Vincular análisis de MegaDetector</h3>
        {latestEdge ? <div className="science-edge-link">
          <p>Último análisis: <strong>{latestEdge.filename}</strong> · {latestEdge.model} · {latestEdge.animals} detecciones animales.</p>
          <label className="science-check">
            <input type="checkbox" checked={draft.edge_analysis !== null}
              onChange={event => update('edge_analysis', event.target.checked ? latestEdge : null)} />
            Vincular este resultado a la observación actual (solo si corresponde a la misma evidencia)
          </label>
          <small>Es un resumen temporal del análisis, no una identificación individual ni la transferencia del video.</small>
        </div> : <p>Analizá una fotografía o video en PantheraID para disponer de un resultado enlazable.</p>}
        <div className="science-actions">
          <button className="action-button" type="submit" disabled={saving || !enabled}>
            {saving ? 'Validando…' : 'Validar y agregar al registro'}
          </button>
        </div>
      </form>
      <section className="science-satellite">
        <h3>5. Copernicus / Sentinel · Contexto satelital</h3>
        <p>Consulta metadatos reales de adquisiciones Sentinel-1 y Sentinel-2, no calcula NDVI ni mide temperatura en la cámara.</p>
        <div className="science-grid">
          <label className="science-field"><span>Radio (km)</span><input type="number" min="1" max="50" value={radius} onChange={event => setRadius(Number(event.target.value))} /></label>
          <label className="science-field"><span>Días anteriores</span><input type="number" min="5" max="90" value={days} onChange={event => setDays(Number(event.target.value))} /></label>
          <label className="science-field"><span>Nubes máximas Sentinel-2 (%)</span><input type="number" min="0" max="100" value={cloudCover} onChange={event => setCloudCover(Number(event.target.value))} /></label>
        </div>
        <div className="science-actions">
          <button type="button" className="action-button" disabled={searching || !enabled}
            onClick={() => void queryCopernicus()}>{searching ? 'Consultando…' : 'Consultar catálogo Sentinel'}</button>
        </div>
        {catalogue && <div className="science-satellite-results">
          <div className="science-metrics"><span>Sentinel-1: <strong>{catalogue.sentinel_1.count}</strong></span>
            <span>Sentinel-2: <strong>{catalogue.sentinel_2.count}</strong></span></div>
          {[['Sentinel-1 SAR', catalogue.sentinel_1.items], ['Sentinel-2 óptico', catalogue.sentinel_2.items]].
            map(([title, items]) => <div key={String(title)}>
              <strong>{String(title)}</strong>
              {(items as typeof catalogue.sentinel_1.items).slice(0, 3).map(item =>
                <p key={item.id}>{item.datetime || 'Sin fecha'} · {item.id} {item.cloud_cover !== null ? '· nubes ' + item.cloud_cover + '%' : ''}</p>)}
            </div>)}
          <div className="science-actions"><button type="button"
            onClick={() => downloadJson(catalogue, 'PantheraEDGE_Sentinel_catalogo.json')}>Descargar metadatos JSON</button></div>
          <small>{catalogue.note}</small>
        </div>}
      </section>
    </>}
    {feedback && <p role="status" className="science-success">{feedback}</p>}
    {error && <p role="alert" className="upload-error">{error}</p>}
    {registry}
  </section>;
}
