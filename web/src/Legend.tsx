// Screen-space overlays of stk.payload/2 (spec §6.7) drawn as HTML/canvas over the vtk.js view:
// scalar bar, categorical legend, orientation sphere (domain-classifiers.md §6.2), axes triad and text.
import {useEffect, useMemo, useRef, type CSSProperties} from 'react';
import {byte, cssColor, cssFloatColor, formatNumber, orientationHsl, resolveColormap} from './colormaps';
import type {LayerSpec, LoadedPayload} from './payload';

/** Camera axes in world coordinates: screen right, screen up, and towards the viewer. */
export interface CameraBasis {right: number[], up: number[], back: number[]}
const IDENTITY: CameraBasis = {right: [1, 0, 0], up: [0, 1, 0], back: [0, 0, 1]};
const ANCHORS = ['top_left', 'top', 'top_right', 'left', 'center', 'right', 'bottom_left', 'bottom', 'bottom_right'];
const DEFAULT_ANCHOR: Record<string, string> = {scalar_bar: 'right', legend: 'top_right', orientation_legend: 'bottom_right', axes_triad: 'bottom_left', text: 'top_left'};
const dot = (a: number[], b: number[]) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

const COLUMNS = {left: ['top_left', 'left', 'bottom_left'], center: ['top', 'center', 'bottom'], right: ['top_right', 'right', 'bottom_right']};
const ROWS = ['top', 'middle', 'bottom'];
const DEFAULT_OFFSET = 12;

/** Extra margin of an item whose offset_px exceeds the column inset (the column already sits 12 px inside). */
function itemMargin(column: string, row: number, offset?: number[]): CSSProperties {
  const [ox, oy] = Array.isArray(offset) && offset.length === 2 ? offset.map(v => Math.max(0, v - DEFAULT_OFFSET)) : [0, 0];
  const style: CSSProperties = {};
  if (column === 'left') style.marginLeft = ox; else if (column === 'right') style.marginRight = ox;
  if (row === 0) style.marginTop = oy; else if (row === 2) style.marginBottom = oy;
  return style;
}

const withUnit = (title: string | null | undefined, unit: string | null | undefined) =>
  [title, unit ? `[${unit}]` : ''].filter(Boolean).join(' ');

function ScalarBar({payload, spec}: {payload: LoadedPayload, spec: LayerSpec}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const cm = useMemo(() => resolveColormap(payload, spec.colormap), [payload, spec.colormap]);
  const vertical = spec.orientation !== 'horizontal';
  useEffect(() => {
    const el = canvas.current;
    if (!el || !cm || cm.kind !== 'continuous') return;
    el.width = vertical ? 1 : 256; el.height = vertical ? 256 : 1;
    const ctx = el.getContext('2d');
    if (!ctx) return;
    const image = ctx.createImageData(el.width, el.height);
    // One pixel per LUT entry, so each bin is drawn exactly (high values at the top).
    for (let i = 0; i < 256; i++) image.data.set(cm.lut.subarray(i * 4, i * 4 + 4), (vertical ? 255 - i : i) * 4);
    ctx.putImageData(image, 0, 0);
  }, [cm, vertical]);
  if (!cm || cm.kind !== 'continuous' || !Array.isArray(spec.range)) return null;
  const [lo, hi] = spec.range as number[];
  const count = Math.max(2, Math.min(20, spec.label_count ?? 5));
  const ticks = Array.from({length: count}, (_, k) => ({f: k / (count - 1), label: formatNumber(lo + ((hi - lo) * k) / (count - 1), spec.format ?? '.3g')}));
  const [w, h] = Array.isArray(spec.size_px) ? spec.size_px as number[] : vertical ? [28, 240] : [240, 28];
  const thickness = Math.max(8, Math.min(vertical ? w : h, 20));
  return <div className={`overlay-box scalar-bar ${vertical ? 'vertical' : 'horizontal'}`}>
    {(spec.title || spec.unit) && <div className="overlay-title">{withUnit(spec.title, spec.unit)}</div>}
    <div className="bar-body" style={vertical ? {height: h} : {width: `min(${w}px, 60cqw)`}}>
      <canvas ref={canvas} style={vertical ? {width: thickness, height: '100%'} : {height: thickness, width: '100%'}}/>
      <div className="ticks">{ticks.map(t => <span key={t.f} style={vertical ? {bottom: `${t.f * 100}%`} : {left: `${t.f * 100}%`}}>{t.label}</span>)}</div>
    </div>
  </div>;
}

function CategoricalLegend({payload, spec}: {payload: LoadedPayload, spec: LayerSpec}) {
  const cm = resolveColormap(payload, spec.colormap);
  if (!cm || cm.kind !== 'categorical') return null;
  const values: number[] = Array.isArray(spec.values) ? spec.values : cm.entries.map(e => e.value);
  const items = values.map(v => cm.entries.find(e => e.value === v) ?? {value: v, name: String(v), color: cm.unknown});
  return <div className="overlay-box legend-box">
    {spec.title && <div className="overlay-title">{spec.title}</div>}
    <ul style={{gridTemplateColumns: `repeat(${Math.max(1, Math.min(8, spec.columns ?? 1))}, auto)`}}>
      {items.map(item => <li key={item.value}><i style={{background: cssColor(item.color)}}/>{item.name}</li>)}
    </ul>
  </div>;
}

function canvasSize(spec: LayerSpec, fallback: number) {
  const size = Array.isArray(spec.size_px) ? Math.min(spec.size_px[0], spec.size_px[1]) : fallback;
  return Math.max(40, Math.min(size, 320));
}

function OrientationLegend({spec, basis}: {spec: LayerSpec, basis: CameraBasis}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const size = canvasSize(spec, 120);
  const [l0, l1] = Array.isArray(spec.lightness_range) ? spec.lightness_range as number[] : [0, 1];
  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext('2d');
    if (!el || !ctx) return;
    const ratio = window.devicePixelRatio || 1;
    const px = Math.round(size * ratio);
    el.width = el.height = px;
    const image = ctx.createImageData(px, px);
    const c = px / 2, R = px * 0.4;
    const {right, up, back} = basis;
    for (let y = 0; y < px; y++) for (let x = 0; x < px; x++) {
      const sx = (x + 0.5 - c) / R, sy = (c - y - 0.5) / R, d2 = sx * sx + sy * sy;
      const coverage = Math.min(1, Math.max(0, (1 - Math.sqrt(d2)) * R + 0.5));
      if (coverage <= 0) continue;
      const sz = Math.sqrt(Math.max(0, 1 - d2));
      // Surface normal n of the unit sphere as seen by the camera, coloured with orientation-hsl(n, M = 1).
      const n = [0, 1, 2].map(k => sx * right[k] + sy * up[k] + sz * back[k]);
      const [r, g, b] = orientationHsl(n[0], n[1], n[2], 1, l0, l1);
      const shade = 0.8 + 0.2 * sz;
      const o = (y * px + x) * 4;
      image.data[o] = byte(r * shade); image.data[o + 1] = byte(g * shade); image.data[o + 2] = byte(b * shade); image.data[o + 3] = byte(coverage);
    }
    ctx.putImageData(image, 0, 0);
    ctx.font = `${Math.round(10 * ratio)}px sans-serif`;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    [['x', [1, 0, 0]], ['y', [0, 1, 0]], ['z', [0, 0, 1]]].forEach(([label, axis]) => {
      const e = axis as number[];
      if (dot(e, back) < -0.3) return;
      ctx.fillStyle = 'rgba(128,128,128,.95)';
      ctx.fillText(label as string, c + dot(e, right) * R * 1.17, c - dot(e, up) * R * 1.17);
    });
  }, [basis, size, l0, l1]);
  return <div className="overlay-box orientation-legend">
    {spec.title && <div className="overlay-title">{spec.title}</div>}
    <canvas ref={canvas} style={{width: `min(${size}px, 30cqmin)`, aspectRatio: '1'}} aria-label="取向色球"/>
  </div>;
}

function AxesTriad({spec, basis}: {spec: LayerSpec, basis: CameraBasis}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const size = canvasSize(spec, 80);
  const labels: string[] = Array.isArray(spec.labels) && spec.labels.length === 3 ? spec.labels : ['x', 'y', 'z'];
  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext('2d');
    if (!el || !ctx) return;
    const ratio = window.devicePixelRatio || 1;
    const px = Math.round(size * ratio);
    el.width = el.height = px;
    ctx.clearRect(0, 0, px, px);
    const c = px / 2, L = px * 0.32;
    const axes = [[1, 0, 0], [0, 1, 0], [0, 0, 1]].map((e, i) => ({i, x: dot(e, basis.right), y: dot(e, basis.up), z: dot(e, basis.back)}));
    axes.sort((a, b) => a.z - b.z); // far axes first
    ctx.lineCap = 'round';
    ctx.font = `bold ${Math.round(11 * ratio)}px sans-serif`;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    for (const a of axes) {
      const colour = ['#e5484d', '#46a758', '#3e63dd'][a.i];
      ctx.strokeStyle = ctx.fillStyle = colour;
      ctx.lineWidth = 2.2 * ratio;
      ctx.beginPath(); ctx.moveTo(c, c); ctx.lineTo(c + a.x * L, c - a.y * L); ctx.stroke();
      ctx.fillText(labels[a.i], c + a.x * L * 1.3, c - a.y * L * 1.3);
    }
  }, [basis, size, labels.join('|')]);
  return <canvas className="axes-triad" ref={canvas} style={{width: `min(${size}px, 24cqmin)`, aspectRatio: '1'}} aria-label="坐标轴"/>;
}

function TextOverlay({spec}: {spec: LayerSpec}) {
  const style: CSSProperties = {fontSize: spec.font_size_px ?? 14};
  if (Array.isArray(spec.color)) style.color = cssFloatColor(spec.color);
  return <div className="overlay-text" style={style}>{spec.text}</div>;
}

/** Overlays in three columns (left, centre, right) of three rows (top, middle, bottom), so anchored items never overlap. */
export function Overlays({payload, overlays, basis, light}: {payload: LoadedPayload, overlays: LayerSpec[], basis: CameraBasis | null, light: boolean}) {
  const groups = new Map<string, LayerSpec[]>();
  for (const overlay of overlays) {
    const anchor = ANCHORS.includes(overlay.anchor) ? overlay.anchor : DEFAULT_ANCHOR[overlay.kind] ?? 'top_left';
    groups.set(anchor, [...(groups.get(anchor) ?? []), overlay]);
  }
  const b = basis ?? IDENTITY;
  const render = (item: LayerSpec) => {
    switch (item.kind) {
      case 'scalar_bar': return <ScalarBar payload={payload} spec={item}/>;
      case 'legend': return <CategoricalLegend payload={payload} spec={item}/>;
      case 'orientation_legend': return <OrientationLegend spec={item} basis={b}/>;
      case 'axes_triad': return <AxesTriad spec={item} basis={b}/>;
      case 'text': return <TextOverlay spec={item}/>;
      default: return null;
    }
  };
  return <div className={`overlays ${light ? 'on-light' : 'on-dark'}`}>
    {Object.entries(COLUMNS).map(([column, anchors]) => {
      const rows = anchors.map(anchor => groups.get(anchor) ?? []);
      if (!rows.some(r => r.length)) return null;
      return <div key={column} className={`overlay-col ${column}`}>
        {rows.map((items, row) => <div key={ROWS[row]} className={`overlay-slot ${ROWS[row]}`}>
          {items.map(item => <div key={item.id} className="overlay-item" style={itemMargin(column, row, item.offset_px)}>{render(item)}</div>)}
        </div>)}
      </div>;
    })}
  </div>;
}
