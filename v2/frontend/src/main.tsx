import React from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const sections = ['Resumen', 'PantheraID', 'PantheraMONITORING', 'PantheraEDGE', 'Investigación'];
function App() {
  const [section, setSection] = React.useState('Resumen');
  return <div className="shell">
    <aside><div className="brand">🐆 PANTHERA<span>LAB</span></div><p className="sub">Conservación inteligente</p><nav aria-label="Navegación principal">{sections.map(s=><button key={s} className={section===s?'active':''} onClick={()=>setSection(s)}>{s}</button>)}</nav><small>PantheraID 2.0 · Vista preliminar</small></aside>
    <main><header><span>Plataforma científica de monitoreo</span><span className="tag">PROTOTIPO UI</span></header>
      <h1>{section}</h1><p className="lead">Sistema de apoyo para monitoreo de fauna y revisión científica de evidencia.</p>
      <div className="cards"><article><span>Identificación individual</span><strong>En migración</strong><p>Los modelos y la validación se integrarán desde el backend Python.</p></article><article><span>Eventos de campo</span><strong>Sin datos conectados</strong><p>Preparado para integrar PantheraEDGE y el nodo VIGÍA.</p></article><article><span>Revisión científica</span><strong>Pendiente</strong><p>Conservaremos cuadros de imágenes, métricas y exportaciones.</p></article></div>
      <section className="panel"><h2>{section} · Espacio de trabajo</h2><p>Esta pantalla es la primera base responsive. No procesa fotografías, videos ni eventos todavía; esas funciones permanecen en la aplicación Streamlit original hasta su migración y prueba.</p></section>
    </main>
  </div>
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
