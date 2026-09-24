// Volume layers (spec §6.6). Loaded on demand so the vtk.js volume renderer is only fetched for payloads with volumes.
import '@kitware/vtk.js/Rendering/OpenGL/Volume';
import '@kitware/vtk.js/Rendering/OpenGL/VolumeMapper';
import vtkImageData from '@kitware/vtk.js/Common/DataModel/ImageData';
import vtkDataArray from '@kitware/vtk.js/Common/Core/DataArray';
import vtkVolume from '@kitware/vtk.js/Rendering/Core/Volume';
import vtkVolumeMapper from '@kitware/vtk.js/Rendering/Core/VolumeMapper';
import vtkPiecewiseFunction from '@kitware/vtk.js/Common/DataModel/PiecewiseFunction';
import vtkColorTransferFunction from '@kitware/vtk.js/Rendering/Core/ColorTransferFunction';
import {resolveColormap, volumeColorPoints} from './colormaps';
import type {Trash} from './layers';
import type {LayerSpec, LoadedPayload} from './payload';

export function buildVolume(p: LoadedPayload, layer: LayerSpec, trash: Trash, warnings: string[]) {
  const grid = layer.grid;
  const [nx, ny, nz] = grid.dimensions as number[];
  const spec = p.accessorSpec(layer.data);
  // u8/u16/f32 are uploaded as stored; other types are converted to float32.
  const values = ['u8', 'u16', 'f32'].includes(spec.type) && !spec.normalized ? p.accessor(layer.data) : p.floats(layer.data);
  const image = trash.add(vtkImageData.newInstance()) as any;
  image.setDimensions(nx, ny, nz);
  image.setOrigin(...(grid.origin as number[]));
  image.setSpacing(...(grid.spacing as number[]));
  // Payload direction is row-major (columns are the axis directions); vtk.js stores it column-major.
  if (Array.isArray(grid.direction)) { const d = grid.direction as number[]; image.setDirection([d[0], d[3], d[6], d[1], d[4], d[7], d[2], d[5], d[8]]); }
  image.getPointData().setScalars(trash.add(vtkDataArray.newInstance({name: 'values', values, numberOfComponents: 1})));

  // Transfer functions are given in physical values; the texture holds stored values.
  const scale = layer.value_scale ?? 1, offset = layer.value_offset ?? 0;
  const stored = (v: number) => (scale !== 0 ? (v - offset) / scale : 0);
  const tf = layer.transfer_function;
  const ctf = trash.add(vtkColorTransferFunction.newInstance()) as any;
  for (const [value, r, g, b] of volumeColorPoints(resolveColormap(p, tf.colormap), tf.range as [number, number], layer.id, warnings)) ctf.addRGBPoint(stored(value), r, g, b);
  const opacity = trash.add(vtkPiecewiseFunction.newInstance()) as any;
  for (const [value, alpha] of tf.opacity as [number, number][]) opacity.addPoint(stored(value), Math.max(0, Math.min(1, alpha)));

  const mapper = trash.add(vtkVolumeMapper.newInstance()) as any;
  mapper.setInputData(image);
  const minSpacing = Math.min(...(grid.spacing as number[]));
  mapper.setSampleDistance(minSpacing * 0.5);
  const volume = trash.add(vtkVolume.newInstance()) as any;
  volume.setMapper(mapper);
  const property = volume.getProperty();
  property.setRGBTransferFunction(0, ctf);
  property.setScalarOpacity(0, opacity);
  property.setScalarOpacityUnitDistance(0, minSpacing);
  if (layer.sampling === 'nearest') property.setInterpolationTypeToNearest(); else property.setInterpolationTypeToLinear();
  property.setShade(layer.shade === true);
  return volume;
}
