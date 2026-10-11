import React from 'react';
import type { EdgeSummary, ScientificObservation } from './ScientificWorkspace';

type Props = {
  records: ScientificObservation[];
  latestEdge: EdgeSummary | null;
  onOpenResearch: () => void;
  onOpenEdge: () => void;
};

function BarTable({ data, title, explanation }: { data: Record<string, number>; title: string; explanation: string }) {
  const rows = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...rows.map(x => x[1]));
  return <div className="edge-chart">
    <h3>{title}</h3>
    {rows.length ? <div className="edge-bars">{rows.map(([label, count]) =>
      <div key={label} className="edge-bar-item"><span title={label}>{label}</span>
        <div className="edge-bar-track"><div style={{ width: count / max * 100 + '%' }}/></div><strong>{count}</strong>
      </div>)}</div> : <p>Sin registros por ahora.</p>}
    <small>{explanation}</small>
  </div>;
}
export default function MonitoringPanel({ records, latestEdge, onOpenResearch, onOpenEdge }: Props) {
  const validated = records.filter(r => r.validation_status === 'validada_investigador' || r.validation_status === 'verificada_campo');
  const uniqueCameras = new Set(records.map(r => r.camera_id).filter(Boolean)).size;
  const uniqueSites = new Set(records.map(r => r.study_site).filter(Boolean)).size;
  const geoCount = records.filter(r => r.latitude !== null && r.longitude !== null).length;
  const group = (field: 'camera_id' | 'species' | 'validation_status') => records.reduce<Record<string, number>>((acc, record) => {
    const value = (record[field] || 'Sin dato').trim();
    acc[value] = (acc[value] ?? 0) + 1;
    return acc;
  }, {});

  return <div className="monitoring-workspace">
    <section className="panel">
      <div className="panel-heading"><div><h2>PantheraMONITORING · Vista científica</h2>
        <p>Dashboard local con las observaciones registradas durante esta sesión de la PWA.</p></div>
        <span className="tag">SIN SUPABASE</span></div>
      <div className="edge-metrics-grid">
        {[['Registros', records.length], ['Revisados / validados', validated.length],
          ['Cámaras distintas', uniqueCameras], ['Sitios distintos', uniqueSites],
          ['Con ubicación', geoCount], ['Detecciones en último análisis', latestEdge?.animals ?? 0]].map(([label, value]) =>
          <div className="edge-metric" key={label}><span>{label}</span><strong>{value}</strong></div>)}
      </div>
      <p className="scientific-note">Estos son conteos de registros cargados en esta sesión, no estimaciones de abundancia, ocupación o precisión de IA. La vista no está conectada al dashboard externo ni a Supabase.</p>
    </section>
    <section className="panel">
      <h2>Distribución de registros</h2>
      <div className="edge-graphs">
        <BarTable data={group('camera_id')} title="Por cámara" explanation="Conteo de observaciones por cámara anotada." />
        <BarTable data={group('validation_status')} title="Por estado de validación" explanation="Estado marcado por el investigador en el formulario." />
        <BarTable data={group('species')} title="Por especie anotada" explanation="Incluye especies sin confirmación; no constituye clasificación automática." />
      </div>
    </section>
    <section className="panel">
      <h2>Últimas observaciones de investigación</h2>
      {records.length === 0 ? <p>El registro está vacío. Ingresá una observación desde PantheraEDGE y aparecerá en este panel.</p> :
        <div className="science-records">{records.slice(-10).reverse().map((record, i) =>
          <div className="science-record" key={record.observation_id + i}>
            <div><strong>{record.observation_name || record.observation_id}</strong>
              <small>{record.study_site || 'Sin sitio'} · {record.species || 'Sin especie'} · {record.camera_id || 'Sin cámara'}</small>
              <small>{record.event_datetime_utc || 'Fecha no registrada'} · {record.validation_status}</small></div>
          </div>)}</div>}
      <div className="science-actions">
        <button type="button" onClick={onOpenEdge}>Ir a PantheraEDGE</button>
        <button type="button" onClick={onOpenResearch}>Ver registro y exportaciones</button>
      </div>
      <p className="science-hint">Las salidas disponibles son PDF, JSON, CSV y GeoJSON para investigación y SIG. Envío automático al SINAC, avisos a guardaparques y almacenamiento permanente siguen pendientes de integración.</p>
    </section>
  </div>;
}
