import {expect, test} from '@playwright/test';
import {muProArtifact, muProFrames, muProManifest, muProRequest, muProVoxelBlob, muProVoxelRequest, muProVoxelValue,
  type GridPoint} from '../src/muproHdf5';
import {scalarNpy} from './mupro-npy-fixture';

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

const accepted = {artifact, frame, component: 1};
const point: GridPoint = [2, 1, 0];

test('MuPRO voxel graph binds one original point to the shown selector, SHA and exact component', () => {
  const request = muProVoxelRequest('task', accepted, point);
  expect(request).toMatchObject({bindings: {run: {task_id: 'task'}}, profile: 'web',
    budget: {max_output_bytes: 256 * 1024}, outputs: ['source', 'voxel'], graph: {
      nodes: [
        {type: 'stk.source.mupro_hdf5@1', params: {binding: 'run', path: artifact.path, expected_sha256: artifact.sha256,
          selector: frame.selector, extent: [2, 2, 1, 1, 0, 0]}},
        {type: 'stk.filter.calculator@1', params: {operation: 'component', component: 1, result: 'value', keep_input: false}},
        {type: 'stk.output.dataset@1', params: {format: 'npy'}, inputs: {in: {from: 'component.out'}}},
      ], outputs: {source: 'field.out', voxel: 'voxel.file'},
    }});
  const scalar = {...accepted, component: null, frame: {...frame, shape: [4, 3, 2, 1] as typeof frame.shape}};
  expect(muProVoxelRequest('task', scalar, point).graph.nodes.map(n => n.id)).toEqual(['field', 'voxel']);
  for (const invalid of [[-1, 0, 0], [4, 0, 0], [0, 1.5, 0], [0, 0, Infinity]]) {
    expect(() => muProVoxelRequest('task', accepted, invalid as GridPoint)).toThrow('整数网格索引');
  }
});

test('MuPRO voxel result checks point geometry and full published source before requesting bytes', () => {
  const descriptor = {schema: 'stk.dataset/1', id: frame.name, kind: 'image',
    geometry: {length_unit: 'grid_index', origin: point, spacing: [1, 1, 1], dimensions: [1, 1, 1]},
    time: {step: frame.step}, fields: [{name: frame.name, dtype: frame.dtype, association: 'point', components: frame.shape[3]}],
    frames: [{step: frame.step, sources: {[frame.name]: {...artifact, selector: frame.selector, reader: 'mupro.hdf5@1'}}}]};
  const voxel = {type: 'file', name: 'voxel.npy', media_type: 'application/x-npy', blob: 'a'.repeat(64), size: 132};
  const make = (source = descriptor, file = voxel) => ({schema: 'stk.graph-result/1', profile: 'web',
    outputs: {source: {type: 'dataset', descriptor: source}, voxel: file}});
  expect(muProVoxelBlob(make(), accepted, point)).toEqual({sha: voxel.blob, size: 132});
  expect(() => muProVoxelBlob(make(), accepted, [1, 2, 0])).toThrow('坐标');
  expect(() => muProVoxelBlob(make(), {...accepted, artifact: {...artifact, sha256: 'e'.repeat(64)}}, point)).toThrow('来源');
  expect(() => muProVoxelBlob(make(), {...accepted, frame: {...frame, dtype: 'float64'}}, point)).toThrow('类型');
  for (const invalid of [{...voxel, size: 4097}, {...voxel, media_type: 'text/plain'}, {...voxel, blob: 'abc'}]) {
    expect(() => muProVoxelBlob(make(descriptor, invalid), accepted, point)).toThrow('文件无效');
  }
});

test('MuPRO voxel NPY rejects untrusted headers, sizes and dtypes while keeping 64-bit values', () => {
  const read = (bytes: Buffer, dtype: string) => muProVoxelValue(Uint8Array.from(bytes).buffer, dtype);
  const unsigned = Buffer.alloc(8);
  unsigned.writeBigUInt64LE(2n ** 63n + 123n);
  const signed = Buffer.alloc(8);
  signed.writeBigInt64BE(-(2n ** 62n) - 17n);
  const precise = Buffer.alloc(8);
  precise.writeDoubleLE(1.0000000000000002);
  expect(read(scalarNpy('<u8', unsigned), 'uint64')).toBe('9223372036854775931');
  expect(read(scalarNpy('>i8', signed), 'int64')).toBe('-4611686018427387921');
  expect(read(scalarNpy('<f8', precise), 'float64')).toBe('1.0000000000000002');
  precise.writeDoubleLE(-0);
  expect(read(scalarNpy('<f8', precise), 'float64')).toBe('-0');
  precise.writeDoubleLE(Infinity);
  expect(read(scalarNpy('<f8', precise), 'float64')).toBe('Infinity');
  const good = scalarNpy('<u8', unsigned);
  const badVersion = Buffer.from(good); badVersion[6] = 2;
  const badOffset = Buffer.from(good); badOffset.writeUInt16LE(0xffff, 8);
  for (const bad of [
    badVersion, badOffset, good.subarray(0, good.length - 1), Buffer.concat([good, Buffer.from([0])]),
    scalarNpy('<u8', unsigned, '(2, 1, 1)'), scalarNpy('<u8', unsigned, '(1, 1, 1)', 'True'),
    scalarNpy('|u8', unsigned), scalarNpy('|O8', unsigned), Buffer.alloc(4097),
  ]) expect(() => read(bad, 'uint64')).toThrow('单个值');
  expect(() => read(good, 'float64')).toThrow('所请求类型');
});
