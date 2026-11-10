import React,{useCallback,useEffect,useLayoutEffect,useRef,useState} from 'react';
import {flushSync} from 'react-dom';
import {createRoot} from 'react-dom/client';
import {action,api,ApiError,events,hasToken,Json,readNode,setToken} from './api';
import {conversationTitle,type Entry,useConversations} from './conversations';
import ErrorBoundary from './ErrorBoundary';
import type {GraphSource} from './GraphPanel';
import TaskObservation from './TaskObservation';
import {isTerminalTaskState,type TaskFact,type TaskScope} from './taskFacts';
import './style.css';
const Viewer=React.lazy(()=>import('./Viewer'));
const GraphPanel=React.lazy(()=>import('./GraphPanel'));
// Development only: `?example=1` renders the payload v2 example without a hub (not part of production builds).
const ExampleView=import.meta.env.DEV&&new URLSearchParams(location.search).has('example')?React.lazy(()=>import('./ExampleView')):null;
const lostAccess=(error:unknown)=>error instanceof ApiError&&(error.status===401||error.status===403);
type ObservedTask = {scope:TaskScope;name:string;state:string;verifiedIdentity:boolean;exactTerminal:boolean};
// The scene 结果 shows in file mode, bound to the task scope and artifact path of the view.build that produced it.
// Choosing another file only edits the choice: the canvas and its source stay until a new build succeeds.
type Displayed = {scope:TaskScope;path:string;scene:Json};
// Persistent sections: 工作台 is the conversation home. All three stay mounted; only the active one is shown.
type Section='workbench'|'tasks'|'results';
type EnvironmentDisclosure='setup'|'auto-closed'|'open'|'closed';
const SECTIONS:readonly (readonly [Section,string])[]=[['workbench','工作台'],['tasks','任务'],['results','结果']];
// Up to this width the conversation history is opened on demand over the active section instead of a fixed column.
const COMPACT='(max-width: 1050px)';
// The secondary line of a history entry: what it is, then any unsent draft or message it holds.
function entryNote(entry:Entry){
  const kind=entry.kind==='local'?'未保存':entry.kind==='missing'?`已不存在 · ${entry.id.slice(0,6)}`:entry.kind==='unconfirmed'?`正在确认 · ${entry.id.slice(0,6)}`:
    [created(entry.created),entry.id.slice(0,6)].filter(Boolean).join(' · ');
  return kind+(entry.draft?' · 有草稿':'')+(entry.outgoing==='sending'?' · 发送中':entry.outgoing==='failed'?' · 发送失败':'');
}
// Characters that render as nothing or reorder the text around them: a source value containing any of them also
// shows an escaped form, so the exact value can be read as well as copied.
const INVISIBLE=/[\p{Cc}\p{Cf}\p{Zl}\p{Zp}]/gu;
// One value of 来源 details as plain text. IDs and paths (selectable) take the focus and then select themselves, so
// Ctrl+C or a touch copies exactly the value; nothing is written to the clipboard by the page.
function SourceValue({value,selectable=false}:{value:string;selectable?:boolean}){
  const escaped=value.replace(INVISIBLE,c=>`\\u{${c.codePointAt(0)!.toString(16).toUpperCase().padStart(4,'0')}}`);
  return <>{selectable?<code className="source-value" tabIndex={0} onFocus={e=>getSelection()?.selectAllChildren(e.currentTarget)}
    onBlur={e=>{const selection=getSelection();if(selection?.anchorNode&&selection.focusNode&&
      e.currentTarget.contains(selection.anchorNode)&&e.currentTarget.contains(selection.focusNode))selection.removeAllRanges();}}>{value}</code>:
    value?<span className="source-name">{value}</span>:<span className="muted">（无名称）</span>}
    {escaped!==value&&<small className="source-escaped">含不可见字符：{escaped}</small>}</>;
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
  const [selection,setSelection]=useState<TaskScope|null>(null),[artifacts,setArtifacts]=useState<Json[]>([]),[path,setPath]=useState(''),[displayed,setDisplayed]=useState<Displayed|null>(null);
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
  const transcriptOffsets=useRef(new Map<string,number>());
  // A visited transcript is cached for the life of this workbench. Restore its position only when the session
  // changes. A history reply or a switch between workbench sections does not reapply the offset.
  useLayoutEffect(()=>{
    if(messageList.current)messageList.current.scrollTop=transcriptOffsets.current.get(conv.session)??0;
  },[conv.session]);
  const [name,setName]=useState('科学项目'),[logs,setLogs]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[tab,setTab]=useState<Section>('workbench'),[online,setOnline]=useState(navigator.onLine);
  const [environmentDisclosure,setEnvironmentDisclosure]=useState<EnvironmentDisclosure>('setup');
  const environment=useRef<HTMLDetailsElement>(null);
  const [probeText,setProbeText]=useState(''),[graphProbeText,setGraphProbeText]=useState(''),[viewError,setViewError]=useState(''),[graphError,setGraphError]=useState('');
  const [graphSource,setGraphSource]=useState<GraphSource|null>(null);
  // The Tasks shortcut that opened 结果 and the task scope it was pressed in. The next navigation forgets it; only
  // 任务 straight from 结果 gives it the focus back, and only while that exact scope is selected (a reselected task is a
  // new scope) and the shortcut is still there, enabled and wholly in view in 任务, which keeps its scroll offsets.
  const returnFocus=useRef<{scope:TaskScope;launcher:HTMLButtonElement}|null>(null);
  const generation=useRef(0),scopeVersion=useRef(0),activeScope=useRef<TaskScope|null>(null),refreshing=useRef(false),alive=useRef(true);
  const artifactReads=useRef({started:0,applied:0});
  // The displayed record as of the latest change, so a late probe reply can tell whether its scene is still shown.
  const displayedNow=useRef<Displayed|null>(null);
  const show=useCallback((next:Displayed|null)=>{displayedNow.current=next;setDisplayed(next);setProbeText('');setViewError('');},[]);
  const [logRoom,setLogRoom]=useState(false);
  // 来源 details: opened and closed only in the page, over 结果 rather than in its flow, so nothing below moves.
  const [sourceOpen,setSourceOpen]=useState(false);
  const sourceToggle=useRef<HTMLButtonElement>(null),sourcePanel=useRef<HTMLDivElement>(null);
  const closeSource=useCallback(()=>{setSourceOpen(false);sourceToggle.current?.focus({preventScroll:true});},[]);
  const fileChoice=useRef<HTMLSelectElement>(null),modeChoice=useRef<HTMLDivElement>(null),logPane=useRef<HTMLDetailsElement>(null);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
  const selected=devices.find(d=>d.id===node&&!d.revoked);
  // 图谱 is in view only in 结果, in 图谱 mode, with no compact history over it. Out of view it reads no progress and
  // drops a scrub not yet sent; work already sent completes in its own scope and is shown on return.
  const graphActive=tab==='results'&&analysis==='graph'&&!overlay;
  // 图谱 is mounted when first in view and then kept, hidden, for the node it was opened under: a mode or section switch
  // keeps its result, camera and probe. Another node drops it while it is out of view, so it only remounts (and reads
  // its presets) when 图谱 is shown in 结果 again; a changed project or task resets it inside the panel (graphScope).
  const graphKey=selected?.id||'';
  const [graphFor,setGraphFor]=useState<string|null>(null);
  if(graphActive?graphFor!==graphKey:graphFor!==null&&graphFor!==graphKey)setGraphFor(graphActive?graphKey:null);
  const graphKept=graphActive||graphFor===graphKey;
  const tasks:Json[]=selected?.snapshot?.tasks||[];
  const task=selected&&selection?.node===node?selection.task:'';
  const heartbeat=task&&tasks.find(t=>t.id===task&&t.workspace_id===selection?.workspace);
  const observed=observedTask?.scope===selection?observedTask:null;
  const taskBound=!!task&&(!!heartbeat||observed?.verifiedIdentity===true);
  const exactTerminal=observed?.exactTerminal===true;
  let graphTasks=tasks;
  if(taskBound&&observed){
    const row={id:task,name:observed.name,state:observed.state,workspace_id:observed.scope.workspace};
    graphTasks=tasks.some(item=>item.id===task)?tasks.map(item=>item.id===task?row:item):[row,...tasks];
  }
  const shown=taskBound&&displayed?.scope===selection?displayed:null,shownScene=shown?.scene??null;
  // The scope 图谱 works in: the chosen project, and the selected task with its own project once it is bound. Any change
  // (another project with no task selected included) starts the panel afresh and drops its late replies.
  const graphScope=JSON.stringify([workspace,task&&selection?selection.workspace:'',taskBound?task:'']);
  const shownGraphSource=graphSource&&graphSource.node===graphKey&&graphSource.scope===graphScope?graphSource:null;
  const features:unknown=selected?.snapshot?.features;
  const canRead=Array.isArray(features)&&features.includes('read');
  const canReadArtifacts=canRead&&readKinds?.includes('task.artifacts')===true;
  const canReadEvents=canRead&&features.includes('task.events')&&readKinds?.includes('task.events')===true;
  const canReadTask=readKinds===null?null:canRead&&features.includes('task.get')&&readKinds.includes('task.get');
  const taskOnline=online&&selected?.online===true;
  // Readable scope of 任务: the queue lists the chosen node, filtered by the chosen project; the selected task keeps its
  // own scope, which can be another project of the node while no project is chosen.
  const nodes=devices.filter(d=>d.role==='node'&&!d.revoked),workspaces:Json[]=selected?.snapshot?.workspaces||[];
  const environmentReady=!!workspace&&workspaces.some(w=>w.id===workspace);
  const environmentOpen=environmentDisclosure==='setup'||environmentDisclosure==='open';
  // Initial setup retires once, when the workspace belongs to the selected node. A lost scope can reopen the
  // automatically folded panel for recovery; subsequent explicit disclosure choices remain as the user left them.
  useLayoutEffect(()=>{
    if(environmentDisclosure==='setup'&&environmentReady){
      const summary=environment.current?.querySelector('summary'),active=document.activeElement;
      if(summary&&active!==summary&&environment.current?.contains(active))summary.focus({preventScroll:true});
      setEnvironmentDisclosure('auto-closed');
    }else if(environmentDisclosure==='auto-closed'&&!environmentReady)setEnvironmentDisclosure('open');
  },[environmentDisclosure,environmentReady]);
  const workspaceName=(id:string)=>workspaces.find(w=>w.id===id)?.name||id.slice(0,8);
  const nodeName=selected?selected.name||node.slice(0,8):'';
  const queue=tasks.filter(t=>!workspace||t.workspace_id===workspace);
  const queueScope=`${nodeName} · ${!online?'最近状态':selected?.online?'在线':'离线'} · ${workspace?workspaceName(workspace):'全部项目'}`;
  const queueEmpty=!selected?(!devicesRead?(online?'正在读取执行节点…':'控制服务未连接。恢复连接后，这里显示执行节点的任务队列。'):
      !nodes.length?'控制服务中暂无执行节点。节点配对后，这里显示它的任务队列。':'在下方「运行环境」中选择执行节点和项目，这里显示任务队列。'):
    !tasks.length?'节点快照中暂无任务。':!queue.length?`${workspaceName(workspace)} 中暂无任务，可在下方「新建任务」中提交。`:'';
  const clearTask=useCallback(()=>{
    generation.current++;scopeVersion.current++;activeScope.current=null;
    setSelection(null);setObservedTask(null);setPath('');setArtifacts([]);show(null);setLogs('');setGraphProbeText('');setGraphSource(null);setLogRoom(false);
  },[show]);
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
    const opensOverlay=query.matches&&inside;
    if(opensOverlay)returnFocus.current=null;
    setWide(!query.matches);setHistoryOpen(opensOverlay);
  };change();query.addEventListener('change',change);return()=>query.removeEventListener('change',change);},[]);
  useEffect(()=>{if(wide&&keepHistoryFocus.current){keepHistoryFocus.current=false;focusHistory();}},[wide]);
  // Escape closes the overlay from anywhere on the page and returns the focus to the 历史 toggle.
  useEffect(()=>{
    if(!overlay)return;
    const key=(e:KeyboardEvent)=>{if(e.key==='Escape'){e.preventDefault();closeHistory();}};
    window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);
  },[overlay]);
  // 来源 details close when 结果 is left, and on a press outside them; the press itself goes on to its target.
  useEffect(()=>{if(tab!=='results'||overlay)setSourceOpen(false);},[tab,overlay]);
  useEffect(()=>{
    if(!sourceOpen||overlay)return;
    const press=(e:PointerEvent)=>{
      const target=e.target as Node;
      if(!sourcePanel.current?.contains(target)&&!sourceToggle.current?.contains(target))setSourceOpen(false);
    };
    const key=(e:KeyboardEvent)=>{if(e.key==='Escape'&&!e.defaultPrevented){e.preventDefault();closeSource();}};
    document.addEventListener('pointerdown',press,true);window.addEventListener('keydown',key);
    return()=>{document.removeEventListener('pointerdown',press,true);window.removeEventListener('keydown',key);};
  },[sourceOpen,overlay,closeSource]);
  // The open details end above the bottom of 结果 (and scroll inside), so on a short or narrow page they stay in view.
  useLayoutEffect(()=>{
    if(!sourceOpen)return;
    const fit=()=>{
      const panel=sourcePanel.current,area=panel?.closest('section'),title=panel?.parentElement;
      if(!panel||!area||!title)return;
      const viewport=area.getBoundingClientRect(),header=title.getBoundingClientRect();
      const below=viewport.bottom-header.bottom-12;
      const constrained=below<120;
      panel.style.top=constrained?`${viewport.top-header.top+2}px`:'';
      panel.style.maxHeight=`${Math.max(0,Math.min(460,Math.floor(constrained?viewport.height-12:below)))}px`;
    };
    fit();window.addEventListener('resize',fit);return()=>window.removeEventListener('resize',fit);
  },[sourceOpen]);
  useEffect(()=>{void refresh();const abort=new AbortController();void events(()=>void refresh(),abort.signal);const timer=setInterval(()=>void refresh(),5000);return()=>{abort.abort();clearInterval(timer);};},[refresh]);
  useEffect(()=>{if(node&&!selected)clearNode();},[node,selected,clearNode]);
  // A graph error or probe reply belongs to the scope it was raised in.
  useEffect(()=>{setGraphError('');setGraphProbeText('');},[graphKey,graphScope]);
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
  async function run(fn:()=>Promise<void>,active?:()=>boolean){
    const report=active?setViewError:setError;
    setBusy(true);report('');
    try{await fn();if(alive.current&&(!active||active()))await refresh();}
    catch(error){if(alive.current){if(lostAccess(error))disconnect();else if(!active||active())report(String(error));}}
    finally{setBusy(false);}
  }
  const invoke=(kind:string,payload:Json,target=node,active?:()=>boolean)=>action(target,kind,payload,
    ()=> (active?setViewError:setError)('操作等待复核，请在任务面板查看完整参数。'),{active});
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
  // A build is accepted only for the scope and file choice it was started with: another task, project or node, or
  // another file choice before it completes, discards it. The accepted scene keeps that scope and path.
  function loadView(){const current=++generation.current,scope=activeScope.current,source=path;if(!scope)return;
    const active=()=>alive.current&&generation.current===current&&activeScope.current===scope;
    const options:Json={mode,axis};if(mode==='slice')options.index=index;if(mode==='iso')options.level=level;if(mode==='vectors')options.component='magnitude';
    void run(async()=>{
      const item=await invoke('view.build',{task_id:scope.task,path:source,options},scope.node,active);
      if(!item.result||!active())return;
      const manifest=item.result.manifest;
      const reported=manifest?.source;
      if(reported!==undefined&&(reported?.task_id!==scope.task||reported?.path!==source)){
        throw new Error('返回的结果来源与所选文件不符。');
      }
      const level=(manifest.value_range[0]+manifest.value_range[1])/2;
      show({scope,path:source,scene:item.result});setLevel(level);
    },active);
  }
  async function readLogs(){const version=scopeVersion.current;const item=await invoke('task.logs',{task_id:task});if(item.result&&scopeVersion.current===version){const bytes=Uint8Array.from(atob(item.result.data),c=>c.charCodeAt(0));setLogs(new TextDecoder().decode(bytes));setProbeText('');setGraphProbeText('');}}
  // An explicit 结果 / 读取日志 click in Tasks opens 结果 at once and brings the target into view; the read itself
  // keeps its own scope checks and never navigates on completion. The analysis mode and Viewer are left as they are.
  // 读取日志 also gives the open log pane its full bounded height (logRoom, until the task scope changes), so the
  // text that arrives later scrolls inside the pane and moves nothing in 结果, whichever page the user is on then.
  function openResults(target:'files'|'logs',launcher:HTMLButtonElement){
    returnFocus.current=activeScope.current&&{scope:activeScope.current,launcher};
    flushSync(()=>{setTab('results');if(target==='logs')setLogRoom(true);});
    const pane=logPane.current;
    if(target==='logs'&&pane)pane.open=true;
    const element=target==='logs'?pane?.querySelector('summary'):analysis==='file'?fileChoice.current:modeChoice.current?.querySelector<HTMLElement>('[aria-selected="true"]');
    (target==='logs'?pane:element)?.scrollIntoView({block:'nearest'});element?.focus({preventScroll:true});
  }
  // A held Enter repeats on the shortcut that just got the focus back; only a fresh press opens 结果 again.
  const ignoreRepeat=(e:React.KeyboardEvent)=>{if(e.repeat&&e.key==='Enter')e.preventDefault();};
  function openSection(key:Section){
    const back=key==='tasks'&&tab==='results'&&!overlay?returnFocus.current:null;
    returnFocus.current=null;
    if(!back||activeScope.current!==back.scope){setTab(key);setHistoryOpen(false);return;}
    flushSync(()=>setTab(key));
    const {launcher}=back,box=launcher.getBoundingClientRect(),area=launcher.closest('.surface')?.getBoundingClientRect();
    if(launcher.isConnected&&!launcher.disabled&&area&&box.height>0&&
       box.top>=area.top&&box.bottom<=area.bottom&&box.left>=area.left&&box.right<=area.right)launcher.focus({preventScroll:true});
  }
  // Choosing a conversation (or a new one) is one explicit action: it opens 工作台 with that conversation's own
  // transcript, reading position and draft. On a compact page the history closes again.
  function openConversation(id:string|null){
    returnFocus.current=null;
    if(id!==conv.session&&messageList.current)transcriptOffsets.current.set(conv.session,messageList.current.scrollTop);
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
    returnFocus.current=null;
    flushSync(()=>{setSourceOpen(false);setHistoryOpen(true);});
    focusHistory();
  }
  // The unsent text of a conversation the Hub no longer has goes to a new local conversation, ready to send there.
  function moveDraft(){flushSync(()=>conv.moveDraft());composer.current?.focus({preventScroll:true});}
  const sessionRow=conv.saved[conv.session];
  const sessionLabel=conv.missing.has(conv.session)?`已不存在 · ${conv.session.slice(0,6)}`:sessionRow?`${conversationTitle(sessionRow)} · ${conv.session.slice(0,6)}`:
    conv.own.has(conv.session)?'新对话 · 未保存':`正在确认 · ${conv.session.slice(0,6)}`;
  const thread=conv.thread,pending=conv.pending&&!thread.messages.some(m=>m.id===conv.pending!.id)?conv.pending:null;
  // 查询原始值 reads the raw data behind the displayed scene: its own task and path, whatever the file choice is now.
  // The reply is kept only while that scene is still the one shown (a new scene or another task discards it).
  function probeValue(){
    const source=displayedNow.current;if(!source||source!==shown)return;
    const active=()=>alive.current&&displayedNow.current===source&&activeScope.current===source.scope;
    void run(async()=>{
      const result=await invoke('view.probe',{task_id:source.scope.task,path:source.path,position:probe},source.scope.node,active);
      if(result.result&&active())setProbeText(JSON.stringify(result.result,null,2));
    },active);
  }
  // File mode uses the selected task and displayed artifact. Graph mode uses the accepted scene or output cards,
  // whose calculation can bind different tasks than the one selected in the queue.
  const taskName=observed?.name||(heartbeat||null)?.name||task.slice(0,8);
  const graphKind=shownGraphSource?.kind==='local'?'本地数据包':shownGraphSource?.display==='scene'?'显示的三维结果':
    shownGraphSource?.display==='outputs'?'显示的图谱输出':'尚未显示图谱结果';
  const graphBinding=shownGraphSource?.kind==='evaluation'&&shownGraphSource.bindings.length===1?shownGraphSource.bindings[0]:null;
  const graphSummary=shownGraphSource?.kind==='local'?shownGraphSource.file:shownGraphSource?.kind==='evaluation'?
    [shownGraphSource.presetName||shownGraphSource.presetId,graphBinding?(graphBinding.taskName||graphBinding.task.slice(0,8)):
      shownGraphSource.bindings.length>1?`${shownGraphSource.bindings.length} 个计算绑定`:'',
      shownGraphSource.step===null?'':`第 ${shownGraphSource.step} 步`].filter(Boolean).join(' · '):'选择数据源并计算图谱';
  const sourceTask=analysis==='graph'?graphKind:task&&selection?(taskBound?`${nodeName} · ${workspaceName(selection.workspace)} · ${taskName}`:`${nodeName} · ${workspaceName(selection.workspace)} · 正在确认任务`):'未选择任务';
  const sourceFile=analysis==='graph'?graphSummary:!task?'在「任务」中选择任务':shown?`显示 ${shown.path}`:'尚未加载结果文件';
  const sourceNext=analysis==='file'&&taskBound&&path&&path!==shown?.path?`已选 ${path}，加载视图后显示`:'';
  const sourceIds=analysis==='file'&&task&&selection?`节点 ${selection.node}\n项目 ${selection.workspace}\n任务 ${selection.task}${shown?`\n文件 ${shown.path}`:''}`:undefined;
  function leaveSource(e:React.FocusEvent){
    const next=e.relatedTarget;
    if(sourceOpen&&next&&!sourcePanel.current?.contains(next)&&!sourceToggle.current?.contains(next))setSourceOpen(false);
  }
  // 来源 details name the same accepted state in full, one labelled value per row: the selected task's node, project
  // and task (name and ID), then in file mode the file the Viewer shows and, separately, a chosen file not yet loaded.
  const sourceNames=task&&selection?{node:selected?.name??'',workspace:workspaces.find(w=>w.id===selection.workspace)?.name??'',
    task:taskBound?observed?.name||(heartbeat||null)?.name||'':''}:null;
  const graphSourceRows=shownGraphSource?.kind==='local'?<dl>
    <div><dt>本地数据包</dt><dd><SourceValue value={shownGraphSource.file} selectable/></dd></div>
  </dl>:shownGraphSource?.kind==='evaluation'?<dl>
    <div><dt>显示内容</dt><dd>{graphKind}</dd></div>
    <div><dt>图谱预设</dt><dd>{shownGraphSource.presetName&&<SourceValue value={shownGraphSource.presetName}/>}<SourceValue value={shownGraphSource.presetId} selectable/></dd></div>
    {shownGraphSource.output&&<div><dt>输出</dt><dd><SourceValue value={shownGraphSource.output} selectable/></dd></div>}
    <div><dt>节点</dt><dd><SourceValue value={nodeName}/><SourceValue value={shownGraphSource.node} selectable/></dd></div>
    {shownGraphSource.bindings.map(binding=><React.Fragment key={binding.name}>
      <div><dt>计算绑定 <bdi>{binding.name}</bdi></dt><dd>{binding.taskName&&<SourceValue value={binding.taskName}/>}<SourceValue value={binding.task} selectable/></dd></div>
      {binding.workspace&&<div><dt>运行工作区 <bdi>{binding.name}</bdi></dt><dd><SourceValue value={workspaces.find(w=>w.id===binding.workspace)?.name??''}/><SourceValue value={binding.workspace} selectable/></dd></div>}
    </React.Fragment>)}
    {shownGraphSource.step!==null&&<div><dt>已显示时间步</dt><dd>{shownGraphSource.step}</dd></div>}
  </dl>:<p className="muted">尚未显示图谱结果。选择数据源后明确计算，或打开本地数据包。</p>;
  const sourceDetails=<div id="result-source-details" ref={sourcePanel} className="source-details" role="region" aria-label="来源详情" tabIndex={-1}>
    {analysis==='graph'?graphSourceRows:sourceNames&&selection?<dl>
      <div><dt>节点</dt><dd><SourceValue value={sourceNames.node}/><SourceValue value={selection.node} selectable/></dd></div>
      <div><dt>项目</dt><dd><SourceValue value={sourceNames.workspace}/><SourceValue value={selection.workspace} selectable/></dd></div>
      <div><dt>任务</dt><dd>{taskBound?<SourceValue value={sourceNames.task}/>:<span className="muted">正在确认任务</span>}<SourceValue value={selection.task} selectable/></dd></div>
      <div><dt>显示的文件</dt><dd>{shown?<SourceValue value={shown.path} selectable/>:<span className="muted">尚未加载结果文件</span>}</dd></div>
      {sourceNext&&<div><dt>已选文件</dt><dd><SourceValue value={path} selectable/><span className="muted">尚未加载，点「加载视图」后显示</span></dd></div>}
    </dl>:<p className="muted">未选择任务。在「任务」中选择任务后，这里显示它的节点、项目与文件。</p>}
    <div className="source-details-foot"><button type="button" className="quiet" onClick={closeSource}>收起</button></div>
  </div>;
  // Result errors are shown with their own mode in 结果: one raised while that mode is out of view waits for its return.
  const resultNotice=tab==='results'&&!overlay?(analysis==='file'?viewError:graphError):'';
  const notice=error||resultNotice;
  const resultText=analysis==='graph'?graphProbeText:shown?probeText:'';
  return <div className="app"><header><div className="wordmark">STK <span>科学工作台</span></div><span className={online?'connection':'connection offline'}>{online?'控制服务已连接':'连接中断 · 显示最近状态'}</span><button className="quiet" onClick={disconnect}>断开</button></header>
    {notice&&<div className="notice" role="alert">{notice}<button onClick={()=>error?setError(''):analysis==='file'?setViewError(''):setGraphError('')}>关闭</button></div>}
    <div className={wide?'workspace with-history':'workspace'}>
    <nav className="section-nav" aria-label="工作区">{SECTIONS.map(([key,label])=><button type="button" className={tab===key?'active':''} aria-current={tab===key?'page':undefined} key={key} onClick={()=>openSection(key)}>{label}</button>)}
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
      {taskBound&&<div className="inline"><button disabled={busy} onKeyDown={ignoreRepeat} onClick={e=>{openResults('logs',e.currentTarget);void run(readLogs);}}>读取日志</button><button disabled={busy} onKeyDown={ignoreRepeat} onClick={e=>{openResults('files',e.currentTarget);void run(files);}}>结果</button><button disabled={busy} onClick={()=>void run(async()=>{await invoke('task.cancel',{task_id:task});})}>取消</button></div>}
      {actions.filter(a=>a.state==='review').map(a=><article className="review" key={a.id}><strong>等待执行复核</strong><p>{a.review_reason}</p><pre>{JSON.stringify(a.request.payload,null,2)}</pre>{[true,false].map(approved=><button key={String(approved)} disabled={busy} onClick={()=>void run(async()=>{await api(`actions/${a.id}/review`,'POST',{approved});})}>{approved?'批准执行':'拒绝'}</button>)}</article>)}
      <details className="setting" ref={environment} open={environmentOpen}><summary onClick={event=>{
        event.preventDefault();setEnvironmentDisclosure(environmentOpen?'closed':'open');
      }}>运行环境 · {nodeName||'未选择节点'}{selected&&` · ${workspace?workspaceName(workspace):'未选择项目'}`}</summary>
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
    <section className={`analysis surface${tab==='results'?'':' surface-hidden'}`} inert={tab!=='results'||overlay}><div className="view-title" onBlur={leaveSource}><div><h1>{analysis==='graph'?'图谱视图':shownScene?.manifest.field||'科学结果'}</h1>
      <div className="source-row"><p className="result-source" aria-label="结果来源" title={sourceIds}><span>{sourceTask}</span><span className="sr-only">，</span>
        <span className="source-file"><span>{sourceFile}</span>{sourceNext&&<span className="source-next" title={sourceNext}>{sourceNext}</span>}</span></p>
        <button type="button" ref={sourceToggle} className="source-toggle" aria-expanded={sourceOpen} aria-controls={sourceOpen?'result-source-details':undefined} onClick={()=>setSourceOpen(open=>!open)}>来源</button></div></div><span className="muted">拖动旋转 · 滚轮缩放 · 点击探针</span>
      {sourceOpen&&sourceDetails}</div>
      <div className="mode-switch" ref={modeChoice} role="tablist" aria-label="分析方式">{([['file','结果文件'],['graph','图谱']] as const).map(([key,label])=><button key={key} role="tab" aria-selected={analysis===key} className={analysis===key?'active':''} onClick={()=>setAnalysis(key)}>{label}</button>)}</div>
      {/* Both analysis modes stay mounted once shown; the inactive one keeps its size but takes no space, focus or pointer. */}
      {graphKept&&<div className={analysis==='graph'?'mode-pane graph-mode':'mode-pane graph-mode mode-hidden'} inert={analysis!=='graph'}><React.Suspense fallback={<div className="viewport empty">正在加载图谱模块…</div>}><GraphPanel key={graphKey} node={selected?node:''} scope={graphScope} task={taskBound?task:''} tasks={graphTasks} artifacts={taskBound?artifacts:[]} canReadEvents={canReadEvents&&taskOnline&&graphActive} active={graphActive} onError={setGraphError} onLog={setGraphProbeText} onSource={setGraphSource}/></React.Suspense></div>}
      <div className={analysis==='file'?'mode-pane file-mode':'mode-pane file-mode mode-hidden'} inert={analysis!=='file'}>
      <div className="view-controls"><label>结果 / 时间步<select aria-label="结果文件" ref={fileChoice} value={taskBound?path:''} onChange={e=>{setPath(e.target.value);generation.current++;setViewError('');}}><option value="">选择数据文件</option>{(taskBound?artifacts:[]).filter(a=>/\.(vti|vtk|npy|dat)$/.test(a.path)).map(a=><option key={a.path} value={a.path}>{a.path}</option>)}</select></label>
      <label>视图<select value={mode} onChange={e=>setMode(e.target.value)}><option value="slice">切片</option><option value="iso">等值面</option><option value="vectors">向量箭头</option></select></label>
      {mode==='slice'&&<><label>方向<select value={axis} onChange={e=>setAxis(Number(e.target.value))}>{['X','Y','Z'].map((v,i)=><option key={v} value={i}>{v}</option>)}</select></label><label>索引<input type="number" min="0" value={index} onChange={e=>setIndex(Number(e.target.value))}/></label></>}
      {mode==='iso'&&<label>等值<input type="number" value={level} onChange={e=>setLevel(Number(e.target.value))}/></label>}
      <button disabled={busy||!taskBound||!path} onClick={loadView}>加载视图</button></div>
      <ErrorBoundary resetKey={shownScene}><React.Suspense fallback={<div className="viewport empty">正在加载三维模块…</div>}><Viewer scene={shownScene} onPick={setProbe}/></React.Suspense></ErrorBoundary>
      {shownScene&&<div className="legend"><span>{shownScene.manifest.value_range[0].toPrecision(5)}</span><i/><span>{shownScene.manifest.value_range[1].toPrecision(5)} {shownScene.manifest.units}</span><small>{shownScene.manifest.display_reduced?'显示网格已简化':'完整显示网格'} · 数值查询使用原始数据</small></div>}
      <div className="probe"><strong>物理坐标探针</strong>{probe.map((v,i)=><input aria-label={`探针${'XYZ'[i]}`} key={i} type="number" value={v} onChange={e=>setProbe(probe.map((n,j)=>i===j?Number(e.target.value):n))}/>)}<button disabled={busy||!shown} onClick={probeValue}>查询原始值</button></div></div>
      <details className={logRoom?'logs log-room':'logs'} ref={logPane} open><summary>日志 / 探针结果</summary><pre>{(selected&&(resultText||logs))||'选择任务读取日志，或在三维视图中选取一个位置。'}</pre></details>
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
