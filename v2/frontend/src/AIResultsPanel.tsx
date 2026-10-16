import React from 'react';
import {useLanguage} from './language';
import {downloadFile,toCsv,loadSession,saveSession} from './scienceShared';
import './AIResultsPanel.css';

type Decision='pending'|'review'|'verified'|'discarded';
type Candidate={label:string;score:number};
type View={crop:string;source:string;suggestions:Candidate[];bbox:number[]|null};
type ModelCandidate={model:string;name:string;score:number|null;metric:string;box:number[]|null};
type AIRecord={
  id:string;filename:string;timestamp:string;importedAt:string;
  modelDetector:string;detectorConfidence:number|null;
  animalCount:number;peopleCount:number;vehicleCount:number;
  classificationStatus:string;species:Candidate[];views:View[];
  lraspp:ModelCandidate|null;sam:ModelCandidate|null;samBody:ModelCandidate|null;
  isSimulation:false;scientificallyVerified:false;cameraId:string;
  reviewer:string;confirmedSpecies:string;notes:string;decision:Decision;
};
const KEY='pantheralab_colab_reports_session_v1';
const MAX_JSON_BYTES=2*1024*1024;
const COLAB_URL='https://colab.research.google.com/github/AndreNavaJime/HackatronJaguar/blob/pantherasense-integration/notebooks/PantheraLAB_IA_Real_Colab.ipynb';
const object=(x:unknown):Record<string,unknown>|null=>
  !!x&&typeof x==='object'&&!Array.isArray(x)?x as Record<string,unknown>:null;
const list=(x:unknown):unknown[]=>Array.isArray(x)?x:[];
const string=(x:unknown,max=180):string=>typeof x==='string'?x.slice(0,max):'';
const score=(x:unknown):number|null=>
  typeof x==='number'&&Number.isFinite(x)&&x>=0&&x<=1?x:null;
const bounds=(x:unknown):number[]|null=>
  Array.isArray(x)&&x.length===4&&x.every(v=>typeof v==='number'&&Number.isFinite(v))
  ?x as number[]:null;
const candidates=(x:unknown):Candidate[]=>list(x).slice(0,10).flatMap(v=>{
  const item=object(v),value=score(item?.score),label=string(item?.label,130);
  return value===null||!label?[]:[{label,score:value}];
});
function scientificModel(x:unknown,model:string,metric:string):ModelCandidate|null{
  const item=object(x);if(!item)return null;
  const value=score(item.sam2_predicted_iou??item.estimated_pixel_score);
  return {model,name:string(item.prompt??item.class_name,100)||model,
    score:value,metric,box:bounds(item.bbox_xyxy)};
}
function parseReport(data:unknown,filename:string):AIRecord{
  const root=object(data);
  if(!root||root.platform!=='PantheraLAB'||root.simulation!==false||
     root.scientifically_verified!==false)throw new Error(
    'El archivo debe ser un JSON real de PantheraLAB, sin simulación y sin validación científica automática.');
  const detector=object(root.megadetector),classification=object(root.speciesnet);
  if(!detector||!classification||!Array.isArray(detector.detections))
    throw new Error('Faltan los resultados megadetector.detections o speciesnet.');
  const detections=list(detector.detections).map(object).filter((d):d is Record<string,unknown>=>d!==null);
  const validDate=string(root.timestamp,80);
  if(!validDate||Number.isNaN(Date.parse(validDate)))
    throw new Error('El informe no contiene una fecha de ejecución válida.');
  const model=string(detector.model,100);
  if(!model)throw new Error('No se identifica el modelo MegaDetector.');
  const views=list(classification.views).slice(0,8).flatMap(item=>{
    const v=object(item);if(!v)return [];
    return [{crop:string(v.crop,100),source:string(v.region_provenance,130),
      suggestions:candidates(v.suggestions),bbox:bounds(v.bbox_xyxy)}];
  });
  const segment=object(root.segmentation),sam=object(root.sam2);
  const animalDetections=detections.filter(d=>d.class_name==='animal');
  const topAnimal=animalDetections.reduce<number|null>((best,item)=>{
    const found=score(item.confidence);return found!==null&&(best===null||found>best)?found:best;
  },null);
  const iso=validDate;
  return {
    id:'COLAB-'+Date.now().toString(36).toUpperCase()+'-'+Math.random().toString(36).slice(2,8),
    filename:filename.slice(0,160),timestamp:iso,importedAt:new Date().toISOString(),
    modelDetector:model,detectorConfidence:topAnimal,
    animalCount:animalDetections.length,
    peopleCount:detections.filter(d=>d.class_name==='person').length,
    vehicleCount:detections.filter(d=>d.class_name==='vehicle').length,
    classificationStatus:string(classification.status,90)||'unknown',
    species:candidates(classification.suggestions),views,
    lraspp:scientificModel(object(segment)?.selected,
      string(object(segment)?.model,120)||'LR-ASPP','pixel_score'),
    sam:scientificModel(object(sam)?.selected,
      string(object(sam)?.model,120)||'SAM 2','predicted_iou'),
    samBody:scientificModel(object(sam)?.body_candidate,
      string(object(sam)?.model,120)||'SAM 2','predicted_iou'),
    isSimulation:false,scientificallyVerified:false,cameraId:'',
    reviewer:'',confirmedSpecies:'',notes:'',decision:'pending'
  };
}
function loadReports():AIRecord[]{
  const stored=loadSession<unknown>(KEY,[]);
  if(!Array.isArray(stored))return [];
  return stored.filter((item):item is AIRecord=>{
    const r=object(item);
    return !!r&&typeof r.id==='string'&&typeof r.filename==='string'&&
      typeof r.timestamp==='string'&&r.isSimulation===false&&
      Array.isArray(r.species)&&Array.isArray(r.views)&&
      ['pending','review','verified','discarded'].includes(String(r.decision));
  }).slice(0,20);
}
const pct=(n:number|null)=>n===null?'—':(n*100).toFixed(1)+' %';
function safeDate(iso:string,language:string){
  const d=new Date(iso);return Number.isNaN(d.getTime())?iso:
    d.toLocaleString(language==='en'?'en-US':'es-CR',{dateStyle:'short',timeStyle:'short'});
}
export default function AIResultsPanel(){
  const {language}=useLanguage();
  const tx=(es:string,en:string)=>language==='en'?en:es;
  const [reports,setReports]=React.useState<AIRecord[]>(loadReports);
  const [selectedId,setSelectedId]=React.useState('');
  const [notice,setNotice]=React.useState('');
  const [reviewConfirmation,setReviewConfirmation]=React.useState(false);
  const [photo,setPhoto]=React.useState<File|null>(null);
  const [mask,setMask]=React.useState<File|null>(null);
  const [photoUrl,setPhotoUrl]=React.useState<string|null>(null);
  const [maskUrl,setMaskUrl]=React.useState<string|null>(null);
  const current=reports.find(r=>r.id===selectedId)||reports[0]||null;
  React.useEffect(()=>{saveSession(KEY,reports);},[reports]);
  React.useEffect(()=>{
    const url=photo?URL.createObjectURL(photo):null;setPhotoUrl(url);
    return ()=>{if(url)URL.revokeObjectURL(url);};
  },[photo]);
  React.useEffect(()=>{
    const url=mask?URL.createObjectURL(mask):null;setMaskUrl(url);
    return ()=>{if(url)URL.revokeObjectURL(url);};
  },[mask]);
  const update=(id:string,values:Partial<AIRecord>)=>
    setReports(all=>all.map(r=>r.id===id?{...r,...values}:r));
  const decisionCount=(status:Decision)=>reports.filter(r=>r.decision===status).length;
  async function importJson(file:File){
    setNotice('');
    if(file.size>MAX_JSON_BYTES){setNotice(tx('JSON demasiado grande (máximo 2 MB).','JSON too large (2 MB limit).'));return;}
    try{
      const text=await file.text();
      const parsed=parseReport(JSON.parse(text) as unknown,file.name);
      setReports(items=>[parsed,...items].slice(0,20));
      setSelectedId(parsed.id);
      setPhoto(null);setMask(null);setReviewConfirmation(false);
      setNotice(tx('Informe de inferencia real importado solo en esta sesión. Revisá sus resultados.',
        'Real inference report imported for this session only. Review its results.'));
    }catch(error){
      setNotice(error instanceof Error?error.message:tx('No se pudo leer el informe.','Unable to read report.'));
    }
  }
  function selectLocalImage(file:File|null,setter:(file:File|null)=>void){
    if(!file){setter(null);return;}
    if(!['image/jpeg','image/png','image/webp'].includes(file.type)||file.size>12*1024*1024){
      setNotice(tx('Solo JPG, PNG o WebP hasta 12 MB.','Use JPG, PNG, or WebP up to 12 MB.'));return;
    }
    setter(file);setNotice('');
  }
  function exportCsv(){
    downloadFile('PantheraLAB_inferencias_revisadas.csv',toCsv(reports.map(r=>({
      report_id:r.id,source_file:r.filename,analyzed_at_utc:r.timestamp,
      animal_count:r.animalCount,detector_model:r.modelDetector,
      detection_confidence:r.detectorConfidence,
      species_proposal:r.species[0]?.label||'',species_model_score:r.species[0]?.score??null,
      sam2_predicted_iou:r.sam?.score??null,
      body_candidate_predicted_iou:r.samBody?.score??null,
      decision:r.decision,reviewer:r.reviewer,confirmed_species:r.confirmedSpecies,
      camera_id:r.cameraId,notes:r.notes,
      image_provided:false,cloud_saved:false
    }))),'text/csv;charset=utf-8');
  }
  function exportJson(){
    downloadFile('PantheraLAB_inferencias_revisadas.json',
      JSON.stringify({format:'pantheralab_colab_import_v1',saved_in_cloud:false,
        exported_at:new Date().toISOString(),reports},null,2),'application/json');
  }
  function verify(){
    if(!current||!current.reviewer.trim()||!current.confirmedSpecies.trim()||!reviewConfirmation){
      setNotice(tx('Para validar, indicá quién revisó, la especie confirmada y marcá la revisión humana.',
        'To verify, provide reviewer, confirmed species, and check human review.'));return;
    }
    update(current.id,{decision:'verified'});
    setNotice(tx('Marcado como confirmado por revisión humana en esta sesión local; no publicado en el registro del estudio.',
      'Marked human-verified in this local session, not published to the study registry.'));
  }
  return <section className="sci-panel ai-review" aria-label="PantheraLAB laboratorio de IA">
    <div className="sci-panel-head ai-review-head">
      <div><span className="sci-kicker">PANTHERALAB / REAL AI EVIDENCE</span>
        <h3>{tx('Laboratorio de IA · Resultados de Colab','AI laboratory · Colab results')}</h3>
        <p className="sci-muted">{tx(
          'Importá el JSON generado por MegaDetector, LR-ASPP, SAM 2 y SpeciesNet. Revisá hipótesis científicas sin confundirlas con identificaciones verificadas.',
          'Import JSON generated by MegaDetector, LR-ASPP, SAM 2 and SpeciesNet. Review scientific hypotheses without treating them as verified identifications.')}</p>
      </div><span className="sci-tag">JSON · {tx('DATOS REALES','REAL DATA')}</span>
    </div>
    <div className="ai-review-flow">
      <span>Colab · IA</span><b>→</b><span>JSON</span><b>→</b>
      <span>Vercel · {tx('Visualización','Visualization')}</span><b>→</b>
      <span>{tx('Revisión humana','Human review')}</span>
    </div>
    <div className="ai-review-actions">
      <label className="ai-review-file">
        <span>{tx('Importar resultado JSON de Colab','Import Colab result JSON')}</span>
        <input type="file" accept=".json,application/json" onChange={event=>{
          const file=event.target.files?.[0];event.target.value='';
          if(file)void importJson(file);
        }}/>
      </label>
      <a className="ai-review-colab" href={COLAB_URL} target="_blank" rel="noopener noreferrer">
        {tx('Abrir cuaderno de IA en Colab ↗','Open AI notebook in Colab ↗')}
      </a>
    </div>
    {notice&&<p className="sci-notice" role="status">{notice}</p>}
    <p className="sci-muted ai-review-disclaimer">{tx(
      'Colab está conectado a GitHub como cuaderno de código, no como API permanente. La importación es manual: este navegador conserva solo metadatos en sessionStorage; no almacena fotografías ni envía datos a Render o Vercel.',
      'Colab opens a GitHub-hosted notebook, not a permanent API. Import is manual: this browser keeps metadata only in sessionStorage; images are not stored or sent to Render or Vercel.')}</p>
    {reports.length===0?<div className="ai-review-empty">
      <strong>{tx('Todavía no hay informes importados','No reports imported yet')}</strong>
      <p>{tx('En Colab descargá resultado_pantheralab.json y elegilo arriba. No necesitás instalar los modelos en Vercel.',
        'Download resultado_pantheralab.json from Colab and select it above. AI models do not need to run on Vercel.')}</p>
    </div>:<>
      <div className="sci-stats ai-review-stats">
        <div><span>{tx('Informes importados','Imported reports')}</span><strong>{reports.length}</strong></div>
        <div><span>{tx('Pendientes','Pending')}</span><strong>{decisionCount('pending')}</strong></div>
        <div><span>{tx('En revisión','Under review')}</span><strong>{decisionCount('review')}</strong></div>
        <div><span>{tx('Confirmados manualmente','Human verified')}</span><strong>{decisionCount('verified')}</strong></div>
      </div>
      <div className="ai-review-toolbar">
        <label>{tx('Elegir informe','Select report')}
          <select value={current?.id||''} onChange={event=>{
            setSelectedId(event.target.value);setPhoto(null);setMask(null);
            setNotice('');setReviewConfirmation(false);
          }}>{reports.map(r=><option value={r.id} key={r.id}>
            {r.filename} · {safeDate(r.timestamp,language)}
          </option>)}</select>
        </label>
        <button type="button" className="sci-secondary" onClick={exportCsv}>CSV ↓</button>
        <button type="button" className="sci-secondary" onClick={exportJson}>JSON ↓</button>
      </div>
      {current&&<div className="ai-review-record" key={current.id}>
        <div className="ai-review-record-head">
          <strong>{tx('Análisis real, sin validación automática','Real inference, not automatically validated')}</strong>
          <span className="sci-tag">{current.decision==='verified'?
            tx('CONFIRMADO POR PERSONA','HUMAN VERIFIED'):
            current.decision==='discarded'?tx('DESCARTADO','DISCARDED'):
            current.decision==='review'?tx('EN REVISIÓN','UNDER REVIEW'):
            tx('PENDIENTE','PENDING')}</span>
        </div>
        <p className="sci-muted">{safeDate(current.timestamp,language)} · {current.modelDetector}</p>
        <div className="sci-stats ai-review-stats">
          <div><span>{tx('Animales candidatos','Animal candidates')}</span><strong>{current.animalCount}</strong></div>
          <div><span>{tx('Puntuación MegaDetector','MegaDetector score')}</span><strong>{pct(current.detectorConfidence)}</strong></div>
          <div><span>{tx('SpeciesNet','SpeciesNet')}</span><strong>{current.classificationStatus==='suggested'?tx('Sugirió taxones','Suggested taxa'):current.classificationStatus}</strong></div>
          <div><span>{tx('IoU estimada SAM 2','SAM 2 predicted IoU')}</span><strong>{pct(current.sam?.score??null)}</strong></div>
        </div>
        <div className="ai-review-models">
          <article><strong>MegaDetector</strong><small>{tx('Detección de fauna','Wildlife detection')}</small>
            <p>{current.animalCount} {tx('animal(es) candidato(s)','animal candidate(s)')}</p></article>
          <article><strong>LR-ASPP</strong><small>{tx('Segmentación semántica','Semantic segmentation')}</small>
            <p>{current.lraspp?current.lraspp.name+' · '+pct(current.lraspp.score):'—'}</p></article>
          <article><strong>SAM 2</strong><small>{tx('Contorno · IoU estimada','Mask · predicted IoU')}</small>
            <p>{pct(current.sam?.score??null)}</p></article>
          <article><strong>{tx('SAM 2 · cuerpo candidato','SAM 2 · body candidate')}</strong>
            <small>{tx('Hipótesis no verificada','Unverified hypothesis')}</small>
            <p>{pct(current.samBody?.score??null)}</p></article>
        </div>
        <div className="ai-review-columns">
          <div>
            <h4>{tx('Especies sugeridas por SpeciesNet','Species suggested by SpeciesNet')}</h4>
            {current.species.length?<div className="ai-review-species">
              {current.species.slice(0,5).map((item,i)=><div className="ai-review-species-row" key={i}>
                <span>{item.label}</span><strong>{pct(item.score)}</strong>
                <div className="ai-review-meter"><i style={{width:(item.score*100)+'%'}}/></div>
              </div>)}
            </div>:<p className="sci-muted">{tx('No hay sugerencias de especie.','No species suggestions.')}</p>}
            <details className="method-details">
              <summary>{tx('Comparar regiones y modelos','Compare regions and models')} ({current.views.length})</summary>
              <div className="ai-review-views">{current.views.map((view,i)=><div key={i}>
                <strong>{view.crop.replace(/_/g,' ')}</strong>
                <small>{view.source||tx('Origen sin especificar','Unknown provenance')}</small>
                <p>{view.suggestions.slice(0,2).map(s=>s.label+' ('+pct(s.score)+')').join(' · ')||'—'}</p>
              </div>)}</div>
            </details>
          </div>
          <div>
            <h4>{tx('Evidencia visual local (opcional)','Local visual evidence (optional)')}</h4>
            <p className="sci-muted">{tx(
              'Seleccioná una foto original y una máscara descargadas de Colab. Son archivos locales y NO se comprueba que correspondan al JSON.',
              'Select an original image and a mask downloaded from Colab. Files stay local and are NOT checked against the JSON.')}</p>
            <label className="ai-review-image-input">{tx('Fotografía / comparativa','Photo / comparison')}
              <input type="file" accept="image/png,image/jpeg,image/webp" onChange={e=>
                selectLocalImage(e.target.files?.[0]||null,setPhoto)}/></label>
            <label className="ai-review-image-input">{tx('Máscara o imagen SAM 2','SAM 2 mask or image')}
              <input type="file" accept="image/png,image/jpeg,image/webp" onChange={e=>
                selectLocalImage(e.target.files?.[0]||null,setMask)}/></label>
            <div className="ai-review-images">
              {photoUrl&&<figure><img src={photoUrl} alt={tx('Imagen científica seleccionada','Selected scientific image')}/><figcaption>{tx('Foto seleccionada','Selected photo')}</figcaption></figure>}
              {maskUrl&&<figure><img src={maskUrl} alt={tx('Máscara seleccionada','Selected mask')}/><figcaption>{tx('Máscara / SAM 2','Mask / SAM 2')}</figcaption></figure>}
              {!photoUrl&&!maskUrl&&<p className="sci-muted">{tx('No se cargaron imágenes; el informe JSON es suficiente para ver las estadísticas.',
                'No images loaded; the JSON report is sufficient for viewing statistics.')}</p>}
            </div>
          </div>
        </div>
        <div className="ai-review-validation">
          <h4>{tx('Revisión científica · decisión manual','Scientific review · manual decision')}</h4>
          <div className="ai-review-inputs">
            <label>{tx('ID de cámara (si se conoce)','Camera ID (if known)')}
              <input value={current.cameraId} maxLength={100}
                onChange={e=>update(current.id,{cameraId:e.target.value,decision:'pending'})}
                placeholder={tx('No suministrado por Colab','Not supplied by Colab')}/></label>
            <label>{tx('Investigador responsable','Reviewer')}
              <input value={current.reviewer} maxLength={120}
                onChange={e=>update(current.id,{reviewer:e.target.value,decision:'pending'})}
                placeholder={tx('Nombre del revisor','Reviewer name')}/></label>
            <label>{tx('Especie confirmada manualmente','Manually confirmed species')}
              <input value={current.confirmedSpecies} maxLength={150}
                onChange={e=>update(current.id,{confirmedSpecies:e.target.value,decision:'pending'})}
                placeholder={tx('Solo tras revisar la evidencia','Only after examining evidence')}/></label>
          </div>
          <label className="ai-review-notes">{tx('Notas de la revisión','Review notes')}
            <textarea rows={3} maxLength={2000} value={current.notes}
              onChange={e=>update(current.id,{notes:e.target.value,decision:'pending'})}
              placeholder={tx('Limitaciones, contraste de pelaje, dudas de la máscara…',
                'Mask limitations, image contrast, uncertainty…')}/></label>
          <label className="ai-review-check">
            <input type="checkbox" checked={reviewConfirmation}
              onChange={e=>setReviewConfirmation(e.target.checked)}/>
            {tx('Confirmo que una persona revisó la evidencia (no solamente el porcentaje de IA).',
              'I confirm a human reviewed the evidence (not merely AI confidence scores).')}
          </label>
          <div className="ai-review-review-actions">
            <button type="button" className="sci-secondary" onClick={()=>{
              update(current.id,{decision:'review'});setNotice('');
            }}>{tx('Marcar para revisión','Mark for review')}</button>
            <button type="button" className="action-button" onClick={verify}>
              {tx('Confirmar identificación manual','Confirm human identification')}</button>
            <button type="button" className="sci-secondary" onClick={()=>{
              update(current.id,{decision:'discarded'});setNotice('');
            }}>{tx('Descartar','Discard')}</button>
            <button type="button" className="sci-inline" onClick={()=>{
              update(current.id,{decision:'pending'});setReviewConfirmation(false);setNotice('');
            }}>{tx('Restablecer','Reset')}</button>
          </div>
          <p className="sci-muted">{tx('Validar aquí solo marca la revisión del informe en este navegador: NO incorpora automáticamente una observación al estudio ni certifica la especie.',
            'Verification here only marks the local report review: it does NOT automatically register a field observation or certify the species.')}</p>
        </div>
      </div>}
    </>}
  </section>;
}
