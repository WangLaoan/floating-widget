const e = require("electron");
console.log("type:", typeof e);
console.log("isArray:", Array.isArray(e));
console.log("first 5 keys:", Object.keys(e).slice(0, 10));
if (typeof e === 'object' && e !== null) {
  console.log("has contextBridge:", 'contextBridge' in e);
  console.log("has app:", 'app' in e);
  console.log("has ipcMain:", 'ipcMain' in e);
  // Try to find ipcMain
  for (const key of Object.keys(e)) {
    if (typeof e[key] === 'object' && e[key] !== null && 'handle' in e[key]) {
      console.log("Found handle in key:", key);
    }
  }
}
