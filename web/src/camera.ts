// Camera of an stk.payload/2 view (stk.view/1, graph spec §7) as a plain pose, without vtk.js, so the rules are
// unit-testable: presets fitted to the bounds, numeric cameras in physical coordinates, zoom, and the signature
// that decides whether a new payload (e.g. the next step) resets the user's camera.
import type {LoadedPayload} from './payload';

export const PRESETS: Record<string, {u: number[], up: number[]}> = {
  '+x': {u: [1, 0, 0], up: [0, 0, 1]}, '-x': {u: [-1, 0, 0], up: [0, 0, 1]},
  '+y': {u: [0, 1, 0], up: [0, 0, 1]}, '-y': {u: [0, -1, 0], up: [0, 0, 1]},
  '+z': {u: [0, 0, 1], up: [0, 1, 0]}, '-z': {u: [0, 0, -1], up: [0, 1, 0]},
  iso: {u: [1 / Math.sqrt(3), -1 / Math.sqrt(3), 1 / Math.sqrt(3)], up: [0, 0, 1]},
};
export const isVec3 = (v: unknown): v is number[] => Array.isArray(v) && v.length === 3 && v.every(Number.isFinite);
export const cross = (a: number[], b: number[]) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
export const unit = (a: number[]) => { const l = Math.hypot(a[0], a[1], a[2]) || 1; return a.map(v => v / l); };
const isObj = (v: unknown): v is Record<string, any> => typeof v === 'object' && v !== null && !Array.isArray(v);
const positive = (v: unknown, fallback: number) => (typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : fallback);

/** The stk.view/1 camera of a payload (an empty object when absent or malformed). */
export function viewCamera(p: LoadedPayload): Record<string, any> {
  const view = p.manifest.view;
  return isObj(view) && isObj(view.camera) ? view.camera : {};
}

/** Camera preset name of a payload, or null for a numeric camera (one without a preset). */
export function presetOf(p: LoadedPayload): string | null {
  const cam = viewCamera(p);
  const preset = cam.preset ?? (isObj(p.manifest.view) ? p.manifest.view.preset : undefined);
  if (typeof preset === 'string' && preset) return preset;
  return isVec3(cam.position) && isVec3(cam.focal_point) ? null : 'iso';
}

/**
 * Changes only when the requested view changes, not with the scene bounds of a new step. Producers send a
 * preset camera already fitted to the step's bounds (numeric position with `preset` set), so the camera
 * counts as numeric only when no preset is given; a preset camera is compared by its preset.
 */
export function cameraSignature(p: LoadedPayload): string {
  const cam = viewCamera(p);
  const preset = presetOf(p);
  const common = [cam.projection ?? null, cam.view_angle_deg ?? null, cam.zoom ?? null, cam.view_up ?? null];
  return JSON.stringify(preset === null ? ['numeric', cam.position, cam.focal_point, ...common] : ['preset', preset, ...common]);
}

/** Bounds [xmin, xmax, ymin, ymax, zmin, zmax] relative to render_origin: the manifest's, else `fallback`. */
export function payloadBounds(p: LoadedPayload, fallback: () => number[]): number[] {
  const b = p.manifest.bounds;
  if (Array.isArray(b) && isVec3(b[0]) && isVec3(b[1])) return [b[0][0], b[1][0], b[0][1], b[1][1], b[0][2], b[1][2]];
  const computed = fallback();
  return computed.length === 6 && computed.every(Number.isFinite) && computed[0] <= computed[1] ? computed : [-1, 1, -1, 1, -1, 1];
}

export interface CameraPose {
  /** Positions relative to render_origin. */
  position: number[], focalPoint: number[], viewUp: number[],
  viewAngle: number, parallel: boolean, parallelScale: number,
}

/**
 * Pose of the payload's camera (as the offscreen renderer, suan/render/offscreen.py): the numeric camera when
 * given (a fitted preset has its zoom built in), else the preset fitted to the bounds (focal point = centre,
 * distance = r / sin(θ/2) / zoom). The zoom of a numeric camera without a preset narrows the view angle
 * (VTK Camera.Zoom); parallel projections use `parallel_scale`, else r / zoom.
 */
export function cameraPose(p: LoadedPayload, bounds: number[]): CameraPose {
  const cam = viewCamera(p);
  const o = p.manifest.render_origin;
  const b = bounds;
  const center = [(b[0] + b[1]) / 2, (b[2] + b[3]) / 2, (b[4] + b[5]) / 2];
  const radius = 0.5 * Math.hypot(b[1] - b[0], b[3] - b[2], b[5] - b[4]) || 1;
  const requested = positive(cam.view_angle_deg, 30);
  const angle = requested < 180 ? requested : 30;
  const zoom = positive(cam.zoom, 1);
  const parallel = cam.projection === 'parallel';
  const preset = presetOf(p);
  const parallelScale = positive(cam.parallel_scale, radius / zoom);
  if (isVec3(cam.position) && isVec3(cam.focal_point) && cam.position.some((v: number, i: number) => v !== cam.focal_point[i])) {
    const position = cam.position.map((v: number, i: number) => v - o[i]);
    const focalPoint = cam.focal_point.map((v: number, i: number) => v - o[i]);
    const dop = unit(focalPoint.map((v: number, i: number) => v - position[i]));
    let viewUp = isVec3(cam.view_up) ? cam.view_up : [0, 0, 1];
    if (Math.hypot(...cross(unit(viewUp), dop)) < 1e-6) viewUp = Math.abs(dop[2]) > 0.99 ? [0, 1, 0] : [0, 0, 1];
    const viewAngle = !parallel && preset === null ? angle / zoom : angle;
    return {position, focalPoint, viewUp, viewAngle, parallel, parallelScale};
  }
  const name = preset ?? 'iso';
  const fit = Object.prototype.hasOwnProperty.call(PRESETS, name) ? PRESETS[name] : PRESETS.iso;
  const distance = radius / Math.sin((angle * Math.PI) / 360) / zoom;
  let viewUp = fit.up;
  if (isVec3(cam.view_up) && Math.hypot(...cross(unit(cam.view_up), fit.u)) > 1e-6) viewUp = cam.view_up;
  return {position: center.map((v, i) => v + fit.u[i] * distance), focalPoint: center, viewUp, viewAngle: angle, parallel, parallelScale};
}
