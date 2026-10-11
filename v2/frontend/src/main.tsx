import React from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const sections = ['Resumen', 'PantheraID', 'PantheraMONITORING', 'PantheraEDGE', 'Investigación'];
type ApiState = 'checking' | 'connected' | 'disconnected';

function App() {
  const [section, setSection] = React.useState('Resumen');
  const [apiState, setApiState] = React.useState<ApiState>('checking');
  const [apiMessage, setApiMessage] = React.useState('Comprobando conexión con Python…');

  const checkApi = React.useCallback(async () => {
    setApiState('checking');
    setApiMessage('Comprobando conexión con Python…');
    try {
      // Same-origin path: Vite forwards /api requests to local FastAPI in Codespaces.
      const response = await fetch('/api/health', { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
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
      <section className={`api-status ${apiState}`} aria-live="polite" aria-label="Estado de la API">
        <div><span className="status-dot" aria-hidden="true"></span><strong>Conexión con backend</strong><p>{apiMessage}</p></div>
        <button type="button" onClick={() => void checkApi()} disabled={apiState === 'checking'}>Comprobar conexión</button>
      </section>
      <div className="cards">
        <article><span>Identificación individual</span><strong>En migración</strong><p>Los modelos y la validación se integrarán desde el backend Python.</p></article>
        <article><span>Eventos de campo</span><strong>Sin datos conectados</strong><p>Preparado para integrar PantheraEDGE y el nodo VIGÍA.</p></article>
        <article><span>Revisión científica</span><strong>Pendiente</strong><p>Conservaremos cuadros de imágenes, métricas y exportaciones.</p></article>
      </div>
      <section className="panel">
        <h2>{section} · Espacio de trabajo</h2>
        <p>Esta pantalla es una primera base responsive. Aunque el backend esté conectado, todavía no procesa fotografías, videos ni eventos. Esas funciones permanecen en Streamlit hasta su migración y validación.</p>
      </section>
    </main>
  </div>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
