export type Json = Record<string, any>;
export const uid=()=>crypto.randomUUID().replaceAll('-','');
let credential=sessionStorage.getItem('stk-token')||'';
export const setToken=(value:string)=>{credential=value;sessionStorage.setItem('stk-token',value);};
export const hasToken=()=>!!credential;
export async function api(path:string,method='GET',body?:unknown):Promise<any>{
  const response=await fetch(`/api/v1/${path}`,{method,headers:{Authorization:`Bearer ${credential}`,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});
  const data=await response.json();
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:`请求失败 (${response.status})`);
  return data;
}
export async function action(node_id:string,kind:string,payload:Json,onReview?:(item:Json)=>void):Promise<Json>{
  if(!node_id)throw new Error('请先选择执行节点');
  const body={id:uid(),node_id,kind,payload};
  // Preserve the complete immutable request for an explicit retry after a lost response.
  sessionStorage.setItem('stk-last-action',JSON.stringify(body));
  let item=await api('actions','POST',body);
  if(item.state==='review'){onReview?.(item);return item;}
  const deadline=Date.now()+90000;
  while(item.state==='queued'&&Date.now()<deadline){await new Promise(r=>setTimeout(r,500));item=await api(`actions/${body.id}`);}
  if(item.state==='failed')throw new Error(item.error);
  if(item.state==='queued')throw new Error('操作仍在排队，可在操作列表中继续查看；无需重复提交。');
  return item;
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
