/**
 * PantheraLAB 3.0 · Blue Edition
 * Diseño y desarrollo de la aplicación: Andrea Navarro Jiménez (2026).
 * Aviso de uso restringido sobre sus aportes originales: ../LICENSE-PANTHERALAB-3.0.md
 * Las bibliotecas y colaboraciones de terceros conservan sus propias licencias y créditos.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import './panthera3.css';
import DetectionPanel from './DetectionPanel';
import VideoPanel from './VideoPanel';
import LiteVideoPanel from './LiteVideoPanel';
import {createAnalysisId} from './videoWorkspaceDb';
import type {VideoEvidenceBatch} from './videoWorkspaceDb';
import type {VideoWorkflowState} from './LiteVideoPanel';
import ScientificWorkspace from './ScientificWorkspace';
import InstallControl from './InstallControl';
import { registerPantheraPwa } from './registerPwa';
import { LanguageProvider, useLanguage } from './language';

const sections = ['Resumen', 'PantheraID', 'PantheraMONITORING', 'PantheraEDGE', 'Investigación'];
const sectionSymbols: Record<string, string> = {
  Resumen: '◈', PantheraID: '◎', PantheraMONITORING: '▦', PantheraEDGE: '⌁', Investigación: '✦',
};
type ApiState = 'checking' | 'connected' | 'disconnected';
type ImageResult = {
  status: string;
  format: string;
  width: number;
  height: number;
  color_mode: string;
  size_bytes: number;
  sha256: string;
  saved: boolean;
  animal_detection: boolean;
  note: string;
};


/** Prepare a compact JPEG research preview; the original uploaded photo remains with the researcher. */
function photoPreviewJpeg(file:File):Promise<string>{
  return new Promise((resolve,reject)=>{
    if(!['image/jpeg','image/png','image/webp'].includes(file.type)){
      reject(new Error('Formato de fotografía no compatible.'));return;
    }
    const url=URL.createObjectURL(file);
    const picture=new Image();
    picture.onerror=()=>{URL.revokeObjectURL(url);reject(new Error('No se pudo preparar la fotografía.'));};
    picture.onload=()=>{
      URL.revokeObjectURL(url);
      try{
        const scale=Math.min(1,480/Math.max(picture.naturalWidth,picture.naturalHeight));
        const canvas=document.createElement('canvas');
        canvas.width=Math.max(1,Math.round(picture.naturalWidth*scale));
        canvas.height=Math.max(1,Math.round(picture.naturalHeight*scale));
        const ctx=canvas.getContext('2d');
        if(!ctx)throw new Error('El navegador no puede procesar esta imagen.');
        ctx.fillStyle='#ffffff';
        ctx.fillRect(0,0,canvas.width,canvas.height);
        ctx.drawImage(picture,0,0,canvas.width,canvas.height);
        let value='';
        for(const q of [.72,.57,.42,.30]){
          value=canvas.toDataURL('image/jpeg',q);
          if(value.length<72000)break;
        }
        if(value.length>=72000)throw new Error('No fue posible comprimir la imagen para el registro.');
        resolve(value);
      }catch(error){reject(error);}
    };
    picture.src=url;
  });
}

function App() {
  const { language, setLanguage, t } = useLanguage();
  const [section, setSection] = React.useState('Resumen');
  const [showCredits,setShowCredits]=React.useState(false);
  React.useEffect(()=>{
    if(!showCredits)return;
    const escape=(event:KeyboardEvent)=>{if(event.key==='Escape')setShowCredits(false);};
    window.addEventListener('keydown',escape);
    return ()=>window.removeEventListener('keydown',escape);
  },[showCredits]);
  const [apiState, setApiState] = React.useState<ApiState>('checking');
  const [aiAvailable, setAiAvailable] = React.useState(false);
  const [liteAvailable, setLiteAvailable] = React.useState(false);
  const [apiMessage, setApiMessage] = React.useState('Verificando disponibilidad del servicio…');
  const [selectedImage, setSelectedImage] = React.useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = React.useState<string | null>(null);
  const [imageResult, setImageResult] = React.useState<ImageResult | null>(null);
  const [imageError, setImageError] = React.useState('');
  const [uploading, setUploading] = React.useState(false);
  const [preparingEvidence,setPreparingEvidence]=React.useState(false);
  const [imageEvidenceId,setImageEvidenceId]=React.useState('');
  const [evidenceDraft,setEvidenceDraft]=React.useState<VideoEvidenceBatch|null>(null);
  const [videoWorkflow,setVideoWorkflow]=React.useState<VideoWorkflowState>({hasResult:false,selectedCount:0});
  const [registryTab,setRegistryTab]=React.useState<'projects'|'stations'|'captures'|'individuals'|'reports'>('projects');
  const [videoNextRequest,setVideoNextRequest]=React.useState(0);
  const [monitorNextRequest,setMonitorNextRequest]=React.useState(0);
  const [reportRequest,setReportRequest]=React.useState(0);
  const onVideoWorkflow=React.useCallback((next:VideoWorkflowState)=>{
    setVideoWorkflow(prev=>prev.hasResult===next.hasResult&&prev.selectedCount===next.selectedCount?prev:next);
  },[]);

  const checkApi = React.useCallback(async () => {
    setApiState('checking');
    setApiMessage('Verificando disponibilidad del servicio…');
    try {
      const response = await fetch('/api/health', { cache: 'no-store' });
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const data: unknown = await response.json();
      if (typeof data !== 'object' || data === null || !('status' in data) || data.status !== 'ok') {
        throw new Error('Respuesta inesperada del servidor');
      }
      setApiState('connected');
      setApiMessage('Servicio de análisis operativo');
      try {
        const caps=await fetch('/api/capabilities',{cache:'no-store'});
        const data:unknown=await caps.json();
        setAiAvailable(caps.ok && typeof data==='object' && data!==null
          && 'animal_detection' in data && data.animal_detection==='optional_dependencies_installed');
        setLiteAvailable(caps.ok && typeof data==='object' && data!==null
          && 'video_lightweight' in data && data.video_lightweight==='available');
      } catch { setAiAvailable(false); setLiteAvailable(false); }
    } catch {
      setLiteAvailable(false);
      setAiAvailable(false);
      setApiState('disconnected');
      setApiMessage('No se pudo establecer conexión con el servicio. Volvé a intentar en unos minutos.');
    }
  }, []);

  React.useEffect(() => { void checkApi(); }, [checkApi]);
  React.useEffect(() => {
    if (!selectedImage) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(selectedImage);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [selectedImage]);

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    setSelectedImage(file);
    setImageResult(null);
    setImageEvidenceId('');
    setImageError('');
  }

  async function inspectImage() {
    if (!selectedImage) return;
    if (selectedImage.size > 12 * 1024 * 1024) {
      setImageError(t('El tamaño máximo permitido es de 12 MB.'));
      return;
    }
    setUploading(true);
    setImageError('');
    setImageResult(null);
    try {
      const response = await fetch('/api/images/inspect', {
        method: 'POST',
        headers: { 'Content-Type': selectedImage.type || 'application/octet-stream' },
        body: selectedImage,
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(typeof payload.detail === 'string' ? payload.detail : t('Error al leer la imagen.'));
      }
      setImageResult(payload as ImageResult);
      setImageEvidenceId(createAnalysisId());
    } catch (err) {
      setImageError(err instanceof Error ? err.message : t('No se pudo enviar la imagen.'));
    } finally {
      setUploading(false);
    }
  }


  async function continueWithPhoto(){
    if(!selectedImage||!imageResult||uploading||preparingEvidence)return;
    setPreparingEvidence(true);setImageError('');
    try{
      const jpg=await photoPreviewJpeg(selectedImage);
      const draft:VideoEvidenceBatch={
        sourceType:'image',sourceSha256:imageResult.sha256,
        analysisId:imageEvidenceId||createAnalysisId(),jobId:'',fileName:selectedImage.name,
        sampleSeconds:0,motionThreshold:0,totalSamples:1,durationSeconds:0,
        frames:[{sample:1,timeSeconds:0,motionScore:0,frameDataUrl:jpg}],
      };
      setEvidenceDraft(draft);
      setSection('PantheraMONITORING');
    }catch(error){
      setImageError(error instanceof Error?error.message:String(error));
    }finally{setPreparingEvidence(false);}
  }

  const workflowLabel=(()=>{
    const en=language==='en';
    if(section==='Resumen')return en?'Next: analyze evidence':'Siguiente: analizar evidencia';
    if(section==='PantheraID'){
      if(videoWorkflow.hasResult&&videoWorkflow.selectedCount>0)
        return en?'Next: record capture':'Siguiente: registrar captura';
      if(videoWorkflow.hasResult)return en?'Next: review frames':'Siguiente: revisar fotogramas';
      if(imageResult)return en?'Next: record observation':'Siguiente: registrar observación';
      return en?'Next: upload evidence':'Siguiente: cargar evidencia';
    }
    if(section==='PantheraMONITORING'){
      const labels:{[key:string]:[string,string]}={
        projects:['Siguiente: configurar estaciones','Next: configure stations'],
        stations:['Siguiente: registrar capturas','Next: record captures'],
        captures:['Siguiente: identificar individuos','Next: identify individuals'],
        individuals:['Siguiente: informe del estudio','Next: study report'],
        reports:['Siguiente: investigación','Next: research'],
      };
      const entry=labels[registryTab]||labels.projects;
      return en?entry[1]:entry[0];
    }
    if(section==='PantheraEDGE')return en?'Next: explore research':'Siguiente: explorar investigación';
    return en?'Next: consolidated report':'Siguiente: informe integral';
  })();
  function advanceWorkflow(){
    if(section==='Resumen'){setSection('PantheraID');return;}
    if(section==='PantheraID'){
      if(videoWorkflow.hasResult){setVideoNextRequest(n=>n+1);return;}
      if(imageResult){void continueWithPhoto();return;}
      document.getElementById(selectedImage?'panthera-image':'lite-video')
        ?.scrollIntoView({behavior:'smooth',block:'center'});
      return;
    }
    if(section==='PantheraMONITORING'){setMonitorNextRequest(n=>n+1);return;}
    if(section==='PantheraEDGE'){setSection('Investigación');return;}
    setReportRequest(n=>n+1);
  }

  return <div className="shell">
    <aside>
      <div className="brand">
        <img className="brand-symbol" src="/icons/pantheralab-3-192.png" alt="" />
        <span className="brand-copy"><strong>PANTHERA<span>LAB</span></strong><small>BLUE EDITION · 3.0</small></span>
      </div>
      <p className="sub">{t('Conservación inteligente')}</p>
      <p className="sidebar-label">{t('CENTRO DE CONTROL')}</p>
      <nav aria-label="Navegación principal">
        {sections.map(s => <button type="button" key={s} className={section===s?'active':''} aria-current={section===s?'page':undefined}
          onClick={() => setSection(s)}>
          <span className="nav-symbol" aria-hidden="true">{sectionSymbols[s]}</span><span className="nav-text">{t(s)}</span>
          <span className="nav-arrow" aria-hidden="true">↗</span>
        </button>)}
      </nav>
      <div className={'sidebar-connection '+apiState}>
        <span className="sidebar-connection-dot" aria-hidden="true" />
        <div><strong>Panthera API</strong><small>{t(apiState==='connected'?'En línea':apiState==='checking'?'Verificando…':'Sin conexión')}</small></div>
      </div>
      <small className="sidebar-footer">PANTHERALAB / V3.0
        <span>{language==='en'?'Application design and development':'Diseño y desarrollo de la aplicación'}</span>
        <strong>Andrea Navarro Jiménez</strong>
        <span>© 2026 · {language==='en'?'Rights reserved on original contributions':'Derechos reservados sobre aportes originales'}</span>
      </small>
    </aside>
    <main>
      <header className="app-header">
        <span className="header-location"><span className="header-location-mark" aria-hidden="true">◉</span> PANTHERALAB 3.0 <span className="header-divider">/</span> {t(section).toUpperCase()}</span>
        <div className="app-header-actions"><span className="top-status">● {t('SISTEMA CIENTÍFICO')}</span>
          <div className="language-switch" role="group" aria-label="Idioma / Language">
            <button type="button" onClick={() => setLanguage('es')} aria-pressed={language==='es'} className={language==='es'?'selected':''}>ES</button>
            <button type="button" onClick={() => setLanguage('en')} aria-pressed={language==='en'} className={language==='en'?'selected':''}>EN</button>
          </div>
          <button type="button" className="panthera3-credits-trigger"
            onClick={()=>setShowCredits(true)}
            aria-haspopup="dialog">{language==='en'?'About · Credits':'Acerca de · Créditos'}</button>
          <InstallControl /></div>
      </header>
      <section className="hero-stage panthera3-hero" aria-label="Introducción a PantheraLAB 3.0">
        <div className="hero-copy">
          <p className="hero-eyebrow"><span className="hero-eyebrow-line" /> {t('OBSERVAR · ANALIZAR · CONSERVAR')}</p>
          <span className="panthera3-version">◈ PANTHERALAB 3.0 · BLUE EDITION</span>
          <h1>{t(section==='Resumen'?'Inteligencia para la vida silvestre':section)}</h1>
          <p className="panthera3-tagline">De la intuición a la evidencia</p>
          <p className="lead">{t('Tecnología aplicada a cámaras trampa, evidencia científica y monitoreo de fauna.')}</p>
          <div className="hero-chips"><span>◆ PANTHERAID 3.0</span><span>◈ {t('INVESTIGACIÓN')}</span><span>◉ COSTA RICA</span></div>
        </div>
        <div className="panthera3-poster">
          <img src="/branding/pantheralab-3-original.webp"
            alt="PantheraLAB: rostro de jaguar mitad natural en dorado y mitad circuitos digitales azules. De la intuición a la evidencia."
            fetchPriority="high" />
        </div>
      </section>
      <section className={'api-status ' + apiState} aria-live="polite" aria-label="Estado de la API">
        <div><span className="status-dot" aria-hidden="true"></span><strong>{t("Estado del servicio")}</strong><p>{t(apiMessage)}</p></div>
        <button type="button" onClick={() => void checkApi()} disabled={apiState === 'checking'}>{t("Actualizar estado")}</button>
      </section>
      <section className="panel upload-panel" style={{display:section==='PantheraID'?undefined:'none'}}>
        <div className="panel-heading">
          <div><h2>{t("PantheraID · Multimedia de cámaras trampa")}</h2><p>{t("Organización de evidencia multimedia y análisis exploratorio de cámaras trampa.")}</p></div>
          <span className="tag">{t("IMAGEN + VIDEO")}</span>
        </div>
        <div className="upload-layout">
          <div className="upload-controls">
            <label htmlFor="panthera-image">{t("Seleccionar fotografía (JPEG, PNG o WebP; máximo 12 MB)")}</label>
            <input id="panthera-image" type="file" accept="image/jpeg,image/png,image/webp" onChange={handleFileChange} />
            <button className="action-button" disabled={!selectedImage || uploading || apiState !== 'connected'} onClick={() => void inspectImage()}>
              {t(uploading ? 'Enviando…' : 'Inspeccionar fotografía')}
            </button>
            {imageError && <p role="alert" className="upload-error">{imageError}</p>}
            {imageResult && <div className="image-result" role="status">
              <strong>✓ {t('Fotografía verificada')}</strong>
              <dl><dt>{t("Formato")}</dt><dd>{imageResult.format}</dd><dt>{t("Dimensiones")}</dt><dd>{imageResult.width} × {imageResult.height} px</dd><dt>{t("Tamaño")}</dt><dd>{(imageResult.size_bytes / 1024 / 1024).toFixed(2)} MB</dd><dt>{t("Almacenada")}</dt><dd>{t("No")}</dd></dl>
              <p>{language==='en'?'File validation completed. Species identification was not performed.':'Validación del archivo completada. No se ha realizado identificación de especies.'}</p>
              <p className="sci-muted">{language==='en'
                ?'Use Next in the bottom bar to register this photo as one capture awaiting scientific review.'
                :'Usá Siguiente en la barra inferior para registrar esta fotografía como una captura pendiente de revisión científica.'}</p>
            </div>}
          </div>
          <div className="image-frame">
            {previewUrl ? <img src={previewUrl} alt={t('Vista previa de la fotografía seleccionada')} /> : <div className="empty-preview">{t("Aquí aparecerá la fotografía seleccionada")}</div>}
            {selectedImage && <small>{selectedImage.name}</small>}
          </div>
        </div>
        <LiteVideoPanel enabled={apiState === 'connected' && liteAvailable}
          onWorkflowState={onVideoWorkflow} nextRequest={videoNextRequest}
          onRecordEvidence={item=>{setEvidenceDraft(item);setSection('PantheraMONITORING');}} />
        <details className="method-details ai-method-details">
          <summary>{language==='en'?'Automatic detection · MegaDetector V6':'Detección automática · MegaDetector V6'}
            <span className="method-status">{aiAvailable
              ? (language==='en'?'Available for testing':'Disponible para pruebas')
              : (language==='en'?'Not enabled':'No habilitado')}</span>
          </summary>
          <p>{aiAvailable
            ? (language==='en'?'The model dependencies are present. Its inference capacity must still be validated in this environment.':'Las dependencias del modelo están presentes. Su capacidad de inferencia aún requiere verificación en este entorno.')
            : (language==='en'?'Automated detection requires additional model dependencies and processing resources. The sequence analysis above remains available using OpenCV.':'La detección automática requiere dependencias y capacidad de procesamiento adicionales. El análisis de secuencias anterior está disponible con OpenCV.')}</p>
        </details>
        {aiAvailable && <VideoPanel enabled={apiState === 'connected'} />}
        {aiAvailable && <DetectionPanel file={selectedImage} enabled={apiState === 'connected' && !uploading} />}
        <details className="method-details method-details-compact">
          <summary>{language==='en'?'Evidence management and data retention':'Gestión de evidencia y conservación de datos'}</summary>
          <p>{language==='en'?'Image inspection does not perform species recognition or save images to Supabase. Video analysis uses temporary files that expire on the processing server. Biological identification requires independent scientific review.':'La inspección de fotografías no reconoce especies ni guarda imágenes en Supabase. El análisis de video utiliza archivos temporales que caducan en el servidor de procesamiento. La identificación biológica exige revisión científica independiente.'}</p>
        </details>
      </section>
      <ScientificWorkspace section={section} onNavigate={setSection}
        pendingEvidence={evidenceDraft} onClearEvidence={()=>setEvidenceDraft(null)}
        monitoringNextRequest={monitorNextRequest} onRegistryTabChange={setRegistryTab}
        requestReport={reportRequest} />
      <footer className="panthera3-main-credits">
        <span>© 2026 · {language==='en'?'Application design and development':'Diseño y desarrollo de la aplicación'}: <strong>Andrea Navarro Jiménez</strong></span>
        <button type="button" onClick={()=>setShowCredits(true)}>
          {language==='en'?'Credits and usage terms':'Créditos y condiciones de uso'}
        </button>
      </footer>
      {showCredits&&<div className="panthera3-credits-overlay" role="presentation"
        onClick={()=>setShowCredits(false)}>
        <section className="panthera3-credits-dialog" role="dialog" aria-modal="true"
          aria-labelledby="panthera3-credits-title" onClick={event=>event.stopPropagation()}>
          <div className="panthera3-credits-heading">
            <span className="panthera3-credits-kicker">PANTHERALAB 3.0 · BLUE EDITION</span>
            <button type="button" onClick={()=>setShowCredits(false)}
              aria-label={language==='en'?'Close credits':'Cerrar créditos'}>✕</button>
          </div>
          <h2 id="panthera3-credits-title">{language==='en'?'Credits and authorship':'Créditos y autoría'}</h2>
          <p className="panthera3-credits-role">
            {language==='en'?'Application design and development':'Diseño y desarrollo de la aplicación'}
          </p>
          <p className="panthera3-credits-name">Andrea Navarro Jiménez</p>
          <p className="panthera3-credits-slogan">De la intuición a la evidencia</p>
          <p>{language==='en'
            ?'© 2026. Rights reserved on original contributions attributed to Andrea Navarro Jiménez. Delivery for private evaluation does not authorize redistribution, commercial reuse or presentation as someone else’s work.'
            :'© 2026. Derechos reservados sobre los aportes originales de Andrea Navarro Jiménez. Entregar una copia para evaluación privada no autoriza su redistribución, reutilización comercial ni presentarla como trabajo propio.'}</p>
          <p>{language==='en'
            ?'Third-party libraries, models, images and contributions retain their own copyrights and applicable licenses. The ownership of all components has not been independently certified.'
            :'Las bibliotecas, modelos, imágenes y contribuciones de otras personas conservan sus derechos y licencias aplicables. No se ha certificado independientemente la titularidad de todos los componentes.'}</p>
          <a className="panthera3-credits-legal" target="_blank" rel="noopener noreferrer"
            href="/AVISO-LEGAL-PANTHERALAB-3.0.txt">
            {language==='en'?'Read authorship and license notice ↗':'Leer aviso de autoría y licencia ↗'}
          </a>
          <button type="button" className="panthera3-credits-close"
            onClick={()=>setShowCredits(false)}>{language==='en'?'Close':'Cerrar'}</button>
        </section>
      </div>}
      {/* One primary Next control for every module, including completed video and image analyses. */}
      <div className="workflow-global-dock" role="region"
        aria-label={language==='en'?'Research workflow navigation':'Navegación del proceso científico'}>
        <div className="workflow-global-copy">
          <span>{language==='en'?'SCIENTIFIC WORKFLOW':'FLUJO CIENTÍFICO'}</span>
          <strong>{section==='PantheraID'
            ?language==='en'?'Multimedia analysis':'Análisis multimedia'
            :t(section)}</strong>
        </div>
        <button type="button" className="workflow-next-button workflow-global-next"
          disabled={section==='PantheraID'&&preparingEvidence}
          onClick={advanceWorkflow}>
          <span>{workflowLabel}</span><span aria-hidden="true">→</span>
        </button>
      </div>
    </main>
  </div>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><LanguageProvider><App /></LanguageProvider></React.StrictMode>);
registerPantheraPwa();
