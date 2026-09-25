export type Json = Record<string, any>;
export const uid=()=>crypto.randomUUID().replaceAll('-','');
let credential=sessionStorage.getItem('stk-token')||'';
export const setToken=(value:string)=>{credential=value;sessionStorage.setItem('stk-token',value);};
export const hasToken=()=>!!credential;
export async function api(path:string,method='GET',body?:unknown):Promise<any>{
  const response=await fetch(`/api/v1/${path}`,{method,headers:{Authorization:`Bearer ${credential}`,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});
  // A proxy or gateway error page is not JSON: report the HTTP status instead of a parse error.
  const data=await response.json().catch(()=>{if(response.ok)throw new Error(`控制服务返回了无效数据 (${response.status})`);return null;});
  if(!response.ok)throw new Error(typeof data?.detail==='string'?data.detail:`请求失败 (${response.status})`);
  return data;
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
  // Preserve the complete immutable request for an explicit retry after a lost response.
  // Background polls (task.events) do not replace the user's last explicit action.
  if(options.remember!==false)sessionStorage.setItem('stk-last-action',JSON.stringify(body));
  let item=await api('actions','POST',body);
  if(item.state==='review'){onReview?.(item);return item;}
  const deadline=Date.now()+(options.timeoutMs??90000);
  const active=options.active??(()=>true);
  while(item.state==='queued'&&Date.now()<deadline&&active()){await new Promise(r=>setTimeout(r,500));if(!active())break;item=await api(`actions/${body.id}`);}
  if(!active())return item;
  if(item.state==='failed')throw new Error(item.error);
  if(item.state==='queued'&&!options.keepQueued)throw new Error('操作仍在排队，可在操作列表中继续查看；无需重复提交。');
  return item;
}
// Content-addressed hub blob (payload buffers, plots, images) with the same bearer credential.
// The hub marks blobs private and immutable; the viewer also keeps a verified in-memory cache.
export async function blob(sha256:string,signal?:AbortSignal):Promise<ArrayBuffer>{
  if(!/^[0-9a-f]{64}$/.test(sha256))throw new Error('无效的数据块标识');
  const response=await fetch(`/api/v1/blobs/${sha256}`,{headers:{Authorization:`Bearer ${credential}`},signal});
  if(!response.ok)throw new Error(response.status===404?'数据块尚未上传到控制服务':`数据块读取失败 (${response.status})`);
  return response.arrayBuffer();
}
export async function events(onEvent:()=>void,signal:AbortSignal){
  let cursor=Number(sessionStorage.getItem('stk-event-cursor')||0);
  while(!signal.aborted){
    try{
      const response=await fetch(`/api/v1/events?after=${cursor}`,{headers:{Authorization:`Bearer ${credential}`},signal,cache:'no-store'});
      if(!response.ok||!response.body)throw new Error('Event connection unavailable');
      const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
      try{while(!signal.aborted){const {value,done}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});let end;
        while((end=buffer.indexOf('\n\n'))>=0){const packet=buffer.slice(0,end);buffer=buffer.slice(end+2);const id=/^id: (\d+)$/m.exec(packet);if(id){cursor=Number(id[1]);sessionStorage.setItem('stk-event-cursor',String(cursor));onEvent();}}
      }}finally{await reader.cancel();}
    }catch(error){if(signal.aborted)return;}
    await new Promise(r=>setTimeout(r,2000));
  }
}
