/// <reference types="vite/client" />
/** Prefer same-origin Vercel /api proxy; support an explicitly configured Render static frontend. */
const configured=(import.meta.env.VITE_API_BASE_URL||'').trim().replace(/\/+$/,'');
const API_BASE=/^https:\/\/[a-z0-9.-]+(?::\d+)?$/i.test(configured)?configured:'';

export function apiUrl(path:string):string{
  return path.startsWith('/api/')?API_BASE+path:path;
}

export function apiFetch(input:RequestInfo|URL,init?:RequestInit):Promise<Response>{
  if(typeof input==='string')return fetch(apiUrl(input),init);
  if(input instanceof URL)return fetch(input,init);
  return fetch(input,init);
}
