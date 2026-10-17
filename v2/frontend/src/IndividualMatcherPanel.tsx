import {apiFetch} from './apiClient';
import React from 'react';
import {useLanguage} from './language';
import FlankCropPicker,{cropSelectedFile,type ImageRegion} from './FlankCropPicker';
import CloudReferencePicker from './CloudReferencePicker';
import './IndividualMatcherPanel.css';

type Flank='left'|'right'|'unknown';
type Reference={id:number;file:File;label:string;flank:Flank;crop:ImageRegion|null};
type Candidate={label:string;reference_index:number;reference_flank:Flank;
  status:'candidate_for_review'|'insufficient_evidence'|'incompatible_flank';
  tentative_matches:number;coherent_matches:number;spread_fraction:number;
  evidence_image:string|null};
type MatchResult={method:string;engine:string;hotspotter_installed:boolean;
  identity_verified:false;scientifically_validated:false;query_flank:Flank;
  reference_count:number;query_keypoints:number;candidates:Candidate[];note:string};
const MAX_BYTES=8*1024*1024;
const SIDE_OPTIONS:{value:Flank;es:string;en:string}[]=[
  {value:'unknown',es:'Sin determinar',en:'Unknown'},
  {value:'left',es:'Costado izquierdo',en:'Left flank'},
  {value:'right',es:'Costado derecho',en:'Right flank'}
];

function download(name:string,report:unknown){
  const blob=new Blob([JSON.stringify(report,null,2)],{type:'application/json'});
  const url=URL.createObjectURL(blob);
  const anchor=document.createElement('a');anchor.href=url;anchor.download=name;
  document.body.appendChild(anchor);anchor.click();anchor.remove();
  window.setTimeout(()=>URL.revokeObjectURL(url),1500);
}

export default function IndividualMatcherPanel({photo,enabled}:{photo:File|null;enabled:boolean}){
  const {language}=useLanguage();
  const tx=(es:string,en:string)=>language==='en'?en:es;
  const [refs,setRefs]=React.useState<Reference[]>([]);
  const [side,setSide]=React.useState<Flank>('unknown');
  const [queryCrop,setQueryCrop]=React.useState<ImageRegion|null>(null);
  const [result,setResult]=React.useState<MatchResult|null>(null);
  const [loading,setLoading]=React.useState(false);
  const [error,setError]=React.useState('');
  const [reviewer,setReviewer]=React.useState('');
  const [reviewChoice,setReviewChoice]=React.useState('');
  const [reviewNotes,setReviewNotes]=React.useState('');
  const [confirmReview,setConfirmReview]=React.useState(false);
  const controller=React.useRef<AbortController|null>(null);

  React.useEffect(()=>{
    controller.current?.abort();controller.current=null;
    setResult(null);setError('');setLoading(false);setReviewChoice('');setConfirmReview(false);setQueryCrop(null);
    return ()=>controller.current?.abort();
  },[photo]);
  const invalidate=()=>{controller.current?.abort();controller.current=null;
    setResult(null);setError('');setLoading(false);setReviewChoice('');setConfirmReview(false);};

  function addReferences(files:FileList|null){
    if(!files)return;
    const list=Array.from(files);
    if(list.length>6||list.length+refs.length>6){
      setError(tx('Máximo seis fotografías de referencia.','Maximum six reference photographs.'));return;
    }
    const rejected=list.find(f=>!['image/jpeg','image/png','image/webp'].includes(f.type)||f.size>MAX_BYTES);
    if(rejected){setError(tx('Cada foto debe ser JPG/PNG/WebP de hasta 8 MB.','Each photo must be JPG/PNG/WebP, at most 8 MB.'));return;}
    invalidate();
    setRefs(previous=>{
      const start=previous.reduce((a,x)=>Math.max(a,x.id),0);
      return [...previous,...list.map((file,i)=>({id:start+i+1,file,label:'',flank:'unknown' as Flank,crop:null}))];
    });
  }
  function changeReference(id:number,patch:Partial<Reference>){
    invalidate();setRefs(previous=>previous.map(r=>r.id===id?{...r,...patch}:r));
  }
  function removeReference(id:number){invalidate();setRefs(previous=>previous.filter(r=>r.id!==id));}

  const ready=!!photo&&refs.length>0&&refs.every(r=>r.label.trim().length>0);
  async function compare(){
    if(!photo||!ready||!enabled||loading)return;
    if(photo.size>MAX_BYTES){setError(tx('La fotografía principal supera 8 MB.','The query photo exceeds 8 MB.'));return;}
    invalidate();
    const active=new AbortController();controller.current=active;
    setLoading(true);
    try{
      const form=new FormData();
      const croppedQuery=await cropSelectedFile(photo,queryCrop);
      if(active.signal.aborted)return;
      form.append('query',croppedQuery,croppedQuery.name);
      for(const ref of refs){
        const cropped=await cropSelectedFile(ref.file,ref.crop);
        if(active.signal.aborted)return;
        form.append('references',cropped,cropped.name);
      }
      form.append('labels',JSON.stringify(refs.map(r=>r.label.trim())));
      form.append('flanks',JSON.stringify(refs.map(r=>r.flank)));
      form.append('query_flank',side);
      const response=await apiFetch('/api/individuals/compare',{
        method:'POST',body:form,signal:active.signal
      });
      const raw=await response.text();
      let payload:unknown;
      try{payload=JSON.parse(raw) as unknown;}catch{
        throw new Error(tx('El servidor no devolvió JSON válido.','Server did not return valid JSON.'));
      }
      if(!response.ok){
        const detail=payload&&typeof payload==='object'&&'detail' in payload
          ? (payload as {detail:unknown}).detail:undefined;
        throw new Error(typeof detail==='string'?detail:tx('Error al comparar.','Comparison failed.'));
      }
      if(!payload||typeof payload!=='object'||!('candidates' in payload)
         ||!Array.isArray((payload as MatchResult).candidates))
        throw new Error(tx('Resultado de comparación incompleto.','Incomplete comparison response.'));
      if(active.signal.aborted)return;
      setResult(payload as MatchResult);
    }catch(e){
      if(active.signal.aborted)return;
      setError(e instanceof Error?e.message:String(e));
    }finally{
      if(controller.current===active){controller.current=null;setLoading(false);}
    }
  }
  function exportReport(){
    if(!result)return;
    download('pantherascan_comparacion_individual_exploratoria.json',{
      format:'pantherascan_individual_review_v1',
      analyzed_at:new Date().toISOString(),
      scientific_validation:false,identity_verified:false,
      photos_saved_to_cloud:false,method:result.method,
      query_filename:photo?.name||'',query_flank:side,query_crop:queryCrop,
      references:refs.map((r,i)=>({index:i,filename:r.file.name,label:r.label,flank:r.flank,crop:r.crop})),
      ranked_candidates:result.candidates.map(({evidence_image,...c})=>c),
      review:{reviewer:reviewer.trim(),decision:reviewChoice||'pending',
        reviewed_by_human:confirmReview&&!!reviewer.trim(),notes:reviewNotes.trim(),
        identity_requires_independent_verification:true},
      note:result.note,
    });
  }
  const candidates=result?.candidates??[];
  const withEvidence=candidates.filter(c=>c.status==='candidate_for_review');
  return <section id="panthera-individual-compare" className="individual-matcher" aria-label={tx('Comparación individual de jaguares','Jaguar individual comparison')}>
    <div className="individual-matcher-head">
      <div>
        <span className="scan-feature-kicker">PANTHERASCAN / {tx('COMPARACIÓN INDIVIDUAL','INDIVIDUAL COMPARISON')}</span>
        <h3>{tx('Comparar jaguares por su patrón de pelaje','Compare jaguars by their coat patterns')}</h3>
        <p>{tx(
          'Subí fotografías de individuos de referencia y comparalas con la foto seleccionada arriba. El sistema propone coincidencias de rasgos locales mediante SIFT + RANSAC.',
          'Add known-individual reference photos and compare them with the photo selected above. The system proposes local-feature correspondences using SIFT + RANSAC.'
        )}</p>
      </div><span className="sci-tag">OpenCV · SIFT</span>
    </div>
    <p className="individual-matcher-warning">{tx(
      'EXPERIMENTAL · Sin identificación automática verificada. Utilizá fotografías recortadas al flanco, de ángulos comparables y con códigos conocidos. Una coincidencia no es una probabilidad ni confirma un individuo nuevo.',
      'EXPERIMENTAL · No verified automatic identity. Use cropped flanks from comparable viewpoints with known reference codes. A match is not a probability or proof of a new individual.'
    )}</p>
    <div className="individual-matcher-steps">
      <span>{tx('1. Foto de consulta','1. Query photo')}</span><span>{tx('2. Referencias','2. References')}</span><span>{tx('3. Comparación','3. Matching')}</span><span>{tx('4. Revisión','4. Review')}</span>
    </div>
    <div className="individual-match-query">
      <div><strong>{tx('Fotografía de consulta','Query photograph')}</strong><small>{photo?photo.name:tx('Elegí primero una foto arriba, en Fotografías.','Select a photo above under Photographs first.')}</small></div>
      <label>{tx('Costado de la consulta','Query flank')}
        <select value={side} onChange={e=>{invalidate();setSide(e.target.value as Flank);}}>
          {SIDE_OPTIONS.map(x=><option key={x.value} value={x.value}>{tx(x.es,x.en)}</option>)}
        </select>
      </label>
    </div>
    {photo&&<FlankCropPicker file={photo} value={queryCrop} language={language}
      title={tx('Seleccioná el costado de la foto de consulta','Select the query photo flank')}
      onChange={crop=>{invalidate();setQueryCrop(crop);}}/>}
    <CloudReferencePicker onChoose={selected=>{
      invalidate();
      setRefs(existing=>{
        const start=existing.reduce((max,x)=>Math.max(max,x.id),0);
        const newItems=selected.slice(0,Math.max(0,6-existing.length)).map((item,index)=>({
          id:start+index+1,file:item.file,label:item.label,flank:item.flank,crop:null,
        }));
        return [...existing,...newItems];
      });
    }}/>
    <div className="individual-match-upload">
      <label htmlFor="panthera-match-references">{tx('Agregar referencias del catálogo (máximo 6 imágenes)','Add reference photos (maximum 6 images)')}</label>
      <input id="panthera-match-references" type="file" accept="image/jpeg,image/png,image/webp" multiple
        onChange={e=>{addReferences(e.target.files);e.target.value='';}}/>
      <small>{tx('Cada referencia necesita el código del jaguar conocido y, de ser posible, su costado. Estas fotos se procesan temporalmente, no se guardan en Render.',
        'Each reference needs the known jaguar code and preferably its flank. Photos are processed temporarily and are not stored on Render.')}</small>
    </div>
    {!!refs.length&&<div className="individual-match-refs">
      {refs.map((r,i)=><div className="individual-match-ref" key={r.id}>
        <div className="individual-match-ref-head">
          <strong>{tx('Referencia','Reference')} {i+1}</strong>
          <button type="button" onClick={()=>removeReference(r.id)}>{tx('Quitar','Remove')} ×</button>
        </div>
        <small title={r.file.name}>{r.file.name}</small>
        <FlankCropPicker file={r.file} value={r.crop} language={language}
          onChange={crop=>changeReference(r.id,{crop})}/>
        <div className="individual-match-ref-fields">
          <label>{tx('Código del individuo','Individual code')}
            <input value={r.label} maxLength={80} placeholder="JAG-001"
              onChange={e=>changeReference(r.id,{label:e.target.value})}/>
          </label>
          <label>{tx('Costado','Flank')}
            <select value={r.flank} onChange={e=>changeReference(r.id,{flank:e.target.value as Flank})}>
              {SIDE_OPTIONS.map(x=><option key={x.value} value={x.value}>{tx(x.es,x.en)}</option>)}
            </select>
          </label>
        </div>
      </div>)}
    </div>}
    <div className="individual-match-action">
      <button type="button" className="action-button" disabled={!ready||!enabled||loading} onClick={()=>void compare()}>
        {loading?tx('Comparando patrones…','Matching patterns…'):tx('Comparar fotografías ahora','Compare photographs now')}
      </button>
      {!enabled&&<small>{tx('Esperando conexión con Render…','Waiting for Render connection…')}</small>}
      {!ready&&<small>{tx('Para comparar necesitás una foto y códigos para las referencias.','To compare, add a query photo and reference codes.')}</small>}
    </div>
    {error&&<p className="upload-error" role="alert">{error}</p>}
    {result&&<div className="individual-match-results" aria-live="polite">
      <div className="individual-match-results-title">
        <h4>{tx('Coincidencias propuestas','Candidate correspondences')}</h4>
        <span className="sci-tag">{tx('REVISIÓN PENDIENTE','REVIEW REQUIRED')}</span>
      </div>
      <p className="sci-muted">{result.method} · {result.reference_count} {tx('referencias','references')} · {result.query_keypoints} {tx('puntos locales en consulta','local keypoints in query')}</p>
      <p className="individual-matcher-warning">{withEvidence.length
        ?tx('Se encontraron correspondencias geométricamente consistentes. NO confirman la identidad.','Geometrically consistent features found. Identity is NOT confirmed.')
        :tx('No hubo coincidencias con evidencia suficiente. Esto NO demuestra que sea un individuo nuevo.','No matches with sufficient evidence. This does NOT prove a new individual.')}</p>
      <div className="individual-match-candidates">
        {candidates.map((c,i)=><article key={c.reference_index}>
          <div className="individual-match-candidate-head">
            <strong>{i+1}. {c.label}</strong>
            <span className={c.status==='candidate_for_review'?'candidate-hit':'candidate-uncertain'}>
              {c.status==='candidate_for_review'?tx('Posible coincidencia','Possible match'):
                c.status==='incompatible_flank'?tx('Costado distinto','Different flank'):
                tx('Evidencia insuficiente','Insufficient evidence')}
            </span>
          </div>
          <div className="individual-match-metrics">
            <span>{tx('Puntos coherentes','Geometrically coherent matches')}: <b>{c.coherent_matches}</b></span>
            <span>{tx('Correspondencias tentativas','Tentative features')}: <b>{c.tentative_matches}</b></span>
          </div>
          {c.evidence_image&&<details className="individual-match-evidence">
            <summary>{tx('Ver evidencia de correspondencias','View matched-feature evidence')}</summary>
            <img src={c.evidence_image} alt={tx('Líneas de correspondencia SIFT entre ambas fotografías','SIFT matching lines between photographs')} loading="lazy"/>
            <small>{tx('Las líneas son coincidencias de características, no rosetas segmentadas ni confirmación de identidad.','Lines show matched features, not segmented rosettes or verified identity.')}</small>
          </details>}
          <button className="sci-secondary" type="button" onClick={()=>{setReviewChoice(c.label);setConfirmReview(false);}}>
            {tx('Seleccionar para revisión','Select for review')}
          </button>
        </article>)}
      </div>
      <div className="individual-match-review">
        <h4>{tx('Decisión del investigador','Researcher decision')}</h4>
        <label>{tx('Candidato a revisar','Candidate for review')}
          <select value={reviewChoice} onChange={e=>{setReviewChoice(e.target.value);setConfirmReview(false);}}>
            <option value="">{tx('Sin resolver','Unresolved')}</option>
            {Array.from(new Set(refs.map(r=>r.label.trim()))).map(label=><option key={label} value={label}>{label}</option>)}
          </select>
        </label>
        <label>{tx('Responsable de revisión','Reviewer')}
          <input value={reviewer} onChange={e=>setReviewer(e.target.value)} maxLength={120} placeholder={tx('Nombre del investigador','Researcher name')}/>
        </label>
        <label>{tx('Observaciones científicas','Scientific notes')}
          <textarea rows={3} maxLength={1500} value={reviewNotes} onChange={e=>setReviewNotes(e.target.value)} />
        </label>
        <label className="individual-match-confirm">
          <input type="checkbox" checked={confirmReview} onChange={e=>setConfirmReview(e.target.checked)}/>
          {tx('Revisé visualmente las fotos. La identidad sigue siendo una decisión científica independiente.',
            'I reviewed the photographs visually. Identity remains an independent scientific decision.')}
        </label>
        <button className="action-button" type="button" onClick={exportReport}>
          {tx('Descargar comparación y revisión · JSON ↓','Download comparison and review · JSON ↓')}
        </button>
        <p className="sci-muted">{result.note} {tx('La comparación y la revisión permanecen en esta pantalla hasta cerrarla; el servidor no almacena fotografías.',
          'Matching and review remain in this page until it is closed; the server stores no photos.')}</p>
      </div>
    </div>}
  </section>;
}
