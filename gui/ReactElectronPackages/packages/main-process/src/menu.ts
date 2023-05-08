// const { app, Menu } = require("electron");
import { app, Menu, MenuItem, MenuItemConstructorOptions } from "electron";
const isMac = process.platform === "darwin";
// const _ = require("underscore-plus");
// import * as _ from "lodash";
import { checkForUpdates } from "./updater";
import * as fs from "fs";
import * as path from "path";
// const xmlParser = require("xml2js");
// import * as xmlParser from 'xml2js';
import fastXmlParser from "fast-xml-parser";
import { convertToString } from "./handler";
// const { dir } = require("console");
import { AppOptions } from "./main-process";
import { MuproWindow } from "./window";
import { getFilesFromDir } from "./handler";

class MuproMenu {
  version: string;
  homepage: string;
  exePath: string;
  name: string;
  activeTemplate: MenuItemConstructorOptions[];
  constructor(options: AppOptions, window: MuproWindow) {
    this.version = options.version;
    // this.feedURL = options.feedURL;
    this.homepage = options.homepage;
    this.exePath = options.exePath;
    this.name = options.name;
    // this.autoUpdateManager = application.autoUpdateManager;
    this.activeTemplate = this.getDefaultTemplate(window);
    // this.setActiveTemplate(this.getDefaultTemplate(window));
    Menu.setApplicationMenu(Menu.buildFromTemplate(this.activeTemplate));
  }
  // setActiveTemplate(template: MenuItemConstructorOptions[]) {
  //     if (!_.isEqual(template, this.activeTemplate)) {
  //         this.activeTemplate = template;
  //         Menu.setApplicationMenu(Menu.buildFromTemplate(_.cloneDeep(template)));
  //     }
  // }

  getExampleMenu(): MenuItemConstructorOptions[] {
    let out: MenuItemConstructorOptions[] = [];
    let directory = "";
    if (app.isPackaged) {
      directory = path.join(this.exePath, "examples");
    } else {
      directory = path.join(this.exePath, "..", "examples");
    }
    console.log("get example menu", directory);
    // let example_path = "";
    if (fs.existsSync(directory)) {
      // let files = fs.readdirSync(directory);
      let files = getFilesFromDir(directory, [".xml"]);
      // , (err, files) => {
      //     if (err) console.log("Unable to read examples directory");
      files.forEach((example) => {
        let example_path = path.join(directory, example);

        let data = fs.readFileSync(example_path);
        let parser = new fastXmlParser.XMLParser();
        let result = parser.parse(data);

        console.log("examples ", example_path, path.basename(example, ".xml"));
        out.push({
          label: result.input.name,
          click(item, win, event) {
            // fs.readFile(example_path, (err, data) => {
            //     const parser = new fastXmlParser.XMLParser();
            //     const result = parser.parse(data);
            convertToString(result);
            // fastXmlParser.parseString(data, (err, result) => {
            console.log("import file", result);
            if (win) {
              // window.handleImport()
              win.webContents.send("importFile", {
                location: directory,
                file: result,
              });
            }
            // });
            // });
          },
        });
      });
    }
    // });
    return out;
  }

  getDefaultTemplate(window: MuproWindow): MenuItemConstructorOptions[] {
    const macOption: MenuItemConstructorOptions = {
      label: "test",
      submenu: [
        { role: "about" },
        { type: "separator" },
        { role: "services" },
        { type: "separator" },
        { role: "hide" },
        { role: "hideOthers" },
        { role: "unhide" },
        { type: "separator" },
        { role: "quit" },
      ],
    };
    const template: MenuItemConstructorOptions[] = [
      {
        label: "File",
        submenu: [
          {
            label: "import",
            click(item, win, event) {
              if (win) window.handleImport();
            },
          },
        ],
      },
      {
        label: "Edit",
        submenu: [
          {
            role: "cut",
            // accelerator: "CmdOrCtrl+X",
          },
          {
            role: "copy",
            // accelerator: "CmdOrCtrl+C",
          },
          {
            role: "paste",
            // accelerator: "CmdOrCtrl+V",
          },
        ],
      },
      {
        label: "View",
        submenu: [
          // { role: "reload" },
          { role: "forceReload" },
          { role: "toggleDevTools" },
          // { type: "separator" },
          // { role: "togglefullscreen" },
        ],
      },
      {
        label: "Examples",
        submenu: this.getExampleMenu(),
      },
      {
        role: "help",
        submenu: [
          {
            label: "Learn More",
            click: async () => {
              const { shell } = require("electron");
              await shell.openExternal(this.homepage);
            },
          },
          {
            label: "Check for updates",
            click: (item, win, event) => {
              // console.log("FeedURL",this.feedURL);
              if (win) {
                checkForUpdates(item, win, event);
              }
            },
          },
          {
            label: "Preferences",
            click(item, win, event) {
              console.log("Opening preference");
              if (win) {
                console.log("win exist");
                win.webContents.send("preferencesOpen", {
                  message: "testing",
                });
              }
            },
          },
          {
            label: "Register",
            click(item, win, event) {
              console.log("Opening register");
              if (win) {
                win.webContents.send("registerOpen", {
                  message: "testing",
                });
              }
            },
          },
        ],
      },
    ];
    if (isMac) {
      template.splice(0, 0, macOption);
      return template;
    } else {
      return template;
    }
  }
}

export { MuproMenu };
