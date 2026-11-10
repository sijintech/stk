import {expect, test} from '@playwright/test';
import {muProArtifact, muProFrames, muProManifest, muProRequest} from '../src/muproHdf5';

const artifact = {path: 'case/run.h5' as const, sha256: 'd'.repeat(64), size: 8192};
const frame = {selector: '/t00000002/Polar', step: 2, name: 'Polar', shape: [4, 3, 2, 3] as [number, number, number, number], dtype: 'float32'};
const result = () => ({schema: 'stk.graph-result/1', profile: 'web',
  outputs: {fields: {type: 'value', value: {...artifact, reader: 'mupro.hdf5@1', fields: [frame]}}}});

test('MuPRO publication requires the exact pilot path and unambiguous bounded identity', () => {
  expect(muProArtifact([artifact])).toEqual(artifact);
  for (const candidate of [
    {...artifact, path: 'other.h5'}, {...artifact, sha256: ''}, {...artifact, sha256: 'D'.repeat(64)},
    {...artifact, size: 0}, {...artifact, size: 1024 ** 3 + 1},
  ]) expect(muProArtifact([candidate])).toBeNull();
  expect(muProArtifact([artifact, artifact])).toBeNull();
});

test('MuPRO fields keep explicit selector, shape and dtype and refuse another publication', () => {
  expect(muProFrames(result(), artifact)).toEqual([frame]);
  expect(() => muProFrames(result(), {...artifact, sha256: 'e'.repeat(64)})).toThrow('发布文件');
  for (const value of [
    {...frame, selector: '/t00000004/Polar'}, {...frame, selector: '/t00000002/Other'},
    {...frame, step: -1}, {...frame, dtype: 'bool'}, {...frame, shape: [4, 3, 2]},
    {...frame, shape: [4, 3, 2, 0]}, null,
  ]) {
    const invalid = result();
    invalid.outputs.fields.value.fields = [value as typeof frame];
    expect(() => muProFrames(invalid, artifact)).toThrow('无效');
  }
  const duplicate = result();
  duplicate.outputs.fields.value.fields.push(frame);
  expect(() => muProFrames(duplicate, artifact)).toThrow('无效');
});

test('MuPRO requests use pinned published nodes and an explicit scalar or component', () => {
  expect(() => muProRequest('task', artifact, {frame, component: null})).toThrow('明确选择');
  expect(() => muProRequest('task', artifact, {frame, component: 3})).toThrow('有效分量');
  expect(muProRequest('task', artifact)).toMatchObject({profile: 'web', outputs: ['fields'], budget: {max_output_bytes: 256 * 1024},
    graph: {nodes: [{type: 'stk.source.mupro_hdf5_fields@1', params: {expected_sha256: artifact.sha256}}]}});
  const selected = muProRequest('task', artifact, {frame, component: 1});
  expect(selected).toMatchObject({outputs: ['view'], graph: {nodes: [
    {type: 'stk.source.mupro_hdf5@1', params: {selector: frame.selector, expected_sha256: artifact.sha256}},
    {type: 'stk.render.volume@1', params: {field: {name: 'Polar', component: 1}, encoding: 'f32'}},
    {type: 'stk.view.scene@1'},
  ]}});
  const scalar = {...frame, name: 'Scalar', selector: '/t00000002/Scalar', shape: [4, 3, 2, 1] as typeof frame.shape};
  expect(muProRequest('task', artifact, {frame: scalar, component: null}).graph.nodes[1].params)
    .toEqual({field: {name: 'Scalar', component: null}, encoding: 'f32'});
});

test('MuPRO frame provenance refuses a different step and invented physical time or units', () => {
  const manifest = {length_unit: 'grid_index', source: {time: {step: 2, time: null}}};
  const response = {schema: 'stk.graph-result/1', profile: 'web', outputs: {view: {type: 'payload', manifest}}};
  expect(muProManifest(response, frame)).toBe(manifest);
  for (const bad of [
    {...manifest, length_unit: 'm'}, {...manifest, source: {time: {step: 4, time: null}}},
    {...manifest, source: {time: {step: 2, time: 1}}},
  ]) expect(() => muProManifest({...response, outputs: {view: {type: 'payload', manifest: bad}}}, frame)).toThrow('所选帧');
});
