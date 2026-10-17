/** Lightweight local-only detector for the PantheraLIVE mobile proof of concept.
 * COCO-SSD is not MegaDetector, SpeciesNet, or a validated wild-jaguar classifier.
 * Loading weights for the first time requires access to Google's public model host.
 */
import * as tf from '@tensorflow/tfjs-core';
import '@tensorflow/tfjs-backend-cpu';
import '@tensorflow/tfjs-backend-webgl';
import * as coco from '@tensorflow-models/coco-ssd';

export type AnimalPrediction={class:string;score:number;bbox:[number,number,number,number]};
export const COCO_ANIMALS=new Set(['bird','cat','dog','horse','sheep','cow','elephant','bear','zebra','giraffe']);
export const MODEL_TITLE='COCO-SSD Lite · demostración local';
let cached:Promise<coco.ObjectDetection>|null=null;
export async function loadLocalAnimalModel():Promise<{
  detect:(video:HTMLVideoElement)=>Promise<AnimalPrediction[]>;
  backend:string;
}>{
  if(!cached)cached=(async()=>{
    try{
      await tf.setBackend('webgl');
      await tf.ready();
    }catch{
      await tf.setBackend('cpu');
      await tf.ready();
    }
    return coco.load({base:'lite_mobilenet_v2'});
  })().catch(e=>{cached=null;throw e;});
  const model=await cached;
  // Return weaker candidates for multi-frame confirmation in PantheraLIVE.
  // Scores are detection confidences, not probabilities of animal identity.
  return {detect:(video)=>model.detect(video,15,.28),backend:tf.getBackend()};
}
