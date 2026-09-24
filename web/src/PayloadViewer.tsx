// stk.payload/2 view: one vtk.js render window that survives payload changes, so the camera is kept
// across steps (shifted when render_origin moves); overlays are HTML (Legend.tsx).
import {useEffect, useRef, useState} from 'react';
import vtkGenericRenderWindow from '@kitware/vtk.js/Rendering/Misc/GenericRenderWindow';
import vtkCellPicker from '@kitware/vtk.js/Rendering/Core/CellPicker';
import {buildScene, type BuiltScene} from './layers';
import {Overlays, type CameraBasis} from './Legend';
import {own, type LoadedPayload, type ProbeRef} from './payload';
import {cameraPose, cameraSignature, cross, payloadBounds, unit} from './camera';

export interface PickInfo {layerId: string, layerName: string, probe?: ProbeRef}
const APP_BACKGROUND: [number, number, number] = [.086, .098, .129];

function backgroundOf(p: LoadedPayload): number[] {
  const bg = p.manifest.view?.background;
  return bg && Array.isArray(bg.color) && bg.color.length >= 3 && bg.color.every(Number.isFinite) ? bg.color.slice(0, 3) : APP_BACKGROUND;
}

function cameraBasis(camera: any): CameraBasis {
  const dop = camera.getDirectionOfProjection();
  const right = unit(cross(dop, camera.getViewUp()));
  return {right, up: cross(right, dop), back: dop.map((v: number) => -v)};
}

/** Applies the payload's camera (camera.ts) to the vtk.js renderer. */
function applyViewCamera(renderer: any, p: LoadedPayload) {
  const camera = renderer.getActiveCamera();
  const pose = cameraPose(p, payloadBounds(p, () => renderer.computeVisiblePropBounds()));
  camera.setParallelProjection(pose.parallel);
  camera.setViewAngle(pose.viewAngle);
  camera.setFocalPoint(pose.focalPoint[0], pose.focalPoint[1], pose.focalPoint[2]);
  camera.setPosition(pose.position[0], pose.position[1], pose.position[2]);
  camera.setViewUp(pose.viewUp[0], pose.viewUp[1], pose.viewUp[2]);
  if (pose.parallel) camera.setParallelScale(pose.parallelScale);
  renderer.resetCameraClippingRange();
}

const count = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) && v > 0 ? v.toLocaleString() : '');

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
      const visibility = payload.manifest.view?.visibility;
      const nextHidden: Record<string, boolean> = {};
      for (const layer of scene.layers) {
        nextHidden[layer.id] = toggled.current[layer.id] ?? (layer.spec.visible === false || own(visibility, layer.id) === false);
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
      <small className="muted">{[count(stats?.triangles) && `${count(stats.triangles)} 三角形`, count(stats?.instances) && `${count(stats.instances)} 箭头`,
        count(stats?.voxels) && `${count(stats.voxels)} 体素`, `${(shown.bytes / 1024).toFixed(0)} KiB`, shown.manifest.source?.reduced === true ? '已按设备预算简化' : ''].filter(Boolean).join(' · ')}</small>
      {warnings.length > 0 && <details className="payload-warnings"><summary>{warnings.length} 条提示</summary><ul>{warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></details>}
    </div>}
  </div>;
}
