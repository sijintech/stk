// Colour mapping for stk.payload/2 (spec §5) and the orientation colours of docs/specs/domain-classifiers.md §6.
// Colormaps travel in the payload as 256-entry RGBA8 LUTs or categorical palettes; nothing is hard-coded here
// except the function colormap stk:orientation-hsl and the generic stk:categorical fallback.
import {LABEL_FORMAT, own, type AttributeSpec, type ColorSpec, type LayerSpec, type LoadedPayload, type TypedArray} from './payload';

export const ORIENTATION_HSL = 'stk:orientation-hsl';
export type RGB = [number, number, number];

export interface ContinuousColormap {kind: 'continuous', id: string, name: string, lut: Uint8Array, nan: Uint8Array, below: Uint8Array, above: Uint8Array}
export interface CategoricalColormap {kind: 'categorical', id: string, name: string, entries: {value: number, name: string, color: Uint8Array}[],
  lookup: Map<number, Uint8Array>, unknown: Uint8Array}
export type Colormap = ContinuousColormap | CategoricalColormap;

/** 8-bit value of a colour component in [0, 1] (spec: floor(255·c + 0.5)). */
export const byte = (c: number) => Math.max(0, Math.min(255, Math.floor(255 * c + 0.5)));
export const rgba8 = (c: ArrayLike<number> | undefined, fallback: number[]): Uint8Array => {
  const v = c && c.length >= 3 ? c : fallback;
  return Uint8Array.of(byte(v[0]), byte(v[1]), byte(v[2]), byte(v.length > 3 ? v[3] : 1));
};

/** CSS Color 4 HSL → RGB, h in degrees, s and l in [0, 1] (domain-classifiers.md §6.1). */
export function hslToRgb(h: number, s: number, l: number): RGB {
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const hp = (((h % 360) + 360) % 360) / 60;
  const x = c * (1 - Math.abs((hp % 2) - 1));
  const [r, g, b] = hp < 1 ? [c, x, 0] : hp < 2 ? [x, c, 0] : hp < 3 ? [0, c, x] : hp < 4 ? [0, x, c] : hp < 5 ? [x, 0, c] : [c, 0, x];
  const m = l - c / 2;
  return [r + m, g + m, b + m];
}

/** stk:orientation-hsl (domain-classifiers.md §6.2): colour of vector p for maximum magnitude M. */
export function orientationHsl(px: number, py: number, pz: number, M: number, l0 = 0, l1 = 1): RGB {
  const m = Math.hypot(px, py, pz);
  const mxy = Math.hypot(px, py);
  if (!(M > 0) || m === 0 || !Number.isFinite(m)) return hslToRgb(0, 0, l0 + (l1 - l0) / 2);
  if (mxy < 1e-5 * M) return hslToRgb(0, 0, l0 + (l1 - l0) * Math.min(1, Math.max(0, (pz + M) / (2 * M))));
  const h = (Math.atan2(py, px) * 180) / Math.PI;
  return hslToRgb(h, Math.min(m / M, 1), l0 + (l1 - l0) * (pz / m + 1) / 2);
}

/** stk:categorical (domain-classifiers.md §6.5) for label fields without a palette. */
export function genericCategoryColor(v: number): RGB {
  if (v === 0) return [0.75, 0.75, 0.75];
  if (v === -1) return [1, 1, 1];
  if (v < -1 || !Number.isInteger(v)) return [0.5, 0.5, 0.5];
  const i = v - 1;
  return hslToRgb((i * 137.50776405003785) % 360, 0.65, [0.5, 0.38, 0.62][i % 3]);
}

const GREY = [0.5, 0.5, 0.5, 1];

export function resolveColormap(p: LoadedPayload, id: string | undefined): Colormap | null {
  const spec = p.colormap(id);
  if (!spec) return null;
  if (spec.categorical) {
    const entries = (spec.entries ?? []).map(e => ({value: e.value, name: e.name, color: rgba8(e.color, GREY)}));
    return {kind: 'categorical', id: spec.id, name: spec.name, entries, lookup: new Map(entries.map(e => [e.value, e.color])), unknown: rgba8(spec.unknown_color, GREY)};
  }
  const lut = p.accessor(spec.lut!) as Uint8Array;
  return {kind: 'continuous', id: spec.id, name: spec.name, lut, nan: rgba8(spec.nan_color, GREY),
    below: spec.below_color ? rgba8(spec.below_color, GREY) : lut.slice(0, 4), above: spec.above_color ? rgba8(spec.above_color, GREY) : lut.slice(1020, 1024)};
}

/** A grey ramp used when a payload names no continuous colormap (reported as a warning by callers). */
export function greyColormap(): ContinuousColormap {
  const lut = new Uint8Array(1024);
  for (let i = 0; i < 256; i++) lut.set([i, i, i, 255], i * 4);
  return {kind: 'continuous', id: 'grey', name: 'gray', lut, nan: rgba8(GREY, GREY), below: lut.slice(0, 4), above: lut.slice(1020)};
}

/**
 * Colour transfer function points [physical value, r, g, b] (spec §6.6, as the offscreen renderer): a
 * continuous LUT spread over `range` (bin centres), or for label volumes each categorical entry held
 * constant over value ± 0.499, so neighbouring labels never blend.
 */
export function volumeColorPoints(cm: Colormap | null, range: [number, number], layerId: string, warnings: string[]): [number, number, number, number][] {
  const points: [number, number, number, number][] = [];
  if (cm?.kind === 'categorical' && cm.entries.length) {
    for (const e of cm.entries) {
      const [r, g, b] = [e.color[0] / 255, e.color[1] / 255, e.color[2] / 255];
      points.push([e.value - 0.499, r, g, b], [e.value + 0.499, r, g, b]);
    }
    return points;
  }
  if (!cm || cm.kind !== 'continuous') { warnings.push(`体图层 ${layerId} 的颜色表无效，使用灰度`); cm = greyColormap(); }
  const [lo, hi] = range;
  const lut = cm.lut;
  // A degenerate range (hi <= lo) is one colour, LUT entry 128 (spec §6.6).
  if (!(hi > lo)) points.push([lo, lut[512] / 255, lut[513] / 255, lut[514] / 255]);
  else for (let i = 0; i < 256; i++) points.push([lo + ((i + 0.5) / 256) * (hi - lo), lut[i * 4] / 255, lut[i * 4 + 1] / 255, lut[i * 4 + 2] / 255]);
  return points;
}

/** LUT index of value v over [lo, hi] (spec §5): −1 below, 256 above, NaN → −2. */
export function lutIndex(v: number, lo: number, hi: number): number {
  if (Number.isNaN(v)) return -2;
  const t = hi === lo ? 0.5 : (v - lo) / (hi - lo);
  if (t < 0) return -1;
  if (t > 1) return 256;
  return Math.min(255, Math.floor(t * 256));
}

export function writeContinuous(cm: ContinuousColormap, v: number, lo: number, hi: number, out: Uint8Array, o: number) {
  const i = lutIndex(v, lo, hi);
  if (i === -2) out.set(cm.nan, o);
  else if (i === -1) out.set(cm.below, o);
  else if (i === 256) out.set(cm.above, o);
  else { out[o] = cm.lut[i * 4]; out[o + 1] = cm.lut[i * 4 + 1]; out[o + 2] = cm.lut[i * 4 + 2]; out[o + 3] = cm.lut[i * 4 + 3]; }
}

/** Scalar per tuple: the given component, or the magnitude (component "magnitude", or null on vectors). */
export function scalarValues(values: ArrayLike<number>, components: number, component: number | 'magnitude' | null | undefined): Float64Array {
  const n = Math.floor(values.length / components);
  const out = new Float64Array(n);
  const magnitude = component === 'magnitude' || ((component === null || component === undefined) && components > 1);
  const c = typeof component === 'number' ? Math.min(component, components - 1) : 0;
  for (let i = 0; i < n; i++) {
    if (!magnitude) { out[i] = values[i * components + c]; continue; }
    let s = 0;
    for (let k = 0; k < components; k++) { const x = values[i * components + k]; s += x * x; }
    out[i] = Math.sqrt(s);
  }
  return out;
}

export function finiteRange(values: ArrayLike<number>): [number, number] {
  let lo = Infinity, hi = -Infinity;
  for (let i = 0; i < values.length; i++) { const v = values[i]; if (Number.isFinite(v)) { if (v < lo) lo = v; if (v > hi) hi = v; } }
  return lo <= hi ? [lo, hi] : [0, 1];
}

export interface ColorResult {
  /** RGBA8 per tuple, or null for a solid colour. */
  colors: Uint8Array | null,
  solid: number[],
  categorical: boolean,
  nearest: boolean,
  range?: [number, number],
  warnings: string[],
}

/** Colours for `count` tuples of a layer per its colour spec (spec §5). */
export function layerColors(p: LoadedPayload, layer: LayerSpec, spec: ColorSpec | undefined, count: number, association: 'point' | 'cell', vectors?: {values: ArrayLike<number>, components: number}): ColorResult {
  const warnings: string[] = [];
  const solid = spec?.solid && spec.solid.length >= 3 ? spec.solid : [0.8, 0.8, 0.8];
  const none: ColorResult = {colors: null, solid, categorical: false, nearest: false, warnings};
  if (!spec || !spec.by || spec.by === 'solid') return none;
  if (spec.by === 'direction') {
    let source = vectors;
    if (spec.attribute) {
      const attr = own(layer.attributes, spec.attribute);
      if (attr) source = {values: p.floats(attr.accessor), components: p.accessorSpec(attr.accessor).components};
    }
    if (!source || source.components < 3) { warnings.push(`图层 ${layer.id} 缺少方向着色所需的三分量向量`); return none; }
    const {values, components} = source;
    let M = spec.max_magnitude ?? 0;
    if (!(M > 0)) for (let i = 0; i < count; i++) M = Math.max(M, Math.hypot(values[i * components], values[i * components + 1], values[i * components + 2]) || 0);
    const [l0, l1] = spec.lightness_range ?? [0, 1];
    const colors = new Uint8Array(count * 4);
    for (let i = 0; i < count; i++) {
      const [r, g, b] = orientationHsl(values[i * components], values[i * components + 1], values[i * components + 2], M, l0, l1);
      colors[i * 4] = byte(r); colors[i * 4 + 1] = byte(g); colors[i * 4 + 2] = byte(b); colors[i * 4 + 3] = 255;
    }
    return {colors, solid, categorical: false, nearest: false, warnings};
  }
  const name = spec.attribute ?? '';
  const attr: AttributeSpec | undefined = own(layer.attributes, name);
  if (!attr) { warnings.push(`图层 ${layer.id} 的着色属性 ${name} 不存在`); return none; }
  if ((attr.association ?? 'point') !== association) warnings.push(`图层 ${layer.id} 的属性 ${name} 关联方式与图层不符`);
  const accessor = p.accessorSpec(attr.accessor);
  const raw: TypedArray = p.accessor(attr.accessor);
  let cm = resolveColormap(p, spec.colormap ?? attr.palette);
  const categorical = attr.categorical === true || cm?.kind === 'categorical';
  const colors = new Uint8Array(count * 4);
  if (categorical) {
    const values = scalarValues(raw, accessor.components, typeof spec.component === 'number' ? spec.component : 0);
    const palette = cm?.kind === 'categorical' ? cm : null;
    if (!palette) warnings.push(`图层 ${layer.id} 的分类属性 ${name} 未附带调色板，使用 stk:categorical`);
    for (let i = 0; i < count; i++) {
      const v = values[i];
      const c = palette ? (palette.lookup.get(v) ?? palette.unknown) : rgba8(genericCategoryColor(v), GREY);
      colors.set(c, i * 4);
    }
    return {colors, solid, categorical: true, nearest: true, warnings};
  }
  if (!cm || cm.kind !== 'continuous') { warnings.push(`图层 ${layer.id} 未指定连续颜色表，使用灰度`); cm = greyColormap(); }
  const values = scalarValues(accessor.normalized ? p.floats(attr.accessor) : raw, accessor.components, spec.component);
  const scalarComponent = accessor.components === 1 || typeof spec.component === 'number';
  const hint = scalarComponent && accessor.min && accessor.max ? [accessor.min[typeof spec.component === 'number' ? spec.component : 0], accessor.max[typeof spec.component === 'number' ? spec.component : 0]] as [number, number] : undefined;
  const range = spec.range ?? attr.range ?? (hint && hint.every(Number.isFinite) ? hint : finiteRange(values));
  for (let i = 0; i < count; i++) writeContinuous(cm, values[i], range[0], range[1], colors, i * 4);
  return {colors, solid, categorical: false, nearest: spec.interpolate === 'nearest', range, warnings};
}

// ---------------------------------------------------------------------------------------------
// Scalar-bar labels (spec §6.7): the Python format-spec subset [sign][#][0][width][,][.precision][type], written by
// hand from the exact decimal expansion of the double, so ties round half to even exactly as Python's format()
// (and suan.render.payload.format_label, the desktop format_label) do; toFixed/toPrecision round ties away from
// zero instead.

interface LabelFormat {sign: string, alternate: boolean, zeroPad: boolean, width: number, grouping: boolean, precision: number, type: string}
/** |v| = 0.d1 d2 d3 … × 10^point; digits without trailing zeros ("0" for zero). */
interface Decimal {digits: string, point: number}

function parseLabelFormat(spec: string): LabelFormat | null {
  if (!LABEL_FORMAT.test(spec)) return null;
  const m = /^([+\- ]?)(#?)(0?)([0-9]*)(,?)(?:\.([0-9]+))?([eEfFgG%d]?)$/.exec(spec)!;
  return {sign: m[1] || '-', alternate: m[2] === '#', zeroPad: m[3] === '0', width: m[4] ? Number(m[4]) : 0,
    grouping: m[5] === ',', precision: m[6] !== undefined ? Number(m[6]) : -1, type: m[7]};
}

/** The exact decimal expansion of a finite double (its magnitude). */
function exactDecimal(value: number): Decimal {
  const v = Math.abs(value);
  if (v === 0) return {digits: '0', point: 1};
  const bits = new DataView(new ArrayBuffer(8));
  bits.setFloat64(0, v);
  const hi = bits.getUint32(0), lo = bits.getUint32(4);
  const biased = (hi >>> 20) & 0x7ff;
  let mantissa = (BigInt(hi & 0xfffff) << 32n) | BigInt(lo);
  let exponent = -1074;
  if (biased !== 0) { mantissa |= 1n << 52n; exponent = biased - 1075; }
  // v = mantissa · 2^exponent = mantissa · 5^−exponent / 10^−exponent for negative exponents.
  const text = exponent >= 0 ? (mantissa << BigInt(exponent)).toString() : (mantissa * 5n ** BigInt(-exponent)).toString();
  const point = text.length - (exponent >= 0 ? 0 : -exponent);
  return {digits: text.replace(/0+$/, '') || '0', point};
}

/** Keep the first `keep` digits (keep may be ≤ 0), rounding half to even; a carry adds a digit and moves the point. */
function roundDigits(d: Decimal, keep: number): Decimal {
  if (d.digits === '0') return {digits: '0'.repeat(Math.max(keep, 0)), point: d.point};
  if (keep >= d.digits.length) return {digits: d.digits + '0'.repeat(keep - d.digits.length), point: d.point};
  let up = false;
  if (keep >= 0) {
    const first = d.digits[keep];
    const rest = /[1-9]/.test(d.digits.slice(keep + 1));
    if (first > '5' || (first === '5' && rest)) up = true;
    else if (first === '5') up = (keep > 0 ? d.digits.charCodeAt(keep - 1) - 48 : 0) % 2 === 1;
  }
  const digits = keep > 0 ? d.digits.slice(0, keep).split('') : [];
  let point = d.point;
  if (up) {
    let i = digits.length - 1;
    while (i >= 0 && digits[i] === '9') digits[i--] = '0';
    if (i >= 0) digits[i] = String.fromCharCode(digits[i].charCodeAt(0) + 1);
    else { digits.unshift('1'); point++; }
  }
  return {digits: digits.join(''), point};
}

/** Fixed notation with `frac` fraction digits (no sign). */
function fixedText(d: Decimal, frac: number): string {
  const r = roundDigits(d, d.point + frac);
  let digits = r.digits, point = r.point;
  if (d.digits === '0') { point = 1; digits = '0'.repeat(frac + 1); }
  let integer: string, fraction: string;
  if (point <= 0) { integer = '0'; fraction = '0'.repeat(-point) + digits; }
  else {
    if (digits.length < point) digits += '0'.repeat(point - digits.length);
    integer = digits.slice(0, point);
    fraction = digits.slice(point);
  }
  fraction = (fraction + '0'.repeat(Math.max(0, frac - fraction.length))).slice(0, frac);
  integer = integer.replace(/^0+/, '') || '0';
  return frac > 0 ? `${integer}.${fraction}` : integer;
}

/** Scientific notation with `frac` mantissa fraction digits: [mantissa, exponent]. */
function scientificText(d: Decimal, frac: number): [string, number] {
  if (d.digits === '0') return [frac > 0 ? `0.${'0'.repeat(frac)}` : '0', 0];
  const r = roundDigits(d, frac + 1);
  return [r.digits.slice(0, 1) + (frac > 0 ? `.${r.digits.slice(1, 1 + frac)}` : ''), r.point - 1];
}

const exponentText = (e: number) => `${e < 0 ? '-' : '+'}${String(Math.abs(e)).padStart(2, '0')}`;
const stripZeros = (text: string) => (text.includes('.') ? text.replace(/0+$/, '').replace(/\.$/, '') : text);

/** Python repr() of a finite double's magnitude: shortest round-trip digits, fixed for 1e-4 ≤ |v| < 1e16. */
function pythonRepr(v: number): string {
  if (v === 0) return '0.0';
  const [m, e] = Math.abs(v).toExponential().split('e');
  const digits = m.replace('.', '');
  const exponent = Number(e);
  if (exponent < -4 || exponent >= 16) return `${digits[0]}${digits.length > 1 ? `.${digits.slice(1)}` : ''}e${exponentText(exponent)}`;
  const point = exponent + 1;
  if (point <= 0) return `0.${'0'.repeat(-point)}${digits}`;
  if (digits.length <= point) return `${digits}${'0'.repeat(point - digits.length)}.0`;
  return `${digits.slice(0, point)}.${digits.slice(point)}`;
}

function groupThousands(integer: string, minWidth: number): string {
  const out: string[] = [];
  let count = 0;
  for (let i = integer.length - 1; i >= 0; i--) {
    if (count && count % 3 === 0) out.push(',');
    out.push(integer[i]);
    count++;
  }
  while (out.length < minWidth) { // zero padding is grouped too; never start with a separator
    if (count % 3 === 0) out.push(',');
    out.push('0');
    count++;
  }
  return out.reverse().join('');
}

/** Sign, zero padding, grouping and width of a formatted magnitude (integer digits + the rest). */
function finish(f: LabelFormat, negative: boolean, integer: string, rest: string, numeric: boolean): string {
  const sign = negative ? '-' : f.sign === '+' ? '+' : f.sign === ' ' ? ' ' : '';
  if (f.zeroPad && numeric) {
    const minWidth = Math.max(0, f.width - sign.length - rest.length);
    return sign + (f.grouping ? groupThousands(integer, minWidth) : integer.padStart(minWidth, '0')) + rest;
  }
  const body = f.grouping && numeric ? groupThousands(integer, 0) : integer;
  if (f.zeroPad) return sign + '0'.repeat(Math.max(0, f.width - sign.length - body.length - rest.length)) + body + rest;
  return (sign + body + rest).padStart(f.width, ' ');
}

/** Python format(value, spec) for a spec of the subset (an integral value for 'd'). */
function formatPython(value: number, f: LabelFormat): string {
  const negative = value < 0 || Object.is(value, -0);
  const upper = f.type === 'E' || f.type === 'F' || f.type === 'G';
  if (!Number.isFinite(value)) {
    const text = Number.isNaN(value) ? 'nan' : 'inf';
    return finish(f, negative && !Number.isNaN(value), upper ? text.toUpperCase() : text, f.type === '%' ? '%' : '', false);
  }
  if (f.type === 'd') return finish(f, negative && value !== 0, fixedText(exactDecimal(value), 0), '', true);
  const v = f.type === '%' ? value * 100 : value;
  if (!Number.isFinite(v)) return finish(f, negative, 'inf', '%', false); // format(1e308, '%') == 'inf%'
  const d = exactDecimal(v);
  let text: string;
  if (f.type === 'f' || f.type === 'F' || f.type === '%') {
    const p = f.precision < 0 ? 6 : f.precision;
    text = fixedText(d, p) + (f.alternate && p === 0 ? '.' : '') + (f.type === '%' ? '%' : '');
  } else if (f.type === 'e' || f.type === 'E') {
    const p = f.precision < 0 ? 6 : f.precision;
    const [mantissa, exponent] = scientificText(d, p);
    text = mantissa + (f.alternate && p === 0 ? '.' : '') + (f.type === 'E' ? 'E' : 'e') + exponentText(exponent);
  } else if (f.type === 'g' || f.type === 'G' || f.precision >= 0) {
    // Round to p significant digits; fixed if -4 <= exp < p (no type: exp < p - 1, with a fraction digit).
    const p = Math.max(1, f.precision < 0 ? 6 : f.precision);
    let [mantissa, exponent] = scientificText(d, p - 1);
    if (d.digits === '0') exponent = 0;
    const none = f.type === '';
    if (exponent >= -4 && exponent < (none ? p - 1 : p)) {
      text = fixedText(d, Math.max(0, p - 1 - exponent));
      if (!f.alternate) text = stripZeros(text);
      else if (!text.includes('.')) text += '.';
      if (none && !text.includes('.')) text += '.0';
    } else {
      if (!f.alternate) mantissa = stripZeros(mantissa);
      else if (!mantissa.includes('.')) mantissa += '.';
      text = mantissa + (f.type === 'G' ? 'E' : 'e') + exponentText(exponent);
    }
  } else {
    text = pythonRepr(v); // no type, no precision: repr
    if (f.alternate && !text.includes('.') && text.includes('e')) text = text.replace('e', '.e');
  }
  const end = /^[0-9]*/.exec(text)![0].length;
  return finish(f, negative, text.slice(0, end), text.slice(end), true);
}

/** Python round(): to the nearest integer, ties to even. */
function roundHalfEven(v: number): number {
  const floor = Math.floor(v);
  const diff = v - floor;
  const r = diff > 0.5 || (diff === 0.5 && floor % 2 !== 0) ? floor + 1 : floor;
  return r === 0 ? 0 : r;
}

/**
 * A scalar-bar label (spec §6.7): Python format-spec semantics for the subset [sign][#][0][width][,][.precision][type].
 * Ties round half to even; 'd' formats the value rounded to the nearest integer (ties to even); a label that shows
 * zero never carries a minus sign; non-finite values print as inf/-inf/nan; other formats fall back to '.3g'.
 */
export function formatNumber(v: number, format = '.3g'): string {
  const f = (typeof format === 'string' ? parseLabelFormat(format) : null) ?? parseLabelFormat('.3g')!;
  const rounded = (x: number) => formatPython(f.type === 'd' && Number.isFinite(x) ? roundHalfEven(x) : x, f);
  const text = rounded(v);
  if (Number.isFinite(v) && (v < 0 || Object.is(v, -0)) && !/[1-9]/.test(text)) return rounded(-v);
  return text;
}

/** CSS colour of an RGBA8 tuple. */
export const cssColor = (c: ArrayLike<number>) => `rgba(${c[0]},${c[1]},${c[2]},${c.length > 3 ? (c[3] / 255).toFixed(3) : 1})`;
/** CSS colour of float RGB(A) components in [0, 1]. */
export const cssFloatColor = (c: ArrayLike<number>) => cssColor([byte(c[0]), byte(c[1]), byte(c[2]), byte(c.length > 3 ? c[3] : 1)]);
