import { contextBridge, desktopCapturer, ipcRenderer } from 'electron';

// main.ts passes the resolved API base URL (local sidecar port OR remote
// central server) via additionalArguments; parse it out here.
const API_URL_ARG = process.argv.find((a) => a.startsWith('--interviewiq-api-url='));
const API_BASE_URL = API_URL_ARG ? API_URL_ARG.split('=')[1] : 'http://localhost:8000';

contextBridge.exposeInMainWorld('electronAPI', {
  getSources: () => desktopCapturer.getSources({ types: ['window', 'screen'] }),
  platform: process.platform,
});

contextBridge.exposeInMainWorld('appConfig', {
  /** Resolved base URL for all shared-data fetch() calls. */
  getApiBaseUrl: () => API_BASE_URL,
  /** Current connection config incl. needsSetup flag (first-run gate). */
  getConfig: () => ipcRenderer.invoke('app:get-config'),
  /** Persist backendMode / remoteApiUrl (writes data/settings.json). */
  setConfig: (update: { backendMode?: string; remoteApiUrl?: string }) =>
    ipcRenderer.invoke('app:set-config', update),
  /** Recreate the window so a changed backend target takes effect. */
  restartWindow: () => ipcRenderer.invoke('app:restart-window'),
});

contextBridge.exposeInMainWorld('integrity', {
  /**
   * Runs port/process scans LOCALLY on this machine (native, in Electron's
   * main process). Never routed through any server — only the resulting
   * flags are uploaded by the renderer.
   */
  runLocalScan: () => ipcRenderer.invoke('integrity:local-scan'),
});
