import { app, BrowserWindow, ipcMain } from 'electron';
import * as path from 'path';
import { spawn, ChildProcess } from 'child_process';
import * as http from 'http';
import * as net from 'net';
import { loadConfig, needsSetup, saveConfig, AppConfig } from './config';
import { runLocalScan } from './integrity';

let mainWindow: BrowserWindow | null = null;
let pythonProcess: ChildProcess | null = null;

const isDev = process.argv.includes('--dev');
const PROJECT_ROOT = path.resolve(__dirname, '..', '..');
const MAX_POLL_ATTEMPTS = 30;
const POLL_INTERVAL_MS = 500;

function getFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.listen(0, () => {
      const address = server.address();
      if (address && typeof address === 'object') {
        const port = address.port;
        server.close(() => resolve(port));
      } else {
        server.close(() => reject(new Error('Failed to get free port')));
      }
    });
    server.on('error', reject);
  });
}

function waitForServer(port: number): Promise<void> {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const poll = () => {
      attempts++;
      if (attempts > MAX_POLL_ATTEMPTS) {
        reject(new Error(`Server on port ${port} did not start within ${MAX_POLL_ATTEMPTS * POLL_INTERVAL_MS / 1000}s`));
        return;
      }
      const req = http.get(`http://localhost:${port}/health`, (res: http.IncomingMessage) => {
        if (res.statusCode === 200) {
          resolve();
        } else {
          setTimeout(poll, POLL_INTERVAL_MS);
        }
      });
      req.on('error', () => setTimeout(poll, POLL_INTERVAL_MS));
      req.end();
    };
    poll();
  });
}

function killPythonProcess(): void {
  if (pythonProcess && !pythonProcess.killed) {
    // SIGTERM is unreliable on Windows; taskkill /T takes the whole child tree.
    if (process.platform === 'win32') {
      spawn('taskkill', ['/PID', String(pythonProcess.pid), '/T', '/F'], { windowsHide: true });
    } else {
      pythonProcess.kill('SIGTERM');
    }
    pythonProcess = null;
  }
}

/**
 * Where should the frontend send shared-data requests?
 *
 * - local mode: the FastAPI sidecar spawned below, on a random loopback port
 *   (unchanged behavior — single-machine / on-site use)
 * - remote mode: no sidecar; everything goes to the central deployed server.
 *   Integrity scans still run LOCALLY via integrity.ts and their results are
 *   POSTed to this same base URL by the renderer.
 */
async function resolveApiBaseUrl(config: AppConfig): Promise<{ baseUrl: string; spawnedPort: number | null }> {
  if (config.backendMode === 'remote') {
    let url = config.remoteApiUrl.replace(/\/+$/, '');
    if (!/^https?:\/\//.test(url)) url = `https://${url}`;
    return { baseUrl: url, spawnedPort: null };
  }

  const port = await getFreePort();
  console.log(`Starting backend on port ${port}...`);

  pythonProcess = spawn('python', ['-m', 'api.main', '--port', String(port)], {
    cwd: PROJECT_ROOT,
    stdio: 'inherit',
  });

  pythonProcess.on('error', (err: Error) => {
    console.error('Failed to start Python process:', err);
  });

  pythonProcess.on('exit', (code: number | null) => {
    console.log(`Python process exited with code ${code}`);
    pythonProcess = null;
  });

  await waitForServer(port);
  console.log('Backend is ready');
  return { baseUrl: `http://127.0.0.1:${port}`, spawnedPort: port };
}

function createWindow(baseUrl: string): BrowserWindow {
  const window = new BrowserWindow({
    width: 1280,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      // The renderer cannot read Node state directly (contextIsolation), so
      // the resolved API base URL travels in through preload's process.argv.
      additionalArguments: [`--interviewiq-api-url=${baseUrl}`],
    },
  });

  window.on('closed', () => {
    mainWindow = null;
    killPythonProcess();
  });

  return window;
}

function registerIpc(): void {
  ipcMain.handle('app:get-config', () => {
    const current = loadConfig();
    return { ...current, needsSetup: needsSetup(current) };
  });
  ipcMain.handle('app:set-config', (_event, update: Partial<AppConfig>) => {
    const next = saveConfig(update);
    return { ...next, needsSetup: needsSetup(next) };
  });
  ipcMain.handle('integrity:local-scan', () => runLocalScan());
  // Called after the setup screen / settings page changes backendMode or
  // remoteApiUrl: the injected API base URL lives in preload's argv, so a
  // fresh window (and sidecar decision) is required to apply it.
  ipcMain.handle('app:restart-window', async () => {
    killPythonProcess();
    await startApp();
  });
}

async function startApp(): Promise<void> {
  try {
    const config = loadConfig();
    console.log(`Backend mode: ${config.backendMode}${config.remoteApiUrl ? ` (${config.remoteApiUrl})` : ''}`);

    const { baseUrl } = await resolveApiBaseUrl(config);

    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.destroy();
      mainWindow = null;
    }

    mainWindow = createWindow(baseUrl);

    if (isDev) {
      mainWindow.loadURL('http://localhost:3000');
    } else {
      mainWindow.loadFile(path.join(PROJECT_ROOT, 'frontend', 'out', 'index.html'));
    }
  } catch (err) {
    console.error('Failed to start application:', err);
    app.quit();
  }
}

app.whenReady().then(() => {
  registerIpc();
  startApp();
});

app.on('will-quit', () => {
  killPythonProcess();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    startApp();
  }
});
