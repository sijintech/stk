// Parity vectors from the web viewer (web/src/payload.ts, colormaps.ts, camera.ts) for the desktop
// C++ viewer model. Node >= 23.6 runs the TypeScript sources directly (type stripping); the three
// modules are copied to a temporary directory with explicit ".ts" import specifiers.
//
//   node desktop/tests/unit/fixtures/make_web_vectors.mjs      (run make_fixtures.py first)
//
// Writes web_vectors.json next to this file.
import {mkdtempSync, readFileSync, writeFileSync, rmSync, readdirSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {dirname, join} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..', '..', '..');
const EXAMPLE = join(ROOT, 'docs', 'specs', 'examples', 'payload-v2');

const work = mkdtempSync(join(tmpdir(), 'stk-web-vectors-'));
for (const name of ['payload', 'colormaps', 'camera']) {
  const source = readFileSync(join(ROOT, 'web', 'src', `${name}.ts`), 'utf8').replace(/from '\.\/(payload|colormaps|camera)'/g, "from './$1.ts'");
  writeFileSync(join(work, `${name}.ts`), source);
}
const payloadMod = await import(pathToFileURL(join(work, 'payload.ts')).href);
const colormapsMod = await import(pathToFileURL(join(work, 'colormaps.ts')).href);
const cameraMod = await import(pathToFileURL(join(work, 'camera.ts')).href);
rmSync(work, {recursive: true, force: true});

const {loadPayload, loadStkp, clearBlobCache} = payloadMod;
const {lutIndex, formatNumber, orientationHsl, hslToRgb, genericCategoryColor, layerColors, volumeColorPoints, resolveColormap} = colormapsMod;
const {cameraPose, presetOf, cameraSignature, PRESETS} = cameraMod;

const num = v => (Number.isFinite(v) ? v : String(v));
const toArrayBuffer = buf => buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
const exampleFetch = async sha => toArrayBuffer(readFileSync(join(EXAMPLE, `${sha}.bin`)));
const hex = bytes => Buffer.from(bytes).toString('hex');

// -------------------------------------------------------------------------------------------------
// Colours of every drawable layer (layers.ts association/count rules).
function colourLayers(p) {
  const out = [];
  for (const layer of p.layers) {
    if (!['triangles', 'points', 'instances', 'slice_image', 'lines'].includes(layer.type)) continue;
    const app = layer.appearance ?? {};
    const attr = app.color?.attribute !== undefined ? layer.attributes?.[app.color.attribute] : undefined;
    const association = attr?.association === 'cell' ? 'cell' : 'point';
    let count;
    if (layer.type === 'slice_image') count = layer.size[0] * layer.size[1];
    else if (association === 'cell') count = p.accessor(layer.indices).length / (layer.type === 'triangles' ? 3 : 2);
    else count = p.accessorSpec(layer.positions).count;
    const vectors = layer.type === 'instances' ? {values: p.floats(layer.directions), components: 3} : undefined;
    const r = layerColors(p, layer, app.color, count, layer.type === 'slice_image' ? 'point' : association, vectors);
    out.push({layer: layer.id, association, count, colors: r.colors ? hex(r.colors) : null, solid: r.solid,
      categorical: r.categorical, nearest: r.nearest, range: r.range ?? null});
  }
  return out;
}

function volumes(p) {
  const out = [];
  for (const layer of p.layers) {
    if (layer.type !== 'volume') continue;
    const warnings = [];
    const points = volumeColorPoints(resolveColormap(p, layer.transfer_function.colormap), layer.transfer_function.range, layer.id, warnings);
    out.push({layer: layer.id, points});
  }
  return out;
}

const payloads = {};
clearBlobCache();
const example = await loadPayload(JSON.parse(readFileSync(join(EXAMPLE, 'manifest.json'), 'utf8')), {fetchBlob: exampleFetch});
payloads.example = {colors: colourLayers(example), volumes: volumes(example),
  camera: cameraPose(example, cameraMod.payloadBounds(example, () => [-1, 1, -1, 1, -1, 1])),
  preset: presetOf(example)};
for (const file of readdirSync(join(HERE, 'payload', 'scenes')).filter(f => f.endsWith('.stkp')).sort()) {
  const p = await loadStkp(toArrayBuffer(readFileSync(join(HERE, 'payload', 'scenes', file))));
  payloads[file.replace('.stkp', '')] = {colors: colourLayers(p), volumes: volumes(p),
    camera: cameraPose(p, cameraMod.payloadBounds(p, () => [-1, 1, -1, 1, -1, 1])), preset: presetOf(p)};
}

// -------------------------------------------------------------------------------------------------
// Cameras of synthetic views (the numeric/preset rules of camera.ts).
const views = [
  undefined,
  {schema: 'stk.view/1'},
  {schema: 'stk.view/1', camera: {preset: '+x'}},
  {schema: 'stk.view/1', camera: {preset: '-z', zoom: 2}},
  {schema: 'stk.view/1', preset: '+y', camera: {}},
  {schema: 'stk.view/1', camera: {preset: 'bogus'}},
  {schema: 'stk.view/1', camera: {preset: '', position: [1e6 + 10, -3, 7], focal_point: [1e6, -3, 7]}},
  {schema: 'stk.view/1', camera: {position: [1e6 + 10, -3, 7], focal_point: [1e6, -3, 7], zoom: 2}},
  {schema: 'stk.view/1', camera: {position: [1e6 + 10, -3, 7], focal_point: [1e6, -3, 7], zoom: 2, projection: 'parallel'}},
  {schema: 'stk.view/1', camera: {position: [0, 0, 10], focal_point: [0, 0, 0]}},
  {schema: 'stk.view/1', camera: {position: [0, 0.001, 10], focal_point: [0, 0, 0]}},
  {schema: 'stk.view/1', camera: {position: [0, 0, 10], focal_point: [0, 0, 0], view_up: [0, 0, 1]}},
  {schema: 'stk.view/1', camera: {position: [1, 2, 3], focal_point: [1, 2, 3]}},
  {schema: 'stk.view/1', camera: {preset: 'iso', view_up: [0, 1, 0], view_angle_deg: 45}},
  {schema: 'stk.view/1', camera: {preset: '+z', view_up: [0, 0, 5]}},
  {schema: 'stk.view/1', camera: {preset: 'iso', view_angle_deg: 200, zoom: -1, parallel_scale: 0}},
  {schema: 'stk.view/1', camera: {preset: 'iso', projection: 'parallel', parallel_scale: 7.5}},
  {schema: 'stk.view/1', camera: {preset: '+x', position: [5, 0, 0], focal_point: [0, 0, 0]}},
  {schema: 'stk.view/1', camera: {position: [5, 5, 5], focal_point: [0, 0, 0], view_up: [1, 1, 1]}},
  {schema: 'stk.view/1', camera: {position: [5, true, 5], focal_point: [0, 0, 0]}},
];
const boundsList = [[-1, 1, -1, 1, -1, 1], [0, 10, 0, 2, 0, 1], [-2, 2, -2, 2, -2, 2], [3, 3, 3, 3, 3, 3]];
const origins = [[0, 0, 0], [1e6, -3, 7]];
const cameras = [];
for (const view of views) for (const bounds of boundsList) for (const origin of origins) {
  const p = {manifest: {render_origin: origin, view}};
  cameras.push({view: view ?? null, bounds, origin, pose: cameraPose(p, bounds), preset: presetOf(p), signature: cameraSignature(p)});
}

// -------------------------------------------------------------------------------------------------
// Scalars.
const lut = [];
for (const [lo, hi] of [[0, 1], [-1, 1], [2, 2], [1, 0], [0, 1e-300], [-1e6, 1e6]]) {
  for (const v of [-1e300, -1, -1e-17, 0, 1e-17, 0.00390625, 0.0039062, 0.5, 0.99609375, 0.9999999, 1, 1.0000001, 2, Infinity, -Infinity, NaN, 0.25, 0.75, 1e6, -1e6]) {
    lut.push({v: num(v), lo, hi, index: lutIndex(v, lo, hi)});
  }
}
const formats = ['.3g', '.2f', '.1e', '.0%', 'd', '', '.3', '.0f', '.2e', '.4g', '.0g', 'g', 'e', 'f', '%', '+.3g', '08.3f', ',d', ' .2f ', '.21g', '.25f', '.30e', 'x'];
const values = [0, -0, 1, -1, 0.5, 1.5, 2.5, -2.5, 0.125, 0.375, 1234.5678, -1234.5678, 1e-5, 1.5e-5, 0.0001, 0.00012345, 123456, 1234567,
  1e16, 1e15, 9.995, 0.995, 99.95, 999.5, 1e21, 1e22, 1e-300, 5e-324, 1.7976931348623157e308, 0.1, 0.2, 0.3, 1 / 3, 2 / 3, 12345678.9, 100, 1e3,
  0.05, 0.015, 0.025, 1.005, 2.675, 1e100, 123.456, -0.0001, 7, 10, 0.9999, 99999.5, 3.14159265358979, -0.4, -0.5, 0.49999999999999994,
  Infinity, -Infinity, NaN];
const format = [];
for (const f of formats) for (const v of values) format.push({format: f, value: num(v), negative_zero: Object.is(v, -0), text: formatNumber(v, f)});
const orientation = [];
let seed = 12345;
const rand = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; };
for (let k = 0; k < 200; k++) {
  const p = [rand() * 4 - 2, rand() * 4 - 2, rand() * 4 - 2];
  if (k % 10 === 0) { p[0] = 0; p[1] = 0; }
  const M = [1, 2, 3.5, 0][k % 4];
  const l = k % 3 ? [0, 1] : [0.2, 0.8];
  orientation.push({p, M, l, rgb: orientationHsl(p[0], p[1], p[2], M, l[0], l[1])});
}
const hsl = [];
for (const h of [-30, 0, 59.9, 60, 180, 359.9, 720.5]) for (const s of [0, 0.65, 1]) for (const l of [0, 0.38, 0.5, 1]) hsl.push({hsl: [h, s, l], rgb: hslToRgb(h, s, l)});
const categorical = [];
for (let v = -3; v < 40; v++) categorical.push({v, rgb: genericCategoryColor(v)});
categorical.push({v: 2.5, rgb: genericCategoryColor(2.5)});

// -------------------------------------------------------------------------------------------------
// The web decoder's verdict on the payload cases of make_fixtures.py.
function applyPatch(m, patch) {
  const [op, path, value] = patch;
  if (op === 'set' && path.length === 0) return structuredClone(value);
  let target = m;
  for (const key of path.slice(0, -1)) target = target[key];
  const last = path[path.length - 1];
  if (op === 'set') target[last] = structuredClone(value);
  else if (op === 'delete') { if (Array.isArray(target)) target.splice(last, 1); else delete target[last]; }
  else if (op === 'append') target[last].push(structuredClone(value));
  return m;
}
const exampleManifest = JSON.parse(readFileSync(join(EXAMPLE, 'manifest.json'), 'utf8'));
const exampleStkp = readFileSync(join(EXAMPLE, 'example.stkp'));
const cases = JSON.parse(readFileSync(join(HERE, 'payload', 'cases.json'), 'utf8'));
const verdicts = [];
for (const c of cases) {
  let ok = true, message = '';
  try {
    if (c.kind === 'example') {
      let m = structuredClone(exampleManifest);
      for (const patch of c.patches) m = applyPatch(m, patch);
      await loadPayload(m, {fetchBlob: exampleFetch});
    } else if (c.kind === 'blobs') {
      await loadPayload(c.manifest, {fetchBlob: async sha => toArrayBuffer(Buffer.from(c.blobs[sha] ?? '', 'base64'))});
    } else {
      let bytes = Buffer.from(exampleStkp);
      for (const [at, h] of c.edits) Buffer.from(h, 'hex').copy(bytes, at);
      if (c.truncate !== null && c.truncate !== undefined) bytes = bytes.subarray(0, c.truncate);
      if (c.append) bytes = Buffer.concat([bytes, Buffer.from(c.append, 'hex')]);
      await loadStkp(toArrayBuffer(bytes));
    }
  } catch (error) {
    ok = false;
    message = error instanceof payloadMod.PayloadError ? error.problems.slice(0, 2).join('; ') : `CRASH ${error?.name}: ${error?.message}`;
  }
  verdicts.push({name: c.name, ok, message});
}

writeFileSync(join(HERE, 'web_vectors.json'), JSON.stringify({node: process.version, payloads, cameras, lut, format, orientation, hsl,
  categorical, presets: PRESETS, verdicts}) + '\n');
console.log(`wrote web_vectors.json (${cameras.length} cameras, ${format.length} formats, ${verdicts.length} payload verdicts)`);
