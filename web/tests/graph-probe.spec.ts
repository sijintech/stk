import {expect, test} from '@playwright/test';
import {resolveProbeArtifact, resolveProbeTarget, type GraphDocument} from '../src/graph';

const graph = (step: unknown, caseDir?: string): GraphDocument => ({nodes: [
  {id: 'run', type: 'stk.source.muferro_run@1', params: {binding: 'run', case_dir: caseDir}},
  {id: 'polar', type: 'stk.source.muferro_frame@1', inputs: {frames: {from: 'run.frames'}}, params: {step}},
]});
const params = {bindings: {run: 'task-b'}, values: {step: 3}, result: {parameters: {'polar.step': {value: 2}}}};
const artifacts = [{path: 'Polar.00000002.dat'}, {path: 'case/Polar.00000002.dat'}];

test('MuFerro probe uses the resolved literal step and published explicit case path', () => {
  const target = resolveProbeTarget(graph(3, './case/'), {node: 'polar'}, params);
  expect(target).toMatchObject({task_id: 'task-b', frame: 'Polar.00000002.dat', caseDir: './case/'});
  if (!('frame' in target)) throw new Error('expected DAT frame');
  expect(resolveProbeArtifact(target, artifacts)).toBe(artifacts[1].path);
  expect(() => resolveProbeArtifact(target, [artifacts[0]])).toThrow('未发布');
});

test('MuFerro probe requires a unique published auto-case path and authoritative step', () => {
  const g = graph({$param: 'step'});
  const target = resolveProbeTarget(g, {node: 'polar'}, {...params, result: {parameters: {step: {value: 2}}}});
  if (!('frame' in target)) throw new Error('expected DAT frame');
  expect(resolveProbeArtifact(target, [artifacts[1]])).toBe(artifacts[1].path);
  expect(() => resolveProbeArtifact(target, artifacts)).toThrow('多个同名');
  expect(() => resolveProbeArtifact(target, [...artifacts].reverse())).toThrow('多个同名');
  expect(() => resolveProbeArtifact(target, [])).toThrow('未发布');
  expect(resolveProbeTarget(g, {node: 'polar'}, {...params, result: undefined})).toHaveProperty('error');
});

test('MuFerro probe rejects mixed-source time when the graph reports only a shared step', () => {
  const g = graph({$param: 'step'});
  g.nodes!.push(
    {id: 'run_b', type: 'stk.source.muferro_run@1', params: {binding: 'other'}},
    {id: 'polar_b', type: 'stk.source.muferro_frame@1', inputs: {frames: {from: 'run_b.frames'}}, params: {step: {$param: 'step'}}},
    {id: 'mixed', type: 'stk.view.scene@1', inputs: {layers: [{from: 'polar.out'}, {from: 'polar_b.out'}]}},
  );
  const shared = {...params, bindings: {...params.bindings, other: 'task-c'}, result: {parameters: {step: {value: 4}}}};
  expect(resolveProbeTarget(g, {node: 'polar'}, shared)).toMatchObject({error: expect.stringContaining('实际使用')});
  expect(resolveProbeTarget(g, {node: 'polar'}, params)).toMatchObject({task_id: 'task-b', frame: 'Polar.00000002.dat'});
  expect(resolveProbeTarget(g, {node: 'mixed'}, shared)).toMatchObject({error: expect.stringContaining('唯一')});
});
