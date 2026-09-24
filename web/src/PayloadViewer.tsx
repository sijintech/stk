// stk.payload/2 view: one vtk.js render window that survives payload changes, so the camera is kept
// across steps (shifted when render_origin moves); overlays are HTML (Legend.tsx).
import {useEffect, useRef, useState} from 'react';
import vtkGenericRenderWindow from '@kitware/vtk.js/Rendering/Misc/GenericRenderWindow';
import vtkCellPicker from '@kitware/vtk.js/Rendering/Core/CellPicker';
import {buildScene, type BuiltScene} from './layers';
import {Overlays, type CameraBasis} from './Legend';
import type {LoadedPayload, ProbeRef} from './payload';

export interface PickInfo {layerId: string, layerName: string, probe?: ProbeRef}
const APP_BACKGROUND: [number, number, number] = [.086, .098, .129];
const PRESETS: Record<string, {u: number[], up: number[]}> = {
  '+x': {u: [1, 0, 0], up: [0, 0, 1]}, '-x': {u: [-1, 0, 0], up: [0, 0, 1]},
  '+y': {u: [0, 1, 0], up: [0, 0, 1]}, '-y': {u: [0, -1, 0], up: [0, 0, 1]},
  '+z': {u: [0, 0, 1], up: [0, 1, 0]}, '-z': {u: [0, 0, -1], up: [0, 1, 0]},
  iso: {u: [1 / Math.sqrt(3), -1 / Math.sqrt(3), 1 / Math.sqrt(3)], up: [0, 0, 1]},
};
const isVec3 = (v: unknown): v is number[] => Array.isArray(v) && v.length === 3 && v.every(Number.isFinite);
const cross = (a: number[], b: number[]) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const unit = (a: number[]) => { const l = Math.hypot(a[0], a[1], a[2]) || 1; return a.map(v => v / l); };

function backgroundOf(p: LoadedPayload): number[] {
  const bg = p.manifest.view?.background;
  return bg && Array.isArray(bg.color) && bg.color.length >= 3 && bg.color.every(Number.isFinite) ? bg.color.slice(0, 3) : APP_BACKGROUND;
}

function cameraBasis(camera: any): CameraBasis {
  const dop = camera.getDirectionOfProjection();
  const right = unit(cross(dop, camera.getViewUp()));
  return {right, up: cross(right, dop), back: dop.map((v: number) => -v)};
}

/** Changes only when the requested view changes (not with the scene bounds of a new step). */
function cameraSignature(p: LoadedPayload) {
  const cam = p.manifest.view?.camera ?? {};
  const numeric = isVec3(cam.position) && isVec3(cam.focal_point);
  return JSON.stringify(numeric ? [cam.position, cam.focal_point, cam.view_up, cam.projection] : [cam.preset ?? p.manifest.view?.preset ?? 'iso', cam.projection, cam.zoom]);
}

function sceneBounds(renderer: any, p: LoadedPayload): number[] {
  const b = p.manifest.bounds;
  if (Array.isArray(b) && isVec3(b[0]) && isVec3(b[1])) return [b[0][0], b[1][0], b[0][1], b[1][1], b[0][2], b[1][2]];
  const computed = renderer.computeVisiblePropBounds();
  return computed.every(Number.isFinite) && computed[0] <= computed[1] ? computed : [-1, 1, -1, 1, -1, 1];
}

/** Camera of the payload's stk.view/1 (physical coordinates) or a preset fitted to the bounds (graph spec §7). */
function applyViewCamera(renderer: any, p: LoadedPayload) {
  const camera = renderer.getActiveCamera();
  const cam = p.manifest.view?.camera ?? {};
  const o = p.manifest.render_origin;
  const b = sceneBounds(renderer, p);
  const center = [(b[0] + b[1]) / 2, (b[2] + b[3]) / 2, (b[4] + b[5]) / 2];
  const radius = 0.5 * Math.hypot(b[1] - b[0], b[3] - b[2], b[5] - b[4]) || 1;
  const angle = Number.isFinite(cam.view_angle_deg) && cam.view_angle_deg > 0 ? cam.view_angle_deg : 30;
  const zoom = Number.isFinite(cam.zoom) && cam.zoom > 0 ? cam.zoom : 1;
  camera.setViewAngle(angle);
  camera.setParallelProjection(cam.projection === 'parallel');
  if (isVec3(cam.position) && isVec3(cam.focal_point)) {
    const position = cam.position.map((v: number, i: number) => v - o[i]);
    const focal = cam.focal_point.map((v: number, i: number) => v - o[i]);
    const dop = unit(focal.map((v: number, i: number) => v - position[i]));
    let up = isVec3(cam.view_up) ? cam.view_up : [0, 0, 1];
    if (Math.hypot(...cross(unit(up), dop)) < 1e-6) up = Math.abs(dop[2]) > 0.99 ? [0, 1, 0] : [0, 0, 1];
    camera.setFocalPoint(focal[0], focal[1], focal[2]);
    camera.setPosition(position[0], position[1], position[2]);
    camera.setViewUp(up[0], up[1], up[2]);
  } else {
    const preset = PRESETS[cam.preset ?? p.manifest.view?.preset ?? 'iso'] ?? PRESETS.iso;
    const distance = radius / Math.sin((angle * Math.PI) / 360) / zoom;
    camera.setFocalPoint(center[0], center[1], center[2]);
    camera.setPosition(...center.map((v, i) => v + preset.u[i] * distance) as [number, number, number]);
    camera.setViewUp(preset.up[0], preset.up[1], preset.up[2]);
  }
  if (cam.projection === 'parallel') camera.setParallelScale(cam.parallel_scale > 0 ? cam.parallel_scale : radius / zoom);
  renderer.resetCameraClippingRange();
}

interface Context {view: any, renderer: any, picker: any, scene: BuiltScene | null, payload: LoadedPayload | null, origin: number[] | null, cameraKey: string | null}

export default function PayloadViewer({payload, onPick, resetKey}: {payload: LoadedPayload, onPick?: (position: number[], info: PickInfo) => void, resetKey?: string}) {
  const host = useRef<HTMLDivElement>(null);
  const pick = useRef(onPick);
  pick.current = onPick;
  const context = useRef<Context | null>(null);
  const toggled = useRef<Record<string, boolean>>({});
  const [basis, setBasis] = useState<CameraBasis | null>(null);
  const [shown, setShown] = useState<LoadedPayload | null>(null);
  const [hidden, setHidden] = useState<Record<string, boolean>>({});
  const [warnings, setWarnings] = useState<string[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    const element = host.current!;
    const view = vtkGenericRenderWindow.newInstance({background: APP_BACKGROUND, listenWindowResize: false});
    view.setContainer(element);
    const renderer = view.getRenderer();
    const interactor = view.getInteractor();
    const camera = renderer.getActiveCamera();
    const picker = vtkCellPicker.newInstance();
    picker.setPickFromList(true);
    picker.setTolerance(0.002); // surfaces and slices: no near-miss hits outside the cells
    let frame = 0;
    const cameraChanged = camera.onModified(() => {
      if (!frame) frame = requestAnimationFrame(() => { frame = 0; setBasis(cameraBasis(camera)); });
    });
    // A click (press and release without dragging) picks; dragging keeps rotating the camera.
    let press: {x: number, y: number} | null = null;
    const down = interactor.onLeftButtonPress((event: any) => { press = {x: event.position.x, y: event.position.y}; });
    const up = interactor.onLeftButtonRelease((event: any) => {
      const start = press;
      press = null;
      const c = context.current;
      if (!start || !c?.scene || !c.payload || Math.hypot(event.position.x - start.x, event.position.y - start.y) > 4) return;
      picker.pick([event.position.x, event.position.y, 0], renderer);
      if (picker.getCellId() < 0) return;
      const actor = picker.getActors()[0];
      const layer = c.scene.layers.find(l => l.prop === actor);
      if (!layer) return;
      // Physical = (layer.origin ?? render_origin) + position (spec §4), from the data-space intersection:
      // vtk.js' getPickPosition() is wrong for translated actors (it applies the inverse actor matrix twice).
      const origin = layer.spec.origin ?? c.payload.manifest.render_origin;
      pick.current?.(picker.getMapperPosition().map((v: number, i: number) => v + origin[i]), {layerId: layer.id, layerName: layer.name, probe: layer.probe});
    });
    const observer = new ResizeObserver(() => view.resize());
    observer.observe(element);
    context.current = {view, renderer, picker, scene: null, payload: null, origin: null, cameraKey: null};
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      cameraChanged.unsubscribe(); down.unsubscribe(); up.unsubscribe();
      context.current?.scene?.dispose();
      picker.delete();
      view.delete();
      context.current = null;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setError('');
    buildScene(payload).then(scene => {
      const c = context.current;
      if (cancelled || !c) { scene.dispose(); return; }
      const {renderer, picker, view} = c;
      // Swap in the new layers only once they are complete, so step scrubbing never shows an empty view.
      for (const layer of c.scene?.layers ?? []) if (layer.prop) layer.type === 'volume' ? renderer.removeVolume(layer.prop) : renderer.removeActor(layer.prop);
      picker.initializePickList();
      const visibility = payload.manifest.view?.visibility ?? {};
      const nextHidden: Record<string, boolean> = {};
      for (const layer of scene.layers) {
        nextHidden[layer.id] = toggled.current[layer.id] ?? (layer.spec.visible === false || visibility[layer.id] === false);
        if (!layer.prop) continue;
        layer.prop.setVisibility(!nextHidden[layer.id]);
        if (layer.type === 'volume') renderer.addVolume(layer.prop); else renderer.addActor(layer.prop);
        if (layer.pickable) picker.addPickList(layer.prop);
      }
      c.scene?.dispose();
      const background = backgroundOf(payload);
      renderer.setBackground(background[0], background[1], background[2]);
      const key = `${resetKey ?? ''}|${cameraSignature(payload)}`;
      if (key !== c.cameraKey || !c.origin) applyViewCamera(renderer, payload);
      else {
        const o = payload.manifest.render_origin;
        const shift = c.origin.map((v, i) => v - o[i]);
        if (shift.some(v => v !== 0)) renderer.getActiveCamera().translate(shift[0], shift[1], shift[2]);
        renderer.resetCameraClippingRange();
      }
      Object.assign(c, {scene, payload, origin: [...payload.manifest.render_origin], cameraKey: key});
      view.resize();
      setHidden(nextHidden);
      setWarnings(scene.warnings);
      setShown(payload);
      setBasis(cameraBasis(renderer.getActiveCamera()));
    }).catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)); });
    return () => { cancelled = true; };
  }, [payload, resetKey]);

  function toggle(id: string) {
    const c = context.current;
    const hide = !hidden[id];
    toggled.current[id] = hide;
    setHidden(h => ({...h, [id]: hide}));
    c?.scene?.layers.find(l => l.id === id)?.prop?.setVisibility(!hide);
    c?.view.getRenderWindow().render();
  }
  function resetCamera() {
    const c = context.current;
    if (!c?.payload) return;
    applyViewCamera(c.renderer, c.payload);
    c.view.getRenderWindow().render();
  }

  const background = shown ? backgroundOf(shown) : APP_BACKGROUND;
  const light = 0.2126 * background[0] + 0.7152 * background[1] + 0.0722 * background[2] > 0.5;
  const overlays = shown ? shown.layers.filter(l => l.type === 'overlay' && !hidden[l.id]) : [];
  const stats = shown?.manifest.stats;
  return <div className="payload-view">
    <div className="viewport v2" aria-label="科学三维视图">
      <div className="vtk-host" ref={host}/>
      {shown && <Overlays payload={shown} overlays={overlays} basis={basis} light={light}/>}
      {!shown && !error && <div className="empty"><span className="orbit">◎</span><p>正在构建三维图层…</p></div>}
      {error && <p className="viewer-error" role="alert">{error}</p>}
    </div>
    {shown && <div className="layer-list">
      <button className="quiet view-reset" onClick={resetCamera} title="恢复数据包给出的视角">复位视角</button>
      {shown.layers.map(l => <label key={l.id} className="chip"><input type="checkbox" checked={!hidden[l.id]} onChange={() => toggle(l.id)}/>{l.name || l.id}</label>)}
      <small className="muted">{[stats?.triangles ? `${stats.triangles.toLocaleString()} 三角形` : '', stats?.instances ? `${stats.instances.toLocaleString()} 箭头` : '',
        stats?.voxels ? `${stats.voxels.toLocaleString()} 体素` : '', `${(shown.bytes / 1024).toFixed(0)} KiB`, shown.manifest.source?.reduced ? '已按设备预算简化' : ''].filter(Boolean).join(' · ')}</small>
      {warnings.length > 0 && <details className="payload-warnings"><summary>{warnings.length} 条提示</summary><ul>{warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></details>}
    </div>}
  </div>;
}
