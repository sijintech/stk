// stk.payload/2 decoder: manifest validation, buffer resolution (hub blobs by sha256 or .stkp chunks),
// hash verification, typed-array accessor views. See docs/specs/stk-render-payload-v2.md (§3, §9, §10).
// Pure TypeScript without DOM or vtk.js imports so it can be unit-tested with Node.
//
// Validation is a port of suan/render/payload.py _Validator (the reference): the same checks, so the web,
// Python and the desktop decoder (desktop/engine/lib/stk_io) accept and reject the same payloads. Checks that
// need buffer data (finite positions, index ranges, polyline offsets) run once the buffers are loaded, so an
// invalid manifest is rejected before anything is downloaded.

export const PAYLOAD_SCHEMA = 'stk.payload/2';
export type Vec3 = [number, number, number];
export type AccessorType = 'i8' | 'u8' | 'i16' | 'u16' | 'i32' | 'u32' | 'f32' | 'f64';
export type TypedArray = Int8Array | Uint8Array | Int16Array | Uint16Array | Int32Array | Uint32Array | Float32Array | Float64Array;
type TypedCtor = {new(buffer: ArrayBufferLike, byteOffset: number, length: number): TypedArray, BYTES_PER_ELEMENT: number};

export interface AccessorInfo {ctor: TypedCtor, integer: boolean, signed: boolean, max: number}
export const ACCESSOR_TYPES: Record<AccessorType, AccessorInfo> = {
  i8: {ctor: Int8Array, integer: true, signed: true, max: 127},
  u8: {ctor: Uint8Array, integer: true, signed: false, max: 255},
  i16: {ctor: Int16Array, integer: true, signed: true, max: 32767},
  u16: {ctor: Uint16Array, integer: true, signed: false, max: 65535},
  i32: {ctor: Int32Array, integer: true, signed: true, max: 2147483647},
  u32: {ctor: Uint32Array, integer: true, signed: false, max: 4294967295},
  f32: {ctor: Float32Array, integer: false, signed: true, max: 1},
  f64: {ctor: Float64Array, integer: false, signed: true, max: 1},
};
/** Own-property lookup, so manifest strings such as "__proto__" or "toString" never reach Object.prototype. */
export const own = <T>(table: Record<string, T> | null | undefined, key: unknown): T | undefined =>
  table && typeof key === 'string' && Object.prototype.hasOwnProperty.call(table, key) ? table[key] : undefined;
/** Storage type of an accessor type name (undefined for unknown names). */
export const accessorInfo = (type: unknown): AccessorInfo | undefined => own(ACCESSOR_TYPES as Record<string, AccessorInfo>, type);

export interface BufferSpec {id: string, uri: string, sha256: string, byteLength: number, encoding?: 'raw'}
export interface AccessorSpec {id: string, buffer: string, byteOffset: number, count: number, type: AccessorType,
  components: number, normalized?: boolean, min?: number[], max?: number[]}
export interface CategoryEntry {value: number, name: string, color: number[], family?: string, direction?: number[], aliases?: string[]}
export interface ColormapSpec {id: string, name: string, categorical: boolean, lut?: string, size?: number, entries?: CategoryEntry[],
  nan_color?: number[], below_color?: number[], above_color?: number[], unknown_color?: number[]}
export interface AttributeSpec {accessor: string, association?: 'point' | 'cell', categorical?: boolean, range?: [number, number],
  unit?: string, quantity?: string, component_names?: string[], palette?: string}
export interface ColorSpec {by?: 'solid' | 'attribute' | 'direction', solid?: number[], attribute?: string,
  component?: number | 'magnitude' | null, colormap?: string, range?: [number, number], interpolate?: 'linear' | 'nearest',
  max_magnitude?: number, lightness_range?: [number, number]}
export interface ProbeRef {node?: string, dataset?: string}
export interface LayerSpec {id: string, type: string, node?: string | null, name?: string | null, visible?: boolean,
  origin?: Vec3, pick?: {probe?: ProbeRef}, attributes?: Record<string, AttributeSpec>, appearance?: any, [key: string]: any}
export interface PayloadManifest {schema: string, source?: any, render_origin: Vec3, length_unit: string,
  bounds?: [Vec3, Vec3], buffers: BufferSpec[], accessors: AccessorSpec[], colormaps?: ColormapSpec[],
  layers: LayerSpec[], view?: any, stats?: any, budget?: any, [key: string]: any}

export const LAYER_TYPES = new Set(['triangles', 'slice_image', 'lines', 'points', 'instances', 'volume', 'overlay']);
export const OVERLAY_KINDS = new Set(['scalar_bar', 'legend', 'orientation_legend', 'text', 'axes_triad']);
export const GLYPH_SHAPES = new Set(['arrow', 'cone', 'sphere', 'line', 'cube']);
export const ORIENTATION_HSL = 'stk:orientation-hsl';
/** Ids that would address the prototype chain when used as object keys (spec §10). */
export const RESERVED_IDS = new Set(['__proto__', 'constructor', 'prototype']);
/** Scalar-bar label formats (spec §6.7); JavaScript's `$` matches only at the very end. */
export const LABEL_FORMAT = /^[+\- ]?#?0?(?:[1-9][0-9]?)?,?(?:(?:\.[0-9]{1,2})?[eEfFgG%]?|d)$/;

export class PayloadError extends Error {
  problems: string[];
  /** JSON pointer of the first problem ('' for the file or the whole manifest). */
  path: string;
  constructor(problems: string[], path = '') {
    super(`渲染数据包无效：${problems.slice(0, 4).join('；')}${problems.length > 4 ? `（另有 ${problems.length - 4} 项）` : ''}`);
    this.name = 'PayloadError';
    this.problems = problems;
    this.path = path;
  }
}

/** A layer that clients skip (spec §10): an unknown type or overlay kind, or overlay presentation members of a wrong type. */
export interface PayloadWarning {path: string, layer: string, message: string}

export interface LoadedPayload {
  manifest: PayloadManifest,
  /** Drawn layers in draw order (skipped layers left out, spec §1, §10). */
  layers: LayerSpec[],
  /** Human-readable warnings (skipped layers, unverified hashes). */
  warnings: string[],
  /** Skipped layers with their JSON pointers (the same list as Python's Payload.warnings). */
  skipped: PayloadWarning[],
  bytes: number,
  accessorSpec(id: string): AccessorSpec,
  /** Zero-copy typed view of an accessor (count × components values). */
  accessor(id: string): TypedArray,
  /** Float32 values (a copy when the stored type differs; applies `normalized`). */
  floats(id: string): Float32Array,
  colormap(id: string | undefined): ColormapSpec | undefined,
}

const HEX64 = /^[0-9a-f]{64}$/;
const ID = /^[A-Za-z0-9_][A-Za-z0-9_.:-]{0,127}$/;
const CHUNK_URI = /^#[1-9][0-9]*$/;
const isObj = (v: unknown): v is Record<string, any> => typeof v === 'object' && v !== null && !Array.isArray(v);
/** A JSON integer (spec §10): an integral number within ±(2^53 − 1). JavaScript cannot tell 5 from 5.0. */
const isInt = (v: unknown): v is number => typeof v === 'number' && Number.isSafeInteger(v);
const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
/** Optional members that are null count as absent (spec §10). */
const present = (v: unknown) => v !== undefined && v !== null;
const isStr = (v: unknown) => !present(v) || typeof v === 'string';
const isVec = (v: unknown, n: number): v is number[] => Array.isArray(v) && v.length === n && v.every(finite);
const hasOwn = (o: object, key: string) => Object.prototype.hasOwnProperty.call(o, key);
const quote = (v: unknown) => (v === undefined ? 'None' : JSON.stringify(v));

const LAYER_REQUIRED: Record<string, string[]> = {
  triangles: ['positions', 'indices'], slice_image: ['plane', 'size', 'attributes'],
  lines: ['positions', 'mode', 'indices'], points: ['positions'],
  instances: ['positions', 'directions', 'glyph'],
  volume: ['grid', 'data', 'value_range', 'transfer_function'], overlay: ['kind'],
};

/**
 * Presentation members of an overlay (spec §6.7) with a wrong type. Such overlays are skipped with a warning
 * (overlays only explain the view); drawing them would break the HTML overlay layer. (payload.py overlay_problems)
 */
export function overlayProblems(layer: LayerSpec): string[] {
  const problems: string[] = [];
  const check = (ok: boolean, key: string, text: string) => { if (!ok) problems.push(`${key} ${text}`); };
  const opt = (v: unknown, ok: (v: any) => boolean) => !present(v) || ok(v);
  check(isStr(layer.title), 'title', '必须是字符串');
  check(isStr(layer.anchor), 'anchor', '必须是字符串');
  check(isStr(layer.source_layer), 'source_layer', '必须是字符串');
  check(opt(layer.offset_px, v => isVec(v, 2)), 'offset_px', '必须是 2 个有限数');
  check(opt(layer.size_px, v => (finite(v) && v > 0) || (isVec(v, 2) && v.every((x: number) => x > 0))), 'size_px', '必须是正数或 2 个正数');
  switch (layer.kind) {
    case 'scalar_bar':
      check(isStr(layer.unit), 'unit', '必须是字符串');
      check(isStr(layer.orientation), 'orientation', '必须是字符串');
      break;
    case 'legend':
      check(opt(layer.values, v => Array.isArray(v) && v.every(isInt)), 'values', '必须是整数数组');
      check(opt(layer.columns, isInt), 'columns', '必须是整数');
      break;
    case 'orientation_legend':
      check(opt(layer.lightness_range, v => isVec(v, 2)), 'lightness_range', '必须是 2 个有限数');
      break;
    case 'text':
      check(opt(layer.font_size_px, v => finite(v) && v > 0), 'font_size_px', '必须是正数');
      check(opt(layer.color, v => Array.isArray(v) && (v.length === 3 || v.length === 4) && v.every(finite)), 'color', '必须是 3 或 4 个有限数');
      break;
    case 'axes_triad':
      check(opt(layer.labels, v => Array.isArray(v) && v.length === 3 && v.every((x: unknown) => typeof x === 'string')), 'labels', '必须是 3 个字符串');
      break;
  }
  return problems;
}

/** A check of spec §10 that needs buffer data: runs with a typed view of each accessor. */
type DataCheck = (view: (id: string) => TypedArray) => void;

interface Validated {manifest: PayloadManifest, skipped: PayloadWarning[], dataChecks: DataCheck[]}

const fail = (message: string, path = ''): never => { throw new PayloadError([path ? `${path}: ${message}` : message], path); };

/**
 * Structural validation (spec §10) of a manifest, in the order of suan/render/payload.py. `chunks` is the chunk
 * count of a .stkp file (buffers are then '#k' chunk references), else buffers are 'sha256:<hex>' blobs.
 */
function validate(input: unknown, chunks?: number): Validated {
  if (!isObj(input)) fail('清单必须是 JSON 对象');
  const m = input as PayloadManifest;
  if (chunks !== undefined) {
    // unpack_stkp: every buffer names a chunk of the file.
    if (present(m.buffers) && !(Array.isArray(m.buffers) && m.buffers.every(isObj))) fail('buffers 必须是对象数组', '/buffers');
    (m.buffers ?? []).forEach((b: any, i: number) => {
      if (typeof b.uri !== 'string' || !CHUNK_URI.test(b.uri) || Number(b.uri.slice(1)) >= chunks) fail(`缓冲区 URI ${quote(b.uri)} 不是本文件的分块`, `/buffers/${i}/uri`);
    });
  }
  if (m.schema !== PAYLOAD_SCHEMA) fail(`schema 应为 ${PAYLOAD_SCHEMA}，实际为 ${quote(m.schema)}`, '/schema');
  for (const key of ['render_origin', 'length_unit', 'buffers', 'accessors', 'layers']) if (!hasOwn(m, key)) fail(`缺少必需的键 ${key}`);
  const skipped: PayloadWarning[] = [];
  const dataChecks: DataCheck[] = [];

  const list = (value: unknown, path: string): Record<string, any>[] => {
    if (!Array.isArray(value)) fail('必须是数组', path);
    (value as unknown[]).forEach((item, i) => { if (!isObj(item)) fail('必须是对象', `${path}/${i}`); });
    return value as Record<string, any>[];
  };
  const object = (value: unknown, path: string, what: string): Record<string, any> => {
    if (!isObj(value)) fail(`${what} 必须是对象`, path);
    return value as Record<string, any>;
  };
  const uniqueId = (item: Record<string, any>, seen: {has(id: string): boolean}, path: string) => {
    const id = item.id;
    if (typeof id !== 'string' || !ID.test(id) || RESERVED_IDS.has(id)) fail(`id ${quote(id)} 无效`, `${path}/id`);
    if (seen.has(id)) fail(`id ${id} 重复`, `${path}/id`);
  };
  const vec3 = (value: unknown, path: string) => { if (!isVec(value, 3)) fail('必须是 3 个有限数', path); };
  const interval = (value: unknown, path: string) => { if (!isVec(value, 2)) fail('必须是 [lo, hi]（两个有限数）', path); };
  const rgb = (value: unknown, path: string) => {
    if (!(Array.isArray(value) && (value.length === 3 || value.length === 4) && value.every(v => finite(v) && v >= 0 && v <= 1))) fail('颜色必须是 [0, 1] 内的 3 或 4 个数', path);
  };

  vec3(m.render_origin, '/render_origin');
  if (typeof m.length_unit !== 'string' || !m.length_unit) fail('length_unit 必须是非空字符串', '/length_unit');

  const buffers = new Map<string, BufferSpec>();
  list(m.buffers, '/buffers').forEach((b, i) => {
    const path = `/buffers/${i}`;
    uniqueId(b, buffers, path);
    if (chunks === undefined && (typeof b.sha256 !== 'string' || b.uri !== `sha256:${b.sha256}`)) fail('缓冲区须以 sha256:<hex> 引用', `${path}/uri`);
    if (present(b.encoding) && b.encoding !== 'raw') fail(`编码 ${quote(b.encoding)} 不受支持`, `${path}/encoding`);
    if (typeof b.sha256 !== 'string' || !HEX64.test(b.sha256)) fail('sha256 必须是 64 位小写十六进制', `${path}/sha256`);
    if (!isInt(b.byteLength) || b.byteLength < 0) fail(`byteLength ${quote(b.byteLength)} 无效`, `${path}/byteLength`);
    buffers.set(b.id, b as BufferSpec);
  });

  const accessors = new Map<string, AccessorSpec>();
  list(m.accessors, '/accessors').forEach((a, i) => {
    const path = `/accessors/${i}`;
    uniqueId(a, accessors, path);
    const buffer = typeof a.buffer === 'string' ? buffers.get(a.buffer) : undefined;
    if (!buffer) return fail(`缓冲区 ${quote(a.buffer)} 不存在`, `${path}/buffer`);
    const info = accessorInfo(a.type);
    if (!info) return fail(`类型 ${quote(a.type)} 无效`, `${path}/type`);
    for (const [key, low] of [['count', 0], ['components', 1], ['byteOffset', 0]] as const) {
      if (!isInt(a[key]) || a[key] < low) fail(`${key} 必须是 ≥ ${low} 的整数`, `${path}/${key}`);
    }
    if (a.components > 16) fail('components 不能超过 16', `${path}/components`);
    if (a.byteOffset % 8 !== 0) fail('byteOffset 必须是 8 的倍数', `${path}/byteOffset`);
    if (a.byteOffset + a.count * a.components * info.ctor.BYTES_PER_ELEMENT > buffer.byteLength) fail('访问器超出其缓冲区', path);
    if (present(a.normalized) && typeof a.normalized !== 'boolean') fail('normalized 必须是布尔值', `${path}/normalized`);
    if (a.normalized === true && !info.integer) fail('normalized 仅适用于整数类型', `${path}/normalized`);
    accessors.set(a.id, a as AccessorSpec);
  });

  const expect = (id: unknown, types: string[] | null, components: number | null, count: number | null, path: string): AccessorSpec => {
    const a = typeof id === 'string' ? accessors.get(id) : undefined;
    if (!a) return fail(`访问器 ${quote(id)} 不存在`, path);
    if (types && !types.includes(a.type)) fail(`访问器 ${a.id} 的类型应为 ${types.join('/')}，实际为 ${a.type}`, path);
    if (components !== null && a.components !== components) fail(`访问器 ${a.id} 应有 ${components} 个分量`, path);
    if (count !== null && a.count !== count) fail(`访问器 ${a.id} 有 ${a.count} 项，应为 ${count}`, path);
    return a;
  };

  const colormaps = new Map<string, ColormapSpec>();
  list(present(m.colormaps) ? m.colormaps : [], '/colormaps').forEach((c, i) => {
    const path = `/colormaps/${i}`;
    uniqueId(c, colormaps, path);
    if (present(c.categorical) && typeof c.categorical !== 'boolean') fail('categorical 必须是布尔值', `${path}/categorical`);
    let keys: string[];
    if (c.categorical === true) {
      const values = new Set<number>();
      let count = 0;
      list(c.entries, `${path}/entries`).forEach((e, j) => {
        const epath = `${path}/entries/${j}`;
        if (!isInt(e.value)) fail('分类值必须是整数', `${epath}/value`);
        if (typeof e.name !== 'string') fail('分类名称必须是字符串', `${epath}/name`);
        rgb(e.color, `${epath}/color`);
        values.add(e.value);
        count++;
      });
      if (values.size !== count) fail('分类值必须互不相同', `${path}/entries`);
      keys = ['unknown_color'];
    } else {
      expect(c.lut, ['u8'], 4, 256, `${path}/lut`);
      if (!isInt(c.size) || c.size !== 256) fail('size 必须是 256', `${path}/size`);
      keys = ['nan_color', 'below_color', 'above_color'];
    }
    for (const key of keys) if (present(c[key])) rgb(c[key], `${path}/${key}`);
    colormaps.set(c.id, c as ColormapSpec);
  });
  const categorical = (id: unknown) => typeof id === 'string' && colormaps.get(id)?.categorical === true;

  // Data-level checks (spec §10), run after the buffers are loaded.
  const finiteData = (id: string, path: string) => dataChecks.push(view => {
    const values = view(id);
    for (let i = 0; i < values.length; i++) if (!Number.isFinite(values[i])) fail('坐标必须是有限数', path);
  });
  const positions = (owner: Record<string, any>, path: string): number => {
    const a = expect(owner.positions, ['f32'], 3, null, `${path}/positions`);
    finiteData(a.id, `${path}/positions`);
    return a.count;
  };
  const indices = (id: unknown, points: number, multiple: number, path: string): number => {
    const a = expect(id, ['u32', 'u16'], 1, null, path);
    if (a.count % multiple !== 0) fail(`索引数必须是 ${multiple} 的倍数`, path);
    dataChecks.push(view => {
      const values = view(a.id);
      for (let i = 0; i < values.length; i++) if (values[i] >= points) fail('索引指向不存在的点', path);
    });
    return a.count / multiple;
  };
  /** Checks attributes; a cell count of 'segments' (polylines) is checked with the offsets data. */
  const attributes = (layer: Record<string, any>, path: string, points: number, cells?: number | {segments: {accessor: string, path: string}[]}): Record<string, any> => {
    if (!present(layer.attributes)) return {};
    const attrs = object(layer.attributes, `${path}/attributes`, 'attributes');
    for (const [name, attr] of Object.entries(attrs)) {
      const apath = `${path}/attributes/${name}`;
      object(attr, apath, '属性');
      const association = present(attr.association) ? attr.association : 'point';
      if (association !== 'point' && !(association === 'cell' && cells !== undefined)) fail(`关联方式 ${quote(association)} 在此无效`, `${apath}/association`);
      if (association === 'point') expect(attr.accessor, null, null, points, `${apath}/accessor`);
      else if (typeof cells === 'number') expect(attr.accessor, null, null, cells, `${apath}/accessor`);
      else cells!.segments.push({accessor: expect(attr.accessor, null, null, null, `${apath}/accessor`).id, path: `${apath}/accessor`});
      if (present(attr.palette) && !categorical(attr.palette)) fail(`调色板 ${quote(attr.palette)} 不是分类颜色表`, `${apath}/palette`);
    }
    return attrs;
  };
  const appearance = (layer: Record<string, any>, path: string): Record<string, any> =>
    present(layer.appearance) ? object(layer.appearance, `${path}/appearance`, 'appearance') : {};
  const color = (spec: unknown, attrs: Record<string, any>, path: string) => {
    if (!present(spec)) return;
    const s = object(spec, path, '颜色设置');
    const by = present(s.by) ? s.by : 'solid'; // spec §5: the default mode
    if (by !== 'solid' && by !== 'attribute' && by !== 'direction') fail(`未知着色方式 ${quote(s.by)}`, `${path}/by`);
    if ((by === 'attribute' || (by === 'direction' && present(s.attribute))) && !(typeof s.attribute === 'string' && hasOwn(attrs, s.attribute))) fail(`属性 ${quote(s.attribute)} 不存在`, `${path}/attribute`);
    if (present(s.colormap)) {
      if (by === 'direction' && s.colormap !== ORIENTATION_HSL) fail(`方向着色仅支持 ${ORIENTATION_HSL}`, `${path}/colormap`);
      if (s.colormap !== ORIENTATION_HSL && !(typeof s.colormap === 'string' && colormaps.has(s.colormap))) fail(`颜色表 ${quote(s.colormap)} 不存在`, `${path}/colormap`);
    }
    if (present(s.range)) interval(s.range, `${path}/range`);
  };
  const dims3 = (v: unknown): v is number[] => Array.isArray(v) && v.length === 3 && v.every(n => isInt(n) && n >= 1);

  const layerChecks: Record<string, (layer: Record<string, any>, path: string) => void> = {
    triangles(layer, path) {
      const n = positions(layer, path);
      const cells = indices(layer.indices, n, 3, `${path}/indices`);
      if (present(layer.normals)) expect(layer.normals, ['f32'], 3, n, `${path}/normals`);
      const attrs = attributes(layer, path, n, cells);
      color(appearance(layer, path).color, attrs, `${path}/appearance/color`);
      list(present(layer.lods) ? layer.lods : [], `${path}/lods`).forEach((lod, j) => {
        const lpath = `${path}/lods/${j}`;
        const count = positions(lod, lpath);
        const lodCells = indices(lod.indices, count, 3, `${lpath}/indices`);
        if (present(lod.normals)) expect(lod.normals, ['f32'], 3, count, `${lpath}/normals`);
        attributes(lod, lpath, count, lodCells);
      });
    },
    slice_image(layer, path) {
      const plane = layer.plane;
      for (const key of ['origin', 'u', 'v']) vec3(isObj(plane) ? plane[key] : undefined, `${path}/plane/${key}`);
      const size = layer.size;
      if (!(Array.isArray(size) && size.length === 2 && size.every(v => isInt(v) && v >= 1))) fail('size 必须是两个正整数 [w, h]', `${path}/size`);
      const attrs = attributes(layer, path, size[0] * size[1]);
      if (!Object.keys(attrs).length) fail('slice_image 图层至少需要一个属性', `${path}/attributes`);
      color(appearance(layer, path).color, attrs, `${path}/appearance/color`);
    },
    lines(layer, path) {
      const n = positions(layer, path);
      let cells: number | {segments: {accessor: string, path: string}[]};
      if (layer.mode === 'segments') cells = indices(layer.indices, n, 2, `${path}/indices`);
      else if (layer.mode === 'polylines') {
        const count = indices(layer.indices, n, 1, `${path}/indices`);
        if (!present(layer.offsets)) fail('polylines 需要 offsets', path);
        const offsets = expect(layer.offsets, ['u32'], 1, null, `${path}/offsets`);
        const segmentAttributes: {accessor: string, path: string}[] = [];
        cells = {segments: segmentAttributes};
        dataChecks.push(view => {
          const o = view(offsets.id);
          let segments = 0, ok = o.length >= 1 && o[0] === 0 && o[o.length - 1] === count;
          for (let i = 1; ok && i < o.length; i++) {
            if (o[i] < o[i - 1]) ok = false;
            else segments += Math.max(o[i] - o[i - 1] - 1, 0); // cell attributes are per segment
          }
          if (!ok) fail('offsets 必须从 0 递增到索引数', `${path}/offsets`);
          for (const attr of segmentAttributes) {
            const got = accessors.get(attr.accessor)!.count;
            if (got !== segments) fail(`应有 ${segments} 个线段值（实际 ${got}）`, attr.path);
          }
        });
      } else return fail(`未知的线模式 ${quote(layer.mode)}`, `${path}/mode`);
      const attrs = attributes(layer, path, n, cells);
      color(appearance(layer, path).color, attrs, `${path}/appearance/color`);
    },
    points(layer, path) {
      const n = positions(layer, path);
      if (present(layer.radii)) expect(layer.radii, ['f32'], 1, n, `${path}/radii`);
      const attrs = attributes(layer, path, n);
      color(appearance(layer, path).color, attrs, `${path}/appearance/color`);
    },
    instances(layer, path) {
      const n = positions(layer, path);
      expect(layer.directions, ['f32'], 3, n, `${path}/directions`);
      if (present(layer.scales)) expect(layer.scales, ['f32'], 1, n, `${path}/scales`);
      const glyph = object(layer.glyph, `${path}/glyph`, 'glyph');
      if (typeof glyph.shape !== 'string' || !GLYPH_SHAPES.has(glyph.shape)) fail(`未知的箭头形状 ${quote(glyph.shape)}`, `${path}/glyph/shape`);
      const attrs = attributes(layer, path, n);
      const app = appearance(layer, path);
      color(app.color, attrs, `${path}/appearance/color`);
      if (present(app.scale)) {
        const scale = object(app.scale, `${path}/appearance/scale`, 'scale');
        if (scale.by === 'attribute' && !(typeof scale.attribute === 'string' && hasOwn(attrs, scale.attribute))) fail(`缩放属性 ${quote(scale.attribute)} 不存在`, `${path}/appearance/scale`);
        if (present(scale.factor) && !(finite(scale.factor) && scale.factor > 0)) fail('缩放系数必须是大于 0 的有限数', `${path}/appearance/scale/factor`);
      }
    },
    volume(layer, path) {
      const grid = layer.grid;
      const dims = isObj(grid) ? grid.dimensions : undefined;
      if (!dims3(dims)) return fail('dimensions 必须是 3 个正整数', `${path}/grid/dimensions`);
      vec3(grid.origin, `${path}/grid/origin`);
      vec3(grid.spacing, `${path}/grid/spacing`);
      if (Math.min(...grid.spacing) <= 0) fail('spacing 必须为正', `${path}/grid/spacing`);
      if (present(grid.direction) && !isVec(grid.direction, 9)) fail('direction 必须是 9 个有限数（行优先 3×3）', `${path}/grid/direction`);
      expect(layer.data, ['u8', 'u16', 'f32'], 1, dims[0] * dims[1] * dims[2], `${path}/data`);
      interval(layer.value_range, `${path}/value_range`);
      for (const key of ['value_scale', 'value_offset']) if (present(layer[key]) && !finite(layer[key])) fail(`${key} 必须是有限数`, `${path}/${key}`);
      const tpath = `${path}/transfer_function`;
      const tf = object(layer.transfer_function, tpath, 'transfer_function');
      // A continuous LUT, or a categorical palette for label volumes (value ± 0.499).
      if (!(typeof tf.colormap === 'string' && colormaps.has(tf.colormap))) fail(`颜色表 ${quote(tf.colormap)} 不存在`, `${tpath}/colormap`);
      interval(tf.range, `${tpath}/range`);
      if (!Array.isArray(tf.opacity) || tf.opacity.length < 2) fail('opacity 至少需要两个 [value, alpha] 点', `${tpath}/opacity`);
      (tf.opacity as unknown[]).forEach((p, j) => {
        if (!isVec(p, 2) || p[1] < 0 || p[1] > 1) fail('不透明度点应为 [有限值, [0, 1] 内的 alpha]', `${tpath}/opacity/${j}`);
      });
      list(present(layer.lods) ? layer.lods : [], `${path}/lods`).forEach((lod, j) => {
        const lpath = `${path}/lods/${j}`;
        if (!dims3(lod.dimensions)) fail('dimensions 必须是 3 个正整数', `${lpath}/dimensions`);
        expect(lod.data, ['u8', 'u16', 'f32'], 1, lod.dimensions[0] * lod.dimensions[1] * lod.dimensions[2], `${lpath}/data`);
      });
    },
    overlay(layer, path) {
      const kind = layer.kind;
      if (typeof kind !== 'string') return fail('kind 必须是字符串', `${path}/kind`);
      if (!OVERLAY_KINDS.has(kind)) { skipped.push({path, layer: layer.id, message: `跳过未知叠加层 ${kind}（${layer.id}）`}); return; }
      if ((kind === 'scalar_bar' || kind === 'legend') && !(typeof layer.colormap === 'string' && colormaps.has(layer.colormap))) fail(`颜色表 ${quote(layer.colormap)} 不存在`, `${path}/colormap`);
      if (kind === 'scalar_bar') {
        if (categorical(layer.colormap)) fail('色标需要连续颜色表', `${path}/colormap`);
        interval(layer.range, `${path}/range`);
        if (present(layer.label_count) && !(isInt(layer.label_count) && layer.label_count >= 2 && layer.label_count <= 20)) fail('label_count 必须是 2 到 20 的整数', `${path}/label_count`);
        if (present(layer.format) && !(typeof layer.format === 'string' && LABEL_FORMAT.test(layer.format))) fail(`不支持的标签格式 ${quote(layer.format)}（如 .3g、.2f、.1e、+.0%、d）`, `${path}/format`);
      }
      if (kind === 'legend' && !categorical(layer.colormap)) fail('图例需要分类颜色表', `${path}/colormap`);
      if (kind === 'text' && typeof layer.text !== 'string') fail('文本叠加层需要 text', `${path}/text`);
      const problems = overlayProblems(layer as LayerSpec);
      if (problems.length) skipped.push({path, layer: layer.id, message: `跳过叠加层 ${layer.id}：${problems.join('；')}`});
    },
  };

  const layerIds = new Set<string>();
  list(m.layers, '/layers').forEach((layer, i) => {
    const path = `/layers/${i}`;
    uniqueId(layer, layerIds, path);
    layerIds.add(layer.id);
    if (!isStr(layer.name)) fail('name 必须是字符串', `${path}/name`);
    if (typeof layer.type !== 'string') fail('type 必须是字符串', `${path}/type`);
    const required = own(LAYER_REQUIRED, layer.type);
    if (!required) { skipped.push({path, layer: layer.id, message: `跳过未知图层类型 ${layer.type}（${layer.id}）`}); return; } // spec §1
    for (const key of required) if (!hasOwn(layer, key)) fail(`${layer.type} 图层缺少 ${key}`, path);
    if (present(layer.origin)) vec3(layer.origin, `${path}/origin`);
    layerChecks[layer.type](layer, path);
  });
  if (present(m.bounds)) {
    if (!Array.isArray(m.bounds) || m.bounds.length !== 2) fail('bounds 必须是 [[min], [max]]', '/bounds');
    vec3(m.bounds[0], '/bounds/0');
    vec3(m.bounds[1], '/bounds/1');
  }
  if (present(m.view) && !(isObj(m.view) && m.view.schema === 'stk.view/1')) fail('view 必须是 stk.view/1 文档', '/view');
  return {manifest: m, skipped, dataChecks};
}

/** Structural validation of a manifest (no buffer data needed). Throws PayloadError. */
export function validateManifest(input: unknown): PayloadManifest {
  return validate(input).manifest;
}

/**
 * Where `view.probe` should read for a layer (spec §6 `pick.probe`); layers without it fall back to their
 * own graph node (`layer.node`), from which clients walk upstream to the field source.
 */
export function probeOf(layer: LayerSpec): ProbeRef | undefined {
  const probe = isObj(layer.pick) && isObj(layer.pick.probe) ? layer.pick.probe : {};
  const node = typeof probe.node === 'string' && probe.node ? probe.node : typeof layer.node === 'string' && layer.node ? layer.node : undefined;
  if (!node) return undefined;
  return typeof probe.dataset === 'string' && probe.dataset ? {node, dataset: probe.dataset} : {node};
}

// ---------------------------------------------------------------------------------------------
// .stkp single-file form (spec §9)

export interface StkpFile {manifest: unknown, chunks: Uint8Array[]}

/** RFC 8259 JSON as every client reads it: numbers must be finite doubles (1e400 is rejected). */
export function parseJson(text: string): unknown {
  return JSON.parse(text, (_key, value) => {
    if (typeof value === 'number' && !Number.isFinite(value)) throw new SyntaxError('number overflows a double');
    return value;
  });
}

export function parseStkp(file: ArrayBuffer): StkpFile {
  const view = new DataView(file);
  const size = file.byteLength;
  const bad = (text: string): never => fail(`.stkp 文件无效：${text}`);
  if (size < 16) bad('文件过短');
  const magic = String.fromCharCode(view.getUint8(0), view.getUint8(1), view.getUint8(2), view.getUint8(3));
  if (magic !== 'STKP') bad('缺少 STKP 标记');
  if (view.getUint32(4, true) !== 2) bad(`版本 ${view.getUint32(4, true)} 不受支持`);
  const total = view.getBigUint64(8, true);
  if (total !== BigInt(size)) bad(`长度字段 ${total} 与文件大小 ${size} 不符`);
  const chunks: Uint8Array[] = [];
  const types: string[] = [];
  let offset = 16;
  while (offset < size) {
    if (offset + 16 > size) bad('分块头不完整');
    const length = view.getBigUint64(offset, true);
    const type = String.fromCharCode(view.getUint8(offset + 8), view.getUint8(offset + 9), view.getUint8(offset + 10), view.getUint8(offset + 11));
    const reserved = view.getUint32(offset + 12, true);
    offset += 16;
    if (reserved !== 0) bad('分块保留字段必须为 0');
    if (length > BigInt(size - offset)) bad(`分块 ${chunks.length} 超出文件长度`);
    const n = Number(length);
    chunks.push(new Uint8Array(file, offset, n));
    types.push(type);
    offset += n + ((8 - (n % 8)) % 8);
  }
  if (offset !== size) bad('填充超出文件末尾');
  if (!chunks.length || types[0] !== 'JSON') bad('第一个分块必须是 JSON 清单');
  types.slice(1).forEach((t, i) => { if (t !== 'BIN ') bad(`分块 ${i + 1} 类型 ${JSON.stringify(t)} 无效`); });
  let manifest: unknown;
  try {
    // Strict UTF-8, and a byte-order mark is kept so that it is rejected like any other stray character.
    manifest = parseJson(new TextDecoder('utf-8', {fatal: true, ignoreBOM: true}).decode(chunks[0]));
  } catch { bad('清单不是有效的 UTF-8 JSON'); }
  return {manifest, chunks};
}

// ---------------------------------------------------------------------------------------------
// Blob fetching with a verified in-memory cache keyed by sha256.

export type BlobFetcher = (sha256: string, signal?: AbortSignal) => Promise<ArrayBuffer>;
const blobCache = new Map<string, Promise<ArrayBuffer>>();
const blobSizes = new Map<string, number>();
let cachedBytes = 0;
// Bounded by device memory where the browser reports it (phones), 128–512 MiB; 256 MiB otherwise.
const deviceMemory = Number((globalThis as any).navigator?.deviceMemory) || 0;
export const BLOB_CACHE_LIMIT = (deviceMemory ? Math.min(512, Math.max(128, deviceMemory * 64)) : 256) * 1024 * 1024;

export async function sha256Hex(bytes: Uint8Array): Promise<string | null> {
  const subtle = (globalThis as any).crypto?.subtle;
  if (!subtle) return null; // insecure context: hashing unavailable (reported as a warning)
  const digest = new Uint8Array(await subtle.digest('SHA-256', bytes));
  let hex = '';
  for (const b of digest) hex += b.toString(16).padStart(2, '0');
  return hex;
}

/** Fetch a blob once per session; the promise resolves only for bytes that hash to `sha`. */
export function cachedBlob(sha: string, fetcher: BlobFetcher, signal?: AbortSignal): Promise<ArrayBuffer> {
  if (!HEX64.test(sha)) return Promise.reject(new PayloadError([`无效的数据块标识 ${sha}`]));
  const hit = blobCache.get(sha);
  if (hit) { blobCache.delete(sha); blobCache.set(sha, hit); return hit; } // LRU order
  const pending = (async () => {
    const data = await fetcher(sha, signal);
    const actual = await sha256Hex(new Uint8Array(data));
    if (actual !== null && actual !== sha) throw new PayloadError([`数据块 ${sha.slice(0, 12)}… 的内容与其 sha256 不符`]);
    return data;
  })();
  blobCache.set(sha, pending);
  pending.then(data => {
    if (blobCache.get(sha) !== pending) return;
    blobSizes.set(sha, data.byteLength);
    cachedBytes += data.byteLength;
    for (const key of blobCache.keys()) {
      if (cachedBytes <= BLOB_CACHE_LIMIT || key === sha) break;
      cachedBytes -= blobSizes.get(key) ?? 0;
      blobSizes.delete(key);
      blobCache.delete(key);
    }
  }, () => { if (blobCache.get(sha) === pending) blobCache.delete(sha); });
  return pending;
}

export function clearBlobCache() { blobCache.clear(); blobSizes.clear(); cachedBytes = 0; }

// ---------------------------------------------------------------------------------------------
// Loading

export interface LoadOptions {
  /** Fetches `sha256:` buffers (hub blob store or a directory of <sha>.bin files). */
  fetchBlob?: BlobFetcher,
  /** Chunks of a .stkp file: every buffer is then a `#k` chunk reference. */
  chunks?: Uint8Array[],
  signal?: AbortSignal,
}

export async function loadStkp(file: ArrayBuffer, options: Omit<LoadOptions, 'chunks'> = {}): Promise<LoadedPayload> {
  const {manifest, chunks} = parseStkp(file);
  return loadPayload(manifest, {...options, chunks});
}

export async function loadPayload(input: unknown, options: LoadOptions = {}): Promise<LoadedPayload> {
  const {manifest, skipped, dataChecks} = validate(input, options.chunks?.length);
  const warnings: string[] = skipped.map(w => w.message);
  const problems: string[] = [];
  const buffers = new Map<string, Uint8Array>();
  let hashSkipped = false;
  await Promise.all(manifest.buffers.map(async (b, i) => {
    let bytes: Uint8Array;
    if (options.chunks) {
      bytes = options.chunks[Number(b.uri.slice(1))];
      const actual = await sha256Hex(bytes);
      if (actual === null) hashSkipped = true;
      else if (actual !== b.sha256) { problems.push(`/buffers/${i}/sha256: 缓冲区 ${b.id} 的内容与 sha256 不符`); return; }
    } else {
      if (!options.fetchBlob) { problems.push(`/buffers/${i}: 缓冲区 ${b.id} 需要从控制服务读取，但未提供读取方式`); return; }
      try { bytes = new Uint8Array(await cachedBlob(b.sha256, options.fetchBlob, options.signal)); } catch (error) {
        if (error instanceof PayloadError) { problems.push(`/buffers/${i}/sha256: ${error.problems[0]}`); return; }
        throw error;
      }
      if ((globalThis as any).crypto?.subtle === undefined) hashSkipped = true;
    }
    if (bytes.byteLength !== b.byteLength) { problems.push(`/buffers/${i}/byteLength: 缓冲区 ${b.id} 长度为 ${bytes.byteLength}，清单声明 ${b.byteLength}`); return; }
    buffers.set(b.id, bytes);
  }));
  if (problems.length) throw new PayloadError(problems, problems[0].slice(0, problems[0].indexOf(':')));
  if (hashSkipped) warnings.push('当前页面不是安全上下文，未能校验数据块 sha256');

  const specs = new Map(manifest.accessors.map(a => [a.id, a]));
  const views = new Map<string, TypedArray>();
  const floatViews = new Map<string, Float32Array>();
  const colormaps = new Map((manifest.colormaps ?? []).map(c => [c.id, c]));
  const accessorSpec = (id: string) => {
    const spec = specs.get(id);
    if (!spec) throw new PayloadError([`访问器 ${id} 不存在`]);
    return spec;
  };
  const accessor = (id: string): TypedArray => {
    const cached = views.get(id);
    if (cached) return cached;
    const spec = accessorSpec(id);
    const bytes = buffers.get(spec.buffer)!;
    const {ctor} = accessorInfo(spec.type)!;
    const length = spec.count * spec.components;
    const start = bytes.byteOffset + spec.byteOffset;
    const view = start % ctor.BYTES_PER_ELEMENT === 0
      ? new ctor(bytes.buffer, start, length)
      : new ctor(bytes.slice(spec.byteOffset, spec.byteOffset + length * ctor.BYTES_PER_ELEMENT).buffer, 0, length);
    views.set(id, view);
    return view;
  };
  const floats = (id: string): Float32Array => {
    const cached = floatViews.get(id);
    if (cached) return cached;
    const spec = accessorSpec(id);
    const raw = accessor(id);
    let out: Float32Array;
    if (raw instanceof Float32Array) out = raw;
    else {
      out = new Float32Array(raw.length);
      const info = accessorInfo(spec.type)!;
      const scale = spec.normalized && info.integer ? 1 / info.max : 1;
      for (let i = 0; i < raw.length; i++) out[i] = spec.normalized && info.signed ? Math.max(-1, raw[i] * scale) : raw[i] * scale;
    }
    floatViews.set(id, out);
    return out;
  };
  for (const check of dataChecks) check(accessor); // finite positions, index ranges, polyline offsets (spec §10)

  const skippedIds = new Set(skipped.map(w => w.layer));
  const loaded: LoadedPayload = {
    manifest, layers: manifest.layers.filter(layer => !skippedIds.has(layer.id)), warnings, skipped,
    bytes: [...buffers.values()].reduce((n, b) => n + b.byteLength, 0),
    accessorSpec, accessor, floats,
    colormap: id => (id === undefined ? undefined : colormaps.get(id)),
  };
  return loaded;
}

/** Physical origin of a layer's coordinates (spec §4). */
export function layerOrigin(p: LoadedPayload, layer: LayerSpec): Vec3 {
  return (layer.origin ?? p.manifest.render_origin) as Vec3;
}
