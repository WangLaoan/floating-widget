const electron = require("electron");
console.log("electron keys:", Object.keys(electron).slice(0, 20));
console.log("ipcMain:", typeof electron.ipcMain);
console.log("app:", typeof electron.app);
