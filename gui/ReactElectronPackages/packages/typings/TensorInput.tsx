import React from "node_modules/@types/react";

export interface TensorComponentData {
  value: string;
  index: string[];
}

// export interface TensorInputImport{
//     name: [string]
//     rank: [string]
//     component: [TensorComponent]
//     pointGroup: [string]
// }

export interface TensorInputData {
  name: string;
  rank: number;
  pointGroup: string;
  component: TensorComponentData[];
}

export const defaultTensorInput: TensorInputData = {
  name: "Default_Tensor",
  rank: 0,
  pointGroup: "custom",
  component: [{ index: ["1"], value: "0" }],
};

export function fixTensorInterfaceFormat(tensor: any) {
  // check material phase
  // check material phase tensor
  // check material phase tensor component
  if (!Array.isArray(tensor.component)) {
    tensor.component = [tensor.component];
  }
  tensor.component.forEach((component: any) => {
    if (!Array.isArray(component.index)) {
      component.index = [component.index];
    }
  });
}

export interface TensorType {
  name: string | React.ReactNode;
  id: string;
  rank: number;
}

export const defaultTensorType: TensorType = {
  name: "empty",
  rank: 0,
  id: "empty",
};
export const Permittivity: TensorType = {
  name: "Relative permittivity",
  rank: 2,
  id: "permittivity",
};
export const Ebreak: TensorType = {
  name: (
    <span>
      Breakdown Field (V&middot;m<sup>-1</sup>)
    </span>
  ),
  rank: 0,
  id: "Ebreak",
};
export const Diffusivity: TensorType = {
  name: (
    <span>
      Diffusivity &nbsp;(cm<sup>2</sup>&middot;s<sup>-1</sup>)
    </span>
  ),
  rank: 2,
  id: "diffusivity",
};
export const Stiffness: TensorType = {
  name: <span>Stiffness &nbsp;(GPa)</span>,
  rank: 4,
  id: "stiffness",
};
export const ElectricalConductivity: TensorType = {
  name: (
    <span>
      Electrical conductivity &nbsp;(W&middot;m<sup>-1</sup>&middot;k
      <sup>-1</sup>)
    </span>
  ),
  rank: 2,
  id: "electrical_conductivity",
};
export const Permeability: TensorType = {
  name: "Relative permeability",
  rank: 2,
  id: "permeability",
};
export const ThermalConductivity: TensorType = {
  name: (
    <span>
      Thermal conductivity &nbsp;(W&middot;m<sup>-1</sup>&middot;k<sup>-1</sup>)
    </span>
  ),
  rank: 2,
  id: "thermal_conductivity",
};
export const Piezoelectric: TensorType = {
  name: (
    <span>
      Piezoelectric coefficient &nbsp;(&mu;C&middot;N<sup>-1</sup>)
    </span>
  ),
  rank: 3,
  id: "piezoelectric",
};
export const Piezomagnetic: TensorType = {
  name: (
    <span>
      Piezomagnetic coefficient &nbsp;(T&middot;GPa<sup>-1</sup>)
    </span>
  ),
  rank: 3,
  id: "piezomagnetic",
};
