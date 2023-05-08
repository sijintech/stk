import {
  defaultTensorInput,
  fixTensorInterfaceFormat,
  TensorInputData,
} from "./TensorInput";

// interface PhaseInputImport{
//     label?:[string],
//     tensor: [TensorInputImport]
// }

export interface PhaseInputData {
  label?: string;
  tensor: TensorInputData[];
}

export const defaultPhaseInput: PhaseInputData = {
  label: "default_label",
  tensor: [defaultTensorInput],
};

export function fixPhaseInterfaceFormat(phase: any) {
  // check material phase
  // check material phase tensor
  // check material phase tensor component
  if (!Array.isArray(phase.tensor)) {
    phase.tensor = [phase.tensor];
  }
  phase.tensor.forEach((tensor: any) => {
    fixTensorInterfaceFormat(tensor);
  });
}
