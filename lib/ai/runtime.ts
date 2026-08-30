export type GpuDiagnostics={webgpu:boolean;adapter:boolean;device:boolean;reason?:string};

export async function diagnoseGpu():Promise<GpuDiagnostics>{
 if(typeof navigator==='undefined'||!(navigator as any).gpu)return{webgpu:false,adapter:false,device:false,reason:'WebGPU is not exposed by this browser.'};
 try{const adapter=await(navigator as any).gpu.requestAdapter();if(!adapter)return{webgpu:true,adapter:false,device:false,reason:'WebGPU is available, but no compatible GPU adapter was returned.'};const device=await adapter.requestDevice();return{webgpu:true,adapter:true,device:!!device};}
 catch(e:any){return{webgpu:true,adapter:false,device:false,reason:e?.message||'GPU initialization failed.'};}
}

export async function requestPersistentStorage():Promise<boolean>{try{return !!navigator.storage?.persist&&await navigator.storage.persist()}catch{return false}}

const KEY='yoho:ai-runtime:v2';
export function saveAiRuntimeState(state:Record<string,unknown>){try{localStorage.setItem(KEY,JSON.stringify({...state,updatedAt:Date.now()}))}catch{}}
export function loadAiRuntimeState():Record<string,unknown>|null{try{const raw=localStorage.getItem(KEY);return raw?JSON.parse(raw):null}catch{return null}}
export function clearAiRuntimeState(){try{localStorage.removeItem(KEY)}catch{}}
