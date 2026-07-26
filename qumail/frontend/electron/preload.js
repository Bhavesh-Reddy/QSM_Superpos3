// contextIsolation is on and nodeIntegration is off (see main.js); the
// renderer only ever talks to the backend over HTTP, so no privileged API
// needs to be bridged here yet.
const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("qumail", {
  version: process.env.npm_package_version ?? "0.0.0",
});
