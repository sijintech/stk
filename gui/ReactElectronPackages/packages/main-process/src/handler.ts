import { app, BrowserWindow, dialog } from "electron";
// const { app, dialog, ipcMain, BrowserWindow } = require("electron");
import { autoUpdater } from "electron-updater";
// const { autoUpdater } = require("electron-updater");
import csv from "csvtojson";
import * as os from "os";
import * as sudoPrompt from "sudo-prompt";
// const csv = require("csvtojson");
// const os = require("os");
// const sudoPrompt = require("sudo-prompt");
// const isDev = require("electron-is-dev");
import * as fs from "fs";
import * as path from "path";
// const path = require("path");
// const fs = require("fs");
// import xml2js from 'xml2js';
import fastXmlParser from "fast-xml-parser";

import { ChildProcess, exec } from "child_process";
// const xmlParser = require("xml2js");
// const { exec } = require("child_process");

import type { PreferenceValue } from "./main-process";

interface GIFInfo {
  filePath: string;
  width: number;
  height: number;
  imgList: string[];
}

let pid: number;

function normalizeDriveLetterName(filePath: string): string {
  if (process.platform === "win32" && filePath) {
    return filePath.replace(
      /^([a-z]):/,
      ([driveLetter]) => driveLetter.toUpperCase() + ":"
    );
  } else {
    return filePath;
  }
}

function nudgeWindow(win: BrowserWindow) {
  //let win=BrowserWindow.getFocusedWindow();
  let gg = win.getBounds();
  console.log("size 1", gg, win.isMaximized());
  // if(win.isMaximized){
  //   win.unmaximize();
  // }

  // win.setPosition(p[0],p[1]);
  console.log(gg);
  win.setBounds({ width: gg.width - 1, height: gg.height - 1 });
  win.setBounds({ width: gg.width, height: gg.height });
  let curB = win.getBounds();
  let heightDiff = curB.height - gg.height;
  if (heightDiff !== 0) {
    console.log("size2 ", win.getBounds(), win.getContentSize());
    win.setBounds({ width: gg.width, height: gg.height - heightDiff });
    console.log("size3 ", win.getBounds(), win.getContentSize());
  }
}

function getFilesFromDir(dir: string, fileTypes: string[]): string[] {
  var filesToReturn: string[] = [];
  function walkDir(currentPath: string) {
    var files = fs.readdirSync(currentPath);
    // console.log("files", files);
    for (var i in files) {
      var curFile = path.join(currentPath, files[i]);
      if (
        fs.statSync(curFile).isFile() &&
        fileTypes.indexOf(path.extname(curFile)) != -1
      ) {
        filesToReturn.push(path.basename(curFile));
      } else if (fs.statSync(curFile).isDirectory()) {
        walkDir(curFile);
      }
    }
  }
  walkDir(dir);
  return filesToReturn;
}

// function fromDir(start: string, filter: string): string[] {
//     //console.log('Starting from dir '+startPath+'/');
//     let fileList = [];
//     let startPath = path.dirname(start);
//     if (!fs.existsSync(startPath)) {
//         console.log("no dir ", startPath);
//         return [];
//     }

//     var files = fs.readdirSync(startPath).sort();
//     for (var i = 0; i < files.length; i++) {
//         var filename = path.join(startPath, files[i]);
//         var stat = fs.lstatSync(filename);
//         if (stat.isDirectory()) {
//             fromDir(filename, filter); //recurse
//         } else if (filename.indexOf(filter) >= 0) {
//             fileList.push(path.basename(filename));
//             // console.log('-- found: ',filename);
//         }
//     }
//     return fileList;
// }

function startSimulation(
  win: BrowserWindow,
  fileLoc: string,
  exePath: string
): number {
  console.log("start simulation in the electron side");
  // console.log("listing the  file location",fileLoc,app.getAppPath (),app.getPath ('exe'));
  let spawn = require("child_process").spawn;
  console.log("the os type", os.type(), fileLoc, exePath);
  //////////////
  process.env.MUPROROOT = app.isPackaged
    ? path.join(path.dirname(app.getAppPath()), "..")
    : app.getAppPath();
  ///////////////
  let bat: ChildProcess;
  if (os.type() === "Windows_NT") {
    bat = spawn(
      "cmd.exe",
      [
        "/c", // Argument for cmd.exe to carry out the specified script
        exePath,
      ],
      {
        cwd: fileLoc,
      }
    );
  } else {
    console.log("not windows");
    bat = spawn(exePath, { cwd: fileLoc });
  }
  let pid: number = -1;
  if (bat.pid) {
    pid = bat.pid;
  }
  if (bat.stdout) {
    bat.stdout.on("data", (data) => {
      // console.log(`stdout: ${data}`);
      win.webContents.send("console", `${data}`.split(/\r?\n/));
    });
  }
  if (bat.stderr) {
    bat.stderr.on("data", (data) => {
      // console.error(`stderr: ${data}`);
      win.webContents.send("console", `${data}`.split(/\r?\n/));
    });
  }

  bat.on("exit", (code) => {
    console.log(`Child exited with code ${code}`);
  });
  return pid;
}

function killSimulation(pid: number): number {
  console.log("kill simulation received");
  console.log("killing pid", pid);
  var spawn = require("child_process").spawn;
  if (os.type() === "Windows_NT") {
    spawn("taskkill", ["/pid", pid, "/f", "/t"]);
  } else {
    spawn("kill", ["-9", pid]);
  }
  console.log("process killed");
  return pid;
}

function obtainImage(win: BrowserWindow) {
  return dialog.showSaveDialogSync(win, {
    filters: [{ name: "Image", extensions: ["png"] }],
    properties: ["showOverwriteConfirmation", "createDirectory"],
  });
}

function writeFile(name: string, file: string) {
  const buf = Buffer.from(file, "base64");
  fs.writeFile(name, buf, () => {});
}

function obtainGIF(win: BrowserWindow): string | undefined {
  let name = dialog.showSaveDialogSync(win, {
    filters: [{ name: "Image", extensions: ["gif"] }],
    properties: ["showOverwriteConfirmation", "createDirectory"],
  });
  console.log("obtain gif", name);
  return name;
}

function writeGIF(gif: GIFInfo) {
  let name = gif.filePath;
  let folder = path.join(path.dirname(name), path.basename(name).split(".")[0]);
  let pngName = "";
  let count = Object.keys(gif.imgList).length;
  // console.log(count,args);
  fs.mkdir(folder, () => {
    console.log("folder", folder, count);
    for (let index = 1; index < count; index++) {
      pngName = path.join(folder, index + ".png");
      console.log("pngName", pngName);
      fs.writeFile(pngName, Buffer.from(gif.imgList[index], "base64"), () => {
        console.log("name", name, folder);
        const GIFEncoder = require("gifencoder");
        const encoder = new GIFEncoder(gif.width, gif.height);
        const pngFileStream = require("png-file-stream");

        const stream = pngFileStream(folder + "/?.png")
          .pipe(
            encoder.createWriteStream({
              repeat: 0,
              delay: 500,
              quality: 10,
            })
          )
          .pipe(fs.createWriteStream(name));

        stream.on("finish", function () {
          // Process generated GIF
          console.log("The gif write finished");
        });
      });
    }
  });
}

function convertToString(myObj: any) {
  Object.keys(myObj).forEach(function (key) {
    typeof myObj[key] == "object"
      ? convertToString(myObj[key])
      : (myObj[key] = String(myObj[key]));
  });
}

function writeInput(fileLocation: string, input: object) {
  // console.log("event", event);
  // console.log("args", args);
  console.log("file location", fileLocation, JSON.stringify(input));

  const builder = new fastXmlParser.XMLBuilder({ format: true });
  const xmlContent = builder.build({ input: input });
  console.log("the xml", xmlContent);
  fs.writeFile(
    // path.join(fileLocation, "input.xml"),
    fileLocation,
    xmlContent,
    () => {}
  );
  return 1;
}

// ipcMain.handle("writeSecret", (event, ...args) => {
//   console.log("event", event);
//   console.log("args", args);
//   // console.log("file location", args[0].fileLocation, "input.in");
//   // let fromFile = args[0].fromFile ? 1:0;
//   // console.log("current input", args[0]);
//   // var builder = new xmlParser.Builder();

function cmdWriteFile(
  content: string,
  dir: string,
  moreCMD?: string[]
): string {
  let command = "";
  if (process.platform === "win32") {
    command = '<nul set /p="' + content + '">"' + dir + '"';
    if (moreCMD) {
      for (let index = 0; index < moreCMD.length; index++) {
        const element = moreCMD[index];
        command = command + ' && "' + element + '"';
      }
    }
    // + secretPath
  } else {
    command = "printf '" + content + "' > \"" + dir + '"';
    if (moreCMD) {
      for (let index = 0; index < moreCMD.length; index++) {
        const element = moreCMD[index];
        command = command + " && " + element;
      }
    }
  }
  return command;
}

function checkLicFile(licPath: string) {
  if (fs.existsSync(licPath)) {
    const lic = fs.readFileSync(licPath, { encoding: "utf8", flag: "r" });
    const last2 = lic.slice(-2);
    if (last2 === "==") {
      return true;
    } else {
      return false;
    }
  } else {
    return false;
  }
}
function writeSecret(
  win: BrowserWindow,
  exePath: string,
  exe: string,
  user_register: string
) {
  let secretPath = path.join(exePath, "secret");

  let licPath = path.join(exePath, "license.lic");
  // let command =
  //     '<nul set /p="' +
  //     user_register +
  //     '">"' +
  //     secretPath +
  //     '" & "' +
  //     path.join(exePath, exe) +
  //     '"'; // + secretPath
  // console.log(command);
  // console.log(exePath,exe,exeName,args)
  let command = "";
  if (process.platform === "win32") {
    command = cmdWriteFile(user_register, secretPath, [
      'type nul >> "' + licPath + '"',
      'del "' + licPath + '"',
      path.join(exePath, exe),
    ]);
  } else {
    command = cmdWriteFile(user_register, secretPath, [
      "touch " + licPath,
      "rm " + licPath,
      path.join(exePath, exe),
    ]);
  }
  console.log("secret command ", command);
  exec(command, (error, stdout, stderr) => {
    win.webContents.send(
      "console",
      "First try to write secret file without admin privilege"
    );

    if (!fs.existsSync(secretPath)) {
      console.log("Secret couldn't be generated");
      win.webContents.send(
        "console",
        "Secret couldn't be generated, now try with admin privilege"
      );

      sudoPrompt.exec(command, { name: "MUPRO" }, (error, stdout, stderr) => {
        if (fs.existsSync(secretPath) && fs.existsSync(licPath)) {
          if (checkLicFile(licPath)) {
            win.webContents.send(
              "console",
              "Secret file and license.lic successfully generated"
            );
          } else {
            win.webContents.send(
              "console",
              "The content of license.lic seems not correct, please check the license.lic file."
            );
          }
        } else {
          if (stdout) {
            console.log("runProcessElevated", stdout);
            win.webContents.send("console", "stdout");
            win.webContents.send("console", stdout.toString());
          }
          if (stderr) {
            console.log("runProcessElevated", stderr);
            win.webContents.send("console", "stderr");
            win.webContents.send("console", stderr.toString());
          }
          if (error) {
            console.log(error);
            win.webContents.send("console", "error");
            win.webContents.send("console", "error");
          }

          if (!fs.existsSync(secretPath)) {
            console.log("Secret still couldn't be generated");
            win.webContents.send(
              "console",
              "Secret still couldn't be generated"
            );
          }

          if (!fs.existsSync(licPath)) {
            console.log("license.lic file is not generated");
            win.webContents.send(
              "console",
              "license.lic file is not generated"
            );
          } else {
            win.webContents.send("console", "license.lic file generated");
          }
        }
      });
    } else {
      win.webContents.send("console", "Secret file generated");
      if (!fs.existsSync(licPath)) {
        console.log("license.lic file is not generated");
        win.webContents.send("console", "license.lic file is not generated");
        if (error) {
          console.log("Error", error);
          win.webContents.send("console", error.toString());
        }
        if (stdout) {
          console.log("Stdout", stdout);
          win.webContents.send("console", stdout.toString());
        }
        if (stderr) {
          console.log("stderr", stderr);
          win.webContents.send("console", stderr.toString());
        }
      } else {
        if (checkLicFile(licPath)) {
          win.webContents.send("console", "license.lic file generated");
        } else {
          win.webContents.send(
            "console",
            "Please check the content of license.lic file, there probably are some problems."
          );
        }
      }
    }
  });

  return 1;
}

function writePreferences(
  win: BrowserWindow,
  preferencesPath: string,
  preferences: PreferenceValue
) {
  // let command =
  //     '<nul set /p="' + JSON.stringify(preferences) + '">"' + preferencesPath;

  let command = cmdWriteFile(JSON.stringify(preferences), preferencesPath);
  console.log("preference command ", command);
  exec(command, (error, stdout, stderr) => {
    win.webContents.send(
      "console",
      "First try to write preferences file without admin privilege"
    );

    if (!fs.existsSync(preferencesPath)) {
      console.log("Preferences file couldn't be generated");
      win.webContents.send(
        "console",
        "Preferences file couldn't be generated, now try with admin privilege"
      );

      sudoPrompt.exec(command, { name: "MUPRO" }, (error, stdout, stderr) => {
        if (fs.existsSync(preferencesPath)) {
          win.webContents.send(
            "console",
            "Preferences file successfully generated"
          );
        } else {
          if (stdout) {
            console.log("runProcessElevated", stdout);
            win.webContents.send("console", "stdout");
            win.webContents.send("console", stdout.toString());
          }
          if (stderr) {
            console.log("runProcessElevated", stderr);
            win.webContents.send("console", "stderr");
            win.webContents.send("console", stderr.toString());
          }
          if (error) {
            console.log(error);
            win.webContents.send("console", "error");
            win.webContents.send("console", "error");
          }

          if (!fs.existsSync(preferencesPath)) {
            console.log("Preferences file still couldn't be generated");
            win.webContents.send(
              "console",
              "Preferences files still couldn't be generated, please contact developer"
            );
          }
        }
      });
    } else {
      win.webContents.send("console", "Preferences file generated");
    }
  });

  return 1;
}

function readPreferences(
  win: BrowserWindow,
  preferencesPath: string
): PreferenceValue {
  let defaultValue: PreferenceValue = {
    hide_basic: false,
    hide_material: false,
    hide_structure: false,
  };
  if (fs.existsSync(preferencesPath)) {
    // const stat = fs.statSync(preferencesPath);
    // if (stat && stat.isFile()) {
    try {
      win.webContents.send(
        "console",
        "Read preferences from " + preferencesPath
      );
      let data = fs.readFileSync(preferencesPath, "utf8");
      win.webContents.send("console", "Successfully load preferences ");

      let out = JSON.parse(data);
      win.webContents.send("console", JSON.stringify(out));
      return out;
    } catch (e) {
      win.webContents.send(
        "console",
        "Some errors appear when loading preferences ",
        e
      );
      return defaultValue;
    }
  } else {
    win.webContents.send(
      "console",
      "The preference file does not exist, using default preferences."
    );
    console.log("The preference file does not exist");
    return defaultValue;
  }
}

function readTextFile(path: string): string {
  return fs.readFileSync(path, "utf8");
}

async function readCSV(path: string): Promise<object> {
  console.log("read csv", path);
  const jsonArray = await csv().fromFile(path);
  return new Promise((resolve) => {
    resolve(jsonArray);
  });
}

export {
  nudgeWindow,
  startSimulation,
  writeSecret,
  obtainImage,
  writeFile,
  writePreferences,
  readPreferences,
  getFilesFromDir,
  normalizeDriveLetterName,
  readTextFile,
  writeInput,
  readCSV,
  obtainGIF,
  killSimulation,
  writeGIF,
  convertToString,
  PreferenceValue,
};

export type { GIFInfo };
