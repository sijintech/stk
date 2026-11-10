import type {Artifact, GraphResult} from './graph';

const PATH = 'case/run.h5';
const READER = 'mupro.hdf5@1';
const SHA = /^[0-9a-f]{64}$/;
const SELECTOR = /^\/t([0-9]{8})\/([A-Za-z][A-Za-z0-9_]{0,63})$/;
const DTYPE = /^(?:float(?:32|64)|u?int(?:8|16|32|64))$/;

export type MuProArtifact = {path: typeof PATH, sha256: string, size: number};
export type MuProFrame = {selector: string, step: number, name: string, shape: [number, number, number, number], dtype: string};
export type MuProSource = {artifact: MuProArtifact, frame: MuProFrame, component: number | null};
export type GridPoint = [number, number, number];

const VOXEL_BUDGET = 256 * 1024;
const MAX_NPY_BYTES = 4096;

/** The pilot uses the published optional MuFerro output, selected explicitly with the MuPRO reader. */
export function muProArtifact(artifacts: Artifact[]): MuProArtifact | null {
  const rows = artifacts.filter(a => a?.path === PATH);
  const row = rows[0];
  return rows.length === 1 && typeof row.sha256 === 'string' && SHA.test(row.sha256) &&
    typeof row.size === 'number' && Number.isSafeInteger(row.size) && row.size > 0 && row.size <= 1024 ** 3
    ? {path: PATH, sha256: row.sha256, size: row.size} : null;
}

export function muProRequest(task: string, artifact: MuProArtifact, selected?: {frame: MuProFrame, component: number | null}) {
  const source = {binding: 'run', path: artifact.path, expected_sha256: artifact.sha256};
  const binding = {bindings: {run: {task_id: task}}, profile: 'web'};
  const graph = {schema: 'stk.graph/1', catalog: {stk: 1}};
  if (!selected) return {...binding, graph: {...graph, nodes: [
    {id: 'fields', type: 'stk.source.mupro_hdf5_fields@1', params: source},
  ], outputs: {fields: 'fields.out'}}, outputs: ['fields'], budget: {max_output_bytes: 256 * 1024}};

  const {frame, component} = selected;
  checkComponent(frame, component);
  return {...binding, graph: {...graph, nodes: [
    {id: 'field', type: 'stk.source.mupro_hdf5@1', params: {...source, selector: frame.selector}},
    {id: 'volume', type: 'stk.render.volume@1', inputs: {in: {from: 'field.out'}},
      params: {field: {name: frame.name, component}, encoding: 'f32'}},
    {id: 'scene', type: 'stk.view.scene@1', inputs: {layers: [{from: 'volume.layer'}]}},
  ], outputs: {view: 'scene.scene'}}, outputs: ['view']};
}

function checkComponent(frame: MuProFrame, component: number | null) {
  if (component === null ? frame.shape[3] !== 1 : !Number.isSafeInteger(component) || component < 0 || component >= frame.shape[3]) {
    throw new Error('请明确选择 HDF5 场的有效分量索引。');
  }
}

function output(result: GraphResult, name: string, type: 'value' | 'payload' | 'dataset' | 'file') {
  const value = result.outputs?.[name];
  if (result.schema !== 'stk.graph-result/1' || result.profile !== 'web' ||
      (result.errors !== undefined && (!Array.isArray(result.errors) || result.errors.length > 0)) || value?.type !== type) {
    throw new Error('MuPRO HDF5 图谱未返回所请求的结果。');
  }
  return value;
}

export function muProFrames(result: GraphResult, artifact: MuProArtifact): MuProFrame[] {
  const value = output(result, 'fields', 'value').value;
  if (value?.reader !== READER || value.path !== artifact.path || value.sha256 !== artifact.sha256 ||
      value.size !== artifact.size || !Array.isArray(value.fields) || value.fields.length > 256) {
    throw new Error('HDF5 字段列表与发布文件不符。');
  }
  const seen = new Set<string>();
  return value.fields.map((raw: unknown) => {
    const field = raw as Partial<MuProFrame>;
    const match = typeof field?.selector === 'string' ? SELECTOR.exec(field.selector) : null;
    if (!match || field.step !== Number(match[1]) || field.name !== match[2] || seen.has(match[0]) ||
        !Array.isArray(field.shape) || field.shape.length !== 4 ||
        !field.shape.every((n: unknown) => typeof n === 'number' && Number.isSafeInteger(n) && n > 0) ||
        typeof field.dtype !== 'string' || !DTYPE.test(field.dtype)) {
      throw new Error('HDF5 字段列表包含无效的场、步号、形状或类型。');
    }
    seen.add(match[0]);
    return {selector: match[0], step: field.step, name: field.name, shape: field.shape, dtype: field.dtype};
  });
}

export function muProManifest(result: GraphResult, frame: MuProFrame): unknown {
  const manifest = output(result, 'view', 'payload').manifest;
  if (manifest?.source?.time?.step !== frame.step || manifest.source.time.time !== null ||
      manifest.length_unit !== 'grid_index') {
    throw new Error('HDF5 渲染数据的步号或网格单位与所选帧不符。');
  }
  return manifest;
}

export function isGridPoint(point: number[], frame: MuProFrame): point is GridPoint {
  return point.length === 3 && point.every((n, axis) => Number.isSafeInteger(n) && n >= 0 && n < frame.shape[axis]);
}

/** Read one exact native grid point, then export just the displayed component as a scalar NPY. */
export function muProVoxelRequest(task: string, {artifact, frame, component}: MuProSource, point: GridPoint) {
  if (!isGridPoint(point, frame)) throw new Error('坐标必须是此帧范围内的整数网格索引。');
  checkComponent(frame, component);
  const extent = point.flatMap(n => [n, n]);
  const field = {id: 'field', type: 'stk.source.mupro_hdf5@1', params: {
    binding: 'run', path: artifact.path, expected_sha256: artifact.sha256, selector: frame.selector, extent,
  }};
  const extract = {id: 'component', type: 'stk.filter.calculator@1', inputs: {in: {from: 'field.out'}},
    params: {operation: 'component', field: frame.name, component, result: 'value', keep_input: false}};
  const voxel = {id: 'voxel', type: 'stk.output.dataset@1',
    inputs: {in: {from: component === null ? 'field.out' : 'component.out'}}, params: {format: 'npy'}};
  return {bindings: {run: {task_id: task}}, profile: 'web', budget: {max_output_bytes: VOXEL_BUDGET},
    graph: {schema: 'stk.graph/1', catalog: {stk: 1}, nodes: component === null ? [field, voxel] : [field, extract, voxel],
      outputs: {source: 'field.out', voxel: 'voxel.file'}},
    outputs: ['source', 'voxel']};
}

const tripletEquals = (value: unknown, expected: GridPoint) =>
  Array.isArray(value) && value.length === 3 && expected.every((n, i) => value[i] === n);

export function muProVoxelBlob(result: GraphResult, {artifact, frame}: MuProSource, point: GridPoint): {sha: string, size: number} {
  const descriptor = output(result, 'source', 'dataset').descriptor;
  const geometry = descriptor?.geometry;
  const sourceFrame = descriptor?.frames?.[0];
  const sources = sourceFrame?.sources;
  const source = sources && Object.hasOwn(sources, frame.name) ? sources[frame.name] : undefined;
  const field = descriptor?.fields?.[0];
  if (descriptor?.schema !== 'stk.dataset/1' || descriptor.id !== frame.name || descriptor.kind !== 'image' ||
      geometry?.length_unit !== 'grid_index' || !tripletEquals(geometry.dimensions, [1, 1, 1]) ||
      !tripletEquals(geometry.origin, point) || !tripletEquals(geometry.spacing, [1, 1, 1]) ||
      descriptor.time?.step !== frame.step || descriptor.frames?.length !== 1 || sourceFrame?.step !== frame.step ||
      source?.reader !== READER || source.path !== artifact.path || source.selector !== frame.selector ||
      source.sha256 !== artifact.sha256 || source.size !== artifact.size ||
      descriptor.fields?.length !== 1 || field?.name !== frame.name || field.association !== 'point' ||
      field.dtype !== frame.dtype || field.components !== frame.shape[3]) {
    throw new Error('HDF5 体素来源、坐标或类型与当前帧不符。');
  }
  const file = output(result, 'voxel', 'file');
  if (file.name !== 'voxel.npy' || file.media_type !== 'application/x-npy' ||
      typeof file.blob !== 'string' || !SHA.test(file.blob) || !Number.isSafeInteger(file.size) ||
      file.size <= 0 || file.size > MAX_NPY_BYTES) {
    throw new Error('HDF5 体素数据文件无效。');
  }
  return {sha: file.blob, size: file.size};
}

const NPY_DTYPES: Record<string, string> = {
  i1: 'int8', i2: 'int16', i4: 'int32', i8: 'int64',
  u1: 'uint8', u2: 'uint16', u4: 'uint32', u8: 'uint64', f4: 'float32', f8: 'float64',
};

/** Decode NumPy's small v1.0 scalar export. Keep integers out of JavaScript Number when they are 64-bit. */
export function muProVoxelValue(bytes: ArrayBuffer, dtype: string): string {
  const invalid = () => new Error('HDF5 体素数据不是所请求类型的单个值。');
  if (bytes.byteLength < 11 || bytes.byteLength > MAX_NPY_BYTES) throw invalid();
  const data = new DataView(bytes);
  if (data.getUint32(0) !== 0x934e554d || data.getUint32(4) !== 0x50590100) throw invalid();
  const offset = 10 + data.getUint16(8, true);
  if (offset <= 10 || offset % 16 !== 0 || offset >= bytes.byteLength) throw invalid();
  const header = new TextDecoder('ascii').decode(new Uint8Array(bytes, 10, offset - 10));
  const match = /^\{'descr': '([<>|])([iuf][1248])', 'fortran_order': False, 'shape': \(1, 1, 1\), \} *\n$/.exec(header);
  if (!match || match[0] !== header) throw invalid();
  const [, endian, kind] = match;
  const width = Number(kind[1]);
  if (!Object.hasOwn(NPY_DTYPES, kind) || NPY_DTYPES[kind] !== dtype ||
      (width === 1 ? endian !== '|' : endian === '|') || offset + width !== bytes.byteLength) throw invalid();
  const le = endian === '<';
  let value: number | bigint;
  switch (kind) {
    case 'i1': value = data.getInt8(offset); break;
    case 'i2': value = data.getInt16(offset, le); break;
    case 'i4': value = data.getInt32(offset, le); break;
    case 'i8': value = data.getBigInt64(offset, le); break;
    case 'u1': value = data.getUint8(offset); break;
    case 'u2': value = data.getUint16(offset, le); break;
    case 'u4': value = data.getUint32(offset, le); break;
    case 'u8': value = data.getBigUint64(offset, le); break;
    case 'f4': value = data.getFloat32(offset, le); break;
    case 'f8': value = data.getFloat64(offset, le); break;
    default: throw invalid();
  }
  return Object.is(value, -0) ? '-0' : String(value);
}
