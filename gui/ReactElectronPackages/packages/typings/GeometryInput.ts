// export interface SlabInputImport {
//     type: ['slab'],
//     centerX: [string],
//     centerY: [string],
//     centerZ: [string],
//     normalX: [string],
//     normalY: [string],
//     normalZ: [string],
//     thickness: [string],
//     label: [string],
//     matrixLabel: [string],
// }

export interface SlabInputData {
  type: "slab";
  centerX: string;
  centerY: string;
  centerZ: string;
  normalX: string;
  normalY: string;
  normalZ: string;
  thickness: string;
  label: string;
  matrixLabel: string;
}

// export interface EllipsoidInputImport{
//     type: ["ellipsoid"],
//     centerX: [string],
//     centerY: [string],
//     centerZ: [string],
//     radiusX: [string],
//     radiusY: [string],
//     radiusZ: [string],
//     rotationX: [string],
//     rotationY: [string],
//     rotationZ: [string],
//     label: [string],
//     matrixLabel: [string],
// }

export interface EllipsoidInputData {
  type: "ellipsoid";
  centerX: string;
  centerY: string;
  centerZ: string;
  radiusX: string;
  radiusY: string;
  radiusZ: string;
  rotationX: string;
  rotationY: string;
  rotationZ: string;
  label: string;
  matrixLabel: string;
}

// export interface EllipsoidRandomInputImport{
//     type: ["ellipsoid_random"],
//     count: [string],
//     centerXMin: [string],
//     centerXMax: [string],
//     centerYMin: [string],
//     centerYMax: [string],
//     centerZMin: [string],
//     centerZMax: [string],
//     radiusXMin: [string],
//     radiusXMax: [string],
//     radiusYMin: [string],
//     radiusYMax: [string],
//     radiusZMin: [string],
//     radiusZMax: [string],
//     rotationXMin: [string],
//     rotationXMax: [string],
//     rotationYMin: [string],
//     rotationYMax: [string],
//     rotationZMin: [string],
//     rotationZMax: [string],
//     label: [string],
//     matrixLabel: [string],
// }

export interface EllipsoidRandomInputData {
  type: "ellipsoid_random";
  count: string;
  centerXMin: string;
  centerXMax: string;
  centerYMin: string;
  centerYMax: string;
  centerZMin: string;
  centerZMax: string;
  radiusXMin: string;
  radiusXMax: string;
  radiusYMin: string;
  radiusYMax: string;
  radiusZMin: string;
  radiusZMax: string;
  rotationXMin: string;
  rotationXMax: string;
  rotationYMin: string;
  rotationYMax: string;
  rotationZMin: string;
  rotationZMax: string;
  label: string;
  matrixLabel: string;
}

// export interface EllipsoidRandomScaleInputImport{
//     type: ["ellipsoid_random_scale"],
//     count: [string],
//     centerXMin: [string],
//     centerXMax: [string],
//     centerYMin: [string],
//     centerYMax: [string],
//     centerZMin: [string],
//     centerZMax: [string],
//     radiusX: [string],
//     radiusY: [string],
//     radiusZ: [string],
//     rotationXMin: [string],
//     rotationXMax: [string],
//     rotationYMin: [string],
//     rotationYMax: [string],
//     rotationZMin: [string],
//     rotationZMax: [string],
//     scaleMin: [string],
//     scaleMax: [string],
//     label: [string],
//     matrixLabel: [string],
// }

export interface EllipsoidRandomScaleInputData {
  type: "ellipsoid_random_scale";
  count: string;
  centerXMin: string;
  centerXMax: string;
  centerYMin: string;
  centerYMax: string;
  centerZMin: string;
  centerZMax: string;
  radiusX: string;
  radiusY: string;
  radiusZ: string;
  rotationXMin: string;
  rotationXMax: string;
  rotationYMin: string;
  rotationYMax: string;
  rotationZMin: string;
  rotationZMax: string;
  scaleMin: string;
  scaleMax: string;
  label: string;
  matrixLabel: string;
}

// export interface EllipsoidShellInputImport{
//     type: ["ellipsoid_shell"],
//     centerXOuter: [string],
//     centerXInner: [string],
//     centerYOuter: [string],
//     centerYInner: [string],
//     centerZOuter: [string],
//     centerZInner: [string],
//     radiusXOuter: [string],
//     radiusXInner: [string],
//     radiusYOuter: [string],
//     radiusYInner: [string],
//     radiusZOuter: [string],
//     radiusZInner: [string],
//     rotationXOuter: [string],
//     rotationXInner: [string],
//     rotationYOuter: [string],
//     rotationYInner: [string],
//     rotationZOuter: [string],
//     rotationZInner: [string],
//     scaleMin: [string],
//     scaleMax: [string],
//     label: [string],
//     labelInner: [string],
//     matrixLabel: [string],
// }

export interface EllipsoidShellInputData {
  type: "ellipsoid_shell";
  centerXOuter: string;
  centerXInner: string;
  centerYOuter: string;
  centerYInner: string;
  centerZOuter: string;
  centerZInner: string;
  radiusXOuter: string;
  radiusXInner: string;
  radiusYOuter: string;
  radiusYInner: string;
  radiusZOuter: string;
  radiusZInner: string;
  rotationXOuter: string;
  rotationXInner: string;
  rotationYOuter: string;
  rotationYInner: string;
  rotationZOuter: string;
  rotationZInner: string;
  scaleMin: string;
  scaleMax: string;
  label: string;
  labelInner: string;
  matrixLabel: string;
}

// export interface EllipsoidShellRandomInputImport{
//     type: ["ellipsoid_shell_random"],
//     count: [string],
//     centerXMin: [string],
//     centerXMax: [string],
//     centerYMin: [string],
//     centerYMax: [string],
//     centerZMin: [string],
//     centerZMax: [string],
//     radiusXMin: [string],
//     radiusXMax: [string],
//     radiusYMin: [string],
//     radiusYMax: [string],
//     radiusZMin: [string],
//     radiusZMax: [string],
//     rotationXMin: [string],
//     rotationXMax: [string],
//     rotationYMin: [string],
//     rotationYMax: [string],
//     rotationZMin: [string],
//     rotationZMax: [string],
//     thicknessMin: [string],
//     thicknessMax: [string],
//     label: [string],
//     labelInner: [string],
//     matrixLabel: [string],
// }

export interface EllipsoidShellRandomInputData {
  type: "ellipsoid_shell_random";
  count: string;
  centerXMin: string;
  centerXMax: string;
  centerYMin: string;
  centerYMax: string;
  centerZMin: string;
  centerZMax: string;
  radiusXMin: string;
  radiusXMax: string;
  radiusYMin: string;
  radiusYMax: string;
  radiusZMin: string;
  radiusZMax: string;
  rotationXMin: string;
  rotationXMax: string;
  rotationYMin: string;
  rotationYMax: string;
  rotationZMin: string;
  rotationZMax: string;
  thicknessMin: string;
  thicknessMax: string;
  label: string;
  labelInner: string;
  matrixLabel: string;
}

// export interface EllipsoidShellRandomScaleInputImport{
//     type: ["ellipsoid_shell_random_scale"],
//     count: [string],
//     centerXMin: [string],
//     centerXMax: [string],
//     centerYMin: [string],
//     centerYMax: [string],
//     centerZMin: [string],
//     centerZMax: [string],
//     radiusX: [string],
//     radiusY: [string],
//     radiusZ: [string],
//     rotationXMin: [string],
//     rotationXMax: [string],
//     rotationYMin: [string],
//     rotationYMax: [string],
//     rotationZMin: [string],
//     rotationZMax: [string],
//     thicknessMin: [string],
//     thicknessMax: [string],
//     scaleMin: [string],
//     scaleMax: [string],
//     label: [string],
//     labelInner: [string],
//     matrixLabel: [string],
// }

export interface EllipsoidShellRandomScaleInputData {
  type: "ellipsoid_shell_random_scale";
  count: string;
  centerXMin: string;
  centerXMax: string;
  centerYMin: string;
  centerYMax: string;
  centerZMin: string;
  centerZMax: string;
  radiusX: string;
  radiusY: string;
  radiusZ: string;
  rotationXMin: string;
  rotationXMax: string;
  rotationYMin: string;
  rotationYMax: string;
  rotationZMin: string;
  rotationZMax: string;
  thicknessMin: string;
  thicknessMax: string;
  scaleMin: string;
  scaleMax: string;
  label: string;
  labelInner: string;
  matrixLabel: string;
}

// export type GeometryInputImport = SlabInputImport|EllipsoidInputImport|EllipsoidRandomInputImport|EllipsoidRandomScaleInputImport|EllipsoidShellInputImport|EllipsoidShellRandomInputImport|EllipsoidShellRandomScaleInputImport;

export type GeometryInputData =
  | SlabInputData
  | EllipsoidInputData
  | EllipsoidRandomInputData
  | EllipsoidRandomScaleInputData
  | EllipsoidShellInputData
  | EllipsoidShellRandomInputData
  | EllipsoidShellRandomScaleInputData;

export const defaultGeometryInput: GeometryInputData = {
  type: "slab",
  centerX: "0",
  centerY: "0",
  centerZ: "0",
  normalX: "0",
  normalY: "0",
  normalZ: "0",
  thickness: "0",
  label: "0",
  matrixLabel: "0",
};
