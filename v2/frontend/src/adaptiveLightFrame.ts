/** PantheraLIVE adaptive illumination for preview-only animal detection.
 *
 * The recorded video is ALWAYS the raw camera stream. Enhanced image pixels
 * are temporary RAM-only inference inputs, not new evidence or night vision.
 * Cannot rescue a totally black sensor frame. Metrics are pixel luminance,
 * not calibrated lux or a scientifically validated exposure measurement.
 */
export type LightCondition='normal'|'dim'|'too_dark';
export type DetectionFrame={
  source:HTMLVideoElement|HTMLCanvasElement;
  condition:LightCondition;
  brightness:number;
  enhanced:boolean;
};

export class AdaptiveLightFrame {
  private sample=document.createElement('canvas');
  private canvas=document.createElement('canvas');
  private sampleContext:CanvasRenderingContext2D|null;
  private context:CanvasRenderingContext2D|null;
  constructor(){
    this.sample.width=80;this.sample.height=45;
    this.canvas.width=320;this.canvas.height=180;
    this.sampleContext=this.sample.getContext('2d',{willReadFrequently:true});
    this.context=this.canvas.getContext('2d',{willReadFrequently:true});
  }

  prepare(video:HTMLVideoElement):DetectionFrame{
    const sc=this.sampleContext,ctx=this.context;
    if(!sc||!ctx||video.readyState<2)
      return {source:video,condition:'normal',brightness:-1,enhanced:false};
    const w=video.videoWidth,h=video.videoHeight;
    if(w===0||h===0)return {source:video,condition:'normal',brightness:-1,enhanced:false};
    sc.drawImage(video,0,0,this.sample.width,this.sample.height);
    const data=sc.getImageData(0,0,this.sample.width,this.sample.height).data;
    let luminance=0,dark=0,n=0;
    for(let i=0;i<data.length;i+=4){
      const y=.2126*data[i]+.7152*data[i+1]+.0722*data[i+2];
      luminance+=y;n++;
      if(y<12)dark++;
    }
    const brightness=luminance/Math.max(1,n);
    // Too little sensor information; avoid turning noise into "an animal".
    if(brightness<11||dark/n>.92)
      return {source:video,condition:'too_dark',brightness,enhanced:false};
    if(brightness>=82)
      return {source:video,condition:'normal',brightness,enhanced:false};

    // A gentle gamma lift can improve dim real frames (also IR greyscale).
    // No artificial data is written to the saved video.
    ctx.drawImage(video,0,0,this.canvas.width,this.canvas.height);
    const image=ctx.getImageData(0,0,this.canvas.width,this.canvas.height);
    const px=image.data;
    const gamma=brightness<30?.54:brightness<50?.68:.82;
    const lut=new Uint8Array(256);
    for(let i=0;i<256;i++){
      const lit=255*Math.pow(i/255,gamma);
      lut[i]=Math.round(Math.min(255,lit));
    }
    for(let i=0;i<px.length;i+=4){
      px[i]=lut[px[i]];px[i+1]=lut[px[i+1]];px[i+2]=lut[px[i+2]];
    }
    ctx.putImageData(image,0,0);
    return {source:this.canvas,condition:'dim',brightness,enhanced:true};
  }
}
