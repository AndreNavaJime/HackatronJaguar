import React from 'react';

export type ImageRegion={x:number;y:number;w:number;h:number};
type Props={file:File;value:ImageRegion|null;onChange:(crop:ImageRegion|null)=>void;
  language:string;title?:string};

export async function cropSelectedFile(file:File,region:ImageRegion|null):Promise<File>{
  if(!region)return file;
  const picture=await createImageBitmap(file,{imageOrientation:'from-image'});
  try{
    const x=Math.floor(picture.width*region.x);
    const y=Math.floor(picture.height*region.y);
    const w=Math.max(1,Math.floor(picture.width*region.w));
    const h=Math.max(1,Math.floor(picture.height*region.h));
    const canvas=document.createElement('canvas');
    // Keep uploaded croppings small on memory-limited Render.
    const scale=Math.min(1,800/Math.max(w,h));
    canvas.width=Math.max(1,Math.round(w*scale));
    canvas.height=Math.max(1,Math.round(h*scale));
    const context=canvas.getContext('2d');
    if(!context)throw new Error('No se pudo crear el recorte.');
    context.drawImage(picture,x,y,w,h,0,0,canvas.width,canvas.height);
    const blob=await new Promise<Blob>((resolve,reject)=>{
      canvas.toBlob(output=>output?resolve(output):reject(new Error('No se pudo exportar el recorte.')),
        'image/jpeg',0.86);
    });
    return new File([blob],file.name.replace(/\.[^.]+$/,'')+'-flanco.jpg',{type:'image/jpeg'});
  }finally{picture.close();}
}

export default function FlankCropPicker({file,value,onChange,language,title}:Props){
  const [preview,setPreview]=React.useState('');
  const [draft,setDraft]=React.useState<ImageRegion|null>(null);
  const anchor=React.useRef<{x:number;y:number}|null>(null);
  React.useEffect(()=>{
    const url=URL.createObjectURL(file);setPreview(url);setDraft(null);
    return ()=>URL.revokeObjectURL(url);
  },[file]);
  const coords=(event:React.PointerEvent<HTMLDivElement>)=>{
    const rect=event.currentTarget.getBoundingClientRect();
    return {x:Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width)),
      y:Math.max(0,Math.min(1,(event.clientY-rect.top)/rect.height))};
  };
  const rectangle=(a:{x:number;y:number},b:{x:number;y:number})=>({
    x:Math.min(a.x,b.x),y:Math.min(a.y,b.y),
    w:Math.abs(a.x-b.x),h:Math.abs(a.y-b.y)
  });
  const active=draft||value;
  const es=language!=='en';
  return <div className="flank-crop-picker">
    {title&&<strong>{title}</strong>}
    <div className="flank-crop-image" role="group"
      aria-label={es?'Arrastrá sobre el cuerpo para recortar el flanco':'Drag over the body to crop the flank'}
      onPointerDown={event=>{
        if(event.button!==0)return;
        anchor.current=coords(event);setDraft(null);
        event.currentTarget.setPointerCapture(event.pointerId);
      }}
      onPointerMove={event=>{
        if(anchor.current){setDraft(rectangle(anchor.current,coords(event)));}
      }}
      onPointerUp={event=>{
        if(!anchor.current)return;
        const next=rectangle(anchor.current,coords(event));
        anchor.current=null;setDraft(null);
        if(next.w>=.06&&next.h>=.06)onChange(next);
        if(event.currentTarget.hasPointerCapture(event.pointerId))
          event.currentTarget.releasePointerCapture(event.pointerId);
      }}
      onPointerCancel={()=>{anchor.current=null;setDraft(null);}}>
      {preview&&<img src={preview} alt={es?'Vista para seleccionar el costado':'View to select the flank'} draggable={false}/>}
      {active&&<div className="flank-crop-selection" style={{
        left:(active.x*100)+'%',top:(active.y*100)+'%',
        width:(active.w*100)+'%',height:(active.h*100)+'%'
      }}/>}
    </div>
    <div className="flank-crop-footer">
      <small>{value?(es?'Se comparará solo la región marcada.':'Only the selected region will be compared.')
        :(es?'Arrastrá sobre el costado para excluir el fondo. Si no seleccionás, se compara toda la foto.':
          'Drag over the flank to exclude background. Without a selection, the whole photo is compared.')}</small>
      {value&&<button type="button" onClick={()=>onChange(null)}>{es?'Quitar recorte':'Clear crop'}</button>}
    </div>
  </div>;
}
