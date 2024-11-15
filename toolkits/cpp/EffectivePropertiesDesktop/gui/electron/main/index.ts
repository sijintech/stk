import { app, BrowserWindow, shell, ipcMain } from 'electron'
import { release } from 'os'
import { join } from 'path'
import { MuproWindow, MuproMenu, isMac, appversion, appname, AppOptions } from '@mupro/main-process/src';
// import { AppOptions } from '@mupro/main-process/src/main-process';
import * as path from 'path';
import * as os from 'os';
import * as log from "electron-log";

log.info("App version: ", appversion);
log.info("App name   : ", appname);
log.info("Is Mac     :", isMac);



// Disable GPU Acceleration for Windows 7
if (release().startsWith('6.1')) app.disableHardwareAcceleration()

// Set application name for Windows 10+ notifications
if (process.platform === 'win32') app.setAppUserModelId(app.getName())

if (!app.requestSingleInstanceLock()) {
  app.quit()
  process.exit(0)
}

process.env['ELECTRON_DISABLE_SECURITY_WARNINGS'] = 'true'

export const ROOT_PATH = {
  // /dist
  dist: join(__dirname, '../..'),
  // /dist or /public
  public: join(__dirname, app.isPackaged ? '../..' : '../../../public'),
}

// let win: BrowserWindow | null = null
// Here, you can also use other preload
const preload = join(__dirname, '../preload/index.js')
// 🚧 Use ['ENV_NAME'] avoid vite:define plugin
// const url = `http://${process.env['VITE_DEV_SERVER_HOST']}:${process.env['VITE_DEV_SERVER_PORT']}`
const url = `${process.env['VITE_DEV_SERVER_URL']}`
const indexHtml = join(ROOT_PATH.dist, 'index.html')

// async function createWindow() {
//   win = new BrowserWindow({
//     title: 'Main window',
//     icon: join(ROOT_PATH.public, 'favicon.svg'),
//     webPreferences: {
//       preload,
//       nodeIntegration: true,
//       contextIsolation: false,
//     },
//   })

//   if (app.isPackaged) {
//     win.loadFile(indexHtml)
//   } else {
//     win.loadURL(url)
//     win.webContents.openDevTools()
//   }

// }

// app.whenReady().then(createWindow);

const loadURL = app.isPackaged ? indexHtml : url;

let exe = "effprop";
if (os.type() === "Windows_NT") {
  exe = "effprop.exe";
}

let exePath = app.isPackaged ? path.join(path.dirname(app.getAppPath()), "..") : app.getAppPath();

let options: AppOptions = {
  name: ["Effective Properties", appversion].join(" "),
  version: appversion,
  loadURL: loadURL,
  exePath: exePath,
  exe: exe,
  homepage: ""
};

app.whenReady().then(() => {
  console.log("ready");
  let win = new MuproWindow(options);
  global.win = win
  new MuproMenu(options, win);

  // autoUpdater.checkForUpdatesAndNotify();
});

app.on('window-all-closed', () => {
  // win = null
  global.win = null
  if (process.platform !== 'darwin') app.quit()
})
