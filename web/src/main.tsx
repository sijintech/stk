import React,{useCallback,useEffect,useRef,useState} from 'react';
import {flushSync} from 'react-dom';
import {createRoot} from 'react-dom/client';
import {action,api,ApiError,events,hasToken,Json,readNode,setToken} from './api';
import {conversationTitle,type Entry,useConversations} from './conversations';
import ErrorBoundary from './ErrorBoundary';
import TaskObservation from './TaskObservation';
import {isTerminalTaskState,type TaskFact,type TaskScope} from './taskFacts';
import './style.css';
const Viewer=React.lazy(()=>import('./Viewer'));
const GraphPanel=React.lazy(()=>import('./GraphPanel'));
// Development only: `?example=1` renders the payload v2 example without a hub (not part of production builds).
const ExampleView=import.meta.env.DEV&&new URLSearchParams(location.search).has('example')?React.lazy(()=>import('./ExampleView')):null;
const lostAccess=(error:unknown)=>error instanceof ApiError&&(error.status===401||error.status===403);
type ObservedTask = {scope:TaskScope;name:string;state:string;verifiedIdentity:boolean;exactTerminal:boolean};
// Persistent sections: 工作台 is the conversation home. All three stay mounted; only the active one is shown.
type Section='workbench'|'tasks'|'results';
const SECTIONS:readonly (readonly [Section,string])[]=[['workbench','工作台'],['tasks','任务'],['results','结果']];
// Up to this width the conversation history is opened on demand over the active section instead of a fixed column.
const COMPACT='(max-width: 1050px)';
// The secondary line of a history entry: what it is, then any unsent draft or message it holds.
function entryNote(entry:Entry){
  const kind=entry.kind==='local'?'未保存':entry.kind==='missing'?`已不存在 · ${entry.id.slice(0,6)}`:entry.kind==='unconfirmed'?`正在确认 · ${entry.id.slice(0,6)}`:
    [created(entry.created),entry.id.slice(0,6)].filter(Boolean).join(' · ');
  return kind+(entry.draft?' · 有草稿':'')+(entry.outgoing==='sending'?' · 发送中':entry.outgoing==='failed'?' · 发送失败':'');
}
const created=(seconds:number)=>seconds?new Date(seconds*1000).toLocaleString(undefined,{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):'';

function App(){
  const [connected,setConnected]=useState(hasToken());
  const disconnect=useCallback(()=>{
    setToken('');
    for(const key of ['stk-event-cursor','stk-last-action','stk-session'])sessionStorage.removeItem(key);
    setConnected(false);
  },[]);
  return connected?<Workbench disconnect={disconnect}/>:<Connect connected={()=>setConnected(true)}/>;
}

function Connect({connected}:{connected:()=>void}){
  const [pairCode,setPairCode]=useState(''),[token,setCredential]=useState('');
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  async function run(connect:()=>Promise<void>){
    setBusy(true);setError('');
    try{await connect();connected();}catch(error){setToken('');setError(String(error));}finally{setBusy(false);}
  }
  return <main className="login"><div className="wordmark">STK <span>科学工作台</span></div><h1>从任意设备<br/>连接你的计算。</h1><p>任务在服务器持续运行。这里用来发起、观察与探索。</p><form onSubmit={e=>{e.preventDefault();void run(async()=>{const result=await api('pairings/claim','POST',{code:pairCode,name:'STK 网页客户端'});if(result.role!=='client')throw new Error('请使用客户端配对码');setToken(result.token);});}}><label>一次性配对码<input value={pairCode} onChange={e=>setPairCode(e.target.value)} autoComplete="off" required/></label><button disabled={busy}>连接工作台 →</button></form><details><summary>使用已有设备凭据</summary><input aria-label="设备凭据" type="password" value={token} onChange={e=>setCredential(e.target.value)}/><button disabled={busy} onClick={()=>void run(async()=>{setToken(token);await api('devices');})}>连接</button></details>{error&&<p role="alert">{error}</p>}</main>;
}

function Workbench({disconnect}:{disconnect:()=>void}){
  const [devices,setDevices]=useState<Json[]>([]),[devicesRead,setDevicesRead]=useState(false),[actions,setActions]=useState<Json[]>([]),[node,setNode]=useState(''),[workspace,setWorkspace]=useState('');
  const [selection,setSelection]=useState<TaskScope|null>(null),[artifacts,setArtifacts]=useState<Json[]>([]),[path,setPath]=useState(''),[scene,setScene]=useState<Json|null>(null);
  const [observedTask,setObservedTask]=useState<ObservedTask|null>(null);
  const [readKinds,setReadKinds]=useState<string[]|null>(null),[taskRefresh,setTaskRefresh]=useState(0);
  const [analysis,setAnalysis]=useState<'file'|'graph'>('file'),[mode,setMode]=useState('slice'),[axis,setAxis]=useState(2),[index,setIndex]=useState(0),[level,setLevel]=useState(0),[probe,setProbe]=useState<number[]>([0,0,0]);
  // Conversations are Hub sessions, independent of the selected node, Runtime workspace and task.
  const refreshNow=useRef(()=>{});
  const conv=useConversations(disconnect,()=>refreshNow.current());
  const {mergeList}=conv;
  const [wide,setWide]=useState(()=>!matchMedia(COMPACT).matches),[historyOpen,setHistoryOpen]=useState(false);
  // overlay: the compact history is open over the active section, which then takes no input until it closes.
  const historyShown=wide||historyOpen,overlay=!wide&&historyOpen;
  const historyPanel=useRef<HTMLElement>(null),historyToggle=useRef<HTMLButtonElement>(null),messageList=useRef<HTMLDivElement>(null),composer=useRef<HTMLTextAreaElement>(null);
  const [name,setName]=useState('科学项目'),[logs,setLogs]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[tab,setTab]=useState<Section>('workbench'),[online,setOnline]=useState(navigator.onLine);
  const generation=useRef(0),scopeVersion=useRef(0),activeScope=useRef<TaskScope|null>(null),refreshing=useRef(false),alive=useRef(true);
  const artifactReads=useRef({started:0,applied:0});
  const [logRoom,setLogRoom]=useState(false);
  const fileChoice=useRef<HTMLSelectElement>(null),modeChoice=useRef<HTMLDivElement>(null),logPane=useRef<HTMLDetailsElement>(null);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
  const selected=devices.find(d=>d.id===node&&!d.revoked);
  const tasks:Json[]=selected?.snapshot?.tasks||[];
  const task=selected&&selection?.node===node?selection.task:'';
  const heartbeat=task&&tasks.find(t=>t.id===task&&t.workspace_id===selection?.workspace);
  const observed=observedTask?.scope===selection?observedTask:null;
  const taskBound=!!task&&(!!heartbeat||observed?.verifiedIdentity===true);
  const exactTerminal=observed?.exactTerminal===true;
  let graphTasks=tasks;
  if(taskBound&&observed){
    const row={id:task,name:observed.name,state:observed.state};
    graphTasks=tasks.some(item=>item.id===task)?tasks.map(item=>item.id===task?row:item):[row,...tasks];
  }
  const shownScene=taskBound?scene:null;
  const features:unknown=selected?.snapshot?.features;
  const canRead=Array.isArray(features)&&features.includes('read');
  const canReadArtifacts=canRead&&readKinds?.includes('task.artifacts')===true;
  const canReadEvents=canRead&&features.includes('task.events')&&readKinds?.includes('task.events')===true;
  const canReadTask=readKinds===null?null:canRead&&features.includes('task.get')&&readKinds.includes('task.get');
  const taskOnline=online&&selected?.online===true;
  // Readable scope of 任务: the queue lists the chosen node, filtered by the chosen project; the selected task keeps its
  // own scope, which can be another project of the node while no project is chosen.
  const nodes=devices.filter(d=>d.role==='node'&&!d.revoked),workspaces:Json[]=selected?.snapshot?.workspaces||[];
  const workspaceName=(id:string)=>workspaces.find(w=>w.id===id)?.name||id.slice(0,8);
  const nodeName=selected?selected.name||node.slice(0,8):'';
  const queue=tasks.filter(t=>!workspace||t.workspace_id===workspace);
  const queueScope=`${nodeName} · ${!online?'最近状态':selected?.online?'在线':'离线'} · ${workspace?workspaceName(workspace):'全部项目'}`;
  const queueEmpty=!selected?(!devicesRead?(online?'正在读取执行节点…':'控制服务未连接。恢复连接后，这里显示执行节点的任务队列。'):
      !nodes.length?'控制服务中暂无执行节点。节点配对后，这里显示它的任务队列。':'在下方「运行环境」中选择执行节点和项目，这里显示任务队列。'):
    !tasks.length?'节点快照中暂无任务。':!queue.length?`${workspaceName(workspace)} 中暂无任务，可在下方「新建任务」中提交。`:'';
  const clearTask=useCallback(()=>{
    generation.current++;scopeVersion.current++;activeScope.current=null;
    setSelection(null);setObservedTask(null);setPath('');setArtifacts([]);setScene(null);setLogs('');setLogRoom(false);
  },[]);
  const clearNode=useCallback(()=>{clearTask();setNode('');setWorkspace('');},[clearTask]);
  const nodeGone=useCallback((scope:TaskScope)=>{if(activeScope.current===scope)clearNode();},[clearNode]);
  const observeTask=useCallback((scope:TaskScope,fact:TaskFact,verifiedIdentity:boolean)=>{
    if(activeScope.current!==scope)return;
    setObservedTask(previous=>{
      const known=previous?.scope===scope?previous:null;
      const exactTerminal=known?.exactTerminal===true||(fact.exact&&isTerminalTaskState(fact.state));
      if(known&&known.state===fact.state&&known.name===fact.name&&known.verifiedIdentity===verifiedIdentity&&
         known.exactTerminal===exactTerminal)return known;
      return {scope,name:fact.name,state:fact.state,verifiedIdentity,exactTerminal};
    });
  },[]);
  const acceptArtifacts=useCallback((version:number,request:number,result:unknown)=>{
    if(!alive.current||scopeVersion.current!==version||request<=artifactReads.current.applied||!Array.isArray(result))return;
    artifactReads.current.applied=request;
    setArtifacts(result);
  },[]);
  function selectWorkspace(id:string){clearTask();setWorkspace(id);}
  const refresh=useCallback(async()=>{
    if(refreshing.current)return;refreshing.current=true;
    try{
      const [d,a,s,p]=await Promise.all([api('devices'),api('actions'),api('sessions?include_labels=true'),api('policy').catch(error=>{
        if(lostAccess(error))throw error;
        return error instanceof ApiError&&(error.status===404||error.status===501)?{}:null;
      })]);
      if(!alive.current)return;
      setDevices(d);setDevicesRead(true);setActions(a);mergeList(s);setOnline(true);
      if(p!==null)setReadKinds(Array.isArray(p?.read_kinds)?p.read_kinds:[]);
    }catch(error){
      if(!alive.current)return;
      if(lostAccess(error))disconnect();
      else{setOnline(false);setError(String(error));}
    }finally{refreshing.current=false;}
  },[disconnect,mergeList]);
  refreshNow.current=()=>void refresh();
  // Across the compact width the history keeps the keyboard focus: focus inside it keeps it open as the overlay when
  // the page narrows, and focus on the 历史 toggle, which only the compact page has, moves into the column when it widens.
  const keepHistoryFocus=useRef(false);
  useEffect(()=>{const query=matchMedia(COMPACT);const change=()=>{
    const focus=document.activeElement,inside=!!historyPanel.current?.contains(focus);
    keepHistoryFocus.current=!query.matches&&!!focus&&focus===historyToggle.current;
    setWide(!query.matches);setHistoryOpen(query.matches&&inside);
  };change();query.addEventListener('change',change);return()=>query.removeEventListener('change',change);},[]);
  useEffect(()=>{if(wide&&keepHistoryFocus.current){keepHistoryFocus.current=false;focusHistory();}},[wide]);
  // Escape closes the overlay from anywhere on the page and returns the focus to the 历史 toggle.
  useEffect(()=>{
    if(!overlay)return;
    const key=(e:KeyboardEvent)=>{if(e.key==='Escape'){e.preventDefault();closeHistory();}};
    window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);
  },[overlay]);
  useEffect(()=>{void refresh();const abort=new AbortController();void events(()=>void refresh(),abort.signal);const timer=setInterval(()=>void refresh(),5000);return()=>{abort.abort();clearInterval(timer);};},[refresh]);
  useEffect(()=>{if(node&&!selected)clearNode();},[node,selected,clearNode]);
  useEffect(()=>{
    if(!taskBound||!taskOnline||!canReadArtifacts)return;
    const abort=new AbortController();
    const version=scopeVersion.current;
    const request=++artifactReads.current.started;
    void readNode(node,'task.artifacts',{task_id:task},abort.signal).then(result=>{
      if(!abort.signal.aborted)acceptArtifacts(version,request,result);
    }).catch(error=>{
      if(!abort.signal.aborted&&lostAccess(error))disconnect();
    });
    return()=>abort.abort();
  },[node,task,taskBound,taskOnline,canReadArtifacts,exactTerminal,acceptArtifacts,disconnect]);
  async function run(fn:()=>Promise<void>){setBusy(true);setError('');try{await fn();if(alive.current)await refresh();}catch(error){if(alive.current){if(lostAccess(error))disconnect();else setError(String(error));}}finally{setBusy(false);}}
  const invoke=(kind:string,payload:Json)=>action(node,kind,payload,()=>setError('操作等待复核，请在任务面板查看完整参数。'));
  async function files(){
    const version=scopeVersion.current;
    const request=++artifactReads.current.started;
    const result=canReadArtifacts?await readNode(node,'task.artifacts',{task_id:task}):
      (await invoke('task.artifacts',{task_id:task})).result;
    acceptArtifacts(version,request,result);
  }
  function selectTask(id:string,workspaceId:string){
    if(!workspaceId||!/^[0-9a-f]{32}$/.test(id))return;
    if(selection?.node===node&&selection.workspace===workspaceId&&selection.task===id){
      setTaskRefresh(value=>value+1);return;
    }
    clearTask();
    const scope={node,workspace:workspaceId,task:id};
    activeScope.current=scope;setSelection(scope);
  }
  async function loadView(){const current=++generation.current;const options:Json={mode,axis};if(mode==='slice')options.index=index;if(mode==='iso')options.level=level;if(mode==='vectors')options.component='magnitude';
    const item=await invoke('view.build',{task_id:task,path,options});if(item.result&&generation.current===current){setScene(item.result);setLevel((item.result.manifest.value_range[0]+item.result.manifest.value_range[1])/2);}}
  async function readLogs(){const version=scopeVersion.current;const item=await invoke('task.logs',{task_id:task});if(item.result&&scopeVersion.current===version){const bytes=Uint8Array.from(atob(item.result.data),c=>c.charCodeAt(0));setLogs(new TextDecoder().decode(bytes));}}
  // An explicit 结果 / 读取日志 click in Tasks opens 结果 at once and brings the target into view; the read itself
  // keeps its own scope checks and never navigates on completion. The analysis mode and Viewer are left as they are.
  // 读取日志 also gives the open log pane its full bounded height (logRoom, until the task scope changes), so the
  // text that arrives later scrolls inside the pane and moves nothing in 结果, whichever page the user is on then.
  function openResults(target:'files'|'logs'){
    flushSync(()=>{setTab('results');if(target==='logs')setLogRoom(true);});
    const pane=logPane.current;
    if(target==='logs'&&pane)pane.open=true;
    const element=target==='logs'?pane?.querySelector('summary'):analysis==='file'?fileChoice.current:modeChoice.current?.querySelector<HTMLElement>('[aria-selected="true"]');
    (target==='logs'?pane:element)?.scrollIntoView({block:'nearest'});element?.focus({preventScroll:true});
  }
  // Choosing a conversation (or a new one) is one explicit action: it opens 工作台 with that conversation's own
  // transcript and draft, and changes nothing in 任务 or 结果. On a compact page the history closes again.
  function openConversation(id:string|null){
    flushSync(()=>{setTab('workbench');setHistoryOpen(false);if(id)conv.select(id);else conv.startNew();});
    if(!id)composer.current?.focus({preventScroll:true});
    else if(!wide)messageList.current?.focus({preventScroll:true});
  }
  function focusHistory(){
    const panel=historyPanel.current;
    const target=panel?.querySelector<HTMLElement>('.conversation[aria-current="true"]')??panel?.querySelector<HTMLElement>('button');
    target?.focus({preventScroll:true});
    target?.scrollIntoView({block:'nearest'});
  }
  function closeHistory(){setHistoryOpen(false);historyToggle.current?.focus({preventScroll:true});}
  function toggleHistory(){
    if(historyOpen){setHistoryOpen(false);return;}
    flushSync(()=>setHistoryOpen(true));
    focusHistory();
  }
  // The unsent text of a conversation the Hub no longer has goes to a new local conversation, ready to send there.
  function moveDraft(){flushSync(()=>conv.moveDraft());composer.current?.focus({preventScroll:true});}
  const sessionRow=conv.saved[conv.session];
  const sessionLabel=conv.missing.has(conv.session)?`已不存在 · ${conv.session.slice(0,6)}`:sessionRow?`${conversationTitle(sessionRow)} · ${conv.session.slice(0,6)}`:
    conv.own.has(conv.session)?'新对话 · 未保存':`正在确认 · ${conv.session.slice(0,6)}`;
  const thread=conv.thread,pending=conv.pending&&!thread.messages.some(m=>m.id===conv.pending!.id)?conv.pending:null;
  async function probeValue(){
    const version=generation.current;
    const result=await invoke('view.probe',{task_id:task,path,position:probe});
    if(generation.current===version)setLogs(JSON.stringify(result.result,null,2));
  }
  return <div className="app"><header><div className="wordmark">STK <span>科学工作台</span></div><span className={online?'connection':'connection offline'}>{online?'控制服务已连接':'连接中断 · 显示最近状态'}</span><button className="quiet" onClick={disconnect}>断开</button></header>
    {error&&<div className="notice" role="alert">{error}<button onClick={()=>setError('')}>关闭</button></div>}
    <div className={wide?'workspace with-history':'workspace'}>
    <nav className="section-nav" aria-label="工作区">{SECTIONS.map(([key,label])=><button type="button" className={tab===key?'active':''} aria-current={tab===key?'page':undefined} key={key} onClick={()=>{setTab(key);setHistoryOpen(false);}}>{label}</button>)}
      {!wide&&<button type="button" ref={historyToggle} className={historyOpen?'history-toggle open':'history-toggle'} aria-expanded={historyOpen} aria-controls="conversation-history" aria-label="对话历史" onClick={toggleHistory}>历史</button>}</nav>
    <section id="conversation-history" ref={historyPanel} aria-label="对话历史" className={`history${wide?'':' history-overlay'}${historyShown?'':' surface-hidden'}`} inert={!historyShown}>
      <div className="history-head"><h2>对话</h2><button type="button" className="new-conversation" onClick={()=>openConversation(null)}>新对话</button></div>
      <ul className="history-list">
        {conv.entries.map(entry=><li key={entry.id}><button type="button" className="conversation" aria-current={entry.id===conv.session?'true':undefined} onClick={()=>openConversation(entry.id)}><span>{entry.name}</span><small>{entryNote(entry)}</small></button></li>)}
      </ul>
      {!conv.entries.some(entry=>entry.kind==='saved')&&<p className="muted">还没有保存的对话。</p>}
    </section>
    {overlay&&<div className="history-backdrop" aria-hidden="true" onClick={closeHistory}/>}
    <aside className={`tasks panel surface${tab==='tasks'?'':' surface-hidden'}`} inert={tab!=='tasks'||overlay}><div className="section-title"><h2>项目与任务</h2><button className="quiet" onClick={()=>{setTaskRefresh(value=>value+1);void refresh();}}>刷新</button></div>
      <section className="queue" aria-label="任务队列"><div className="queue-head"><h3>任务队列</h3>{selected&&<span className="muted">{queueScope}</span>}</div>
      <div className="task-list">{queue.map(t=><button className={`task ${task===t.id?'selected':''}`} key={t.id} onClick={()=>selectTask(t.id,t.workspace_id)}><span>{t.name||t.id.slice(0,8)}</span><small className={`state ${t.state}`}>{t.state}</small></button>)}{queueEmpty&&<p className="muted">{queueEmpty}</p>}</div>
      {selected&&<p className="muted">节点快照 · 最多 200 条任务</p>}
      {workspace&&<form className="task-lookup" key={`${node}/${workspace}`} onSubmit={event=>{
        event.preventDefault();selectTask(String(new FormData(event.currentTarget).get('task-id')).trim(),workspace);
      }}>
        <label>按任务 ID 查看<input name="task-id" pattern="[0-9a-f]{32}" required/></label>
        <button className="quiet">查看任务</button>
      </form>}</section>
      {task&&selection&&<p className="muted task-scope">所选任务 · {nodeName} · {workspaceName(selection.workspace)}</p>}
      {task&&selection&&<TaskObservation key={`${node}/${selection.workspace}/${task}`} scope={selection}
        heartbeat={heartbeat} online={taskOnline} supported={canReadTask} refresh={taskRefresh}
        onObservation={observeTask} onAccessLost={disconnect} onNodeGone={nodeGone}/>}
      {taskBound&&<div className="inline"><button disabled={busy} onClick={()=>{openResults('logs');void run(readLogs);}}>读取日志</button><button disabled={busy} onClick={()=>{openResults('files');void run(files);}}>结果</button><button disabled={busy} onClick={()=>void run(async()=>{await invoke('task.cancel',{task_id:task});})}>取消</button></div>}
      {actions.filter(a=>a.state==='review').map(a=><article className="review" key={a.id}><strong>等待执行复核</strong><p>{a.review_reason}</p><pre>{JSON.stringify(a.request.payload,null,2)}</pre>{[true,false].map(approved=><button key={String(approved)} disabled={busy} onClick={()=>void run(async()=>{await api(`actions/${a.id}/review`,'POST',{approved});})}>{approved?'批准执行':'拒绝'}</button>)}</article>)}
      <details className="setting" open><summary>运行环境 · {nodeName||'未选择节点'}{selected&&` · ${workspace?workspaceName(workspace):'未选择项目'}`}</summary>
      <label>执行节点<select value={node} onChange={e=>{clearTask();setNode(e.target.value);setWorkspace('');}}><option value="">选择节点</option>{nodes.map(d=><option key={d.id} value={d.id}>{d.online?'●':'○'} {d.name}</option>)}</select></label>
      {selected&&<p className="muted">{selected.online?'在线':'离线'} · 最近更新 {selected.last_seen?new Date(selected.last_seen*1000).toLocaleString():'尚未连接'}{selected.snapshot.cpu_percent!==undefined&&<><br/>CPU {selected.snapshot.cpu_percent}% · 内存 {selected.snapshot.memory_percent}%</>}</p>}
      <label>项目<select value={workspace} onChange={e=>selectWorkspace(e.target.value)}><option value="">选择项目</option>{workspaces.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</select></label>
      <div className="inline"><input aria-label="项目名称" value={name} onChange={e=>setName(e.target.value)}/><button disabled={busy||!node} onClick={()=>void run(async()=>{const version=scopeVersion.current;const a=await invoke('workspace.create',{name});if(a.result&&scopeVersion.current===version)selectWorkspace(a.result.id);})}>新建</button></div>
      </details>
      <details className="setting"><summary>新建任务{workspace?` · ${workspaceName(workspace)}`:' · 先选择项目'}</summary>
      <button type="button" className="primary wide" disabled={busy||!workspace} onClick={()=>void run(async()=>{const version=scopeVersion.current;const a=await invoke('task.submit',{template:'demo-field',spec:{workspace_id:workspace,name:'解析场验证',argv:['@python','-m','suan.control.demo_job'],outputs:['scalar-0.vti','scalar-1.vti','vector.vti']}});if(a.result&&scopeVersion.current===version)selectTask(a.result.id,workspace);})}>运行解析场示例</button>
      <p className="muted">自定义任务：输入 TaskSpec JSON。新命令将先进入执行复核。</p><form onSubmit={e=>{e.preventDefault();const form=new FormData(e.currentTarget);void run(async()=>{const spec=JSON.parse(String(form.get('spec')));await invoke('task.submit',{spec:{workspace_id:workspace,...spec}});});}}><textarea name="spec" aria-label="TaskSpec" defaultValue={'{"argv":["python3","analysis.py"],"outputs":[]}'}/><button disabled={busy||!workspace}>提交复核</button></form>
      </details>
      <details><summary>最近操作与重试</summary>{actions.filter(a=>a.request.kind!=='task.events').slice(0,20).map(a=><p key={a.id}><small>{a.request.kind} · {a.state}<br/>{a.error}</small></p>)}<button onClick={()=>void run(async()=>{const saved=sessionStorage.getItem('stk-last-action');if(saved)await api('actions','POST',JSON.parse(saved));})}>以相同 ID 重试上次操作</button></details>
    </aside>
    <section className={`analysis surface${tab==='results'?'':' surface-hidden'}`} inert={tab!=='results'||overlay}><div className="view-title"><div><span className="eyebrow">RESULT EXPLORER</span><h1>{analysis==='graph'?'图谱视图':shownScene?.manifest.field||'科学结果'}</h1></div><span className="muted">拖动旋转 · 滚轮缩放 · 点击探针</span></div>
      <div className="mode-switch" ref={modeChoice} role="tablist" aria-label="分析方式">{([['file','结果文件'],['graph','图谱']] as const).map(([key,label])=><button key={key} role="tab" aria-selected={analysis===key} className={analysis===key?'active':''} onClick={()=>setAnalysis(key)}>{label}</button>)}</div>
      {analysis==='graph'?<React.Suspense fallback={<div className="viewport empty">正在加载图谱模块…</div>}><GraphPanel key={selected?.id||''} node={selected?node:''} task={taskBound?task:''} tasks={graphTasks} artifacts={taskBound?artifacts:[]} canReadEvents={canReadEvents&&taskOnline} onError={setError} onLog={setLogs}/></React.Suspense>:<>
      <div className="view-controls"><label>结果 / 时间步<select aria-label="结果文件" ref={fileChoice} value={taskBound?path:''} onChange={e=>{setPath(e.target.value);generation.current++;}}><option value="">选择数据文件</option>{(taskBound?artifacts:[]).filter(a=>/\.(vti|vtk|npy|dat)$/.test(a.path)).map(a=><option key={a.path} value={a.path}>{a.path}</option>)}</select></label>
      <label>视图<select value={mode} onChange={e=>setMode(e.target.value)}><option value="slice">切片</option><option value="iso">等值面</option><option value="vectors">向量箭头</option></select></label>
      {mode==='slice'&&<><label>方向<select value={axis} onChange={e=>setAxis(Number(e.target.value))}>{['X','Y','Z'].map((v,i)=><option key={v} value={i}>{v}</option>)}</select></label><label>索引<input type="number" min="0" value={index} onChange={e=>setIndex(Number(e.target.value))}/></label></>}
      {mode==='iso'&&<label>等值<input type="number" value={level} onChange={e=>setLevel(Number(e.target.value))}/></label>}
      <button disabled={busy||!taskBound||!path} onClick={()=>void run(loadView)}>加载视图</button></div>
      <ErrorBoundary resetKey={shownScene}><React.Suspense fallback={<div className="viewport empty">正在加载三维模块…</div>}><Viewer scene={shownScene} onPick={setProbe}/></React.Suspense></ErrorBoundary>
      {shownScene&&<div className="legend"><span>{shownScene.manifest.value_range[0].toPrecision(5)}</span><i/><span>{shownScene.manifest.value_range[1].toPrecision(5)} {shownScene.manifest.units}</span><small>{shownScene.manifest.display_reduced?'显示网格已简化':'完整显示网格'} · 数值查询使用原始数据</small></div>}
      <div className="probe"><strong>物理坐标探针</strong>{probe.map((v,i)=><input aria-label={`探针${'XYZ'[i]}`} key={i} type="number" value={v} onChange={e=>setProbe(probe.map((n,j)=>i===j?Number(e.target.value):n))}/>)}<button disabled={busy||!shownScene} onClick={()=>void run(probeValue)}>查询原始值</button></div></>}
      <details className={logRoom?'logs log-room':'logs'} ref={logPane} open><summary>日志 / 探针结果</summary><pre>{(selected&&logs)||'选择任务读取日志，或在三维视图中选取一个位置。'}</pre></details>
    </section>
    <aside className={`chat panel surface${tab==='workbench'?'':' surface-hidden'}`} inert={tab!=='workbench'||overlay}><div className="section-title"><h2>AI 对话</h2><span className="muted conversation-name">{sessionLabel}</span></div>
      <div className="messages" ref={messageList} tabIndex={-1} role="log" aria-label="对话记录">
        {thread.status==='loading'&&!thread.messages.length&&<p className="muted">正在读取对话…</p>}
        {thread.status==='missing'&&<div className="chat-intro"><h3>这个对话已不存在</h3><p>控制服务中没有这个对话，未创建新会话。{conv.draft.trim()?'未发送的草稿仍在这里，可以移到新对话再发送。':'可以从「新对话」重新开始。'}</p>
          {!!conv.draft.trim()&&<button type="button" onClick={moveDraft}>移到新对话</button>}</div>}
        {thread.status==='error'&&<p className="muted">读取对话失败：{thread.error} <button type="button" className="quiet" onClick={conv.retry}>重新读取</button></p>}
        {thread.status==='ready'&&!thread.messages.length&&!pending&&<div className="chat-intro"><h3>从一个科学问题开始</h3><p>描述你要执行的任务。命令、资源与执行状态会在任务面板中明确展示。</p></div>}
        {thread.messages.map(m=><article key={m.id} className={m.role}><small>{m.role==='user'?'你':'STK'}</small><p>{m.content}</p></article>)}
        {pending&&<article className="user pending"><small>你 · 发送中</small><p>{pending.content}</p></article>}
      </div>
      {conv.failure&&<div className="send-failure" role="alert"><p>{conv.recorded?'消息已记录，回复尚未确认。':'发送未完成，草稿已保留。'}{conv.failure.error}</p>
        {!conv.recorded&&conv.failure.content!==conv.draft&&<p className="failed-text">未发送：{conv.failure.content}</p>}
        {conv.canResend&&conv.draft.trim()&&conv.failure.content!==conv.draft&&<p>请先重试上一条消息，当前草稿会保留。</p>}
        <button type="button" className="quiet" disabled={!conv.canResend} onClick={()=>void conv.resend()}>重新发送</button></div>}
      {conv.draftTooLong&&<p className="muted" role="status">单条消息最多 12,000 字符，请缩短后发送。</p>}
      <form onSubmit={e=>{e.preventDefault();void conv.send();}}><label className="sr-only" htmlFor="chat-input">对话内容</label><textarea id="chat-input" ref={composer} value={conv.draft} onChange={e=>conv.setDraft(e.target.value)} placeholder="描述计算任务…"/><button className="primary wide" disabled={!conv.canSend}>发送</button></form><small className="muted">常规模板自动执行；新脚本及高资源任务需复核。</small></aside>
    </div><footer>{busy||conv.sendingCount?'正在处理请求…':'就绪'}<span>STK · 计算持续运行，视图随处可达</span></footer>
  </div>;
}
createRoot(document.getElementById('root')!).render(ExampleView?<React.Suspense fallback={null}><ExampleView/></React.Suspense>:<App/>);
if('serviceWorker' in navigator)void navigator.serviceWorker.register('/sw.js');
