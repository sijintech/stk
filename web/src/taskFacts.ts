export type TaskScope = {node: string; workspace: string; task: string};
export type TaskFact = {name: string; state: string; updated: string; cancelRequested: boolean; reason: string; exact: boolean};

const terminal = new Set(['succeeded', 'failed', 'cancelled']);
// Chinese labels match the desktop jobs.state catalog for the published Runtime states.
const stateLabels: Record<string, string> = {
  preparing: '准备中',
  queued: '排队中',
  submitting: '提交中',
  running: '运行中',
  succeeded: '成功',
  failed: '失败',
  cancelled: '已取消',
  unknown: '待核实',
};
const states = new Set(Object.keys(stateLabels));

export const isTerminalTaskState = (state: string) => terminal.has(state);

export function taskStateLabel(state: unknown, cancelRequested = false): string {
  if (typeof state !== 'string') return '';
  if (!states.has(state)) return state;
  return cancelRequested && !isTerminalTaskState(state) ? '正在取消' : stateLabels[state];
}

export function taskFact(value: unknown, scope: TaskScope, exact: boolean): TaskFact | null {
  if (!value || typeof value !== 'object') return null;
  const row = value as Record<string, unknown>;
  if (row.id !== scope.task || row.workspace_id !== scope.workspace ||
      typeof row.state !== 'string' || !states.has(row.state) ||
      typeof row.updated_at !== 'string' || !row.updated_at) return null;
  return {name: typeof row.name === 'string' ? row.name : '', state: row.state, updated: row.updated_at,
          cancelRequested: row.cancel_requested === true,
          reason: typeof row.reason === 'string' ? row.reason.slice(0, 240) : '', exact};
}

export function acceptsTaskFact(next: TaskFact, known: TaskFact | null) {
  if (!known) return true;
  // Runtime terminal states and cancellation requests do not roll back.
  if (terminal.has(next.state) !== terminal.has(known.state)) return terminal.has(next.state);
  if (terminal.has(known.state) && next.state !== known.state) return false;
  if (!terminal.has(known.state) && next.cancelRequested !== known.cancelRequested) return next.cancelRequested;
  return next.updated > known.updated || (next.updated === known.updated && (next.exact || !known.exact));
}
