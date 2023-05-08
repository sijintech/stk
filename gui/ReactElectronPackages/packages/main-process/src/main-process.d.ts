interface AppOptions {
  loadURL: string;
  name: string;
  exe: string;
  exePath: string;
  version: string;
  homepage: string;
}

interface PreferenceValue {
  hide_basic: boolean;
  hide_material: boolean;
  hide_structure: boolean;
}

export type { AppOptions, PreferenceValue };
