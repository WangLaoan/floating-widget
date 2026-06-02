// Resolve electron from the electron binary's built-in modules
const Module = require('module');
const originalResolve = Module._resolveFilename;

// Check what Module.globalPaths contains
console.log("globalPaths:", module.globalPaths);
console.log("process.resourcesPath:", process.resourcesPath);

// Try to find the real electron module
try {
  // In Electron, require('electron') should work natively
  const e = require('electron');
  console.log("require('electron') type:", typeof e);
} catch(err) {
  console.log("Error:", err.message);
}

// Check if process has electron-specific properties
console.log("process.type:", process.type);
console.log("process.versions.electron:", process.versions.electron);
