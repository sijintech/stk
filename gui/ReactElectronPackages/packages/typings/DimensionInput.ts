// export interface DimensionInputImport {
//     nx: [string],
//     ny: [string],
//     nz: [string],
//     dx: [string],
//     dy: [string],
//     dz: [string],
// }

export interface DimensionInputData {
  nx: string;
  ny: string;
  nz: string;
  dx: string;
  dy: string;
  dz: string;
}

export const defaultDimensionInput: DimensionInputData = {
  nx: "32",
  ny: "32",
  nz: "32",
  dx: "1e-7",
  dy: "1e-7",
  dz: "1e-7",
};
