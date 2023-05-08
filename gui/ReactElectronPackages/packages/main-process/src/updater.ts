import { BrowserWindow, dialog, MenuItem, KeyboardEvent, app } from "electron";
import { autoUpdater } from "electron-updater";
import * as log from "electron-log";

let updater: MenuItem;
autoUpdater.logger = log;
// autoUpdater.logger.transports.file.level = "info";
autoUpdater.autoDownload = false;

let globalFocusedWindow: BrowserWindow;

autoUpdater.on("error", (error) => {
  dialog.showErrorBox(
    "Error: ",
    error == null ? "unknown" : (error.stack || error).toString()
  );
});

autoUpdater.on("checking-for-update", () => {
  globalFocusedWindow.webContents.send(
    "console",
    "Checking for updated, please wait"
  );
});

autoUpdater.on("update-available", () => {
  globalFocusedWindow.webContents.send("console", "Update available");
  const buttonIndex = dialog.showMessageBoxSync({
    type: "info",
    title: "Found Updates",
    message: "Found updates, do you want update now?",
    buttons: ["Yes", "No"],
    noLink: true,
  });
  // console.log(buttonIndex);
  // .then((buttonIndex) => {
  console.log("choose ", buttonIndex);
  globalFocusedWindow.webContents.send("console", "Your choice ", buttonIndex);
  if (buttonIndex === 0) {
    console.log("download update");
    autoUpdater.downloadUpdate();
  } else {
    console.log("don't download");

    updater.enabled = true;
    // updater = null;
  }
  // });
});

autoUpdater.on("update-not-available", () => {
  dialog.showMessageBox({
    title: "No Updates",
    message: "Current version is up-to-date.",
  });
  updater.enabled = true;
  // updater = null;
});

autoUpdater.on("update-downloaded", () => {
  dialog
    .showMessageBox({
      title: "Install Updates",
      message: "Updates downloaded, application will be quit for update...",
    })
    .then(() => {
      setTimeout(() => {
        autoUpdater.quitAndInstall();
        app.exit();
      }, 2000);
    });
});

autoUpdater.on("download-progress", (progressObj) => {
  let log_message = "Download speed: " + progressObj.bytesPerSecond;
  log_message = log_message + " - Downloaded " + progressObj.percent + "%";
  log_message =
    log_message +
    " (" +
    progressObj.transferred +
    "/" +
    progressObj.total +
    ")";
  console.log("downloading ", log_message);
  globalFocusedWindow.webContents.send("console", log_message);
});

function checkForUpdates(
  menuItem: MenuItem,
  focusedWindow: BrowserWindow,
  event: KeyboardEvent
) {
  updater = menuItem;
  updater.enabled = false;
  //   autoUpdater.setFeedURL(feedURL)
  globalFocusedWindow = focusedWindow;
  focusedWindow.webContents.send("console", "Start to check for update");

  autoUpdater.checkForUpdatesAndNotify();
}

export { checkForUpdates };
