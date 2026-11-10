import React,{useCallback,useEffect,useRef,useState} from 'react';
import {flushSync} from 'react-dom';
import {createRoot} from 'react-dom/client';
import {action,api,ApiError,events,hasToken,Json,readNode,setToken,uid} from './api';
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
  const [devices,setDevices]=useState<Json[]>([]),[actions,setActions]=useState<Json[]>([]),[node,setNode]=useState(''),[workspace,setWorkspace]=useState('');
  const [selection,setSelection]=useState<TaskScope|null>(null),[artifacts,setArtifacts]=useState<Json[]>([]),[path,setPath]=useState(''),[scene,setScene]=useState<Json|null>(null);
  const [observedTask,setObservedTask]=useState<ObservedTask|null>(null);
  const [readKinds,setReadKinds]=useState<string[]|null>(null),[taskRefresh,setTaskRefresh]=useState(0);
  const [analysis,setAnalysis]=useState<'file'|'graph'>('file'),[mode,setMode]=useState('slice'),[axis,setAxis]=useState(2),[index,setIndex]=useState(0),[level,setLevel]=useState(0),[probe,setProbe]=useState<number[]>([0,0,0]);
  const [session,setSession]=useState(()=>sessionStorage.getItem('stk-session')||uid()),[sessions,setSessions]=useState<Json[]>([]),[messages,setMessages]=useState<Json[]>([]),[chat,setChat]=useState('');
  const [name,setName]=useState('科学项目'),[logs,setLogs]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[tab,setTab]=useState<Section>('workbench'),[online,setOnline]=useState(navigator.onLine);
  const generation=useRef(0),scopeVersion=useRef(0),activeScope=useRef<TaskScope|null>(null),refreshing=useRef(false),alive=useRef(true);
  const artifactReads=useRef({started:0,applied:0});
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
  const clearTask=useCallback(()=>{
    generation.current++;scopeVersion.current++;activeScope.current=null;
    setSelection(null);setObservedTask(null);setPath('');setArtifacts([]);setScene(null);setLogs('');
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
      const [d,a,s,p]=await Promise.all([api('devices'),api('actions'),api('sessions'),api('policy').catch(error=>{
        if(lostAccess(error))throw error;
        return error instanceof ApiError&&(error.status===404||error.status===501)?{}:null;
      })]);
      if(!alive.current)return;
      setDevices(d);setActions(a);setSessions(s);setOnline(true);
      if(p!==null)setReadKinds(Array.isArray(p?.read_kinds)?p.read_kinds:[]);
    }catch(error){
      if(!alive.current)return;
      if(lostAccess(error))disconnect();
      else{setOnline(false);setError(String(error));}
    }finally{refreshing.current=false;}
  },[disconnect]);
  useEffect(()=>{void refresh();const abort=new AbortController();void events(()=>void refresh(),abort.signal);const timer=setInterval(()=>void refresh(),5000);return()=>{abort.abort();clearInterval(timer);};},[refresh]);
  useEffect(()=>{sessionStorage.setItem('stk-session',session);void api(`sessions/${session}`).then(s=>setMessages(s.messages)).catch(e=>setError(String(e)));},[session]);
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
  function openResults(target:'files'|'logs'){
    flushSync(()=>setTab('results'));
    const pane=logPane.current;
    if(target==='logs'&&pane)pane.open=true;
    const element=target==='logs'?pane?.querySelector('summary'):analysis==='file'?fileChoice.current:modeChoice.current?.querySelector<HTMLElement>('[aria-selected="true"]');
    (target==='logs'?pane:element)?.scrollIntoView({block:'nearest'});element?.focus({preventScroll:true});
  }
  async function probeValue(){
    const version=generation.current;
    const result=await invoke('view.probe',{task_id:task,path,position:probe});
    if(generation.current===version)setLogs(JSON.stringify(result.result,null,2));
  }
  return <div className="app"><header><div className="wordmark">STK <span>科学工作台</span></div><span className={online?'connection':'connection offline'}>{online?'控制服务已连接':'连接中断 · 显示最近状态'}</span><button className="quiet" onClick={disconnect}>断开</button></header>
    {error&&<div className="notice" role="alert">{error}<button onClick={()=>setError('')}>关闭</button></div>}
    <div className="workspace">
    <nav className="section-nav" aria-label="工作区">{SECTIONS.map(([key,label])=><button type="button" className={tab===key?'active':''} aria-current={tab===key?'page':undefined} key={key} onClick={()=>setTab(key)}>{label}</button>)}</nav>
    <aside className={`tasks panel surface${tab==='tasks'?'':' surface-hidden'}`} inert={tab!=='tasks'}><div className="section-title"><h2>项目与任务</h2><button className="quiet" onClick={()=>{setTaskRefresh(value=>value+1);void refresh();}}>刷新</button></div>
      <label>执行节点<select value={node} onChange={e=>{clearTask();setNode(e.target.value);setWorkspace('');}}><option value="">选择节点</option>{devices.filter(d=>d.role==='node'&&!d.revoked).map(d=><option key={d.id} value={d.id}>{d.online?'●':'○'} {d.name}</option>)}</select></label>
      {selected&&<p className="muted">{selected.online?'在线':'离线'} · 最近更新 {selected.last_seen?new Date(selected.last_seen*1000).toLocaleString():'尚未连接'}{selected.snapshot.cpu_percent!==undefined&&<><br/>CPU {selected.snapshot.cpu_percent}% · 内存 {selected.snapshot.memory_percent}%</>}</p>}
      <label>项目<select value={workspace} onChange={e=>selectWorkspace(e.target.value)}><option value="">选择项目</option>{(selected?.snapshot?.workspaces||[]).map((w:Json)=><option key={w.id} value={w.id}>{w.name}</option>)}</select></label>
      <div className="inline"><input aria-label="项目名称" value={name} onChange={e=>setName(e.target.value)}/><button disabled={busy||!node} onClick={()=>void run(async()=>{const version=scopeVersion.current;const a=await invoke('workspace.create',{name});if(a.result&&scopeVersion.current===version)selectWorkspace(a.result.id);})}>新建</button></div>
      <button className="primary wide" disabled={busy||!workspace} onClick={()=>void run(async()=>{const version=scopeVersion.current;const a=await invoke('task.submit',{template:'demo-field',spec:{workspace_id:workspace,name:'解析场验证',argv:['@python','-m','suan.control.demo_job'],outputs:['scalar-0.vti','scalar-1.vti','vector.vti']}});if(a.result&&scopeVersion.current===version)selectTask(a.result.id,workspace);})}>运行解析场示例</button>
      <details><summary>自定义任务</summary><p className="muted">输入 TaskSpec JSON。新命令将先进入执行复核。</p><form onSubmit={e=>{e.preventDefault();const form=new FormData(e.currentTarget);void run(async()=>{const spec=JSON.parse(String(form.get('spec')));await invoke('task.submit',{spec:{workspace_id:workspace,...spec}});});}}><textarea name="spec" aria-label="TaskSpec" defaultValue={'{"argv":["python3","analysis.py"],"outputs":[]}'}/><button disabled={busy||!workspace}>提交复核</button></form></details>
      {selected&&<p className="muted">节点快照 · 最多 200 条任务</p>}
      <div className="task-list">{tasks.filter(t=>!workspace||t.workspace_id===workspace).map(t=><button className={`task ${task===t.id?'selected':''}`} key={t.id} onClick={()=>selectTask(t.id,t.workspace_id)}><span>{t.name||t.id.slice(0,8)}</span><small className={`state ${t.state}`}>{t.state}</small></button>)}{!tasks.length&&<p className="muted">快照中暂无任务。</p>}</div>
      {workspace&&<form key={`${node}/${workspace}`} onSubmit={event=>{
        event.preventDefault();selectTask(String(new FormData(event.currentTarget).get('task-id')).trim(),workspace);
      }}>
        <label>按任务 ID 查看<input name="task-id" pattern="[0-9a-f]{32}" required/></label>
        <button className="quiet">查看任务</button>
      </form>}
      {task&&selection&&<TaskObservation key={`${node}/${selection.workspace}/${task}`} scope={selection}
        heartbeat={heartbeat} online={taskOnline} supported={canReadTask} refresh={taskRefresh}
        onObservation={observeTask} onAccessLost={disconnect} onNodeGone={nodeGone}/>}
      {taskBound&&<div className="inline"><button disabled={busy} onClick={()=>{openResults('logs');void run(readLogs);}}>读取日志</button><button disabled={busy} onClick={()=>{openResults('files');void run(files);}}>结果</button><button disabled={busy} onClick={()=>void run(async()=>{await invoke('task.cancel',{task_id:task});})}>取消</button></div>}
      {actions.filter(a=>a.state==='review').map(a=><article className="review" key={a.id}><strong>等待执行复核</strong><p>{a.review_reason}</p><pre>{JSON.stringify(a.request.payload,null,2)}</pre>{[true,false].map(approved=><button key={String(approved)} disabled={busy} onClick={()=>void run(async()=>{await api(`actions/${a.id}/review`,'POST',{approved});})}>{approved?'批准执行':'拒绝'}</button>)}</article>)}
      <details><summary>最近操作与重试</summary>{actions.filter(a=>a.request.kind!=='task.events').slice(0,20).map(a=><p key={a.id}><small>{a.request.kind} · {a.state}<br/>{a.error}</small></p>)}<button onClick={()=>void run(async()=>{const saved=sessionStorage.getItem('stk-last-action');if(saved)await api('actions','POST',JSON.parse(saved));})}>以相同 ID 重试上次操作</button></details>
    </aside>
    <section className={`analysis surface${tab==='results'?'':' surface-hidden'}`} inert={tab!=='results'}><div className="view-title"><div><span className="eyebrow">RESULT EXPLORER</span><h1>{analysis==='graph'?'图谱视图':shownScene?.manifest.field||'科学结果'}</h1></div><span className="muted">拖动旋转 · 滚轮缩放 · 点击探针</span></div>
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
      <details className="logs" ref={logPane} open><summary>日志 / 探针结果</summary><pre>{(selected&&logs)||'选择任务读取日志，或在三维视图中选取一个位置。'}</pre></details>
    </section>
    <aside className={`chat panel surface${tab==='workbench'?'':' surface-hidden'}`} inert={tab!=='workbench'}><div className="section-title"><h2>AI 对话</h2><button className="quiet" onClick={()=>{setSession(uid());setMessages([]);}}>新会话</button></div><select aria-label="恢复会话" value={session} onChange={e=>setSession(e.target.value)}><option value={session}>当前会话</option>{sessions.filter(s=>s.id!==session).map(s=><option key={s.id} value={s.id}>{s.name} · {s.id.slice(0,6)}</option>)}</select>
      <div className="messages">{!messages.length&&<div className="chat-intro"><h3>从一个科学问题开始</h3><p>描述你要执行的任务。命令、资源与执行状态会在任务面板中明确展示。</p></div>}{messages.map(m=><article key={m.id} className={m.role}><small>{m.role==='user'?'你':'STK'}</small><p>{m.content}</p></article>)}</div>
      <form onSubmit={e=>{e.preventDefault();const content=chat;setChat('');void run(async()=>{const result=await api(`sessions/${session}/messages`,'POST',{id:uid(),content});setMessages(result.messages);});}}><label className="sr-only" htmlFor="chat-input">对话内容</label><textarea id="chat-input" value={chat} onChange={e=>setChat(e.target.value)} placeholder="描述计算任务…"/><button className="primary wide" disabled={busy||!chat.trim()}>发送</button></form><small className="muted">常规模板自动执行；新脚本及高资源任务需复核。</small></aside>
    </div><footer>{busy?'正在处理请求…':'就绪'}<span>STK · 计算持续运行，视图随处可达</span></footer>
  </div>;
}
createRoot(document.getElementById('root')!).render(ExampleView?<React.Suspense fallback={null}><ExampleView/></React.Suspense>:<App/>);
if('serviceWorker' in navigator)void navigator.serviceWorker.register('/sw.js');
