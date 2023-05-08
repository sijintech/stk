// const { BrowserWindow, app, dialog, ipcMain, screen } = require("electron");
import {
  app,
  BrowserWindow,
  screen,
  ipcMain,
  dialog,
  OpenDialogOptions,
} from "electron";
import * as fs from "fs";
import * as path from "path";
import url from "url";
import { EventEmitter } from "events";
// const path = require("path");
// const fs = require("fs");
// const url = require("url");
// const { EventEmitter } = require("events");
// const isDev = require("electron-is-dev");
import {
  nudgeWindow,
  startSimulation,
  getFilesFromDir,
  writeSecret,
  obtainImage,
  writeFile,
  writePreferences,
  writeInput,
  readCSV,
  readTextFile,
  obtainGIF,
  killSimulation,
  writeGIF,
  convertToString,
  readPreferences,
} from "./handler";

import * as chokidar from "chokidar";

// import { setInterval, clearInterval } from 'timers/promises';
// const {
//     nudgeWindow,
//     startSimulation,
//     fromDir,
//     writeSecret,
//     writePreferences,
//     readPreferences,
// } = require("./handler");

// import * as xmlParser from 'xml2js';
import fastXmlParser from "fast-xml-parser";
import { takeHeapSnapshot, windowsStore } from "process";
// import internal from 'stream';
// const xmlParser = require("xml2js");
// const log = require("electron-log");
import * as log from "electron-log";

import { AppOptions, PreferenceValue } from "./main-process";
// import { setInterval } from 'timers/promises';

const ICON_PATH = path.resolve(__dirname, "..", "static", "icon.png");
var nextId = 0;

class MuproWindow extends EventEmitter {
  //fields
  id: number;
  loadURL: string;
  name: string;
  exe: string;
  exePath: string;
  loadedPromise: Promise<number>;
  // resolveLoadedPromise:void;
  closedPromise: Promise<number>;
  // resolveClosedPromise:void;
  browserWindow: BrowserWindow;
  preferences: PreferenceValue;
  pid: number;
  // interval: NodeJS.Timer;
  fileWatcher: chokidar.FSWatcher;
  currentVTKOut: string;

  constructor(settings: AppOptions) {
    super();

    this.id = nextId++;
    this.loadURL = settings.loadURL;
    this.name = settings.name;
    this.exe = settings.exe;
    this.exePath = settings.exePath;
    this.pid = -1;
    // this.interval = setInterval(() => { console.log("1h passed") }, 1000 * 60 * 3600);
    this.currentVTKOut = "./*.vti";
    this.fileWatcher = chokidar.watch(this.currentVTKOut);
    this.loadedPromise = new Promise<number>((resolve) => {
      let resolveLoadedPromise = resolve(1);
    });
    this.closedPromise = new Promise<number>((resolve) => {
      let resolveClosedPromise = resolve(1);
    });

    const p = screen.getPrimaryDisplay().size;
    const options = {
      show: false,
      title: this.name,
      tabbingIdentifier: "mupro",
      width: p.width,
      height: p.height - 30,
      webPreferences: {
        nodeIntegration: true,
        contextIsolation: false,
      },
    };
    log.info("The titles is ", options.title, p);

    // Don't set icon on Windows so the exe's ico will be used as window and
    // taskbar's icon. See https://github.com/atom/atom/issues/4811 for more.

    this.browserWindow = new BrowserWindow(options);
    app.setName(this.name);

    this.handleEvents();

    if (app.isPackaged) {
      // win.loadFile(indexHtml)
      this.browserWindow.loadFile(this.loadURL);
    } else {
      // win.loadURL(url)
      // win.webContents.openDevTools()
      this.browserWindow.loadURL(this.loadURL);
    }

    // this.browserWindow.showSaveDialog = this.showSaveDialog.bind(this);
    this.browserWindow.once("ready-to-show", () => {
      this.browserWindow.show();
    });

    this.preferences = readPreferences(
      this.browserWindow,
      path.join(this.exePath, "preferences.json")
    );
  }

  handleEvents() {
    log.info("Inside the window handle event");
    ipcMain.handle("nudgeWindow", () => {
      console.log("nudge window induced");
      nudgeWindow(this.browserWindow);
    });

    ipcMain.handle("startSimulation", (event, fileLoc) => {
      let input_path = fileLoc;
      if (!fs.lstatSync(fileLoc).isDirectory()) {
        input_path = path.dirname(fileLoc);
      }
      this.pid = startSimulation(
        this.browserWindow,
        input_path,
        path.join(this.exePath, this.exe)
      );
      return this.pid;
    });

    ipcMain.handle("obtainImage", (event, ...args) => {
      return obtainImage(this.browserWindow);
    });

    ipcMain.handle("writeFile", (event, ...args) => {
      writeFile(args[0], args[1]);
    });

    ipcMain.handle("readFile", (event, ...args) => {
      console.log("READ file location", args);
      return readTextFile(path.join(...args));
    });

    ipcMain.handle("obtainGIF", (event, ...args) => {
      obtainGIF(this.browserWindow);
    });
    ipcMain.handle("writeGIF", (event, ...args) => {
      writeGIF(args[0]);
    });

    ipcMain.handle("readCSV", (event, ...args) => {
      readCSV(args[0]).then((result: object) => {
        return result;
      });
    });

    ipcMain.handle("writeInput", (event, ...args) => {
      log.info("Write input", args[0]);
      writeInput(args[0].fileLocation, args[0].input);
    });

    ipcMain.handle("writeSecret", (event, ...args) => {
      console.log("event", event);
      console.log("args", args);
      writeSecret(
        this.browserWindow,
        this.exePath,
        this.exe,
        args[0].user_register
      );
    });

    ipcMain.handle("writePreferences", (event, ...args) => {
      console.log("event", event);
      console.log("args", args);
      return writePreferences(
        this.browserWindow,
        path.join(this.exePath, "preferences.json"),
        args[0]
      );
    });

    ipcMain.handle("loadPreferences", (event, ...args) => {
      console.log("load preferences");
      return readPreferences(
        this.browserWindow,
        path.join(this.exePath, "preferences.json")
      );
    });

    ipcMain.handle("messageBox", (event, ...args) => {
      let value = dialog.showMessageBoxSync(this.browserWindow, {
        message: args[0],
      });
      return value;
    });

    ipcMain.handle("killSimulation", (event, ...args) => {
      killSimulation(this.pid);
    });

    ipcMain.handle("selectFile", async (event, ...args) => {
      let result = await dialog.showOpenDialog(this.browserWindow, {
        properties: ["createDirectory", "openFile", "openDirectory"],
        title: "Select File",
        defaultPath: "microstructure.in",
      });

      if (result.canceled) {
        log.info("Save Canceled");
        this.browserWindow.webContents.send(
          "console",
          "You choose no file to save"
        );
        return "Canceled, not ready";
      } else {
        console.log("callback fucn");
        let file = result.filePaths[0];
        console.log("directory", file, result);
        this.browserWindow.webContents.send(
          "console",
          "You select the file" + file
        );
        return file;
      }
    });

    ipcMain.handle("saveFile", async (event, ...args) => {
      let result = await dialog.showSaveDialog(this.browserWindow, {
        properties: ["createDirectory"],
        title: "Save File",
        defaultPath: "input.xml",
      });

      if (result.canceled) {
        log.info("Save Canceled");
        this.browserWindow.webContents.send(
          "console",
          "You choose no file to save"
        );
        return "Canceled, not ready";
      } else {
        console.log("callback fucn");
        let file = result.filePath!;
        console.log("directory", file);
        this.browserWindow.webContents.send(
          "console",
          "Output input.xml as " + file
        );
        // console.log("The files in list", fromDir(directory[0],'vti'));
        let directory = path.dirname(file);

        this.browserWindow.webContents.send(
          "fileList",
          directory,
          getFilesFromDir(directory, [".vti"])
        );

        this.fileWatcher.unwatch(this.currentVTKOut);
        // console.log("current out dir", this.currentVTKOut);
        this.fileWatcher.add(`${directory}/*.vti`);
        this.fileWatcher.on("all", (event, path) => {
          console.log("on change ", path, event);
          this.browserWindow.webContents.send(
            "fileList",
            directory,
            getFilesFromDir(directory, [".vti"])
          );
        });
        this.currentVTKOut = directory;
        // this.interval = setInterval(() => {
        //     this.browserWindow.webContents.send(
        //         "fileList",
        //         directory,
        //         getFilesFromDir(directory, [".vti"])
        //     );
        // }, 5000);

        // interval.unref();
        return file;
      }
    });
    // });

    //this.browserWindow.on("close", async (event) => {
    //  if (
    //    (!this.muproApplication.quitting ||
    //      this.muproApplication.quittingForUpdate) &&
    //    !this.unloading
    //  ) {
    //    event.preventDefault();
    //    this.unloading = true;
    //    this.muproApplication.saveCurrentWindowOptions(false);
    //    if (await this.prepareToUnload()) this.close();
    //  }
    //});

    //this.browserWindow.on("closed", () => {
    //  this.muproApplication.removeWindow(this);
    //  this.resolveClosedPromise();
    //});

    this.browserWindow.on("unresponsive", async () => {
      const result = await dialog.showMessageBox(this.browserWindow, {
        type: "warning",
        buttons: ["Force Close", "Keep Waiting"],
        cancelId: 1, // Canceling should be the least destructive action
        message: "MuPRO app is not responding",
        detail:
          "MuPRO app is not responding. Would you like to force close it or just keep waiting?",
      });
      if (result.response === 0) this.browserWindow.destroy();
    });

    this.browserWindow.webContents.on("crashed", async () => {
      // if (this.headless) {
      //     console.log("Renderer process crashed, exiting");
      //     this.muproApplication.exit(100);
      //     return;
      // }
      const result = await dialog.showMessageBox(this.browserWindow, {
        type: "warning",
        buttons: ["Close Window", "Reload", "Keep It Open"],
        cancelId: 2, // Canceling should be the least destructive action
        message: "The MuPRO app has crashed",
        detail: "Please report this issue to mesoscale-modeling@mupro.co",
      });

      switch (result.response) {
        case 0:
          this.browserWindow.destroy();
          break;
        case 1:
          this.browserWindow.reload();
          break;
      }
    });
  }

  handleImport() {
    log.info("running the import");
    this.promptForPath(
      "file",
      (directory) => {
        console.log("directory", directory[0]);
        // path.join(directory[0],"input.xml")
        fs.readFile(directory[0], (err, data) => {
          const parser = new fastXmlParser.XMLParser({
            ignoreAttributes: false,
          });
          let jsonObj = parser.parse(data);
          convertToString(jsonObj);
          console.log("import file", jsonObj);
          this.browserWindow.webContents.send("importFile", {
            location: directory[0],
            file: jsonObj,
          });

          // fastXmlParser.parseString(data, (err: NodeJS.ErrnoException | null, result: any) => {
          // });
        });
      },
      ""
    );
  }

  sendConsole(text: string) {
    log.info(text);
    this.browserWindow.webContents.send("console", text);
  }
  promptForPath(
    type: string,
    callback: (path: string[]) => void,
    path: string
  ) {
    log.info("prompt for path");
    const properties: Array<
      | "openFile"
      | "openDirectory"
      | "multiSelections"
      | "showHiddenFiles"
      | "createDirectory"
      | "promptToCreate"
      | "noResolveAliases"
      | "treatPackageAsDirectory"
      | "dontAddToRecent"
    > = (() => {
      switch (type) {
        case "file":
          return ["openFile"];
        case "folder":
          return ["openDirectory"];
        case "all":
          return ["openFile", "openDirectory"];
        default:
          throw new Error(`${type} is an invalid type for promptForPath`);
      }
    })();

    let openOptions: OpenDialogOptions = {
      properties: properties.concat(["createDirectory"]),
      title: (() => {
        switch (type) {
          case "file":
            return "Open File";
          case "folder":
            return "Open Folder";
          default:
            return "Open";
        }
      })(),
    };

    // File dialog defaults to project directory of currently active editor
    if (path) openOptions.defaultPath = path;
    console.log("prompt for path");
    dialog.showOpenDialog(this.browserWindow, openOptions).then((result) => {
      if (result.canceled) {
        log.info("Open Canceled");
        this.browserWindow.webContents.send(
          "console",
          "You choose no file to open"
        );
      } else {
        if (typeof callback === "function") {
          console.log("callback fucn");
          return callback(result.filePaths);
        }
      }
    });
  }

  getDimensions() {
    const [x, y] = Array.from(this.browserWindow.getPosition());
    const [width, height] = Array.from(this.browserWindow.getSize());
    return { x, y, width, height };
  }

  // showSaveDialog(options, callback) {
  //     options = Object.assign(
  //         {
  //             title: "Save File",
  //             defaultPath: this.projectRoots[0],
  //         },
  //         options
  //     );

  //     let promise = dialog.showSaveDialog(this.browserWindow, options);
  //     if (typeof callback === "function") {
  //         promise = promise.then(({ filePath, bookmark }) => {
  //             callback(filePath, bookmark);
  //         });
  //     }
  //     return promise;
  // }

  close() {
    clearInterval(this.interval);
    console.log("closing the window");
    return this.browserWindow.close();
    // process.exit();
  }

  focus() {
    return this.browserWindow.focus();
  }

  minimize() {
    return this.browserWindow.minimize();
  }

  maximize() {
    return this.browserWindow.maximize();
  }

  unmaximize() {
    return this.browserWindow.unmaximize();
  }

  restore() {
    return this.browserWindow.restore();
  }

  // setFullScreen(fullScreen) {
  //     return this.browserWindow.setFullScreen(fullScreen);
  // }

  // setAutoHideMenuBar(autoHideMenuBar) {
  //     return this.browserWindow.setAutoHideMenuBar(autoHideMenuBar);
  // }

  // handlesAtomCommands() {
  //     return !this.isSpecWindow() && this.isWebViewFocused();
  // }

  isFocused() {
    return this.browserWindow.isFocused();
  }

  isMaximized() {
    return this.browserWindow.isMaximized();
  }

  isMinimized() {
    return this.browserWindow.isMinimized();
  }

  // isWebViewFocused() {
  //     return this.browserWindow.isWebViewFocused();
  // }

  // reload() {
  //     this.loadedPromise = new Promise<number>((resolve) => {
  //         this.resolveLoadedPromise = resolve(1);
  //     });
  //     this.prepareToUnload().then((canUnload) => {
  //         if (canUnload) this.browserWindow.reload();
  //     });
  //     return this.loadedPromise;
  // }

  // toggleDevTools() {
  //     return this.browserWindow.toggleDevTools();
  // }

  // openDevTools() {
  //     return this.browserWindow.openDevTools();
  // }

  // closeDevTools() {
  //     return this.browserWindow.closeDevTools();
  // }

  // copy() {
  //     return this.browserWindow.copy();
  // }
}

export { MuproWindow };
