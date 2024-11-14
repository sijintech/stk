import type { TensorType } from "@mupro/typings/TensorInput";
import { Permittivity, Diffusivity, Stiffness, ElectricalConductivity, Permeability, ThermalConductivity, Piezoelectric, Piezomagnetic } from "@mupro/typings/TensorInput";

export const DielectricRefTensorList: TensorType[] = [Permittivity];
export const DiffusionRefTensorList: TensorType[] = [Diffusivity];
export const ElasticRefTensorList: TensorType[] = [Stiffness];
export const ElectricalRefTensorList: TensorType[] = [ElectricalConductivity];
export const MagneticRefTensorList: TensorType[] = [Permeability];
export const ThermalRefTensorList: TensorType[] = [ThermalConductivity];
export const PiezoelectricRefTensorList: TensorType[] = [Stiffness, Permittivity];
export const PiezomagneticRefTensorList: TensorType[] = [Stiffness, Permeability];

export const DielectricTensorList: TensorType[] = [Permittivity];
export const DiffusionTensorList: TensorType[] = [Diffusivity];
export const ElasticTensorList: TensorType[] = [Stiffness];
export const ElectricalTensorList: TensorType[] = [ElectricalConductivity];
export const MagneticTensorList: TensorType[] = [Permeability];
export const ThermalTensorList: TensorType[] = [ThermalConductivity];
export const PiezoelectricTensorList: TensorType[] = [Stiffness, Permittivity, Piezoelectric];
export const PiezomagneticTensorList: TensorType[] = [Stiffness, Permeability, Piezomagnetic];


export type SystemType = 'empty' | 'dielectric' | 'electrical' | 'magnetic' | 'thermal' | 'diffusion' | 'elastic' | 'piezoelectric' | 'piezomagnetic';



export interface VectorField {
  x: string,
  y: string,
  z: string,
}

// export interface VectorFieldImport {
//   x: [string],
//   y: [string],
//   z: [string],
// }

export interface TensorRank2 {
  tensor11: string,
  tensor22: string,
  tensor33: string,
  tensor23: string,
  tensor13: string,
  tensor12: string,
}

// export interface TensorRank2Import {
//   tensor11: [string],
//   tensor22: [string],
//   tensor33: [string],
//   tensor23: [string],
//   tensor13: [string],
//   tensor12: [string],
// }

// export interface ElectricFieldImport {
//   electricField: [VectorFieldImport]
// }

export interface ElectricField {
  electricField: VectorField
}

// export interface ConcentrationGradientFieldImport {
//   concentrationGradient: [VectorFieldImport]
// }

export interface ConcentrationGradientField {
  concentrationGradient: VectorField
}

// export interface MagneticFieldImport {
//   magneticField: [VectorFieldImport]
// }

export interface MagneticField {
  magneticField: VectorField
}

// export interface TemperatureGradientImport { temperatureGradient: [VectorFieldImport] }

export interface TemperatureGradientField { temperatureGradient: VectorField }

// export interface StressImport { type: ['stress'], stress: [TensorRank2Import] }
// export interface StrainImport { type: ['strain'], strain: [TensorRank2Import] }
export interface StressTensor { type: 'stress', stress: TensorRank2 }
export interface StrainTensor { type: 'strain', strain: TensorRank2 }

// export type ElasticImport = { elastic: [StressImport | StrainImport] };
export type ElasticField = { elastic: StressTensor | StrainTensor };
// export interface PiezoelectricImport { electricField: [VectorFieldImport], elastic: [StressImport | StrainImport] }
export interface PiezoelectricField { electricField: VectorField, elastic: StressTensor | StrainTensor }

// export interface PiezomagneticImport { magneticField: [VectorFieldImport], elastic: [StressImport | StrainImport] }
export interface PiezomagneticField { magneticField: VectorField, elastic: StressTensor | StrainTensor }


// export type ExternalFieldInputImport = ElectricFieldImport | ConcentrationGradientFieldImport | MagneticFieldImport | TemperatureGradientImport | PiezomagneticImport | ElasticImport;

export type ExternalField = ElectricField | ConcentrationGradientField | MagneticField | TemperatureGradientField | PiezomagneticField | PiezoelectricField | ElasticField;

import type { PhaseInputData } from "@mupro/typings/PhaseInput";
import { defaultPhaseInput } from "@mupro/typings/PhaseInput";

// export interface SystemImport {
//   type: [SystemType],
//   distribution: ['0' | '1'],
//   external?: [ExternalFieldInputImport],
//   solver: [{
//     ref: [PhaseInputImport],
//   }],
//   material: [{
//     phase: PhaseInputImport[],
//   }],
// }

export interface SystemData {
  type: SystemType,
  distribution: '0' | '1',
  external?: ExternalField,
  solver: {
    ref: PhaseInputData,
  },
  material: {
    phase: PhaseInputData[],
  },
}

export const defaultSystem: SystemData = {
  type: 'dielectric',
  distribution: '0',
  solver: {
    ref: defaultPhaseInput,
  },
  material: {
    phase: [defaultPhaseInput],
  },
}
