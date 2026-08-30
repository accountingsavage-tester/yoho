export const WORKSPACE_KEY='yoho:workspace:v2';
export type WorkspaceState={section?:string;problem?:string;solution?:unknown;chat?:{role:string;text:string}[]};
export function readWorkspace():WorkspaceState{if(typeof window==='undefined')return{};try{return JSON.parse(localStorage.getItem(WORKSPACE_KEY)||'{}')}catch{return{}}}
export function writeWorkspace(patch:WorkspaceState){if(typeof window==='undefined')return;try{localStorage.setItem(WORKSPACE_KEY,JSON.stringify({...readWorkspace(),...patch}))}catch{}}
