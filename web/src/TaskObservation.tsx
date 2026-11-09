import {useEffect, useState} from 'react';
import {ApiError, readNode} from './api';
import {acceptsTaskFact, isTerminalTaskState, taskFact, type TaskFact, type TaskScope} from './taskFacts';

type Phase = 'checking' | 'verified' | 'unsupported' | 'unavailable' | 'unconfirmed';
type Observation = {fact: TaskFact | null; phase: Phase};
const labels: Record<Phase, string> = {
  checking: '正在读取 Runtime 状态',
  verified: '已读取 Runtime 状态',
  unsupported: '节点或控制服务不支持精确读取',
  unavailable: '暂时无法读取 Runtime 状态',
  unconfirmed: 'Runtime 状态未确认',
};

export default function TaskObservation({scope, heartbeat, online, supported, refresh,
                                         onVerified, onAccessLost, onNodeGone}: {
  scope: TaskScope;
  heartbeat: unknown;
  online: boolean;
  supported: boolean | null;
  refresh: number;
  onVerified: (scope: TaskScope, terminal?: boolean) => void;
  onAccessLost: () => void;
  onNodeGone: (scope: TaskScope) => void;
}) {
  const {node, workspace, task} = scope;
  const [observation, setObservation] = useState<Observation>(() => ({fact: taskFact(heartbeat, scope, false), phase: 'checking'}));

  useEffect(() => {
    const next = taskFact(heartbeat, {node, workspace, task}, false);
    if (next) setObservation(current => acceptsTaskFact(next, current.fact) ? {...current, fact: next} : current);
  }, [heartbeat, node, workspace, task]);

  useEffect(() => {
    if (!online || supported !== true) return;
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function read() {
      setObservation(current => ({...current, phase: 'checking'}));
      try {
        const result = await readNode(node, 'task.get', {task_id: task}, abort.signal);
        if (abort.signal.aborted) return;
        const next = taskFact(result, {node, workspace, task}, true);
        if (next) onVerified(scope);
        setObservation(current => next && acceptsTaskFact(next, current.fact) ?
          {fact: next, phase: 'verified'} : {...current, phase: 'unconfirmed'});
      } catch (error) {
        if (abort.signal.aborted) return;
        if (error instanceof ApiError) {
          if (error.status === 401 || error.status === 403) { onAccessLost(); return; }
          if (error.status === 404) { onNodeGone(scope); return; }
        }
        const phase = !(error instanceof ApiError) || error.status === 503 || error.status === 504 || error.status === 429 ?
          'unavailable' : error.status === 501 ? 'unsupported' : 'unconfirmed';
        setObservation(current => ({...current, phase}));
      }
      if (!abort.signal.aborted) timer = setTimeout(() => void read(), 5000);
    }
    void read();
    return () => { abort.abort(); clearTimeout(timer); };
  }, [scope, node, workspace, task, online, supported, refresh, onVerified, onAccessLost, onNodeGone]);

  const phase = !online ? 'unavailable' : supported === false ? 'unsupported' :
    supported === null ? 'checking' : observation.phase;
  const current = observation.fact;
  const exactTerminal = current?.exact === true && isTerminalTaskState(current.state);
  useEffect(() => {
    if (exactTerminal) onVerified(scope, true);
  }, [exactTerminal, onVerified, scope]);

  return <section className="task-observation" aria-label="所选任务状态">
    <strong>{current?.name || task.slice(0, 8)}</strong>
    <p className="muted" role="status">
      {current && <>{current.exact ? '最近 Runtime 状态' : '最近节点快照'} · <span className={`state ${current.state}`}>{current.state}</span><br/></>}
      {labels[phase === 'verified' && current && !current.exact ? 'checking' : phase]}
      {current?.cancelRequested && current.state !== 'cancelled' && <><br/>Runtime 已记录取消请求</>}
      {current?.reason && <><br/>{current.reason}</>}
    </p>
  </section>;
}
