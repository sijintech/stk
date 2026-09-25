// stk.payload/2 decoder: manifest validation, buffer resolution (hub blobs by sha256 or .stkp chunks),
// hash verification, typed-array accessor views. See docs/specs/stk-render-payload-v2.md (§3, §9, §10).
// Pure TypeScript without DOM or vtk.js imports so it can be unit-tested with Node.

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
export const ORIENTATION_HSL = 'stk:orientation-hsl';

export class PayloadError extends Error {
  problems: string[];
  constructor(problems: string[]) {
    super(`渲染数据包无效：${problems.slice(0, 4).join('；')}${problems.length > 4 ? `（另有 ${problems.length - 4} 项）` : ''}`);
    this.name = 'PayloadError';
    this.problems = problems;
  }
}

export interface LoadedPayload {
  manifest: PayloadManifest,
  /** Layers of known types in draw order (unknown types are skipped per spec §1). */
  layers: LayerSpec[],
  warnings: string[],
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
/** Ids are used as object keys by the viewer; "__proto__" would address the prototype. */
const validId = (v: unknown): v is string => typeof v === 'string' && ID.test(v) && v !== '__proto__';
const isObj = (v: unknown): v is Record<string, any> => typeof v === 'object' && v !== null && !Array.isArray(v);
const isInt = (v: unknown): v is number => typeof v === 'number' && Number.isInteger(v);
const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const isVec = (v: unknown, n: number) => Array.isArray(v) && v.length === n && v.every(finite);

/** Structural validation of a manifest (no buffer data needed). Throws PayloadError. */
export function validateManifest(input: unknown): PayloadManifest {
  const problems: string[] = [];
  const bad = (text: string) => { if (problems.length < 200) problems.push(text); };
  if (!isObj(input)) throw new PayloadError(['清单不是 JSON 对象']);
  const m = input as PayloadManifest;
  if (m.schema !== PAYLOAD_SCHEMA) throw new PayloadError([`schema 应为 ${PAYLOAD_SCHEMA}，实际为 ${JSON.stringify(m.schema)}`]);
  if (!isVec(m.render_origin, 3)) bad('render_origin 必须是 3 个有限数');
  if (typeof m.length_unit !== 'string' || !m.length_unit) bad('缺少 length_unit');
  for (const key of ['buffers', 'accessors', 'layers'] as const) if (!Array.isArray(m[key])) bad(`${key} 必须是数组`);
  if (problems.length) throw new PayloadError(problems);
  if (m.bounds !== undefined && !(Array.isArray(m.bounds) && m.bounds.length === 2 && isVec(m.bounds[0], 3) && isVec(m.bounds[1], 3))) bad('bounds 格式错误');

  const buffers = new Map<string, BufferSpec>();
  for (const b of m.buffers) {
    if (!isObj(b) || !validId(b.id)) { bad('缓冲区 id 无效'); continue; }
    if (buffers.has(b.id)) bad(`缓冲区 ${b.id} 重复`);
    if (typeof b.sha256 !== 'string' || !HEX64.test(b.sha256)) bad(`缓冲区 ${b.id} 的 sha256 无效`);
    if (!isInt(b.byteLength) || b.byteLength < 0) bad(`缓冲区 ${b.id} 的 byteLength 无效`);
    if (typeof b.uri !== 'string' || !/^(sha256:[0-9a-f]{64}|#[1-9][0-9]*)$/.test(b.uri)) bad(`缓冲区 ${b.id} 的 uri 无效`);
    else if (b.uri.startsWith('sha256:') && b.uri.slice(7) !== b.sha256) bad(`缓冲区 ${b.id} 的 uri 与 sha256 不一致`);
    if (b.encoding !== undefined && b.encoding !== 'raw') bad(`缓冲区 ${b.id} 的编码 ${b.encoding} 不受支持`);
    buffers.set(b.id, b);
  }
  const accessors = new Map<string, AccessorSpec>();
  for (const a of m.accessors) {
    if (!isObj(a) || !validId(a.id)) { bad('访问器 id 无效'); continue; }
    if (accessors.has(a.id)) bad(`访问器 ${a.id} 重复`);
    accessors.set(a.id, a);
    const info = accessorInfo(a.type);
    const buffer = buffers.get(a.buffer);
    if (!info) { bad(`访问器 ${a.id} 的类型 ${String(a.type)} 无效`); continue; }
    if (!isInt(a.components) || a.components < 1 || a.components > 16) { bad(`访问器 ${a.id} 的分量数无效`); continue; }
    if (!isInt(a.count) || a.count < 0) { bad(`访问器 ${a.id} 的 count 无效`); continue; }
    if (!isInt(a.byteOffset) || a.byteOffset < 0 || a.byteOffset % 8 !== 0) { bad(`访问器 ${a.id} 的 byteOffset 未按 8 字节对齐`); continue; }
    if (a.normalized && !info.integer) bad(`访问器 ${a.id}：normalized 仅适用于整数类型`);
    if (!buffer) { bad(`访问器 ${a.id} 引用了不存在的缓冲区 ${a.buffer}`); continue; }
    const end = a.byteOffset + a.count * a.components * info.ctor.BYTES_PER_ELEMENT;
    if (isInt(buffer.byteLength) && end > buffer.byteLength) bad(`访问器 ${a.id} 超出缓冲区 ${buffer.id} 范围（${end} > ${buffer.byteLength}）`);
  }
  const colormaps = new Map<string, ColormapSpec>();
  for (const c of m.colormaps ?? []) {
    if (!isObj(c) || typeof c.id !== 'string') { bad('颜色表 id 无效'); continue; }
    if (colormaps.has(c.id)) bad(`颜色表 ${c.id} 重复`);
    colormaps.set(c.id, c);
    if (c.categorical) {
      if (!Array.isArray(c.entries)) bad(`分类颜色表 ${c.id} 缺少 entries`);
      else for (const e of c.entries) if (!isObj(e) || !isInt(e.value) || typeof e.name !== 'string' || !Array.isArray(e.color) || e.color.length < 3 || !e.color.every(finite)) { bad(`分类颜色表 ${c.id} 含无效条目`); break; }
      if (c.unknown_color !== undefined && !(Array.isArray(c.unknown_color) && c.unknown_color.length >= 3 && c.unknown_color.every(finite))) bad(`分类颜色表 ${c.id} 的 unknown_color 无效`);
    } else {
      const lut = c.lut === undefined ? undefined : accessors.get(c.lut);
      if (!lut) bad(`颜色表 ${c.id} 引用了不存在的查找表访问器 ${c.lut}`);
      else if (lut.type !== 'u8' || lut.components !== 4 || lut.count !== 256) bad(`颜色表 ${c.id} 的查找表必须是 256 × 4 u8`);
    }
  }

  const needAcc = (layer: string, key: string, id: unknown, opts: {components?: number, count?: number, integer?: boolean, multipleOf?: number, optional?: boolean} = {}) => {
    if (id === undefined || id === null) { if (!opts.optional) bad(`图层 ${layer} 缺少 ${key}`); return undefined; }
    const a = typeof id === 'string' ? accessors.get(id) : undefined;
    if (!a) { bad(`图层 ${layer} 的 ${key} 引用了不存在的访问器 ${String(id)}`); return undefined; }
    const info = accessorInfo(a.type);
    if (!info) return undefined;
    if (opts.components !== undefined && a.components !== opts.components) bad(`图层 ${layer} 的 ${key} 应为 ${opts.components} 分量（${a.id} 为 ${a.components}）`);
    if (opts.integer && !info.integer) bad(`图层 ${layer} 的 ${key} 必须是整数类型`);
    if (opts.count !== undefined && a.count !== opts.count) bad(`图层 ${layer} 的 ${key} 数量应为 ${opts.count}（${a.id} 为 ${a.count}）`);
    if (opts.multipleOf && (a.count * a.components) % opts.multipleOf !== 0) bad(`图层 ${layer} 的 ${key} 数量必须是 ${opts.multipleOf} 的倍数`);
    return a;
  };
  const needMap = (layer: string, id: unknown, kind?: 'continuous' | 'categorical') => {
    if (id === undefined || id === ORIENTATION_HSL) return;
    const c = typeof id === 'string' ? colormaps.get(id) : undefined;
    if (!c) { bad(`图层 ${layer} 引用了不存在的颜色表 ${String(id)}`); return; }
    if (kind === 'continuous' && c.categorical) bad(`图层 ${layer} 需要连续颜色表（${c.id} 为分类颜色表）`);
    if (kind === 'categorical' && !c.categorical) bad(`图层 ${layer} 需要分类颜色表（${c.id} 为连续颜色表）`);
  };
  const checkAttributes = (layer: LayerSpec, points: number | undefined, cells: number | undefined) => {
    if (layer.attributes === undefined) return;
    if (!isObj(layer.attributes)) { bad(`图层 ${layer.id} 的 attributes 格式错误`); return; }
    for (const [name, attr] of Object.entries(layer.attributes)) {
      if (!isObj(attr)) { bad(`图层 ${layer.id} 的属性 ${name} 格式错误`); continue; }
      const cell = attr.association === 'cell';
      const count = cell ? cells : points;
      const a = needAcc(layer.id, `属性 ${name}`, attr.accessor);
      if (a && count !== undefined && a.count !== count) bad(`图层 ${layer.id} 的属性 ${name} 应有 ${count} 个${cell ? '单元' : '点'}值（实际 ${a.count}）`);
      if (attr.palette !== undefined) needMap(layer.id, attr.palette, 'categorical');
    }
  };
  const checkColor = (layer: LayerSpec, color: any) => {
    if (color === undefined) return;
    if (!isObj(color)) { bad(`图层 ${layer.id} 的颜色设置格式错误`); return; }
    if (color.by === 'attribute') {
      if (!own(layer.attributes, color.attribute)) bad(`图层 ${layer.id} 的着色属性 ${String(color.attribute)} 不存在`);
      needMap(layer.id, color.colormap);
    } else if (color.by === 'direction') {
      if (color.colormap !== undefined && color.colormap !== ORIENTATION_HSL) bad(`图层 ${layer.id}：方向着色仅支持 ${ORIENTATION_HSL}`);
      if (color.attribute !== undefined && !own(layer.attributes, color.attribute)) bad(`图层 ${layer.id} 的方向属性 ${String(color.attribute)} 不存在`);
    }
    if (color.range !== undefined && !isVec(color.range, 2)) bad(`图层 ${layer.id} 的颜色范围无效`);
  };

  const layerIds = new Set<string>();
  for (const layer of m.layers) {
    if (!isObj(layer) || !validId(layer.id)) { bad('图层 id 无效'); continue; }
    if (layerIds.has(layer.id)) bad(`图层 ${layer.id} 重复`);
    layerIds.add(layer.id);
    // Shown as text by the viewer (layer list, legends): wrong types would break rendering.
    if (layer.name !== undefined && layer.name !== null && typeof layer.name !== 'string') bad(`图层 ${layer.id} 的 name 必须是字符串`);
    if (!LAYER_TYPES.has(layer.type)) continue; // unknown types are skipped by clients (spec §1)
    if (layer.origin !== undefined && !isVec(layer.origin, 3)) bad(`图层 ${layer.id} 的 origin 必须是 3 个有限数`);
    const id = layer.id;
    const app = isObj(layer.appearance) ? layer.appearance : {};
    switch (layer.type) {
      case 'triangles': {
        const pos = needAcc(id, 'positions', layer.positions, {components: 3});
        const idx = needAcc(id, 'indices', layer.indices, {integer: true, multipleOf: 3});
        needAcc(id, 'normals', layer.normals, {components: 3, count: pos?.count, optional: true});
        checkAttributes(layer, pos?.count, idx ? idx.count * idx.components / 3 : undefined);
        checkColor(layer, app.color);
        for (const lod of Array.isArray(layer.lods) ? layer.lods : []) {
          const lp = needAcc(id, 'lod positions', lod?.positions, {components: 3});
          needAcc(id, 'lod indices', lod?.indices, {integer: true, multipleOf: 3});
          needAcc(id, 'lod normals', lod?.normals, {components: 3, count: lp?.count, optional: true});
        }
        break;
      }
      case 'slice_image': {
        const plane = layer.plane;
        if (!isObj(plane) || !isVec(plane.origin, 3) || !isVec(plane.u, 3) || !isVec(plane.v, 3)) bad(`图层 ${id} 的 plane 必须含有限的 origin/u/v`);
        const size = layer.size;
        if (!(Array.isArray(size) && size.length === 2 && size.every(n => isInt(n) && n >= 1))) { bad(`图层 ${id} 的 size 无效`); break; }
        if (!isObj(layer.attributes) || !Object.keys(layer.attributes).length) bad(`图层 ${id} 缺少采样属性`);
        checkAttributes(layer, size[0] * size[1], size[0] * size[1]);
        checkColor(layer, app.color);
        break;
      }
      case 'lines': {
        const pos = needAcc(id, 'positions', layer.positions, {components: 3});
        if (layer.mode !== 'segments' && layer.mode !== 'polylines') bad(`图层 ${id} 的 mode 无效`);
        const idx = needAcc(id, 'indices', layer.indices, {integer: true, multipleOf: layer.mode === 'segments' ? 2 : undefined});
        let cells: number | undefined;
        if (layer.mode === 'polylines') {
          const off = needAcc(id, 'offsets', layer.offsets, {integer: true, components: 1});
          if (off && off.count < 1) bad(`图层 ${id} 的 offsets 至少需要 1 项`);
          cells = off ? off.count - 1 : undefined;
          // Cell attributes may be per polyline or per segment; checked after loading.
          checkAttributes({...layer, attributes: Object.fromEntries(Object.entries(layer.attributes ?? {}).filter(([, a]) => (a as AttributeSpec)?.association !== 'cell'))}, pos?.count, cells);
        } else {
          cells = idx ? idx.count * idx.components / 2 : undefined;
          checkAttributes(layer, pos?.count, cells);
        }
        checkColor(layer, app.color);
        break;
      }
      case 'points': {
        const pos = needAcc(id, 'positions', layer.positions, {components: 3});
        needAcc(id, 'radii', layer.radii, {components: 1, count: pos?.count, optional: true});
        checkAttributes(layer, pos?.count, pos?.count);
        checkColor(layer, app.color);
        break;
      }
      case 'instances': {
        const pos = needAcc(id, 'positions', layer.positions, {components: 3});
        needAcc(id, 'directions', layer.directions, {components: 3, count: pos?.count});
        needAcc(id, 'scales', layer.scales, {components: 1, count: pos?.count, optional: true});
        if (!isObj(layer.glyph) || typeof layer.glyph.shape !== 'string') bad(`图层 ${id} 缺少 glyph.shape`);
        checkAttributes(layer, pos?.count, pos?.count);
        checkColor(layer, app.color);
        const scale = app.scale;
        if (scale !== undefined && (!isObj(scale) || !finite(scale.factor) || scale.factor <= 0)) bad(`图层 ${id} 的缩放设置无效`);
        if (scale?.by === 'attribute' && !own(layer.attributes, scale.attribute)) bad(`图层 ${id} 的缩放属性 ${String(scale.attribute)} 不存在`);
        break;
      }
      case 'volume': {
        const g = layer.grid;
        const dimsOk = isObj(g) && Array.isArray(g.dimensions) && g.dimensions.length === 3 && g.dimensions.every((n: unknown) => isInt(n) && n >= 1);
        if (!dimsOk) { bad(`图层 ${id} 的 grid.dimensions 无效`); break; }
        if (!isVec(g.origin, 3)) bad(`图层 ${id} 的 grid.origin 必须是 3 个有限数`);
        if (!isVec(g.spacing, 3) || g.spacing.some((s: number) => s <= 0)) bad(`图层 ${id} 的 grid.spacing 必须为正`);
        if (g.direction !== undefined && !isVec(g.direction, 9)) bad(`图层 ${id} 的 grid.direction 必须是 9 个有限数`);
        const [nx, ny, nz] = g.dimensions;
        needAcc(id, 'data', layer.data, {components: 1, count: nx * ny * nz});
        if (!isVec(layer.value_range, 2)) bad(`图层 ${id} 的 value_range 无效`);
        const tf = layer.transfer_function;
        if (!isObj(tf) || !isVec(tf.range, 2) || !Array.isArray(tf.opacity) || tf.opacity.length < 2 || !tf.opacity.every((p: unknown) => isVec(p, 2))) bad(`图层 ${id} 的 transfer_function 无效`);
        else needMap(id, tf.colormap); // a continuous LUT, or a categorical palette for label volumes (value ± 0.499)
        break;
      }
      case 'overlay': {
        if (!OVERLAY_KINDS.has(layer.kind)) break; // unknown overlay kinds are skipped
        if (layer.kind === 'scalar_bar') { needMap(id, layer.colormap ?? '', 'continuous'); if (!isVec(layer.range, 2)) bad(`图层 ${id} 的色标范围无效`); }
        if (layer.kind === 'legend') needMap(id, layer.colormap ?? '', 'categorical');
        if (layer.kind === 'text' && typeof layer.text !== 'string') bad(`图层 ${id} 缺少文本`);
        break;
      }
    }
  }
  if (problems.length) throw new PayloadError(problems);
  return m;
}

const isStr = (v: unknown) => v === undefined || v === null || typeof v === 'string';
/** Optional field: absent/null, or passing `ok` (the overlay code falls back to its defaults for absent fields). */
const opt = (v: unknown, ok: (v: any) => boolean) => v === undefined || v === null || ok(v);
const isColor = (v: unknown) => Array.isArray(v) && (v.length === 3 || v.length === 4) && v.every(finite);

/**
 * Presentation fields of an overlay (spec §6.7) with a wrong type. Such overlays are skipped with a warning
 * (overlays only explain the view); drawing them would break the HTML overlay layer.
 */
export function overlayProblems(layer: LayerSpec): string[] {
  const problems: string[] = [];
  const check = (ok: boolean, key: string, text: string) => { if (!ok) problems.push(`${key} ${text}`); };
  check(isStr(layer.title), 'title', '必须是字符串');
  check(isStr(layer.anchor), 'anchor', '必须是字符串');
  check(isStr(layer.source_layer), 'source_layer', '必须是字符串');
  check(opt(layer.offset_px, v => isVec(v, 2)), 'offset_px', '必须是 2 个有限数');
  check(opt(layer.size_px, v => (finite(v) && v > 0) || (isVec(v, 2) && v.every((x: number) => x > 0))), 'size_px', '必须是正数或 2 个正数');
  switch (layer.kind) {
    case 'scalar_bar':
      check(isStr(layer.unit), 'unit', '必须是字符串');
      check(isStr(layer.format), 'format', '必须是字符串');
      check(isStr(layer.orientation), 'orientation', '必须是字符串');
      check(opt(layer.label_count, isInt), 'label_count', '必须是整数');
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
      check(opt(layer.color, isColor), 'color', '必须是 3 或 4 个有限数');
      break;
    case 'axes_triad':
      check(opt(layer.labels, v => Array.isArray(v) && v.length === 3 && v.every((x: unknown) => typeof x === 'string')), 'labels', '必须是 3 个字符串');
      break;
  }
  return problems;
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

export function parseStkp(file: ArrayBuffer): StkpFile {
  const view = new DataView(file);
  const fail = (text: string): never => { throw new PayloadError([`.stkp 文件无效：${text}`]); };
  if (file.byteLength < 16) fail('文件过短');
  const magic = String.fromCharCode(view.getUint8(0), view.getUint8(1), view.getUint8(2), view.getUint8(3));
  if (magic !== 'STKP') fail('缺少 STKP 标记');
  if (view.getUint32(4, true) !== 2) fail(`版本 ${view.getUint32(4, true)} 不受支持`);
  const total = Number(view.getBigUint64(8, true));
  if (total > file.byteLength) fail(`文件被截断（${file.byteLength} < ${total}）`);
  const chunks: Uint8Array[] = [];
  const types: string[] = [];
  let offset = 16;
  while (offset < total) {
    if (offset + 16 > total) fail('分块头不完整');
    const length = Number(view.getBigUint64(offset, true));
    const type = String.fromCharCode(view.getUint8(offset + 8), view.getUint8(offset + 9), view.getUint8(offset + 10), view.getUint8(offset + 11));
    const start = offset + 16;
    if (start + length > total) fail(`分块 ${chunks.length} 超出文件长度`);
    chunks.push(new Uint8Array(file, start, length));
    types.push(type);
    offset = start + Math.ceil(length / 8) * 8;
  }
  if (!chunks.length || types[0] !== 'JSON') fail('第一个分块必须是 JSON 清单');
  types.slice(1).forEach((t, i) => { if (t !== 'BIN ') fail(`分块 ${i + 1} 类型 ${JSON.stringify(t)} 无效`); });
  let manifest: unknown;
  try { manifest = JSON.parse(new TextDecoder().decode(chunks[0])); } catch { fail('清单不是有效 JSON'); }
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
  /** Chunks of a .stkp file for `#k` buffers. */
  chunks?: Uint8Array[],
  signal?: AbortSignal,
}

export async function loadStkp(file: ArrayBuffer, options: Omit<LoadOptions, 'chunks'> = {}): Promise<LoadedPayload> {
  const {manifest, chunks} = parseStkp(file);
  return loadPayload(manifest, {...options, chunks});
}

export async function loadPayload(input: unknown, options: LoadOptions = {}): Promise<LoadedPayload> {
  const manifest = validateManifest(input);
  const warnings: string[] = [];
  const problems: string[] = [];
  const buffers = new Map<string, Uint8Array>();
  let hashSkipped = false;
  await Promise.all(manifest.buffers.map(async b => {
    let bytes: Uint8Array;
    if (b.uri.startsWith('#')) {
      const k = Number(b.uri.slice(1));
      const chunk = options.chunks?.[k];
      if (!chunk || k < 1) { problems.push(`缓冲区 ${b.id} 引用的分块 ${b.uri} 不存在`); return; }
      bytes = chunk;
      const actual = await sha256Hex(chunk);
      if (actual === null) hashSkipped = true;
      else if (actual !== b.sha256) { problems.push(`缓冲区 ${b.id} 的内容与 sha256 不符`); return; }
    } else {
      if (!options.fetchBlob) { problems.push(`缓冲区 ${b.id} 需要从控制服务读取，但未提供读取方式`); return; }
      const data = await cachedBlob(b.sha256, options.fetchBlob, options.signal);
      bytes = new Uint8Array(data);
      if ((globalThis as any).crypto?.subtle === undefined) hashSkipped = true;
    }
    if (bytes.byteLength !== b.byteLength) { problems.push(`缓冲区 ${b.id} 长度为 ${bytes.byteLength}，清单声明 ${b.byteLength}`); return; }
    buffers.set(b.id, bytes);
  }));
  if (problems.length) throw new PayloadError(problems);
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

  const layers: LayerSpec[] = [];
  for (const layer of manifest.layers) {
    if (!LAYER_TYPES.has(layer.type)) { warnings.push(`跳过未知图层类型 ${String(layer.type)}（${layer.id}）`); continue; }
    if (layer.type === 'overlay' && !OVERLAY_KINDS.has(layer.kind)) { warnings.push(`跳过未知叠加层 ${String(layer.kind)}（${layer.id}）`); continue; }
    if (layer.type === 'overlay') {
      const issues = overlayProblems(layer);
      if (issues.length) { warnings.push(`跳过叠加层 ${layer.id}：${issues.join('；')}`); continue; }
    }
    layers.push(layer);
  }
  const loaded: LoadedPayload = {
    manifest, layers, warnings,
    bytes: [...buffers.values()].reduce((n, b) => n + b.byteLength, 0),
    accessorSpec, accessor, floats,
    colormap: id => (id === undefined ? undefined : colormaps.get(id)),
  };
  validateData(loaded);
  return loaded;
}

/** Data-level checks of spec §10 that need the buffers: finite positions, index bounds, offsets. */
export function validateData(p: LoadedPayload) {
  const problems: string[] = [];
  const checkFinite = (layer: string, key: string, id: string | undefined) => {
    if (!id) return;
    const values = p.accessor(id);
    for (let i = 0; i < values.length; i++) if (!Number.isFinite(values[i])) { problems.push(`图层 ${layer} 的 ${key} 含非有限值（第 ${Math.floor(i / 3)} 项）`); return; }
  };
  const checkIndices = (layer: string, id: string | undefined, points: number) => {
    if (!id) return;
    const values = p.accessor(id);
    for (let i = 0; i < values.length; i++) if (values[i] < 0 || values[i] >= points) { problems.push(`图层 ${layer} 的索引 ${values[i]} 超出点数 ${points}`); return; }
  };
  for (const layer of p.layers) {
    const points = layer.positions ? p.accessorSpec(layer.positions).count : 0;
    switch (layer.type) {
      case 'triangles':
        checkFinite(layer.id, 'positions', layer.positions);
        checkIndices(layer.id, layer.indices, points);
        for (const lod of Array.isArray(layer.lods) ? layer.lods : []) {
          checkFinite(layer.id, 'lod positions', lod.positions);
          checkIndices(layer.id, lod.indices, p.accessorSpec(lod.positions).count);
        }
        break;
      case 'lines': {
        checkFinite(layer.id, 'positions', layer.positions);
        checkIndices(layer.id, layer.indices, points);
        if (layer.mode === 'polylines') {
          const offsets = p.accessor(layer.offsets);
          const total = p.accessor(layer.indices).length;
          for (let i = 0; i < offsets.length; i++) {
            if (offsets[i] > total || (i > 0 && offsets[i] < offsets[i - 1]) || offsets[i] < 0) { problems.push(`图层 ${layer.id} 的 offsets 无效`); break; }
          }
          const lines = offsets.length - 1;
          const segments = lines > 0 ? offsets[lines] - offsets[0] - lines : 0;
          for (const [name, attr] of Object.entries(layer.attributes ?? {})) {
            if (attr.association !== 'cell') continue;
            const count = p.accessorSpec(attr.accessor).count;
            if (count !== lines && count !== segments) problems.push(`图层 ${layer.id} 的属性 ${name} 应有 ${lines}（折线）或 ${segments}（线段）个单元值`);
          }
        }
        break;
      }
      case 'points': case 'instances':
        checkFinite(layer.id, 'positions', layer.positions);
        if (layer.type === 'instances') checkFinite(layer.id, 'directions', layer.directions);
        break;
    }
  }
  if (problems.length) throw new PayloadError(problems);
}

/** Physical origin of a layer's coordinates (spec §4). */
export function layerOrigin(p: LoadedPayload, layer: LayerSpec): Vec3 {
  return (layer.origin ?? p.manifest.render_origin) as Vec3;
}
