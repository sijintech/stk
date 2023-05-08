import { app } from "electron";
import { MuproWindow } from "./window";

const appversion = `${app.getVersion()}`;
const appname = app.getName().split("-").join(" ");

const isMac = process.platform === "darwin";

// const MuproWindow = require("./window");
import { MuproMenu } from "./menu";
import type { AppOptions, PreferenceValue } from "./main-process";

if (process.env.NODE_ENV === "production") {
  console.log = () => {};
  console.error = () => {};
  console.debug = () => {};
}

export { MuproWindow, MuproMenu, isMac, appversion, appname, AppOptions };
