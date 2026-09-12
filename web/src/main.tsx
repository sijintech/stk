import React,{useCallback,useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {action,api,events,hasToken,Json,setToken,uid} from './api';
import './style.css';
const Viewer=React.lazy(()=>import('./Viewer'));

function App(){
  const [connected,setConnected]=useState(hasToken()),[pairCode,setPairCode]=useState(''),[token,setCredential]=useState('');
  const [devices,setDevices]=useState<Json[]>([]),[actions,setActions]=useState<Json[]>([]),[node,setNode]=useState(''),[workspace,setWorkspace]=useState('');
  const [task,setTask]=useState(''),[artifacts,setArtifacts]=useState<Json[]>([]),[path,setPath]=useState(''),[scene,setScene]=useState<Json|null>(null);
  const [mode,setMode]=useState('slice'),[axis,setAxis]=useState(2),[index,setIndex]=useState(0),[level,setLevel]=useState(0),[probe,setProbe]=useState<number[]>([0,0,0]);
  const [session,setSession]=useState(()=>sessionStorage.getItem('stk-session')||uid()),[sessions,setSessions]=useState<Json[]>([]),[messages,setMessages]=useState<Json[]>([]),[chat,setChat]=useState('');
  const [name,setName]=useState('科学项目'),[logs,setLogs]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[tab,setTab]=useState('tasks'),[online,setOnline]=useState(navigator.onLine);
  const generation=useRef(0),refreshing=useRef(false);
  const selected=devices.find(d=>d.id===node),tasks:Json[]=selected?.snapshot?.tasks||[];
  const refresh=useCallback(async()=>{
    if(refreshing.current)return;refreshing.current=true;
    try{const [d,a,s]=await Promise.all([api('devices'),api('actions'),api('sessions')]);setDevices(d);setActions(a);setSessions(s);setOnline(true);}
    catch(e){setOnline(false);setError(String(e));}finally{refreshing.current=false;}
  },[]);
  useEffect(()=>{if(!connected)return;void refresh();const abort=new AbortController();void events(()=>void refresh(),abort.signal);const timer=setInterval(()=>void refresh(),5000);return()=>{abort.abort();clearInterval(timer);};},[connected,refresh]);
  useEffect(()=>{if(!connected)return;sessionStorage.setItem('stk-session',session);void api(`sessions/${session}`).then(s=>setMessages(s.messages)).catch(e=>setError(String(e)));},[session,connected]);
  async function run(fn:()=>Promise<void>){setBusy(true);setError('');try{await fn();await refresh();}catch(e){setError(String(e));}finally{setBusy(false);}}
  const invoke=(kind:string,payload:Json)=>action(node,kind,payload,()=>setError('操作等待复核，请在任务面板查看完整参数。'));
  async function files(taskId:string){const item=await invoke('task.artifacts',{task_id:taskId});if(item.result)setArtifacts(item.result);}
  function selectTask(id:string){generation.current++;setTask(id);setPath('');setArtifacts([]);setScene(null);void run(()=>files(id));}
  async function loadView(){const current=++generation.current;const options:Json={mode,axis};if(mode==='slice')options.index=index;if(mode==='iso')options.level=level;if(mode==='vectors')options.component='magnitude';
    const item=await invoke('view.build',{task_id:task,path,options});if(item.result&&generation.current===current){setScene(item.result);setLevel((item.result.manifest.value_range[0]+item.result.manifest.value_range[1])/2);setTab('view');}}
  async function readLogs(){const item=await invoke('task.logs',{task_id:task});if(item.result){const bytes=Uint8Array.from(atob(item.result.data),c=>c.charCodeAt(0));setLogs(new TextDecoder().decode(bytes));}}
  if(!connected)return <main className="login"><div className="wordmark">STK <span>科学工作台</span></div><h1>从任意设备<br/>连接你的计算。</h1><p>任务在服务器持续运行。这里用来发起、观察与探索。</p><form onSubmit={e=>{e.preventDefault();void run(async()=>{const result=await api('pairings/claim','POST',{code:pairCode,name:'STK 网页客户端'});if(result.role!=='client')throw new Error('请使用客户端配对码');setToken(result.token);setPairCode('');setConnected(true);});}}><label>一次性配对码<input value={pairCode} onChange={e=>setPairCode(e.target.value)} autoComplete="off" required/></label><button disabled={busy}>连接工作台 →</button></form><details><summary>使用已有设备凭据</summary><input aria-label="设备凭据" type="password" value={token} onChange={e=>setCredential(e.target.value)}/><button onClick={()=>void run(async()=>{setToken(token);await api('devices');setConnected(true);})}>连接</button></details>{error&&<p role="alert">{error}</p>}</main>;
  return <div className="app"><header><div className="wordmark">STK <span>科学工作台</span></div><span className={online?'connection':'connection offline'}>{online?'控制服务已连接':'连接中断 · 显示最近状态'}</span><button className="quiet" onClick={()=>{setToken('');setConnected(false);sessionStorage.removeItem('stk-event-cursor');}}>断开</button></header>
    <nav className="mobile-nav">{[['tasks','任务'],['chat','对话'],['view','三维']].map(([key,label])=><button className={tab===key?'active':''} key={key} onClick={()=>setTab(key)}>{label}</button>)}</nav>
    {error&&<div className="notice" role="alert">{error}<button onClick={()=>setError('')}>关闭</button></div>}
    <div className="workspace">
    <aside className={`tasks panel mobile-${tab==='tasks'?'show':'hide'}`}><div className="section-title"><h2>项目与任务</h2><button className="quiet" onClick={()=>void refresh()}>刷新</button></div>
      <label>执行节点<select value={node} onChange={e=>{generation.current++;setNode(e.target.value);setWorkspace('');setTask('');setScene(null);setArtifacts([]);}}><option value="">选择节点</option>{devices.filter(d=>d.role==='node'&&!d.revoked).map(d=><option key={d.id} value={d.id}>{d.online?'●':'○'} {d.name}</option>)}</select></label>
      {selected&&<p className="muted">{selected.online?'在线':'离线'} · 最近更新 {selected.last_seen?new Date(selected.last_seen*1000).toLocaleString():'尚未连接'}{selected.snapshot.cpu_percent!==undefined&&<><br/>CPU {selected.snapshot.cpu_percent}% · 内存 {selected.snapshot.memory_percent}%</>}</p>}
      <label>项目<select value={workspace} onChange={e=>setWorkspace(e.target.value)}><option value="">选择项目</option>{(selected?.snapshot?.workspaces||[]).map((w:Json)=><option key={w.id} value={w.id}>{w.name}</option>)}</select></label>
      <div className="inline"><input aria-label="项目名称" value={name} onChange={e=>setName(e.target.value)}/><button disabled={busy||!node} onClick={()=>void run(async()=>{const a=await invoke('workspace.create',{name});if(a.result)setWorkspace(a.result.id);})}>新建</button></div>
      <button className="primary wide" disabled={busy||!workspace} onClick={()=>void run(async()=>{const a=await invoke('task.submit',{template:'demo-field',spec:{workspace_id:workspace,name:'解析场验证',argv:['@python','-m','suan.control.demo_job'],outputs:['scalar-0.vti','scalar-1.vti','vector.vti']}});if(a.result)setTask(a.result.id);})}>运行解析场示例</button>
      <details><summary>自定义任务</summary><p className="muted">输入 TaskSpec JSON。新命令将先进入执行复核。</p><form onSubmit={e=>{e.preventDefault();const form=new FormData(e.currentTarget);void run(async()=>{const spec=JSON.parse(String(form.get('spec')));await invoke('task.submit',{spec:{workspace_id:workspace,...spec}});});}}><textarea name="spec" aria-label="TaskSpec" defaultValue={'{"argv":["python3","analysis.py"],"outputs":[]}'}/><button disabled={busy||!workspace}>提交复核</button></form></details>
      <div className="task-list">{tasks.filter(t=>!workspace||t.workspace_id===workspace).map(t=><button className={`task ${task===t.id?'selected':''}`} key={t.id} onClick={()=>selectTask(t.id)}><span>{t.name||t.id.slice(0,8)}</span><small className={`state ${t.state}`}>{t.state}</small></button>)}{!tasks.length&&<p className="muted">该节点尚无任务。</p>}</div>
      {task&&<div className="inline"><button disabled={busy} onClick={()=>void run(readLogs)}>读取日志</button><button disabled={busy} onClick={()=>void run(()=>files(task))}>结果</button><button disabled={busy} onClick={()=>void run(async()=>{await invoke('task.cancel',{task_id:task});})}>取消</button></div>}
      {actions.filter(a=>a.state==='review').map(a=><article className="review" key={a.id}><strong>等待执行复核</strong><p>{a.review_reason}</p><pre>{JSON.stringify(a.request.payload,null,2)}</pre>{[true,false].map(approved=><button key={String(approved)} disabled={busy} onClick={()=>void run(async()=>{await api(`actions/${a.id}/review`,'POST',{approved});})}>{approved?'批准执行':'拒绝'}</button>)}</article>)}
      <details><summary>最近操作与重试</summary>{actions.slice(0,20).map(a=><p key={a.id}><small>{a.request.kind} · {a.state}<br/>{a.error}</small></p>)}<button onClick={()=>void run(async()=>{const saved=sessionStorage.getItem('stk-last-action');if(saved)await api('actions','POST',JSON.parse(saved));})}>以相同 ID 重试上次操作</button></details>
    </aside>
    <section className={`analysis mobile-${tab==='view'?'show':'hide'}`}><div className="view-title"><div><span className="eyebrow">RESULT EXPLORER</span><h1>{scene?.manifest.field||'科学结果'}</h1></div><span className="muted">拖动旋转 · 滚轮缩放 · 点击探针</span></div>
      <div className="view-controls"><label>结果 / 时间步<select aria-label="结果文件" value={path} onChange={e=>{setPath(e.target.value);generation.current++;}}><option value="">选择数据文件</option>{artifacts.filter(a=>/\.(vti|vtk|npy|dat)$/.test(a.path)).map(a=><option key={a.path} value={a.path}>{a.path}</option>)}</select></label>
      <label>视图<select value={mode} onChange={e=>setMode(e.target.value)}><option value="slice">切片</option><option value="iso">等值面</option><option value="vectors">向量箭头</option></select></label>
      {mode==='slice'&&<><label>方向<select value={axis} onChange={e=>setAxis(Number(e.target.value))}>{['X','Y','Z'].map((v,i)=><option key={v} value={i}>{v}</option>)}</select></label><label>索引<input type="number" min="0" value={index} onChange={e=>setIndex(Number(e.target.value))}/></label></>}
      {mode==='iso'&&<label>等值<input type="number" value={level} onChange={e=>setLevel(Number(e.target.value))}/></label>}
      <button disabled={busy||!path} onClick={()=>void run(loadView)}>加载视图</button></div>
      <React.Suspense fallback={<div className="viewport empty">正在加载三维模块…</div>}><Viewer scene={scene} onPick={setProbe}/></React.Suspense>
      {scene&&<div className="legend"><span>{scene.manifest.value_range[0].toPrecision(5)}</span><i/><span>{scene.manifest.value_range[1].toPrecision(5)} {scene.manifest.units}</span><small>{scene.manifest.display_reduced?'显示网格已简化':'完整显示网格'} · 数值查询使用原始数据</small></div>}
      <div className="probe"><strong>物理坐标探针</strong>{probe.map((v,i)=><input aria-label={`探针${'XYZ'[i]}`} key={i} type="number" value={v} onChange={e=>setProbe(probe.map((n,j)=>i===j?Number(e.target.value):n))}/>)}<button disabled={busy||!scene} onClick={()=>void run(async()=>{const a=await invoke('view.probe',{task_id:task,path,position:probe});setLogs(JSON.stringify(a.result,null,2));})}>查询原始值</button></div>
      <details className="logs" open><summary>日志 / 探针结果</summary><pre>{logs||'选择任务读取日志，或在三维视图中选取一个位置。'}</pre></details>
    </section>
    <aside className={`chat panel mobile-${tab==='chat'?'show':'hide'}`}><div className="section-title"><h2>AI 对话</h2><button className="quiet" onClick={()=>{setSession(uid());setMessages([]);}}>新会话</button></div><select aria-label="恢复会话" value={session} onChange={e=>setSession(e.target.value)}><option value={session}>当前会话</option>{sessions.filter(s=>s.id!==session).map(s=><option key={s.id} value={s.id}>{s.name} · {s.id.slice(0,6)}</option>)}</select>
      <div className="messages">{!messages.length&&<div className="chat-intro"><h3>从一个科学问题开始</h3><p>描述你要执行的任务。命令、资源与执行状态会在任务面板中明确展示。</p></div>}{messages.map(m=><article key={m.id} className={m.role}><small>{m.role==='user'?'你':'STK'}</small><p>{m.content}</p></article>)}</div>
      <form onSubmit={e=>{e.preventDefault();const content=chat;setChat('');void run(async()=>{const result=await api(`sessions/${session}/messages`,'POST',{id:uid(),content});setMessages(result.messages);});}}><label className="sr-only" htmlFor="chat-input">对话内容</label><textarea id="chat-input" value={chat} onChange={e=>setChat(e.target.value)} placeholder="描述计算任务…"/><button className="primary wide" disabled={busy||!chat.trim()}>发送</button></form><small className="muted">常规模板自动执行；新脚本及高资源任务需复核。</small></aside>
    </div><footer>{busy?'正在处理请求…':'就绪'}<span>STK · 计算持续运行，视图随处可达</span></footer>
  </div>;
}
createRoot(document.getElementById('root')!).render(<App/>);
if('serviceWorker' in navigator)void navigator.serviceWorker.register('/sw.js');
