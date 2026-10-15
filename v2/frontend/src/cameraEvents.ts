export type CameraFireCandidate = {
  id:string;
  camera_id:string;
  recorded_at:string;
  signal:'smoke'|'flame';
  source:'virtual_camera_simulation';
  simulation:true;
  verified:false;
};
