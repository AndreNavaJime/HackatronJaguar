import React from 'react';
import {useLanguage} from './language';
import {downloadFile,loadSession,saveSession} from './scienceShared';
import './PantheraRosettesPanel.css';

type Candidate={label:string;best_cosine_similarity:number;best_reference_filename:string;reference_images:number};
type Comparison={
  id:string;timestamp:string;queryFilename:string;referenceCount:number;
  candidates:Candidate[];model:string;license:string;
  reviewer:string;chosenName:string;notes:string;
  decision:'pending'|'candidate'|'unresolved';
};
const KEY='pantherascan_rosette_experiments_v1';
const COLAB='https://colab.research.google.com/github/AndreNavaJime/HackatronJaguar/blob/pantherasense-integration/notebooks/PantheraSCAN_Rosetas_Colab.ipynb';
const obj=(v:unknown):Record<string,unknown>|null=>
  v!==null&&typeof v==='object'&&!Array.isArray(v)?v as Record<string,unknown>:null;
const safeStr=(v:unknown,max=160)=>typeof v==='string'?v.slice(0,max):'';
const validCos=(v:unknown):v is number=>typeof v==='number'&&Number.isFinite(v)&&v>=-1&&v<=1;
function parseComparison(input:unknown):Comparison{
  const r=obj(input),query=obj(r?.query),model=obj(r?.model);
  if(!r||r.platform!=='PantheraLAB'||r.module!=='PantheraSCAN'||
     r.schema!=='pantherascan_rosetas_v1'||r.simulation!==false||
     r.identity_verified!==false||r.scientifically_verified!==false||
     !Array.isArray(r.ranked_candidates)||!query||!model)
    throw new Error('El archivo no es un informe experimental de rosetas PantheraSCAN válido.');
  const ts=safeStr(r.timestamp,50),name=safeStr(query.filename,160);
  if(!ts||Number.isNaN(Date.parse(ts))||!name||
     model.metric!=='cosine_similarity'||model.weights_license!=='CC-BY-NC-4.0'||
     model.mode!=='research_noncommercial')
    throw new Error('El informe carece de procedencia, fecha o licencia válida.');
  const candidates:Candidate[]=r.ranked_candidates.slice(0,20).map((v:unknown)=>{
    const c=obj(v),label=safeStr(c?.label,80),file=safeStr(c?.best_reference_filename,160);
    const similarity=c?.best_cosine_similarity;
    if(!c||!label||!file||!validCos(similarity)||typeof c.reference_images!=='number'||
       !Number.isInteger(c.reference_images)||c.reference_images<1||c.reference_images>100)
      throw new Error('El informe contiene una coincidencia incompleta.');
    return {label,best_cosine_similarity:similarity,best_reference_filename:file,reference_images:c.reference_images};
  });
  if(!candidates.length)throw new Error('No hay fotografías de referencia comparables.');
  return {
    id:'REID-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,7),
    timestamp:ts,queryFilename:name,
    referenceCount:typeof r.reference_image_count==='number'&&Number.isFinite(r.reference_image_count)
      ?Math.max(0,Math.min(100,Math.round(r.reference_image_count))):candidates.length,
    candidates,model:safeStr(model.feature_extractor,120),license:'CC-BY-NC-4.0',
    reviewer:'',chosenName:'',notes:'',decision:'pending'
  };
}
function load():Comparison[]{
  const raw=loadSession<unknown>(KEY,[]);
  if(!Array.isArray(raw))return [];
  return raw.filter((v):v is Comparison=>{
    const o=obj(v);return !!o&&typeof o.id==='string'&&typeof o.queryFilename==='string'&&
      Array.isArray(o.candidates)&&['pending','candidate','unresolved'].includes(String(o.decision));
  }).slice(0,10);
}
export default function PantheraRosettesPanel(){
  const {language}=useLanguage(),tx=(es:string,en:string)=>language==='en'?en:es;
  const [records,setRecords]=React.useState<Comparison[]>(load);
  const [selected,setSelected]=React.useState('');
  const [message,setMessage]=React.useState('');
  const current=records.find(r=>r.id===selected)||records[0]||null;
  React.useEffect(()=>{saveSession(KEY,records);},[records]);
  const edit=(data:Partial<Comparison>)=>{
    if(!current)return;
    setRecords(all=>all.map(r=>r.id===current.id?{...r,...data}:r));
  };
  async function importFile(f:File){
    setMessage('');
    if(f.size>512*1024){setMessage(tx('El JSON supera el máximo de 512 KB.','The JSON exceeds 512 KB.'));return;}
    try{
      const data=parseComparison(JSON.parse(await f.text()) as unknown);
      setRecords(prev=>[data,...prev].slice(0,10));
      setSelected(data.id);
      setMessage(tx('Comparación exploratoria importada en esta sesión. No confirma identidad.',
        'Exploratory comparison imported locally. This does not verify identity.'));
    }catch(e){setMessage(e instanceof Error?e.message:String(e));}
  }
  function exportResult(){
    if(!current)return;
    downloadFile('PantheraSCAN_revision_rosetas.json',
      JSON.stringify({
        format:'pantherascan_rosette_review_v1',
        exported_at:new Date().toISOString(),
        source:'research_noncommercial_megadescriptor',
        saved_in_cloud:false,identity_verified:false,scientifically_verified:false,
        query_filename:current.queryFilename,comparison_timestamp:current.timestamp,
        model:current.model,weights_license:current.license,
        ranked_candidates:current.candidates,
        review:{decision:current.decision,reviewer:current.reviewer,
          candidate_name:current.chosenName,notes:current.notes,
          independent_photo_verification_required:true}
      },null,2),'application/json');
  }
  return <details className="method-details rosette-panel">
    <summary>{tx('Opcional · Comparar rosetas de jaguares (experimental)',
      'Optional · Compare jaguar rosettes (experimental)')}</summary>
    <div className="rosette-body">
      <p className="sci-muted">{tx(
        'Compará fotografías propias con referencias de individuos conocidos usando WildlifeTools en Colab. No se requiere una base de datos de ONG.',
        'Compare your own images with known-individual references in Colab using WildlifeTools. No NGO database required.')}</p>
      <p className="sci-warning">{tx(
        'Solo investigación NO COMERCIAL. Los pesos de MegaDescriptor tienen licencia CC BY-NC 4.0. Las similitudes no son probabilidades ni identificaciones verificadas.',
        'NONCOMMERCIAL research only. MegaDescriptor weights are CC BY-NC 4.0. Similarity scores are not probabilities or verified identifications.')}</p>
      <div className="rosette-import">
        <a href={COLAB} target="_blank" rel="noopener noreferrer">
          {tx('Abrir comparación de rosetas en Colab ↗','Open rosette comparison in Colab ↗')}</a>
        <label>{tx('Importar resultado de comparación (JSON)','Import comparison result (JSON)')}
          <input type="file" accept=".json,application/json" onChange={e=>{
            const f=e.target.files?.[0];e.target.value='';if(f)void importFile(f);
          }}/></label>
      </div>
      <p className="sci-muted">{tx(
        'Colab calcula el resultado y devuelve un JSON. Las fotografías y las coincidencias no se suben automáticamente a Vercel; solo se guardan metadatos temporales en este navegador.',
        'Colab computes a JSON result. Photos and matches are not automatically uploaded to Vercel; temporary metadata stays in this browser.')}</p>
      {message&&<p className="sci-notice" role="status">{message}</p>}
      {current&&<>
        {records.length>1&&<label className="rosette-select">{tx('Comparación','Comparison')}
          <select value={current.id} onChange={e=>setSelected(e.target.value)}>
            {records.map(item=><option key={item.id} value={item.id}>{item.queryFilename}</option>)}
          </select></label>}
        <h4>{tx('Fotografía de consulta','Query photo')}: {current.queryFilename}</h4>
        <p className="sci-muted">{tx('Referencias evaluadas','Reference images')}: {current.referenceCount} ·
          {' '}{tx('Modelo','Model')}: {current.model}</p>
        <div className="rosette-candidates">{current.candidates.slice(0,8).map((c,i)=>
          <div key={c.label+'-'+i} className="rosette-match">
            <strong>{i+1}. {c.label}</strong>
            <span>{tx('Similitud coseno','Cosine similarity')}: {c.best_cosine_similarity.toFixed(4)}</span>
            <small>{tx('Mejor referencia','Best reference')}: {c.best_reference_filename} · {c.reference_images} {tx('imágenes','images')}</small>
            <button type="button" className="sci-secondary" onClick={()=>edit({
              chosenName:c.label,decision:'candidate'
            })}>{tx('Anotar como candidato','Mark as candidate')}</button>
          </div>)}</div>
        <div className="rosette-review">
          <label>{tx('Nombre o código propuesto por el investigador','Researcher-proposed name or code')}
            <input maxLength={80} value={current.chosenName}
              onChange={e=>edit({chosenName:e.target.value,decision:'candidate'})}
              placeholder={tx('Opcional · sin confirmación automática','Optional · not automatically verified')}/></label>
          <label>{tx('Investigador','Reviewer')}
            <input maxLength={120} value={current.reviewer}
              onChange={e=>edit({reviewer:e.target.value})}/></label>
          <label>{tx('Observaciones / dudas','Notes / doubts')}
            <textarea rows={2} maxLength={1500} value={current.notes}
              onChange={e=>edit({notes:e.target.value})}/></label>
          <div className="rosette-controls">
            <button type="button" className="sci-secondary" onClick={()=>edit({decision:'unresolved',chosenName:''})}>
              {tx('Identidad sin resolver','Identity unresolved')}</button>
            <button type="button" className="action-button" onClick={exportResult}>
              {tx('Descargar revisión JSON ↓','Download review JSON ↓')}</button>
          </div>
          <p className="sci-muted">{tx(
            'Asignar un nombre aquí no valida científicamente la identidad. Para verificarla hay que revisar fotografías comparables y el protocolo de la organización.',
            'Naming a candidate here does not validate identity. Verification requires comparing source photos and following the organization’s protocol.')}</p>
        </div>
      </>}
    </div>
  </details>;
}
