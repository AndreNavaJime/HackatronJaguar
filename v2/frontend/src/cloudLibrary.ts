import {createClient, type SupabaseClient, type Session} from '@supabase/supabase-js';
import React from 'react';

export type CloudOrg={id:string;name:string;created_at:string};
export type CloudStudy={id:string;organization_id:string;title:string;country:string};
export type CloudIndividual={id:string;organization_id:string;study_id:string;code:string;
  alias:string;species:string;sex:'female'|'male'|'unknown';
  age_class:'unknown'|'juvenile'|'subadult'|'adult';review_status:'provisional'|'verified';notes:string};
export type CloudPhoto={id:string;organization_id:string;study_id:string;individual_id:string;
  filename:string;storage_path:string;flank:'left'|'right'|'unknown';photo_review_status:string};
export type ImportRow={filename:string;code:string;alias:string;species:string;
  sex:'female'|'male'|'unknown';age_class:'unknown'|'juvenile'|'subadult'|'adult';
  flank:'left'|'right'|'unknown';notes:string};

const url=String(import.meta.env.VITE_SUPABASE_URL||'').trim();
const key=String(import.meta.env.VITE_SUPABASE_ANON_KEY||'').trim();
const validUrl=/^https:\/\/[a-z0-9.-]+\.supabase\.co\/?$/i.test(url);
export const cloudConfigured=validUrl&&key.length>24&&!/(service_role|secret)/i.test(key);
let singleton:SupabaseClient|null=null;
export function cloudClient():SupabaseClient|null{
  if(!cloudConfigured)return null;
  if(!singleton)singleton=createClient(url.replace(/\/$/,''),key,{
    auth:{persistSession:true,autoRefreshToken:true,detectSessionInUrl:true},
  });
  return singleton;
}
export function useCloudIdentity(){
  const [session,setSession]=React.useState<Session|null>(null);
  const [ready,setReady]=React.useState(!cloudConfigured);
  React.useEffect(()=>{
    const client=cloudClient();if(!client)return;
    let mounted=true;
    void client.auth.getSession().then(({data})=>{
      if(mounted){setSession(data.session);setReady(true);}
    }).catch(()=>{if(mounted)setReady(true);});
    const {data:subscription}=client.auth.onAuthStateChange((_event,next)=>{
      if(mounted){setSession(next);setReady(true);}
    });
    return ()=>{mounted=false;subscription.subscription.unsubscribe();};
  },[]);
  return {client:cloudClient(),session,ready};
}
function requireCloud(){
  const client=cloudClient();
  if(!client)throw new Error('Conectá primero un proyecto Supabase autorizado.');
  return client;
}
export async function listCloudOrganizations():Promise<CloudOrg[]>{
  const {data,error}=await requireCloud().from('pl_organizations')
    .select('id,name,created_at').order('created_at',{ascending:false}).limit(100);
  if(error)throw error;
  return (data||[]) as CloudOrg[];
}
export async function createCloudOrganization(name:string,userId:string):Promise<void>{
  const {error}=await requireCloud().from('pl_organizations')
    .insert({name:name.trim(),created_by:userId});
  if(error)throw error;
}
export async function listCloudStudies(orgId:string):Promise<CloudStudy[]>{
  const {data,error}=await requireCloud().from('pl_studies')
    .select('id,organization_id,title,country').eq('organization_id',orgId).limit(100);
  if(error)throw error;
  return (data||[]) as CloudStudy[];
}
export async function createCloudStudy(orgId:string,title:string,country:string):Promise<void>{
  const {error}=await requireCloud().from('pl_studies')
    .insert({organization_id:orgId,title:title.trim(),country:country.trim()});
  if(error)throw error;
}
export async function listCloudIndividuals(studyId:string):Promise<CloudIndividual[]>{
  const {data,error}=await requireCloud().from('pl_individuals')
    .select('id,organization_id,study_id,code,alias,species,sex,age_class,review_status,notes')
    .eq('study_id',studyId).order('code').limit(1500);
  if(error)throw error;
  return (data||[]) as CloudIndividual[];
}
export async function listCloudPhotos(studyId:string):Promise<CloudPhoto[]>{
  const {data,error}=await requireCloud().from('pl_reference_photos')
    .select('id,organization_id,study_id,individual_id,filename,storage_path,flank,photo_review_status')
    .eq('study_id',studyId).limit(1500);
  if(error)throw error;
  return (data||[]) as CloudPhoto[];
}
export async function saveCloudReference(orgId:string,studyId:string,row:ImportRow,file:File):Promise<void>{
  if(!['image/jpeg','image/png','image/webp'].includes(file.type)||file.size>8*1024*1024)
    throw new Error('Cada foto debe ser JPG, PNG o WebP de hasta 8 MB.');
  const client=requireCloud();
  // Only reuse the code within the *selected study*. Never match on alias or filename.
  const {data:existing,error:lookupError}=await client.from('pl_individuals')
    .select('id').eq('study_id',studyId).eq('code',row.code).maybeSingle();
  if(lookupError)throw lookupError;
  let individualId=existing?.id as string|undefined;
  if(!individualId){
    const {data,error}=await client.from('pl_individuals').insert({
      organization_id:orgId,study_id:studyId,code:row.code,alias:row.alias,
      species:row.species||'Panthera onca',sex:row.sex,
      age_class:row.age_class,review_status:'provisional',notes:row.notes,
    }).select('id').single();
    if(error)throw error;
    individualId=data.id;
  }
  const extension=file.type==='image/png'?'png':file.type==='image/webp'?'webp':'jpg';
  const storagePath=`${orgId}/${studyId}/${crypto.randomUUID()}.${extension}`;
  const {error:uploadError}=await client.storage.from('pantheralab-private').upload(storagePath,file,{
    contentType:file.type,cacheControl:'3600',upsert:false,
  });
  if(uploadError)throw uploadError;
  const {error:photoError}=await client.from('pl_reference_photos').insert({
    organization_id:orgId,study_id:studyId,individual_id:individualId,
    storage_path:storagePath,filename:file.name,flank:row.flank,
  });
  if(photoError){
    await client.storage.from('pantheralab-private').remove([storagePath]).catch(()=>null);
    throw photoError;
  }
}
export async function getPrivateReferenceFile(photo:CloudPhoto):Promise<File>{
  const client=requireCloud();
  const {data,error}=await client.storage.from('pantheralab-private')
    .createSignedUrl(photo.storage_path,60);
  if(error||!data?.signedUrl)throw error||new Error('Sin acceso a fotografía privada.');
  const response=await fetch(data.signedUrl,{cache:'no-store'});
  if(!response.ok)throw new Error('No se pudo recuperar la fotografía autorizada.');
  const blob=await response.blob();
  if(blob.size>8*1024*1024)throw new Error('La fotografía supera 8 MB.');
  return new File([blob],photo.filename,{type:blob.type||'image/jpeg'});
}
