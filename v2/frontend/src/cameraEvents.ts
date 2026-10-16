export type CameraFireCandidate={
  id:string;
  camera_id:string;
  recorded_at:string;
  signal:'smoke'|'flame';
  source:'virtual_fire_simulation'|'pyroengine_browser_camera';
  simulation:boolean;
  verified:false;
  confidence?:number;
};
