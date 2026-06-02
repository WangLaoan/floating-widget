"use strict";
const { app, BrowserWindow, ipcMain, Tray, Menu, nativeImage, } = require("electron");
const path = require("path");
let mainWindow = null;
let tray = null;
let isQuitting = false;
const WINDOW_WIDTH = 360;
const WINDOW_HEIGHT = 520;
function createWindow() {
    mainWindow = new BrowserWindow({
        width: WINDOW_WIDTH,
        height: WINDOW_HEIGHT,
        minWidth: 320,
        minHeight: 420,
        maxWidth: 480,
        maxHeight: 700,
        x: undefined,
        y: undefined,
        alwaysOnTop: true,
        transparent: true,
        frame: false,
        resizable: true,
        skipTaskbar: false,
        hasShadow: true,
        roundedCorners: true,
        backgroundColor: "#00000000",
        webPreferences: {
            preload: path.join(__dirname, "preload.js"),
            contextIsolation: true,
            nodeIntegration: false,
            sandbox: false,
        },
    });
    const isDev = process.argv.includes("--dev") || process.env.NODE_ENV === "development";
    if (isDev) {
        mainWindow.loadURL("http://localhost:5173");
    }
    else {
        mainWindow.loadFile(path.join(__dirname, "../renderer/index.html"));
    }
    mainWindow.on("close", (event) => {
        if (!isQuitting) {
            event.preventDefault();
            mainWindow?.hide();
        }
    });
    mainWindow.on("closed", () => {
        mainWindow = null;
    });
}
function createTray() {
    const size = 16;
    const buffer = Buffer.alloc(size * size * 4);
    for (let y = 0; y < size; y++) {
        for (let x = 0; x < size; x++) {
            const idx = (y * size + x) * 4;
            const cx = x - size / 2;
            const cy = y - size / 2;
            const dist = Math.sqrt(cx * cx + cy * cy);
            if (dist <= 6) {
                buffer[idx] = 56;
                buffer[idx + 1] = 189;
                buffer[idx + 2] = 248;
                buffer[idx + 3] = 255;
            }
            else if (dist <= 7) {
                const alpha = Math.max(0, Math.min(255, (7 - dist) * 255));
                buffer[idx] = 56;
                buffer[idx + 1] = 189;
                buffer[idx + 2] = 248;
                buffer[idx + 3] = Math.round(alpha);
            }
            else {
                buffer[idx + 3] = 0;
            }
        }
    }
    const icon = nativeImage.createFromBuffer(buffer, {
        width: size,
        height: size,
    });
    tray = new Tray(icon);
    const contextMenu = Menu.buildFromTemplate([
        {
            label: "显示 / 隐藏",
            click: () => {
                if (mainWindow?.isVisible()) {
                    mainWindow.hide();
                }
                else {
                    mainWindow?.show();
                }
            },
        },
        { type: "separator" },
        {
            label: "退出",
            click: () => {
                isQuitting = true;
                app.quit();
            },
        },
    ]);
    tray.setToolTip("估值温度");
    tray.setContextMenu(contextMenu);
    tray.on("double-click", () => {
        if (mainWindow?.isVisible()) {
            mainWindow.hide();
        }
        else {
            mainWindow?.show();
        }
    });
}
ipcMain.handle("window:hide", () => {
    mainWindow?.hide();
});
ipcMain.handle("window:minimize", () => {
    mainWindow?.minimize();
});
ipcMain.handle("window:close", () => {
    isQuitting = true;
    app.quit();
});
app.whenReady().then(() => {
    createWindow();
    createTray();
});
app.on("window-all-closed", () => {
    if (process.platform !== "darwin") {
        app.quit();
    }
});
app.on("activate", () => {
    if (mainWindow === null) {
        createWindow();
    }
    else {
        mainWindow.show();
    }
});
app.on("before-quit", () => {
    isQuitting = true;
});
//# sourceMappingURL=main.js.map