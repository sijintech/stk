import type { GeometryInputData } from "./GeometryInput";

// export interface StructureInputXMLImport{
//     sourceType: ['xml'],
//     geometry: GeometryInputImport[],
//     matrixLabel: [string],
// }

// export interface StructureInputDATImport{
//     sourceType: ['vti'|'dat'],
//     dataType: ['continuous'|'discrete'],
//     keypoints: [{value:string[]}],
// }

export interface StructureInputXMLData {
  sourceType: "xml";
  geometry: GeometryInputData[];
  matrixLabel: string;
}

export type StructureInputDATData =
  | StructureInputDATDataContinuous
  | StructureInputDATDataDiscrete;
export interface StructureInputDATDataContinuous {
  sourceType: "vti" | "dat";
  dataType: "continuous";
  file: string;
  keypoints: { value: string[] };
}
export interface StructureInputDATDataDiscrete {
  sourceType: "vti" | "dat";
  dataType: "discrete";
  file: string;
}

export interface StructureInputDream3DData {
  file: string;
  sourceType: "dream3d";
}

export const defaultStructureDATInput: StructureInputDATData = {
  sourceType: "dat",
  dataType: "continuous",
  keypoints: { value: ["0.5"] },
  file: "microstructure.in",
};

import { defaultGeometryInput } from "./GeometryInput";
export const defaultStructureXMLInput: StructureInputXMLData = {
  sourceType: "xml",
  geometry: [defaultGeometryInput],
  matrixLabel: "0",
};

export function fixStructureInterfaceFormat(structure: any) {
  // check system external field, to be done by user
  // check system solver reference tensor, to be done by user
  if (structure.sourceType === "xml") {
    // check structure geometry
    if (!Array.isArray(structure.geometry)) {
      structure.geometry = [structure.geometry];
    }
  } else {
    // check structure keypoints
    if (structure.keypoints && !Array.isArray(structure.keypoints.value)) {
      structure.keypoints.value = [structure.keypoints.value];
    }
  }
}

// export type StructureInputImport = StructureInputXMLImport|StructureInputDATImport;
export type StructureInputData =
  | StructureInputXMLData
  | StructureInputDATData
  | StructureInputDream3DData;
