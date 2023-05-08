// export interface OutputInputImport{
//     format: [string],
//     frequency: [string]
// }

export interface OutputInputData {
  format: string;
  frequency?: string;
}

export const defaultOutputInput: OutputInputData = {
  format: "vti",
};
