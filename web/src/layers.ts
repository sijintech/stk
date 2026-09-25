// vtk.js objects for stk.payload/2 layers (spec §6). Colours are mapped on the client from the payload's
// LUTs/palettes (colormaps.ts); volumes are built by the lazily loaded volume.ts (vtk.js Volume profile).
import '@kitware/vtk.js/Rendering/Profiles/Geometry';
import '@kitware/vtk.js/Rendering/Profiles/Glyph';
import '@kitware/vtk.js/Rendering/OpenGL/SphereMapper';
import vtkPolyData from '@kitware/vtk.js/Common/DataModel/PolyData';
import vtkImageData from '@kitware/vtk.js/Common/DataModel/ImageData';
import vtkDataArray from '@kitware/vtk.js/Common/Core/DataArray';
import vtkMapper from '@kitware/vtk.js/Rendering/Core/Mapper';
import vtkActor from '@kitware/vtk.js/Rendering/Core/Actor';
import vtkTexture from '@kitware/vtk.js/Rendering/Core/Texture';
import vtkGlyph3DMapper from '@kitware/vtk.js/Rendering/Core/Glyph3DMapper';
import vtkSphereMapper from '@kitware/vtk.js/Rendering/Core/SphereMapper';
import vtkArrowSource from '@kitware/vtk.js/Filters/Sources/ArrowSource';
import vtkConeSource from '@kitware/vtk.js/Filters/Sources/ConeSource';
import vtkSphereSource from '@kitware/vtk.js/Filters/Sources/SphereSource';
import vtkCubeSource from '@kitware/vtk.js/Filters/Sources/CubeSource';
import vtkLineSource from '@kitware/vtk.js/Filters/Sources/LineSource';
import {layerColors, scalarValues, type ColorResult} from './colormaps';
import {own, probeOf, type LayerSpec, type LoadedPayload, type ProbeRef, type TypedArray, type Vec3} from './payload';

export interface BuiltLayer {
  id: string, name: string, type: string, spec: LayerSpec,
  /** vtkActor / vtkVolume, null for overlays. */
  prop: any,
  /** Picking is enabled on triangles and slice images (spec §4: physical = render_origin + pick). */
  pickable: boolean,
  probe?: ProbeRef,
}
export interface BuiltScene {layers: BuiltLayer[], warnings: string[], dispose(): void}

/** Collects vtk.js objects so a scene can be released at once. */
export class Trash {
  items: any[] = [];
  add<T>(item: T): T { this.items.push(item); return item; }
  dispose() { for (const item of this.items.reverse()) { try { (item as any)?.delete?.(); } catch { /* already released */ } } this.items = []; }
}

const dataArray = (trash: Trash, name: string, values: TypedArray, components: number) =>
  trash.add(vtkDataArray.newInstance({name, values, numberOfComponents: components}));

/** VTK cell array [n, i0, …] from a flat index array with fixed cell size. */
function cells(indices: ArrayLike<number>, size: number): Uint32Array {
  const n = Math.floor(indices.length / size);
  const out = new Uint32Array(n * (size + 1));
  for (let c = 0, o = 0; c < n; c++) {
    out[o++] = size;
    for (let k = 0; k < size; k++) out[o++] = indices[c * size + k];
  }
  return out;
}

/** Area-weighted smooth normals for triangles without a normals accessor. */
function smoothNormals(pos: Float32Array, idx: ArrayLike<number>): Float32Array {
  const n = new Float32Array(pos.length);
  for (let t = 0; t + 2 < idx.length; t += 3) {
    const a = idx[t] * 3, b = idx[t + 1] * 3, c = idx[t + 2] * 3;
    const ux = pos[b] - pos[a], uy = pos[b + 1] - pos[a + 1], uz = pos[b + 2] - pos[a + 2];
    const vx = pos[c] - pos[a], vy = pos[c + 1] - pos[a + 1], vz = pos[c + 2] - pos[a + 2];
    const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    for (const p of [a, b, c]) { n[p] += nx; n[p + 1] += ny; n[p + 2] += nz; }
  }
  for (let i = 0; i < n.length; i += 3) {
    const l = Math.hypot(n[i], n[i + 1], n[i + 2]) || 1;
    n[i] /= l; n[i + 1] /= l; n[i + 2] /= l;
  }
  return n;
}

function applyColors(trash: Trash, color: ColorResult, data: any, mapper: any, actor: any, association: 'point' | 'cell') {
  const property = actor.getProperty();
  if (!color.colors) {
    mapper.setScalarVisibility(false);
    property.setColor(color.solid[0], color.solid[1], color.solid[2]);
    return;
  }
  const scalars = dataArray(trash, 'stk_colors', color.colors, 4);
  (association === 'cell' ? data.getCellData() : data.getPointData()).setScalars(scalars);
  mapper.setScalarVisibility(true);
  mapper.setColorModeToDirectScalars();
  if (association === 'cell') mapper.setScalarModeToUseCellData(); else mapper.setScalarModeToUsePointData();
  mapper.setInterpolateScalarsBeforeMapping?.(false);
}

function solidOpacity(color: ColorResult, opacity: number | undefined) {
  const alpha = !color.colors && color.solid.length > 3 ? color.solid[3] : 1;
  return (opacity ?? 1) * alpha;
}

function placeActor(p: LoadedPayload, layer: LayerSpec, prop: any) {
  // Layers with their own absolute origin are shifted into the render_origin frame (spec §4).
  if (!layer.origin) return;
  const o = p.manifest.render_origin;
  prop.setPosition(layer.origin[0] - o[0], layer.origin[1] - o[1], layer.origin[2] - o[2]);
}

function buildTriangles(p: LoadedPayload, layer: LayerSpec, trash: Trash, warnings: string[]) {
  const pos = p.floats(layer.positions);
  const idx = p.accessor(layer.indices);
  const app = layer.appearance ?? {};
  const poly = trash.add(vtkPolyData.newInstance()) as any;
  poly.getPoints().setData(pos, 3);
  poly.getPolys().setData(cells(idx, 3));
  if (app.shading !== 'flat') {
    const normals = layer.normals ? p.floats(layer.normals) : smoothNormals(pos, idx);
    poly.getPointData().setNormals(dataArray(trash, 'Normals', normals, 3));
  }
  const mapper = trash.add(vtkMapper.newInstance()) as any;
  mapper.setInputData(poly);
  const actor = trash.add(vtkActor.newInstance()) as any;
  actor.setMapper(mapper);
  const association = own(layer.attributes, app.color?.attribute)?.association === 'cell' ? 'cell' : 'point';
  const color = layerColors(p, layer, app.color, association === 'cell' ? idx.length / 3 : pos.length / 3, association);
  warnings.push(...color.warnings);
  applyColors(trash, color, poly, mapper, actor, association);
  const property = actor.getProperty();
  property.setOpacity(solidOpacity(color, app.opacity));
  property.setLighting(app.lighting ?? true);
  if (app.shading === 'flat') property.setInterpolationToFlat();
  if (app.edges?.visible) {
    property.setEdgeVisibility(true);
    const e = app.edges.color ?? [0, 0, 0];
    property.setEdgeColor(e[0], e[1], e[2]);
    property.setLineWidth(app.edges.width_px ?? 1);
  }
  return actor;
}

function buildSliceImage(p: LoadedPayload, layer: LayerSpec, trash: Trash, warnings: string[]) {
  const [w, h] = layer.size as [number, number];
  const {origin: o, u, v} = layer.plane as {origin: Vec3, u: Vec3, v: Vec3};
  const app = layer.appearance ?? {};
  const poly = trash.add(vtkPolyData.newInstance()) as any;
  // The quad spans sample (0,0) … (w−1,h−1); texel centres sit on the samples (spec §6.2).
  const corners = [o, [o[0] + u[0], o[1] + u[1], o[2] + u[2]], [o[0] + u[0] + v[0], o[1] + u[1] + v[1], o[2] + u[2] + v[2]], [o[0] + v[0], o[1] + v[1], o[2] + v[2]]];
  poly.getPoints().setData(Float32Array.from(corners.flat()), 3);
  poly.getPolys().setData(Uint32Array.of(3, 0, 1, 2, 3, 0, 2, 3));
  const s0 = 0.5 / w, s1 = (w - 0.5) / w, t0 = 0.5 / h, t1 = (h - 0.5) / h;
  poly.getPointData().setTCoords(dataArray(trash, 'TCoords', Float32Array.of(s0, t0, s1, t0, s1, t1, s0, t1), 2));
  const mapper = trash.add(vtkMapper.newInstance()) as any;
  mapper.setInputData(poly);
  mapper.setScalarVisibility(false);
  const actor = trash.add(vtkActor.newInstance()) as any;
  actor.setMapper(mapper);
  const color = layerColors(p, layer, app.color, w * h, 'point');
  warnings.push(...color.warnings);
  const property = actor.getProperty();
  if (color.colors) {
    const image = trash.add(vtkImageData.newInstance()) as any;
    image.setDimensions(w, h, 1);
    image.getPointData().setScalars(dataArray(trash, 'texels', color.colors, 4));
    const texture = trash.add(vtkTexture.newInstance()) as any;
    texture.setInputData(image);
    texture.setInterpolate(!(color.nearest || color.categorical));
    texture.setEdgeClamp?.(true);
    actor.addTexture(texture);
    property.setColor(1, 1, 1);
  } else property.setColor(color.solid[0], color.solid[1], color.solid[2]);
  property.setOpacity(solidOpacity(color, app.opacity));
  property.setLighting(app.lighting ?? false);
  return actor;
}

function buildLines(p: LoadedPayload, layer: LayerSpec, trash: Trash, warnings: string[]) {
  const pos = p.floats(layer.positions);
  const idx = p.accessor(layer.indices);
  const app = layer.appearance ?? {};
  const poly = trash.add(vtkPolyData.newInstance()) as any;
  poly.getPoints().setData(pos, 3);
  const attr = own(layer.attributes, app.color?.attribute);
  const association = attr?.association === 'cell' ? 'cell' : 'point';
  let cellCount: number;
  if (layer.mode === 'polylines') {
    const offsets = p.accessor(layer.offsets);
    const lines = offsets.length - 1;
    // Cell attributes of polylines are per segment (spec §6.3): draw each segment as its own cell.
    const perSegment = association === 'cell' && app.color?.by === 'attribute' && !!attr;
    const out: number[] = [];
    for (let l = 0; l < lines; l++) {
      const a = offsets[l], b = offsets[l + 1];
      if (perSegment) for (let k = a; k + 1 < b; k++) out.push(2, idx[k], idx[k + 1]);
      else { out.push(b - a); for (let k = a; k < b; k++) out.push(idx[k]); }
    }
    poly.getLines().setData(Uint32Array.from(out));
    cellCount = perSegment ? out.length / 3 : lines;
  } else {
    poly.getLines().setData(cells(idx, 2));
    cellCount = idx.length / 2;
  }
  const mapper = trash.add(vtkMapper.newInstance()) as any;
  mapper.setInputData(poly);
  const actor = trash.add(vtkActor.newInstance()) as any;
  actor.setMapper(mapper);
  const color = layerColors(p, layer, app.color, association === 'cell' ? cellCount : pos.length / 3, association);
  warnings.push(...color.warnings);
  applyColors(trash, color, poly, mapper, actor, association);
  const property = actor.getProperty();
  property.setOpacity(solidOpacity(color, app.opacity));
  property.setLighting(app.lighting ?? false);
  property.setLineWidth(app.width_px ?? 1);
  return actor;
}

function buildPoints(p: LoadedPayload, layer: LayerSpec, trash: Trash, warnings: string[]) {
  const pos = p.floats(layer.positions);
  const n = pos.length / 3;
  const app = layer.appearance ?? {};
  const poly = trash.add(vtkPolyData.newInstance()) as any;
  poly.getPoints().setData(pos, 3);
  const spheres = app.render_as === 'spheres';
  let mapper: any;
  if (spheres) {
    mapper = trash.add(vtkSphereMapper.newInstance());
    mapper.setRadius(app.radius ?? 0.5);
    if (layer.radii) {
      poly.getPointData().addArray(dataArray(trash, 'radii', p.floats(layer.radii), 1));
      mapper.setScaleArray('radii');
    }
  } else {
    const verts = new Uint32Array(n * 2);
    for (let i = 0; i < n; i++) { verts[i * 2] = 1; verts[i * 2 + 1] = i; }
    poly.getVerts().setData(verts);
    mapper = trash.add(vtkMapper.newInstance());
  }
  mapper.setInputData(poly);
  const actor = trash.add(vtkActor.newInstance()) as any;
  actor.setMapper(mapper);
  const color = layerColors(p, layer, app.color, n, 'point');
  warnings.push(...color.warnings);
  applyColors(trash, color, poly, mapper, actor, 'point');
  const property = actor.getProperty();
  property.setOpacity(solidOpacity(color, app.opacity));
  if (!spheres) { property.setPointSize(app.size_px ?? 3); property.setLighting(false); }
  return actor;
}

/** Canonical glyph geometry (spec §6.5): unit length along +x, VTK source defaults. */
function glyphSource(trash: Trash, shape: string, resolution: number, center: boolean): any {
  let source: any;
  if (shape === 'cone') source = vtkConeSource.newInstance({height: 1, radius: 0.25, resolution, direction: [1, 0, 0]});
  // `resolution` longitudes and max(3, ⌊resolution / 2⌋ + 1) latitude rows (spec §6.5, as offscreen and desktop).
  else if (shape === 'sphere') source = vtkSphereSource.newInstance({radius: 0.5, thetaResolution: resolution, phiResolution: Math.max(3, Math.floor(resolution / 2) + 1)});
  else if (shape === 'cube') source = vtkCubeSource.newInstance({xLength: 1, yLength: 1, zLength: 1});
  else if (shape === 'line') source = vtkLineSource.newInstance({point1: [0, 0, 0], point2: [1, 0, 0]});
  else source = vtkArrowSource.newInstance({tipResolution: resolution, shaftResolution: resolution, tipRadius: 0.1, tipLength: 0.35, shaftRadius: 0.03});
  trash.add(source);
  const poly = source.getOutputData();
  if (shape !== 'sphere' && shape !== 'cube') {
    // vtk.js centres arrows and cones on the origin; the canonical glyph starts at x = 0.
    const points = poly.getPoints();
    const data = points.getData();
    const shift = -poly.getBounds()[0] - (center ? 0.5 : 0);
    for (let i = 0; i < data.length; i += 3) data[i] += shift;
    points.modified();
    poly.modified();
  }
  return poly;
}

function buildInstances(p: LoadedPayload, layer: LayerSpec, trash: Trash, warnings: string[]) {
  const pos = p.floats(layer.positions);
  const dir = p.floats(layer.directions);
  const n = pos.length / 3;
  const app = layer.appearance ?? {};
  const scale = app.scale ?? {by: 'uniform', factor: 1};
  const factor = scale.factor > 0 ? scale.factor : 1;
  const scales = layer.scales ? p.floats(layer.scales) : null;
  let attribute: Float64Array | null = null;
  if (!scales && scale.by === 'attribute') {
    const attr = own(layer.attributes, scale.attribute);
    if (attr) attribute = scalarValues(p.floats(attr.accessor), p.accessorSpec(attr.accessor).components, null);
    else warnings.push(`图层 ${layer.id} 的缩放属性 ${scale.attribute} 不存在`);
  }
  const color = layerColors(p, layer, app.color, n, 'point', {values: dir, components: 3});
  warnings.push(...color.warnings);
  // Instances with a zero or non-finite direction, or a non-finite scale, are not drawn (spec §6.5); |s| is drawn.
  const keep: number[] = [], sizes: number[] = [];
  for (let i = 0; i < n; i++) {
    const magnitude = Math.hypot(dir[i * 3], dir[i * 3 + 1], dir[i * 3 + 2]);
    const s = scales ? scales[i] : scale.by === 'magnitude' ? factor * magnitude : scale.by === 'attribute' && attribute ? factor * attribute[i] : factor;
    if (magnitude > 0 && Number.isFinite(magnitude) && Number.isFinite(s)) { keep.push(i); sizes.push(Math.abs(s)); }
  }
  const kPos = new Float32Array(keep.length * 3), kDir = new Float32Array(keep.length * 3), kScale = Float32Array.from(sizes);
  const kColor = color.colors ? new Uint8Array(keep.length * 4) : null;
  keep.forEach((i, j) => {
    kPos.set(pos.subarray(i * 3, i * 3 + 3), j * 3);
    kDir.set(dir.subarray(i * 3, i * 3 + 3), j * 3);
    if (kColor && color.colors) kColor.set(color.colors.subarray(i * 4, i * 4 + 4), j * 4);
  });
  const poly = trash.add(vtkPolyData.newInstance()) as any;
  poly.getPoints().setData(kPos, 3);
  poly.getPointData().addArray(dataArray(trash, 'stk_direction', kDir, 3));
  poly.getPointData().addArray(dataArray(trash, 'stk_scale', kScale, 1));
  const mapper = trash.add(vtkGlyph3DMapper.newInstance()) as any;
  mapper.setInputData(poly, 0);
  const glyph = layer.glyph ?? {};
  if (!['arrow', 'cone', 'sphere', 'line', 'cube'].includes(glyph.shape)) warnings.push(`图层 ${layer.id} 的箭头形状 ${glyph.shape} 未知，使用 arrow`);
  mapper.setInputData(glyphSource(trash, glyph.shape ?? 'arrow', glyph.resolution ?? 8, glyph.center === true), 1);
  mapper.setOrientationArray('stk_direction');
  mapper.setOrientationModeToDirection();
  mapper.setScaleArray('stk_scale');
  mapper.setScaleModeToScaleByMagnitude();
  mapper.setScaleFactor(1);
  const actor = trash.add(vtkActor.newInstance()) as any;
  actor.setMapper(mapper);
  applyColors(trash, {...color, colors: kColor}, poly, mapper, actor, 'point');
  const property = actor.getProperty();
  property.setOpacity(solidOpacity(color, app.opacity));
  property.setLighting(app.lighting ?? true);
  return actor;
}

/**
 * stk.view/1 lighting preset: `headlight` keeps the VTK default (diffuse only), `none` draws unlit colours,
 * `three_point` (the scene default) adds an ambient term so lit faces keep their legend colours readable.
 */
function applyLighting(prop: any, preset: string) {
  const property = prop.getProperty();
  if (preset === 'none') property.setLighting(false);
  else if (preset !== 'headlight' && property.getLighting()) { property.setAmbient(0.25); property.setDiffuse(0.75); }
}

/** Builds every layer of a payload; overlays are returned without a prop (drawn as HTML by Legend.tsx). */
export async function buildScene(p: LoadedPayload): Promise<BuiltScene> {
  const trash = new Trash();
  const warnings: string[] = [...p.warnings];
  const layers: BuiltLayer[] = [];
  const lighting = String(p.manifest.view?.lighting?.preset ?? 'three_point');
  try {
    for (const layer of p.layers) {
      let prop: any = null;
      switch (layer.type) {
        case 'triangles': prop = buildTriangles(p, layer, trash, warnings); break;
        case 'slice_image': prop = buildSliceImage(p, layer, trash, warnings); break;
        case 'lines': prop = buildLines(p, layer, trash, warnings); break;
        case 'points': prop = buildPoints(p, layer, trash, warnings); break;
        case 'instances': prop = buildInstances(p, layer, trash, warnings); break;
        case 'volume': prop = (await import('./volume')).buildVolume(p, layer, trash, warnings); break;
      }
      if (prop) { placeActor(p, layer, prop); if (layer.type !== 'volume') applyLighting(prop, lighting); }
      layers.push({id: layer.id, name: layer.name || layer.id, type: layer.type, spec: layer, prop,
        pickable: layer.type === 'triangles' || layer.type === 'slice_image', probe: probeOf(layer)});
    }
  } catch (error) {
    trash.dispose();
    throw error;
  }
  return {layers, warnings, dispose: () => trash.dispose()};
}
