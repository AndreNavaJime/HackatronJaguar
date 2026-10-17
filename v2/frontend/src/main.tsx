import React from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import DetectionPanel from './DetectionPanel';
import VideoPanel from './VideoPanel';
import LiteVideoPanel from './LiteVideoPanel';
import {createAnalysisId} from './videoWorkspaceDb';
import type {VideoEvidenceBatch} from './videoWorkspaceDb';
import type {VideoWorkflowState} from './LiteVideoPanel';
import ScientificWorkspace from './ScientificWorkspace';
import PantheraRosettesPanel from './PantheraRosettesPanel';
import InstallControl from './InstallControl';
import { registerPantheraPwa } from './registerPwa';
import { LanguageProvider, useLanguage } from './language';

// Keep the PantheraID section identifier to avoid breaking existing research workflows.
const sections = ['Resumen', 'PantheraID', 'PantheraMONITORING', 'PantheraLIVE', 'PantheraSENSE', 'PantheraSAT', 'PantheraFIRE'];
function ModuleIcon({section}:{section:string}){
  const paths:Record<string,React.ReactNode>={
    Resumen:<><rect x="3.5" y="3.5" width="17" height="17" rx="4"/><path d="M8 12h8M12 8v8"/></>,
    PantheraID:<><path d="M4 9V6a2 2 0 0 1 2-2h3M15 4h3a2 2 0 0 1 2 2v3M20 15v3a2 2 0 0 1-2 2h-3M9 20H6a2 2 0 0 1-2-2v-3"/><circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r=".65" fill="currentColor" stroke="none"/></>,
    PantheraMONITORING:<><rect x="3" y="3" width="18" height="18" rx="3"/><path d="M9 3v18M15 3v18M3 9h18M3 15h18"/></>,
    PantheraLIVE:<path d="m13 2-9 11h7l-1 9 10-12h-7l0-8Z"/>,
    PantheraSENSE:<><path d="M10 14.5V5a2 2 0 0 1 4 0v9.5a4.5 4.5 0 1 1-4 0Z"/><path d="M12 9v9"/></>,
    PantheraSAT:<><path d="m8 16-4 4m9-9 2-2M4 14l6 6M14 4l6 6"/><rect x="8.5" y="8.5" width="7" height="7" rx="1" transform="rotate(45 12 12)"/><path d="M3 3c3 0 5 2 5 5M16 16c0 3 2 5 5 5"/></>,
    PantheraFIRE:<path d="M12 22c4.5 0 7-3 7-7 0-3.3-2-5.8-4-7-.1 3-1.8 4.4-2.5 4.5C13 8 11 5 8 2c.5 4-3 6.8-3 12.5C5 19 7.8 22 12 22Zm0-2c-2 0-3-1.3-3-3 0-1.8 1.4-3 2.5-4 .2 1.5 1.3 2.4 2.5 3.2.7.5 1 1.1 1 1.8 0 1.2-1.1 2-3 2Z"/>
  };
  return <svg className="nav-icon-svg" viewBox="0 0 24 24" width="18" height="18"
    fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round"
    strokeLinejoin="round" focusable="false" aria-hidden="true">{paths[section]}</svg>;
}
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
  const moduleLabel=(name:string)=>name==='PantheraID'?'PantheraSCAN':t(name);
  const [section, setSection] = React.useState('Resumen');
  const [showCredits,setShowCredits]=React.useState(false);
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
        reports:['Siguiente: PantheraLIVE','Next: PantheraLIVE'],
      };
      const entry=labels[registryTab]||labels.projects;
      return en?entry[1]:entry[0];
    }
    if(section==='PantheraLIVE')return en?'Next: environmental sensors':'Siguiente: sensores ambientales';
    if(section==='PantheraSENSE')return en?'Next: explore satellite tools':'Siguiente: explorar satélites';
    if(section==='PantheraSAT')return en?'Next: review environmental alerts':'Siguiente: revisar alertas ambientales';
    return en?'Next: consolidated report':'Siguiente: informe integral';
  })();
  function advanceWorkflow(){
    if(section==='Resumen'){setSection('PantheraID');return;}
    if(section==='PantheraID'){
      if(videoWorkflow.hasResult){setVideoNextRequest(n=>n+1);return;}
      if(imageResult){void continueWithPhoto();return;}
      if(selectedImage)document.getElementById('panthera-photo-details')?.setAttribute('open','');
      document.getElementById(selectedImage?'panthera-image':'lite-video')
        ?.scrollIntoView({behavior:'smooth',block:'center'});
      return;
    }
    if(section==='PantheraMONITORING'){setMonitorNextRequest(n=>n+1);return;}
    if(section==='PantheraLIVE'){setSection('PantheraSENSE');return;}
    if(section==='PantheraSENSE'){setSection('PantheraSAT');return;}
    if(section==='PantheraSAT'){setSection('PantheraFIRE');return;}
    setSection('Resumen');
  }

  return <div className="shell">
    <aside>
      <div className="brand">
        <img className="brand-symbol" src="/icons/jaguar-modern-512.png" alt="" />
        <span className="brand-copy"><strong>PANTHERA<span>LAB</span></strong><small>WILDLIFE INTELLIGENCE</small></span>
      </div>
      <p className="sub">{t('Conservación inteligente')}</p>
      <p className="sidebar-label">{t('CENTRO DE CONTROL')}</p>
      <nav aria-label="Navegación principal">
        {sections.map(s => <button type="button" key={s} className={(section===s?'active':'')+(s==='PantheraFIRE'?' nav-pantherafire':'')} aria-current={section===s?'page':undefined}
          onClick={() => setSection(s)}>
          <span className="nav-symbol" aria-hidden="true"><ModuleIcon section={s}/></span><span className="nav-text">{moduleLabel(s)}</span>
          <span className="nav-arrow" aria-hidden="true">↗</span>
        </button>)}
      </nav>
      <div className={'sidebar-connection '+apiState}>
        <span className="sidebar-connection-dot" aria-hidden="true" />
        <div><strong>Panthera API</strong><small>{t(apiState==='connected'?'En línea':apiState==='checking'?'Verificando…':'Sin conexión')}</small></div>
      </div>
      <small className="sidebar-footer">PANTHERALAB / V2.0<br />{language==='en'?'SCIENTIFIC MONITORING':'MONITOREO CIENTÍFICO'}</small>
    </aside>
    <main>
      <header className="app-header">
        <span className="header-location"><span className="header-location-mark" aria-hidden="true">◉</span> PANTHERALAB <span className="header-divider">/</span> {moduleLabel(section).toUpperCase()}</span>
        <div className="app-header-actions"><span className="top-status">● {t('SISTEMA CIENTÍFICO')}</span>
          <div className="language-switch" role="group" aria-label="Idioma / Language">
            <button type="button" onClick={() => setLanguage('es')} aria-pressed={language==='es'} className={language==='es'?'selected':''}>ES</button>
            <button type="button" onClick={() => setLanguage('en')} aria-pressed={language==='en'} className={language==='en'?'selected':''}>EN</button>
          </div>
          <InstallControl /></div>
      </header>
      <section className="hero-stage" aria-label="Introducción a PantheraLAB">
        <div className="hero-copy">
          <p className="hero-eyebrow"><span className="hero-eyebrow-line" /> {t('OBSERVAR · ANALIZAR · CONSERVAR')}</p>
          <h1>{section==='Resumen'?t('Inteligencia para la vida silvestre'):moduleLabel(section)}</h1>
          <p className="lead">{t('Tecnología aplicada a cámaras trampa, evidencia científica y monitoreo de fauna.')}</p>
          <div className="hero-chips"><span>◆ PANTHERASCAN / PANTHERALAB</span><span>◈ {t('INVESTIGACIÓN')}</span><span>◉ COSTA RICA</span></div>
        </div>
        <div className="hero-orbit" aria-hidden="true">
          <div className="hero-orbit-outer" />
          <div className="hero-orbit-inner"><img src="/icons/jaguar-modern-512.png" alt="" /></div>
          <span className="orbit-code orbit-code-top">FIELD DATA · 01</span>
          <span className="orbit-code orbit-code-bottom">WILDLIFE / INTELLIGENCE</span>
        </div>
      </section>
      <section className={'api-status ' + apiState} aria-live="polite" aria-label="Estado de la API">
        <div><span className="status-dot" aria-hidden="true"></span><strong>{t("Estado del servicio")}</strong><p>{t(apiMessage)}</p></div>
        <button type="button" onClick={() => void checkApi()} disabled={apiState === 'checking'}>{t("Actualizar estado")}</button>
      </section>
      <section className="panel upload-panel" style={{display:section==='PantheraID'?undefined:'none'}}>
        <div className="panel-heading">
          <div><h2>PantheraSCAN · {language==='en'?'Wildlife evidence screening':'Exploración de evidencia de fauna'}</h2>
            <p>{language==='en'
              ?'Review camera-trap videos, screen frames and prepare evidence for researchers. Animal detection requires an AI-enabled server.'
              :'Revisá videos de cámaras trampa, seleccioná fotogramas y prepará evidencia. La detección automática requiere un servidor con IA activa.'}</p></div>
          <span className="tag">{language==='en'?'VIDEO + PHOTO':'VIDEO + FOTO'}</span>
        </div>
        <div className="scan-module-links">
          <a href="https://colab.research.google.com/github/AndreNavaJime/HackatronJaguar/blob/pantherasense-integration/notebooks/PantheraLAB_IA_Real_Colab.ipynb"
            target="_blank" rel="noopener noreferrer">{language==='en'?'Try experimental AI in Colab ↗':'Probar IA experimental en Colab ↗'}</a>
          <button type="button" onClick={()=>setSection('PantheraMONITORING')}>
            {language==='en'?'Review Colab results in MONITORING →':'Revisar resultados de Colab en MONITORING →'}
          </button>
        </div>
        <LiteVideoPanel enabled={apiState === 'connected' && liteAvailable}
          onWorkflowState={onVideoWorkflow} nextRequest={videoNextRequest}
          onRecordEvidence={item=>{setEvidenceDraft(item);setSection('PantheraMONITORING');}} />
        <details id="panthera-photo-details" className="method-details scan-photo-details">
          <summary>{language==='en'?'Photograph: automatic AI analysis and file check':'Fotografía: análisis automático y validación del archivo'}</summary>
          <p className="sci-muted">{language==='en'
            ?'Selecting a photo automatically explores its texture on Render. Wildlife detection additionally requires an enabled AI model; file validation is optional.'
            :'Al seleccionar una foto se explora automáticamente su textura en Render. Con un modelo IA habilitado también se detecta fauna; la validación del archivo es opcional.'}</p>
        <div className="upload-layout">
          <div className="upload-controls">
            <label htmlFor="panthera-image">{t("Seleccionar fotografía (JPEG, PNG o WebP; máximo 12 MB)")}</label>
            <input id="panthera-image" type="file" accept="image/jpeg,image/png,image/webp" onChange={handleFileChange} />
            <button className="action-button" disabled={!selectedImage || uploading || apiState !== 'connected'} onClick={() => void inspectImage()}>
              {uploading?(language==='en'?'Validating…':'Validando…'):(language==='en'?'Validate photo file (no AI)':'Validar archivo de foto (sin IA)')}
            </button>
            {imageError && <p role="alert" className="upload-error">{imageError}</p>}
            {imageResult && <div className="image-result" role="status">
              <strong>✓ {language==='en'?'File validated — no animal analysis':'Archivo validado — sin análisis de fauna'}</strong>
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
        {selectedImage && <DetectionPanel file={selectedImage}
          enabled={apiState === 'connected' && !uploading} />}
        {selectedImage && !aiAvailable && <p className="sci-muted" role="status">
          {language==='en'
            ? 'Render runs lightweight texture exploration only; animal/species detection requires a separately enabled AI model.'
            : 'Render ejecuta únicamente una exploración ligera de texturas; la detección de animales o especies requiere activar un modelo de IA por separado.'}
        </p>}
        </details>
        <PantheraRosettesPanel />
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
        <details className="method-details method-details-compact">
          <summary>{language==='en'?'Evidence management and data retention':'Gestión de evidencia y conservación de datos'}</summary>
          <p>{language==='en'?'Image inspection does not perform species recognition or save images to Supabase. Video analysis uses temporary files that expire on the processing server. Biological identification requires independent scientific review.':'La inspección de fotografías no reconoce especies ni guarda imágenes en Supabase. El análisis de video utiliza archivos temporales que caducan en el servidor de procesamiento. La identificación biológica exige revisión científica independiente.'}</p>
        </details>
      </section>
      <ScientificWorkspace section={section} onNavigate={setSection}
        pendingEvidence={evidenceDraft} onClearEvidence={()=>setEvidenceDraft(null)}
        monitoringNextRequest={monitorNextRequest} onRegistryTabChange={setRegistryTab}
        requestReport={reportRequest} />
      {/* One primary Next control for every module, including completed video and image analyses. */}
      <div className="workflow-global-dock" role="region"
        aria-label={language==='en'?'Research workflow navigation':'Navegación del proceso científico'}>
        <div className="workflow-global-copy">
          <span>{language==='en'?'SCIENTIFIC WORKFLOW':'FLUJO CIENTÍFICO'}</span>
          <strong>{section==='PantheraID'
            ?language==='en'?'Evidence screening':'Exploración de evidencia'
            :moduleLabel(section)}</strong>
        </div>
        <button type="button" className="workflow-next-button workflow-global-next"
          disabled={section==='PantheraID'&&preparingEvidence}
          onClick={advanceWorkflow}>
          <span>{workflowLabel}</span><span aria-hidden="true">→</span>
        </button>
      </div>
      <footer className="panthera-bottom-credit">
        <span>{language==='en'?'CONCEPT & PROTOTYPE':'CONCEPTO Y PROTOTIPO'}</span>
        <strong>Andrea Navarro Jiménez</strong>
        <button type="button" onClick={()=>setShowCredits(true)}>
          {language==='en'?'Credits & contact':'Créditos y contacto'} ↗
        </button>
      </footer>
    </main>
    {showCredits&&<div className="panthera-credits-overlay"
      onMouseDown={event=>{if(event.target===event.currentTarget)setShowCredits(false);}}>
      <section className="panthera-credits-dialog" role="dialog" aria-modal="true"
        aria-labelledby="panthera-credits-title">
        <button type="button" className="panthera-credits-close" autoFocus
          onClick={()=>setShowCredits(false)} aria-label={language==='en'?'Close':'Cerrar'}>×</button>
        <span className="panthera-credits-kicker">PANTHERALAB / 2026</span>
        <h2 id="panthera-credits-title">{language==='en'?'About the project':'Acerca del proyecto'}</h2>
        <p>{language==='en'
          ?'Experimental biodiversity conservation platform integrating field events, satellite context and clearly labeled simulations.'
          :'Plataforma experimental para la conservación de la biodiversidad, con eventos de campo, contexto satelital y simulaciones identificadas.'}</p>
        <div className="panthera-credits-group">
          <span>{language==='en'?'CONCEPT AND PROTOTYPE DEVELOPMENT':'CONCEPTO Y DESARROLLO DEL PROTOTIPO'}</span>
          <strong>Andrea Navarro Jiménez</strong>
          <small>Costa Rica · 2026</small>
        </div>
        <details className="panthera-credits-details">
          <summary>{language==='en'?'Professional contact':'Contacto profesional'}</summary>
          <p>{language==='en'?'For collaboration or project inquiries:':'Para colaboraciones o consultas sobre el proyecto:'}</p>
          <a href="mailto:andrenavarrojime@gmail.com?subject=Consulta%20sobre%20PantheraLAB">
            {language==='en'?'Send an email ↗':'Enviar correo ↗'}</a>
        </details>
        <details className="panthera-credits-details">
          <summary>{language==='en'?'Technologies and acknowledgments':'Tecnologías y reconocimientos'}</summary>
          <p>{language==='en'
            ?'The prototype uses external tools and services, including open-source software, Copernicus/Sentinel data and connectivity simulations. Third-party licenses, credits and contributions remain independent.'
            :'El prototipo utiliza herramientas y servicios externos, incluidos programas de código abierto, datos Copernicus/Sentinel y simulaciones de conectividad. Las licencias, créditos y contribuciones de terceros deben reconocerse por separado.'}</p>
          <p>{language==='en'
            ?'Experimental features are not validated field monitoring or operational emergency services.'
            :'Las funciones experimentales no constituyen monitoreo de campo validado ni servicios operativos de emergencia.'}</p>
        </details>
      </section>
    </div>}
  </div>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><LanguageProvider><App /></LanguageProvider></React.StrictMode>);
registerPantheraPwa();
