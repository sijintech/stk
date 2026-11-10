import {expect, test} from '@playwright/test';
import {acceptsTaskFact, taskFact, taskStateLabel} from '../src/taskFacts';

const scope = {node: 'a'.repeat(32), workspace: 'b'.repeat(32), task: 'c'.repeat(32)};
const running = {id: scope.task, workspace_id: scope.workspace, state: 'running', name: 'simulation',
                 updated_at: '2026-11-09T15:30:00.000000Z', cancel_requested: false};

test('a live result is bound to the requested task and workspace', () => {
  expect(taskFact(running, scope, true)?.state).toBe('running');
  expect(taskFact({...running, id: 'd'.repeat(32)}, scope, true)).toBeNull();
  expect(taskFact({...running, workspace_id: 'e'.repeat(32)}, scope, true)).toBeNull();
  expect(taskFact({...running, state: 'invalid'}, scope, true)).toBeNull();
  expect(taskFact({...running, updated_at: null}, scope, true)).toBeNull();
});

test('an exact fact at the heartbeat timestamp retains its provenance', () => {
  const heartbeat = taskFact(running, scope, false)!;
  const exact = taskFact(running, scope, true)!;
  expect(acceptsTaskFact(exact, heartbeat)).toBe(true);
  expect(acceptsTaskFact(heartbeat, exact)).toBe(false);
  const newer = taskFact({...running, updated_at: '2026-11-09T15:31:00.000000Z'}, scope, false)!;
  expect(acceptsTaskFact(newer, exact)).toBe(true);
  expect(acceptsTaskFact(exact, newer)).toBe(false);
});

test('a later observation cannot erase terminal state or a pending cancellation', () => {
  const newer = {...running, updated_at: '2026-11-09T15:31:00.000000Z'};
  const succeeded = taskFact({...running, state: 'succeeded'}, scope, true)!;
  const cancelling = taskFact({...running, cancel_requested: true}, scope, true)!;
  expect(acceptsTaskFact(taskFact(newer, scope, true)!, succeeded)).toBe(false);
  expect(acceptsTaskFact(taskFact({...newer, state: 'failed'}, scope, true)!, succeeded)).toBe(false);
  expect(acceptsTaskFact(taskFact(newer, scope, true)!, cancelling)).toBe(false);
  expect(acceptsTaskFact(taskFact({...newer, state: 'cancelled'}, scope, true)!, cancelling)).toBe(true);
});

test('task display distinguishes cancellation, an unresolved state and unfamiliar Runtime states', () => {
  expect(taskStateLabel('unknown')).toBe('待核实');
  expect(taskStateLabel('unknown', true)).toBe('正在取消');
  expect(taskStateLabel('cancelled', true)).toBe('已取消');
  expect(taskStateLabel('succeeded', true)).toBe('成功');
  expect(taskStateLabel('constructor', true)).toBe('constructor');
  expect(taskStateLabel(null)).toBe('');
});
