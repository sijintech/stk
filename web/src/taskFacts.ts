export type TaskScope = {node: string; workspace: string; task: string};
export type TaskFact = {name: string; state: string; updated: string; cancelRequested: boolean; reason: string; exact: boolean};

const terminal = new Set(['succeeded', 'failed', 'cancelled']);
const states = new Set(['preparing', 'queued', 'submitting', 'running', 'unknown', ...terminal]);

export const isTerminalTaskState = (state: string) => terminal.has(state);

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
