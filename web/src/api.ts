export type Json = Record<string, any>;
export const uid=()=>crypto.randomUUID().replaceAll('-','');
let credential=sessionStorage.getItem('stk-token')||'';
export const setToken=(value:string)=>{credential=value;sessionStorage.setItem('stk-token',value);};
export const hasToken=()=>!!credential;
export class ApiError extends Error {
  constructor(readonly status: number, message: string) { super(message); }
}
export async function api(path:string,method='GET',body?:unknown,signal?:AbortSignal):Promise<any>{
  const response=await fetch(`/api/v1/${path}`,{method,headers:{Authorization:`Bearer ${credential}`,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),cache:'no-store',signal});
  // A proxy or gateway error page is not JSON: report the HTTP status instead of a parse error.
  const data=await response.json().catch(()=>{if(response.ok)throw new Error(`控制服务返回了无效数据 (${response.status})`);return null;});
  if(!response.ok)throw new ApiError(response.status,typeof data?.detail==='string'?data.detail:`请求失败 (${response.status})`);
  return data;
}
export async function readNode(node: string, kind: string, payload: Json, signal?: AbortSignal): Promise<unknown> {
  const response = await api(`nodes/${encodeURIComponent(node)}/read`, 'POST', {kind, payload}, signal);
  return response?.result;
}
/**
 * remember: keep the request for an explicit retry (default true); timeoutMs: how long to poll a queued action;
 * keepQueued: return an action still queued after timeoutMs instead of throwing, so long-running callers
 * (graph.evaluate waiting behind other evaluations) keep polling it themselves; active: polling stops (and the
 * pending action is returned) once it reports false, e.g. after the requesting view was closed.
 */
export interface ActionOptions{remember?:boolean,timeoutMs?:number,keepQueued?:boolean,active?:()=>boolean}
export async function action(node_id:string,kind:string,payload:Json,onReview?:(item:Json)=>void,options:ActionOptions={}):Promise<Json>{
  if(!node_id)throw new Error('请先选择执行节点');
  const body={id:uid(),node_id,kind,payload};
  const token=credential;
  const active=()=>token===credential&&(options.active?.()??true);
  // Preserve the complete immutable request for an explicit retry after a lost response.
  // Background polls (task.events) do not replace the user's last explicit action.
  if(options.remember!==false)sessionStorage.setItem('stk-last-action',JSON.stringify(body));
  let item=await api('actions','POST',body);
  if(item.state==='review'){if(active())onReview?.(item);return item;}
  const deadline=Date.now()+(options.timeoutMs??90000);
  while(item.state==='queued'&&Date.now()<deadline&&active()){await new Promise(r=>setTimeout(r,500));if(!active())break;item=await api(`actions/${body.id}`);}
  if(!active())return item;
  if(item.state==='failed')throw new Error(item.error);
  if(item.state==='queued'&&!options.keepQueued)throw new Error('操作仍在排队，可在操作列表中继续查看；无需重复提交。');
  return item;
}
// Content-addressed hub blob (payload buffers, plots, images) with the same bearer credential.
// The hub marks blobs private and immutable; the viewer also keeps a verified in-memory cache.
export async function blob(sha256:string,signal?:AbortSignal,maxBytes?:number):Promise<ArrayBuffer>{
  if(!/^[0-9a-f]{64}$/.test(sha256))throw new Error('无效的数据块标识');
  const response=await fetch(`/api/v1/blobs/${sha256}`,{headers:{Authorization:`Bearer ${credential}`},signal});
  if(!response.ok)throw new Error(response.status===404?'数据块尚未上传到控制服务':`数据块读取失败 (${response.status})`);
  if(maxBytes===undefined)return response.arrayBuffer();
  const tooLarge=()=>new Error('数据块超过声明的大小');
  if(Number(response.headers.get('content-length'))>maxBytes){
    await response.body?.cancel();
    throw tooLarge();
  }
  const reader=response.body?.getReader();
  if(!reader)throw new Error('无法读取数据块内容');
  const bytes=new Uint8Array(maxBytes);
  let offset=0;
  try{
    while(true){
      const {done,value}=await reader.read();
      if(done)return bytes.buffer.slice(0,offset);
      if(value.length>maxBytes-offset){await reader.cancel();throw tooLarge();}
      bytes.set(value,offset);offset+=value.length;
    }
  }finally{reader.releaseLock();}
}
export async function events(onEvent:()=>void,signal:AbortSignal){
  const token=credential;
  const active=()=>!signal.aborted&&token===credential;
  let cursor=Number(sessionStorage.getItem('stk-event-cursor')||0);
  while(active()){
    try{
      const response=await fetch(`/api/v1/events?after=${cursor}`,{headers:{Authorization:`Bearer ${token}`},signal,cache:'no-store'});
      if(response.status===401||response.status===403)return;
      if(!response.ok||!response.body)throw new Error('Event connection unavailable');
      const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
      try{while(active()){const {value,done}=await reader.read();if(done||!active())break;buffer+=decoder.decode(value,{stream:true});let end;
        while((end=buffer.indexOf('\n\n'))>=0){const packet=buffer.slice(0,end);buffer=buffer.slice(end+2);const id=/^id: (\d+)$/m.exec(packet);if(id){cursor=Number(id[1]);sessionStorage.setItem('stk-event-cursor',String(cursor));onEvent();}}
      }}finally{await reader.cancel();}
    }catch(error){if(!active())return;}
    await new Promise(r=>setTimeout(r,2000));
  }
}
