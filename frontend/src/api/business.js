import {api,post} from './client.js';
export const batches={list:()=>api('/batches'),save:(d,id)=>post('/batches'+(id?'/'+id:''),d,id?'PUT':'POST')};
export const mappings={list:()=>api('/mappings'),save:(d,id)=>post('/mappings'+(id?'/'+id:''),d,id?'PUT':'POST')};
export const runs={list:()=>api('/runs'),run:d=>post('/runs',d),cancel:id=>post('/runs/'+id+'/cancel',{}),targets:id=>api('/runs/'+id+'/targets'),restore:(id,backup)=>post('/runs/'+id+'/restore',{backup})};
export const drills={list:()=>api('/drill-packages'),create:d=>post('/drill-packages',d),detail:id=>api('/drill-packages/'+id),append:(id,d)=>post('/drill-packages/'+id+'/appends',d),withdraw:id=>post('/drill-packages/'+id+'/withdraw',{}),reopen:(id,d)=>post('/drill-packages/'+id+'/reopen',d),resume:job=>post('/drill-jobs/'+job+'/resume',{})};
