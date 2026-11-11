import React,{useCallback,useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {flushSync} from 'react-dom';
import {createRoot} from 'react-dom/client';
import {action,api,ApiError,events,hasToken,Json,readNode,setToken} from './api';
import {conversationTitle,type Entry,useConversations} from './conversations';
import ErrorBoundary from './ErrorBoundary';
import type {GraphSource,ProbeReading} from './GraphPanel';
import TaskObservation from './TaskObservation';
import {isTerminalTaskState,taskStateLabel,type TaskFact,type TaskScope} from './taskFacts';
import './style.css';
const Viewer=React.lazy(()=>import('./Viewer'));
const GraphPanel=React.lazy(()=>import('./GraphPanel'));
// Development only: `?example=1` renders the payload v2 example without a hub (not part of production builds).
const ExampleView=import.meta.env.DEV&&new URLSearchParams(location.search).has('example')?React.lazy(()=>import('./ExampleView')):null;
const lostAccess=(error:unknown)=>error instanceof ApiError&&(error.status===401||error.status===403);
type ObservedTask = {scope:TaskScope;name:string;state:string;cancelRequested:boolean;verifiedIdentity:boolean;exactTerminal:boolean};
type ArtifactConnection = {scope:TaskScope;modern:boolean;observesTask:boolean};
type ArtifactTarget = {connection:ArtifactConnection;succeeded:boolean;exactTerminal:boolean};
type ArtifactRead = {target:ArtifactTarget;controller:AbortController;result:Promise<Json[]|null>;accepted?:Json[]};
type DefaultPick = {scope:TaskScope;open:boolean;edits:number};
// The stage one 在查看器中打开 click is in, for the footer: waiting for the list it needs (`listing`), or for the
// build of the exact file it chose (`loading`, with that file's path). Each stage is its own object, the identity of
// the current operation, so a later stage or a newer click never inherits an earlier one.
type OpenProgress = {connection:ArtifactConnection;pick:DefaultPick;stage:'listing'|'loading';path:string};
// The scene 结果 shows in file mode, bound to the task scope and artifact path of the view.build that produced it.
// Choosing another file only edits the choice: the canvas and its source stay until a new build succeeds.
type Displayed = {scope:TaskScope;path:string;scene:Json};
// The task log 结果 shows: the text of one stream as accepted for the task scope it was read in. `next` is the source
// byte offset the Runtime reported after the accepted bytes (null for a reply without offsets, which cannot be
// continued safely); `tail` holds the bytes of a UTF-8 character split at that offset, shown once the rest arrives.
// `ended`: an empty chunk while the task was already terminal, so nothing more will be written. `idle`: the latest
// continuation found no new bytes while the task was still running.
type LogStream='stdout'|'stderr';
type TaskLog = {scope:TaskScope;stream:LogStream;order:number;text:string;next:number|null;tail:Uint8Array;ended:boolean;idle:boolean};
const LOG_STREAMS:readonly (readonly [LogStream,string])[]=[['stdout','标准输出'],['stderr','标准错误']];
// The decoded text of `bytes` and the trailing bytes of a character that continues past them. A character is never
// counted by its displayed length: offsets stay in source bytes, and an incomplete sequence waits for the next chunk.
function decodeLog(bytes:Uint8Array,first:boolean,final:boolean):{text:string;tail:Uint8Array}{
  let cut=bytes.length;
  if(!final){
    let lead=bytes.length-1;
    while(lead>=0&&lead>bytes.length-4&&(bytes[lead]&0xc0)===0x80)lead--;
    const byte=lead<0?0:bytes[lead],width=byte>=0xf8?1:byte>=0xf0?4:byte>=0xe0?3:byte>=0xc0?2:1;
    if(width>1&&bytes.length-lead<width)cut=lead;
  }
  // A byte-order mark is dropped only at the start of the stream, as a single read of the whole file would.
  return {text:new TextDecoder('utf-8',{ignoreBOM:!first}).decode(bytes.subarray(0,cut)),tail:bytes.slice(cut)};
}
const logCount=(value:unknown):value is number=>typeof value==='number'&&Number.isSafeInteger(value)&&value>=0;
// A published file the 结果文件 list offers.
const viewable=(artifact:Json)=>/\.(vti|vtk|npy|dat)$/i.test(artifact.path);
// The rule the desktop's 在查看器中打开 uses for one step (JobsState sole_task_vti): a published path in canonical relative
// POSIX form, as view.build and the graph accept it verbatim (no absolute path, drive letter, backslash, control
// character, or empty, "." or ".." segment), at most 1024 characters.
const canonicalArtifactPath=(path:unknown):path is string=>typeof path==='string'&&!!path&&[...path].length<=1024&&
  !/[\\\u0000-\u001f\u007f]/.test(path)&&!/^[A-Za-z]:/.test(path)&&path.split('/').every(part=>part&&part!=='.'&&part!=='..');
// Logs and notes a result may carry beside its data; anything else may be a result.
const noteArtifact=(path:string)=>/\.(log|txt|md)$/i.test(path);
// The one VTI of a published list whose other entries are only logs or notes. Every other file (DAT, NPY, VTK, HDF5,
// JSON, images, plugin formats) counts as a possible result, so a mixed list keeps the two-step route. The whole list
// is refused when any entry has a non-canonical path, a digest that is not lowercase SHA-256, a size that is not a
// whole non-negative number, or a path that repeats another (also by case) or names a directory of another entry.
// The file must also be one the 结果文件 list offers, so the choice it makes is a listed option.
function soleVti(list:unknown[]):Json|null{
  const folded=new Set<string>();
  let candidate:Json|null=null;
  for(const entry of list){
    if(!entry||typeof entry!=='object')return null;
    const file=entry as Json;
    if(!canonicalArtifactPath(file.path)||typeof file.sha256!=='string'||!/^[0-9a-f]{64}$/.test(file.sha256)||
       !Number.isSafeInteger(file.size)||file.size<0)return null;
    const key=file.path.toLowerCase();
    if(folded.has(key))return null;
    folded.add(key);
    if(!noteArtifact(file.path)){
      if(candidate)return null;
      candidate=file;
    }
  }
  for(const key of folded){
    for(let slash=key.indexOf('/');slash!==-1;slash=key.indexOf('/',slash+1)){
      if(folded.has(key.slice(0,slash)))return null;
    }
  }
  return candidate&&/\.vti$/i.test(candidate.path)&&candidate.size>0?candidate:null;
}
// Persistent sections: 工作台 is the conversation home. All three stay mounted; only the active one is shown.
type Section='workbench'|'tasks'|'results';
type EnvironmentDisclosure='setup'|'auto-closed'|'open'|'closed';
const RUN_ENVIRONMENT='stk-run-environment';
const scopeId=(value:unknown):value is string=>typeof value==='string'&&/^[a-f0-9]{32}$/.test(value);
function rememberedEnvironment(devices:Json[]):{node:string;workspace:string}|null{
  try{
    const choice=JSON.parse(sessionStorage.getItem(RUN_ENVIRONMENT)??'null');
    if(!scopeId(choice?.node)||!scopeId(choice?.workspace))return null;
    const node=devices.find(device=>device.id===choice.node&&device.role==='node'&&!device.revoked);
    if(Array.isArray(node?.snapshot?.workspaces)&&node.snapshot.workspaces.some((row:Json)=>row.id===choice.workspace)){
      return {node:choice.node,workspace:choice.workspace};
    }
  }catch{/* A malformed tab preference is discarded on the first accepted listing. */}
  return null;
}
// 新建任务 is closed by default. A workspace created and adopted from 运行环境 opens it once; any summary click is the
// user's choice from then on, which later creations keep.
type NewTaskDisclosure='default'|'open'|'closed';
const SECTIONS:readonly (readonly [Section,string])[]=[['workbench','工作台'],['tasks','任务'],['results','结果']];
// Up to this width the conversation history is opened on demand over the active section instead of a fixed column.
// The native workbench switches its rail at the same logical width.
const COMPACT='(max-width: 700px)';
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
    for(const key of ['stk-event-cursor','stk-last-action','stk-session',RUN_ENVIRONMENT])sessionStorage.removeItem(key);
    setConnected(false);
  },[]);
  return connected?<Workbench disconnect={disconnect}/>:<Connect connected={()=>{
    sessionStorage.removeItem(RUN_ENVIRONMENT);
    setConnected(true);
  }}/>;
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
  const levelEdited=useRef(false);
  // Edits of 视图, 方向, 索引 and 等值: one made while 在查看器中打开 waits for its list leaves the open to 加载视图.
  const viewEdits=useRef(0);
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
  const [name,setName]=useState('科学项目'),[log,setLog]=useState<TaskLog|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[tab,setTab]=useState<Section>('workbench'),[online,setOnline]=useState(navigator.onLine);
  const [environmentDisclosure,setEnvironmentDisclosure]=useState<EnvironmentDisclosure>('setup');
  const environment=useRef<HTMLDetailsElement>(null);
  const restoreEnvironment=useRef(true);
  const [newTaskDisclosure,setNewTaskDisclosure]=useState<NewTaskDisclosure>('default');
  const newTaskOpen=newTaskDisclosure==='open';
  const [fileProbe,setFileProbe]=useState<ProbeReading|null>(null),[graphProbe,setGraphProbe]=useState<ProbeReading|null>(null);
  const [viewError,setViewError]=useState(''),[graphError,setGraphError]=useState('');
  const [graphSource,setGraphSource]=useState<GraphSource|null>(null);
  // The Tasks shortcut that opened 结果 and the task scope it was pressed in. The next navigation forgets it; only
  // 任务 straight from 结果 gives it the focus back, and only while that exact scope is selected (a reselected task is a
  // new scope) and the shortcut is still there, enabled and wholly in view in 任务, which keeps its scroll offsets.
  const returnFocus=useRef<{scope:TaskScope;launcher:HTMLButtonElement}|null>(null);
  const generation=useRef(0),scopeVersion=useRef(0),activeScope=useRef<TaskScope|null>(null),refreshing=useRef(false),alive=useRef(true);
  const artifactReads=useRef({started:0,applied:0}),logReads=useRef(0);
  const modernArtifacts=useRef<ArtifactRead|null>(null);
  // The accepted log as of the latest change, so a continuation reply can tell whether it still extends it.
  const logNow=useRef<TaskLog|null>(null),continuing=useRef(false);
  const acceptLog=useCallback((next:TaskLog|null)=>{logNow.current=next;setLog(next);},[]);
  // The explicit Tasks shortcut 在查看器中打开 may choose the sole file from its own accepted reply for a successful
  // task, and open a sole published VTI in one step (`open`: the click was in 切片 view; `edits`: viewEdits then).
  // Leaving 结果, opening history over it, switching mode, editing the file choice or changing tasks drops the pick.
  const defaultPick=useRef<DefaultPick|null>(null),fileEdited=useRef(false);
  // The current stage of that click while it is the one in progress; see openProgress below for when it is shown.
  const [opening,setOpening]=useState<OpenProgress|null>(null);
  // Dropping the pick ends a click still waiting for its list (that wait no longer opens anything). A build already
  // sent keeps its stage, which the render checks against the page, connection, task and file.
  const dropPick=useCallback(()=>{defaultPick.current=null;setOpening(current=>current?.stage==='listing'?null:current);},[]);
  const completedTaskScopeNow=useRef<TaskScope|null>(null);
  const exactCompletedTaskScopeNow=useRef<TaskScope|null>(null);
  // 结果 is shown in 结果文件 mode with no compact history over it, as of the latest render.
  const filesShown=useRef(false);
  // The displayed record as of the latest change, so a late probe reply can tell whether its scene is still shown.
  const displayedNow=useRef<Displayed|null>(null);
  const readingOrder=useRef(0);
  const beginReading=useCallback(()=>++readingOrder.current,[]);
  const show=useCallback((next:Displayed|null)=>{displayedNow.current=next;setDisplayed(next);setFileProbe(null);setViewError('');},[]);
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
  const completedTaskScope=taskBound&&(observed?.state??(heartbeat||null)?.state)==='succeeded'?selection:null;
  completedTaskScopeNow.current=completedTaskScope;
  filesShown.current=tab==='results'&&analysis==='file'&&!overlay;
  const exactTerminal=observed?.exactTerminal===true;
  exactCompletedTaskScopeNow.current=exactTerminal?completedTaskScope:null;
  let graphTasks=tasks;
  if(taskBound&&observed){
    const row={id:task,name:observed.name,state:observed.state,cancel_requested:observed.cancelRequested,workspace_id:observed.scope.workspace};
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
  const artifactConnection=useMemo(()=>taskBound&&taskOnline&&selection?
    {scope:selection,modern:canReadArtifacts,observesTask:canReadTask===true}:null,
    [selection,taskBound,taskOnline,canReadArtifacts,canReadTask]);
  const artifactTarget=useMemo(()=>artifactConnection?.modern?{connection:artifactConnection,succeeded:!!completedTaskScope,exactTerminal}:null,
    [artifactConnection,completedTaskScope,exactTerminal]);
  const artifactTargetNow=useRef(artifactTarget);
  artifactTargetNow.current=artifactTarget;
  const artifactConnectionNow=useRef(artifactConnection);
  artifactConnectionNow.current=artifactConnection;
  // The stage of the current 在查看器中打开 holds for the same connection and task while its request can still open
  // something: waiting for its list with the pick kept (leaving 结果, 图谱, the compact history or a file choice drop
  // it), or loading the file it chose while that file is still the choice, not yet shown, of a task still successful.
  // Anything else ends it for good; the requests keep their own checks. It is shown only while 结果文件 is in view
  // with no history over it, so a build still pending on the return is named again rather than offered as 加载视图.
  const openingHeld=opening&&busy&&opening.connection===artifactConnection&&opening.pick.scope===selection&&
    (opening.stage==='listing'?!path&&defaultPick.current===opening.pick:
      path===opening.path&&shown?.path!==path&&completedTaskScope===selection)?opening:null;
  if(opening&&!openingHeld)setOpening(null);
  const openProgress=openingHeld&&tab==='results'&&analysis==='file'&&!overlay?openingHeld:null;
  const loadingChoice=openProgress?.stage==='loading';
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
    generation.current++;scopeVersion.current++;activeScope.current=null;dropPick();fileEdited.current=false;levelEdited.current=false;
    setSelection(null);setObservedTask(null);setPath('');setArtifacts([]);show(null);acceptLog(null);setGraphProbe(null);setGraphSource(null);setLogRoom(false);
  },[show,acceptLog,dropPick]);
  const selectNode=useCallback((id:string)=>{
    restoreEnvironment.current=false;
    sessionStorage.removeItem(RUN_ENVIRONMENT);
    clearTask();setNode(id);setWorkspace('');
  },[clearTask]);
  const nodeGone=useCallback((scope:TaskScope)=>{if(activeScope.current===scope)selectNode('');},[selectNode]);
  const observeTask=useCallback((scope:TaskScope,fact:TaskFact,verifiedIdentity:boolean)=>{
    if(activeScope.current!==scope)return;
    setObservedTask(previous=>{
      const known=previous?.scope===scope?previous:null;
      const exactTerminal=known?.exactTerminal===true||(fact.exact&&isTerminalTaskState(fact.state));
      if(known&&known.state===fact.state&&known.name===fact.name&&known.cancelRequested===fact.cancelRequested&&known.verifiedIdentity===verifiedIdentity&&
         known.exactTerminal===exactTerminal)return known;
      return {scope,name:fact.name,state:fact.state,cancelRequested:fact.cancelRequested,verifiedIdentity,exactTerminal};
    });
  },[]);
  const acceptArtifacts=useCallback((version:number,request:number,result:unknown):result is Json[]=>{
    if(!alive.current||scopeVersion.current!==version||request<=artifactReads.current.applied||
       !Array.isArray(result)||result.some(file=>!file||typeof file.path!=='string'))return false;
    artifactReads.current.applied=request;
    setArtifacts(result);
    return true;
  },[]);
  const readArtifacts=useCallback((target:ArtifactTarget,refresh=false)=>{
    const previous=modernArtifacts.current;
    if(previous?.target===target&&(!refresh||!previous.accepted))return previous.result;
    previous?.controller.abort();
    const controller=new AbortController(),scope=target.connection.scope;
    const version=scopeVersion.current,request=++artifactReads.current.started;
    const result=readNode(scope.node,'task.artifacts',{task_id:scope.task},controller.signal).then(receipt=>{
      if(artifactTargetNow.current!==target||controller.signal.aborted||activeScope.current!==scope)return null;
      if(acceptArtifacts(version,request,receipt)){
        entry.accepted=receipt;
        return receipt;
      }
      throw new Error('任务产物清单格式无效。');
    }).catch(error=>{
      if(modernArtifacts.current?.controller===controller)modernArtifacts.current=null;
      if(artifactTargetNow.current!==target||controller.signal.aborted||activeScope.current!==scope)return null;
      throw error;
    });
    const entry:ArtifactRead={target,controller,result};
    modernArtifacts.current=entry;
    return result;
  },[acceptArtifacts]);
  function selectWorkspace(id:string,created=false){
    restoreEnvironment.current=false;
    // A successful explicit creation can precede the node's next listing. Only remember its exact returned ID.
    if(selected?.role==='node'&&scopeId(node)&&scopeId(id)&&(created||workspaces.some(row=>row.id===id))){
      sessionStorage.setItem(RUN_ENVIRONMENT,JSON.stringify({node,workspace:id}));
    }else sessionStorage.removeItem(RUN_ENVIRONMENT);
    clearTask();setWorkspace(id);
  }
  // 新建 in 运行环境: the receipt's workspace is chosen only while this instance and the node and selection the create
  // was sent from are current (scopeVersion), and only by the ID the Runtime returned. Adopting it is the evidence
  // that opens 新建任务 by default; a review, a receipt without an ID or a late reply changes nothing. Nothing is
  // submitted, no draft is touched and the section stays as it is.
  async function createWorkspace(){
    const version=scopeVersion.current;
    const a=await invoke('workspace.create',{name});
    const id:unknown=a.result?.id;
    if(!alive.current||scopeVersion.current!==version||a.state!=='succeeded'||!scopeId(id))return;
    selectWorkspace(id,true);
    setNewTaskDisclosure(current=>current==='default'?'open':current);
  }
  const refresh=useCallback(async()=>{
    if(refreshing.current)return;refreshing.current=true;
    try{
      const [d,a,s,p]=await Promise.all([api('devices'),api('actions'),api('sessions?include_labels=true'),api('policy').catch(error=>{
        if(lostAccess(error))throw error;
        return error instanceof ApiError&&(error.status===404||error.status===501)?{}:null;
      })]);
      if(!alive.current)return;
      setDevices(d);setDevicesRead(true);setActions(a);mergeList(s);setOnline(true);
      // Consume the tab preference only with an authenticated listing. A failed first refresh leaves it pending,
      // with neither selection shown, so the ordinary refresh path can validate it when connectivity returns.
      if(restoreEnvironment.current&&Array.isArray(d)){
        restoreEnvironment.current=false;
        const choice=rememberedEnvironment(d);
        if(choice){setNode(choice.node);setWorkspace(choice.workspace);}
        else sessionStorage.removeItem(RUN_ENVIRONMENT);
      }
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
    if(opensOverlay){returnFocus.current=null;dropPick();}
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
  useEffect(()=>{if(node&&!selected)selectNode('');},[node,selected,selectNode]);
  // A graph error or probe reply belongs to the scope it was raised in.
  useEffect(()=>{setGraphError('');setGraphProbe(null);},[graphKey,graphScope]);
  useEffect(()=>{
    if(!artifactTarget)return;
    void readArtifacts(artifactTarget).catch(error=>{if(lostAccess(error))disconnect();});
    return()=>{
      const entry=modernArtifacts.current;
      if(entry?.target===artifactTarget){entry.controller.abort();modernArtifacts.current=null;}
    };
  },[artifactTarget,readArtifacts,disconnect]);
  async function run(fn:()=>Promise<void>,active?:()=>boolean){
    const report=active?setViewError:setError;
    setBusy(true);report('');
    try{await fn();if(alive.current&&(!active||active()))await refresh();}
    catch(error){if(alive.current){if(lostAccess(error))disconnect();else if(!active||active())report(String(error));}}
    finally{setBusy(false);}
  }
  const invoke=(kind:string,payload:Json,target=node,active?:()=>boolean)=>action(target,kind,payload,
    ()=> (active?setViewError:setError)('操作等待复核，请在任务面板查看完整参数。'),{active});
  async function files(connection:ArtifactConnection|null,pick:DefaultPick|null){
    if(!connection||artifactConnectionNow.current!==connection||activeScope.current!==connection.scope)return;
    // The stage this click shows, replaced only while it is still the current one (see dropPick and openProgress).
    let progress:OpenProgress|null=null;
    const enter=(stage:OpenProgress['stage'],path='')=>{
      if(!pick)return;
      const previous=progress,next:OpenProgress={connection,pick,stage,path};
      progress=next;
      setOpening(current=>current===previous?next:current);
    };
    try{await openFiles(connection,pick,enter);}
    finally{const last=progress;if(last)setOpening(current=>current===last?null:current);}
  }
  async function openFiles(connection:ArtifactConnection,pick:DefaultPick|null,enter:(stage:OpenProgress['stage'],path?:string)=>void){
    const scope=connection.scope;
    let result:Json[]|null;
    if(connection.modern){
      const target=artifactTargetNow.current;
      if(!target||target.connection.scope!==scope)return;
      const accepted=modernArtifacts.current?.target===target?modernArtifacts.current.accepted:undefined;
      // A confirmed sole VTI can open from its current listing. Other uses of this action still refresh the file list.
      const reuse=pick?.open&&target.succeeded&&(!connection.observesTask||target.exactTerminal)&&accepted&&soleVti(accepted);
      // The reused listing is already accepted: the click goes on to its build in the same turn, with no list wait.
      if(reuse&&accepted)result=accepted;
      else{enter('listing');result=await readArtifacts(target,true);}
      const latest=artifactTargetNow.current;
      // The exact terminal read can replace a same-connection heartbeat receipt while this click waits.
      if(latest!==target){
        if(!latest||latest.connection!==target.connection||!latest.exactTerminal||!latest.succeeded||
           !pick||defaultPick.current!==pick)return;
        result=await readArtifacts(latest);
        if(artifactTargetNow.current!==latest)return;
      }
    }else{
      const version=scopeVersion.current,request=++artifactReads.current.started;
      enter('listing');
      const item=await invoke('task.artifacts',{task_id:scope.task},scope.node);
      result=item.state==='succeeded'&&artifactConnectionNow.current===connection&&
        acceptArtifacts(version,request,item.result)?item.result:null;
    }
    if(!result||!pick||defaultPick.current!==pick)return;
    defaultPick.current=null;
    const choices=result.filter(viewable);
    if(choices.length!==1||completedTaskScopeNow.current!==pick.scope||activeScope.current!==pick.scope||
       fileEdited.current||displayedNow.current)return;
    setPath(choices[0].path);
    const sole=soleVti(result);
    if(!sole||sole.path!==choices[0].path||!pick.open||viewEdits.current!==pick.edits||!filesShown.current||
       artifactConnectionNow.current!==connection||
       (connection.observesTask&&exactCompletedTaskScopeNow.current!==scope))return;
    const currentBuild=startBuild(scope);
    const active=()=>currentBuild()&&artifactConnectionNow.current===connection&&completedTaskScopeNow.current===scope;
    setViewError('');
    enter('loading',sole.path);
    try{await buildView(scope,sole.path,{mode:'slice',axis,index},active,sole.sha256);}
    catch(error){if(lostAccess(error))throw error;if(active())setViewError(String(error));}
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
  function startBuild(scope:TaskScope){
    const current=++generation.current;
    return ()=>alive.current&&generation.current===current&&activeScope.current===scope;
  }
  async function buildView(scope:TaskScope,source:string,options:Json,active:()=>boolean,expectedDigest?:string){
    const item=await invoke('view.build',{task_id:scope.task,path:source,options},scope.node,active);
    if(item.state!=='succeeded'||!item.result||!active())return;
    const manifest=item.result.manifest;
    const reported=manifest?.source;
    if((reported!==undefined||expectedDigest)&&(reported?.task_id!==scope.task||reported?.path!==source)){
      throw new Error('返回的结果来源与所选文件不符。');
    }
    if(expectedDigest&&manifest.dataset_id!==expectedDigest)throw new Error('返回的数据摘要与发布文件不符。');
    const midpoint=(manifest.value_range[0]+manifest.value_range[1])/2;
    show({scope,path:source,scene:item.result});
    // Other views can seed an untouched threshold. An iso build used its captured value, and an edit while any
    // build was pending belongs to the next request.
    if(options.mode!=='iso'&&!levelEdited.current)setLevel(midpoint);
  }
  function loadView(){const scope=activeScope.current,source=path;if(!scope)return;
    const active=startBuild(scope);
    const options:Json={mode,axis};if(mode==='slice')options.index=index;if(mode==='iso')options.level=level;if(mode==='vectors')options.component='magnitude';
    void run(()=>buildView(scope,source,options,active),active);
  }
  // One explicit read of one stream with the published task.logs action. Standard output keeps the original payload
  // (the node's default stream); standard error names its stream. The text is accepted only for this instance, the
  // task scope (node, project and task) it was asked in and the latest read, labelled with the stream it asked for.
  // An expired reply or error leaves the accepted log, the section and the focus as they are.
  async function readLogs(stream:LogStream){
    const scope=activeScope.current;if(!scope)return;
    const version=scopeVersion.current,current=++logReads.current,order=beginReading();
    const active=()=>alive.current&&activeScope.current===scope&&scopeVersion.current===version&&logReads.current===current;
    try{
      const item=await invoke('task.logs',stream==='stdout'?{task_id:scope.task}:{task_id:scope.task,stream},scope.node);
      if(!item.result||!active())return;
      const chunk=logChunk(item.result,null);
      const ended=chunk.next!==null&&!chunk.bytes.length&&chunk.terminal;
      const {text,tail}=decodeLog(chunk.bytes,true,chunk.next===null||ended);
      acceptLog({scope,stream,order,text,next:chunk.next,tail,ended,idle:chunk.next!==null&&!ended&&!chunk.bytes.length});
    }catch(error){if(active()||lostAccess(error))throw error;}
  }
  // A null request offset identifies the first read, which may accept a legacy reply without offsets. An explicit
  // continuation, including one from byte zero, must report the exact source byte range it returned.
  function logChunk(result:Json,asked:number|null){
    const invalid=()=>new Error('日志回执格式无效。');
    if(typeof result.data!=='string')throw invalid();
    let bytes:Uint8Array;
    try{bytes=Uint8Array.from(atob(result.data),c=>c.charCodeAt(0));}catch{throw invalid();}
    if(result.offset===undefined&&result.next_offset===undefined){
      if(asked!==null)throw invalid();
      return {bytes,next:null,terminal:false};
    }
    const offset=asked??0;
    if(!logCount(result.offset)||!logCount(result.next_offset)||result.offset!==offset||result.next_offset!==offset+bytes.length)throw invalid();
    return {bytes,next:result.next_offset as number,terminal:result.terminal===true};
  }
  // 继续读取: one task.logs read of the shown stream from the offset accepted last, appended to its text. It is kept
  // only for the same instance, task scope, stream and accepted log (a new read, another stream or another task
  // discards it), in the order of the click. A failure leaves the log as it was, so another click asks the same offset.
  async function continueLog(){
    const base=logNow.current,scope=activeScope.current;
    if(!base||!scope||base.scope!==scope||base.next===null||base.ended||continuing.current)return;
    continuing.current=true;
    const version=scopeVersion.current,current=++logReads.current,order=beginReading(),offset=base.next;
    const active=()=>alive.current&&activeScope.current===scope&&scopeVersion.current===version&&logReads.current===current&&logNow.current===base;
    try{
      const item=await invoke('task.logs',base.stream==='stdout'?{task_id:scope.task,offset}:{task_id:scope.task,stream:base.stream,offset},scope.node);
      if(!item.result||!active())return;
      const chunk=logChunk(item.result,offset);
      const ended=!chunk.bytes.length&&chunk.terminal;
      const bytes=new Uint8Array(base.tail.length+chunk.bytes.length);
      bytes.set(base.tail);bytes.set(chunk.bytes,base.tail.length);
      const {text,tail}=decodeLog(bytes,offset===base.tail.length,ended);
      acceptLog({...base,order,text:base.text+text,next:chunk.next,tail,ended,idle:!ended&&!chunk.bytes.length});
    }catch(error){if(active()||lostAccess(error))throw error;}
    finally{continuing.current=false;}
  }
  // An explicit 在查看器中打开 / 读取日志 click in Tasks opens 结果 at once and brings the target into view; the read itself
  // keeps its own scope checks and never navigates on completion. The analysis mode and Viewer are left as they are.
  // 读取日志 also gives the open log pane its full bounded height (logRoom, until the task scope changes), so the
  // text that arrives later scrolls inside the pane and moves nothing in 结果, whichever page the user is on then.
  function openResults(target:'files'|'logs',launcher:HTMLButtonElement){
    returnFocus.current=activeScope.current&&{scope:activeScope.current,launcher};
    const scope=activeScope.current;
    defaultPick.current=target==='files'&&scope&&completedTaskScope===scope&&analysis==='file'&&
      !path&&!displayedNow.current&&!fileEdited.current?{scope,open:mode==='slice',edits:viewEdits.current}:null;
    const pick=defaultPick.current;
    flushSync(()=>{setTab('results');if(target==='logs')setLogRoom(true);});
    const pane=logPane.current;
    if(target==='logs'&&pane)pane.open=true;
    const element=target==='logs'?pane?.querySelector('summary'):analysis==='file'?fileChoice.current:modeChoice.current?.querySelector<HTMLElement>('[aria-selected="true"]');
    (target==='logs'?pane:element)?.scrollIntoView({block:'nearest'});element?.focus({preventScroll:true});
    return pick;
  }
  function openTaskFiles(launcher:HTMLButtonElement){
    const connection=artifactConnectionNow.current;
    const pick=openResults('files',launcher);
    void run(()=>files(connection,pick));
  }
  // A held Enter repeats on the shortcut that just got the focus back; only a fresh press opens 结果 again.
  const ignoreRepeat=(e:React.KeyboardEvent)=>{if(e.repeat&&e.key==='Enter')e.preventDefault();};
  function openSection(key:Section){
    const back=key==='tasks'&&tab==='results'&&!overlay?returnFocus.current:null;
    returnFocus.current=null;dropPick();
    if(!back||activeScope.current!==back.scope){setTab(key);setHistoryOpen(false);return;}
    flushSync(()=>setTab(key));
    const {launcher}=back,box=launcher.getBoundingClientRect(),area=launcher.closest('.surface')?.getBoundingClientRect();
    if(launcher.isConnected&&!launcher.disabled&&area&&box.height>0&&
       box.top>=area.top&&box.bottom<=area.bottom&&box.left>=area.left&&box.right<=area.right)launcher.focus({preventScroll:true});
  }
  // Choosing a conversation (or a new one) is one explicit action: it opens 工作台 with that conversation's own
  // transcript, reading position and draft. Focus follows keyboard activation and the closing compact history.
  function openConversation(id:string|null,keyboardActivation=false){
    returnFocus.current=null;dropPick();
    if(id!==conv.session&&messageList.current)transcriptOffsets.current.set(conv.session,messageList.current.scrollTop);
    flushSync(()=>{setTab('workbench');setHistoryOpen(false);if(id)conv.select(id);else conv.startNew();});
    if(!id)composer.current?.focus({preventScroll:true});
    else if(!wide||keyboardActivation)messageList.current?.focus({preventScroll:true});
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
    returnFocus.current=null;dropPick();
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
    const order=beginReading();
    const active=()=>alive.current&&displayedNow.current===source&&activeScope.current===source.scope;
    void run(async()=>{
      const result=await invoke('view.probe',{task_id:source.scope.task,path:source.path,position:probe},source.scope.node,active);
      if(result.result&&active())setFileProbe({order,text:JSON.stringify(result.result,null,2)});
    },active);
  }
  // File mode uses the selected task and displayed artifact. Graph mode uses the accepted scene or output cards,
  // whose calculation can bind different tasks than the one selected in the queue.
  const taskName=observed?.name||(heartbeat||null)?.name||task.slice(0,8);
  const completedTask=completedTaskScope?{name:taskName,workspace:completedTaskScope.workspace}:null;
  const graphKind=shownGraphSource?.kind==='local'?'本地数据包':shownGraphSource?.display==='scene'?'显示的三维结果':
    shownGraphSource?.display==='outputs'?'显示的图谱输出':'尚未显示图谱结果';
  const graphBinding=shownGraphSource?.kind==='evaluation'&&shownGraphSource.bindings.length===1?shownGraphSource.bindings[0]:null;
  const graphSummary=shownGraphSource?.kind==='local'?shownGraphSource.file:shownGraphSource?.kind==='evaluation'?
    [shownGraphSource.hdf5?'MuPRO HDF5':shownGraphSource.presetName||shownGraphSource.presetId,graphBinding?(graphBinding.taskName||graphBinding.task.slice(0,8)):
      shownGraphSource.bindings.length>1?`${shownGraphSource.bindings.length} 个计算绑定`:'',
      shownGraphSource.step===null?'':`第 ${shownGraphSource.step} 步`].filter(Boolean).join(' · '):'选择数据源并计算图谱';
  const sourceTask=analysis==='graph'?graphKind:task&&selection?(taskBound?`${nodeName} · ${workspaceName(selection.workspace)} · ${taskName}`:`${nodeName} · ${workspaceName(selection.workspace)} · 正在确认任务`):'未选择任务';
  const sourceFile=analysis==='graph'?graphSummary:!task?'在「任务」中选择任务':shown?`显示 ${shown.path}`:'尚未加载结果文件';
  const sourceNext=analysis==='file'&&taskBound&&path&&path!==shown?.path?`已选 ${path}，${loadingChoice?'正在加载视图…':'加载视图后显示'}`:'';
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
    {shownGraphSource.hdf5?<><div><dt>原生读取器</dt><dd><SourceValue value="mupro.hdf5@1" selectable/></dd></div>
      <div><dt>发布文件</dt><dd><SourceValue value={shownGraphSource.hdf5.artifact.path} selectable/></dd></div>
      <div><dt>发布 SHA-256</dt><dd><SourceValue value={shownGraphSource.hdf5.artifact.sha256} selectable/></dd></div>
      <div><dt>场选择器</dt><dd><SourceValue value={shownGraphSource.hdf5.frame.selector} selectable/></dd></div>
      <div><dt>分量索引</dt><dd>{shownGraphSource.hdf5.component??'标量'}</dd></div></>:
      <div><dt>图谱预设</dt><dd>{shownGraphSource.presetName&&<SourceValue value={shownGraphSource.presetName}/>}<SourceValue value={shownGraphSource.presetId} selectable/></dd></div>}
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
      {sourceNext&&<div><dt>已选文件</dt><dd><SourceValue value={path} selectable/><span className="muted">{loadingChoice?'正在加载视图…':'尚未加载，点「加载视图」后显示'}</span></dd></div>}
    </dl>:<p className="muted">未选择任务。在「任务」中选择任务后，这里显示它的节点、项目与文件。</p>}
    <div className="source-details-foot"><button type="button" className="quiet" onClick={closeSource}>收起</button></div>
  </div>;
  // Result errors are shown with their own mode in 结果: one raised while that mode is out of view waits for its return.
  const resultNotice=tab==='results'&&!overlay?(analysis==='file'?viewError:graphError):'';
  const notice=error||resultNotice;
  // Use the latest accepted reading for this mode, ordered by the user action even if the replies arrive out of order.
  const taskLog=log&&log.scope===selection?log:null;
  const probeReading=analysis==='graph'?graphProbe:shown?fileProbe:null;
  const resultText=probeReading&&(!taskLog||probeReading.order>taskLog.order)?probeReading.text:'';
  const logShown=resultText?null:taskLog;
  const streamLabel=taskLog?LOG_STREAMS.find(([key])=>key===taskLog.stream)![1]:'';
  const logText=taskLog?taskLog.text||`${streamLabel}暂无内容。`:'';
  const streamSwitch=taskBound&&logRoom;
  // 继续读取 is offered for the shown log once its reply reported offsets. It stays in place, inert, when the stream has
  // ended, so a keyboard user keeps the focus on it.
  const logMore=streamSwitch&&logShown&&logShown.next!==null?logShown:null;
  const logNote=!streamSwitch||!logShown?'':logShown.next===null?'此日志回执不含读取位置，不能继续读取。':
    logShown.ended?`${streamLabel}已读完，任务已结束。`:logShown.idle?'暂无新内容，可稍后继续读取。':'';
  return <div className="app"><header><div className="wordmark">STK <span>科学工作台</span></div><span className={online?'connection':'connection offline'}>{online?'控制服务已连接':'连接中断 · 显示最近状态'}</span><button className="quiet" onClick={disconnect}>断开</button></header>
    {notice&&<div className="notice" role="alert">{notice}<button onClick={()=>error?setError(''):analysis==='file'?setViewError(''):setGraphError('')}>关闭</button></div>}
    <div className="workspace">
    <nav className="section-nav" aria-label="工作区">{SECTIONS.map(([key,label])=><button type="button" className={tab===key?'active':''} aria-current={tab===key?'page':undefined} key={key} onClick={()=>openSection(key)}>{label}</button>)}
      {!wide&&<button type="button" ref={historyToggle} className={historyOpen?'history-toggle open':'history-toggle'} aria-expanded={historyOpen} aria-controls="conversation-history" aria-label="对话历史" onClick={toggleHistory}>历史</button>}</nav>
    <section id="conversation-history" ref={historyPanel} aria-label="对话历史" className={`history${wide?'':' history-overlay'}${historyShown?'':' surface-hidden'}`} inert={!historyShown}>
      <div className="history-head"><h2>对话</h2><button type="button" className="new-conversation" onClick={()=>openConversation(null)}>新对话</button></div>
      <ul className="history-list">
        {conv.entries.map(entry=><li key={entry.id}><button type="button" className="conversation" aria-current={entry.id===conv.session?'true':undefined} onClick={e=>openConversation(entry.id,e.detail===0)}><span>{entry.name}</span><small>{entryNote(entry)}</small></button></li>)}
      </ul>
      {!conv.entries.some(entry=>entry.kind==='saved')&&<p className="muted">还没有保存的对话。</p>}
    </section>
    {overlay&&<div className="history-backdrop" aria-hidden="true" onClick={closeHistory}/>}
    <aside className={`tasks panel surface${tab==='tasks'?'':' surface-hidden'}`} inert={tab!=='tasks'||overlay}><div className="section-title"><h2>项目与任务</h2><button className="quiet" onClick={()=>{setTaskRefresh(value=>value+1);void refresh();}}>刷新</button></div>
      <section className="queue" aria-label="任务队列"><div className="queue-head"><h3>任务队列</h3>{selected&&<span className="muted">{queueScope}</span>}</div>
      <div className="task-list">{queue.map(t=><button className={`task ${task===t.id?'selected':''}`} key={t.id} onClick={()=>selectTask(t.id,t.workspace_id)}><span>{t.name||t.id.slice(0,8)}</span><small className={`state ${t.state}`}>{taskStateLabel(t.state,t.cancel_requested===true)}</small></button>)}{queueEmpty&&<p className="muted">{queueEmpty}</p>}</div>
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
      {taskBound&&<div className="inline"><button disabled={busy} onKeyDown={ignoreRepeat} onClick={e=>{const stream=taskLog?.stream??'stdout';openResults('logs',e.currentTarget);void run(()=>readLogs(stream));}}>读取日志</button><button disabled={busy} onKeyDown={ignoreRepeat} onClick={e=>openTaskFiles(e.currentTarget)}>在查看器中打开</button><button disabled={busy} onClick={()=>void run(async()=>{await invoke('task.cancel',{task_id:task});})}>取消</button></div>}
      {actions.filter(a=>a.state==='review').map(a=><article className="review" key={a.id}><strong>等待执行复核</strong><p>{a.review_reason}</p><pre>{JSON.stringify(a.request.payload,null,2)}</pre>{[true,false].map(approved=><button key={String(approved)} disabled={busy} onClick={()=>void run(async()=>{await api(`actions/${a.id}/review`,'POST',{approved});})}>{approved?'批准执行':'拒绝'}</button>)}</article>)}
      <details className="setting" ref={environment} open={environmentOpen}><summary onClick={event=>{
        event.preventDefault();setEnvironmentDisclosure(environmentOpen?'closed':'open');
      }}>运行环境 · {nodeName||'未选择节点'}{selected&&` · ${workspace?workspaceName(workspace):'未选择项目'}`}</summary>
      <label>执行节点<select value={node} onChange={e=>selectNode(e.target.value)}><option value="">选择节点</option>{nodes.map(d=><option key={d.id} value={d.id}>{d.online?'●':'○'} {d.name}</option>)}</select></label>
      {selected&&<p className="muted">{selected.online?'在线':'离线'} · 最近更新 {selected.last_seen?new Date(selected.last_seen*1000).toLocaleString():'尚未连接'}{selected.snapshot.cpu_percent!==undefined&&<><br/>CPU {selected.snapshot.cpu_percent}% · 内存 {selected.snapshot.memory_percent}%</>}</p>}
      <label>项目<select value={workspace} onChange={e=>selectWorkspace(e.target.value)}><option value="">选择项目</option>{workspaces.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</select></label>
      <div className="inline"><input aria-label="项目名称" value={name} onChange={e=>setName(e.target.value)}/><button disabled={busy||!node} onClick={()=>void run(createWorkspace)}>新建</button></div>
      </details>
      <details className="setting" open={newTaskOpen}><summary onClick={event=>{
        event.preventDefault();setNewTaskDisclosure(newTaskOpen?'closed':'open');
      }}>新建任务{workspace?` · ${workspaceName(workspace)}`:' · 先选择项目'}</summary>
      <button type="button" className="primary wide" disabled={busy||!workspace} onClick={()=>void run(async()=>{const version=scopeVersion.current;const a=await invoke('task.submit',{template:'demo-field',spec:{workspace_id:workspace,name:'解析场验证',argv:['@python','-m','suan.control.demo_job'],outputs:['scalar-0.vti','scalar-1.vti','vector.vti']}});if(a.result&&scopeVersion.current===version)selectTask(a.result.id,workspace);})}>运行解析场示例</button>
      <p className="muted">自定义任务：输入 TaskSpec JSON。新命令将先进入执行复核。</p><form onSubmit={e=>{
        e.preventDefault();
        const form=new FormData(e.currentTarget);
        void run(async()=>{
          const spec=JSON.parse(String(form.get('spec')));
          if(spec?.workspace_id!==undefined&&spec.workspace_id!==workspace){
            throw new Error('TaskSpec 的工作区与当前项目不一致。请在「运行环境」选择目标项目，或修改 TaskSpec 中的 workspace_id。');
          }
          await invoke('task.submit',{spec:{...spec,workspace_id:workspace}});
        });
      }}><textarea name="spec" aria-label="TaskSpec" defaultValue={'{"argv":["python3","analysis.py"],"outputs":[]}'}/><button disabled={busy||!workspace}>提交复核</button></form>
      </details>
      <details><summary>最近操作与重试</summary>{actions.filter(a=>a.request.kind!=='task.events').slice(0,20).map(a=><p key={a.id}><small>{a.request.kind} · {a.state}<br/>{a.error}</small></p>)}<button onClick={()=>void run(async()=>{const saved=sessionStorage.getItem('stk-last-action');if(saved)await api('actions','POST',JSON.parse(saved));})}>以相同 ID 重试上次操作</button></details>
    </aside>
    <section className={`analysis surface${tab==='results'?'':' surface-hidden'}`} inert={tab!=='results'||overlay}><div className="view-title" onBlur={leaveSource}><div><h1>{analysis==='graph'?'图谱视图':shownScene?.manifest.field||'科学结果'}</h1>
      <div className="source-row"><p className="result-source" aria-label="结果来源" title={sourceIds}><span>{sourceTask}</span><span className="sr-only">，</span>
        <span className="source-file"><span>{sourceFile}</span>{sourceNext&&<span className="source-next" title={sourceNext}>{sourceNext}</span>}</span></p>
        <button type="button" ref={sourceToggle} className="source-toggle" aria-expanded={sourceOpen} aria-controls={sourceOpen?'result-source-details':undefined} onClick={()=>setSourceOpen(open=>!open)}>来源</button></div></div><span className="muted">拖动旋转 · 滚轮缩放 · 点击探针</span>
      {sourceOpen&&sourceDetails}</div>
      <div className="mode-switch" ref={modeChoice} role="tablist" aria-label="分析方式">{([['file','结果文件'],['graph','图谱']] as const).map(([key,label])=><button key={key} role="tab" aria-selected={analysis===key} className={analysis===key?'active':''} onClick={()=>{if(key!==analysis)dropPick();setAnalysis(key);}}>{label}</button>)}</div>
      {/* Both analysis modes stay mounted once shown; the inactive one keeps its size but takes no space, focus or pointer. */}
      {graphKept&&<div className={analysis==='graph'?'mode-pane graph-mode':'mode-pane graph-mode mode-hidden'} inert={analysis!=='graph'}><React.Suspense fallback={<div className="viewport empty">正在加载图谱模块…</div>}><GraphPanel key={graphKey} node={selected?node:''} scope={graphScope} task={taskBound?task:''} tasks={graphTasks} artifacts={taskBound?artifacts:[]} completedTask={completedTask} canReadArtifacts={canReadArtifacts} canReadEvents={canReadEvents&&taskOnline&&graphActive} active={graphActive} onError={setGraphError} beginReading={beginReading} onProbe={setGraphProbe} onSource={setGraphSource}/></React.Suspense></div>}
      <div className={analysis==='file'?'mode-pane file-mode':'mode-pane file-mode mode-hidden'} inert={analysis!=='file'}>
      <div className="view-controls"><label>结果 / 时间步<select aria-label="结果文件" ref={fileChoice} value={taskBound?path:''} onChange={e=>{
        const next=e.target.value;
        if(next!==path)levelEdited.current=false;
        fileEdited.current=true;dropPick();setPath(next);generation.current++;setViewError('');
      }}><option value="">选择数据文件</option>{(taskBound?artifacts:[]).filter(viewable).map(a=><option key={a.path} value={a.path}>{a.path}</option>)}</select></label>
      <label>视图<select value={mode} onChange={e=>{viewEdits.current++;setMode(e.target.value);}}><option value="slice">切片</option><option value="iso">等值面</option><option value="vectors">向量箭头</option></select></label>
      {mode==='slice'&&<><label>方向<select value={axis} onChange={e=>{viewEdits.current++;setAxis(Number(e.target.value));}}>{['X','Y','Z'].map((v,i)=><option key={v} value={i}>{v}</option>)}</select></label><label>索引<input type="number" min="0" value={index} onChange={e=>{viewEdits.current++;setIndex(Number(e.target.value));}}/></label></>}
      {mode==='iso'&&<label>等值<input type="number" value={level} onChange={e=>{viewEdits.current++;levelEdited.current=true;setLevel(Number(e.target.value));}}/></label>}
      <button disabled={busy||!taskBound||!path} onClick={loadView}>加载视图</button></div>
      <ErrorBoundary resetKey={shownScene}><React.Suspense fallback={<div className="viewport empty">正在加载三维模块…</div>}><Viewer scene={shownScene} onPick={setProbe}/></React.Suspense></ErrorBoundary>
      {shownScene&&<div className="legend"><span>{shownScene.manifest.value_range[0].toPrecision(5)}</span><i/><span>{shownScene.manifest.value_range[1].toPrecision(5)} {shownScene.manifest.units}</span><small>{shownScene.manifest.display_reduced?'显示网格已简化':'完整显示网格'} · 数值查询使用原始数据</small></div>}
      <div className="probe"><strong>物理坐标探针</strong>{probe.map((v,i)=><input aria-label={`探针${'XYZ'[i]}`} key={i} type="number" value={v} onChange={e=>setProbe(probe.map((n,j)=>i===j?Number(e.target.value):n))}/>)}<button disabled={busy||!shown} onClick={probeValue}>查询原始值</button></div></div>
      <details className={logRoom?'logs log-room':'logs'} ref={logPane} open><summary>日志 / 探针结果</summary>
        {streamSwitch&&<div className="log-streams"><div className="log-stream-choice" role="group" aria-label="日志流">{LOG_STREAMS.map(([key,label])=><button type="button" key={key}
          className={logShown?.stream===key?'active':''} aria-pressed={logShown?.stream===key} aria-disabled={busy}
          onKeyDown={ignoreRepeat} onClick={()=>{if(!busy)void run(()=>readLogs(key));}}>{label}</button>)}</div>
          {logMore&&<button type="button" className={logMore.ended?'log-more ended':'log-more'} aria-disabled={busy||logMore.ended}
            onKeyDown={ignoreRepeat} onClick={()=>{if(!busy&&!logMore.ended&&!continuing.current)void run(continueLog);}}>{logMore.ended?'已读完':'继续读取'}</button>}
          <small className="log-note" role="status">{logNote}</small></div>}
        <pre>{(selected&&(resultText||logText))||'选择任务读取日志，或在三维视图中选取一个位置。'}</pre></details>
    </section>
    <aside className={`chat surface${tab==='workbench'?'':' surface-hidden'}`} inert={tab!=='workbench'||overlay}>
      <h2 className="conversation-name" title={sessionLabel}>{sessionLabel}</h2>
      <div className="messages" ref={messageList} tabIndex={thread.messages.length || pending ? 0 : -1} role="log" aria-label="对话记录">
        {thread.status==='loading'&&!thread.messages.length&&<p className="muted">正在读取对话…</p>}
        {thread.status==='missing'&&<div className="chat-intro"><h3>这个对话已不存在</h3><p>控制服务中没有这个对话，未创建新会话。{conv.draft.trim()?'未发送的草稿仍在这里，可以移到新对话再发送。':'可以从「新对话」重新开始。'}</p>
          {!!conv.draft.trim()&&<button type="button" onClick={moveDraft}>移到新对话</button>}</div>}
        {thread.status==='error'&&<p className="muted">读取对话失败：{thread.error} <button type="button" className="quiet" onClick={conv.retry}>重新读取</button></p>}
        {thread.status==='ready'&&!thread.messages.length&&!pending&&<p className="chat-intro">从一个科学问题开始</p>}
        {thread.messages.map(m=><article key={m.id} className={m.role}><small>{m.role==='user'?'你':'STK'}</small><p>{m.content}</p></article>)}
        {pending&&<article className="user pending"><small>你 · 发送中</small><p>{pending.content}</p></article>}
      </div>
      {conv.failure&&<div className="send-failure" role="alert"><p>{conv.recorded?'消息已记录，回复尚未确认。':'发送未完成，草稿已保留。'}{conv.failure.error}</p>
        {!conv.recorded&&conv.failure.content!==conv.draft&&<p className="failed-text">未发送：{conv.failure.content}</p>}
        {conv.canResend&&conv.draft.trim()&&conv.failure.content!==conv.draft&&<p>请先重试上一条消息，当前草稿会保留。</p>}
        <button type="button" className="quiet" disabled={!conv.canResend} onClick={()=>void conv.resend()}>重新发送</button></div>}
      {conv.draftTooLong&&<p className="muted" role="status">单条消息最多 12,000 字符，请缩短后发送。</p>}
      <form className="chat-composer" onSubmit={e=>{e.preventDefault();void conv.send();}}>
        <label className="sr-only" htmlFor="chat-input">对话内容</label>
        <textarea id="chat-input" ref={composer} value={conv.draft} onChange={e=>conv.setDraft(e.target.value)} placeholder="描述计算任务…"/>
        <div className="chat-actions">
          <small className="muted">常规模板自动执行。新脚本和高资源任务需复核。</small>
          <button type="submit" className="primary" disabled={!conv.canSend}>发送</button>
        </div>
      </form>
    </aside>
    </div><footer>{openProgress?(openProgress.stage==='listing'?'列出结果文件…':'正在加载视图…'):busy||conv.sendingCount?'正在处理请求…':'就绪'}<span>STK · 计算持续运行，视图随处可达</span></footer>
  </div>;
}
createRoot(document.getElementById('root')!).render(ExampleView?<React.Suspense fallback={null}><ExampleView/></React.Suspense>:<App/>);
if('serviceWorker' in navigator)void navigator.serviceWorker.register('/sw.js');
