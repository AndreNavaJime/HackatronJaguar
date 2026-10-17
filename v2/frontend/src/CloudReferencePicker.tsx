import React from 'react';
import {useLanguage} from './language';
import {cloudConfigured,useCloudIdentity,listCloudOrganizations,listCloudStudies,
  listCloudIndividuals,listCloudPhotos,getPrivateReferenceFile,
  type CloudOrg,type CloudStudy,type CloudIndividual,type CloudPhoto} from './cloudLibrary';

type Selection={file:File;label:string;flank:'left'|'right'|'unknown'};
export default function CloudReferencePicker({onChoose}:{onChoose:(items:Selection[])=>void}){
  const {language}=useLanguage(),tx=(es:string,en:string)=>language==='en'?en:es;
  const {session}=useCloudIdentity();
  const [organizations,setOrganizations]=React.useState<CloudOrg[]>([]);
  const [org,setOrg]=React.useState('');
  const [studies,setStudies]=React.useState<CloudStudy[]>([]);
  const [study,setStudy]=React.useState('');
  const [individuals,setIndividuals]=React.useState<CloudIndividual[]>([]);
  const [photos,setPhotos]=React.useState<CloudPhoto[]>([]);
  const [selected,setSelected]=React.useState<string[]>([]);
  const [error,setError]=React.useState('');
  const [busy,setBusy]=React.useState(false);
  React.useEffect(()=>{
    if(!session){setOrganizations([]);setOrg('');return;}
    let closed=false;
    void listCloudOrganizations().then(values=>{
      if(!closed){setOrganizations(values);setOrg(x=>values.some(a=>a.id===x)?x:(values[0]?.id||''));}
    }).catch(e=>{if(!closed)setError(String(e.message||e));});
    return ()=>{closed=true;};
  },[session?.user.id]);
  React.useEffect(()=>{
    if(!org){setStudies([]);setStudy('');return;}
    let closed=false;
    void listCloudStudies(org).then(values=>{
      if(!closed){setStudies(values);setStudy(x=>values.some(a=>a.id===x)?x:(values[0]?.id||''));}
    }).catch(e=>{if(!closed)setError(String(e.message||e));});
    return ()=>{closed=true;};
  },[org]);
  React.useEffect(()=>{
    setSelected([]);setIndividuals([]);setPhotos([]);
    if(!study)return;
    let closed=false;
    void Promise.all([listCloudIndividuals(study),listCloudPhotos(study)]).then(([people,pictures])=>{
      if(!closed){setIndividuals(people);setPhotos(pictures);}
    }).catch(e=>{if(!closed)setError(String(e.message||e));});
    return ()=>{closed=true;};
  },[study]);

  if(!cloudConfigured||!session)return null;
  const people=new Map(individuals.map(ind=>[ind.id,ind]));
  async function choose(){
    if(!selected.length)return;setBusy(true);setError('');
    try{
      const result:Selection[]=[];
      for(const id of selected){
        const p=photos.find(x=>x.id===id),person=p?people.get(p.individual_id):undefined;
        if(!p||!person)throw new Error('Referencia sin individuo asociado.');
        result.push({file:await getPrivateReferenceFile(p),label:person.code,flank:p.flank});
      }
      onChoose(result);
      setSelected([]);
    }catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  }
  return <details className="cloud-reference-picker method-details">
    <summary>{tx('Usar referencias de mi biblioteca privada','Use references from my private library')}</summary>
    <div className="cloud-reference-inputs">
      <label>{tx('Institución','Organization')}
        <select value={org} onChange={e=>setOrg(e.target.value)}>
          {organizations.map(o=><option key={o.id} value={o.id}>{o.name}</option>)}
        </select>
      </label>
      <label>{tx('Colección','Collection')}
        <select value={study} onChange={e=>setStudy(e.target.value)}>
          {studies.map(s=><option key={s.id} value={s.id}>{s.title}</option>)}
        </select>
      </label>
    </div>
    {study&&<div className="cloud-reference-choices">
      {photos.length===0?<p className="sci-muted">{tx('Este estudio no tiene fotografías de referencia.',
        'No reference photographs in this study.')}</p>:
      photos.slice(0,100).map(p=>{
        const person=people.get(p.individual_id);
        return <label key={p.id} className="cloud-reference-option">
          <input type="checkbox" checked={selected.includes(p.id)} onChange={e=>{
            if(e.target.checked){if(selected.length<6)setSelected(items=>[...items,p.id]);}
            else setSelected(items=>items.filter(id=>id!==p.id));
          }}/>
          <span>{person?.code||'?'} · {p.flank} · {p.filename}</span>
        </label>;
      })}
    </div>}
    <p className="sci-muted">{tx(
      'Elegí hasta seis fotografías de una sola colección. Las imágenes privadas se envían temporalmente al servidor de comparación.',
      'Choose up to six photographs from one collection. Private photos are sent temporarily to the matching server.'
    )}</p>
    <button className="sci-secondary" disabled={!selected.length||busy} type="button"
      onClick={()=>void choose()}>{busy?tx('Preparando…','Preparing…'):tx(
        'Usar referencias seleccionadas','Use selected references')} ({selected.length}/6)</button>
    {error&&<p className="sci-warning" role="alert">{error}</p>}
  </details>;
}
