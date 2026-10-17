import React from 'react';
import {useLanguage} from './language';
import {cloudConfigured,createCloudOrganization,createCloudStudy,listCloudOrganizations,
  listCloudStudies,listCloudIndividuals,listCloudPhotos,saveCloudReference,
  useCloudIdentity,type CloudOrg,type CloudStudy,type CloudIndividual,type CloudPhoto,
  type ImportRow} from './cloudLibrary';
import './CloudLibraryPanel.css';

const MAX_BULK=20;
const allowedSides=['left','right','unknown'];
const allowedSexes=['female','male','unknown'];
const allowedAges=['unknown','juvenile','subadult','adult'];
function parseCsv(csv:string):string[][]{
  const text=csv.replace(/^\uFEFF/,'');
  const delimiter=(text.split(/\r?\n/,1)[0].match(/;/g)||[]).length>
    (text.split(/\r?\n/,1)[0].match(/,/g)||[]).length?';':',';
  const result:string[][]=[],row:string[]=[];let field='',quoted=false;
  for(let i=0;i<text.length;i++){
    const c=text[i];
    if(c==='"'){
      if(quoted&&text[i+1]==='"'){field+='"';i++;}else quoted=!quoted;
    }else if(c===delimiter&&!quoted){row.push(field.trim());field='';}
    else if((c==='\n'||c==='\r')&&!quoted){
      if(c==='\r'&&text[i+1]==='\n')i++;
      row.push(field.trim());field='';
      if(row.some(Boolean))result.push([...row]);row.length=0;
    }else field+=c;
  }
  if(quoted)throw new Error('CSV inválido: comillas sin cerrar.');
  row.push(field.trim());if(row.some(Boolean))result.push([...row]);
  return result;
}
export function parseIndividualCsv(input:string):ImportRow[]{
  const matrix=parseCsv(input);
  if(matrix.length<2)throw new Error('El archivo CSV no tiene registros.');
  const header=matrix[0].map(h=>h.toLowerCase().trim());
  const key=(name:string)=>header.indexOf(name);
  if(key('filename')<0||key('code')<0)
    throw new Error('El CSV debe incluir columnas filename y code.');
  const seen=new Set<string>();
  return matrix.slice(1).map((columns,i)=>{
    const read=(name:string)=>(columns[key(name)]||'').trim();
    const filename=read('filename'),code=read('code');
    const flank=read('flank')||'unknown',sex=read('sex')||'unknown',
      age=read('age_class')||'unknown';
    if(!filename||!code||code.length>80||filename.length>260)
      throw new Error('Fila '+(i+2)+': filename y code son obligatorios.');
    if(!allowedSides.includes(flank)||!allowedSexes.includes(sex)||!allowedAges.includes(age))
      throw new Error('Fila '+(i+2)+': flanco, sexo o edad no válidos.');
    if(seen.has(filename.toLowerCase()))throw new Error('Fotografía repetida: '+filename);
    seen.add(filename.toLowerCase());
    return {filename,code,alias:read('alias').slice(0,120),species:read('species')||'Panthera onca',
      sex:sex as ImportRow['sex'],age_class:age as ImportRow['age_class'],
      flank:flank as ImportRow['flank'],notes:read('notes').slice(0,800)};
  });
}

export default function CloudLibraryPanel(){
  const {language}=useLanguage();
  const tx=(es:string,en:string)=>language==='en'?en:es;
  const {client,session,ready}=useCloudIdentity();
  const [email,setEmail]=React.useState('');
  const [organizations,setOrganizations]=React.useState<CloudOrg[]>([]);
  const [orgId,setOrgId]=React.useState('');
  const [studies,setStudies]=React.useState<CloudStudy[]>([]);
  const [studyId,setStudyId]=React.useState('');
  const [individuals,setIndividuals]=React.useState<CloudIndividual[]>([]);
  const [photos,setPhotos]=React.useState<CloudPhoto[]>([]);
  const [newOrg,setNewOrg]=React.useState('');
  const [newStudy,setNewStudy]=React.useState('');
  const [country,setCountry]=React.useState('');
  const [rows,setRows]=React.useState<ImportRow[]>([]);
  const [imageFiles,setImageFiles]=React.useState<File[]>([]);
  const [busy,setBusy]=React.useState(false);
  const [notice,setNotice]=React.useState('');
  const [error,setError]=React.useState('');
  const [finished,setFinished]=React.useState(0);

  const reloadOrganizations=React.useCallback(async()=>{
    const all=await listCloudOrganizations();
    setOrganizations(all);setOrgId(previous=>all.some(o=>o.id===previous)?previous:(all[0]?.id||''));
  },[]);
  React.useEffect(()=>{
    if(!session){setOrganizations([]);setOrgId('');return;}
    let canceled=false;
    void listCloudOrganizations().then(all=>{
      if(!canceled){setOrganizations(all);setOrgId(previous=>all.some(o=>o.id===previous)?previous:(all[0]?.id||''));}
    }).catch(e=>{if(!canceled)setError(String(e.message||e));});
    return ()=>{canceled=true;};
  },[session?.user.id]);
  React.useEffect(()=>{
    if(!orgId){setStudies([]);setStudyId('');return;}
    let canceled=false;
    void listCloudStudies(orgId).then(all=>{
      if(!canceled){setStudies(all);setStudyId(previous=>all.some(s=>s.id===previous)?previous:(all[0]?.id||''));}
    }).catch(e=>{if(!canceled)setError(String(e.message||e));});
    return ()=>{canceled=true;};
  },[orgId]);
  const reloadCatalog=React.useCallback(async()=>{
    if(!studyId){setIndividuals([]);setPhotos([]);return;}
    const [people,pictures]=await Promise.all([listCloudIndividuals(studyId),listCloudPhotos(studyId)]);
    setIndividuals(people);setPhotos(pictures);
  },[studyId]);
  React.useEffect(()=>{let ignore=false;
    if(!studyId){setIndividuals([]);setPhotos([]);return;}
    void Promise.all([listCloudIndividuals(studyId),listCloudPhotos(studyId)]).then(([people,pictures])=>{
      if(!ignore){setIndividuals(people);setPhotos(pictures);}
    }).catch(e=>{if(!ignore)setError(String(e.message||e));});
    return ()=>{ignore=true;};
  },[studyId]);
  async function action(callback:()=>Promise<void>){
    setError('');setNotice('');setBusy(true);
    try{await callback();}catch(e){setError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  }
  async function sendAccess(){
    if(!client||!email.includes('@'))return;
    await action(async()=>{
      const {error:e}=await client.auth.signInWithOtp({email:email.trim(),
        options:{emailRedirectTo:location.origin+location.pathname}});
      if(e)throw e;
      setNotice(tx('Revisá tu correo para entrar a la biblioteca privada.',
        'Check your email to access the private library.'));
    });
  }
  async function createOrganization(){
    if(!session||newOrg.trim().length<2)return;
    await action(async()=>{
      await createCloudOrganization(newOrg,session.user.id);setNewOrg('');
      await reloadOrganizations();
    });
  }
  async function createStudy(){
    if(!orgId||newStudy.trim().length<2)return;
    await action(async()=>{
      await createCloudStudy(orgId,newStudy,country);
      setNewStudy('');setCountry('');
      const all=await listCloudStudies(orgId);setStudies(all);setStudyId(all[all.length-1]?.id||'');
    });
  }
  async function readCsv(file:File|null){
    setError('');setNotice('');setRows([]);
    if(!file)return;
    if(file.size>400_000){setError(tx('CSV demasiado grande (máximo 400 KB).','CSV too large (400 KB maximum).'));return;}
    try{
      const parsed=parseIndividualCsv(await file.text());
      if(parsed.length>MAX_BULK)throw new Error(tx(
        'Importá hasta 20 imágenes por lote.','Import up to 20 photos per batch.'));
      setRows(parsed);
    }catch(e){setError(e instanceof Error?e.message:String(e));}
  }
  const filesByName=new Map(imageFiles.map(f=>[f.name.toLowerCase(),f]));
  const missing=rows.filter(row=>!filesByName.has(row.filename.toLowerCase()));
  async function upload(){
    if(!studyId||!orgId||!rows.length||missing.length)return;
    await action(async()=>{
      let uploaded=0;
      for(const row of rows){
        const image=filesByName.get(row.filename.toLowerCase());
        if(!image)throw new Error('Falta la fotografía: '+row.filename);
        await saveCloudReference(orgId,studyId,row,image);
        uploaded++;setFinished(uploaded);
      }
      await reloadCatalog();setRows([]);setImageFiles([]);
      setNotice(tx('Referencias guardadas en biblioteca privada.',
        'References saved to your private study library.'));
    });
  }
  function template(){
    const csv='filename,code,alias,species,sex,age_class,flank,notes\njag001_left.jpg,JAG-001,Estrella,Panthera onca,unknown,unknown,left,Fotografía de referencia\n';
    const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
    const anchor=document.createElement('a');anchor.href=url;anchor.download='pantheralab_plantilla_individuos.csv';
    anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }

  return <section className="cloud-library-panel" aria-label={tx('Biblioteca en la nube','Cloud library')}>
    <div className="cloud-library-header">
      <div><span className="sci-kicker">PANTHERALAB / {tx('BIBLIOTECA PRIVADA','PRIVATE LIBRARY')}</span>
        <h3>{tx('Biblioteca de individuos · Nube','Individual library · Cloud')}</h3>
        <p>{tx('Una biblioteca independiente por institución y estudio. Solo sus miembros autorizados pueden acceder.',
          'Separate libraries by organization and study, accessible only to authorized members.')}</p>
      </div>
      <span className="sci-tag">{cloudConfigured?tx('Configurada','Configured'):tx('Pendiente de conexión','Connection required')}</span>
    </div>
    {!cloudConfigured?<p className="sci-muted cloud-library-note">{tx(
      'La biblioteca está preparada, pero aún no está conectada a un proyecto Supabase. Tus fichas actuales siguen siendo locales; ninguna foto se ha subido a la nube.',
      'Cloud library is prepared but not connected to a Supabase project. Existing local records remain local; no photographs have been uploaded.'
    )}</p>:!ready?<p className="sci-muted">{tx('Verificando sesión privada…','Checking private session…')}</p>:
    !session?<div className="cloud-library-auth">
      <label>{tx('Correo institucional','Institutional email')}
        <input type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="investigador@institucion.org"/>
      </label>
      <button type="button" className="action-button" onClick={()=>void sendAccess()} disabled={busy||!email.includes('@')}>
        {tx('Enviar enlace de acceso','Send sign-in link')}
      </button>
    </div>:<>
      <div className="cloud-library-selects">
        <label>{tx('Institución','Organization')}
          <select value={orgId} onChange={e=>setOrgId(e.target.value)}>
            {!organizations.length&&<option value="">{tx('Sin instituciones','No organizations')}</option>}
            {organizations.map(org=><option key={org.id} value={org.id}>{org.name}</option>)}
          </select>
        </label>
        <label>{tx('Colección / estudio','Collection / study')}
          <select value={studyId} onChange={e=>{setStudyId(e.target.value);setRows([]);setImageFiles([]);}}>
            {!studies.length&&<option value="">{tx('Sin colecciones','No collections')}</option>}
            {studies.map(study=><option key={study.id} value={study.id}>{study.title} · {study.country}</option>)}
          </select>
        </label>
        <button className="sci-secondary" onClick={()=>void client?.auth.signOut()}>{tx('Cerrar sesión','Sign out')}</button>
      </div>
      <details className="method-details cloud-library-setup">
        <summary>{tx('Crear institución o estudio','Create organization or study')}</summary>
        <div className="cloud-library-forms">
          <label>{tx('Nombre de institución','Organization name')}
            <input maxLength={120} value={newOrg} onChange={e=>setNewOrg(e.target.value)}/>
            <button type="button" className="sci-secondary" disabled={busy||newOrg.trim().length<2}
              onClick={()=>void createOrganization()}>{tx('Crear institución','Create organization')}</button>
          </label>
          {!!orgId&&<label>{tx('Nombre del estudio','Study name')}
            <input maxLength={150} value={newStudy} onChange={e=>setNewStudy(e.target.value)}/>
            <input maxLength={80} placeholder={tx('País (opcional)','Country (optional)')}
              value={country} onChange={e=>setCountry(e.target.value)}/>
            <button type="button" className="sci-secondary" disabled={busy||newStudy.trim().length<2}
              onClick={()=>void createStudy()}>{tx('Crear colección','Create collection')}</button>
          </label>}
        </div>
      </details>
      {!!studyId&&<>
        <div className="cloud-library-stats">
          <span>{individuals.length} {tx('individuos registrados','registered individuals')}</span>
          <span>{photos.length} {tx('fotografías de referencia','reference photos')}</span>
        </div>
        <details className="method-details cloud-library-import">
          <summary>{tx('Importar referencias CSV + fotografías','Import CSV + reference photos')}</summary>
          <p>{tx('Seleccioná un CSV con filename y code, y luego sus fotografías con los mismos nombres. Máximo 20 por lote.',
            'Select a CSV with filename and code, then the photos with matching filenames. Up to 20 per batch.')}</p>
          <button type="button" className="sci-secondary" onClick={template}>
            {tx('Descargar plantilla CSV ↓','Download CSV template ↓')}</button>
          <label>{tx('Tabla CSV','CSV table')}
            <input type="file" accept=".csv,text/csv" onChange={e=>{
              void readCsv(e.target.files?.[0]||null);e.target.value='';
            }}/>
          </label>
          <label>{tx('Fotografías del estudio','Study photographs')}
            <input type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={e=>{
              setImageFiles(Array.from(e.target.files||[]));e.target.value='';
            }}/>
          </label>
          {!!rows.length&&<p className="sci-muted">{rows.length} {tx('filas preparadas','rows prepared')} · {imageFiles.length} {tx('archivos elegidos','files selected')}
            {missing.length>0?' · '+missing.length+' '+tx('fotografías faltantes','missing photos'):''}</p>}
          {missing.length>0&&<p className="sci-warning">{tx('Faltan archivos:','Missing files:')} {missing.map(x=>x.filename).slice(0,3).join(', ')}</p>}
          <button type="button" className="action-button"
            disabled={busy||!rows.length||!!missing.length}
            onClick={()=>void upload()}>
            {busy?tx('Guardando…','Saving…'):tx('Guardar referencias privadas','Save private references')}
          </button>
          {busy&&finished>0&&<p className="sci-muted">{finished} / {rows.length}</p>}
        </details>
        {individuals.length>0&&<div className="cloud-library-individuals">
          {individuals.slice(0,50).map(ind=><div key={ind.id}>
            <strong>{ind.code}{ind.alias?' · '+ind.alias:''}</strong>
            <small>{ind.species} · {ind.sex} · {ind.review_status} · {photos.filter(p=>p.individual_id===ind.id).length} {tx('fotografías','photos')}</small>
          </div>)}
        </div>}
      </>}
    </>}
    {notice&&<p className="sci-notice" role="status">{notice}</p>}
    {error&&<p className="sci-warning" role="alert">{error}</p>}
  </section>;
}
