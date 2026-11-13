import {useEffect,useRef,useState} from 'react';
import {api,ApiError,type Json} from './api';

const states:Record<string,string>={
  review:'等待复核',queued:'等待执行节点',succeeded:'已提交',failed:'提交失败',rejected:'复核未通过',
};
type TaskReference={
  message_id:string;action_id:string;node_id:string;workspace_id:string;state:string;task_id:string|null;
};
type TaskList={tasks:TaskReference[];more:boolean};
const id=(value:unknown):value is string=>typeof value==='string'&&/^[a-f0-9]{32}$/.test(value);
function taskList(value:Json,session:string):TaskList {
  if(value?.id!==session||!Array.isArray(value.tasks)||value.tasks.length>100||typeof value.more!=='boolean'||
    value.tasks.some(task=>!id(task?.message_id)||!id(task.action_id)||!id(task.node_id)||!id(task.workspace_id)||
      !Object.hasOwn(states,task.state)||(task.task_id!==null&&(!id(task.task_id)||task.state!=='succeeded')))){
    throw new Error('控制服务返回了无效的任务引用。');
  }
  return value as TaskList;
}

export function ConversationTasks({session,onClose,onAccessLost}:{
  session:string;onClose:()=>void;onAccessLost:()=>void;
}){
  const dialog=useRef<HTMLDialogElement>(null);
  const [list,setList]=useState<TaskList|null>(null),[error,setError]=useState('');
  useEffect(()=>{
    const element=dialog.current!;
    element.showModal();
    return ()=>{element.close();};
  },[]);
  useEffect(()=>{
    const request=new AbortController();
    void api(`sessions/${session}/tasks`,'GET',undefined,request.signal).then(value=>{
      if(!request.signal.aborted)setList(taskList(value,session));
    }).catch((error:unknown)=>{
      if(request.signal.aborted)return;
      if(error instanceof ApiError&&(error.status===401||error.status===403)){onAccessLost();return;}
      setError(error instanceof ApiError&&error.status===404?'当前控制服务未提供此对话的任务列表。':String(error));
    });
    return ()=>request.abort();
  },[session,onAccessLost]);
  return <dialog className="conversation-tasks" ref={dialog} aria-labelledby="conversation-tasks-title"
    onCancel={event=>{event.preventDefault();onClose();}}>
    <div className="conversation-tasks-head">
      <h2 id="conversation-tasks-title">关联任务</h2>
      <button type="button" className="quiet" autoFocus onClick={onClose}>关闭</button>
    </div>
    {error?<p role="alert">{error}</p>:!list?<p role="status">正在读取关联任务…</p>:
      !list.tasks.length?<p className="muted">此对话暂无关联任务。</p>:
      <ul>{list.tasks.map(task=><li key={task.action_id}>
        <strong>{task.state==='succeeded'&&!task.task_id?'已收到回执，任务 ID 未确认':states[task.state]}</strong>
        <span>操作 {task.action_id}</span>
        {task.task_id&&<span>任务 {task.task_id}</span>}
      </li>)}</ul>}
    {list?.more&&<p className="muted">显示最近 100 条关联任务。</p>}
  </dialog>;
}
