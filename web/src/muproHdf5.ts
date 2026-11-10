import type {Artifact, GraphResult} from './graph';

const PATH = 'case/run.h5';
const READER = 'mupro.hdf5@1';
const SHA = /^[0-9a-f]{64}$/;
const SELECTOR = /^\/t([0-9]{8})\/([A-Za-z][A-Za-z0-9_]{0,63})$/;
const DTYPE = /^(?:float(?:32|64)|u?int(?:8|16|32|64))$/;

export type MuProArtifact = {path: typeof PATH, sha256: string, size: number};
export type MuProFrame = {selector: string, step: number, name: string, shape: [number, number, number, number], dtype: string};
export type MuProSource = {artifact: MuProArtifact, frame: MuProFrame, component: number | null};

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
  if (component === null ? frame.shape[3] !== 1 : !Number.isSafeInteger(component) || component < 0 || component >= frame.shape[3]) {
    throw new Error('请明确选择 HDF5 场的有效分量索引。');
  }
  return {...binding, graph: {...graph, nodes: [
    {id: 'field', type: 'stk.source.mupro_hdf5@1', params: {...source, selector: frame.selector}},
    {id: 'volume', type: 'stk.render.volume@1', inputs: {in: {from: 'field.out'}},
      params: {field: {name: frame.name, component}, encoding: 'f32'}},
    {id: 'scene', type: 'stk.view.scene@1', inputs: {layers: [{from: 'volume.layer'}]}},
  ], outputs: {view: 'scene.scene'}}, outputs: ['view']};
}

function output(result: GraphResult, name: 'fields' | 'view', type: 'value' | 'payload') {
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
