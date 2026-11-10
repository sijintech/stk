// Hub conversations for the Web workbench: the saved list, the selected conversation's transcript, per-conversation
// drafts and explicit sends. Navigation is read-only: a saved transcript is read only through the non-creating
// GET sessions/{id}/history, a new conversation is a local ID until its first explicit send, and a session is
// created on the Hub only by POST sessions/{id}/messages. That POST is sent only for an ID this page made or whose
// history the Hub returned: a list row alone may be stale, so it confirms a stored choice but does not enable 发送.
// Only the Hub's own "Session not found" means a conversation does not exist; any other 404 (a proxy, a Hub without
// the read-only history) is a read failure with 重新读取, and nothing falls back to a creating request.
// Every read and send is keyed by its own conversation ID and applied only to that conversation. Hub messages are
// immutable and keyed by ID, so observations of one transcript are merged and a late answer never hides newer ones.
import {useCallback,useEffect,useRef,useState} from 'react';
import {api,ApiError,type Json,uid} from './api';

export type SessionRow={id:string;name:string;created:number;label?:string};
export const conversationTitle=(row:SessionRow)=>row.name==='新会话'&&row.label?row.label:row.name;
export type Thread={status:'loading'|'ready'|'missing'|'error';messages:Json[];error?:string};
// The one unsent message of a conversation. Its ID is kept while it is sending or after it failed, so sending the
// same text in the same conversation again reuses it: the Hub, which may already have recorded that message (or
// even its reply) before the error reached us, ignores a repeated ID, so the message is recorded once.
export type Outgoing={id:string;content:string;state:'sending'|'failed';error?:string};
// A history entry: 'local' is a new conversation of this page the Hub has not listed, 'saved' a listed one,
// 'missing' one the Hub said it does not have, 'unconfirmed' a stored or chosen ID whose read has not answered.
export type Entry={id:string;kind:'local'|'saved'|'missing'|'unconfirmed';name:string;created:number;draft:boolean;outgoing?:Outgoing['state']};
const SESSION_ID=/^[0-9a-f]{32}$/;
const STORED='stk-session';
const MAX_MESSAGE_LENGTH=12000;
const tooLong=(text:string)=>text.length>MAX_MESSAGE_LENGTH&&Array.from(text).length>MAX_MESSAGE_LENGTH;
const lostAccess=(error:unknown)=>error instanceof ApiError&&(error.status===401||error.status===403);
const absent=(error:unknown)=>error instanceof ApiError&&error.status===404&&error.message==='Session not found';
const readError=(error:unknown)=>error instanceof ApiError&&error.status===404?
  `控制服务没有提供只读对话历史（${error.message}），可能是代理或较旧的控制服务；没有创建会话`:String(error);
const without=<T,>(record:Record<string,T>,key:string)=>{if(!(key in record))return record;const next={...record};delete next[key];return next;};
const add=(ids:ReadonlySet<string>,id:string)=>ids.has(id)?ids:new Set(ids).add(id);
const remove=(ids:ReadonlySet<string>,id:string)=>{if(!ids.has(id))return ids;const next=new Set(ids);next.delete(id);return next;};
// Union by message ID in the Hub's creation order (the order of observation when a message has no time).
function merge(known:Json[],incoming:unknown):Json[]{
  if(!Array.isArray(incoming))return known;
  const seen=new Set(known.map(m=>m?.id)),extra=incoming.filter(m=>m&&!seen.has(m.id)&&seen.add(m.id));
  if(!extra.length)return known;
  const all=[...known,...extra];
  return all.every(m=>typeof m.created==='number')?all.sort((a,b)=>a.created-b.created):all;
}

export function useConversations(onAccessLost:()=>void,onSent:()=>void){
  // A stored browser choice is only a candidate: it is restored once the list or the history read confirms it.
  const [initial]=useState(()=>{
    const stored=sessionStorage.getItem(STORED)||'';
    return SESSION_ID.test(stored)?{id:stored,restored:true}:{id:uid(),restored:false};
  });
  const [session,setSession]=useState(initial.id);
  const [saved,setSaved]=useState<Record<string,SessionRow>>({});
  // own: IDs this page made, which 发送 may create. posted: those with a send attempt, which the Hub may have recorded.
  const [own,setOwn]=useState<ReadonlySet<string>>(()=>new Set(initial.restored?[]:[initial.id]));
  const [posted,setPosted]=useState<ReadonlySet<string>>(()=>new Set());
  const [missing,setMissing]=useState<ReadonlySet<string>>(()=>new Set());
  const [verified,setVerified]=useState<ReadonlySet<string>>(()=>new Set());
  const [threads,setThreads]=useState<Record<string,Thread>>(()=>({[initial.id]:{status:initial.restored?'loading':'ready',messages:[]}}));
  const [drafts,setDrafts]=useState<Record<string,string>>({});
  const [outgoing,setOutgoing]=useState<Record<string,Outgoing>>({});
  const selected=useRef(initial.id),alive=useRef(true),reader=useRef<AbortController|null>(null);
  // Conversations with a send in flight, updated synchronously so a second submit in the same tick is refused.
  const inflight=useRef(new Set<string>());
  // Read order guards request identity. The applied order fences read failures after a successful send.
  // A positive snapshot can contain newer messages regardless of when a send response was delivered.
  const order=useRef(0),latest=useRef(new Map<string,number>()),applied=useRef(new Map<string,number>());
  const callbacks=useRef({onAccessLost,onSent}),current=useRef({drafts,own});
  callbacks.current={onAccessLost,onSent};current.current={drafts,own};

  // The Hub has this conversation. Once confirmed, the local ID no longer has permission to create it.
  const confirm=useCallback((id:string)=>{
    setVerified(ids=>add(ids,id));setMissing(ids=>remove(ids,id));setOwn(ids=>remove(ids,id));
    setSaved(rows=>rows[id]?rows:{...rows,[id]:{id,name:'新会话',created:Date.now()/1000}});
  },[]);
  const choose=useCallback((id:string)=>{
    reader.current?.abort();reader.current=null;
    selected.current=id;setSession(id);
  },[]);
  const begin=useCallback((draft='')=>{
    const id=uid();
    setOwn(ids=>add(ids,id));
    setThreads(all=>({...all,[id]:{status:'ready',messages:[]}}));
    if(draft)setDrafts(all=>({...all,[id]:draft}));
    choose(id);
  },[choose]);
  const read=useCallback((id:string,restoring=false)=>{
    reader.current?.abort();
    const controller=new AbortController();reader.current=controller;
    const request=++order.current;latest.current.set(id,request);
    const latestRead=()=>!controller.signal.aborted&&alive.current&&latest.current.get(id)===request;
    setThreads(all=>({...all,[id]:{status:'loading',messages:all[id]?.messages??[]}}));
    api(`sessions/${id}/history`,'GET',undefined,controller.signal).then((result:Json)=>{
      if(!latestRead())return;
      applied.current.set(id,Math.max(applied.current.get(id)??0,request));confirm(id);
      setThreads(all=>({...all,[id]:{status:'ready',messages:merge(all[id]?.messages??[],result?.messages)}}));
    },(error:unknown)=>{
      if(!latestRead()||(applied.current.get(id)??0)>=request)return;
      if(lostAccess(error)){callbacks.current.onAccessLost();return;}
      if(absent(error)){
        applied.current.set(id,request);
        // An ID of this page that the Hub has not recorded (yet): it stays a new conversation and its send may still create it.
        if(current.current.own.has(id)){setThreads(all=>({...all,[id]:{status:'ready',messages:all[id]?.messages??[]}}));return;}
        setMissing(ids=>add(ids,id));
        setThreads(all=>({...all,[id]:{status:'missing',messages:[]}}));
        // A stored choice the Hub does not have is dropped for a fresh local draft; its unsent text moves along.
        if(restoring&&selected.current===id){sessionStorage.removeItem(STORED);begin(current.current.drafts[id]||'');setDrafts(all=>without(all,id));}
        return;
      }
      setThreads(all=>({...all,[id]:{status:'error',messages:all[id]?.messages??[],error:readError(error)}}));
    });
  },[begin,confirm]);

  useEffect(()=>{
    alive.current=true;
    if(initial.restored)read(initial.id,true);
    return()=>{alive.current=false;reader.current?.abort();};
  },[initial,read]);
  const sendable=(id:string)=>(own.has(id)||verified.has(id))&&!missing.has(id);
  // The browser keeps the choice of a listed conversation only; a local draft or a missing ID is not kept.
  useEffect(()=>{
    if(saved[session]&&!missing.has(session))sessionStorage.setItem(STORED,session);
    else if(own.has(session)||missing.has(session))sessionStorage.removeItem(STORED);
  },[session,saved,own,missing]);

  // Explicit choice: show what is already known at once and read the saved transcript. A new conversation of this
  // page is read only after a send attempt, to show what the Hub recorded of it.
  const select=(id:string)=>{
    if(!SESSION_ID.test(id))return;
    choose(id);
    if(!own.has(id)||posted.has(id))read(id);
  };
  const empty=(id:string)=>own.has(id)&&!saved[id]&&!drafts[id]?.trim()&&!outgoing[id]&&!threads[id]?.messages.length;
  // New conversation: reuse the current local draft while it is still empty, otherwise start another local ID.
  const startNew=()=>{if(empty(selected.current))choose(selected.current);else begin();};
  // The unsent text of a conversation the Hub does not have, moved to a new local conversation where it can be sent.
  const moveDraft=()=>{
    const id=selected.current,text=drafts[id]??'';
    if(!missing.has(id)||!text.trim())return;
    setDrafts(all=>without(all,id));begin(text);
  };
  const setDraft=(text:string)=>{const id=selected.current;setDrafts(all=>({...all,[id]:text}));};
  // The list only adds or renames rows: a list that started before a send cannot remove what the send confirmed.
  const mergeList=useCallback((rows:unknown)=>{
    if(!Array.isArray(rows))return;
    setSaved(previous=>{
      let next=previous;
      for(const row of rows){
        if(!row||typeof row.id!=='string'||!SESSION_ID.test(row.id))continue;
        const known=next[row.id];
        const value={id:row.id,name:typeof row.name==='string'&&row.name?row.name:'新会话',
          created:Number(row.created)||0,label:typeof row.label==='string'&&row.label?row.label:known?.label};
        if(known&&known.name===value.name&&known.created===value.created&&known.label===value.label)continue;
        if(next===previous)next={...previous};
        next[row.id]=value;
      }
      return next;
    });
  },[]);
  // An ambiguous failure may already have committed. Resolve it by its original ID before sending another
  // message in this conversation. The other draft can still be edited and survives a retry.
  async function post(id:string,content:string){
    const earlier=outgoing[id];
    const retry=earlier?.state==='failed';
    if(!content.trim()||tooLong(content)||inflight.current.has(id)||!sendable(id)||(retry&&earlier.content!==content))return;
    inflight.current.add(id);
    const message={id:retry?earlier.id:uid(),content};
    setPosted(ids=>add(ids,id));
    setOutgoing(all=>({...all,[id]:{...message,state:'sending'}}));
    setDrafts(all=>all[id]===content?{...all,[id]:''}:all);
    try{
      const result:Json=await api(`sessions/${id}/messages`,'POST',message);
      if(!alive.current)return;
      applied.current.set(id,++order.current);confirm(id);
      setThreads(all=>({...all,[id]:{status:'ready',messages:merge(all[id]?.messages??[],result?.messages)}}));
      setOutgoing(all=>all[id]?.id===message.id?without(all,id):all);
      callbacks.current.onSent();
    }catch(error){
      if(!alive.current)return;
      if(lostAccess(error)){callbacks.current.onAccessLost();return;}
      setDrafts(all=>all[id]?all:{...all,[id]:content});
      setOutgoing(all=>({...all,[id]:{...message,state:'failed',error:String(error)}}));
    }finally{
      inflight.current.delete(id);
    }
  }
  const send=()=>{const id=selected.current;return post(id,drafts[id]??'');};
  // Sends the failed message again, under its ID, and leaves newer text in the composer as it is.
  const resend=()=>{const id=selected.current,failed=outgoing[id];return failed?.state==='failed'?post(id,failed.content):Promise.resolve();};

  // History entries, one per ID: a listed row wins over this page's own record of the same ID. A missing or not yet
  // confirmed conversation stays listed while it is current or holds an unsent draft or message, so it stays reachable.
  const kept=(id:string)=>id===session||!!drafts[id]?.trim()||!!outgoing[id];
  const entry=(id:string,kind:Entry['kind'],name:string,created:number):Entry=>({id,kind,name,created,draft:!!drafts[id]?.trim(),outgoing:outgoing[id]?.state});
  const others=[...new Set([...own,session,...Object.keys(drafts),...Object.keys(outgoing)])].filter(id=>!saved[id]&&kept(id)&&(own.has(id)||SESSION_ID.test(id)))
    .map(id=>entry(id,own.has(id)?'local':missing.has(id)?'missing':'unconfirmed',own.has(id)?'新对话':missing.has(id)?'已不存在的对话':'未确认的对话',0));
  const listed=Object.values(saved).filter(row=>!missing.has(row.id)||kept(row.id)).sort((a,b)=>b.created-a.created)
    .map(row=>entry(row.id,missing.has(row.id)?'missing':'saved',conversationTitle(row),row.created));
  const thread=threads[session]??{status:'loading',messages:[]},mine=outgoing[session],draft=drafts[session]??'';
  const draftTooLong=tooLong(draft),canPost=sendable(session)&&mine?.state!=='sending';
  return {session,entries:[...others.filter(e=>e.kind==='local'),...others.filter(e=>e.kind!=='local'),...listed],
    saved,own,missing,thread,draft,draftTooLong,
    pending:mine?.state==='sending'?mine:null,failure:mine?.state==='failed'?mine:null,
    // The failed message is in the transcript the Hub returned: it was recorded, only its reply may be missing.
    recorded:mine?.state==='failed'&&thread.messages.some(m=>m.id===mine.id),
    canSend:canPost&&!!draft.trim()&&!draftTooLong&&(mine?.state!=='failed'||mine.content===draft),
    canResend:canPost&&mine?.state==='failed',
    sendingCount:Object.values(outgoing).filter(o=>o.state==='sending').length,
    select,startNew,setDraft,send,resend,moveDraft,mergeList,
    // A retried read of a stored choice the Hub has not confirmed yet is still a restore.
    retry:()=>read(selected.current,!saved[selected.current])};
}
