import { app } from "electron";
import { MuproWindow } from "./src/window";
import {
  fixPhaseInterfaceFormat,
  fixStructureInterfaceFormat,
} from "./src/handler";
const appversion = `${app.getVersion()}`;
const appname = app.getName().split("-").join(" ");

const isMac = process.platform === "darwin";

// const MuproWindow = require("./window");
const MuproMenu = require("./menu");

module.exports = {
  MuproWindow,
  MuproMenu,
  isMac,
  appversion,
  appname,
  fixPhaseInterfaceFormat,
  fixStructureInterfaceFormat,
};
